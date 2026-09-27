# -*- coding: utf-8 -*-
"""Sentry (plano grátis), DESLIGADO por padrão — o app guarda dado de saúde.

`config/observabilidade.opcoes_do_sentry` e `ligar_sentry` são o par: o
primeiro trava as opções que existem para NÃO vazar corpo de pedido, variável
local ou performance detalhada de gente que guarda peso e treino; o segundo é
o interruptor — sem `SENTRY_DSN`, `sentry_sdk` nem é importado, porque uma
dependência nova que nunca é chamada ainda é risco (CVE de supply chain) se
estiver sempre carregada.

O antes-de-enviar existe porque a URL e a query string de um pedido podem
carregar o token do disparo pontual de lembretes, o token de redefinição de
senha (`/senha/nova/<uid>/<token>/`, três horas de acesso à conta) e o
`code=`/`state=` do OAuth do Google — os mesmos que `PADROES` já redige do
log comum (achado da revisão de 27/09/2026: a primeira versão só cobria
`/externo/`). O antes-de-breadcrumb existe porque toda requisição de saída
(inclusive o `webpush`, que posta no endpoint da assinatura — um
identificador por aparelho) deixa rastro por padrão.
"""
import json
import subprocess
import sys
from unittest import mock

import sentry_sdk
from sentry_sdk.transport import Transport

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config import observabilidade
from config.settings import BASE_DIR
from config.wsgi import application as _aplicacao_wsgi

DSN_FALSO = "https://chave@o0.ingest.sentry.io/0"


class SemDSNONadaAcontece(SimpleTestCase):
    """Sem DSN o app continua rodando exatamente como hoje — sem Sentry."""

    def test_ligar_sentry_sem_dsn_devolve_falso(self):
        self.assertFalse(observabilidade.ligar_sentry("", "producao", None))

    def test_sem_dsn_sentry_sdk_nunca_e_importado(self):
        """Prova num subprocesso limpo: se o módulo já tivesse `import
        sentry_sdk` no topo (em vez de dentro do `if dsn:`), este teste
        pegaria — mesmo sem nunca chamar `ligar_sentry` com DSN."""
        codigo = (
            "import sys, config.observabilidade as o\n"
            "o.ligar_sentry('', 'producao', None)\n"
            "print('sentry_sdk' in sys.modules)\n"
        )
        p = subprocess.run(
            [sys.executable, "-c", codigo],
            capture_output=True, text=True, cwd=str(BASE_DIR),
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "False")


class OpcoesDoSentryTravamAPrivacidade(SimpleTestCase):
    """Um log de saúde e dieta é dado sensível — o Sentry não pode virar o
    vazamento que `config/observabilidade.py` já evita no logging comum."""

    def test_as_quatro_opcoes_de_privacidade(self):
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)

        self.assertIs(opcoes["send_default_pii"], False)
        self.assertEqual(opcoes["max_request_body_size"], "never")
        self.assertIs(opcoes["include_local_variables"], False)
        self.assertEqual(opcoes["traces_sample_rate"], 0)

    def test_o_dsn_e_o_ambiente_passam_direto(self):
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "staging", None)

        self.assertEqual(opcoes["dsn"], DSN_FALSO)
        self.assertEqual(opcoes["environment"], "staging")

    def test_ambiente_vazio_vira_producao(self):
        """`NUTRIPLAN_AMBIENTE` é vazio em produção (ver `config/ambiente.py`)
        — sem esta troca, todo evento de produção chegaria marcado com o
        ambiente em branco."""
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "", None)

        self.assertEqual(opcoes["environment"], "producao")

    def test_release_e_o_commit_curto_ou_none(self):
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", "abcdef0")
        self.assertEqual(opcoes["release"], "abcdef0")

        sem_versao = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        self.assertIsNone(sem_versao["release"])


