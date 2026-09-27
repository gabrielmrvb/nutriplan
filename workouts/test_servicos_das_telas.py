"""As funções de `workouts/telas.py`, chamadas DIRETO — sem cliente HTTP.

As quatro telas de treino (ficha, leitura do exercício, carga, série) liam o
banco de dentro da view. A leitura e a escrita saíram para `telas.py`, e este
arquivo prende o que não podia mudar na mudança: a escrita da carga e da série
continua idempotente — a fila offline reenvia quando a resposta se perde, e
uma segunda linha para o mesmo toque é volume que a pessoa não levantou — e a
ficha continua sendo a da própria pessoa.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from workouts import services, telas
from workouts.models import Exercise, ExerciseLog, SessionExercise
from workouts.tests import create_user


class ACargaEASerieNaoDuplicamTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="telas@exemplo.com")
        self.exercicio = Exercise.objects.create(
            name="Supino das telas", muscle_group="chest", padrao="pressao_de_peito"
        )
        self.hoje = timezone.localdate()

    def _series(self):
        return list(
            ExerciseLog.objects.filter(user=self.pessoa, exercise=self.exercicio)
            .order_by("set_number")
            .values_list("set_number", "weight_kg")
        )

    def test_a_mesma_carga_anotada_duas_vezes_fica_uma_linha_com_o_peso_novo(self):
        """Anotar de novo a MESMA série corrige, não duplica.

        É o `update_or_create` na chave pessoa · exercício · dia · série que o
        CLAUDE.md chama de "já seguro": a fila reenvia o mesmo corpo quando a
        resposta se perde, e trocá-lo por `create` faria o reenvio virar uma
        segunda série — ou um 500 no `UniqueConstraint` que a fila repete para
        sempre."""
        telas.anotar_carga(self.pessoa, self.exercicio, Decimal("40"), 2, reps=8)
        telas.anotar_carga(self.pessoa, self.exercicio, Decimal("42.5"), 2, reps=8)

        self.assertEqual(self._series(), [(2, Decimal("42.5"))])

    def test_series_feitas_regravam_de_um_a_n_e_apagam_o_que_passa(self):
        """"Fiz 4" repetido é o mesmo estado; baixar para 3 apaga a quarta —
        senão o volume do dia mentiria para sempre."""
        for _ in range(2):
            telas.anotar_carga(self.pessoa, self.exercicio, Decimal("40"), 1, feitas=4)
        self.assertEqual([n for n, _ in self._series()], [1, 2, 3, 4])

        telas.anotar_carga(self.pessoa, self.exercicio, Decimal("40"), 1, feitas=3)
        self.assertEqual([n for n, _ in self._series()], [1, 2, 3])

    def test_a_serie_reenviada_com_o_mesmo_op_id_fica_uma_linha(self):
        """O reenvio da fila (mesmo `op_id`) é reconhecido e não é dia novo.

        Controle positivo no fim: um toque NOVO (outro `op_id`) grava a
        segunda série — senão o teste passaria com uma função que nunca
        grava nada."""
        primeiro = telas.concluir_serie(self.pessoa, self.exercicio, "40", self.hoje, reps=10, op_id="toque-1")
        reenvio = telas.concluir_serie(self.pessoa, self.exercicio, "40", self.hoje, reps=10, op_id="toque-1")

        self.assertEqual(primeiro, (True, True))
        self.assertEqual(reenvio, (False, False))
        self.assertEqual(len(self._series()), 1)

        outro = telas.concluir_serie(self.pessoa, self.exercicio, "40", self.hoje, reps=10, op_id="toque-2")
        self.assertEqual(outro, (True, False))
        self.assertEqual([n for n, _ in self._series()], [1, 2])


class AFichaLidaDiretoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="ficha-direta@exemplo.com")
        services.sync_active_routine(self.pessoa)
        self.plano = services.get_active_routine(self.pessoa)
        self.sessao = self.plano.sessions.first()

    def test_a_ficha_devolve_a_sessao_com_os_itens_e_as_linhas_do_plano(self):
        """O que a view desenhava: a sessão pedida com os itens dela, e as
        linhas do plano de onde saem letra, opção e nomeação (A1/A2)."""
        sessao, linhas, historico = telas.ficha_da_pessoa(self.pessoa, self.sessao.pk)

        self.assertEqual(sessao.pk, self.sessao.pk)
        self.assertEqual(
            [i.pk for i in sessao.exercises.all()],
            list(SessionExercise.objects.filter(session=self.sessao).values_list("pk", flat=True)),
        )
        self.assertEqual([s.pk for s in linhas], [s.pk for s in self.plano.sessions.all()])
        self.assertFalse(historico)

    def test_a_ficha_de_outra_pessoa_nao_abre(self):
        """IDOR: o id é da URL, e um id alheio não pode abrir a ficha dos outros."""
        estranha = create_user(email="estranha@exemplo.com")
        with self.assertRaises(Http404):
            telas.ficha_da_pessoa(estranha, self.sessao.pk)

    def test_a_ficha_de_programa_anterior_abre_como_historico_com_as_series_de_hoje(self):
        """Remontar o programa não pode transformar a ficha em uso em 404 —
        ela abre como histórico e conta as séries de hoje (e só as de hoje)."""
        self.plano.is_active = False
        self.plano.save(update_fields=["is_active"])
        item = self.sessao.exercises.first()
        hoje = timezone.localdate()
        for dia, serie in ((hoje, 1), (hoje, 2), (hoje - timedelta(days=1), 1)):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise_id=item.exercise_id, date=dia,
                set_number=serie, weight_kg=Decimal("30"),
            )

        sessao, _, historico = telas.ficha_da_pessoa(self.pessoa, self.sessao.pk)

        self.assertTrue(historico)
        ids = [i.exercise_id for i in sessao.exercises.all()]
        self.assertEqual(telas.series_anotadas_hoje(self.pessoa, ids), 2)
