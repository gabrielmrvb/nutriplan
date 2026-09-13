# -*- coding: utf-8 -*-
"""Dupla progressão: a carga sobe quando a faixa fecha, com a razão escrita.

`_sugestao_de_carga` só repetia a última carga, e o painel ensinava em prosa
a regra que a faria subir ("quando fechar o topo da faixa em todas as séries,
suba a carga"). A regra passa a ser CALCULADA — decisão do dono em 13/09/2026,
depois da pesquisa: ACSM 2009 (+2-10% ao fechar a faixa), Plotkin 2022 (reps
com carga fixa ≈ carga), com a calibração declarada baixa.

A regra, dita inteira:

- SUBIR quando TODAS as séries prescritas da ÚLTIMA data anterior foram
  anotadas com reps ≥ rep_max, em exercício de repetições e com anilha;
- degrau ABSOLUTO: +2,5 kg no tronco e braços, +5 kg em quadríceps,
  posterior, glúteo e panturrilha (arredondado ao múltiplo de 2,5 acima);
- MANTER com a razão ("faltaram N reps na série K") quando a faixa não fechou;
- SEM frase quando o histórico é incompleto (menos séries anotadas que
  prescritas) — sem histórico não se inventa número, como sempre;
- HOJE MANDA: com série anotada hoje, o campo segue a carga de hoje e a
  progressão não interfere (`test_hoje_manda_na_sugestao`).

Quando sobe, as reps pré-preenchidas voltam ao PISO da faixa: é a dupla
progressão — carga nova, reps recomeçam de baixo. É também o que segura o
risco do prefill: subir de novo exige fechar a faixa de novo, com reps que
a pessoa precisa aumentar por conta própria.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog, Measure, MuscleGroup
from workouts.tests import create_user, dias_incluindo_hoje, sem_scripts


class _Item:
    def __init__(self, sets=3, rep_min=8, rep_max=10, measure=Measure.REPS,
                 equipment="barbell", grupo=MuscleGroup.CHEST, load=None):
        self.sets, self.rep_min, self.rep_max, self.measure = sets, rep_min, rep_max, measure
        self.load = load or {}

        class _Ex:
            pass

        self.exercise = _Ex()
        self.exercise.equipment = equipment
        self.exercise.muscle_group = grupo


class _Log:
    def __init__(self, peso, reps):
        self.weight_kg = Decimal(peso)
        self.reps = reps


def _anterior(*series):
    return {n + 1: _Log(p, r) for n, (p, r) in enumerate(series)}


class ARegraTests(TestCase):
    def test_fechou_a_faixa_em_todas_as_series_sobe_dois_e_meio_no_tronco(self):
        item = _Item(load={"anterior": _anterior((60, 10), (60, 10), (60, 10)), "hoje": {}})
        p = services.proxima_carga(item)
        self.assertEqual(p.estado, "subir")
        self.assertEqual(p.valor, Decimal("62.5"))
        self.assertIn("3×10", p.razao)

    def test_perna_sobe_cinco(self):
        item = _Item(rep_max=12, grupo=MuscleGroup.QUADS,
                     load={"anterior": _anterior((80, 12), (80, 12), (80, 12)), "hoje": {}})
        p = services.proxima_carga(item)
        self.assertEqual(p.estado, "subir")
        self.assertEqual(p.valor, Decimal("85"))

    def test_o_degrau_arredonda_ao_multiplo_de_dois_e_meio(self):
        item = _Item(load={"anterior": _anterior((61, 10), (61, 10), (61, 10)), "hoje": {}})
        self.assertEqual(services.proxima_carga(item).valor, Decimal("65"))

    def test_faltou_uma_rep_mantem_e_diz_onde(self):
        item = _Item(load={"anterior": _anterior((60, 10), (60, 10), (60, 9)), "hoje": {}})
        p = services.proxima_carga(item)
        self.assertEqual(p.estado, "manter")
        self.assertEqual(p.valor, Decimal("60"))
        self.assertIn("1 rep", p.razao)
        self.assertIn("série 3", p.razao)

    def test_historico_incompleto_nao_sugere(self):
        """Duas de três séries anotadas: sem número, sem frase."""
        item = _Item(load={"anterior": _anterior((60, 10), (60, 10)), "hoje": {}})
        self.assertIsNone(services.proxima_carga(item))

    def test_reps_nao_anotadas_contam_como_nao_fechadas(self):
        item = _Item(load={"anterior": _anterior((60, 10), (60, None), (60, 10)), "hoje": {}})
        self.assertEqual(services.proxima_carga(item).estado, "manter")

    def test_peso_do_corpo_e_segundos_ficam_fora(self):
        corporal = _Item(equipment="bodyweight", load={"anterior": _anterior((0, 15), (0, 15), (0, 15)), "hoje": {}})
        prancha = _Item(measure=Measure.SECONDS, load={"anterior": _anterior((0, 45), (0, 45), (0, 45)), "hoje": {}})
        self.assertIsNone(services.proxima_carga(corporal))
        self.assertIsNone(services.proxima_carga(prancha))

    def test_com_serie_hoje_a_progressao_nao_interfere(self):
        item = _Item(load={"anterior": _anterior((60, 10), (60, 10), (60, 10)), "hoje": {1: _Log(60, 8)}})
        self.assertIsNone(services.proxima_carga(item))

    def test_sem_historico_nenhum_nao_sugere(self):
        self.assertIsNone(services.proxima_carga(_Item(load={})))


class ATelaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="dupla@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        plano = services.get_active_routine(self.pessoa)
        sessao = next(s for s in plano.sessions.all() if s.weekday == self.hoje.weekday())
        self.item = next(
            i for i in sessao.exercises.select_related("exercise")
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _ultima_vez(self, reps_por_serie, peso="60"):
        for n, reps in enumerate(reps_por_serie, start=1):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=3),
                set_number=n, weight_kg=Decimal(peso), reps=reps,
            )

    def _html(self):
        return sem_scripts(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode())

    def _campo(self, html, nome):
        import re

        return re.search(r'name="%s"[^>]*value="([^"]*)"' % nome, html).group(1)

    def test_fechou_a_faixa_o_campo_abre_com_a_carga_nova_e_as_reps_no_piso(self):
        self._ultima_vez([self.item.rep_max] * self.item.sets)
        html = self._html()
        esperado = Decimal("60") + (Decimal("5") if self.item.exercise.muscle_group in services.GRUPOS_INFERIORES else Decimal("2.5"))
        self.assertEqual(Decimal(self._campo(html, "weight_kg").replace(",", ".")), esperado)
        self.assertEqual(self._campo(html, "reps"), str(self.item.rep_min))
        sugestao = html.split('class="agora__anterior-sugestao"', 1)[1].split("</span>", 1)[0]
        self.assertIn("subir", sugestao)
        self.assertIn("%d×%d" % (self.item.sets, self.item.rep_max), sugestao)

    def test_nao_fechou_o_campo_abre_com_a_mesma_carga_e_a_razao(self):
        reps = [self.item.rep_max] * self.item.sets
        reps[-1] = self.item.rep_max - 2
        self._ultima_vez(reps)
        html = self._html()
        self.assertEqual(self._campo(html, "weight_kg"), "60")
        sugestao = html.split('class="agora__anterior-sugestao"', 1)[1].split("</span>", 1)[0]
        self.assertIn("manter", sugestao)
        self.assertIn("2 reps", sugestao)
        self.assertIn("série %d" % self.item.sets, sugestao)

    def test_historico_incompleto_fica_como_sempre_manter_sem_razao(self):
        self._ultima_vez([self.item.rep_max])
        html = self._html()
        self.assertEqual(self._campo(html, "weight_kg"), "60")
        sugestao = html.split('class="agora__anterior-sugestao"', 1)[1].split("</span>", 1)[0]
        self.assertIn("manter", sugestao)
        self.assertNotIn("faltaram", sugestao)
