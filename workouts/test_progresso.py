"""O treino na tela de progresso: o que dá para afirmar e o que não dá."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from workouts import progresso
from workouts.models import Exercise, ExerciseLog

User = get_user_model()


class DiasTreinadosTests(TestCase):
    """Dias com série anotada, por semana — e nunca séries."""

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="treino@exemplo.com", password="senha-bem-forte-123"
        )
        self.supino = Exercise.objects.create(
            name="Supino reto com barra", muscle_group="peito",
        )
        # Uma quarta-feira, para a semana não depender do dia em que a suíte
        # roda: com "hoje" variável, o teste passaria ou falharia conforme o
        # calendário.
        self.hoje = date(2026, 9, 2)

    def _serie(self, dia, numero=1, carga="60"):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.supino, date=dia,
            set_number=numero, weight_kg=Decimal(carga), reps=10,
        )

    def test_conta_dias_e_nao_series(self):
        """Quem faz cinco exercícios num dia registra dezenas de linhas.
        Contar linhas faria um dia parecer uma semana movimentada."""
        for numero in range(1, 6):
            self._serie(self.hoje, numero=numero)

        semanas = progresso.dias_treinados(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 1)

    def test_dias_diferentes_contam_separado(self):
        self._serie(self.hoje)
        self._serie(self.hoje - timedelta(days=1), numero=2)

        semanas = progresso.dias_treinados(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 2)

    def test_a_semana_comeca_na_segunda(self):
        """02/09/2026 é quarta. O domingo anterior é da semana passada, e
        colocá-lo na semana atual inflaria a contagem de quem treina no fim de
        semana."""
        self._serie(self.hoje)
        self._serie(self.hoje - timedelta(days=3), numero=2)  # domingo

        semanas = progresso.dias_treinados(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 1)
        self.assertEqual(semanas[-2]["dias"], 1)

    def test_semana_sem_treino_aparece_zerada(self):
        """Buraco na série é informação: pular a semana faria oito semanas de
        treino irregular parecerem oito semanas seguidas."""
        self._serie(self.hoje)

        semanas = progresso.dias_treinados(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(semanas), progresso.SEMANAS)
        self.assertEqual([s["dias"] for s in semanas[:-1]], [0] * 7)


class ProgressaoDeCargaTests(TestCase):
    """Antes e agora, por exercício."""

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="carga@exemplo.com", password="senha-bem-forte-123"
        )
        self.supino = Exercise.objects.create(
            name="Supino reto com barra", muscle_group="peito",
        )
        self.remada = Exercise.objects.create(
            name="Remada curvada", muscle_group="costas",
        )
        self.hoje = date(2026, 9, 2)

    def _serie(self, exercicio, dia, carga, numero=1):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=exercicio, date=dia,
            set_number=numero, weight_kg=carga, reps=10,
        )

    def test_compara_o_primeiro_registro_com_o_ultimo(self):
        self._serie(self.supino, self.hoje - timedelta(days=30), Decimal("60"))
        self._serie(self.supino, self.hoje, Decimal("70"))

        linhas = progresso.progressao_de_carga(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["primeiro"], Decimal("60"))
        self.assertEqual(linhas[0]["ultimo"], Decimal("70"))
        self.assertEqual(linhas[0]["delta"], Decimal("10"))

    def test_nao_e_recorde_contra_recorde(self):
        """Máximo de tudo contra máximo de tudo devolveria "seu recorde é seu
        recorde" — verdade, e não evolução. Aqui a carga CAIU, e a tela precisa
        poder dizer isso."""
        self._serie(self.supino, self.hoje - timedelta(days=30), Decimal("80"))
        self._serie(self.supino, self.hoje - timedelta(days=15), Decimal("90"))
        self._serie(self.supino, self.hoje, Decimal("70"))

        linhas = progresso.progressao_de_carga(self.pessoa, hoje=self.hoje)

        self.assertEqual(linhas[0]["ultimo"], Decimal("70"))
        self.assertEqual(linhas[0]["delta"], Decimal("-10"))

    def test_um_registro_so_fica_de_fora(self):
        """Com um ponto não há reta. "60 → 60" para quem treinou uma vez
        sugere estagnação onde houve uma sessão."""
        self._serie(self.supino, self.hoje, Decimal("60"))

        self.assertEqual(progresso.progressao_de_carga(self.pessoa, hoje=self.hoje), [])

    def test_exercicio_sem_carga_nao_inventa_numero(self):
        """Peso corporal grava ZERO — a coluna é `NOT NULL` com mínimo 0.

        Sem guarda, flexão e barra apareceriam como "0 kg → 0 kg", que lê como
        estagnação e é ausência de carga. Elas contam como dia treinado."""
        self._serie(self.supino, self.hoje - timedelta(days=7), Decimal("0"))
        self._serie(self.supino, self.hoje, Decimal("0"))

        self.assertEqual(progresso.progressao_de_carga(self.pessoa, hoje=self.hoje), [])
        self.assertEqual(
            progresso.dias_treinados(self.pessoa, hoje=self.hoje)[-1]["dias"], 1
        )

    def test_pega_a_maior_carga_do_dia(self):
        """A pessoa aquece com 40 e trabalha com 70. O que mede progresso é a
        série de trabalho."""
        self._serie(self.supino, self.hoje - timedelta(days=14), Decimal("60"))
        self._serie(self.supino, self.hoje, Decimal("40"), numero=1)
        self._serie(self.supino, self.hoje, Decimal("70"), numero=2)

        linhas = progresso.progressao_de_carga(self.pessoa, hoje=self.hoje)

        self.assertEqual(linhas[0]["ultimo"], Decimal("70"))

    def test_cada_exercicio_tem_a_propria_linha(self):
        for exercicio, antes, agora in (
            (self.supino, "60", "70"), (self.remada, "50", "55")
        ):
            self._serie(exercicio, self.hoje - timedelta(days=20), Decimal(antes))
            self._serie(exercicio, self.hoje, Decimal(agora))

        linhas = progresso.progressao_de_carga(self.pessoa, hoje=self.hoje)

        self.assertEqual({l["nome"] for l in linhas}, {"Supino reto com barra", "Remada curvada"})

    def test_o_custo_nao_cresce_com_o_numero_de_series(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for n in range(4):
            self._serie(self.supino, self.hoje - timedelta(days=n * 7), Decimal("60"), numero=n + 1)
        with CaptureQueriesContext(connection) as poucas:
            progresso.progressao_de_carga(self.pessoa, hoje=self.hoje)

        for n in range(4, 40):
            self._serie(
                self.supino, self.hoje - timedelta(days=n % 50),
                Decimal("60"), numero=n + 1,
            )
        with CaptureQueriesContext(connection) as muitas:
            progresso.progressao_de_carga(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(poucas.captured_queries), len(muitas.captured_queries))
