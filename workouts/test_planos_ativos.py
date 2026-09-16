"""Plano ativo antigo NÃO é remontado sozinho (17/09/2026).

Política: a conferência de `sync_active_routine` só remonta quando o plano
ficou INVÁLIDO — sessão apontando para exercício aposentado, dias de treino
que mudaram, divisão que não corresponde mais à frequência. Quando só a
PRESCRIÇÃO mudou (o catálogo cresceu, a faixa de séries mudou), a ficha
fica como está — é retrato — e a Home mostra um aviso único e dispensável:
"Seu treino pode ficar mais completo — regenerar?". Regenerar é pedido da
pessoa; a dispensa fica gravada no plano, não no navegador.

O que este arquivo impede: o deploy de 17/09 trocando a ficha de quem já
tinha uma no meio da semana, sem ninguém pedir.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import services
from workouts.models import Exercise, TrainingPlan, WorkoutTemplateItem


def _pessoa(email):
    # Completo (até 90): nada é cortado pelo relógio, então a dose do
    # principal na ficha é a do catálogo — e mudá-la no catálogo diverge.
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="one",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.COMPLETO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in (0, 3):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


def _retrato(plan):
    return sorted(
        (s.label, i.opcao, i.exercise_id, i.sets)
        for s in plan.sessions.all()
        for i in s.exercises.all()
    )


def _mudar_a_prescricao(plan, catalogo="catalogo-de-ontem"):
    """Simula o catálogo mudando embaixo da ficha: o primeiro item do modelo
    de A ganha duas repetições no topo da faixa — a prescrição diverge, a
    ficha continua válida — e a ficha passa a dizer que nasceu de OUTRO
    catálogo (`catalogo`; `""` é a ficha de antes de 17/09/2026). Repetições,
    e não séries: uma série a mais ou a menos é absorvida pela faixa
    (`preencher_ate_a_faixa` sobe o acessório de volta) e a prescrição
    sairia igual."""
    modelo = {t.label: t for t in services.templates_for(plan.split)}["A"]
    item = modelo.items.select_related("exercise").filter(exercise__is_active=True).order_by("order").first()
    WorkoutTemplateItem.objects.filter(pk=item.pk).update(rep_max=item.rep_max + 2)
    TrainingPlan.objects.filter(pk=plan.pk).update(catalogo=catalogo)
    plan.catalogo = catalogo


class PlanoAntigoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_prescricao_diferente_nao_remonta_o_plano(self):
        user = _pessoa("antigo@exemplo.com")
        plan = services.create_routine(user)
        antes = _retrato(plan)
        _mudar_a_prescricao(plan)

        self.assertTrue(services.rotina_desatualizada(plan, user))
        self.assertFalse(services.rotina_invalida(plan, user))
        depois, mudou = services.sync_active_routine(user)

        self.assertFalse(mudou)
        self.assertEqual(depois.pk, plan.pk)
        self.assertEqual(_retrato(depois), antes)

    def test_a_ficha_e_retrato_das_entradas(self):
        """Catálogo, nível e faixa de duração ficam gravados no plano."""
        user = _pessoa("retrato@exemplo.com")
        plan = services.create_routine(user)

        self.assertEqual(plan.catalogo, services.versao_do_catalogo())
        self.assertEqual(plan.nivel, "intermediario")
        self.assertEqual(plan.duracao, DuracaoTreino.COMPLETO)
        self.assertEqual(len(plan.catalogo), 16)

    def test_mudar_o_proprio_nivel_ou_a_faixa_remonta_como_sempre(self):
        """A pessoa mexeu na PRÓPRIA entrada: é o caso dos dias de treino,
        não o do catálogo — a ficha fica inválida e o painel remonta. Sem
        isto, quem trocasse para "Rápido" no Perfil continuaria com a ficha
        de 60 minutos e um aviso dizendo que ela "pode ficar mais completa"."""
        from accounts.models import Profile

        user = _pessoa("entrada@exemplo.com")
        plan = services.create_routine(user)
        self.assertFalse(services.rotina_invalida(plan, user))

        Profile.objects.filter(user=user).update(experiencia="avancado")
        user.refresh_from_db()
        self.assertTrue(services.rotina_invalida(plan, user))
        self.assertFalse(services.rotina_desatualizada(plan, user), "inválida não é desatualizada")
        depois, mudou = services.sync_active_routine(user)
        self.assertTrue(mudou)
        self.assertEqual(depois.nivel, "avancado")

        Profile.objects.filter(user=user).update(duracao_treino=DuracaoTreino.RAPIDO)
        user.refresh_from_db()
        self.assertTrue(services.rotina_invalida(depois, user))
        de_novo, mudou = services.sync_active_routine(user)
        self.assertTrue(mudou)
        self.assertEqual(de_novo.duracao, DuracaoTreino.RAPIDO)

    def test_a_ficha_de_antes_de_17_09_nao_e_invalidada_pelo_desconhecido(self):
        """Plano com as três entradas em branco (nascido antes da migration):
        não é remontado por isso, e cai na conferência exata para o aviso."""
        user = _pessoa("antes@exemplo.com")
        plan = services.create_routine(user)
        TrainingPlan.objects.filter(pk=plan.pk).update(catalogo="", nivel="", duracao="")
        plan.refresh_from_db()

        self.assertFalse(services.rotina_invalida(plan, user))
        self.assertFalse(services.rotina_desatualizada(plan, user), "mesma prescrição: sem aviso")
        _mudar_a_prescricao(plan, catalogo="")
        self.assertTrue(services.rotina_desatualizada(plan, user))
        self.assertEqual(services.sync_active_routine(user)[0].pk, plan.pk)

    def test_com_o_mesmo_catalogo_a_conferencia_nao_represcreve(self):
        """A impressão digital responde sozinha: nenhuma consulta de modelo
        ou de sessão para dizer que nada mudou."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        user = _pessoa("barato@exemplo.com")
        plan = services.create_routine(user)
        with CaptureQueriesContext(connection) as ctx:
            self.assertFalse(services.aviso_de_regenerar(user, plan=plan))
        self.assertEqual(len(ctx.captured_queries), 0, [q["sql"][:80] for q in ctx.captured_queries])

    def test_a_conferencia_que_bate_carimba_a_impressao_digital_de_hoje(self):
        """Ficha nascida de outro catálogo, prescrição IGUAL à de hoje (o
        caso de todo deploy que só reescreve prosa do TREINO.md): a
        primeira visita paga a conferência exata e grava a impressão de
        hoje no plano; a segunda responde com zero consultas. Sem o
        carimbo eram onze consultas por visita, para sempre."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        user = _pessoa("carimbo@exemplo.com")
        plan = services.create_routine(user)
        TrainingPlan.objects.filter(pk=plan.pk).update(catalogo="catalogo-de-ontem")
        plan.catalogo = "catalogo-de-ontem"

        self.assertFalse(services.aviso_de_regenerar(user, plan=plan))
        plan.refresh_from_db()
        self.assertEqual(plan.catalogo, services.versao_do_catalogo())
        with CaptureQueriesContext(connection) as ctx:
            self.assertFalse(services.aviso_de_regenerar(user, plan=plan))
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_a_prescricao_diferente_nao_recebe_o_carimbo(self):
        """Controle: com a prescrição divergente o aviso aparece e o plano
        continua dizendo de que catálogo nasceu — carimbar aqui apagaria o
        aviso na visita seguinte sem ninguém decidir nada."""
        user = _pessoa("sem-carimbo@exemplo.com")
        plan = services.create_routine(user)
        _mudar_a_prescricao(plan)
        self.assertTrue(services.aviso_de_regenerar(user, plan=plan))
        plan.refresh_from_db()
        self.assertEqual(plan.catalogo, "catalogo-de-ontem")

    def test_plano_invalido_continua_sendo_remontado(self):
        """Exercício aposentado na ficha é o caso de sempre: remonta."""
        user = _pessoa("invalido@exemplo.com")
        plan = services.create_routine(user)
        exercicio = plan.sessions.first().exercises.first().exercise
        Exercise.objects.filter(pk=exercicio.pk).update(is_active=False)

        self.assertTrue(services.rotina_invalida(plan, user))
        depois, mudou = services.sync_active_routine(user)

        self.assertTrue(mudou)
        self.assertNotEqual(depois.pk, plan.pk)
        self.assertFalse(TrainingPlan.objects.get(pk=plan.pk).is_active)

    def test_o_painel_nao_troca_a_ficha_de_quem_ja_tinha(self):
        user = _pessoa("painel@exemplo.com")
        plan = services.create_routine(user)
        antes = _retrato(plan)
        _mudar_a_prescricao(plan)
        self.client.force_login(user)

        self.client.get(reverse("workouts:routine"))

        self.assertEqual(TrainingPlan.objects.get(user=user, is_active=True).pk, plan.pk)
        self.assertEqual(_retrato(plan), antes)


class AvisoDeRegenerarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = _pessoa("aviso@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)

    def test_sem_divergencia_a_home_nao_avisa(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn("regenerar?", html)

    def test_com_divergencia_a_home_avisa_uma_vez_e_a_dispensa_fica_no_plano(self):
        _mudar_a_prescricao(self.plan)

        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("Seu treino pode ficar mais completo", html)
        self.assertIn('class="card aviso-regenerar"', html)

        resposta = self.client.post(reverse("workouts:dispensar_aviso"))
        self.assertEqual(resposta.status_code, 302)
        self.plan.refresh_from_db()
        self.assertIsNotNone(self.plan.aviso_dispensado_em)
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn("Seu treino pode ficar mais completo", html)

    def test_regenerar_cria_o_plano_novo_e_o_antigo_fica_como_retrato(self):
        _mudar_a_prescricao(self.plan)

        resposta = self.client.post(reverse("workouts:regenerar"))

        self.assertEqual(resposta.status_code, 302)
        novo = TrainingPlan.objects.get(user=self.user, is_active=True)
        self.assertNotEqual(novo.pk, self.plan.pk)
        self.assertTrue(TrainingPlan.objects.filter(pk=self.plan.pk, is_active=False).exists())
        self.assertFalse(services.rotina_desatualizada(novo, self.user))
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn("Seu treino pode ficar mais completo", html)

    def test_ficha_ajustada_a_mao_nao_recebe_o_aviso(self):
        """Quem ajustou a ficha escolheu aqueles exercícios; o aviso de
        regenerar seria o app pedindo para desfazer a escolha."""
        from django.utils import timezone

        _mudar_a_prescricao(self.plan)
        TrainingPlan.objects.filter(pk=self.plan.pk).update(customized_at=timezone.now())

        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn("Seu treino pode ficar mais completo", html)


class DemoResemeadoTests(TestCase):
    def test_o_demo_recebe_a_ficha_nova_quando_a_prescricao_muda(self):
        """O demo é fixture de que o seed é dono: ele NÃO espera alguém
        clicar em regenerar."""
        from demo.middleware import DEMO_EMAIL as EMAIL_DEMO

        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        call_command("seed_demo", verbosity=0)
        from accounts.models import User

        user = User.objects.get(email=EMAIL_DEMO)
        plan = TrainingPlan.objects.get(user=user, is_active=True)
        _mudar_a_prescricao(plan)
        self.assertTrue(services.rotina_desatualizada(plan, user))

        call_command("seed_demo", verbosity=0)

        novo = TrainingPlan.objects.get(user=user, is_active=True)
        self.assertNotEqual(novo.pk, plan.pk)
        self.assertFalse(services.rotina_desatualizada(novo, user))
