"""A regra de "treino iniciado" da migração 0018, medida caso a caso.

POR QUE ESTE ARQUIVO EXISTE. A primeira versão da migração decidia por PLANO —
bastava uma série em qualquer exercício para a ficha inteira virar intocável — e
usava `date__gte=plano.created_at.date()` como janela, o que conta um registro
feito de manhã para um plano criado à tarde do mesmo dia.

A regra correta é comportamental e por SESSÃO: existe `ExerciseLog` de algum
exercício DAQUELA sessão, gravado depois de o plano nascer? Se sim, a
prescrição fica como está. `created_at` do plano não prova execução — ele só
delimita a janela, para um registro do plano ANTERIOR não congelar uma ficha
que ninguém começou.

A função da migração é chamada DIRETAMENTE, com o registro real de modelos.
Ela só usa `get_model`, filtros, `update` e `delete`, que funcionam igual — e
testar a função é a única forma de exercitar os casos, já que uma migração roda
uma vez só.
"""
import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as registro_de_modelos
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from workouts.models import (
    Exercise,
    ExerciseLog,
    SessionExercise,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplateItem,
)

APOSENTADO = "Remada curvada com barra"
SUBSTITUTO = "Remada baixa na polia"

migracao = importlib.import_module(
    "workouts.migrations.0018_aposenta_remada_curvada_com_barra"
)

User = get_user_model()


