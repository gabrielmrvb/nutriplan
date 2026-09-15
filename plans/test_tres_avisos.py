"""Três avisos que faltavam: sessão vencida, alimento não reconhecido, peso ecoado.

UX E01: a sessão vence debaixo de um toque, o POST vira `/conta/entrar/?next=…`
e a tela dizia "Bom te ver de volta" — o toque se perdeu em silêncio. Com
`next`, a entrada diz que a sessão venceu e que o toque não foi salvo.

UX UXA-04: em "Comi outra coisa", um alimento fora do catálogo era descartado
em silêncio — a refeição entrava, mas aquela linha não contava nas calorias
e ninguém sabia. A refeição continua entrando; a tela avisa qual nome não
achou.

UX UXA-06: salvar o peso fazia a faixa da Home sumir, e o valor só existia
dentro de "Dados do cálculo". A MENSAGEM ecoa o número. A faixa NÃO fica
como eco: `ConvitePesagemNoPainelTests` guarda uma decisão medida — a
primeira refeição começa a 740 px numa dobra que termina a 776, e "estado
ocupado sem ação pendente é espaço da dobra gasto para dizer que não há o
que fazer". Corrigir continua em Progresso, onde o campo abre com o peso
de hoje.

PA-03 (o histórico do navegador cresce a cada registro de água) fica FORA:
o POST + redirecionamento é o que cria a entrada, e só um envio sem
navegação resolve — é o caminho de `fila.js` online, que não é desta onda.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry
from plans import services
from plans.models import MealLog, MealSlot, MealStatus
from plans.tests import create_complete_user


class SessaoVencidaTests(TestCase):
    def test_com_next_a_entrada_diz_que_o_toque_nao_foi_salvo(self):
        html = self.client.get(reverse("accounts:login") + "?next=/agua/").content.decode()
        self.assertIn("Sua sessão venceu", html)
        self.assertIn("não foi salvo", html)
        self.assertNotIn("Bom te ver de volta", html)

    def test_sem_next_a_entrada_e_a_de_sempre(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn("Bom te ver de volta", html)
        self.assertNotIn("Sua sessão venceu", html)


class AlimentoNaoReconhecidoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = MealSlot.objects.filter(plan=self.plan).first()
        self.client.force_login(self.user)

    def _post(self, alimentos):
        dados = {"status": MealStatus.OFF_PLAN, "notes": "pizza com a família"}
        dados["alimento"] = [a for a, _ in alimentos]
        dados["gramas"] = [g for _, g in alimentos]
        return self.client.post(reverse("plans:mark_meal", args=[self.slot.pk]), dados)

    def test_nome_fora_do_catalogo_avisa_e_a_refeicao_entra(self):
        resposta = self._post([("Xuxuzinho da vovó", "100")])
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(MealLog.objects.filter(user=self.user, slot=self.slot, status=MealStatus.OFF_PLAN).exists())
        textos = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertTrue(any("Xuxuzinho da vovó" in m and "Não achei" in m for m in textos), textos)

    def test_nome_do_catalogo_nao_avisa(self):
        from catalog.models import Food
        comida = Food.objects.filter(is_active=True).first()
        resposta = self._post([(comida.name, "100")])
        textos = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertFalse(any("Não achei" in m for m in textos), textos)


class PesoEcoadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        services.create_plan(self.user)
        self.client.force_login(self.user)

    def test_a_mensagem_traz_o_numero(self):
        resposta = self.client.post(
            reverse("accounts:log_weight"), {"weight_kg": "82,5", "origem": "hoje"}
        )
        textos = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertIn("Peso registrado: 82,50 kg.", textos)

    def test_corrigir_continua_em_progresso_com_o_campo_preenchido(self):
        WeightEntry.objects.update_or_create(
            user=self.user, date=timezone.localdate(), defaults={"weight_kg": Decimal("82.5")}
        )
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertIn('value="82,50"', html)
