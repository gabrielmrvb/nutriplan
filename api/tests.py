# -*- coding: utf-8 -*-
"""O contrato que um cliente que NÃO é navegador precisa cumprir.

Estes testes vieram antes da implementação. Eles descrevem o menor contrato que
prova a Fase 1: alguém de fora autentica, se identifica, sincroniza uma corrida,
reenvia sem duplicar, consulta o que salvou, e nunca alcança a corrida de outra
pessoa.

A regra que organiza tudo: **a API não olha a sessão**. Ela autentica só pelo
cabeçalho `Authorization: Bearer`. Isso não é preferência — é o que torna
`csrf_exempt` correto em vez de perigoso. CSRF existe porque o navegador ANEXA
o cookie sozinho; um endpoint que recusa cookie não tem o que ser forjado. Há
teste exigindo que sessão válida NÃO autentique a API.
"""
import json
from datetime import datetime, timedelta
from datetime import timezone as fuso

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TokenDeApp
from plans.tests import create_complete_user
from workouts.models import Corrida, TracoDaCorrida

SENHA = "senha-bem-forte-123"


class Base(TestCase):
    def setUp(self):
        self.pessoa = create_complete_user("api.dona@exemplo.com")
        self.pessoa.set_password(SENHA)
        self.pessoa.save()
        self.outra = create_complete_user("api.outra@exemplo.com")
        self.outra.set_password(SENHA)
        self.outra.save()
        self.client = Client()

    def token_de(self, pessoa):
        _, cru = TokenDeApp.emitir(pessoa)
        return cru

    def com_token(self, token):
        return {"HTTP_AUTHORIZATION": "Bearer " + token}

    def json_de(self, resposta):
        return json.loads(resposta.content.decode())


