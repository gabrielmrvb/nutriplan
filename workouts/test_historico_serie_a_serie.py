# -*- coding: utf-8 -*-
"""O histórico do exercício mostra CADA SÉRIE, com a carga dela.

MEDIDO no navegador em 24/09/2026, conta de teste, três séries registradas
pela execução: 60 kg × 8, 62,5 × 7 e 62,5 × 6. O banco guardou as três
certas — `ExerciseLog` sempre teve `set_number` e `weight_kg` por linha — e
a leitura do exercício (`/treino/exercicio/<id>/`, "Como fui") escreveu:

    24/09   62,50 × 8, 7, 6

Uma carga para as três, e a carga era o MÁXIMO da sessão:
`historico_do_exercicio` reduzia o dia a `max(weight_kg)` e juntava as
repetições numa lista. A primeira série, que foi a 60, aparecia como 62,5 —
o número da tela divergindo do número guardado, que é o defeito que esta
missão existe para fechar.

O volume vem junto pela mesma razão: com uma carga só por dia não havia como
conferir a conta. `60×8 + 62,5×7 + 62,5×6` são 1 292,5 kg, e é isso que a
tela diz agora.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje

#: As três séries do relato, na ordem em que foram feitas.
SERIES = ((1, "60.00", 8), (2, "62.50", 7), (3, "62.50", 6))


class OHistoricoMostraCadaSerieTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="serie@exemplo.com", weekdays=dias_incluindo_hoje(4))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        sessao = services.sessao_do_dia(plano, timezone.localdate())
        self.exercicio = sessao.exercises.first().exercise
        self.hoje = timezone.localdate()
        for numero, carga, reps in SERIES:
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.exercicio, date=self.hoje,
                set_number=numero, weight_kg=Decimal(carga), reps=reps,
            )

    def test_cada_serie_traz_a_propria_carga_e_as_proprias_reps(self):
        dias = services.historico_do_exercicio(self.pessoa, self.exercicio)
        self.assertEqual(len(dias), 1)
        medido = [
            (s["numero"], str(s["carga"]), s["reps"]) for s in dias[0]["series"]
        ]
        self.assertEqual(medido, [(n, c, r) for n, c, r in SERIES])

    def test_o_volume_da_sessao_e_series_vezes_reps_vezes_carga(self):
        """A conta que a pessoa consegue refazer no papel — e a razão de o
        volume vir com as séries: sem ele, uma lista de pares não fecha."""
        dias = services.historico_do_exercicio(self.pessoa, self.exercicio)
        esperado = sum(Decimal(c) * r for _, c, r in SERIES)
        self.assertEqual(dias[0]["volume"], esperado)

    def test_a_tela_escreve_a_carga_de_cada_serie(self):
        """A função pode estar certa e a TELA continuar errada: era o
        template que juntava `carga` com `reps|join`."""
        html = self.client.get(
            reverse("workouts:exercicio", args=[self.exercicio.pk])
        ).content.decode()
        historico = html.split('class="data-list historico"', 1)[1].split("</dl>", 1)[0]
        self.assertIn("60", historico)
        self.assertIn("62,50", historico)
        # A carga máxima NÃO pode aparecer três vezes: era o defeito.
        self.assertEqual(historico.count("62,50"), 2, historico)

    def test_sabotagem_mudar_a_carga_da_primeira_serie_muda_a_tela(self):
        """A prova de que a tela LÊ o banco: altero a série 1 no banco e a
        tela tem de mudar. Antes não mudava — ela mostrava o máximo do dia,
        e 60 ou 55 davam a mesma linha."""
        def linha():
            html = self.client.get(
                reverse("workouts:exercicio", args=[self.exercicio.pk])
            ).content.decode()
            return html.split('class="data-list historico"', 1)[1].split("</dl>", 1)[0]

        antes = linha()
        ExerciseLog.objects.filter(
            user=self.pessoa, exercise=self.exercicio, date=self.hoje, set_number=1
        ).update(weight_kg=Decimal("47.50"))
        depois = linha()
        self.assertNotEqual(antes, depois, "a tela não acompanhou o banco")
        self.assertIn("47,50", depois)

    def test_exercicio_sem_carga_continua_mostrando_so_repeticoes(self):
        """Peso do corpo grava ZERO (`weight_kg` é NOT NULL), e "0,00 × 8"
        seria o mesmo defeito ao contrário: um número que não descreve nada."""
        ExerciseLog.objects.filter(user=self.pessoa, exercise=self.exercicio).update(
            weight_kg=Decimal("0")
        )
        dias = services.historico_do_exercicio(self.pessoa, self.exercicio)
        self.assertIsNone(dias[0]["volume"])
        html = self.client.get(
            reverse("workouts:exercicio", args=[self.exercicio.pk])
        ).content.decode()
        historico = html.split('class="data-list historico"', 1)[1].split("</dl>", 1)[0]
        self.assertNotIn("0,00", historico)
        self.assertIn("8", historico)

    def test_um_dia_por_data_e_as_series_em_ordem(self):
        ontem = self.hoje - timedelta(days=1)
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.exercicio, date=ontem,
            set_number=2, weight_kg=Decimal("55.00"), reps=10,
        )
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.exercicio, date=ontem,
            set_number=1, weight_kg=Decimal("50.00"), reps=12,
        )
        dias = services.historico_do_exercicio(self.pessoa, self.exercicio)
        self.assertEqual([d["data"] for d in dias], [self.hoje, ontem])
        self.assertEqual([s["numero"] for s in dias[1]["series"]], [1, 2])