class AntesDeEnviarRedigeURLEQueryString(SimpleTestCase):
    """O mesmo que `PADROES` redige do log comum não pode sobreviver dentro
    de um evento do Sentry — em `request.url` E em `request.query_string`.

    Achado da revisão de 27/09/2026: a primeira versão só cobria `/externo/`
    (um regex próprio, mais estreito que `PADROES`) e deixava vazar o token
    de redefinição de senha e o `code=`/`state=` do OAuth do Google. Agora é
    `redigir` direto — a mesma lista, sem uma segunda cópia dela."""

    def test_apaga_o_token_da_url_de_externo(self):
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        antes_de_enviar = opcoes["before_send"]
        evento = {
            "request": {
                "url": "https://nutriplan-xxfn.onrender.com/tarefas/lembretes/externo/abc123token/",
            },
        }

        resultado = antes_de_enviar(evento, {})

        self.assertEqual(
            resultado["request"]["url"],
            "https://nutriplan-xxfn.onrender.com/tarefas/lembretes/externo/[REDIGIDO]/",
        )

    def test_apaga_o_token_de_redefinicao_de_senha_da_url(self):
        """`/conta/senha/nova/<uid>/<token>/` dá acesso à conta por três
        horas (o mesmo comentário urgente de `PADROES`) — um 500 nessa view
        não pode entregar o token a um terceiro fora do Brasil."""
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        antes_de_enviar = opcoes["before_send"]
        evento = {
            "request": {
                "url": "https://nutriplan-xxfn.onrender.com/conta/senha/nova/MQ/abc-123-token/",
            },
        }

        resultado = antes_de_enviar(evento, {})

        self.assertNotIn("abc-123-token", resultado["request"]["url"])

    def test_apaga_code_e_state_da_query_string_do_callback_do_google(self):
        """O callback do Google já quebrou em produção (`ModuleNotFoundError`
        na verificação do id_token — ver o comentário em requirements.txt); um
        500 ali não pode expor `code`/`state` na query string do evento."""
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        antes_de_enviar = opcoes["before_send"]
        evento = {
            "request": {
                "url": "https://nutriplan-xxfn.onrender.com/contas/google/login/callback/",
                "query_string": "code=SEGREDO-DE-USO-UNICO&state=abc123",
            },
        }

        resultado = antes_de_enviar(evento, {})

        self.assertNotIn("SEGREDO-DE-USO-UNICO", resultado["request"]["query_string"])
        self.assertNotIn("abc123", resultado["request"]["query_string"])

    def test_evento_sem_request_nao_quebra(self):
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        antes_de_enviar = opcoes["before_send"]

        self.assertEqual(antes_de_enviar({}, {}), {})

    def test_apaga_todos_os_cabecalhos_do_pedido(self):
        """Achado do evento de teste real em 27/09/2026 (NUTRIPLAN-1):
        `Cf-Connecting-Ip` — o IP de quem usa o app, que o Cloudflare na
        frente do Render acrescenta — chegou ao Sentry inteiro, porque
        `send_default_pii=False` só reconhece nomes como Authorization,
        Cookie e X-Forwarded-For, não esse. IP é dado pessoal pela LGPD, e
        o cabeçalho não serve para depurar este app: a saída é não mandar
        cabeçalho nenhum, não ampliar uma lista que sempre vai ficar atrás
        de um nome novo de proxy."""
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        antes_de_enviar = opcoes["before_send"]
        evento = {
            "request": {
                "url": "https://nutriplan-xxfn.onrender.com/hoje/",
                "headers": {
                    "Cf-Connecting-Ip": "201.0.0.1",
                    "X-Forwarded-For": "201.0.0.1",
                    "True-Client-Ip": "201.0.0.1",
                    "User-Agent": "curl",
                },
            },
        }

        resultado = antes_de_enviar(evento, {})

        self.assertNotIn("headers", resultado["request"])


class BeforeBreadcrumbDescartaHttpDeSaida(SimpleTestCase):
    """Breadcrumb de HTTP de saída carrega o endpoint de push — um
    identificador por aparelho — e não pode viajar num evento do Sentry."""

    def test_descarta_breadcrumb_de_categoria_httplib(self):
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", None)
        before_breadcrumb = opcoes["before_breadcrumb"]
        crumb = {"category": "httplib", "data": {"url": "https://fcm.googleapis.com/fcm/send/abc123"}}

        self.assertIsNone(before_breadcrumb(crumb, {}))


