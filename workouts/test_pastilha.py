# -*- coding: utf-8 -*-
"""A pastilha da série diz carga × reps de hoje, e a última vez enquanto falta.

`set_rows` sempre carregou as reps de hoje e `load["anterior"]` sempre teve a
mesma série do último treino — e a tela mostrava só a carga de hoje. A
pesquisa de 13/09/2026 achou o dado morto em duas cópias (`services` e
`views`), e a frase "Sugestão: manter X" citando um número diferente do que
o campo trazia preenchido: a frase lia `melhor_anterior`, o campo lia
`sugestao_carga` (hoje > mesma série anterior > melhor). Duas afirmações na
mesma tela sobre o mesmo número, divergindo.

Agora: UMA função (`linhas_de_serie`), a pastilha feita mostra "62,50×9", a
pendente mostra "60×10" em cinza — a mesma série da última vez, com "última
vez:" para o leitor de tela —, e a frase de sugestão cita o número do campo.
A prioridade da sugestão NÃO muda (`test_hoje_manda_na_sugestao`).
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


class APastilhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="pastilha@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        plano = services.get_active_routine(self.pessoa)
        sessao = services.sessao_do_dia(plano, self.hoje)  # como o app resolve, nunca por weekday
        # A execução abre a opção ESCOLHIDA (a 1, gravada aqui): os itens de
        # teste vêm DELA — um item que só existe na opção 2 dava 404 na
        # execução em dias em que a recomendada era a outra.
        escolher_opcao_de_hoje(self.pessoa)
        itens = list(sessao.da_opcao(1))
        self.item = next(
            i for i in itens
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS and i.sets >= 3
        )
        self.corporal = next((i for i in itens if i.exercise.equipment == "bodyweight"), None)

    def _log(self, exercicio, dias_atras, serie, peso, reps):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=exercicio, date=self.hoje - timedelta(days=dias_atras),
            set_number=serie, weight_kg=Decimal(peso), reps=reps,
        )

    def _html(self, item):
        url = "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        return sem_scripts(self.client.get(url).content.decode())

    def _pastilhas(self, html):
        return re.findall(r'<li class="series__item[^"]*">(.*?)</li>', html, re.S)

    def test_feita_mostra_carga_x_reps_e_pendente_mostra_a_ultima_vez(self):
        self._log(self.item.exercise, 2, 1, "60", 10)
        self._log(self.item.exercise, 2, 2, "60", 10)
        self._log(self.item.exercise, 0, 1, "62.5", 9)

        pastilhas = self._pastilhas(self._html(self.item))
        self.assertGreaterEqual(len(pastilhas), 3)
        self.assertIn("62,50×9", re.sub(r"\s+", "", pastilhas[0]))
        self.assertIn('class="series__antes', pastilhas[1])
        self.assertIn("última vez", pastilhas[1])
        self.assertIn("60×10", re.sub(r"\s+", "", pastilhas[1]))
        # A terceira nunca foi anotada: nem hoje, nem da última vez.
        self.assertNotIn("series__antes", pastilhas[2])
        self.assertIn("—", pastilhas[2])

    def test_sem_reps_a_pastilha_mostra_so_a_carga(self):
        self._log(self.item.exercise, 0, 1, "62.5", None)
        primeira = re.sub(r"\s+", "", self._pastilhas(self._html(self.item))[0])
        self.assertIn("62,5", primeira)
        self.assertNotIn("×", primeira)

    def test_peso_do_corpo_mostra_so_as_reps(self):
        if self.corporal is None:
            self.skipTest("a sessão de hoje não tem exercício de peso corporal")
        self._log(self.corporal.exercise, 0, 1, "0", 12)
        primeira = re.sub(r"\s+", "", self._pastilhas(self._html(self.corporal))[0])
        self.assertIn("×12", primeira)
        self.assertNotIn("0×", primeira)
        self.assertNotIn("kg", primeira)

    def test_a_frase_de_sugestao_cita_o_mesmo_numero_do_campo(self):
        """Hoje manda: com uma série a 62,5 hoje, campo e frase dizem 62,5 —
        e não os 60 da última vez, que continuam como FATO na mesma linha."""
        self._log(self.item.exercise, 2, 1, "60", 10)
        self._log(self.item.exercise, 0, 1, "62.5", 9)

        html = self._html(self.item)
        campo = re.search(r'name="weight_kg"[^>]*value="([^"]*)"', html).group(1)
        self.assertEqual(campo, "62,50")
        sugestao = html.split('class="agora__anterior-sugestao"', 1)[1].split("</span>", 1)[0]
        self.assertIn("62,50", sugestao)
        fato = html.split('class="agora__anterior-fato"', 1)[1].split("</span>", 1)[0]
        self.assertIn("60", fato)

    def test_as_duas_copias_de_set_rows_viraram_uma(self):
        """`views.set_rows` e o bloco de `estado_do_treino` divergiam há duas
        campanhas; agora as duas chamam `services.linhas_de_serie`."""
        from workouts import views

        linhas = services.linhas_de_serie(self.item, {
            "hoje": {1: self._log(self.item.exercise, 0, 1, "62.5", 9)},
            "anterior": {2: self._log(self.item.exercise, 2, 2, "60", 10)},
        })
        self.assertEqual(linhas[0]["weight"], Decimal("62.5"))
        self.assertEqual(linhas[1]["antes_peso"], Decimal("60"))
        self.assertEqual(linhas[1]["antes_reps"], 10)
        self.assertIs(views.set_rows, services.linhas_de_serie)