class ARegraDeTreinoIniciadoTests(TestCase):
    """Cada caso da lista, montado à mão e medido."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="aposentadoria@exemplo.com", password="x8Kd2Lm9Qp4z"
        )
        self.velho = Exercise.objects.get(name=APOSENTADO)
        self.novo = Exercise.objects.get(name=SUBSTITUTO)
        # O catálogo já nasce com o exercício aposentado (o seed lê
        # `active: false`). Para exercitar a migração é preciso reconstruir o
        # estado ANTERIOR a ela: exercício ativo e presente em fichas.
        Exercise.objects.filter(pk=self.velho.pk).update(is_active=True)

    # ------------------------------------------------------------ auxiliares
    def _plano(self, criado_ha_dias=0):
        plano = TrainingPlan.objects.create(
            user=self.user, is_active=True, split="abc", days_per_week=3
        )
        if criado_ha_dias:
            nascimento = timezone.now() - timedelta(days=criado_ha_dias)
            TrainingPlan.objects.filter(pk=plano.pk).update(created_at=nascimento)
            plano.refresh_from_db()
        return plano

    def _sessao(self, plano, label="B", weekday=1, com_aposentado=True, extras=()):
        sessao = TrainingSession.objects.create(
            plan=plano, weekday=weekday, label=label, name="Costas", order=weekday
        )
        ordem = 0
        if com_aposentado:
            SessionExercise.objects.create(
                session=sessao, exercise=self.velho, sets=4,
                rep_min=8, rep_max=12, rest_seconds=80, order=ordem,
            )
            ordem += 1
        for exercicio in extras:
            SessionExercise.objects.create(
                session=sessao, exercise=exercicio, sets=3,
                rep_min=10, rep_max=12, rest_seconds=80, order=ordem,
            )
            ordem += 1
        return sessao

    def _registrar(self, exercicio, plano=None, quando=None, numero=1):
        log = ExerciseLog.objects.create(
            user=self.user, exercise=exercicio, date=timezone.localdate(),
            set_number=numero, weight_kg=Decimal("60"), reps=10,
        )
        if quando is not None:
            ExerciseLog.objects.filter(pk=log.pk).update(created_at=quando)
        return log

    def _rodar(self):
        migracao.aposentar(registro_de_modelos, None)

    def _exercicios(self, sessao):
        return list(
            SessionExercise.objects.filter(session=sessao)
            .select_related("exercise").order_by("order")
        )

    # ------------------------------------------------ 1. nunca iniciado
    def test_plano_criado_e_nunca_iniciado_recebe_a_substituicao(self):
        plano = self._plano()
        sessao = self._sessao(plano)

        self._rodar()

        nomes = [i.exercise.name for i in self._exercicios(sessao)]
        self.assertNotIn(APOSENTADO, nomes)
        self.assertIn(SUBSTITUTO, nomes)

    def test_a_substituicao_preserva_ordem_series_faixa_e_descanso(self):
        """"Não embaralhe" — a linha é a mesma, só a identidade muda."""
        plano = self._plano()
        sessao = self._sessao(plano)

        self._rodar()

        linha = self._exercicios(sessao)[0]
        self.assertEqual(linha.exercise.name, SUBSTITUTO)
        self.assertEqual((linha.sets, linha.rep_min, linha.rep_max), (4, 8, 12))
        self.assertEqual((linha.rest_seconds, linha.order), (80, 0))

    def test_o_video_que_a_pessoa_ve_e_o_do_exercicio_novo(self):
        """O vídeo vem do exercício, não da linha — então trocar a identidade
        troca o vídeo junto, e nunca deixa o clipe do aposentado apontando para
        o substituto."""
        plano = self._plano()
        sessao = self._sessao(plano)

        self._rodar()

        linha = self._exercicios(sessao)[0]
        self.assertEqual(
            linha.exercise.video_url,
            Exercise.objects.get(name=SUBSTITUTO).video_url,
        )
        self.assertNotEqual(
            linha.exercise.video_url,
            Exercise.objects.get(name=APOSENTADO).video_url,
        )

    # ------------------------------------- 2. criado há dias, nunca iniciado
    def test_plano_antigo_e_nunca_iniciado_TAMBEM_recebe_a_substituicao(self):
        """Tempo passado não é execução. Um plano de duas semanas atrás em que
        ninguém treinou continua sendo uma ficha por começar."""
        plano = self._plano(criado_ha_dias=14)
        sessao = self._sessao(plano)

        self._rodar()

        self.assertEqual(
            [i.exercise.name for i in self._exercicios(sessao)], [SUBSTITUTO]
        )

    # ------------------------------------------ 3. criado hoje e já iniciado
    def test_sessao_com_serie_registrada_e_PRESERVADA(self):
        plano = self._plano()
        sessao = self._sessao(plano)
        self._registrar(self.velho)

        self._rodar()

        self.assertEqual(
            [i.exercise.name for i in self._exercicios(sessao)], [APOSENTADO]
        )

    # ------------------------------------------- 4. execução em OUTRO dia
    def test_dia_nao_iniciado_e_substituido_mesmo_com_outro_dia_iniciado(self):
        """A granularidade é da SESSÃO.

        Quem treinou pernas na quarta e nunca começou o dia B recebe a
        substituição no dia B. A primeira versão desta regra olhava o plano
        inteiro e congelava a ficha toda por causa de um dia.
        """
        plano = self._plano()
        agachamento = Exercise.objects.get(name="Agachamento livre")
        pernas = TrainingSession.objects.create(
            plan=plano, weekday=2, label="C", name="Pernas", order=2
        )
        SessionExercise.objects.create(
            session=pernas, exercise=agachamento, sets=4,
            rep_min=6, rep_max=10, rest_seconds=80, order=0,
        )
        costas = self._sessao(plano)
        self._registrar(agachamento)

        self._rodar()

        self.assertEqual(
            [i.exercise.name for i in self._exercicios(costas)], [SUBSTITUTO],
            "o dia não iniciado ficou intocável por causa de outro dia",
        )
        self.assertEqual(
            [i.exercise.name for i in self._exercicios(pernas)],
            ["Agachamento livre"],
        )

    # ---------------------------------- 5. mesmo dia, outro exercício feito
    def test_dia_iniciado_por_OUTRO_exercicio_dele_e_preservado(self):
        """Começar o dia B pela rosca e ainda não ter chegado na remada é um
        treino EM ANDAMENTO. Trocar o exercício ali é reescrever o que a pessoa
        está fazendo agora."""
        plano = self._plano()
        rosca = Exercise.objects.get(name="Rosca direta com barra")
        sessao = self._sessao(plano, extras=(rosca,))
        self._registrar(rosca)

        self._rodar()

        self.assertIn(
            APOSENTADO, [i.exercise.name for i in self._exercicios(sessao)]
        )

    # -------------------------------------------------- 6. treino concluído
    def test_treino_concluido_e_preservado_com_o_historico_intacto(self):
        plano = self._plano()
        sessao = self._sessao(plano)
        for numero in range(1, 5):
            self._registrar(self.velho, numero=numero)

        self._rodar()

        self.assertEqual(
            [i.exercise.name for i in self._exercicios(sessao)], [APOSENTADO]
        )
        self.assertEqual(
            ExerciseLog.objects.filter(user=self.user, exercise=self.velho).count(), 4
        )

    # ----------------------------------------------------- 7. histórico antigo
    def test_registro_ANTERIOR_ao_plano_nao_conta_como_inicio(self):
        """A janela existe para isto.

        Um registro do plano PASSADO — mesmo exercício, semanas atrás — não pode
        marcar como iniciada uma ficha que acabou de nascer. Sem a janela, quem
        já treinou remada alguma vez na vida jamais receberia a substituição.
        """
        plano = self._plano()
        self._registrar(self.velho, quando=plano.created_at - timedelta(days=30))
        sessao = self._sessao(plano)

        self._rodar()

        self.assertEqual(
            [i.exercise.name for i in self._exercicios(sessao)], [SUBSTITUTO]
        )

    # ------------------------------------------------- 8. rodar duas vezes
    def test_rodar_a_migracao_duas_vezes_nao_muda_mais_nada(self):
        plano = self._plano()
        sessao = self._sessao(plano)

        self._rodar()
        depois_da_primeira = [
            (i.exercise.name, i.sets, i.order) for i in self._exercicios(sessao)
        ]
        self._rodar()

        self.assertEqual(
            [(i.exercise.name, i.sets, i.order) for i in self._exercicios(sessao)],
            depois_da_primeira,
        )
        self.assertFalse(Exercise.objects.get(name=APOSENTADO).is_active)

    # --------------------------------------------- 9. seed depois da migração
    def test_o_seed_depois_da_migracao_nao_ressuscita_o_aposentado(self):
        """O `seed_workouts` roda em TODO deploy (`scripts/build.sh`).

        Enquanto a aposentadoria vivia só na migração, o seed seguinte
        reativava a linha — `update_or_create` com `is_active` vindo do JSON. O
        catálogo passou a declarar `active: false`, e é isso que este teste
        guarda.
        """
        self._rodar()

        call_command("seed_workouts", verbosity=0)

        self.assertFalse(Exercise.objects.get(name=APOSENTADO).is_active)
        self.assertFalse(
            WorkoutTemplateItem.objects.filter(exercise__name=APOSENTADO).exists(),
            "o seed devolveu o aposentado para os modelos",
        )

    # ------------------------------------------- 10. continua existindo
    def test_o_exercicio_NAO_e_apagado_e_o_historico_sobrevive(self):
        """`ExerciseLog.exercise` é CASCADE. Apagar o exercício levaria o
        histórico junto, em silêncio — por isso a aposentadoria é
        `is_active=False`, e por isso este teste mede as duas coisas."""
        plano = self._plano()
        self._sessao(plano)
        log = self._registrar(self.velho)

        self._rodar()

        velho = Exercise.objects.filter(name=APOSENTADO).first()
        self.assertIsNotNone(velho, "o exercício foi APAGADO")
        self.assertFalse(velho.is_active)
        self.assertTrue(velho.video_url)
        self.assertTrue(
            ExerciseLog.objects.filter(pk=log.pk).exists(),
            "o histórico sumiu junto com a aposentadoria",
        )

    def test_o_historico_continua_apontando_para_o_exercicio_ORIGINAL(self):
        """"Não crie uma nova associação com o substituto." O registro é do que
        a pessoa fez, e ela fez remada curvada."""
        plano = self._plano()
        self._sessao(plano)
        log = self._registrar(self.velho)

        self._rodar()

        de_volta = ExerciseLog.objects.select_related("exercise").get(pk=log.pk)
        self.assertEqual(de_volta.exercise.name, APOSENTADO)
        self.assertEqual(de_volta.weight_kg, Decimal("60"))

    # ------------------------------------------------------- controle geral
    def test_nenhum_OUTRO_exercicio_e_tocado(self):
        """Controle negativo: a substituição é por identidade, e uma regra que
        pegasse pela posição derrubaria o vizinho."""
        plano = self._plano()
        rosca = Exercise.objects.get(name="Rosca direta com barra")
        sessao = self._sessao(plano, extras=(rosca,))

        self._rodar()

        nomes = [i.exercise.name for i in self._exercicios(sessao)]
        self.assertIn("Rosca direta com barra", nomes)
        self.assertEqual(len(nomes), 2)

    def test_quando_o_substituto_JA_esta_na_sessao_ele_herda_a_dose(self):
        """Duplicar violaria `unique_exercise_per_session`. A linha aposentada
        sai e o substituto sobe para a dose dela — sem isso o dia perderia
        quatro séries de puxada horizontal."""
        plano = self._plano()
        sessao = self._sessao(plano, extras=(self.novo,))

        self._rodar()

        linhas = self._exercicios(sessao)
        self.assertEqual([i.exercise.name for i in linhas], [SUBSTITUTO])
        self.assertEqual(linhas[0].sets, 4, "a dose de principal se perdeu")
