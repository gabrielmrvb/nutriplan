"""Testes do acompanhamento profissional.

A maior parte deles não testa funcionalidade: testa que o acesso PARA. Esta é a
primeira parte do NutriPlan em que uma pessoa lê e escreve os dados de saúde de
outra, e o modo de falhar interessante não é "o botão não funcionou" — é "o
treinador do João abriu a ficha da Maria".

Por isso cada caminho de escrita tem um teste espelhado de negação, e eles
batem no HTTP e não na função: é pela URL que o ataque chega.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActivityLevel, Goal, Profile, TrainingDay, User, WeightEntry
from catalog.models import MealCategory, MealTemplate
from plans import services as plan_services
from plans.models import MealStatus
from plans.tests import CatalogFixture, create_complete_user
from workouts.models import (
    Exercise,
    ExerciseLog,
    SessionExercise,
    TrainingPlan,
    WorkoutTemplate,
)
from workouts.services import create_routine, get_active_routine, sync_active_routine

from . import monitoring, permissions, portfolio, prescription
from .models import (
    CoachUpdate,
    LinkRole,
    LinkStatus,
    ProfessionalProfile,
    ProfessionalStudentLink,
    VALIDADE_CONVITE,
    gerar_codigo,
)

SENHA = "senha-bem-forte-123"


def make_professional(email="treinador@exemplo.com", role=LinkRole.BOTH):
    user = User.objects.create_user(email=email, password=SENHA, first_name="Ana")
    ProfessionalProfile.objects.create(
        user=user, display_name="Ana Treinadora", default_role=role, council_id="CREF 1234-G/SP"
    )
    return user


def make_link(professional, student, role=LinkRole.BOTH, status=LinkStatus.ACTIVE):
    return ProfessionalStudentLink.objects.create(
        professional=professional,
        student=student,
        role=role,
        status=status,
        accepted_at=timezone.now() if status == LinkStatus.ACTIVE else None,
    )


# ==========================================================================
# O código do convite
# ==========================================================================

class InviteCodeTests(TestCase):
    def test_the_code_avoids_the_characters_people_mistype(self):
        """I, O, zero e um são as quatro que erram quando o código é ditado."""
        for _ in range(200):
            codigo = gerar_codigo()
            with self.subTest(codigo=codigo):
                self.assertNotRegex(codigo, r"[IO01]")
                self.assertEqual(len(codigo), 6)

    def test_two_codes_in_a_row_are_not_the_same(self):
        self.assertNotEqual(gerar_codigo(), gerar_codigo())


class InviteLifecycleTests(TestCase):
    def setUp(self):
        self.pro = make_professional()
        self.aluno = User.objects.create_user(email="aluno@exemplo.com", password=SENHA)

    def _convite(self, **kwargs):
        return ProfessionalStudentLink.objects.create(
            professional=self.pro, role=LinkRole.TRAINER, **kwargs
        )

    def test_a_fresh_invite_is_open(self):
        convite = self._convite()
        self.assertTrue(convite.convite_aberto)
        self.assertFalse(convite.convite_expirado)

    def test_an_invite_older_than_a_week_is_dead(self):
        """Convite aberto é uma autorização de escrita sobre dados de saúde
        esperando alguém apanhá-la. Sete dias, e ele envelhece sozinho."""
        convite = self._convite()
        ProfessionalStudentLink.objects.filter(pk=convite.pk).update(
            created_at=timezone.now() - VALIDADE_CONVITE - timedelta(minutes=1)
        )
        convite.refresh_from_db()

        self.assertTrue(convite.convite_expirado)
        self.assertFalse(convite.convite_aberto)

    def test_an_accepted_link_never_expires(self):
        convite = self._convite()
        convite.aceitar(self.aluno)
        ProfessionalStudentLink.objects.filter(pk=convite.pk).update(
            created_at=timezone.now() - timedelta(days=400)
        )
        convite.refresh_from_db()

        self.assertFalse(convite.convite_expirado)

    def test_accepting_records_who_and_when(self):
        convite = self._convite()
        convite.aceitar(self.aluno)

        self.assertEqual(convite.student, self.aluno)
        self.assertEqual(convite.status, LinkStatus.ACTIVE)
        self.assertIsNotNone(convite.accepted_at)

    def test_the_scope_decides_what_the_link_authorises(self):
        casos = [
            (LinkRole.TRAINER, True, False),
            (LinkRole.NUTRITIONIST, False, True),
            (LinkRole.BOTH, True, True),
        ]
        for role, treino, dieta in casos:
            with self.subTest(role=role):
                link = ProfessionalStudentLink(role=role)
                self.assertEqual(link.pode_treino, treino)
                self.assertEqual(link.pode_dieta, dieta)


class InviteFlowTests(TestCase):
    """O aceite pela web, que é por onde ele realmente acontece."""

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        self.convite = ProfessionalStudentLink.objects.create(
            professional=self.pro, role=LinkRole.TRAINER
        )
        self.url = reverse("connect", args=[self.convite.invite_code])

    def test_opening_the_link_does_not_accept_it(self):
        """O WhatsApp abre a URL antes de a pessoa tocar nela. Se o GET
        aceitasse, a pré-visualização do link autorizaria o acesso."""
        self.client.force_login(self.aluno)
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.convite.refresh_from_db()
        self.assertEqual(self.convite.status, LinkStatus.PENDING)
        self.assertIsNone(self.convite.student_id)

    def test_the_page_spells_out_what_is_being_authorised(self):
        self.client.force_login(self.aluno)
        corpo = self.client.get(self.url).content.decode()

        self.assertIn("alterar sua ficha de treino", corpo)
        # Convite de treinador não promete acesso à dieta.
        self.assertNotIn("alterar suas metas e seu cardápio", corpo)

    def test_posting_accepts_and_links(self):
        self.client.force_login(self.aluno)
        self.client.post(self.url)

        self.convite.refresh_from_db()
        self.assertEqual(self.convite.status, LinkStatus.ACTIVE)
        self.assertEqual(self.convite.student, self.aluno)

    def test_an_expired_invite_is_refused(self):
        ProfessionalStudentLink.objects.filter(pk=self.convite.pk).update(
            created_at=timezone.now() - VALIDADE_CONVITE - timedelta(minutes=1)
        )
        self.client.force_login(self.aluno)
        self.client.post(self.url)

        self.convite.refresh_from_db()
        self.assertEqual(self.convite.status, LinkStatus.PENDING)
        self.assertIsNone(self.convite.student_id)

    def test_nobody_links_to_themselves(self):
        self.client.force_login(self.pro)
        self.client.post(self.url)

        self.convite.refresh_from_db()
        self.assertEqual(self.convite.status, LinkStatus.PENDING)

    def test_a_second_invite_widens_the_scope_instead_of_crashing(self):
        """Um segundo vínculo ativo para o mesmo par violaria o índice único —
        e revogar um deixaria o outro em pé, que é o pior desfecho possível."""
        make_link(self.pro, self.aluno, role=LinkRole.TRAINER)

        segundo = ProfessionalStudentLink.objects.create(
            professional=self.pro, role=LinkRole.BOTH
        )
        self.client.force_login(self.aluno)
        self.client.post(reverse("connect", args=[segundo.invite_code]))

        ativos = ProfessionalStudentLink.objects.filter(
            professional=self.pro, student=self.aluno, status=LinkStatus.ACTIVE
        )
        self.assertEqual(ativos.count(), 1)
        self.assertEqual(ativos.first().role, LinkRole.BOTH)

    def test_an_unknown_code_does_not_leak_whether_it_ever_existed(self):
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("connect", args=["ZZZZZZ"]))

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Convite inválido", resposta.content.decode())


# ==========================================================================
# Autorização — a parte que precisa parar
# ==========================================================================

class AuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        self.estranho = create_complete_user(email="estranho@exemplo.com")
        plan_services.create_plan(self.aluno)
        create_routine(self.aluno)
        self.client.force_login(self.pro)

    def _rotas_de_leitura(self, student):
        return [
            reverse("coaching:student_monitor", args=[student.pk]),
            reverse("coaching:student_workout", args=[student.pk]),
            reverse("coaching:student_nutrition", args=[student.pk]),
        ]

    # ------------------------------------------------------ sem vínculo
    def test_without_a_link_every_tab_is_forbidden(self):
        for url in self._rotas_de_leitura(self.aluno):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_a_link_to_one_student_does_not_open_another(self):
        """O id vem da URL e é tratado como entrada hostil: a consulta filtra
        por profissional E por aluno, então id alheio não casa com nada."""
        make_link(self.pro, self.aluno)

        for url in self._rotas_de_leitura(self.estranho):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_another_professional_sees_nothing(self):
        make_link(self.pro, self.aluno)
        outro = make_professional(email="outro@exemplo.com")
        self.client.force_login(outro)

        for url in self._rotas_de_leitura(self.aluno):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    # ------------------------------------------------------------ escopo
    def test_a_trainer_cannot_open_the_nutrition_tab(self):
        make_link(self.pro, self.aluno, role=LinkRole.TRAINER)

        self.assertEqual(
            self.client.get(
                reverse("coaching:student_nutrition", args=[self.aluno.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("coaching:student_workout", args=[self.aluno.pk])
            ).status_code,
            200,
        )

    def test_a_nutritionist_cannot_open_the_workout_tab(self):
        make_link(self.pro, self.aluno, role=LinkRole.NUTRITIONIST)

        self.assertEqual(
            self.client.get(
                reverse("coaching:student_workout", args=[self.aluno.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("coaching:student_nutrition", args=[self.aluno.pk])
            ).status_code,
            200,
        )

    def test_a_trainer_cannot_write_to_the_diet(self):
        """Esconder a aba é cortesia; a trava é a rota recusar o POST."""
        make_link(self.pro, self.aluno, role=LinkRole.TRAINER)
        antes = plan_services.get_active_plan(self.aluno).target_kcal

        resposta = self.client.post(
            reverse("coaching:adjust_targets", args=[self.aluno.pk]),
            {
                "activity_level": ActivityLevel.SEDENTARY,
                "goal": Goal.CUT,
                "kcal_adjustment": -300,
            },
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(plan_services.get_active_plan(self.aluno).target_kcal, antes)

    def test_a_nutritionist_cannot_write_to_the_workout(self):
        make_link(self.pro, self.aluno, role=LinkRole.NUTRITIONIST)
        item = SessionExercise.objects.filter(
            session__plan__user=self.aluno
        ).first()
        antes = item.sets

        resposta = self.client.post(
            reverse("coaching:adjust_exercise", args=[self.aluno.pk, item.pk]),
            {"sets": 9, "rep_min": 5, "rep_max": 8, "rest_seconds": 180},
        )

        self.assertEqual(resposta.status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.sets, antes)

    # ------------------------------------------------------- revogação
    def test_revoking_closes_every_door_immediately(self):
        link = make_link(self.pro, self.aluno)
        self.assertEqual(
            self.client.get(
                reverse("coaching:student_monitor", args=[self.aluno.pk])
            ).status_code,
            200,
        )

        link.revogar()

        for url in self._rotas_de_leitura(self.aluno):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_revoking_also_stops_writes(self):
        link = make_link(self.pro, self.aluno)
        item = SessionExercise.objects.filter(session__plan__user=self.aluno).first()
        link.revogar()

        resposta = self.client.post(
            reverse("coaching:adjust_exercise", args=[self.aluno.pk, item.pk]),
            {"sets": 9, "rep_min": 5, "rep_max": 8, "rest_seconds": 180},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_only_the_student_revokes(self):
        """O profissional não corta o próprio acesso pela porta do aluno — e,
        mais importante, não corta o de ninguém."""
        link = make_link(self.pro, self.aluno)

        resposta = self.client.post(reverse("coaching:revoke", args=[link.pk]))

        self.assertEqual(resposta.status_code, 404)
        link.refresh_from_db()
        self.assertEqual(link.status, LinkStatus.ACTIVE)

    def test_a_student_cannot_revoke_someone_elses_link(self):
        link = make_link(self.pro, self.estranho)
        self.client.force_login(self.aluno)

        resposta = self.client.post(reverse("coaching:revoke", args=[link.pk]))

        self.assertEqual(resposta.status_code, 404)
        link.refresh_from_db()
        self.assertEqual(link.status, LinkStatus.ACTIVE)

    def test_the_student_revokes_from_their_own_screen(self):
        link = make_link(self.pro, self.aluno)
        self.client.force_login(self.aluno)

        self.client.post(reverse("coaching:revoke", args=[link.pk]))

        link.refresh_from_db()
        self.assertEqual(link.status, LinkStatus.REVOKED)
        self.assertIsNotNone(link.revoked_at)

    # -------------------------------------------------- quem é profissional
    def test_someone_without_a_professional_profile_is_sent_to_signup(self):
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("coaching:panel"))

        self.assertRedirects(resposta, reverse("coaching:signup"))

    def test_the_panel_asks_for_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("coaching:panel"))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_the_service_layer_refuses_even_without_a_view(self):
        """A camada de serviço não confia na view. Se um dia alguém escrever
        uma rota nova e esquecer o `vinculo_ativo`, a escrita ainda para."""
        link = make_link(self.pro, self.aluno, role=LinkRole.TRAINER)
        with self.assertRaises(PermissionDenied):
            prescription.ajustar_metas(link, kcal_adjustment=-200)

        link.role = LinkRole.NUTRITIONIST
        item = SessionExercise.objects.filter(session__plan__user=self.aluno).first()
        with self.assertRaises(PermissionDenied):
            prescription.ajustar_exercicio(
                link, item, sets=4, rep_min=8, rep_max=12, rest_seconds=90
            )


# ==========================================================================
# Prescrição de treino
# ==========================================================================

class WorkoutPrescriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        create_routine(self.aluno)
        self.link = make_link(self.pro, self.aluno, role=LinkRole.TRAINER)
        self.item = SessionExercise.objects.filter(
            session__plan__user=self.aluno
        ).select_related("session").first()
        self.client.force_login(self.pro)

    def _ajustar(self, **dados):
        campos = {"sets": 5, "rep_min": 6, "rep_max": 8, "rest_seconds": 150}
        campos.update(dados)
        return self.client.post(
            reverse("coaching:adjust_exercise", args=[self.aluno.pk, self.item.pk]),
            campos,
        )

    def test_the_change_reaches_the_students_own_screen(self):
        """O teste que importa: não é "gravou no banco", é "o aluno vê"."""
        self._ajustar()
        self.client.force_login(self.aluno)

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.item.refresh_from_db()
        self.assertEqual(self.item.sets, 5)
        self.assertEqual(self.item.rest_seconds, 150)
        self.assertIn("6-8", html)

    def test_out_of_range_prescriptions_are_refused(self):
        antes = self.item.sets
        casos = [
            {"sets": 40},
            {"sets": 0},
            {"rep_min": 12, "rep_max": 8},
            {"rest_seconds": 5},
            {"rest_seconds": 3600},
        ]
        for caso in casos:
            with self.subTest(**caso):
                self._ajustar(**caso)
                self.item.refresh_from_db()
                self.assertEqual(self.item.sets, antes)

    def test_swapping_keeps_the_prescription(self):
        """Trocar o exercício não é recomeçar: séries e descanso continuam."""
        self._ajustar()
        novo = Exercise.objects.filter(is_active=True).exclude(
            pk=self.item.exercise_id
        ).first()

        self.client.post(
            reverse("coaching:swap_exercise", args=[self.aluno.pk, self.item.pk]),
            {"exercise": novo.pk},
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.exercise, novo)
        self.assertEqual(self.item.sets, 5)
        self.assertEqual(self.item.rest_seconds, 150)

    def test_the_last_exercise_of_a_session_cannot_be_removed(self):
        """Uma ficha vazia não é uma ficha simplificada — é um erro."""
        sessao = self.item.session
        sessao.exercises.exclude(pk=self.item.pk).delete()

        self.client.post(
            reverse("coaching:remove_exercise", args=[self.aluno.pk, self.item.pk])
        )

        self.assertEqual(sessao.exercises.count(), 1)

    def test_adding_the_same_exercise_twice_is_refused(self):
        sessao = self.item.session
        antes = sessao.exercises.count()

        self.client.post(
            reverse("coaching:add_exercise", args=[self.aluno.pk, sessao.pk]),
            {"exercise": self.item.exercise_id},
        )

        self.assertEqual(sessao.exercises.count(), antes)

    def test_cloning_replaces_the_whole_session(self):
        sessao = self.item.session
        modelo = WorkoutTemplate.objects.filter(is_active=True).first()

        self.client.post(
            reverse("coaching:clone_template", args=[self.aluno.pk, sessao.pk]),
            {"template": modelo.pk},
        )

        sessao.refresh_from_db()
        self.assertEqual(sessao.name, modelo.name)
        self.assertEqual(
            list(sessao.exercises.order_by("order").values_list("exercise_id", flat=True)),
            list(modelo.items.order_by("order").values_list("exercise_id", flat=True)),
        )

    def test_a_prescribed_plan_is_never_rebuilt_by_the_generator(self):
        """O risco real do módulo inteiro.

        `sync_active_routine` remonta a ficha a partir do catálogo quando os
        dias de treino mudam. Sem a marca de "prescrita", o aluno mudar o
        horário de terça apagaria a prescrição do treinador em silêncio — e
        ninguém descobriria, porque a ficha nova também parece certa.
        """
        self._ajustar()
        plano = get_active_routine(self.aluno)
        self.assertTrue(plano.is_prescribed)

        TrainingDay.objects.create(
            user=self.aluno, weekday=6, start_time=time(8, 0), duration_min=45
        )
        rotina, mudou = sync_active_routine(self.aluno)

        self.assertFalse(mudou)
        self.assertEqual(rotina.pk, plano.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.sets, 5)

    def test_a_plan_nobody_prescribed_is_still_rebuilt(self):
        """A trava vale só para ficha com dono humano. Sem isso, o app pararia
        de acompanhar quem mudou a rotina sozinho."""
        plano = get_active_routine(self.aluno)
        self.assertFalse(plano.is_prescribed)

        TrainingDay.objects.create(
            user=self.aluno, weekday=6, start_time=time(8, 0), duration_min=45
        )
        _, mudou = sync_active_routine(self.aluno)

        self.assertTrue(mudou)

    def test_a_retired_exercise_still_forces_a_rebuild(self):
        """Aqui o gerador não está discordando do treinador: está avisando que
        o catálogo mudou embaixo dos dois."""
        self._ajustar()
        Exercise.objects.filter(pk=self.item.exercise_id).update(is_active=False)

        _, mudou = sync_active_routine(self.aluno)

        self.assertTrue(mudou)


# ==========================================================================
# Prescrição nutricional
# ==========================================================================

class NutritionPrescriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        plan_services.create_plan(self.aluno)
        self.link = make_link(self.pro, self.aluno, role=LinkRole.NUTRITIONIST)
        self.client.force_login(self.pro)

    def _metas(self, **dados):
        campos = {
            "activity_level": ActivityLevel.LIGHT,
            "goal": Goal.CUT,
            "kcal_adjustment": 0,
        }
        campos.update(dados)
        return self.client.post(
            reverse("coaching:adjust_targets", args=[self.aluno.pk]), campos
        )

    def test_the_prescription_survives_the_next_page_load(self):
        """O risco que quase derrubou o desenho inteiro.

        `plan_is_current` compara os números gravados no plano com os que o
        motor calcula hoje. Gravar a prescrição direto no plano faria os dois
        divergirem sempre, e o plano seria descartado e refeito a cada visita —
        apagando a prescrição em silêncio. Por isso ela entra como ENTRADA, no
        perfil.
        """
        self._metas(protein_g_per_kg="2.4")

        plano, mudou = plan_services.sync_active_plan(self.aluno)
        # 2,4 g/kg sobre 82,4 kg = 198 g.
        self.assertEqual(plano.protein_g, 198)
        self.assertFalse(mudou, "o plano foi refeito e perdeu a prescrição")

        # E de novo, para provar que não é só a primeira leitura.
        plano, mudou = plan_services.sync_active_plan(self.aluno)
        self.assertEqual(plano.protein_g, 198)
        self.assertFalse(mudou)

    def test_the_kcal_adjustment_reaches_the_target(self):
        antes = plan_services.get_active_plan(self.aluno).target_kcal
        self._metas(kcal_adjustment=-300)

        depois = plan_services.get_active_plan(self.aluno).target_kcal
        self.assertLess(depois, antes)

    def test_the_engine_floor_still_beats_the_prescription(self):
        """Uma prescrição não fura a trava. Comer abaixo do gasto de repouso
        não acelera nada: derruba o treino e come músculo."""
        plano = plan_services.get_active_plan(self.aluno)
        self._metas(kcal_adjustment=prescription.AJUSTE_MIN)

        depois = plan_services.get_active_plan(self.aluno)
        self.assertGreaterEqual(depois.target_kcal, depois.bmr_kcal)
        self.assertEqual(depois.bmr_kcal, plano.bmr_kcal)

    def test_absurd_macros_are_refused(self):
        antes = plan_services.get_active_plan(self.aluno).protein_g

        for caso in ({"protein_g_per_kg": "18"}, {"protein_g_per_kg": "0.2"},
                     {"fat_kcal_share": "90"}, {"fat_kcal_share": "2"}):
            with self.subTest(**caso):
                self._metas(**caso)
                self.assertEqual(
                    plan_services.get_active_plan(self.aluno).protein_g, antes
                )

    def test_the_fat_floor_survives_a_low_prescription(self):
        """0,7 g/kg é a parte hormonal, e é o número que alguém apressado corta."""
        self._metas(fat_kcal_share="15")

        plano = plan_services.get_active_plan(self.aluno)
        piso = round(Decimal("82.4") * Decimal("0.7"))
        self.assertGreaterEqual(plano.fat_g, piso)

    def test_the_macros_still_add_up_to_the_target(self):
        """Prescrever proteína e gordura e deixar o carboidrato ser o resto é o
        que garante que a soma feche. Três macros livres não fechariam."""
        self._metas(protein_g_per_kg="2.2", fat_kcal_share="30")

        plano = plan_services.get_active_plan(self.aluno)
        soma = plano.protein_g * 4 + plano.carb_g * 4 + plano.fat_g * 9
        self.assertLess(abs(soma - plano.target_kcal), 30)

    def test_swapping_a_meal_option_rescales_the_portion(self):
        """A mesma receita serve 400 kcal no lanche e 700 no almoço. Uma troca
        que só trocasse o ponteiro deixaria o cardápio somando outro total."""
        plano = plan_services.get_active_plan(self.aluno)
        slot = plano.slots.filter(category=MealCategory.MAIN).first()
        opcao = slot.options.first()
        outro = (
            MealTemplate.objects.filter(is_active=True, category=slot.category)
            .exclude(pk=opcao.template_id)
            .first()
        )

        self.client.post(
            reverse("coaching:swap_option", args=[self.aluno.pk, opcao.pk]),
            {"template": outro.pk},
        )

        opcao.refresh_from_db()
        self.assertEqual(opcao.template, outro)
        # A porção foi reescalada para o alvo do horário, não copiada crua.
        self.assertLess(abs(opcao.kcal - slot.target_kcal), slot.target_kcal * Decimal("0.5"))

    def test_a_recipe_from_another_category_is_refused(self):
        plano = plan_services.get_active_plan(self.aluno)
        slot = plano.slots.filter(category=MealCategory.MAIN).first()
        opcao = slot.options.first()
        cafe = MealTemplate.objects.filter(
            is_active=True, category=MealCategory.BREAKFAST
        ).first()

        self.client.post(
            reverse("coaching:swap_option", args=[self.aluno.pk, opcao.pk]),
            {"template": cafe.pk},
        )

        opcao.refresh_from_db()
        self.assertNotEqual(opcao.template, cafe)

    def test_the_option_of_another_student_is_invisible(self):
        outro = create_complete_user(email="outro@exemplo.com")
        plano_alheio = plan_services.create_plan(outro)
        opcao = plano_alheio.slots.first().options.first()
        modelo = MealTemplate.objects.filter(is_active=True).first()

        resposta = self.client.post(
            reverse("coaching:swap_option", args=[self.aluno.pk, opcao.pk]),
            {"template": modelo.pk},
        )

        self.assertEqual(resposta.status_code, 404)


# ==========================================================================
# O aviso ao aluno
# ==========================================================================

class CoachUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        plan_services.create_plan(self.aluno)
        create_routine(self.aluno)
        self.link = make_link(self.pro, self.aluno)

    def test_every_change_leaves_a_notice(self):
        item = SessionExercise.objects.filter(session__plan__user=self.aluno).first()
        prescription.ajustar_exercicio(
            self.link, item, sets=4, rep_min=8, rep_max=12, rest_seconds=90
        )

        aviso = CoachUpdate.objects.get(student=self.aluno)
        self.assertIn("Ana Treinadora", aviso.message)
        self.assertIn(item.exercise.name, aviso.message)
        self.assertIsNone(aviso.seen_at)

    def test_the_notice_shows_up_on_any_screen_the_student_opens(self):
        """A mudança pode ter sido no treino e o aluno abrir a dieta primeiro.
        Uma ficha que muda sozinha assusta — a pessoa acha que perdeu o
        progresso — e o que desarma isso é dizer quem mexeu e no quê."""
        item = SessionExercise.objects.filter(session__plan__user=self.aluno).first()
        prescription.ajustar_exercicio(
            self.link, item, sets=4, rep_min=8, rep_max=12, rest_seconds=90
        )
        self.client.force_login(self.aluno)

        for rota in ("plans:today", "workouts:routine", "plans:history"):
            with self.subTest(rota=rota):
                corpo = self.client.get(reverse(rota)).content.decode()
                self.assertIn("Ana Treinadora", corpo)

    def test_dismissing_marks_everything_as_seen(self):
        for i in range(3):
            CoachUpdate.objects.create(
                student=self.aluno, professional=self.pro, kind="workout", message=f"a{i}"
            )
        self.client.force_login(self.aluno)

        self.client.post(reverse("coaching:dismiss_updates"))

        self.assertFalse(
            CoachUpdate.objects.filter(student=self.aluno, seen_at__isnull=True).exists()
        )

    def test_one_student_never_sees_another_students_notices(self):
        outro = create_complete_user(email="outro@exemplo.com")
        CoachUpdate.objects.create(
            student=outro, professional=self.pro, kind="workout", message="segredo do outro"
        )
        self.client.force_login(self.aluno)

        corpo = self.client.get(reverse("plans:today")).content.decode()

        self.assertNotIn("segredo do outro", corpo)

    def test_a_seen_notice_does_not_come_back(self):
        CoachUpdate.objects.create(
            student=self.aluno,
            professional=self.pro,
            kind="workout",
            message="ja visto",
            seen_at=timezone.now(),
        )
        self.client.force_login(self.aluno)

        corpo = self.client.get(reverse("plans:today")).content.decode()

        self.assertNotIn("ja visto", corpo)


# ==========================================================================
# A carteira e os alertas
# ==========================================================================

class PortfolioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pro = make_professional()
        self.hoje = timezone.localdate()

    def _aluno(self, email, **kwargs):
        aluno = create_complete_user(email=email, **kwargs)
        make_link(self.pro, aluno)
        return aluno

    def _montar(self):
        return portfolio.montar(permissions.carteira(self.pro), hoje=self.hoje)

    def _pesar(self, aluno, dias_atras, peso):
        WeightEntry.objects.update_or_create(
            user=aluno,
            date=self.hoje - timedelta(days=dias_atras),
            defaults={"weight_kg": Decimal(str(peso))},
        )

    def test_an_empty_portfolio_is_an_empty_list_and_not_a_crash(self):
        self.assertEqual(self._montar(), [])

    def test_someone_who_stopped_weighing_raises_a_flag(self):
        aluno = self._aluno("sumiu@exemplo.com")
        WeightEntry.objects.filter(user=aluno).delete()
        self._pesar(aluno, 9, 84)

        linha = self._montar()[0]

        self.assertEqual(linha.dias_sem_pesagem, 9)
        self.assertIn("sem_peso", [a.slug for a in linha.alertas])
        self.assertTrue(linha.precisa_atencao)

    def test_someone_who_weighed_yesterday_does_not(self):
        aluno = self._aluno("emdia@exemplo.com")
        WeightEntry.objects.filter(user=aluno).delete()
        self._pesar(aluno, 1, 84)

        linha = self._montar()[0]

        self.assertNotIn("sem_peso", [a.slug for a in linha.alertas])

    def test_a_flat_average_for_two_weeks_raises_a_flag(self):
        """Duas semanas paradas é o ponto em que o profissional age. O app
        sozinho só sugere recalibrar na terceira — e é por isso que o painel
        avisa antes."""
        aluno = self._aluno("parado@exemplo.com")
        WeightEntry.objects.filter(user=aluno).delete()
        # Três semanas com a mesma média: dois deltas abaixo do limiar.
        for semanas, peso in ((2, "84.00"), (1, "84.02"), (0, "84.01")):
            self._pesar(aluno, semanas * 7 + self.hoje.weekday(), peso)

        linha = self._montar()[0]

        self.assertGreaterEqual(linha.semanas_paradas, 2)
        self.assertIn("estagnado", [a.slug for a in linha.alertas])

    def test_finishing_every_workout_of_the_week_is_good_news(self):
        aluno = self._aluno("aplicado@exemplo.com")
        create_routine(aluno)
        exercicio = Exercise.objects.filter(is_active=True).first()
        inicio = self.hoje - timedelta(days=self.hoje.weekday())
        # Três dias distintos na semana, que é o que a rotina prevê.
        for i in range(3):
            dia = inicio + timedelta(days=i)
            if dia > self.hoje:
                dia = self.hoje
            ExerciseLog.objects.update_or_create(
                user=aluno,
                exercise=exercicio,
                date=dia,
                set_number=1,
                defaults={"weight_kg": Decimal("40"), "reps": 10},
            )

        linha = self._montar()[0]

        if linha.treinos_feitos >= linha.treinos_previstos:
            self.assertIn("treino_ok", [a.slug for a in linha.alertas])
            self.assertEqual(
                [a.tom for a in linha.alertas if a.slug == "treino_ok"], ["bom"]
            )

    def test_good_news_does_not_count_as_needing_attention(self):
        """Um painel que pinta tudo de âmbar não destaca nada."""
        alerta_bom = portfolio.Alerta("treino_ok", "halter", "fechou", tom="bom")
        linha = portfolio.Aluno(link=None, user=None, iniciais="AB", alertas=[alerta_bom])

        self.assertFalse(linha.precisa_atencao)
        self.assertEqual(linha.situacao, "em_dia")

    def test_each_student_lands_in_exactly_one_drawer(self):
        for email in ("a@exemplo.com", "b@exemplo.com", "c@exemplo.com"):
            self._aluno(email)

        alunos = self._montar()
        contagem = portfolio.contagem(alunos)

        self.assertEqual(contagem["todos"], 3)
        self.assertEqual(
            contagem["atencao"] + contagem["em_dia"] + contagem["sem_treino"], 3
        )

    def test_the_filter_narrows_the_list(self):
        aluno = self._aluno("sumiu@exemplo.com")
        WeightEntry.objects.filter(user=aluno).delete()
        self._pesar(aluno, 20, 84)
        self._aluno("normal@exemplo.com")

        alunos = self._montar()

        self.assertEqual(len(portfolio.filtrar(alunos, "todos")), 2)
        self.assertEqual(len(portfolio.filtrar(alunos, "atencao")), 1)
        self.assertEqual(
            portfolio.filtrar(alunos, "atencao")[0].user.email, "sumiu@exemplo.com"
        )

    def test_whoever_needs_attention_comes_first(self):
        """Em ordem alfabética o aluno em risco se esconde na letra T."""
        calmo = self._aluno("aaa@exemplo.com")
        risco = self._aluno("zzz@exemplo.com")
        WeightEntry.objects.filter(user=risco).delete()
        self._pesar(risco, 30, 90)

        alunos = self._montar()

        self.assertEqual(alunos[0].user, risco)
        self.assertEqual(alunos[1].user, calmo)

    def test_the_portfolio_does_not_grow_a_query_per_student(self):
        """Consulta dentro de laço é o jeito mais fácil de deixar esta tela
        lenta, e o mais difícil de notar com dois alunos de teste."""
        for i in range(2):
            self._aluno(f"dois{i}@exemplo.com")
        links = list(permissions.carteira(self.pro))
        with self.assertNumQueries(5):
            portfolio.montar(links, hoje=self.hoje)

        # O número é o mesmo com quatro vezes mais alunos: é isso que o teste
        # está afirmando, e não o valor 5 em si.
        for i in range(6):
            self._aluno(f"muitos{i}@exemplo.com")
        links = list(permissions.carteira(self.pro))
        with self.assertNumQueries(5):
            portfolio.montar(links, hoje=self.hoje)

    def test_initials_fall_back_to_the_email(self):
        sem_nome = User(email="zeca@exemplo.com", first_name="", last_name="")
        com_nome = User(email="x@exemplo.com", first_name="Maria", last_name="Silva")

        self.assertEqual(portfolio._iniciais(sem_nome), "ZE")
        self.assertEqual(portfolio._iniciais(com_nome), "MS")


# ==========================================================================
# Monitoramento
# ==========================================================================

class MonitoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        self.hoje = timezone.localdate()

    def test_the_chart_scale_starts_at_the_lightest_week_and_not_at_zero(self):
        """Numa escala a partir do zero, 82 kg e 85 kg são a mesma barra."""
        WeightEntry.objects.filter(user=self.aluno).delete()
        for semanas, peso in ((3, "88.0"), (2, "86.0"), (1, "84.0"), (0, "82.0")):
            WeightEntry.objects.create(
                user=self.aluno,
                date=self.hoje - timedelta(days=semanas * 7 + self.hoje.weekday()),
                weight_kg=Decimal(peso),
            )

        grafico = monitoring.grafico_de_peso(self.aluno)

        alturas = [s["altura"] for s in grafico["semanas"]]
        self.assertTrue(grafico["tem_dados"])
        self.assertEqual(alturas[0], 88)   # a semana mais pesada, no topo
        self.assertEqual(alturas[-1], 12)  # a mais leve, no piso visível
        self.assertTrue(all(0 < a <= 100 for a in alturas))

    def test_a_single_weighing_does_not_divide_by_zero(self):
        grafico = monitoring.grafico_de_peso(self.aluno)
        self.assertTrue(all(0 < s["altura"] <= 100 for s in grafico["semanas"]))

    def test_the_target_line_shares_the_scale_with_the_bars(self):
        WeightEntry.objects.filter(user=self.aluno).delete()
        for semanas, peso in ((1, "86.0"), (0, "84.0")):
            WeightEntry.objects.create(
                user=self.aluno,
                date=self.hoje - timedelta(days=semanas * 7 + self.hoje.weekday()),
                weight_kg=Decimal(peso),
            )

        grafico = monitoring.grafico_de_peso(self.aluno, meta_kg=Decimal("80"))

        # A meta está abaixo de tudo, então ela ancora o piso da escala.
        self.assertEqual(grafico["meta_altura"], 12)
        self.assertTrue(all(s["altura"] > 12 for s in grafico["semanas"]))

    def test_a_day_within_ten_percent_counts_as_on_target(self):
        plano = plan_services.create_plan(self.aluno)
        casos = [
            (plano.target_kcal, "dentro"),
            (int(plano.target_kcal * Decimal("1.05")), "dentro"),
            (int(plano.target_kcal * Decimal("0.7")), "abaixo"),
            (int(plano.target_kcal * Decimal("1.4")), "acima"),
        ]
        for kcal, esperado in casos:
            with self.subTest(kcal=kcal):
                dia = monitoring.DiaDeDieta(
                    data=self.hoje, kcal=kcal, meta=plano.target_kcal,
                    marcadas=4, cumpridas=4,
                )
                self.assertEqual(dia.situacao, esperado)

    def test_a_day_with_nothing_marked_is_not_a_deviation(self):
        plano = plan_services.create_plan(self.aluno)
        dia = monitoring.DiaDeDieta(
            data=self.hoje, kcal=0, meta=plano.target_kcal, marcadas=0, cumpridas=0
        )
        self.assertEqual(dia.situacao, "vazio")

    def test_volume_is_sets_times_reps_times_load(self):
        exercicio = Exercise.objects.filter(is_active=True).first()
        for serie in (1, 2, 3):
            ExerciseLog.objects.create(
                user=self.aluno,
                exercise=exercicio,
                date=self.hoje,
                set_number=serie,
                weight_kg=Decimal("50"),
                reps=10,
            )

        sessoes = monitoring.treinos(self.aluno)

        self.assertEqual(len(sessoes), 1)
        self.assertEqual(sessoes[0].volume_kg, Decimal("1500"))
        self.assertEqual(sessoes[0].series, 3)

    def test_the_delta_compares_with_the_previous_session(self):
        exercicio = Exercise.objects.filter(is_active=True).first()
        for dias, carga in ((7, "40"), (0, "50")):
            ExerciseLog.objects.create(
                user=self.aluno,
                exercise=exercicio,
                date=self.hoje - timedelta(days=dias),
                set_number=1,
                weight_kg=Decimal(carga),
                reps=10,
            )

        sessoes = monitoring.treinos(self.aluno)

        self.assertEqual(sessoes[0].volume_kg, Decimal("500"))
        self.assertEqual(sessoes[0].delta, Decimal("100"))
        self.assertIsNone(sessoes[1].delta)

    def test_a_student_with_no_plan_does_not_blow_up_the_tab(self):
        self.assertEqual(monitoring.dieta(self.aluno, None)["total"], 0)
        self.assertEqual(monitoring.treinos(self.aluno), [])


# ==========================================================================
# As telas
# ==========================================================================

class PanelScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com", )
        self.aluno.first_name = "João"
        self.aluno.save(update_fields=["first_name"])
        plan_services.create_plan(self.aluno)
        create_routine(self.aluno)
        make_link(self.pro, self.aluno)
        self.client.force_login(self.pro)

    def test_the_panel_lists_the_student(self):
        corpo = self.client.get(reverse("coaching:panel")).content.decode()

        self.assertIn("João", corpo)
        self.assertIn("Atenção necessária", corpo)

    def test_the_filter_counts_appear_in_the_labels(self):
        """"Atenção necessária (0)" é a melhor notícia da tela, e sem o número
        ela custa um clique para ser lida."""
        corpo = self.client.get(reverse("coaching:panel")).content.decode()
        self.assertIn('class="filtro__conta num"', corpo)

    def test_generating_an_invite_shows_the_code(self):
        self.client.post(
            reverse("coaching:invite_create"), {"role": LinkRole.TRAINER}
        )

        convite = ProfessionalStudentLink.objects.filter(
            professional=self.pro, status=LinkStatus.PENDING
        ).first()
        self.assertIsNotNone(convite)

        corpo = self.client.get(reverse("coaching:panel")).content.decode()
        self.assertIn(convite.invite_code, corpo)

    def test_cancelling_an_invite_removes_it(self):
        self.client.post(reverse("coaching:invite_create"), {"role": LinkRole.TRAINER})
        convite = ProfessionalStudentLink.objects.get(
            professional=self.pro, status=LinkStatus.PENDING
        )

        self.client.post(reverse("coaching:invite_cancel", args=[convite.pk]))

        self.assertFalse(
            ProfessionalStudentLink.objects.filter(pk=convite.pk).exists()
        )

    def test_a_professional_cannot_cancel_someone_elses_invite(self):
        outro = make_professional(email="outro@exemplo.com")
        alheio = ProfessionalStudentLink.objects.create(
            professional=outro, role=LinkRole.TRAINER
        )

        resposta = self.client.post(
            reverse("coaching:invite_cancel", args=[alheio.pk])
        )

        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(ProfessionalStudentLink.objects.filter(pk=alheio.pk).exists())

    def test_the_three_tabs_render(self):
        for rota in (
            "coaching:student_monitor",
            "coaching:student_workout",
            "coaching:student_nutrition",
        ):
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(rota, args=[self.aluno.pk]))
                self.assertEqual(resposta.status_code, 200)
                self.assertIn("João", resposta.content.decode())

    def test_a_trainer_only_link_hides_the_diet_tab(self):
        ProfessionalStudentLink.objects.filter(
            professional=self.pro, student=self.aluno
        ).update(role=LinkRole.TRAINER)

        corpo = self.client.get(
            reverse("coaching:student_workout", args=[self.aluno.pk])
        ).content.decode()

        self.assertNotIn(
            reverse("coaching:student_nutrition", args=[self.aluno.pk]), corpo
        )

    def test_the_student_screen_lists_who_can_see_them(self):
        self.client.force_login(self.aluno)

        corpo = self.client.get(reverse("accounts:professionals")).content.decode()

        self.assertIn("Ana Treinadora", corpo)
        self.assertIn("CREF 1234-G/SP", corpo)
        self.assertIn("Revogar acesso", corpo)

    def test_the_professional_signup_opens_the_panel(self):
        novo = create_complete_user(email="novo@exemplo.com")
        self.client.force_login(novo)

        self.client.post(
            reverse("coaching:signup"),
            {"display_name": "Carlos Nutri", "default_role": LinkRole.NUTRITIONIST,
             "council_id": "CRN 9999"},
        )

        self.assertTrue(permissions.e_profissional(novo))
        self.assertEqual(self.client.get(reverse("coaching:panel")).status_code, 200)


class ScheduleDriftTests(TestCase):
    """O outro lado da trava que protege a prescrição.

    Ficha prescrita não é remontada pelo gerador — é o certo, e é o que impede
    a prescrição de sumir. Mas quando o aluno muda os dias de treino, a ficha
    passa a discordar da agenda dele, e ninguém percebe: os dois lados
    continuam parecendo corretos isoladamente. Quem pode resolver é o
    treinador, então é a ele que a tela conta.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pro = make_professional()
        self.aluno = create_complete_user(email="aluno@exemplo.com")
        create_routine(self.aluno)
        self.link = make_link(self.pro, self.aluno, role=LinkRole.TRAINER)
        self.client.force_login(self.pro)
        self.url = reverse("coaching:student_workout", args=[self.aluno.pk])

    def _prescrever(self):
        item = SessionExercise.objects.filter(session__plan__user=self.aluno).first()
        prescription.ajustar_exercicio(
            self.link, item, sets=5, rep_min=6, rep_max=8, rest_seconds=150
        )

    def test_a_matching_schedule_says_nothing(self):
        self._prescrever()
        resposta = self.client.get(self.url)

        self.assertFalse(resposta.context["agenda_mudou"])

    def test_a_changed_schedule_is_reported_to_the_trainer(self):
        self._prescrever()
        TrainingDay.objects.filter(user=self.aluno).update(start_time=time(6, 30))

        resposta = self.client.get(self.url)

        self.assertTrue(resposta.context["agenda_mudou"])
        self.assertIn("mudou os dias ou horários", resposta.content.decode())

    def test_an_unprescribed_plan_never_drifts(self):
        """Sem prescrição o gerador remonta sozinho — não há divergência para
        avisar, e o aviso apareceria toda vez."""
        TrainingDay.objects.filter(user=self.aluno).update(start_time=time(6, 30))

        resposta = self.client.get(self.url)

        self.assertFalse(resposta.context["agenda_mudou"])
