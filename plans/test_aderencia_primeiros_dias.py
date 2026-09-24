"""A aderência não reprova o primeiro dia — nem o dia que ainda não acabou.

Item 6 da missão de UX (22/09/2026): o Progresso mostrava "20 % Aderência"
para quem registrou 1 de 5 refeições no primeiro dia de uso, ao meio-dia —
uma nota de reprovação para um dia que só tinha chegado ao lanche da manhã.
O denominador continua sendo O PLANO (a doutrina da ofensiva), mas o dia
de HOJE só cobra as refeições cujo horário já passou, e o consolidado só
soma os dias FECHADOS: no primeiro dia ele mostra "1/2 até agora" em vez
de uma porcentagem.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans import services, tracking
from plans.models import MealLog, MealStatus
from plans.tests import CatalogFixture, create_complete_user


class AderenciaDosPrimeirosDiasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user(email="aderencia@exemplo.com")
        self.plan = services.create_plan(self.user)
        self.slots = list(self.plan.slots.order_by("time"))
        self.hoje = timezone.localdate()
        self.agora = timezone.localtime().time()
        self.client.force_login(self.user)

    def _marcar(self, dia, quantas, status=MealStatus.DONE):
        for slot in self.slots[:quantas]:
            MealLog.objects.update_or_create(user=self.user, slot=slot, date=dia, defaults={"status": status})

    def test_hoje_so_cobra_as_refeicoes_que_ja_passaram(self):
        self._marcar(self.hoje, 1)
        ja_passaram = len([s for s in self.slots if s.time <= self.agora])
        self.assertGreater(ja_passaram, 0, "a suíte congela às 12:00: alguma refeição já passou")
        self.assertLess(ja_passaram, len(self.slots))
        linha = tracking.history(self.user)[0]
        self.assertTrue(linha["is_today"])
        self.assertEqual(linha["previstas"], ja_passaram)
        self.assertEqual(linha["adherence_pct"], int(100 / ja_passaram))
        self.assertTrue(linha["parcial"])

    def test_no_primeiro_dia_o_consolidado_nao_e_uma_porcentagem(self):
        self._marcar(self.hoje, 1)
        totais = tracking.adherence(tracking.history(self.user))
        self.assertIsNone(totais["adherence_pct"])
        self.assertEqual(totais["hoje_feitas"], 1)
        self.assertEqual(totais["days"], 1)
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertNotIn("20%", html)
        self.assertIn("até agora", html)

    def test_com_dias_fechados_a_porcentagem_e_dos_dias_fechados(self):
        ontem = self.hoje - timedelta(days=1)
        self._marcar(ontem, 4)
        self._marcar(self.hoje, 1)
        totais = tracking.adherence(tracking.history(self.user))
        self.assertEqual(totais["adherence_pct"], 80)
        # O TILE separa número e unidade em dois elementos desde o redesenho
        # (23/09/2026), então "80%" deixou de existir como string do HTML. A
        # régua passa a ser o tile, que é onde o número mora — e ela é mais
        # forte: casa com o valor E com o rótulo, em vez de com dois
        # caracteres que qualquer outro lugar da página poderia ter.
        painel = self.client.get(reverse("plans:history")).context["painel"]
        dieta = [t for t in painel["tiles"] if t.chave == "dieta"][0]
        self.assertEqual((dieta.valor, dieta.unidade), ("80", "%"))

    def test_no_dia_do_cadastro_as_refeicoes_de_antes_dele_nao_entram(self):
        """Quem se cadastrou às 10h não deve o café das 7h30 (achado #7)."""
        from datetime import datetime, time
        self.user.date_joined = timezone.make_aware(datetime.combine(self.hoje, time(10, 0)))
        self.user.save(update_fields=["date_joined"])
        self._marcar(self.hoje, 0)
        # marca a refeição das 11h (a primeira depois do cadastro)
        depois = [s for s in self.slots if s.time >= time(10, 0) and s.time <= self.agora]
        self.assertTrue(depois)
        MealLog.objects.create(user=self.user, slot=depois[0], date=self.hoje, status=MealStatus.DONE)
        linha = tracking.history(self.user)[0]
        self.assertEqual(linha["previstas"], len(depois))
        self.assertEqual(linha["adherence_pct"], int(100 / len(depois)))

    def test_marcar_uma_refeicao_futura_nao_passa_de_cem(self):
        self._marcar(self.hoje, len(self.slots))  # tudo marcado ao meio-dia
        linha = tracking.history(self.user)[0]
        self.assertEqual(linha["adherence_pct"], 100)
