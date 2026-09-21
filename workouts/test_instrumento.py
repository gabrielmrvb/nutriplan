# -*- coding: utf-8 -*-
"""T2.4 — o instrumento: `medir_progressao`, a guarda do recorde, o convite
de nível e a poda das operações sincronizadas (17/09/2026).

Quatro coisas pequenas que o plano mestre juntou porque compartilham a
mesma natureza — medir e limpar sem mudar o que a pessoa vê:

- `manage.py medir_progressao` é SÓ LEITURA: conta, por abertura de
  exercício, o estado que a adaptação daria (subir/manter/retomar/
  estagnado), quantas repetições a pessoa fez além ou aquém de `rep_max`,
  quantas séries pararam EXATAMENTE em `rep_max` (o sinal de que a faixa
  está sendo lida como teto — RIR-ultima-serie), quantos "retomar" vêm
  de exercício abandonado com a pessoa treinando (sem pausa de verdade) e
  a distribuição dos intervalos. É o dado que vai rever os 21/28/27 dias
  do T2.3, que hoje são calibração [HIPOTÉTICA];
- `RecordLoadView` avalia conquista só na primeira série do dia ou no
  recorde — a mesma guarda que `ConcluirSerieView` já tinha. O catálogo
  inteiro custa dezenas de consultas, e a rota antiga pagava em toda
  carga anotada;
- o Progresso convida quem se declarou iniciante (ou não respondeu) a
  atualizar o nível depois de 180 dias e 24 datas com série: o teto por
  grupo sobe (TREINO.md, tabela B), e o app não infere nível — convida;
- `manage.py podar_operacoes` roda no build e apaga `SyncedOperation`
  vencidas; `VALIDADE_DIAS` (30) fica acima dos 7 dias que a fila offline
  ainda pode reenviar — poda nunca apaga `op_id` que um item drenável
  reenviaria.
"""
import io
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import Experiencia, Profile, SyncedOperation
from achievements.models import UserAchievement as Conquista
from workouts import progresso, services
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje

RAIZ = Path(__file__).resolve().parent.parent


