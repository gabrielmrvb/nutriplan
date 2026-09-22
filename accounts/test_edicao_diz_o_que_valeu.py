"""Editar treinos pelo Perfil diz o que valeu — como a duração já dizia.

Achado #8 das personas (21/09/2026): trocar "só peso do corpo" por "em
casa, com halteres" respondia "Alterações salvas." e a ficha continuava
idêntica, sem dizer que muda amanhã; no dia 2 virou outra em silêncio. A
troca de DURAÇÃO, ao lado, fazia certo: "Há série registrada hoje, então
a ficha muda amanhã." A etapa 2 em edição passa a dizer a mesma coisa —
remontada, muda amanhã, ou ajustada à mão e por isso intocada.
"""
from decimal import Decimal

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Equipamento, Profile, User
from accounts.test_tres_etapas import ETAPA1, ETAPA2, ETAPA3, etapa
from workouts.models import Exercise, ExerciseLog, SessionExercise, TrainingPlan


class EdicaoDizOQueValeuTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(email="edita@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), {**ETAPA2, "musculacao": "sim", "equipamento": "peso_corporal", "experiencia": "iniciante"})
        self.client.post(etapa(3), ETAPA3, follow=True)
        self.editar = etapa(2) + "?origem=perfil"

    def _mensagens(self, resposta):
        return [str(m) for m in get_messages(resposta.wsgi_request)]

    def _editar(self, **mudancas):
        dados = {**ETAPA2, "musculacao": "sim", "equipamento": "peso_corporal", "experiencia": "iniciante", **mudancas}
        return self.client.post(self.editar, dados)

    def test_sem_serie_hoje_diz_que_a_ficha_foi_remontada(self):
        resposta = self._editar(equipamento="casa_halteres")
        self.assertEqual(Profile.objects.get(user=self.user).equipamento, Equipamento.CASA_HALTERES)
        mensagens = " ".join(self._mensagens(resposta))
        self.assertIn("remontada", mensagens)
        self.assertEqual(TrainingPlan.objects.get(user=self.user, is_active=True).equipamento, "casa_halteres")

    def test_com_serie_hoje_diz_que_muda_amanha(self):
        plano = TrainingPlan.objects.get(user=self.user, is_active=True)
        item = SessionExercise.objects.filter(session__plan=plano).select_related("exercise").first()
        ExerciseLog.objects.create(user=self.user, exercise=item.exercise, date=timezone.localdate(), set_number=1, weight_kg=Decimal("0"), reps=10)
        resposta = self._editar(equipamento="casa_halteres")
        mensagens = " ".join(self._mensagens(resposta))
        self.assertIn("muda amanhã", mensagens)
        # e a ficha de hoje NÃO mudou
        self.assertEqual(TrainingPlan.objects.get(user=self.user, is_active=True).pk, plano.pk)

    def test_sem_mudanca_de_entrada_so_diz_salvas(self):
        resposta = self._editar()
        mensagens = " ".join(self._mensagens(resposta))
        self.assertIn("Alterações salvas", mensagens)
        self.assertNotIn("remontada", mensagens)
        self.assertNotIn("muda amanhã", mensagens)
