"""Como o servidor RECONHECE um replay — e o que ele nao pode reconhecer.

O middleware precisa ver o replay antes de qualquer mutacao, sem estragar o
resto. Duas coisas podem dar errado, em direcoes opostas:

- reconhecer de menos: um POST `multipart` com `op_id` passando pela barreira
  inteira, que foi o buraco da primeira versao desta guarda;
- reconhecer demais: ler `request.POST` num pedido JSON obriga o Django a
  consumir o corpo, e a view que le `request.body` recebe vazio. O endpoint de
  corrida e exatamente esse caso.

E a regra que nao muda: o cabecalho e `op_id` dizem QUE PROTOCOLO e o pedido.
Nao autenticam, nao autorizam, nao escolhem conta e nao dispensam CSRF.
"""
import json

from django.test import Client, TestCase

from accounts.models import SyncedOperation
from accounts.replay import (
    CODIGO_OUTRA_SESSAO,
    CODIGO_PROCESSADO,
    STATUS_PRESERVA,
)
from plans.models import HydrationLog
from plans.tests import create_complete_user
from workouts.models import Corrida


class DeteccaoPorTipoDeCorpoTests(TestCase):
    """As cinco formas de POST que chegam neste servidor."""

    def setUp(self):
        self.a = create_complete_user(email="det-a@exemplo.com")
        self.b = create_complete_user(email="det-b@exemplo.com")
        self.client.force_login(self.b)

    def test_a_urlencoded_com_op_id_e_replay(self):
        """O que o cliente publicado manda."""
        r = self.client.post(
            "/agua/",
            "ml=250&op_id=urlenc",
            content_type="application/x-www-form-urlencoded",
            HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.a.pk),
        )

        self.assertEqual(r.status_code, STATUS_PRESERVA)
        self.assertEqual(r.json()["code"], CODIGO_OUTRA_SESSAO)

    def test_b_multipart_com_op_id_tambem_e_replay(self):
        """O buraco da primeira guarda: ela exigia urlencoded ANTES de olhar o
        cabecalho, entao um multipart com `op_id` passava direto."""
        r = self.client.post(
            "/agua/",
            {"ml": "250", "op_id": "multi"},
            HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.a.pk),
        )

        self.assertEqual(r.status_code, STATUS_PRESERVA)
        self.assertFalse(HydrationLog.objects.exists())

    def test_c_json_comum_nao_e_lido_como_formulario(self):
        """Ler `request.POST` aqui consumiria o corpo que a view precisa."""
        r = self.client.post(
            "/agua/", json.dumps({"ml": 250}), content_type="application/json"
        )

        self.assertNotEqual(r.status_code, STATUS_PRESERVA)

    def test_d_post_normal_sem_op_id_segue_o_fluxo(self):
        """Controle positivo: a pessoa tocando o botao continua funcionando."""
        r = self.client.post("/agua/", {"ml": "250"})

        self.assertEqual(HydrationLog.objects.get(user=self.b).ml, 250)
        self.assertNotEqual(r.status_code, STATUS_PRESERVA)

    def test_e_o_endpoint_de_corrida_continua_lendo_o_proprio_corpo(self):
        """A corrida manda JSON com `op_id` DENTRO do corpo, e a view le por
        `request.body`. Se a barreira tocasse nesse corpo, a corrida sumiria
        com uma mensagem de erro que ninguem conseguiria explicar."""
        corpo = {
            "op_id": "corrida-deteccao",
            "comecou_em": "2026-09-02T07:00:00+00:00",
            "terminou_em": "2026-09-02T07:30:00+00:00",
            "distancia_m": 5000,
            "duracao_s": 1800,
            "teve_lacuna": False,
            "parciais": [],
        }

        r = self.client.post(
            "/treino/corridas/salvar/",
            json.dumps(corpo),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertTrue(
            Corrida.objects.filter(user=self.b, op_id="corrida-deteccao").exists()
        )

    def test_o_cabecalho_de_replay_nao_concede_nada(self):
        """Anunciar-se como replay nao autentica, nao autoriza e nao escolhe
        conta: o destino continua sendo `request.user`."""
        self.client.post(
            "/agua/",
            {"ml": "250", "op_id": "so-cabecalho"},
            HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.b.pk),
        )

        self.assertTrue(HydrationLog.objects.filter(user=self.b).exists())
        self.assertFalse(HydrationLog.objects.filter(user=self.a).exists())


