"""Nenhum GET CRIA conquista — o item 0 da missão "quem entra não desiste".

A missão A deixou a lista dos números que ainda divergem, e o segundo era
este: `achievements.resumo` DESBLOQUEAVA a regra que chegou a 100 % dentro
de uma requisição GET, e `ConquistasView` chamava `avaliar` — o catálogo
inteiro, com escrita — também num GET. Duas consequências reais:

- a primeira leitura do Progresso num dia podia devolver um número de
  conquistas diferente da segunda, com os mesmos dados. "Mesmos dados,
  números diferentes", pela porta de trás;
- uma requisição que a pessoa não pediu — um prefetch do navegador, um
  "abrir em nova aba", um robô — mudava o banco dela.

A saída não foi um botão "resgatar", que ninguém tocaria: foi mover a
escrita para o POST QUE CRIA O FATO, que é o que a doutrina de
`ConcluirSerieView` já dizia desde 16/09/2026 ("a conquista é avaliada na
primeira série do dia e no recorde, e anunciada onde nasce"). Agora vale
para as outras portas: refeição, água e corrida.

E o defeito que a avaliação no GET existia para evitar — barra "1/1" cheia
com a conquista trancada ao lado (avaliação B35, 16/09/2026) — não volta,
porque a barra só chega a 100 % DEPOIS de um desses POSTs, e ele desbloqueia
na hora. O último teste daqui é exatamente esse.
"""
from datetime import timedelta
from decimal import Decimal

from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay
from achievements.models import UserAchievement
from plans.models import MealStatus
from plans.tests import create_complete_user
from workouts import services as treino
from workouts.models import ExerciseLog


class NenhumGETDesbloqueiaConquistaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="get-nao-grava@exemplo.com")
        self.client.force_login(self.user)
        # Histórico que fecha "Primeiro treino" e "5 treinos" — o estado em
        # que a avaliação no GET tinha o que gravar.
        hoje = timezone.localdate()
        treino.create_routine(self.user)
        plano = treino.get_active_routine(self.user)
        exercicio = plano.sessions.first().exercises.first().exercise
        for atras in range(6):
            ExerciseLog.objects.create(
                user=self.user, exercise=exercicio, date=hoje - timedelta(days=atras + 1),
                set_number=1, weight_kg=Decimal("20"), reps=10,
            )

    def _quantas(self):
        return UserAchievement.objects.filter(user=self.user).count()

    def test_a_pre_condicao_ha_o_que_gravar_e_nada_gravado(self):
        """SEM ESTE TESTE AS VARREDURAS ABAIXO PODIAM PASSAR VAZIAS (revisão do
        PR #162). Elas comparam `antes` com `depois`; se o fixture nascesse com
        a conquista já gravada, ou sem nenhuma regra a 100 %, "nada mudou"
        ficaria verde sem nunca ter havido o que mudar."""
        from achievements import services

        self.assertEqual(self._quantas(), 0)
        cheias = [
            c for c in services.a_caminho(services.reunir(self.user), set())
            if c["pct"] >= 100
        ]
        self.assertTrue(cheias, "o fixture não deixa nenhuma regra a 100 %")

    def test_abrir_o_progresso_cinco_vezes_nao_cria_conquista(self):
        antes = self._quantas()
        for _ in range(5):
            self.assertEqual(self.client.get(reverse("plans:history")).status_code, 200)
        self.assertEqual(self._quantas(), antes)

    def test_abrir_as_conquistas_cinco_vezes_nao_cria_conquista(self):
        antes = self._quantas()
        for _ in range(5):
            self.assertEqual(
                self.client.get(reverse("achievements:list")).status_code, 200
            )
        self.assertEqual(self._quantas(), antes)

    def test_nenhuma_tela_do_app_grava_conquista_num_GET(self):
        """A varredura: as telas que leem conquista, uma a uma."""
        antes = self._quantas()
        for rota in ("plans:today", "plans:history", "achievements:list", "areas"):
            with self.subTest(rota=rota):
                self.client.get(reverse(rota))
                self.assertEqual(self._quantas(), antes, rota)


