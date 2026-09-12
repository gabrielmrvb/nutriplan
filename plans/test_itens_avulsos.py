# -*- coding: utf-8 -*-
"""A lista de compras aceita o que o cardápio não pede — e o risco dura a semana.

§36 pede adicionar, remover, marcar e persistência. O QA de 12/09/2026
encontrou dois buracos: não havia como acrescentar item (a pessoa levava duas
listas ao mercado), e o risco sumia à meia-noite — a chave era o dia de hoje
e a leitura só lia ela, com a tela prometendo que ficava salvo.

O formulário de adicionar é enviado RENDERIZADO, com o CSRF de verdade: com o
`name` do campo trocado no template, um `client.post` de dicionário seguiria
verde e a tela estaria quebrada (`nutriplan-missao`, seção 5).
"""
import re
from datetime import timedelta

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from plans import services, shopping
from plans.models import ItemAvulsoDaLista, ItemDaListaMarcado
from plans.tests import create_complete_user


class _Lista(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = create_complete_user(email="avulso@exemplo.com")
        self.plan = services.create_plan(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = shopping.dias_da_semana()[0]

    def tela(self, opcao="A"):
        return self.client.get(reverse("plans:shopping") + "?opcao=" + opcao)

    def secao(self, opcao="A"):
        html = self.tela(opcao).content.decode()
        return html[html.index('id="seus-itens"'):]

    def nomes_na_tela(self, opcao="A"):
        return re.findall(r'class="shopping__name">([^<]*)<', self.secao(opcao))


class AdicionarTests(_Lista):
    def test_o_item_entra_na_tela_e_sobrevive_a_recarga(self):
        self.client.post(reverse("plans:adicionar_item"), {"nome": "Café", "opcao": "A"})

        self.assertEqual(self.nomes_na_tela(), ["Café"])
        self.assertEqual(self.nomes_na_tela(), ["Café"])  # segunda visita, mesma lista

    def test_o_formulario_renderizado_e_o_que_adiciona(self):
        """Enviado como o navegador envia: `action`, `name` e CSRF da página."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.pessoa)
        html = cliente.get(reverse("plans:shopping")).content.decode()
        secao = html[html.index('id="seus-itens"'):]
        form = re.search(r'<form method="post" action="([^"]+)" class="compra-avulsa">(.*?)</form>', secao, re.S)
        self.assertIsNotNone(form, "sumiu o formulário de adicionar")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form.group(2)).group(1)
        campo = re.search(r'<input type="text"[^>]*name="([^"]+)"', form.group(2)).group(1)

        resposta = cliente.post(form.group(1), {"csrfmiddlewaretoken": token, campo: "Papel toalha", "opcao": "B"})

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("#seus-itens", resposta["Location"])
        self.assertIn("opcao=B", resposta["Location"])
        self.assertEqual(list(ItemAvulsoDaLista.objects.values_list("nome", flat=True)), ["Papel toalha"])

    def test_adicionar_duas_vezes_e_um_item(self):
        """Toque duplo no botão, reenvio do formulário: um café."""
        for _ in range(2):
            self.client.post(reverse("plans:adicionar_item"), {"nome": "  Café   ", "opcao": "A"})

        self.assertEqual(ItemAvulsoDaLista.objects.count(), 1)
        self.assertEqual(self.nomes_na_tela(), ["Café"])

    def test_nome_vazio_nao_cria_nada(self):
        resposta = self.client.post(reverse("plans:adicionar_item"), {"nome": "   "})

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ItemAvulsoDaLista.objects.count(), 0)

    def test_o_nome_e_cortado_no_tamanho_do_campo(self):
        self.client.post(reverse("plans:adicionar_item"), {"nome": "x" * 200})

        self.assertEqual(len(ItemAvulsoDaLista.objects.get().nome), 60)
        self.assertIn('maxlength="60"', self.secao())

    def test_o_item_aparece_nas_duas_opcoes(self):
        """Café é café na A e na B: o avulso não depende da opção."""
        self.client.post(reverse("plans:adicionar_item"), {"nome": "Café"})

        self.assertEqual(self.nomes_na_tela("A"), ["Café"])
        self.assertEqual(self.nomes_na_tela("B"), ["Café"])

    def test_vazio_explica_o_valor_e_o_formulario_e_o_proximo_passo(self):
        secao = self.secao()
        self.assertIn("Falta algo que o cardápio não pede", secao)
        self.assertIn('class="compra-avulsa"', secao)
        self.assertNotIn('class="shopping__name"', secao)

    def test_quem_nao_entrou_nao_adiciona(self):
        self.client.logout()
        resposta = self.client.post(reverse("plans:adicionar_item"), {"nome": "Café"})
        self.assertNotEqual(resposta.status_code, 200)
        self.assertEqual(ItemAvulsoDaLista.objects.count(), 0)


class MarcarERemoverTests(_Lista):
    def setUp(self):
        super().setUp()
        self.item = ItemAvulsoDaLista.objects.create(user=self.pessoa, semana=self.hoje, nome="Café")

    def _marcar(self, marcado, item=None):
        return self.client.post(
            reverse("plans:marcar_item"),
            {"avulso_id": (item or self.item).pk, "marcado": marcado},
        )

    def _caixa(self):
        return re.search(r'<input type="checkbox"[^>]*data-avulso="%d"[^>]*>' % self.item.pk, self.secao()).group(0)

    def test_marcar_persiste_e_a_caixa_volta_marcada(self):
        self._marcar("1")
        self.item.refresh_from_db()
        self.assertTrue(self.item.marcado)
        self.assertIn("checked", self._caixa())

    def test_desmarcar_tambem_persiste(self):
        self._marcar("1")
        self._marcar("0")
        self.item.refresh_from_db()
        self.assertFalse(self.item.marcado)
        self.assertNotIn("checked", self._caixa())

    def test_marcar_duas_vezes_e_o_mesmo_que_uma(self):
        """Estado absoluto: o reenvio da mesma marcação não desfaz nada."""
        self._marcar("1")
        self._marcar("1")
        self.item.refresh_from_db()
        self.assertTrue(self.item.marcado)

    def test_o_item_de_outra_pessoa_nao_se_marca_nem_se_remove(self):
        outra = create_complete_user(email="outra-avulso@exemplo.com")
        alheio = ItemAvulsoDaLista.objects.create(user=outra, semana=self.hoje, nome="Leite")

        self._marcar("1", item=alheio)
        self.client.post(reverse("plans:remover_item"), {"item_id": alheio.pk})

        alheio.refresh_from_db()
        self.assertFalse(alheio.marcado)
        self.assertTrue(ItemAvulsoDaLista.objects.filter(pk=alheio.pk).exists())

    def test_remover_tira_da_tela_e_do_banco(self):
        resposta = self.client.post(reverse("plans:remover_item"), {"item_id": self.item.pk, "opcao": "A"})

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(ItemAvulsoDaLista.objects.exists())
        self.assertEqual(self.nomes_na_tela(), [])

    def test_remover_duas_vezes_nao_estoura(self):
        self.client.post(reverse("plans:remover_item"), {"item_id": self.item.pk})
        resposta = self.client.post(reverse("plans:remover_item"), {"item_id": self.item.pk})
        self.assertEqual(resposta.status_code, 302)

    def test_o_botao_de_remover_e_um_formulario_por_item(self):
        secao = self.secao()
        self.assertIn('action="%s"' % reverse("plans:remover_item"), secao)
        self.assertIn('name="item_id" value="%d"' % self.item.pk, secao)
        self.assertIn('aria-label="Remover Café da lista"', secao)

    def test_o_script_manda_o_avulso_pela_propria_chave(self):
        """`pwa.js` é o único que roda (`app.js` não é servido): a caixa do
        avulso tem de mandar `avulso_id`, e não um `food_id` vazio."""
        from pathlib import Path

        from django.conf import settings

        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        self.assertIn('caixa.hasAttribute("data-avulso")', js)
        self.assertIn('corpo.set("avulso_id"', js)


class AJanelaDeSeteDiasTests(_Lista):
    """O risco e o avulso valem sete dias a partir do dia em que entraram."""

    def _primeiro_alimento(self):
        for corredor in shopping.shopping_list(self.plan, label="A"):
            for item in corredor["items"]:
                return item["food"]
        raise AssertionError("a lista nasceu vazia")

    def _riscados(self):
        return {
            item["food"].id
            for corredor in self.tela().context["aisles"]
            for item in corredor["items"]
            if item["marcado"]
        }

    def test_o_risco_de_ontem_continua_valendo_hoje(self):
        """Era o defeito: a leitura só via o risco do próprio dia."""
        alimento = self._primeiro_alimento()
        ItemDaListaMarcado.objects.create(
            user=self.pessoa, food=alimento, opcao="A", semana=self.hoje - timedelta(days=1)
        )
        self.assertIn(alimento.id, self._riscados())

    def test_o_risco_de_seis_dias_atras_vale_e_o_de_sete_nao(self):
        alimento = self._primeiro_alimento()
        ItemDaListaMarcado.objects.create(
            user=self.pessoa, food=alimento, opcao="A", semana=self.hoje - timedelta(days=6)
        )
        self.assertIn(alimento.id, self._riscados())

        ItemDaListaMarcado.objects.all().delete()
        ItemDaListaMarcado.objects.create(
            user=self.pessoa, food=alimento, opcao="A", semana=self.hoje - timedelta(days=7)
        )
        self.assertNotIn(alimento.id, self._riscados())

    def test_desriscar_hoje_apaga_o_risco_de_ontem(self):
        """Senão o arroz desriscado na quarta voltaria riscado na quinta,
        porque a linha de sábado continuava lá."""
        alimento = self._primeiro_alimento()
        ItemDaListaMarcado.objects.create(
            user=self.pessoa, food=alimento, opcao="A", semana=self.hoje - timedelta(days=3)
        )
        self.client.post(
            reverse("plans:marcar_item"),
            {"food_id": alimento.pk, "opcao": "A", "semana": str(self.hoje), "marcado": "0"},
        )
        self.assertEqual(ItemDaListaMarcado.objects.count(), 0)

    def test_o_avulso_de_ontem_aparece_e_o_de_oito_dias_atras_nao(self):
        ItemAvulsoDaLista.objects.create(user=self.pessoa, semana=self.hoje - timedelta(days=1), nome="Café")
        ItemAvulsoDaLista.objects.create(user=self.pessoa, semana=self.hoje - timedelta(days=8), nome="Leite")

        self.assertEqual(self.nomes_na_tela(), ["Café"])

    def test_a_janela_e_a_mesma_da_lista(self):
        inicio, fim = shopping.janela_de_marcacao(self.hoje)
        self.assertEqual(fim - inicio, timedelta(days=shopping.DAYS - 1))
        self.assertEqual(fim, self.hoje)
