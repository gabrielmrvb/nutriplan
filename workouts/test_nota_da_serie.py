# -*- coding: utf-8 -*-
"""A OBSERVAÇÃO E A FALHA DE UMA SÉRIE (22/09/2026).

Pedido do dono na missão do Treino: "campo de observação opcional por série
('falhei na 5ª', 'dor no ombro') e marcador de falha — vira dado para a
progressão".

As três decisões que este arquivo prende:

1. **os dois campos viajam no MESMO corpo da série**, então a fila offline
   os reenvia sem contrato novo, e item antigo (sem os campos) cai no
   default — nada quebra;
2. **a falha é um FATO da pessoa**, não uma inferência do app: repetição
   abaixo da faixa pode ser aquecimento, drop set ou anotação parcial. Só
   quem estava lá sabe que a barra parou no meio;
3. **ela SEGURA o subir, e não baixa nada.** Quem fechou a faixa mas marcou
   falha recebia "+2,5 kg" por uma repetição que não subiu; agora recebe
   "manter", com a razão dita. A adaptação continua sendo LEITURA — nenhum
   número é reduzido, nenhuma prescrição é reescrita.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import adaptacao, services
from workouts.models import ExerciseLog
from workouts.tests import create_user, escolher_opcao_de_hoje


class ANotaDaSerieTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(
            email="nota@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(self.user)
        escolher_opcao_de_hoje(self.user)
        self.client.force_login(self.user)
        self.estado = services.estado_do_treino(self.user)
        self.item = self.estado.itens[0]

    def _post(self, **extra):
        dados = {
            "exercise_id": self.item.exercise_id,
            "weight_kg": "40",
            "reps": "8",
            "op_id": "op-nota-%s" % extra.get("op", "1"),
            "dia": timezone.localdate().isoformat(),
            "sessao": self.estado.sessao.pk,
        }
        extra.pop("op", None)
        dados.update(extra)
        return self.client.post(reverse("workouts:record_set"), dados, follow=True)

    def test_a_tela_oferece_anotar_e_marcar_falha(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn('name="nota"', html)
        self.assertIn('name="falhou"', html)
        self.assertIn("Anotar algo desta série", html)

    def test_a_observacao_e_gravada_com_a_serie(self):
        self._post(nota="dor no ombro")
        log = ExerciseLog.objects.get(user=self.user, exercise=self.item.exercise)
        self.assertEqual(log.nota, "dor no ombro")
        self.assertFalse(log.falhou)

    def test_a_falha_e_gravada_e_aparece_na_fileira(self):
        self._post(falhou="1", nota="parou no meio")
        log = ExerciseLog.objects.get(user=self.user, exercise=self.item.exercise)
        self.assertTrue(log.falhou)
        html = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode()
        self.assertIn("series__item--falhou", html)
        self.assertIn("parou no meio", html)

    def test_sem_anotar_nada_a_serie_continua_igual(self):
        """Controle positivo: os campos são OPCIONAIS."""
        self._post()
        log = ExerciseLog.objects.get(user=self.user, exercise=self.item.exercise)
        self.assertEqual(log.nota, "")
        self.assertFalse(log.falhou)
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertNotIn("series__item--falhou", html)

    def test_uma_nota_gigante_e_cortada_e_nao_recusa_a_serie(self):
        """Perder o toque por causa do texto seria o pior desfecho."""
        self._post(nota="x" * 500)
        log = ExerciseLog.objects.get(user=self.user, exercise=self.item.exercise)
        self.assertEqual(len(log.nota), 120)


class AFalhaSeguraOSubirTests(TestCase):
    """A adaptação é LEITURA: a falha segura o subir e não baixa nada."""

    class _Exercicio:
        sem_carga = False
        muscle_group = "chest"

    class _Item:
        sets = 3
        rep_min = 8
        rep_max = 10
        measure = "reps"
        load = {}

        def __init__(self):
            self.exercise = AFalhaSeguraOSubirTests._Exercicio()

    class _Registro:
        def __init__(self, peso, reps, falhou=False):
            self.weight_kg = Decimal(str(peso))
            self.reps = reps
            self.falhou = falhou

    def _sessao(self, falhou_na=None):
        return {
            n: self._Registro(60, 10, falhou=(n == falhou_na)) for n in (1, 2, 3)
        }

    def test_fechou_a_faixa_sem_falha_sobe(self):
        hoje = timezone.localdate()
        ontem = hoje - timedelta(days=3)
        p = adaptacao.ajuste(self._Item(), [(ontem, self._sessao())], None, hoje)
        self.assertEqual(p.estado, adaptacao.Estado.SUBIR)

    def test_a_mesma_sessao_com_falha_marcada_mantem_e_diz_por_que(self):
        hoje = timezone.localdate()
        ontem = hoje - timedelta(days=3)
        p = adaptacao.ajuste(self._Item(), [(ontem, self._sessao(falhou_na=3))], None, hoje)
        self.assertEqual(p.estado, adaptacao.Estado.MANTER)
        self.assertIn("falha na série 3", p.razao)
        self.assertEqual(p.valor, Decimal("60"), "nada é BAIXADO — a adaptação é leitura")