class FilaForegroundTests(TestCase):
    """O `fila.js`: mesma fila A+B, mas com o CSRF renovado antes de enviar."""

    def setUp(self):
        self.a = create_complete_user(email="fg-a@exemplo.com")
        self.b = create_complete_user(email="fg-b@exemplo.com")
        self.c = Client(enforce_csrf_checks=True)

    def _entrar(self, quem):
        self.c.force_login(quem)
        self.c.get("/")
        return self.c.cookies["csrftoken"].value

    def _como_a_pagina_envia(self, item, token_atual):
        """O `enviar()` do `fila.js`: o token guardado e SUBSTITUIDO."""
        dados = dict(item["dados"])
        dados["csrfmiddlewaretoken"] = token_atual
        return self.c.post(
            item["url"],
            dados,
            HTTP_X_REQUESTED_WITH="fetch",
            HTTP_X_NUTRIPLAN_REPLAY="1",
            **(
                {"HTTP_X_NUTRIPLAN_DONO": str(item["dono"])}
                if item.get("dono")
                else {}
            )
        )

    @staticmethod
    def _a_pagina_removeria(r):
        if r.status_code in (301, 302, 303, 307, 308):
            return False
        if r.status_code in (401, 403) or r.status_code >= 500:
            return False
        return True

    def test_fila_com_a_e_b_na_sessao_de_b(self):
        """Item 7: A preserva, B sincroniza — agora com CSRF valido nos DOIS.

        E aqui que o guarda de dono e a unica coisa entre o item de A e a conta
        de B: o `fila.js` renova o token, entao o CSRF nao tem o que recusar.
        No worker o token fica velho e a barreira responde antes; no
        foreground ela e a UNICA barreira. Por isso este teste existe separado.
        """
        token_velho_de_a = self._entrar(self.a)
        self.c.logout()
        token_de_b = self._entrar(self.b)

        fila = [
            {"op_id": "de-a", "dono": self.a.pk, "url": "/agua/",
             "dados": {"ml": "750", "op_id": "de-a",
                       "csrfmiddlewaretoken": token_velho_de_a}},
            {"op_id": "de-b", "dono": self.b.pk, "url": "/agua/",
             "dados": {"ml": "250", "op_id": "de-b",
                       "csrfmiddlewaretoken": token_velho_de_a}},
        ]
        sobreviveram = [
            i["op_id"] for i in fila
            if not self._a_pagina_removeria(
                self._como_a_pagina_envia(i, token_de_b)
            )
        ]

        self.assertEqual(sobreviveram, ["de-a"])
        self.assertEqual(HydrationLog.objects.get(user=self.b).ml, 250)
        self.assertFalse(HydrationLog.objects.filter(user=self.a).exists())
        self.assertFalse(SyncedOperation.objects.filter(op_id="de-a").exists())

    def test_o_item_de_a_sincroniza_quando_a_volta(self):
        """Preservar so vale se a conta certa conseguir subir depois."""
        self._entrar(self.a)
        self.c.logout()
        token_de_b = self._entrar(self.b)
        item = {"op_id": "de-a", "dono": self.a.pk, "url": "/agua/",
                "dados": {"ml": "750", "op_id": "de-a",
                          "csrfmiddlewaretoken": "qualquer"}}
        self._como_a_pagina_envia(item, token_de_b)

        self.c.logout()
        token_de_a = self._entrar(self.a)
        r = self._como_a_pagina_envia(item, token_de_a)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["code"], CODIGO_PROCESSADO)
        self.assertEqual(HydrationLog.objects.get(user=self.a).ml, 750)
        self.assertFalse(HydrationLog.objects.filter(user=self.b).exists())

    def test_o_token_guardado_e_realmente_substituido(self):
        """Item 8, medido pelo efeito e nao pelo texto do arquivo.

        O Django le `csrfmiddlewaretoken` do POST primeiro e so olha o
        cabecalho quando o campo esta vazio. Acrescentar `X-CSRFToken` sem
        trocar o campo nao adiantaria nada — e o teste que provasse isso lendo
        o `fila.js` nao perceberia a diferenca.
        """
        self._entrar(self.a)
        self.c.logout()
        token_atual = self._entrar(self.a)
        guardado = {"op_id": "renovada", "dono": self.a.pk, "url": "/agua/",
                    "dados": {"ml": "250", "op_id": "renovada",
                              "csrfmiddlewaretoken": "TOKEN-VELHO-QUE-JA-MORREU"}}

        r = self._como_a_pagina_envia(guardado, token_atual)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(HydrationLog.objects.get(user=self.a).ml, 250)

    def test_o_legado_sem_dono_nao_e_adotado_no_foreground(self):
        """Renovar o CSRF de um item sem dono e envia-lo seria adota-lo."""
        self._entrar(self.a)
        self.c.logout()
        token_de_b = self._entrar(self.b)
        legado = {"op_id": "legada", "dono": None, "url": "/agua/",
                  "dados": {"ml": "500", "op_id": "legada",
                            "csrfmiddlewaretoken": "velho"}}

        fonte = (
            __import__("pathlib").Path(__file__).resolve().parent.parent
            / "static" / "js" / "fila.js"
        ).read_text(encoding="utf-8")
        trecho = fonte[fonte.index("function meus()"):][:600]

        # O cliente nem chega a enviar: `meus()` exige igualdade estrita.
        self.assertIn("i.dono === eu", trecho)
        self.assertNotIn("i.dono || ", trecho)

        # E o `enviar()` tambem nao inventa dono na hora de montar o pedido.
        # Sem esta linha, um `item.dono || dono()` transformaria o item orfao
        # em item da sessao atual no ultimo passo, depois de `meus()` ter
        # feito o filtro certo — a adocao entrando pela porta dos fundos.
        envio = fonte[fonte.index("function enviar("):][:1200]
        self.assertIn("if (item.dono) cabecalhos", envio)
        self.assertNotIn("item.dono || ", envio)

        # E se enviasse assim mesmo, o servidor nao inventaria dono para ele.
        self._como_a_pagina_envia(legado, token_de_b)
        self.assertEqual(HydrationLog.objects.filter(user=self.b).count(), 1)


class ORuidoDeLogTests(TestCase):
    """503 de compatibilidade nao pode se passar por erro de servidor.

    `django.request` loga QUALQUER 5xx como ERROR. Sem isto, cada replay
    preservado viraria `ERROR Service Unavailable` no log de producao — e o
    5xx de verdade ficaria escondido no meio deles.
    """

    def test_a_resposta_preservada_nao_e_logada_como_erro(self):
        from accounts.replay import resposta_que_preserva

        resposta = resposta_que_preserva("qualquer")

        self.assertTrue(getattr(resposta, "_has_been_logged", False))
