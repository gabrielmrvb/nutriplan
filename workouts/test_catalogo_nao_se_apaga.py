# -*- coding: utf-8 -*-
"""O histórico de carga não pode sumir pela porta do admin.

`ExerciseLog.exercise` é CASCADE, e é CASCADE por um bom motivo: a carga
pertence ao EXERCÍCIO e não à sessão, para sobreviver quando a ficha é
remontada. O PROTECT que segura o `delete()` vem de `WorkoutTemplateItem` e
`SessionExercise` — linhas que o próprio app apaga ao remontar. Quando um
exercício sai de todas as fichas, sobra o CASCADE sozinho.
"""
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.models import User
from workouts.admin import ExerciseAdmin
from workouts.models import Exercise, ExerciseLog


class OAdminNaoApagaExercicioTests(TestCase):
    def setUp(self):
        self.dono = User.objects.create_superuser(
            email="dono-do-admin@exemplo.com", password="senha-bem-forte-123"
        )
        self.admin = ExerciseAdmin(Exercise, AdminSite())
        self.pedido = RequestFactory().get("/admin/")
        self.pedido.user = self.dono

    def test_o_botao_de_apagar_nao_e_oferecido_nem_ao_superusuario(self):
        """O dono é o único `is_staff` do banco e tem todas as permissões —
        medido. A trava não pode depender de permissão, porque a permissão ele
        tem."""
        exercicio = Exercise.objects.create(name="Um exercício", muscle_group="back")

        self.assertFalse(self.admin.has_delete_permission(self.pedido, exercicio))
        self.assertFalse(self.admin.has_delete_permission(self.pedido))

    def test_a_acao_em_massa_de_apagar_some_da_listagem(self):
        """A ação em massa apaga vinte de uma vez, e é outro caminho que o
        botão da tela de edição.

        Quem a fecha é o `has_delete_permission` acima, não um `pop` à mão:
        `delete_selected` declara `allowed_permissions = ("delete",)`, e
        `ModelAdmin._filter_actions_by_permissions` a descarta sozinho. Este
        teste existe para o CAMINHO, não para a implementação — se alguém
        reabrir a permissão, ele acusa junto com o de cima.
        """
        self.assertNotIn("delete_selected", self.admin.get_actions(self.pedido))


class OCascataDoHistoricoExisteEEstaDocumentadaTests(TestCase):
    """Este teste não conserta nada: ele CONGELA a razão da trava acima.

    Se um dia alguém trocar `on_delete` para PROTECT no `ExerciseLog`, este
    teste fica vermelho e a pessoa lê aqui por que a trava do admin existia —
    em vez de removê-la por parecer redundante.
    """

    def test_apagar_exercicio_sem_ficha_leva_o_historico_junto(self):
        pessoa = User.objects.create_user(
            email="quem-treina@exemplo.com", password="senha-bem-forte-123"
        )
        exercicio = Exercise.objects.create(name="Solto no catálogo",
                                            muscle_group="back")
        for serie in (1, 2, 3):
            ExerciseLog.objects.create(user=pessoa, exercise=exercicio,
                                       date=timezone.localdate(), set_number=serie,
                                       weight_kg=Decimal("40"))

        self.assertEqual(ExerciseLog.objects.filter(exercise=exercicio).count(), 3)

        exercicio.delete()

        self.assertEqual(ExerciseLog.objects.count(), 0)

    def test_exercicio_que_ainda_esta_numa_ficha_recusa_o_delete(self):
        """CONTROLE POSITIVO: o PROTECT existe e funciona — só que ele depende
        de uma linha que a remontagem da ficha remove."""
        from workouts.models import WorkoutTemplate, WorkoutTemplateItem

        exercicio = Exercise.objects.create(name="Na ficha", muscle_group="back")
        ficha = WorkoutTemplate.objects.create(split="ab", label="A", name="Superior")
        WorkoutTemplateItem.objects.create(template=ficha, exercise=exercicio)

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                exercicio.delete()