class NenhumaEscritaNaTabelaDeConquistasNumGETTests(TestCase):
    """A varredura por CONSULTA, e não por contagem de linhas.

    `UserAchievement.objects.count()` é cego a um `UPDATE` (revisão do PR
    #162): o GET que ANUNCIA uma conquista marca `seen_at`, e a contagem não
    muda. Aqui se lê o SQL de cada tela e se procura escrita na tabela de
    conquistas — e o controle positivo prova que a varredura enxerga essa
    escrita quando ela existe.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="get-sql@exemplo.com")
        self.client.force_login(self.user)
        treino.create_routine(self.user)

    def _escritas(self, rota):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as capturado:
            self.client.get(reverse(rota))
        return [
            q["sql"] for q in capturado.captured_queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            and "achievements_userachievement" in q["sql"]
        ]

    def test_nenhuma_tela_escreve_na_tabela_de_conquistas(self):
        for rota in ("plans:today", "plans:history", "achievements:list", "areas"):
            with self.subTest(rota=rota):
                self.assertEqual(self._escritas(rota), [], rota)

    def test_com_anuncio_pendente_o_get_continua_sem_escrever(self):
        """ERA a exceção conhecida (o anúncio marcava `seen_at` no GET) e
        deixou de ser (decisão do dono, 27/09/2026): um prefetch consumia o
        anúncio. Com um id na sessão, a tela desenha o aviso e NÃO escreve.

        O controle positivo desta varredura é o POST do "visto", e mora em
        `config/test_get_nao_grava.py` junto da régua geral."""
        from achievements.context_processors import CHAVE

        conquista = UserAchievement.objects.create(user=self.user, slug="primeiro-treino")
        sessao = self.client.session
        sessao[CHAVE] = [conquista.pk]
        sessao.save()
        self.assertEqual(self._escritas("plans:history"), [])
        conquista.refresh_from_db()
        self.assertIsNone(conquista.seen_at)

    def test_controle_positivo_o_post_do_visto_escreve_e_a_varredura_ve(self):
        """A varredura não é cega: capturando o POST do "visto", a mesma
        função que diz "zero" nas telas enxerga o `UPDATE`."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        conquista = UserAchievement.objects.create(user=self.user, slug="primeiro-treino")
        with CaptureQueriesContext(connection) as capturado:
            self.client.post(
                reverse("achievements:marcar_vistas"), {"id": conquista.pk},
                HTTP_X_REQUESTED_WITH="fetch",
            )
        self.assertTrue(any(
            q["sql"].lstrip().upper().startswith("UPDATE")
            and "achievements_userachievement" in q["sql"]
            for q in capturado.captured_queries
        ))