class APodaTests(TestCase):
    def test_a_validade_e_maior_que_a_janela_de_reenvio_da_fila(self):
        """A fila offline reenvia item de até 7 dias (`CLAUDE.md`, "O DIA
        viaja com o evento"): uma validade menor apagaria o `op_id` que o
        reenvio traria de volta, e água somaria duas vezes."""
        self.assertGreater(SyncedOperation.VALIDADE_DIAS, 7)
        self.assertIn("7", SyncedOperation.__doc__ + str(SyncedOperation.podar.__doc__))

    def test_o_comando_apaga_so_o_vencido(self):
        pessoa = create_user(email="poda@exemplo.com")
        SyncedOperation.ja_aplicada(pessoa, "velha")
        SyncedOperation.objects.filter(op_id="velha").update(
            created_at=timezone.now() - timedelta(days=SyncedOperation.VALIDADE_DIAS + 1)
        )
        SyncedOperation.ja_aplicada(pessoa, "recente")
        SyncedOperation.objects.filter(op_id="recente").update(
            created_at=timezone.now() - timedelta(days=SyncedOperation.VALIDADE_DIAS - 1)
        )
        saida = io.StringIO()
        call_command("podar_operacoes", stdout=saida)
        self.assertIn("1", saida.getvalue())
        self.assertEqual(
            sorted(SyncedOperation.objects.values_list("op_id", flat=True)), ["recente"]
        )

    def test_o_build_roda_a_poda_depois_dos_seeds(self):
        build = (RAIZ / "scripts" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("python manage.py podar_operacoes", build)
        self.assertGreater(build.index("podar_operacoes"), build.index("seed_demo"))


class AGuardaDoRecordeNaCargaTests(TestCase):
    """`RecordLoadView` (a rota da ficha, fora da fila) avalia conquista só
    quando há motivo: primeira série do dia ou recorde."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="guarda@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )
        self.url = reverse("workouts:record_load", args=[self.item.exercise_id])

    def _log(self, dias_atras, serie, peso):
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=dias_atras),
            set_number=serie, weight_kg=Decimal(peso), reps=8,
        )

    def test_abaixo_do_recorde_e_sem_ser_a_primeira_do_dia_nao_avalia(self):
        self._log(10, 1, "65")
        self._log(0, 1, "60")
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.post(self.url, {"weight_kg": "60", "reps": "8", "set_number": "2"})
        self.assertIn(resposta.status_code, (200, 302))
        self.assertFalse(Conquista.objects.filter(user=self.pessoa).exists())
        # A régua: o custo de gravar uma série, sem o catálogo de conquistas
        # atrás — medido em 17/09/2026 (a rota antiga pagava 40+).
        self.assertLessEqual(len(consultas), 24, [q["sql"][:70] for q in consultas])

    def test_acima_do_recorde_avalia_e_a_conquista_nasce(self):
        """Controle positivo: a guarda deixa passar o recorde."""
        self._log(10, 1, "65")
        self._log(0, 1, "60")
        self.client.post(self.url, {"weight_kg": "70", "reps": "8", "set_number": "2"})
        self.assertTrue(Conquista.objects.filter(user=self.pessoa, slug="novo-recorde").exists())

    def test_a_primeira_serie_do_dia_avalia(self):
        self.client.post(self.url, {"weight_kg": "40", "reps": "8", "set_number": "1"})
        self.assertTrue(Conquista.objects.filter(user=self.pessoa, slug="primeiro-treino").exists())


class OConviteDeNivelTests(TestCase):
    """Quem se declarou iniciante e treina há meses recebe o convite — e só."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="nivel@exemplo.com", weekdays=dias_incluindo_hoje(3))
        Profile.objects.filter(user=self.pessoa).update(experiencia=Experiencia.INICIANTE)
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        self.exercicio = next(
            i.exercise for s in services.get_active_routine(self.pessoa).sessions.all()
            for i in s.exercises.all()
        )

    def _treinar(self, dias, datas):
        """`datas` datas espalhadas pelos últimos `dias` dias."""
        for k in range(datas):
            dia = self.hoje - timedelta(days=int(dias * k / max(datas - 1, 1)))
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.exercicio, date=dia, set_number=1,
                weight_kg=Decimal("40"), reps=10,
            )

    def test_duzentos_dias_e_trinta_datas_convidam(self):
        self._treinar(200, 30)
        self.assertTrue(progresso.convidar_a_atualizar_experiencia(self.pessoa))
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertIn('class="card convite-nivel"', html)
        self.assertIn(reverse("accounts:profile"), html.split('class="card convite-nivel"', 1)[1].split("</section>", 1)[0])

    def test_cem_dias_nao_convidam_mesmo_com_muitas_datas(self):
        self._treinar(100, 30)
        self.assertFalse(progresso.convidar_a_atualizar_experiencia(self.pessoa))
        self.assertNotIn('class="card convite-nivel"', self.client.get(reverse("plans:history")).content.decode())

    def test_poucas_datas_nao_convidam_mesmo_com_muitos_dias(self):
        self._treinar(300, 10)
        self.assertFalse(progresso.convidar_a_atualizar_experiencia(self.pessoa))

    def test_quem_nao_respondeu_tambem_e_convidado(self):
        Profile.objects.filter(user=self.pessoa).update(experiencia="")
        self._treinar(200, 30)
        pessoa = type(self.pessoa).objects.get(pk=self.pessoa.pk)
        self.assertTrue(progresso.convidar_a_atualizar_experiencia(pessoa))

    def test_intermediario_e_avancado_nunca(self):
        self._treinar(400, 60)
        for nivel in (Experiencia.INTERMEDIARIO, Experiencia.AVANCADO):
            Profile.objects.filter(user=self.pessoa).update(experiencia=nivel)
            # Recarregada: `user.profile` fica em cache no objeto.
            pessoa = type(self.pessoa).objects.get(pk=self.pessoa.pk)
            self.assertFalse(progresso.convidar_a_atualizar_experiencia(pessoa), nivel)

    def test_a_pergunta_custa_uma_consulta_para_qualquer_nivel(self):
        """O nível entra na MESMA consulta (junção com o perfil): no
        Progresso `user.profile` não está em cache, e lê-lo à parte custava
        uma segunda consulta — 28 contra o teto de 26 da tela."""
        self._treinar(200, 30)
        with CaptureQueriesContext(connection) as ctx:
            self.assertTrue(progresso.convidar_a_atualizar_experiencia(self.pessoa))
        self.assertEqual(len(ctx.captured_queries), 1)
        Profile.objects.filter(user=self.pessoa).update(experiencia=Experiencia.INTERMEDIARIO)
        with CaptureQueriesContext(connection) as ctx:
            self.assertFalse(progresso.convidar_a_atualizar_experiencia(self.pessoa))
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_as_constantes_sao_as_do_plano(self):
        self.assertEqual(progresso.DIAS_PARA_O_CONVITE, 180)
        self.assertEqual(progresso.DATAS_PARA_O_CONVITE, 24)


