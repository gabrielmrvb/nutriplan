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
import subprocess
import sys
from unittest import mock

from django.test import SimpleTestCase

from config import observabilidade
from config.settings import BASE_DIR

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