class OPOSTQueCriaOFatoDesbloqueiaTests(TestCase):
    """CONTROLE POSITIVO do arquivo inteiro: a escrita não sumiu do app —
    ela mudou de porta."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="post-desbloqueia@exemplo.com")
        self.client.force_login(self.user)
        hoje = timezone.localdate()
        TrainingDay.objects.filter(user=self.user).delete()
        TrainingDay.objects.create(user=self.user, weekday=hoje.weekday(), duration_min=60)
        treino.create_routine(self.user)

    def _slugs(self):
        return set(
            UserAchievement.objects.filter(user=self.user).values_list("slug", flat=True)
        )

    def test_a_primeira_serie_desbloqueia_o_primeiro_treino(self):
        self.assertNotIn("primeiro-treino", self._slugs())
        plano = treino.get_active_routine(self.user)
        item = plano.sessions.first().exercises.first()
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": item.exercise_id, "weight_kg": "0", "reps": "10",
             "dia": timezone.localdate().isoformat()},
        )
        self.assertIn(resposta.status_code, (200, 302))
        self.assertIn("primeiro-treino", self._slugs())

    def test_marcar_refeicao_desbloqueia_o_que_a_ofensiva_fechou(self):
        """A refeição não cria conquista de treino — ela pode FECHAR o dia, e
        dia fechado move a ofensiva. O que se mede aqui é que o POST passa
        pela avaliação: sem ela, nada nasceria até alguém abrir o Progresso.
        """
        from plans import services as plano_services

        import math

        from plans import streaks
        from plans.models import MealLog

        plano, _ = plano_services.sync_active_plan(self.user)
        slots = list(plano.slots.order_by("time"))
        # A avaliação só roda quando a refeição LEVA o dia ao limiar (decisão
        # do dono, 27/09/2026: `streaks.dieta_fechou_o_pilar`); as de antes
        # são gravadas direto, e a que cruza passa pela view.
        precisa = math.ceil(len(slots) * streaks.ADESAO_MINIMA_PCT / 100)
        for anterior in slots[: precisa - 1]:
            MealLog.objects.create(
                user=self.user, slot=anterior, date=timezone.localdate(),
                status=MealStatus.DONE, chosen_option=anterior.options.first(),
            )
        slot = slots[precisa - 1]
        antes = UserAchievement.objects.filter(user=self.user).count()
        # "Comi esta" exige a OPÇÃO — o filtro que fecha o IDOR do cardápio.
        opcao = slot.options.first()
        with mock.patch("plans.views.conquistas.sincronizar") as espiao:
            resposta = self.client.post(
                reverse("plans:mark_meal", args=[slot.pk]),
                {"status": MealStatus.DONE, "option": opcao.pk},
            )
        self.assertEqual(resposta.status_code, 302)
        # O ESPIÃO, e não uma contagem: `count() >= antes` era verdadeiro
        # sempre — uma contagem nunca cai — e seguia verde com a chamada
        # apagada da view (revisão do PR #162).
        espiao.assert_called_once()
        self.assertEqual(espiao.call_args.args[0], self.user)
        self.assertGreaterEqual(UserAchievement.objects.filter(user=self.user).count(), antes)

    def test_a_agua_passa_pela_avaliacao(self):
        """Quem só bebe água também pode fechar o dia — e sem esta chamada, com
        o GET não gravando mais, nada nasceria até o próximo build. O copo é
        o que CRUZA o alvo — só esse pode fechar o dia (`streaks.
        agua_fechou_o_pilar`); o caso que não cruza está em `plans/
        test_stress.py`."""
        from plans import services as plano_services
        from plans import streaks, weight_trend
        from plans.models import HydrationLog

        plano, _ = plano_services.sync_active_plan(self.user)
        alvo = weight_trend.hidratacao_ml(plano.weight_kg) * streaks.HIDRATACAO_MINIMA_PCT / 100
        HydrationLog.objects.create(user=self.user, date=timezone.localdate(), ml=int(alvo) - 100)
        with mock.patch("plans.views.conquistas.sincronizar") as espiao:
            resposta = self.client.post(reverse("plans:log_hydration"), {"ml": 250})
        self.assertIn(resposta.status_code, (200, 302))
        espiao.assert_called_once()

    def test_a_agua_reenviada_nao_avalia_de_novo(self):
        """A fila offline reenvia; o reenvio (`op_id` já aplicado) não soma, e
        não deve pagar a avaliação."""
        corpo = {"ml": 250, "op_id": "reenvio-agua-1"}
        self.client.post(reverse("plans:log_hydration"), corpo)
        with mock.patch("plans.views.conquistas.sincronizar") as espiao:
            self.client.post(reverse("plans:log_hydration"), corpo)
        espiao.assert_not_called()

    def test_a_corrida_manual_passa_pela_avaliacao(self):
        import uuid

        dados = {
            "distancia_km": "5,2", "tempo": "28:10",
            "data": timezone.localdate().isoformat(), "sensacao": "normal",
            "op_id": uuid.uuid4().hex,
        }
        with mock.patch("workouts.corrida_views.conquistas.sincronizar") as espiao:
            resposta = self.client.post(reverse("workouts:corrida_nova"), dados)
        self.assertEqual(resposta.status_code, 302)
        espiao.assert_called_once()

    def test_a_corrida_do_gps_passa_pela_avaliacao(self):
        import json
        import uuid

        fim = timezone.now()
        corpo = {
            "op_id": uuid.uuid4().hex,
            "comecou_em": (fim - timedelta(minutes=30)).isoformat(),
            "terminou_em": fim.isoformat(),
            "distancia_m": 5200, "duracao_s": 1800,
        }
        with mock.patch("workouts.corrida_views.conquistas.sincronizar") as espiao:
            resposta = self.client.post(
                reverse("workouts:salvar_corrida"),
                json.dumps(corpo), content_type="application/json",
            )
        self.assertLess(resposta.status_code, 400, resposta.content[:200])
        espiao.assert_called_once()
