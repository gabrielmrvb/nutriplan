# -*- coding: utf-8 -*-
"""A melhor série (reps×carga) é recorde ao lado da maior carga.

BENCHMARK-2026-09 (a): Hevy, Strong e Fitbod celebram o recorde na hora — e
os dois que eles celebram são "maior carga" e "melhor série". O NutriPlan
tinha o primeiro (`test_recorde_na_hora.py`). Este arquivo acrescenta o
segundo SEM tocar o contrato de `_recorde` ("não é volume, não é carga por
repetição"): é uma SEGUNDA regra, `melhor-serie`, com a mesma chave
`exercício:data` e nenhum número persistido.

Estreia não é recorde (não há série anterior para superar); exercício sem
carga não tem melhor série; carga E melhor série no mesmo toque são DUAS
conquistas (uma de cada regra), anunciadas na mesma fila.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from achievements.models import UserAchievement as Conquista
from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.test_recorde_na_hora import CONSULTAS_DO_POST_SEM_RECORDE
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class AMelhorSerieTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="melhor@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _log(self, dias_atras, serie, peso, reps):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(str(peso)), reps=reps,
        )

    def _concluir(self, peso, reps):
        return self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.item.exercise.pk, "weight_kg": str(peso), "reps": str(reps)},
        )

    # ---- o serviço ----

    def test_load_history_traz_o_maior_produto_anterior(self):
        self._log(7, 1, 60, 10)   # 600
        self._log(7, 2, 62.5, 8)  # 500 — carga maior, produto menor
        load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)
        self.assertEqual(load[self.item.exercise.pk]["melhor_serie_anterior"], Decimal("600"))
        self.assertEqual(load[self.item.exercise.pk]["recorde_anterior"], Decimal("62.5"))

    def test_supera_recorde_diz_qual_especie(self):
        self._log(7, 1, 60, 10)   # carga 60, produto 600
        ex = self.item.exercise
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("65"), reps=8, dia=self.hoje), {"carga"})
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("60"), reps=12, dia=self.hoje), {"melhor_serie"})
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("65"), reps=10, dia=self.hoje), {"carga", "melhor_serie"})
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("55"), reps=10, dia=self.hoje), set())

    def test_igualar_nao_e_superar(self):
        self._log(7, 1, 60, 10)
        self.assertEqual(services.supera_recorde(self.pessoa, self.item.exercise, Decimal("60"), reps=10, dia=self.hoje), set())

    def test_estreia_nao_e_recorde_de_especie_nenhuma(self):
        self.assertEqual(services.supera_recorde(self.pessoa, self.item.exercise, Decimal("100"), reps=20, dia=self.hoje), set())

    def test_sem_reps_nao_ha_melhor_serie(self):
        self._log(7, 1, 60, 10)
        self.assertEqual(services.supera_recorde(self.pessoa, self.item.exercise, Decimal("60"), reps=None, dia=self.hoje), set())

    def test_serie_anterior_sem_reps_nao_infla_o_produto_maximo(self):
        """Uma série antiga só com carga (sem reps anotadas) tem produto
        indefinido — ela não pode virar o "melhor anterior" a bater. Uma
        pessoa que uma vez anotou só o peso (999 kg, por exemplo um erro de
        dedo, ou um exercício isométrico sem reps) não pode travar toda
        melhora futura de reps×carga neste exercício."""
        self._log(7, 1, 60, 10)   # produto 600 — o recorde de verdade
        self._log(5, 1, 999, None)  # carga alta, sem reps: produto indefinido
        # 65 kg × 10 = 650, MENOR que 999 (então não é recorde de carga: 999
        # já é maior), mas MAIOR que 600 — então É melhor série, se e só se
        # a série sem reps não tiver sido usada como se fosse 999×algo.
        self.assertEqual(
            services.supera_recorde(self.pessoa, self.item.exercise, Decimal("65"), reps=10, dia=self.hoje),
            {"melhor_serie"},
        )

    def test_a_linha_da_serie_marca_a_melhor_serie(self):
        self._log(7, 1, 60, 10)
        self._log(0, 1, 60, 12)
        load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)
        linhas = services.linhas_de_serie(self.item, load[self.item.exercise.pk])
        self.assertTrue(linhas[0]["melhor_serie"])
        self.assertFalse(linhas[0]["recorde"])

    # ---- a rota que a execução usa ----

    def test_a_melhor_serie_vira_conquista_na_hora(self):
        self._log(7, 1, 60, 10)
        self._concluir(60, 12)
        slugs = set(Conquista.objects.filter(user=self.pessoa).values_list("slug", flat=True))
        self.assertIn("melhor-serie", slugs)
        self.assertNotIn("novo-recorde", slugs)

    def test_carga_e_melhor_serie_no_mesmo_toque_sao_duas_conquistas(self):
        self._log(7, 1, 60, 10)
        self._concluir(65, 10)
        slugs = set(Conquista.objects.filter(user=self.pessoa).values_list("slug", flat=True))
        self.assertTrue({"novo-recorde", "melhor-serie"} <= slugs, slugs)

    def test_a_tela_diz_melhor_serie_na_pastilha_e_no_fato(self):
        """`assertIn("melhor série", html.lower())` passava por acidente: o
        título do AVISO de conquista ("Melhor série: <exercício>.") e o FATO
        abaixo do campo ("Melhor série: 60 kg × 10") também carregam a
        mesma frase — apagar o `<span class="series__recorde">melhor
        série</span>` de dentro da pastilha (`agora.html`) continuava verde
        (revisão final de 16/09/2026, achado F4). Âncora na PASTILHA — o
        `<li class="series__item…">` da série concluída — e o FATO checado
        pela própria marca, e não pela mesma substring solta."""
        self._log(7, 1, 60, 10)
        self._concluir(60, 12)
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()

        itens = re.findall(r'<li class="series__item[^"]*">(.*?)</li>', html, re.S)
        self.assertIn('class="series__recorde"', itens[0])
        self.assertIn("melhor série", itens[0])

        self.assertRegex(
            html,
            r'<span class="agora__recorde">\s*Melhor série:\s*'
            r'<b class="num">60 kg × 10</b>',
        )

    def test_o_post_sem_recorde_nao_custa_mais(self):
        # Desde 16/09/2026 a PRIMEIRA série do dia também avalia o catálogo
        # inteiro (B5, `test_recorde_na_hora.CONSULTAS_DO_POST_SEM_RECORDE`) —
        # por isso já existe uma série de hoje aqui: a medida é a SEGUNDA,
        # a que a fila reenvia em rajada, não a que abre o dia.
        self._log(7, 1, 60, 10)   # produto 600, carga 60 — a régua
        self._log(0, 1, 55, 8)    # já há treino hoje; nem carga nem melhor série
        with CaptureQueriesContext(connection) as consultas:
            self._concluir(55, 8)  # repete a mesma série: nenhuma espécie de recorde
        self.assertLessEqual(len(consultas), CONSULTAS_DO_POST_SEM_RECORDE, consultas.captured_queries)

    def test_a_frase_da_conquista_nao_carrega_numero(self):
        """O nome do exercício entra na frase ("Melhor série: <nome>.") e
        pode ter dígito de verdade (ex. um exercício "Cadeira flexora 90°"
        do catálogo) sem que isso seja o contrato quebrando — o que a
        privacidade proíbe é PESO/REPS, não o nome. Tira o nome antes de
        contar dígito, ou este teste reprovaria por coincidência de catálogo,
        não pela regra que ele existe para provar."""
        self._log(7, 1, 60, 10)
        self._concluir(60, 12)
        conquista = Conquista.objects.get(user=self.pessoa, slug="melhor-serie")
        nome = self.item.exercise.name
        texto = (conquista.titulo + conquista.frase).replace(nome, "")
        self.assertFalse(any(c.isdigit() for c in texto), texto)

    def test_a_frase_usa_o_titulo_de_cada_regra(self):
        """`UserAchievement.frase` (achievements/models.py) usa
        `self.regra.titulo` como prefixo, e não mais o texto fixo "Novo
        recorde: " — com duas regras de RECORDE, um prefixo fixo mentiria na
        segunda. Carga E melhor série no mesmo toque produzem as duas
        conquistas; cada uma tem que carregar o título da SUA regra.

        Sabotagem: reverter o prefixo para "Novo recorde: " fixo (em vez de
        `self.regra.titulo`) faz a asserção da melhor-série ficar vermelha,
        enquanto a do novo-recorde continuaria passando por coincidência."""
        self._log(7, 1, 60, 10)
        self._concluir(65, 10)  # carga E melhor série no mesmo toque
        nome = self.item.exercise.name
        melhor_serie = Conquista.objects.get(user=self.pessoa, slug="melhor-serie")
        novo_recorde = Conquista.objects.get(user=self.pessoa, slug="novo-recorde")
        self.assertEqual(melhor_serie.frase, "Melhor série: %s." % nome)
        self.assertEqual(novo_recorde.frase, "Novo recorde: %s." % nome)
