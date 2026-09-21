"""A VERSÃO RÁPIDA SÓ EXISTE ONDE CORTA ALGUMA COISA — e o que ela corta
mudou com o catálogo de peso do corpo (decisão 1 da avaliação de UX,
20/09/2026).

Até 18/09 a ficha A do "só peso do corpo" tinha 3 exercícios e ~30 minutos:
cabia inteira nos 40 minutos da rápida (`TETO_RAPIDO_MIN`), então "Menos
tempo hoje?" NÃO aparecia — gerar uma "rápida" ali seria o mesmo treino com
outro nome (o defeito de veracidade que o app recusa). Com os 34 exercícios
de peso do corpo a ficha desse perfil ficou cheia (letra A ~52 min), e agora
ele TAMBÉM oferece a rápida, como os outros. O que segue valendo é a régua:
a rápida só aparece onde `hoje.rapida_muda` (`preparar_dia`) — removidos ou
séries diferentes. O caso "sem corte" é testado com um perfil cuja duração
já é a rápida (não sobra o que cortar).
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


def _pessoa(email, equipamento, duracao=DuracaoTreino.PADRAO):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=duracao, equipamento=equipamento,
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

    def _painel(self, equipamento, duracao=DuracaoTreino.PADRAO):
        user = _pessoa("rapida-%s-%s@exemplo.com" % (equipamento, duracao), equipamento, duracao)
        plano = services.create_routine(user)
        self.client.force_login(user)
        resposta = self.client.get(reverse("workouts:routine"))
        hoje = resposta.context["hoje"]
        return plano, hoje, sem_scripts(resposta.content.decode())

    def test_peso_do_corpo_agora_oferece_a_rapida_porque_a_ficha_ficou_cheia(self):
        """Virou em 20/09/2026 (decisão 1 da avaliação de UX): com os 34
        exercícios de peso do corpo, a ficha A desse perfil passou de ~30 min
        para ~52 min — passou a haver o que cortar, e a rápida aparece, como
        nos outros perfis."""
        plano, hoje, html = self._painel(Equipamento.PESO_CORPORAL)
        self.assertGreater(hoje.minutos, TETO_RAPIDO_MIN, hoje.minutos)
        self.assertTrue(hoje.rapida_muda)
        self.assertIn("Menos tempo hoje?", html)
        self.assertIn(reverse("workouts:rapida_hoje"), html)
        self.assertLess(hoje.rapida_minutos, hoje.minutos)
        self.assertIn("Começar treino", html)

    def test_em_casa_com_halteres_a_rapida_aparece_porque_corta(self):
        """Controle positivo: mesmo teste, perfil em que a rápida muda algo."""
        plano, hoje, html = self._painel(Equipamento.CASA_HALTERES)
        self.assertTrue(hoje.rapida_muda)
        self.assertIn("Menos tempo hoje?", html)
        self.assertLess(hoje.rapida_minutos, hoje.minutos)

    def test_o_post_da_rapida_no_perfil_sem_corte_nao_muda_a_ficha(self):
        """Quem chegar à rota sem o botão (link velho) pina a versão, mas a
        ficha continua a mesma: nada é removido e as séries não mudam.

        O caso "sem corte" agora é um perfil cuja DURAÇÃO já é a rápida — a
        ficha nasce dentro do teto, então não sobra o que cortar. (Antes era o
        peso do corpo, que ficou cheio com o catálogo de 20/09.)"""
        plano, hoje, _ = self._painel(Equipamento.COMPLETA, DuracaoTreino.RAPIDO)
        self.assertFalse(hoje.rapida_muda, "o perfil rápido não deveria ter corte")
        antes = [(i.exercise_id, i.sets) for i in hoje.itens_do_dia]
        self.client.post(reverse("workouts:rapida_hoje"))
        estado = services.estado_do_treino(plano.user)
        self.assertEqual([(i.exercise_id, i.sets) for i in estado.itens], antes)
        self.assertEqual(estado.removidos, [])