class ComDSNSentrySdkEIniciado(SimpleTestCase):
    """Com DSN, `ligar_sentry` de fato liga — chama `sentry_sdk.init` com
    exatamente as opções travadas acima, e não uma cópia divergente delas."""

    def test_ligar_sentry_chama_init_com_as_opcoes(self):
        modulo_falso = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"sentry_sdk": modulo_falso}):
            ligou = observabilidade.ligar_sentry(DSN_FALSO, "producao", "abcdef0")

        self.assertTrue(ligou)
        modulo_falso.init.assert_called_once()
        opcoes_esperadas = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", "abcdef0")
        # `before_send`/`before_breadcrumb` são funções de MÓDULO — o mesmo
        # objeto em toda chamada de `opcoes_do_sentry` — então comparar o
        # dict inteiro por igualdade já prova que NENHUMA opção diverge,
        # sem precisar de um laço que ignore as funções.
        self.assertEqual(modulo_falso.init.call_args.kwargs, opcoes_esperadas)


class _TransporteCapturador(Transport):
    """Transporte de verdade do SDK (não um mock) que guarda o evento em
    memória em vez de mandar pela rede — é o gancho que deixa inspecionar o
    que o PIPELINE inteiro do `sentry_sdk` monta, e não só a função isolada
    que os testes acima já cobrem."""

    def __init__(self):
        self.eventos = []

    def capture_envelope(self, envelope):
        evento = envelope.get_event()
        if evento is not None:
            self.eventos.append(evento)


class PipelineDeVerdadeNaoLevaCabecalhoAoSentry(SimpleTestCase):
    """Achado de 27/09/2026 (NUTRIPLAN-1): os testes de
    `AntesDeEnviarRedigeURLEQueryString` provam a FUNÇÃO `before_send`
    isolada — quem de fato PÕE `url`/`method`/`headers`/`env` no evento é o
    `SentryWsgiMiddleware` do próprio SDK, instalado por cima de
    `WSGIHandler.__call__` (a classe que `config/wsgi.py` usa).

    Por isso este teste NÃO usa `self.client` (o client de teste do Django):
    ele roda em cima de `ClientHandler`, uma classe IRMÃ de `WSGIHandler` —
    não filha —, então o middleware do SDK nunca entra em cena por ali.
    MEDIDO: um `self.client.post(...)` chega ao `before_send` com
    `event["request"]` só com a chave `data`; sem `headers`, sem `url`, com
    ou sem o `pop("headers")` do fix. Um teste "e2e" com `self.client`
    passaria mesmo sabotado — o exato risco que este arquivo já nomeia
    noutro comentário ("passa pelo motivo errado"). Este teste chama
    `config.wsgi.application` diretamente com um environ de verdade
    (`RequestFactory`), o mesmo objeto que o Render serve em produção —
    e SÓ assim o cabeçalho chega a existir no evento para o `before_send`
    ter o que apagar.
    """

    def setUp(self):
        self.token = "token-de-ensaio-sentry-e2e"
        self.transporte = _TransporteCapturador()
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "producao", "abc1234")
        opcoes["transport"] = self.transporte
        sentry_sdk.init(**opcoes)

    def tearDown(self):
        # Devolve o SDK ao estado DESLIGADO de antes deste teste. Sem isto,
        # todo teste depois deste — neste arquivo ou em qualquer outro,
        # `config.test_sentry` roda no mesmo processo dos demais — herdaria
        # uma integração do Django ligada e um transporte fake capturando
        # eventos que ninguém foi ler.
        sentry_sdk.get_client().close()
        sentry_sdk.init()

    def _post_pelo_wsgi_de_verdade(self, **cabecalhos):
        with override_settings(NUTRIPLAN_TAREFAS_TOKEN=self.token):
            requisicao = RequestFactory().post(
                reverse("erro_controlado"),
                HTTP_AUTHORIZATION="Bearer " + self.token,
                **cabecalhos,
            )
            status = {}

            def start_response(codigo, headers, exc_info=None):
                status["codigo"] = codigo

            # `raise_request_exception=False` de produção: o WSGI não
            # reergue, devolve a resposta 500 — e é NESSE caminho
            # (`got_request_exception`) que o Django integration do SDK
            # captura o evento.
            b"".join(_aplicacao_wsgi(requisicao.environ, start_response))
            return status["codigo"]

    def test_pedido_real_com_erro_nao_leva_cabecalho_nem_ip_ao_evento(self):
        codigo = self._post_pelo_wsgi_de_verdade(
            HTTP_CF_CONNECTING_IP="201.0.0.99",
            HTTP_X_FORWARDED_FOR="201.0.0.99",
            HTTP_TRUE_CLIENT_IP="201.0.0.99",
            HTTP_USER_AGENT="curl/8",
        )

        self.assertTrue(codigo.startswith("500"))
        self.assertEqual(len(self.transporte.eventos), 1)
        evento = self.transporte.eventos[0]
        self.assertNotIn("headers", evento["request"])
        self.assertNotIn("201.0.0.99", json.dumps(evento))


