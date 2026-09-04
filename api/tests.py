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

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TokenDeApp
from plans.tests import create_complete_user
from workouts.models import Corrida

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

    def test_o_tracado_nao_e_guardado(self):
        """A decisão de privacidade do model continua valendo: os pontos são
        calculados e DESCARTADOS. Guardar coordenada é guardar onde a pessoa
        mora."""
        self.enviar_pontos(self.pontos_retos())
        corrida = Corrida.objects.get(user=self.pessoa)

        bruto = json.dumps(
            {c.name: str(getattr(corrida, c.name)) for c in corrida._meta.fields}
        )

        self.assertNotIn("-46.63", bruto)
        self.assertNotIn("lat", bruto)

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