@tag("lento")  # medição read-only sobre 365 dias semeados; não é guarda de correção
class OMedidorDeProgressaoTests(TestCase):
    """`medir_progressao` lê tudo e não escreve nada."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user

        self.pessoa = create_complete_user(email="medir@exemplo.com", experiencia="intermediario")
        call_command("seed_stress", self.pessoa.email, "--dias", "120", verbosity=0)

    def test_so_le_e_nao_muda_uma_linha(self):
        antes = (ExerciseLog.objects.count(), list(ExerciseLog.objects.order_by("pk").values_list("pk", "weight_kg", "reps")[:50]))
        saida = io.StringIO()
        with CaptureQueriesContext(connection) as ctx:
            call_command("medir_progressao", stdout=saida)
        escritas = [
            q["sql"] for q in ctx.captured_queries
            if not q["sql"].lstrip().upper().startswith(("SELECT", "SAVEPOINT", "RELEASE SAVEPOINT", "SET "))
        ]
        self.assertEqual(escritas, [])
        self.assertEqual((ExerciseLog.objects.count(), list(ExerciseLog.objects.order_by("pk").values_list("pk", "weight_kg", "reps")[:50])), antes)
        texto = saida.getvalue()
        for chave in ("aberturas", "manter", "retomar", "paradas exatas em rep_max", "sem pausa", "intervalo", "versão rápida"):
            self.assertIn(chave, texto, texto)

    def test_conta_os_usos_da_versao_rapida_dos_ultimos_trinta_dias(self):
        """O dado que decide a rápida em 30 dias (ficha única, 17/09/2026):
        um uso por pessoa e dia; o de 31 dias atrás fica de fora."""
        from datetime import timedelta

        from django.utils import timezone

        from plans.tests import create_complete_user
        from workouts.models import EventoDeProduto

        hoje = timezone.localdate()
        outra = create_complete_user(email="medir-rapida@exemplo.com")
        EventoDeProduto.objects.create(user=self.pessoa, nome=EventoDeProduto.VERSAO_RAPIDA, date=hoje)
        EventoDeProduto.objects.create(user=self.pessoa, nome=EventoDeProduto.VERSAO_RAPIDA, date=hoje - timedelta(days=2))
        EventoDeProduto.objects.create(user=outra, nome=EventoDeProduto.VERSAO_RAPIDA, date=hoje - timedelta(days=29))
        EventoDeProduto.objects.create(user=outra, nome=EventoDeProduto.VERSAO_RAPIDA, date=hoje - timedelta(days=31))
        saida = io.StringIO()
        call_command("medir_progressao", stdout=saida)
        self.assertIn("versão rápida: 3 uso(s) em 2 pessoa(s) nos últimos 30 dias", saida.getvalue())

    def test_o_custo_nao_cresce_por_exercicio(self):
        """Duas consultas fixas (planos e registros) — não uma por exercício
        nem por pessoa: é um instrumento para rodar sobre produção inteira."""
        with CaptureQueriesContext(connection) as ctx:
            call_command("medir_progressao", stdout=io.StringIO())
        # 4 -> 6 (17/09/2026): as duas agregações da versão rápida (usos e pessoas), fixas.
        self.assertLessEqual(len(ctx.captured_queries), 6, [q["sql"][:60] for q in ctx.captured_queries])
