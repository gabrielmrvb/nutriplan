"""A SEMANA DA ÁGUA COMEÇA NA CONTA (pente-fino de qualidade, onda 5, 28/09/2026).

Medido no dia 1 da corredora: "Últimos 7 dias" listava 22/09 a 27/09 —
seis dias antes de a conta existir — e cobrava "0/7 com registro". O mesmo
limite que a ofensiva já respeita (`streaks.primeiro_dia_da_conta`): antes
do cadastro não havia app para registrar. E com um dia só a semana é o
próprio "Hoje" repetido, então o bloco não aparece.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from plans import tracking
from plans.tests import create_complete_user


class ASemanaDaAguaComecaNaContaTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()
        self.hoje = timezone.localdate()

    def nasceu_ha(self, dias):
        User.objects.filter(pk=self.user.pk).update(date_joined=timezone.now() - timedelta(days=dias))
        self.user.refresh_from_db()

    def test_conta_de_tres_dias_mostra_tres_dias(self):
        self.nasceu_ha(2)
        semana = tracking.agua_dos_ultimos_dias(self.user, 2000, hoje=self.hoje)
        self.assertEqual(semana["dias"], 3)
        self.assertEqual(semana["linhas"][0]["data"], self.hoje - timedelta(days=2))

    def test_controle_conta_antiga_continua_com_sete(self):
        self.assertEqual(tracking.agua_dos_ultimos_dias(self.user, 2000, hoje=self.hoje)["dias"], 7)

    def test_no_primeiro_dia_a_tela_nao_desenha_a_semana(self):
        self.nasceu_ha(0)
        self.client.force_login(self.user)
        tela = self.client.get(reverse("plans:hydration"))
        self.assertEqual(tela.status_code, 200)
        self.assertNotContains(tela, 'aria-label="Água registrada por dia"')

    def test_controle_no_segundo_dia_a_semana_aparece(self):
        self.nasceu_ha(1)
        self.client.force_login(self.user)
        tela = self.client.get(reverse("plans:hydration"))
        self.assertContains(tela, "Últimos 2 dias")
        self.assertContains(tela, "0/2")
