"""A VERSÃO RÁPIDA SÓ EXISTE ONDE CORTA ALGUMA COISA — e no perfil "só peso
do corpo" não corta (decisão registrada em 18/09/2026, opção (a)).

Provado em produção com conta descartável em 18/09: a ficha A desse
perfil tem 3 exercícios e ~30 minutos — cabe inteira nos 40 minutos da
rápida (`TETO_RAPIDO_MIN`), então "Menos tempo hoje?" NÃO aparece no
painel. Gerar uma "rápida" com menos séries para esse perfil seria oferecer
o mesmo treino com outro nome, o defeito de veracidade que o app recusa
desde a faixa de duração ("texto da ficha só afirma o que aconteceu"). O
botão é `hoje.rapida_muda` (`preparar_dia`): removidos ou séries diferentes.
Em casa com halteres (B com 6 exercícios e ~48 min) ele aparece.
"""
from datetime import date, timedelta
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, Equipamento, TrainingDay
from plans.tests import create_complete_user
from workouts import services
from workouts.opcoes import TETO_RAPIDO_MIN
from workouts.tests import sem_scripts

SEGUNDA = date(2026, 9, 14)


def _pessoa(email, equipamento):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO, equipamento=equipamento,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(5):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class ARapidaPorPerfilDeEquipamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = mock.patch("django.utils.timezone.localdate", return_value=SEGUNDA)
        self.relogio.start()
        self.addCleanup(self.relogio.stop)

    def _painel(self, equipamento):
        user = _pessoa("rapida-%s@exemplo.com" % equipamento, equipamento)
        plano = services.create_routine(user)
        self.client.force_login(user)
        resposta = self.client.get(reverse("workouts:routine"))
        hoje = resposta.context["hoje"]
        return plano, hoje, sem_scripts(resposta.content.decode())

    def test_so_peso_do_corpo_nao_oferece_a_rapida_porque_nao_ha_o_que_cortar(self):
        plano, hoje, html = self._painel(Equipamento.PESO_CORPORAL)
        # A ficha de hoje (A) já cabe na rápida: o motor não tira nada.
        self.assertLessEqual(hoje.minutos, TETO_RAPIDO_MIN, hoje.minutos)
        self.assertFalse(hoje.rapida_muda)
        self.assertNotIn("Menos tempo hoje?", html)
        self.assertNotIn(reverse("workouts:rapida_hoje"), html)
        # E não é "hoje sem treino": é dia de treino, com a ficha inteira.
        self.assertIn("Começar treino", html)

    def test_em_casa_com_halteres_a_rapida_aparece_porque_corta(self):
        """Controle positivo: mesmo teste, perfil em que a rápida muda algo."""
        plano, hoje, html = self._painel(Equipamento.CASA_HALTERES)
        self.assertTrue(hoje.rapida_muda)
        self.assertIn("Menos tempo hoje?", html)
        self.assertLess(hoje.rapida_minutos, hoje.minutos)

    def test_o_post_da_rapida_no_perfil_sem_corte_nao_muda_a_ficha(self):
        """Quem chegar à rota sem o botão (link velho) pina a versão, mas a
        ficha continua a mesma: nada é removido e as séries não mudam."""
        plano, hoje, _ = self._painel(Equipamento.PESO_CORPORAL)
        antes = [(i.exercise_id, i.sets) for i in hoje.itens_do_dia]
        self.client.post(reverse("workouts:rapida_hoje"))
        estado = services.estado_do_treino(plano.user)
        self.assertEqual([(i.exercise_id, i.sets) for i in estado.itens], antes)
        self.assertEqual(estado.removidos, [])
