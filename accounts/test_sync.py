"""Testes da trava de repetição que torna a fila offline segura.

O problema que ela resolve, em uma frase: **duas das quatro escritas do app não
são idempotentes**. Água soma (`ml + ml`), suplemento alterna. Uma fila que
reenvia o que ficou parado offline reenviaria essas duas também — e reenviar
"+500 ml" duas vezes registra um litro que ninguém bebeu, sem erro nenhum
aparecer.

A correção não é "tentar reenviar só uma vez": rede não dá essa garantia. É o
servidor lembrar quais operações já aplicou, por um identificador que o cliente
gera ANTES de enviar. Reenvio vira consulta.

Estes testes vêm antes da implementação de propósito. O modo de falhar aqui é
silencioso — o número fica errado e continua parecendo certo — e é exatamente
o tipo de coisa que só um teste pega.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans.models import HydrationLog
from plans.tests import CatalogFixture, create_complete_user
from supplements.models import Supplement, SupplementLog

from .models import SyncedOperation


class SyncedOperationTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()

    def test_the_first_time_an_operation_is_seen_it_is_new(self):
        self.assertFalse(SyncedOperation.ja_aplicada(self.user, "abc-123"))

    def test_the_second_time_it_is_a_replay(self):
        SyncedOperation.ja_aplicada(self.user, "abc-123")
        self.assertTrue(SyncedOperation.ja_aplicada(self.user, "abc-123"))

    def test_an_empty_id_is_never_treated_as_a_replay(self):
        """Sem identificador não há como saber se repetiu. Tratar o vazio como
        repetição travaria toda escrita que vem da tela normal, que não manda
        identificador nenhum."""
        for vazio in ("", None, "   "):
            with self.subTest(valor=repr(vazio)):
                self.assertFalse(SyncedOperation.ja_aplicada(self.user, vazio))
                self.assertFalse(SyncedOperation.ja_aplicada(self.user, vazio))

    def test_two_people_can_use_the_same_id(self):
        """O identificador é gerado no aparelho. Dois aparelhos podem sortear
        o mesmo — e a trava é por pessoa, não global."""
        outro = create_complete_user(email="outro@exemplo.com")

        self.assertFalse(SyncedOperation.ja_aplicada(self.user, "mesmo-id"))
        self.assertFalse(SyncedOperation.ja_aplicada(outro, "mesmo-id"))

    def test_an_oversized_id_does_not_blow_up(self):
        """O identificador vem do navegador, então é entrada hostil."""
        self.assertFalse(SyncedOperation.ja_aplicada(self.user, "x" * 500))

    def test_old_operations_are_prunable(self):
        """A tabela cresce a cada marcação offline. Sem poda, ela vira o maior
        objeto do banco num app cujo banco gratuito tem limite de tamanho."""
        SyncedOperation.ja_aplicada(self.user, "velha")
        SyncedOperation.objects.filter(op_id="velha").update(
            created_at=timezone.now() - timedelta(days=40)
        )
        SyncedOperation.ja_aplicada(self.user, "nova")

        removidas = SyncedOperation.podar()

        self.assertEqual(removidas, 1)
        self.assertTrue(SyncedOperation.objects.filter(op_id="nova").exists())
        self.assertFalse(SyncedOperation.objects.filter(op_id="velha").exists())


class WaterReplayTests(TestCase):
    """Água é aditiva — o caso que quebra sem a trava."""

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)
        self.url = reverse("plans:log_hydration")

    def _hoje(self):
        registro = HydrationLog.objects.filter(
            user=self.user, date=timezone.localdate()
        ).first()
        return registro.ml if registro else 0

    def test_replaying_the_same_operation_does_not_add_twice(self):
        """Reenviar "+500 ml" duas vezes registraria um litro que ninguém
        bebeu, e nada apareceria errado na tela."""
        for _ in range(3):
            self.client.post(self.url, {"ml": 500, "op_id": "gole-1"})

        self.assertEqual(self._hoje(), 500)

    def test_different_operations_still_add_up(self):
        """A trava não pode impedir a pessoa de beber água duas vezes."""
        self.client.post(self.url, {"ml": 500, "op_id": "gole-1"})
        self.client.post(self.url, {"ml": 500, "op_id": "gole-2"})

        self.assertEqual(self._hoje(), 1000)

    def test_without_an_identifier_nothing_changes(self):
        """A tela normal não manda identificador, e precisa continuar somando."""
        self.client.post(self.url, {"ml": 250})
        self.client.post(self.url, {"ml": 250})

        self.assertEqual(self._hoje(), 500)

    def test_one_persons_operation_does_not_block_another(self):
        outro = create_complete_user(email="outro@exemplo.com")
        self.client.post(self.url, {"ml": 500, "op_id": "compartilhado"})

        self.client.force_login(outro)
        self.client.post(self.url, {"ml": 500, "op_id": "compartilhado"})

        registro = HydrationLog.objects.get(user=outro, date=timezone.localdate())
        self.assertEqual(registro.ml, 500)


class SupplementReplayTests(TestCase):
    """Suplemento alterna — o outro caso que quebra sem a trava."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_supplements", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.creatina = Supplement.objects.get(slug="creatina")
        self.client.force_login(self.user)
        self.url = reverse("supplements:toggle", args=[self.creatina.pk])

    def _marcado(self):
        return SupplementLog.objects.filter(
            user=self.user, supplement=self.creatina, date=timezone.localdate()
        ).exists()

    def test_replaying_a_toggle_does_not_undo_it(self):
        """Alternar duas vezes volta ao estado anterior. Um reenvio da fila
        desmarcaria o que a pessoa marcou — e ela veria o contrário do que fez.
        """
        for _ in range(3):
            self.client.post(self.url, {"op_id": "tomei-creatina"})

        self.assertTrue(self._marcado())

    def test_a_new_operation_still_toggles(self):
        self.client.post(self.url, {"op_id": "marquei"})
        self.client.post(self.url, {"op_id": "desmarquei"})

        self.assertFalse(self._marcado())

    def test_without_an_identifier_it_still_toggles(self):
        self.client.post(self.url)
        self.assertTrue(self._marcado())

        self.client.post(self.url)
        self.assertFalse(self._marcado())


class IdempotentByNatureTests(TestCase):
    """As duas escritas que já eram seguras — travadas para continuarem sendo.

    Marcação de refeição e carga de série usam `update_or_create` com o valor
    final, então reenviar grava o mesmo estado. É por isso que elas entram na
    fila sem precisar de nada: a propriedade é do desenho, e um teste que a
    afirma é o que impede alguém de trocá-las por um contador algum dia.
    """

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        from plans import services

        self.plan = services.create_plan(self.user)
        self.client.force_login(self.user)

    def test_marking_a_meal_twice_leaves_one_record(self):
        from plans.models import MealLog

        slot = self.plan.slots.first()
        url = reverse("plans:mark_meal", args=[slot.pk])

        for _ in range(3):
            self.client.post(url, {"status": "skipped"})

        self.assertEqual(MealLog.objects.filter(user=self.user, slot=slot).count(), 1)

    def test_recording_the_same_set_twice_leaves_one_record(self):
        from workouts.models import Exercise, ExerciseLog
        from workouts.services import create_routine

        create_routine(self.user)
        exercicio = Exercise.objects.filter(is_active=True).first()
        url = reverse("workouts:record_load", args=[exercicio.pk])

        for _ in range(3):
            self.client.post(url, {"weight_kg": "60", "set_number": 1, "reps": "10"})

        logs = ExerciseLog.objects.filter(user=self.user, exercise=exercicio)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().weight_kg, Decimal("60"))