class OTermoDaBuscaNaoSaiNoEventoSerializadoTests(TestCase):
    """O que a pessoa COMEU não vai para o Sentry — medido no evento que o SDK
    de VERDADE monta, serializado, e não num dicionário escrito à mão.

    Decisão do dono (27/09/2026, revisão do PR #162): a busca de "comi outra
    coisa" continua GET (`/alimentos/buscar/?q=cerveja`), e um 500 nela levava
    o termo em `request.url` e `request.query_string` para fora do Brasil.
    `redigir` passou a conhecer `q`, e `before_send` já passa por `redigir`.

    Os outros testes desta página chamam `before_send` com um evento montado à
    mão, e isso não prova que o SDK põe o termo onde o dicionário à mão diz:
    aqui o pedido passa pela integração do Django, o evento é capturado pelo
    transporte e serializado em JSON, e a asserção é sobre o TEXTO que sairia.
    O controle positivo roda o mesmo pedido sem `before_send` e ACHA o termo —
    senão "não achei" poderia ser o SDK que simplesmente não o anexa.
    """

    TERMO = "cerveja-artesanal-ipa"

    def _evento_serializado(self, com_before_send):
        """O pedido passa pelo `WSGIHandler` de verdade — como o gunicorn o
        chama —, porque é ali que a integração do Django põe `request.url` e
        `request.query_string` no evento. O `Client` de teste usa outro
        handler, e com ele o evento sai com `"request": {"data": ""}` — o
        controle positivo abaixo foi o que mostrou isso: sem ele, "o termo não
        está no evento" teria passado por o SDK nem ter anexado o pedido."""
        import json

        import sentry_sdk
        from django.conf import settings
        from django.core.handlers.wsgi import WSGIHandler
        from django.core.signals import request_finished, request_started
        from django.db import close_old_connections
        from django.test import Client, RequestFactory
        from django.urls import reverse

        from plans.tests import create_complete_user

        capturados = []
        opcoes = observabilidade.opcoes_do_sentry(DSN_FALSO, "teste", None)
        if not com_before_send:
            opcoes.pop("before_send")
        sentry_sdk.init(**opcoes, transport=capturados.append)
        self.addCleanup(sentry_sdk.init)  # sem DSN: o cliente volta a desligado

        user = create_complete_user(email="sentry-%s@exemplo.com" % com_before_send)
        sessao = Client()
        sessao.force_login(user)
        cookie = "%s=%s" % (
            settings.SESSION_COOKIE_NAME, sessao.cookies[settings.SESSION_COOKIE_NAME].value
        )
        environ = RequestFactory().get(
            reverse("plans:buscar_alimento"), {"q": self.TERMO}, HTTP_COOKIE=cookie
        ).environ
        # O `Client` de teste desliga isto pelo mesmo motivo: fechar conexão
        # "velha" no fim do pedido derrubaria a transação do `TestCase`.
        request_started.disconnect(close_old_connections)
        request_finished.disconnect(close_old_connections)
        self.addCleanup(request_started.connect, close_old_connections)
        self.addCleanup(request_finished.connect, close_old_connections)

        status = []
        with mock.patch("plans.views.busca.sugerir", side_effect=RuntimeError("quebrou")):
            corpo = WSGIHandler()(environ, lambda s, h, *a: status.append(s))
            b"".join(corpo)
        sentry_sdk.flush()
        self.assertTrue(status and status[0].startswith("500"), status)
        self.assertEqual(len(capturados), 1, "o SDK não capturou o 500")
        return json.dumps(capturados[0], default=str, ensure_ascii=False)

    def test_controle_positivo_sem_before_send_o_termo_iria_junto(self):
        texto = self._evento_serializado(com_before_send=False)
        self.assertIn(self.TERMO, texto)

    def test_com_before_send_o_termo_nao_sai(self):
        texto = self._evento_serializado(com_before_send=True)
        self.assertNotIn(self.TERMO, texto)
        self.assertIn("q=[REDIGIDO]", texto)
