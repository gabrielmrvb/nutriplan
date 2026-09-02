"""Progresso: a meta da época, e o que a tela pode afirmar sobre evolução."""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    Goal,
    Profile,
    Sex,
)
from plans import tracking
from plans.models import MealLog, MealStatus, NutritionPlan

User = get_user_model()


class MetaDaEpocaTests(TestCase):
    """A barra do dia a dia compara com a meta que valia NAQUELE dia.

    O defeito que isto corrige: a tela comparava todo dia com a meta atual.
    Como a meta muda justamente quando o peso muda, o dia da recalibragem era
    o dia em que a comparação passava a mentir para trás — quem cortou 200
    kcal na terça via a segunda inteira parecendo excesso.

    O dado sempre esteve no banco: `NutritionPlan` é retrato e os antigos
    ficam. Faltava ir buscar.
    """

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="progresso@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.pessoa,
            sex=Sex.MALE,
            birth_date=date(1995, 4, 12),
            height_cm=178,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        self.hoje = timezone.localdate()

    def _plano(self, alvo, dias_atras, ativo=False):
        plano = NutritionPlan.objects.create(
            user=self.pessoa,
            weight_kg=Decimal("80"), height_cm=178, age_years=30,
            sex=Sex.MALE, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            bmr_kcal=1700, tdee_kcal=2300, target_kcal=alvo,
            protein_g=160, carb_g=300, fat_g=70,
            is_active=ativo,
        )
        # `auto_now_add` ignora o valor passado; a data se ajusta depois.
        NutritionPlan.objects.filter(pk=plano.pk).update(
            created_at=timezone.now() - timedelta(days=dias_atras)
        )
        return plano

    def test_cada_dia_usa_a_meta_que_valia_nele(self):
        self._plano(2600, dias_atras=20)
        self._plano(2400, dias_atras=5, ativo=True)

        dias = [self.hoje - timedelta(days=n) for n in (10, 1)]
        metas = tracking.metas_por_dia(self.pessoa, dias)

        self.assertEqual(metas[self.hoje - timedelta(days=10)], 2600)
        self.assertEqual(metas[self.hoje - timedelta(days=1)], 2400)

    def test_o_dia_da_troca_ja_usa_a_meta_nova(self):
        """O plano vale para o dia em que nasceu: quem recalibrou de manhã
        passou o dia inteiro com a meta nova."""
        self._plano(2600, dias_atras=20)
        self._plano(2400, dias_atras=3, ativo=True)

        dia_da_troca = self.hoje - timedelta(days=3)
        metas = tracking.metas_por_dia(self.pessoa, [dia_da_troca])

        self.assertEqual(metas[dia_da_troca], 2400)

    def test_dia_anterior_ao_primeiro_plano_usa_o_primeiro(self):
        """Comparar o que a pessoa comeu antes de existir plano com uma meta
        que ainda não existia seria inventar a régua. Usar a primeira é a
        aproximação menos errada, e não afeta o caso comum: quase ninguém tem
        registro anterior ao próprio plano."""
        self._plano(2600, dias_atras=5, ativo=True)

        antigo = self.hoje - timedelta(days=30)
        metas = tracking.metas_por_dia(self.pessoa, [antigo])

        self.assertEqual(metas[antigo], 2600)

    def test_sem_plano_nenhum_nao_quebra(self):
        self.assertEqual(tracking.metas_por_dia(self.pessoa, [self.hoje]), {})

    def test_a_tela_usa_a_meta_da_epoca_na_barra(self):
        """Prova de ponta a ponta: o mesmo consumo em dois dias com metas
        diferentes tem que render barras diferentes. Comparado com a meta de
        hoje, os dois dariam a mesma."""
        self._plano(2000, dias_atras=20)
        self._plano(4000, dias_atras=2, ativo=True)
        for atras in (10, 1):
            MealLog.objects.create(
                user=self.pessoa,
                date=self.hoje - timedelta(days=atras),
                status=MealStatus.DONE,
                kcal=1000,
                slot_name="almoço",
            )
        self.client.force_login(self.pessoa)

        linhas = self.client.get("/historico/").context["rows"]

        por_dia = {linha["date"]: linha for linha in linhas}
        antigo = por_dia[self.hoje - timedelta(days=10)]
        recente = por_dia[self.hoje - timedelta(days=1)]
        self.assertEqual(antigo["meta"], 2000)
        self.assertEqual(recente["meta"], 4000)
        self.assertEqual(antigo["pct"], 50)
        self.assertEqual(recente["pct"], 25)

    def test_a_meta_da_epoca_nao_custa_uma_consulta_por_dia(self):
        """Trinta dias na tela não podem virar trinta consultas."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._plano(2600, dias_atras=20)
        self._plano(2400, dias_atras=5, ativo=True)

        poucos = [self.hoje - timedelta(days=n) for n in range(3)]
        with CaptureQueriesContext(connection) as a:
            tracking.metas_por_dia(self.pessoa, poucos)

        muitos = [self.hoje - timedelta(days=n) for n in range(30)]
        with CaptureQueriesContext(connection) as b:
            tracking.metas_por_dia(self.pessoa, muitos)

        self.assertEqual(len(a.captured_queries), len(b.captured_queries))


class AguaPorSemanaTests(TestCase):
    """Média sobre os dias com registro, e o número de dias junto."""

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="agua@exemplo.com", password="senha-bem-forte-123"
        )
        self.hoje = date(2026, 9, 2)  # quarta

    def _agua(self, dia, ml):
        from plans.models import HydrationLog

        return HydrationLog.objects.create(user=self.pessoa, date=dia, ml=ml)

    def test_a_media_e_sobre_os_dias_com_registro(self):
        """Dividir por sete transformaria "3 litros em dois dias" em "média de
        850 ml", que descreve um comportamento que não aconteceu. Quem esqueceu
        de anotar não bebeu zero — o app só não sabe."""
        self._agua(self.hoje, 3000)
        self._agua(self.hoje - timedelta(days=1), 3000)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 2)
        self.assertEqual(semanas[-1]["media_ml"], 3000)

    def test_o_numero_de_dias_acompanha_a_media(self):
        """A média sozinha esconde quantos dias a sustentam."""
        self._agua(self.hoje, 4000)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 1)
        self.assertEqual(semanas[-1]["media_ml"], 4000)

    def test_linha_zerada_nao_conta_como_dia(self):
        """A linha nasce por `get_or_create` quando a tela do dia abre.
        Existir não é ter bebido."""
        self._agua(self.hoje, 0)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 0)
        self.assertEqual(semanas[-1]["media_ml"], 0)

    def test_semana_sem_registro_aparece_zerada(self):
        self._agua(self.hoje, 2000)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(semanas), 8)
        self.assertEqual([s["dias"] for s in semanas[:-1]], [0] * 7)

    def test_o_custo_nao_cresce_com_os_registros(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for n in range(5):
            self._agua(self.hoje - timedelta(days=n), 2000)
        with CaptureQueriesContext(connection) as poucos:
            tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        for n in range(5, 50):
            self._agua(self.hoje - timedelta(days=n), 2000)
        with CaptureQueriesContext(connection) as muitos:
            tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(poucos.captured_queries), len(muitos.captured_queries))


class TelaDeProgressoTests(TestCase):
    """A tela mostra o treino, e diz o que cada número significa."""

    def setUp(self):
        from workouts.models import Exercise, ExerciseLog

        self.pessoa = User.objects.create_user(
            email="tela@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.pessoa, sex=Sex.MALE, birth_date=date(1995, 4, 12),
            height_cm=178, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            wake_time=time(7, 0), sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        self.hoje = timezone.localdate()
        self.supino = Exercise.objects.create(
            name="Supino reto com barra", muscle_group="peito"
        )
        for atras, carga in ((14, "60"), (0, "70")):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.supino,
                date=self.hoje - timedelta(days=atras),
                set_number=1, weight_kg=Decimal(carga), reps=10,
            )
        # Uma refeição marcada: sem ela `totals.days` é zero e a tela mostra o
        # estado vazio inteiro, sem o cartão do dia a dia. O teste da régua
        # mediria a ausência do cartão em vez do texto dele.
        MealLog.objects.create(
            user=self.pessoa, date=self.hoje, status=MealStatus.DONE,
            kcal=800, slot_name="almoço",
        )
        self.client.force_login(self.pessoa)

    def _html(self):
        return self.client.get("/historico/").content.decode()

    def test_o_treino_aparece_na_tela(self):
        """O buraco que a V2 fecha: cada série estava no banco e nenhuma
        aparecia numa tela chamada Métricas."""
        html = self._html()

        self.assertIn("Supino reto com barra", html)
        self.assertIn("60", html)
        self.assertIn("70", html)

    def test_a_tela_nao_chama_frequencia_de_aderencia(self):
        """`TrainingDay` é o que a pessoa DECLAROU; `ExerciseLog` é o que ela
        fez. Uma razão entre os dois fingiria medir compromisso."""
        html = self._html().lower()

        pedaco = html[html.index("treino") : html.index("treino") + 3000]
        for palavra in ("aderência ao treino", "% dos treinos", "compromisso"):
            with self.subTest(palavra=palavra):
                self.assertNotIn(palavra, pedaco)

    def test_a_dica_explica_a_regua_de_cada_dia(self):
        """A barra passou a usar a meta da época. Se a tela continuasse dizendo
        "sua meta atual", o texto contradiria o número."""
        html = self._html()

        self.assertIn("que valia NAQUELE dia", html)
        self.assertNotIn("compara o dia com a sua meta atual", html)

    def test_o_custo_da_tela_nao_cresce_com_os_registros(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from workouts.models import ExerciseLog

        self.client.get("/historico/")
        with CaptureQueriesContext(connection) as poucos:
            self.client.get("/historico/")

        for n in range(2, 40):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.supino,
                date=self.hoje - timedelta(days=n % 40),
                set_number=n, weight_kg=Decimal("65"), reps=10,
            )
        with CaptureQueriesContext(connection) as muitos:
            self.client.get("/historico/")

        self.assertEqual(len(poucos.captured_queries), len(muitos.captured_queries))

    def test_sem_treino_nenhum_a_tela_convida_em_vez_de_cobrar(self):
        from workouts.models import ExerciseLog

        ExerciseLog.objects.filter(user=self.pessoa).delete()

        html = self._html()

        self.assertIn("Nenhuma série anotada ainda", html)


class MesmaGramaticaTests(TestCase):
    """Treino e água respondem a mesma pergunta e são lidos do mesmo jeito.

    Eu tinha desenhado uma como barras e a outra como lista, na MESMA tela.
    Duas soluções para o mesmo problema é dívida de UX nascendo: quem lê passa
    a decodificar dois formatos para comparar duas séries do próprio hábito.

    Este teste é sobre CONSISTÊNCIA e não sobre estilo — ele não afirma como a
    série deve parecer, afirma que as duas parecem a mesma coisa.
    """

    def setUp(self):
        from plans.models import HydrationLog
        from workouts.models import Exercise, ExerciseLog

        self.pessoa = User.objects.create_user(
            email="gramatica@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.pessoa, sex=Sex.MALE, birth_date=date(1995, 4, 12),
            height_cm=178, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            wake_time=time(7, 0), sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        hoje = timezone.localdate()
        exercicio = Exercise.objects.create(name="Supino", muscle_group="peito")
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=exercicio, date=hoje,
            set_number=1, weight_kg=Decimal("60"), reps=10,
        )
        HydrationLog.objects.create(user=self.pessoa, date=hoje, ml=2500)
        MealLog.objects.create(
            user=self.pessoa, date=hoje, status=MealStatus.DONE,
            kcal=700, slot_name="almoço",
        )
        self.client.force_login(self.pessoa)

    def test_as_duas_series_usam_a_mesma_estrutura(self):
        html = self.client.get("/historico/").content.decode()

        # Duas listas `.semanas`, uma para cada série.
        self.assertEqual(html.count('class="semanas"'), 2)
        self.assertIn("Dias com treino registrado por semana", html)
        self.assertIn("Dias com água registrada por semana", html)

    def test_as_duas_tem_oito_semanas(self):
        """Buraco na série é informação nas duas: uma mostrando oito semanas e
        a outra só as preenchidas seriam duas réguas diferentes."""
        html = self.client.get("/historico/").content.decode()

        self.assertEqual(html.count('class="semana__barra"'), 16)

    def test_a_media_de_agua_vem_com_os_dias_que_a_sustentam(self):
        """A média sozinha mente nos dois sentidos. A barra é quantos dias."""
        html = self.client.get("/historico/").content.decode()

        self.assertIn("2500", html)
        self.assertIn("semana__preenche--1", html)