class AutenticarTests(Base):
    """1, 3 e 4 do contrato: entrar, sair, e o que acontece sem token."""

    def test_um_cliente_externo_troca_email_e_senha_por_um_token(self):
        resposta = self.client.post(
            reverse("api:token"),
            json.dumps({"email": self.pessoa.email, "senha": SENHA}),
            content_type="application/json",
        )
        corpo = self.json_de(resposta)

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(corpo["token"])
        self.assertIn("expira_em", corpo)

    def test_senha_errada_nao_devolve_token(self):
        resposta = self.client.post(
            reverse("api:token"),
            json.dumps({"email": self.pessoa.email, "senha": "nao-e-essa"}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("token", self.json_de(resposta))

    def test_a_recusa_nao_diz_se_o_email_existe(self):
        """Duas mensagens diferentes transformariam o endpoint num oráculo de
        cadastro — a mesma regra que `accounts/limites.py` já aplica na
        recuperação de senha."""
        errada = self.client.post(
            reverse("api:token"),
            json.dumps({"email": self.pessoa.email, "senha": "nao-e-essa"}),
            content_type="application/json",
        )
        inexistente = self.client.post(
            reverse("api:token"),
            json.dumps({"email": "ninguem@exemplo.com", "senha": "nao-e-essa"}),
            content_type="application/json",
        )

        self.assertEqual(errada.status_code, inexistente.status_code)
        self.assertEqual(errada.content, inexistente.content)

    def test_sem_token_nao_se_alcanca_dado_privado(self):
        for nome in ("api:eu", "api:corridas"):
            with self.subTest(rota=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 401)

    def test_token_revogado_para_de_valer(self):
        token = self.token_de(self.pessoa)
        antes = self.client.get(reverse("api:eu"), **self.com_token(token))

        self.client.delete(reverse("api:token"), **self.com_token(token))
        depois = self.client.get(reverse("api:eu"), **self.com_token(token))

        self.assertEqual(antes.status_code, 200)
        self.assertEqual(depois.status_code, 401)

    def test_token_vencido_nao_vale(self):
        registro, cru = TokenDeApp.emitir(self.pessoa)
        TokenDeApp.objects.filter(pk=registro.pk).update(
            expira_em=timezone.now() - timezone.timedelta(seconds=1)
        )

        self.assertEqual(
            self.client.get(reverse("api:eu"), **self.com_token(cru)).status_code, 401
        )

    def test_o_token_nao_fica_guardado_em_claro(self):
        """Um vazamento do banco não pode entregar sessões vivas. É o ponto em
        que este desenho é melhor que o token do DRF, que guarda o valor."""
        _, cru = TokenDeApp.emitir(self.pessoa)

        self.assertFalse(TokenDeApp.objects.filter(digest=cru).exists())
        self.assertEqual(TokenDeApp.objects.count(), 1)

    def test_sessao_do_navegador_NAO_autentica_a_api(self):
        """A regra que sustenta o `csrf_exempt`.

        Se a sessão valesse aqui, o navegador anexaria o cookie sozinho e um
        POST de terceiro passaria — que é exatamente o que o CSRF existe para
        impedir. A API só olha o cabeçalho.
        """
        navegador = Client()
        navegador.force_login(self.pessoa)

        self.assertEqual(navegador.get(reverse("api:eu")).status_code, 401)


class QuemSouEuTests(Base):
    """2 do contrato: identificar o usuário."""

    def test_devolve_a_pessoa_do_token(self):
        corpo = self.json_de(
            self.client.get(reverse("api:eu"), **self.com_token(self.token_de(self.pessoa)))
        )

        self.assertEqual(corpo["email"], self.pessoa.email)

    def test_nao_devolve_dado_interno(self):
        corpo = self.json_de(
            self.client.get(reverse("api:eu"), **self.com_token(self.token_de(self.pessoa)))
        )

        for proibido in ("password", "senha", "is_superuser", "is_staff"):
            with self.subTest(campo=proibido):
                self.assertNotIn(proibido, corpo)


class SincronizarCorridaTests(Base):
    """5, 6, 8 e 9 do contrato: criar, reenviar, e o que é recusado."""

    def corpo_valido(self, **troca):
        dados = {
            "op_id": "op-de-teste-1",
            "comecou_em": "2026-09-04T07:00:00+00:00",
            "terminou_em": "2026-09-04T07:30:00+00:00",
            "distancia_m": 5030,
            "duracao_s": 1782,
            "parciais": [{"km": 1, "segundos": 354.0}],
        }
        dados.update(troca)
        return dados

    def enviar(self, corpo, token=None):
        return self.client.post(
            reverse("api:corridas"),
            json.dumps(corpo),
            content_type="application/json",
            **self.com_token(token or self.token_de(self.pessoa)),
        )

    def test_uma_corrida_e_criada(self):
        resposta = self.enviar(self.corpo_valido())

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_reenviar_a_mesma_operacao_nao_duplica(self):
        """O coração do offline: a fila reenvia o que ficou parado, e a resposta
        perdida é indistinguível do envio perdido."""
        token = self.token_de(self.pessoa)
        primeira = self.enviar(self.corpo_valido(), token)
        segunda = self.enviar(self.corpo_valido(), token)

        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)
        self.assertEqual(self.json_de(primeira)["op_id"], self.json_de(segunda)["op_id"])

    def test_o_reenvio_diz_que_ja_existia(self):
        """200 e não 201: o cliente precisa saber que não criou nada agora, e
        não pode tratar isso como erro — erro faria a fila insistir para
        sempre."""
        token = self.token_de(self.pessoa)
        self.enviar(self.corpo_valido(), token)

        self.assertEqual(self.enviar(self.corpo_valido(), token).status_code, 200)

    def test_o_mesmo_op_id_de_outra_pessoa_e_outra_corrida(self):
        """A chave é por PESSOA. Dois aparelhos podem sortear o mesmo
        identificador, e um deles não pode engolir a corrida do outro."""
        self.enviar(self.corpo_valido(), self.token_de(self.pessoa))
        self.enviar(self.corpo_valido(), self.token_de(self.outra))

        self.assertEqual(Corrida.objects.count(), 2)

    def test_payload_invalido_e_recusado(self):
        for falta in ("op_id", "comecou_em", "distancia_m"):
            with self.subTest(campo=falta):
                corpo = self.corpo_valido()
                del corpo[falta]

                self.assertEqual(self.enviar(corpo).status_code, 400)

    def test_corpo_que_nao_e_json_e_recusado(self):
        resposta = self.client.post(
            reverse("api:corridas"),
            "isto não é json",
            content_type="application/json",
            **self.com_token(self.token_de(self.pessoa)),
        )

        self.assertEqual(resposta.status_code, 400)

    def test_distancia_impossivel_e_recusada(self):
        self.assertEqual(self.enviar(self.corpo_valido(distancia_m=10_000_000)).status_code, 400)

    def test_terminar_antes_de_comecar_e_recusado(self):
        corpo = self.corpo_valido(terminou_em="2026-09-04T06:00:00+00:00")

        self.assertEqual(self.enviar(corpo).status_code, 400)

    def test_nada_e_gravado_quando_o_payload_e_recusado(self):
        self.enviar(self.corpo_valido(distancia_m=-5))

        self.assertEqual(Corrida.objects.count(), 0)


class OServidorCalculaQuandoRecebePontosTests(Base):
    """A autoridade do cálculo, e o motor Python que existia sem uso."""

    def enviar_pontos(self, pontos, **troca):
        corpo = {
            "op_id": "op-com-pontos",
            "comecou_em": "2026-09-04T07:00:00+00:00",
            "terminou_em": "2026-09-04T07:30:00+00:00",
            "duracao_s": 1782,
            "pontos": pontos,
        }
        corpo.update(troca)
        return self.client.post(
            reverse("api:corridas"),
            json.dumps(corpo),
            content_type="application/json",
            **self.com_token(self.token_de(self.pessoa)),
        )

    def pontos_retos(self, quantos=60, passo=0.0001):
        return [
            {"lat": -23.55 + i * passo, "lon": -46.63, "t": i, "accuracy": 5}
            for i in range(quantos)
        ]

    def test_a_distancia_vem_do_servidor_e_nao_do_cliente(self):
        """Com pontos, o número que o cliente mandou é ignorado. É o que tira a
        distância do lado que a pessoa controla."""
        self.enviar_pontos(self.pontos_retos(), distancia_m=999_999)
        corrida = Corrida.objects.get(user=self.pessoa)

        self.assertNotEqual(corrida.distancia_m, 999_999)
        self.assertGreater(corrida.distancia_m, 0)

    def test_o_tracado_nunca_fica_na_linha_da_corrida(self):
        """O percurso é guardado, mas JAMAIS dentro de `Corrida`.

        Este teste nasceu afirmando outra coisa — que o traçado não era
        guardado de jeito nenhum —, e isso era verdade enquanto não havia mapa.
        Quando o percurso passou a ser produto, ele foi para `TracoDaCorrida`,
        e a asserção teria continuado VERDE sem proteger nada: ela só olha os
        campos de `Corrida`.

        Reescrita, ela protege o que de fato importa agora: a linha da corrida
        continua sem coordenada. É isso que faz a LISTA do histórico não
        arrastar o percurso de cada corrida, e é isso que permite apagar o
        traçado depois sem perder a estatística.
        """
        self.enviar_pontos(self.pontos_retos())
        corrida = Corrida.objects.get(user=self.pessoa)

        bruto = json.dumps(
            {c.name: str(getattr(corrida, c.name)) for c in corrida._meta.fields}
        )

        self.assertNotIn("-46.63", bruto)
        self.assertNotIn("lat", bruto)

        # Controle positivo: sem isto, apagar a gravação do traço deixaria as
        # duas asserções acima verdes e o teste provaria o oposto do que diz.
        self.assertTrue(corrida.traco.pontos)

    def test_tracado_que_soma_distancia_impossivel_e_recusado(self):
        """O filtro de teleporte é ponto a ponto, e por isso não vê o total.

        Espaçando as leituras 300 s, cada passo de 3,3 km fica a 11 m/s — abaixo
        dos 12,5 m/s que o motor recusa. Cem passos assim somam 334 km e passam
        pelo filtro um a um, acima do teto de 300 km.

        Cabe folgado no limite de 1 MB do corpo: são cem pontos. O teto precisa
        valer sobre o número GRAVADO, e não só sobre o que o cliente declara —
        foi a sabotagem S240 que mostrou que essa guarda estava sem teste.
        """
        pontos = [
            {"lat": -23.55 + i * 0.030, "lon": -46.63, "t": i * 300, "accuracy": 5}
            for i in range(100)
        ]
        resposta = self.enviar_pontos(pontos, duracao_s=29_700)

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_ponto_malformado_nao_derruba_o_endpoint(self):
        resposta = self.enviar_pontos([{"lat": "abc", "lon": None, "t": "x"}])

        self.assertEqual(resposta.status_code, 400)

    def test_sem_pontos_o_resumo_do_cliente_continua_valendo(self):
        """O contrato antigo não pode quebrar: a PWA em produção manda o
        resumo, e ela continua no ar."""
        resposta = self.client.post(
            reverse("api:corridas"),
            json.dumps(
                {
                    "op_id": "op-sem-pontos",
                    "comecou_em": "2026-09-04T07:00:00+00:00",
                    "terminou_em": "2026-09-04T07:30:00+00:00",
                    "distancia_m": 5030,
                    "duracao_s": 1782,
                }
            ),
            content_type="application/json",
            **self.com_token(self.token_de(self.pessoa)),
        )

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(Corrida.objects.get(user=self.pessoa).distancia_m, 5030)


class NinguemAlcancaCorridaAlheiaTests(Base):
    """7, 10 e 11 do contrato: ownership em listagem e detalhe."""

    def setUp(self):
        super().setUp()
        self.minha = Corrida.objects.create(
            user=self.pessoa,
            op_id="minha",
            comecou_em=timezone.now(),
            terminou_em=timezone.now(),
            distancia_m=5000,
            duracao_s=1800,
        )
        self.alheia = Corrida.objects.create(
            user=self.outra,
            op_id="alheia",
            comecou_em=timezone.now(),
            terminou_em=timezone.now(),
            distancia_m=9000,
            duracao_s=3000,
        )

    def test_a_listagem_traz_somente_as_minhas(self):
        corpo = self.json_de(
            self.client.get(
                reverse("api:corridas"), **self.com_token(self.token_de(self.pessoa))
            )
        )
        ids = [c["op_id"] for c in corpo["corridas"]]

        self.assertEqual(ids, ["minha"])

    def test_o_detalhe_da_corrida_alheia_e_404(self):
        """404 e não 403: 403 confirmaria que a corrida existe."""
        resposta = self.client.get(
            reverse("api:corrida", args=["alheia"]),
            **self.com_token(self.token_de(self.pessoa)),
        )

        self.assertEqual(resposta.status_code, 404)

    def test_o_detalhe_da_minha_corrida_vem(self):
        corpo = self.json_de(
            self.client.get(
                reverse("api:corrida", args=["minha"]),
                **self.com_token(self.token_de(self.pessoa)),
            )
        )

        self.assertEqual(corpo["op_id"], "minha")
        self.assertEqual(corpo["distancia_m"], 5000)


class OWebContinuaFuncionandoTests(TestCase):
    """12 do contrato: a API não pode ter mexido no que já existia."""

    def setUp(self):
        self.pessoa = create_complete_user("api.web@exemplo.com")

    def test_a_tela_de_entrar_continua_de_pe(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_o_dia_de_hoje_continua_de_pe(self):
        self.client.force_login(self.pessoa)

        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)

    def test_a_rota_web_de_salvar_corrida_continua_existindo(self):
        """A PWA em produção posta nela. A API é rota NOVA, e não substituição."""
        self.client.force_login(self.pessoa)
        resposta = self.client.post(
            reverse("workouts:salvar_corrida"),
            json.dumps(
                {
                    "op_id": "pela-web",
                    "comecou_em": "2026-09-04T07:00:00+00:00",
                    "terminou_em": "2026-09-04T07:30:00+00:00",
                    "distancia_m": 5030,
                    "duracao_s": 1782,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Corrida.objects.filter(user=self.pessoa, op_id="pela-web").exists())


class OMesmoOpIdComConteudoDiferenteTests(Base):
    """O contrato que faltava definir antes de um app depender dele.

    Reenvio IDÊNTICO é o caso normal do offline — resposta perdida é
    indistinguível de envio perdido, então o cliente reenvia. Isso continua
    sendo sucesso.

    Reenvio DIVERGENTE é outra coisa: ou o cliente tem bug, ou o armazenamento
    local corrompeu, ou dois estados diferentes ganharam o mesmo identificador.
    Aceitar em silêncio faria o app acreditar que sincronizou um número que o
    servidor jogou fora.

    A resposta é **409**, e ela é TERMINAL: reenviar não muda nada. A regra da
    fila passa a ser 2xx apaga, 409 apaga e reporta, 5xx e falha de rede
    mantêm.

    Isto vale só na API. `workouts:salvar_corrida` — a rota que a PWA publicada
    usa — continua respondendo 200, porque mudar um contrato publicado sem
    aviso é o que esta missão proíbe. A diferença está em `docs/api-v1.md`.
    """

    def base(self, **troca):
        dados = {
            "op_id": "op-divergente",
            "comecou_em": "2026-09-04T07:00:00+00:00",
            "terminou_em": "2026-09-04T07:30:00+00:00",
            "distancia_m": 5030,
            "duracao_s": 1782,
        }
        dados.update(troca)
        return dados

    def enviar(self, corpo, token):
        return self.client.post(
            reverse("api:corridas"),
            json.dumps(corpo),
            content_type="application/json",
            **self.com_token(token),
        )

    def test_reenvio_identico_continua_sendo_sucesso(self):
        token = self.token_de(self.pessoa)
        self.enviar(self.base(), token)

        self.assertEqual(self.enviar(self.base(), token).status_code, 200)

    def test_reenvio_divergente_responde_409(self):
        token = self.token_de(self.pessoa)
        self.enviar(self.base(), token)

        resposta = self.enviar(self.base(distancia_m=9999), token)

        self.assertEqual(resposta.status_code, 409)

    def test_o_409_diz_o_que_divergiu(self):
        """Sem isso o cliente sabe que deu conflito e não sabe em quê — e o
        diagnóstico vira adivinhação de quem só tem o log do aparelho."""
        token = self.token_de(self.pessoa)
        self.enviar(self.base(), token)

        corpo = self.json_de(self.enviar(self.base(distancia_m=9999), token))

        self.assertIn("distancia_m", corpo["divergiram"])
        self.assertEqual(corpo["guardado"]["distancia_m"], 5030)

    def test_o_divergente_nao_cria_segunda_corrida(self):
        token = self.token_de(self.pessoa)
        self.enviar(self.base(), token)
        self.enviar(self.base(distancia_m=9999), token)

        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_o_divergente_nao_sobrescreve_o_que_ja_estava(self):
        """O primeiro envio vence. O segundo é suspeito por construção."""
        token = self.token_de(self.pessoa)
        self.enviar(self.base(), token)
        self.enviar(self.base(distancia_m=9999), token)

        self.assertEqual(Corrida.objects.get(user=self.pessoa).distancia_m, 5030)

    def test_parciais_em_outra_ordem_nao_contam_como_divergencia(self):
        """Comparar JSON cru acusaria conflito onde não há um. A comparação é
        sobre VALOR, e por isso a lista é comparada elemento a elemento."""
        token = self.token_de(self.pessoa)
        com_parciais = self.base(parciais=[{"km": 1, "segundos": 354.0}])
        self.enviar(com_parciais, token)

        de_novo = self.base(parciais=[{"segundos": 354.0, "km": 1}])

        self.assertEqual(self.enviar(de_novo, token).status_code, 200)

    def test_outra_pessoa_com_o_mesmo_op_id_nao_da_conflito(self):
        self.enviar(self.base(), self.token_de(self.pessoa))

        resposta = self.enviar(self.base(distancia_m=9999), self.token_de(self.outra))

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(Corrida.objects.count(), 2)


class RevisaoDirigidaDoTokenTests(Base):
    """A checagem que uma credencial de implementação própria exige.

    Não redesenha nada: confirma, item a item, o que já foi escrito.
    """

    def test_a_entropia_e_suficiente(self):
        """`token_urlsafe(32)` são 256 bits. Não há dicionário para atacar
        isso, e é o motivo de o digest não precisar de sal nem de KDF caro."""
        _, cru = TokenDeApp.emitir(self.pessoa)

        self.assertGreaterEqual(len(cru), 40)
        self.assertEqual(len({TokenDeApp.emitir(self.pessoa)[1] for _ in range(20)}), 20)

    def test_o_token_de_uma_pessoa_nao_abre_a_conta_de_outra(self):
        corpo = self.json_de(
            self.client.get(reverse("api:eu"), **self.com_token(self.token_de(self.outra)))
        )

        self.assertEqual(corpo["email"], self.outra.email)
        self.assertNotEqual(corpo["email"], self.pessoa.email)

    def test_a_resposta_nunca_ecoa_o_digest(self):
        registro, cru = TokenDeApp.emitir(self.pessoa)
        corpo = self.client.get(reverse("api:eu"), **self.com_token(cru)).content.decode()

        self.assertNotIn(registro.digest, corpo)

    def test_o_token_nao_viaja_em_url(self):
        """Query string vai para log de servidor, de proxy e para o histórico
        do navegador. O token viaja em cabeçalho, e só."""
        _, cru = TokenDeApp.emitir(self.pessoa)

        pela_url = self.client.get(reverse("api:eu") + "?token=" + cru)

        self.assertEqual(pela_url.status_code, 401)

    def test_a_migracao_nao_carrega_segredo(self):
        from pathlib import Path

        from config.settings import BASE_DIR

        texto = (
            Path(BASE_DIR) / "accounts" / "migrations" / "0022_token_de_app.py"
        ).read_text(encoding="utf-8")

        for proibido in ("SECRET_KEY", "token_urlsafe", "sha256"):
            with self.subTest(termo=proibido):
                self.assertNotIn(proibido, texto)

    def test_o_admin_nao_expoe_a_credencial(self):
        """Registrar `TokenDeApp` no Admin poria o digest numa tela. Ele não
        está registrado, e a matriz de capability do B10 é quem cobra que
        superfície nova entre com decisão escrita."""
        from django.contrib import admin

        self.assertFalse(admin.site.is_registered(TokenDeApp))


class OTracadoDaCorridaTests(Base):
    """O percurso: quando é guardado, quem enxerga, e o que nunca sai na lista.

    O traçado é o dado mais sensível que este app guarda — ele diz onde a
    pessoa mora e a que horas ela sai de casa. Todo teste aqui existe para uma
    pergunta de dono: quem consegue ler isto?
    """

    def enviar(self, op_id="op-traco", pontos=None, **troca):
        corpo = {
            "op_id": op_id,
            "comecou_em": "2026-09-04T07:00:00+00:00",
            "terminou_em": "2026-09-04T07:30:00+00:00",
            "duracao_s": 1782,
        }
        if pontos is not None:
            corpo["pontos"] = pontos
        corpo.update(troca)
        return self.client.post(
            reverse("api:corridas"),
            json.dumps(corpo),
            content_type="application/json",
            **self.com_token(self.token_de(self.pessoa)),
        )

    def pontos_retos(self, quantos=60, passo=0.0001):
        return [
            {"lat": -23.55 + i * passo, "lon": -46.63, "t": i, "accuracy": 5}
            for i in range(quantos)
        ]

    def test_o_percurso_e_guardado_quando_vem_ponto(self):
        """Sem isto não existe mapa nem resumo compartilhável: os dois desenham
        o traçado, e o traçado precisa sobreviver ao pedido."""
        self.enviar(pontos=self.pontos_retos())

        traco = TracoDaCorrida.objects.get(corrida__user=self.pessoa)
        self.assertEqual(len(traco.pontos), 60)
        self.assertIn("lat", traco.pontos[0])

    def test_corrida_sem_ponto_nao_ganha_tracado(self):
        """A PWA publicada sincroniza só os números, e continua tendo de
        funcionar. Corrida sem percurso é caso NORMAL, não erro."""
        self.enviar(op_id="op-sem-ponto", distancia_m=5000)

        corrida = Corrida.objects.get(user=self.pessoa, op_id="op-sem-ponto")
        self.assertFalse(TracoDaCorrida.objects.filter(corrida=corrida).exists())

    def test_a_lista_nunca_devolve_o_percurso(self):
        """A lista existe para desenhar distância e tempo de muitas corridas.

        Mandar o percurso de cada uma junto seria arrastar milhares de
        coordenadas para uma tela que não as usa — e é exatamente o que a
        tabela separada existe para evitar. Asserção sobre a COORDENADA, e não
        sobre a chave: uma chave renomeada continuaria vazando o dado.
        """
        self.enviar(pontos=self.pontos_retos())

        resposta = self.client.get(
            reverse("api:corridas"), **self.com_token(self.token_de(self.pessoa))
        )
        cru = resposta.content.decode()

        self.assertNotIn("-46.63", cru)
        self.assertNotIn("pontos", cru)

    def test_o_detalhe_devolve_o_percurso_para_o_dono(self):
        """O dono lê o próprio traçado — é o que o mapa da corrida consome."""
        self.enviar(pontos=self.pontos_retos())

        resposta = self.client.get(
            reverse("api:corrida", args=["op-traco"]),
            **self.com_token(self.token_de(self.pessoa)),
        )
        corpo = self.json_de(resposta)

        self.assertTrue(corpo["tem_traco"])
        self.assertEqual(len(corpo["pontos"]), 60)

    def test_o_detalhe_de_corrida_sem_tracado_nao_estoura(self):
        """`OneToOne` que não existe levanta `RelatedObjectDoesNotExist` se
        alguém acessar direto. A tela precisa da ausência como valor, não como
        exceção."""
        self.enviar(op_id="op-sem-ponto", distancia_m=5000)

        resposta = self.client.get(
            reverse("api:corrida", args=["op-sem-ponto"]),
            **self.com_token(self.token_de(self.pessoa)),
        )
        corpo = self.json_de(resposta)

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(corpo["tem_traco"])
        self.assertEqual(corpo["pontos"], [])

    def test_ninguem_le_o_percurso_de_outra_pessoa(self):
        """A pergunta que mais importa nesta tabela. 404 e não 403: 403
        confirmaria que a corrida existe, e com ela que a pessoa correu."""
        self.enviar(pontos=self.pontos_retos())

        resposta = self.client.get(
            reverse("api:corrida", args=["op-traco"]),
            **self.com_token(self.token_de(self.outra)),
        )

        self.assertEqual(resposta.status_code, 404)
        self.assertNotIn("-46.63", resposta.content.decode())

    def test_reenvio_identico_nao_duplica_o_percurso(self):
        """A fila offline reenvia em rajada quando a rede volta. Dois traçados
        para uma corrida é o mesmo defeito que `op_id` existe para impedir — e
        `OneToOne` transformaria a segunda gravação em erro 500."""
        pontos = self.pontos_retos()
        primeira = self.enviar(pontos=pontos)
        segunda = self.enviar(pontos=pontos)

        self.assertEqual(primeira.status_code, 201)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(TracoDaCorrida.objects.count(), 1)

    def test_leitura_recusada_pelo_motor_nao_e_guardada(self):
        """Guardar a leitura que o filtro rejeitou seria guardar mais
        coordenada para desenhar um mapa PIOR. O teleporte entra no meio de um
        percurso reto e não pode sobreviver no banco."""
        pontos = self.pontos_retos(10)
        pontos.insert(5, {"lat": -10.0, "lon": -40.0, "t": 5.5, "accuracy": 5})

        self.enviar(pontos=pontos)
        traco = TracoDaCorrida.objects.get(corrida__user=self.pessoa)

        guardado = json.dumps(traco.pontos)
        self.assertNotIn("-40.0", guardado)
        self.assertGreaterEqual(traco.descartadas, 1)

    def test_apagar_a_corrida_apaga_o_percurso(self):
        """Contrato deste repositório: todo dado pessoal cai junto. Traçado que
        sobrevive à corrida é coordenada órfã que ninguém sabe que tem."""
        self.enviar(pontos=self.pontos_retos())
        self.assertEqual(TracoDaCorrida.objects.count(), 1)

        Corrida.objects.get(user=self.pessoa).delete()

        self.assertEqual(TracoDaCorrida.objects.count(), 0)

    def test_apagar_a_conta_apaga_o_percurso(self):
        """Excluir a conta é a promessa mais forte do app. Se o traçado
        sobreviver a ela, o endereço de casa sobrevive junto."""
        self.enviar(pontos=self.pontos_retos())
        self.assertEqual(TracoDaCorrida.objects.count(), 1)

        self.pessoa.delete()

        self.assertEqual(TracoDaCorrida.objects.count(), 0)


class OLoteForaDeOrdemTests(Base):
    """O aparelho entrega o lote bagunçado, e a corrida não pode encolher.

    Isto não é hipótese de laboratório. O iOS suspende o app, ENFILEIRA as
    atualizações de localização e as entrega quando ele volta a rodar; um app
    encerrado no meio da corrida pode subir o lote novo antes de esvaziar o
    antigo. Chegar fora de ordem é o caso normal do cliente nativo.

    O modo de falha é o pior que existe: silencioso. O motor recusa todo trecho
    com tempo andando para trás — está certo —, e sem ordenação isso vira uma
    corrida MENOR do que a pessoa correu, sem erro, sem aviso, sem log.
    """

    def enviar(self, pontos, op_id):
        corpo = {
            "op_id": op_id,
            "comecou_em": "2026-09-04T07:00:00+00:00",
            "terminou_em": "2026-09-04T07:30:00+00:00",
            "duracao_s": 1782,
            "pontos": pontos,
        }
        return self.client.post(
            reverse("api:corridas"),
            json.dumps(corpo),
            content_type="application/json",
            **self.com_token(self.token_de(self.pessoa)),
        )

    def pontos_retos(self, quantos=60, passo=0.0001):
        return [
            {"lat": -23.55 + i * passo, "lon": -46.63, "t": i, "accuracy": 5}
            for i in range(quantos)
        ]

    def test_lote_embaralhado_mede_o_mesmo_que_lote_em_ordem(self):
        """A asserção é de IGUALDADE contra o caso ordenado, e não um piso.

        Um `assertGreater(distancia, 0)` passaria com metade dos pontos
        recusados — que é exatamente o defeito que este teste existe para pegar.
        """
        ordenados = self.pontos_retos()
        embaralhados = [ordenados[i] for i in (30, 5, 59, 0, 17)] + [
            p for i, p in enumerate(ordenados) if i not in (30, 5, 59, 0, 17)
        ]

        self.enviar(ordenados, "op-em-ordem")
        self.enviar(embaralhados, "op-bagunca")

        em_ordem = Corrida.objects.get(user=self.pessoa, op_id="op-em-ordem")
        bagunca = Corrida.objects.get(user=self.pessoa, op_id="op-bagunca")

        self.assertEqual(bagunca.distancia_m, em_ordem.distancia_m)
        self.assertGreater(em_ordem.distancia_m, 0)

    def test_lote_ao_contrario_ainda_mede_a_corrida_inteira(self):
        """O pior caso: a entrega chega invertida de ponta a ponta."""
        ordenados = self.pontos_retos()

        self.enviar(ordenados, "op-frente")
        self.enviar(list(reversed(ordenados)), "op-tras")

        frente = Corrida.objects.get(user=self.pessoa, op_id="op-frente")
        tras = Corrida.objects.get(user=self.pessoa, op_id="op-tras")

        self.assertEqual(tras.distancia_m, frente.distancia_m)

    def test_o_tracado_guardado_sai_em_ordem(self):
        """O mapa liga os pontos na ordem em que estão guardados. Traçado fora
        de ordem desenha um risco de ida e volta que ninguém correu."""
        ordenados = self.pontos_retos()
        self.enviar(list(reversed(ordenados)), "op-tras")

        traco = TracoDaCorrida.objects.get(corrida__op_id="op-tras")
        instantes = [p["t"] for p in traco.pontos]

        # A completude vem PRIMEIRO, e é o que dá dente à asserção seguinte:
        # sem ordenação o motor recusa tudo depois da primeira leitura, sobra
        # um ponto só — e lista de um elemento está trivialmente ordenada.
        # Sem esta linha, a sabotagem passava verde.
        self.assertEqual(len(traco.pontos), 60)
        self.assertEqual(instantes, sorted(instantes))

    def test_lote_novo_antes_do_lote_velho_nao_perde_a_primeira_metade(self):
        """O cenário concreto que o iOS produz, e o mais caro dos dois.

        O app é encerrado no meio da corrida. Ao relançar, ele sobe o lote
        recente e só depois esvazia o que tinha ficado no disco — então o
        servidor recebe os minutos 15–30 ANTES dos minutos 0–15.

        Sem ordenação a primeira metade inteira é recusada, porque cada leitura
        dela tem tempo menor que a última já processada. A corrida chega ao
        histórico com metade da distância, sem erro nenhum.

        Uma versão anterior deste teste media leitura REPETIDA. Ela passava
        verde com a ordenação sabotada — repetição é recusada por dois filtros
        do motor (tempo zero e deslocamento zero) e nunca dependeu da ordem.
        Testava algo verdadeiro que não era o que o nome prometia.
        """
        ordenados = self.pontos_retos()
        primeira_metade, segunda_metade = ordenados[:30], ordenados[30:]

        self.enviar(ordenados, "op-inteiro")
        self.enviar(segunda_metade + primeira_metade, "op-lotes-trocados")

        inteiro = Corrida.objects.get(user=self.pessoa, op_id="op-inteiro")
        trocados = Corrida.objects.get(user=self.pessoa, op_id="op-lotes-trocados")

        self.assertEqual(trocados.distancia_m, inteiro.distancia_m)
        self.assertEqual(len(trocados.traco.pontos), 60)


class OHistoricoEPaginadoTests(Base):
    """Devolver o histórico inteiro a cada abertura de tela é defeito que só
    aparece em quem usa o app há muito tempo — e aí já é tarde para consertar,
    porque apertar um teto que não existia quebra o app publicado.

    Por isso o teto entra ANTES de haver cliente. É o único momento barato.
    """

    def criar_corridas(self, quantas, base_dia=1):
        Corrida.objects.bulk_create(
            [
                Corrida(
                    user=self.pessoa,
                    op_id=f"op-{i}",
                    comecou_em=datetime(2026, 1, base_dia, 7, 0, tzinfo=fuso.utc)
                    + timedelta(days=i),
                    terminou_em=datetime(2026, 1, base_dia, 7, 30, tzinfo=fuso.utc)
                    + timedelta(days=i),
                    distancia_m=5000,
                    duracao_s=1800,
                )
                for i in range(quantas)
            ]
        )

    def listar(self, query=""):
        return self.client.get(
            reverse("api:corridas") + query,
            **self.com_token(self.token_de(self.pessoa)),
        )

    def test_sem_parametro_o_historico_vem_limitado(self):
        self.criar_corridas(60)

        corpo = self.json_de(self.listar())

        self.assertEqual(len(corpo["corridas"]), 50)
        self.assertTrue(corpo["tem_mais"])

    def test_tem_mais_e_falso_quando_acabou(self):
        """Sem isto o cliente pediria página seguinte para sempre."""
        self.criar_corridas(3)

        corpo = self.json_de(self.listar())

        self.assertEqual(len(corpo["corridas"]), 3)
        self.assertFalse(corpo["tem_mais"])

    def test_o_limite_pedido_e_respeitado(self):
        self.criar_corridas(10)

        corpo = self.json_de(self.listar("?limite=4"))

        self.assertEqual(len(corpo["corridas"]), 4)
        self.assertTrue(corpo["tem_mais"])

    def test_limite_absurdo_e_aparado_no_teto(self):
        """Teto de verdade, não sugestão: sem isto `?limite=100000` devolveria
        o histórico inteiro e o parâmetro seria decoração."""
        self.criar_corridas(210)

        corpo = self.json_de(self.listar("?limite=100000"))

        self.assertEqual(len(corpo["corridas"]), 200)

    def test_limite_ilegivel_e_recusado(self):
        resposta = self.listar("?limite=muitas")

        self.assertEqual(resposta.status_code, 400)

    def test_desde_recorta_por_data(self):
        self.criar_corridas(10)

        corpo = self.json_de(self.listar("?desde=2026-01-06T00:00:00%2B00:00"))

        self.assertEqual(len(corpo["corridas"]), 5)

    def test_data_ilegivel_e_recusada_em_vez_de_ignorada(self):
        """Ignorar a data errada devolveria a lista inteira, e a sincronização
        incremental pareceria funcionar enquanto baixa tudo toda vez."""
        self.criar_corridas(5)

        resposta = self.listar("?desde=ontem")

        self.assertEqual(resposta.status_code, 400)

    def test_a_pagina_continua_sem_coordenada(self):
        """A paginação não pode ter reaberto o que a tabela separada fechou."""
        pontos = [
            {"lat": -23.55 + i * 0.0001, "lon": -46.63, "t": i, "accuracy": 5}
            for i in range(60)
        ]
        self.client.post(
            reverse("api:corridas"),
            json.dumps(
                {
                    "op_id": "op-com-traco",
                    "comecou_em": "2026-09-04T07:00:00+00:00",
                    "terminou_em": "2026-09-04T07:30:00+00:00",
                    "duracao_s": 1782,
                    "pontos": pontos,
                }
            ),
            content_type="application/json",
            **self.com_token(self.token_de(self.pessoa)),
        )

        cru = self.listar().content.decode()

        self.assertNotIn("-46.63", cru)
