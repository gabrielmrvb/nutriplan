"""Testes do catálogo de suplementos e do checklist de um toque."""
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans.tests import create_complete_user

from .models import Supplement, SupplementLog, Unit
from .views import checklist


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_supplements", verbosity=0)

    def test_the_six_supplements_are_there(self):
        esperados = {
            "creatina", "whey", "beta-alanina",
            "omega-3", "multivitaminico", "pre-treino",
        }
        self.assertEqual(
            set(Supplement.objects.values_list("slug", flat=True)), esperados
        )

    def test_seeding_twice_does_not_duplicate(self):
        call_command("seed_supplements", verbosity=0)
        self.assertEqual(Supplement.objects.count(), 6)

    def test_something_dropped_from_the_file_is_retired_and_not_deleted(self):
        """Apagar levaria junto todo registro de quem já tomou aquilo."""
        extra = Supplement.objects.create(
            slug="inventado", name="Inventado", purpose="x", is_active=True
        )
        SupplementLog.objects.create(
            user=create_complete_user(), supplement=extra
        )

        call_command("seed_supplements", verbosity=0)

        extra.refresh_from_db()
        self.assertFalse(extra.is_active)
        self.assertEqual(SupplementLog.objects.filter(supplement=extra).count(), 1)

    def test_every_supplement_says_what_it_is_for(self):
        for item in Supplement.objects.all():
            with self.subTest(nome=item.name):
                self.assertTrue(item.purpose)
                self.assertTrue(item.attributes)
                self.assertTrue(item.timing)

    def test_every_supplement_carries_a_myth_and_the_fact(self):
        """O mito não é enfeite: quase todo suplemento desta lista carrega uma
        crença errada mais popular que a informação certa."""
        for item in Supplement.objects.all():
            with self.subTest(nome=item.name):
                self.assertTrue(item.myth)
                self.assertTrue(item.fact)

    def test_the_ones_that_need_a_caution_carry_one(self):
        """Creatina e ômega-3 têm ressalva específica — rim e anticoagulante."""
        for slug in ("creatina", "omega-3", "pre-treino"):
            with self.subTest(slug=slug):
                self.assertTrue(Supplement.objects.get(slug=slug).caution)


class DoseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_supplements", verbosity=0)

    def test_a_per_kilo_dose_scales_with_the_person(self):
        creatina = Supplement.objects.get(slug="creatina")
        # 0,03 g/kg × 82,4 kg = 2,47 → arredonda para 2,5.
        self.assertEqual(creatina.dose_para(Decimal("82.4")), Decimal("2.5"))
        self.assertEqual(creatina.dose_para(Decimal("100")), Decimal("3"))

    def test_the_dose_is_rounded_to_something_a_scoop_can_measure(self):
        """Ninguém pesa creatina em balança de precisão: a dosadora tem 5 g e a
        colher de chá, cerca de 3. "4,63 g" seria exato e inútil."""
        creatina = Supplement.objects.get(slug="creatina")
        for peso in (70, 75, 82, 91, 103):
            with self.subTest(peso=peso):
                valor = creatina.dose_para(Decimal(peso))
                self.assertEqual((valor * 2) % 1, 0, f"{valor} não é múltiplo de 0,5")

    def test_a_milligram_dose_rounds_to_tens(self):
        pre = Supplement.objects.get(slug="pre-treino")
        # 4 mg/kg × 82,4 = 329,6 → 330.
        self.assertEqual(pre.dose_para(Decimal("82.4")), 330)

    def test_a_fixed_dose_ignores_the_weight(self):
        omega = Supplement.objects.get(slug="omega-3")
        self.assertEqual(
            omega.dose_para(Decimal("60")), omega.dose_para(Decimal("120"))
        )

    def test_without_a_weight_the_per_kilo_dose_does_not_invent_a_number(self):
        creatina = Supplement.objects.get(slug="creatina")
        self.assertIsNone(creatina.dose_para(None))
        self.assertEqual(creatina.dose_display(None), "conforme o rótulo")

    def test_a_whole_dose_does_not_print_its_decimal_places(self):
        """Decimal guarda as casas significativas e imprime todas: "1.00 dose"
        é o que sai de um campo declarado com duas casas."""
        multi = Supplement.objects.get(slug="multivitaminico")
        self.assertEqual(multi.dose_display(80), "1 dose")

    def test_the_unit_shows_up_in_the_text(self):
        self.assertIn("g", Supplement.objects.get(slug="creatina").dose_display(80))
        self.assertIn("mg", Supplement.objects.get(slug="pre-treino").dose_display(80))
        self.assertIn(
            "dose", Supplement.objects.get(slug="multivitaminico").dose_display(80)
        )


class ChecklistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_supplements", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.creatina = Supplement.objects.get(slug="creatina")
        self.client.force_login(self.user)

    def _marcar(self, suplemento=None):
        return self.client.post(
            reverse("supplements:toggle", args=[(suplemento or self.creatina).pk])
        )

    def test_one_tap_marks_it(self):
        self._marcar()

        self.assertTrue(
            SupplementLog.objects.filter(
                user=self.user, supplement=self.creatina, date=timezone.localdate()
            ).exists()
        )

    def test_another_tap_unmarks_it(self):
        """Sem desfazer, o único caminho de volta de um toque errado seria o
        admin."""
        self._marcar()
        self._marcar()

        self.assertFalse(SupplementLog.objects.filter(user=self.user).exists())

    def test_marking_twice_never_creates_two_rows(self):
        SupplementLog.objects.create(
            user=self.user, supplement=self.creatina, date=timezone.localdate()
        )
        self._marcar()  # desmarca
        self._marcar()  # marca de novo

        self.assertEqual(SupplementLog.objects.filter(user=self.user).count(), 1)

    def test_the_checklist_reports_the_state(self):
        linhas = {l["supplement"].slug: l for l in checklist(self.user)}
        self.assertFalse(linhas["creatina"]["tomado"])

        self._marcar()

        linhas = {l["supplement"].slug: l for l in checklist(self.user)}
        self.assertTrue(linhas["creatina"]["tomado"])

    def test_the_checklist_carries_the_dose_for_this_person(self):
        linhas = {l["supplement"].slug: l for l in checklist(self.user)}
        # O usuário de teste pesa 82,4 kg.
        # Vírgula, como o resto do app: o campo de carga ao lado mostra "62,50".
        self.assertEqual(linhas["creatina"]["dose"], "2,5 g")

    def test_a_retired_supplement_leaves_the_checklist(self):
        Supplement.objects.filter(slug="creatina").update(is_active=False)
        slugs = [l["supplement"].slug for l in checklist(self.user)]
        self.assertNotIn("creatina", slugs)

    def test_one_person_never_marks_for_another(self):
        outro = create_complete_user(email="outro@exemplo.com")
        self._marcar()

        self.assertFalse(SupplementLog.objects.filter(user=outro).exists())

    def test_marking_a_retired_supplement_is_refused(self):
        Supplement.objects.filter(slug="creatina").update(is_active=False)

        resposta = self._marcar()

        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(SupplementLog.objects.filter(user=self.user).exists())

    def test_it_asks_for_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("supplements:list"))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])


class SupplementScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_supplements", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_the_tab_lists_everything_with_dose_and_myth(self):
        html = self.client.get(reverse("supplements:list")).content.decode()

        for item in Supplement.objects.filter(is_active=True):
            with self.subTest(nome=item.name):
                self.assertIn(item.name, html)
                self.assertIn(item.myth, html)

    def test_the_disclaimer_comes_before_the_first_dose(self):
        """Um aviso depois de seis cartões de dose é um aviso que ninguém leu."""
        html = self.client.get(reverse("supplements:list")).content.decode()

        aviso = html.index("não é prescrição")
        primeiro = html.index("Dose")
        self.assertLess(aviso, primeiro)

    def test_the_bottom_bar_reaches_the_tab(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn(reverse("supplements:list"), html)
