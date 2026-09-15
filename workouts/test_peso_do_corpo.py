# -*- coding: utf-8 -*-
"""Peso do corpo não pede anilha, e a prancha conta segundos.

`weight_kg` era `required` em todo exercício, e o servidor recusava vazio
("Carga inválida"): numa flexão, a pessoa tinha de digitar um número para um
peso que não levantou — o comentário do próprio template diz que registrar
peso que não se levantou é o que se evita. E a prancha, cujo `measure` é
segundos, aparecia como "30-45s reps" com o campo rotulado "Reps". Achados
da pesquisa de 13/09/2026.

Em peso do corpo o campo deixa de ser obrigatório e o vazio vira 0 — SÓ ali:
num supino, campo esquecido continua sendo erro, senão gravaria 0 kg em
silêncio. Em segundos o rótulo e o `aria-label` dizem "Segundos" e a faixa
deixa de concatenar "reps".
"""
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import Exercise, ExerciseLog, Measure, SessionExercise
from workouts.tests import create_user, dias_incluindo_hoje, sem_scripts


class PesoDoCorpoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="corpo@exemplo.com", weekdays=dias_incluindo_hoje(7))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        plano = services.get_active_routine(self.pessoa)
        self.sessao = next(s for s in plano.sessions.all() if s.weekday == self.hoje.weekday())
        # A sessão de hoje pode não ter flexão nem prancha: elas ENTRAM na
        # ficha de hoje como itens de teste, com a dose do catálogo.
        self.flexao = self._garantir("Flexão de braço", Measure.REPS, 10, 15)
        self.prancha = self._garantir("Prancha abdominal", Measure.SECONDS, 30, 45)
        # Ficha ajustada não é remontada: sem isto `sync_active_routine`
        # compara com o catálogo, vê o item a mais e refaz a semana.
        plano.customized_at = timezone.now()
        plano.save(update_fields=["customized_at"])
        self.supino = next(
            i for i in self.sessao.exercises.select_related("exercise")
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _garantir(self, nome, measure, rep_min, rep_max):
        exercicio = Exercise.objects.get(name=nome)
        item = self.sessao.exercises.filter(exercise=exercicio).first()
        if item is None:
            item = SessionExercise.objects.create(
                session=self.sessao, exercise=exercicio, order=99,
                sets=3, rep_min=rep_min, rep_max=rep_max, measure=measure, rest_seconds=60,
            )
        return item

    def _html(self, item):
        url = "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        return sem_scripts(self.client.get(url).content.decode())

    def _post(self, item, peso, op):
        return self.client.post(reverse("workouts:record_set"), {
            "exercise_id": item.exercise_id, "weight_kg": peso, "reps": "12",
            "op_id": op, "dia": self.hoje.isoformat(),
        })

    def test_flexao_sem_carga_grava_zero(self):
        self._post(self.flexao, "", "op-flexao")
        log = ExerciseLog.objects.get(user=self.pessoa, exercise=self.flexao.exercise)
        self.assertEqual(log.weight_kg, 0)
        self.assertEqual(log.reps, 12)

    def test_supino_sem_carga_continua_sendo_erro_e_nao_grava(self):
        """Campo esquecido num supino não pode virar 0 kg em silêncio."""
        resposta = self._post(self.supino, "", "op-supino")
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(ExerciseLog.objects.filter(user=self.pessoa, exercise=self.supino.exercise).exists())

    def test_o_campo_de_carga_da_flexao_nao_e_obrigatorio_e_o_do_supino_e(self):
        campo = lambda html: html.split('name="weight_kg"', 1)[0].rsplit("<input", 1)[1] + html.split('name="weight_kg"', 1)[1].split(">", 1)[0]
        self.assertNotIn("required", campo(self._html(self.flexao)))
        self.assertIn("peso do corpo", campo(self._html(self.flexao)))
        self.assertIn("required", campo(self._html(self.supino)))
        # Sem anilha não há ±2,5 kg para somar.
        self.assertNotIn("data-passo", self._html(self.flexao))
        self.assertIn("data-passo", self._html(self.supino))

    def test_a_prancha_fala_em_segundos(self):
        html = self._html(self.prancha)
        self.assertIn(">Segundos<", html)
        self.assertIn('aria-label="Segundos da série', html)
        faixa = html.split('class="series__faixa num"', 1)[1].split("</span>", 1)[0]
        self.assertNotIn("reps", faixa)
        self.assertIn("30-45s", faixa)

    def test_o_supino_continua_falando_em_reps(self):
        html = self._html(self.supino)
        self.assertIn(">Reps<", html)
        faixa = html.split('class="series__faixa num"', 1)[1].split("</span>", 1)[0]
        self.assertIn("reps", faixa)


class ATelaPerguntaAoExercicioENaoAoCampoTests(SimpleTestCase):
    """`bodyweight` não aparece na view nem nos templates da execução.

    "Tem anilha?" é `Exercise.sem_carga` — uma propriedade do exercício, o
    mesmo motivo pelo qual o motor a lê em vez de `equipment`
    (`test_o_motor_nao_le_equipamento`). Nove leituras do campo cru
    sobreviveram em `views.py`, `agora.html` e `exercicio.html` (TREINO
    ONDA-0, 14/09/2026): cada uma é um lugar a corrigir quando a resposta
    mudar, e a propriedade existe para haver UM.

    Controle positivo: sabotar `sem_carga` para `False` derruba
    `test_flexao_sem_carga_grava_zero` — a tela lê a propriedade de verdade.
    """

    def test_nenhuma_tela_da_execucao_le_o_campo_cru(self):
        base = Path(settings.BASE_DIR)
        arquivos = [base / "workouts" / "views.py"] + sorted(
            (base / "templates" / "workouts").glob("*.html")
        )
        com_leitura = [
            a.relative_to(base).as_posix()
            for a in arquivos
            if "bodyweight" in a.read_text(encoding="utf-8")
        ]
        self.assertEqual(com_leitura, [])
