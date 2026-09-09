"""TREINO — o horário deixa de ser exigência artificial.

O CAMPO ERA OBRIGATÓRIO E NÃO PARTICIPAVA DA MONTAGEM DO TREINO. `create_routine`
nunca leu `start_time`: ele servia a duas coisas, e nenhuma delas é a
prescrição.

  - `plans/agora.py` usa o horário para colocar o treino na fila do dia, e já
    testava `inicio is not None` antes de fazê-lo;
  - `plans/meal_planner.py` soma `start_time + duration_min` para não marcar
    refeição no meio do treino.

O preço de exigi-lo era concreto: todo mundo saía do passo 3 com "19:00", o
padrão do campo, e a tela repetia esse horário em cada cartão como se fosse a
rotina da pessoa.

A AUSÊNCIA É UM ESTADO DE VERDADE, e o comportamento dela é explícito: sem
horário não há janela de treino a evitar, e o cardápio volta a ser distribuído
pela janela de sono — que é exatamente o caminho de quem nunca cadastrou dia de
treino. O que NÃO se faz é preencher um padrão: inventar 19:00 para quem não
respondeu é o app afirmar uma rotina que ninguém declarou, e é a mesma doutrina
de `prioridade == ""` em `Profile`.
"""
from datetime import time

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import TrainingDay

from . import services
from .models import TrainingPlan
from .tests import create_user


def sem_horario(user):
    TrainingDay.objects.filter(user=user).update(start_time=None)
    return user


class OTreinoFuncionaSemHorarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_ficha_e_montada_sem_horario_nenhum(self):
        user = sem_horario(create_user(email="sem-hora@exemplo.com"))

        plano = services.create_routine(user)

        self.assertTrue(plano.sessions.exists())
        for sessao in plano.sessions.all():
            self.assertIsNone(sessao.start_time)

    def test_a_prescricao_e_identica_com_e_sem_horario(self):
        """O horário nunca participou da montagem, e isto prova.

        Se a ficha mudasse, haveria uma dependência escondida — e ela seria o
        motivo real de o campo ser obrigatório.
        """
        com = create_user(email="com-hora@exemplo.com")
        sem = sem_horario(create_user(email="sem-hora-2@exemplo.com"))

        p_com = services.create_routine(com)
        p_sem = services.create_routine(sem)

        def receita(plano):
            return sorted(
                (s.label, i.exercise_id, i.sets)
                for s in plano.sessions.all()
                for i in s.exercises.all()
            )

        self.assertEqual(receita(p_com), receita(p_sem))

    def test_as_telas_abrem_sem_horario(self):
        user = sem_horario(create_user(email="telas@exemplo.com"))
        services.create_routine(user)
        self.client.force_login(user)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()

        rotas = [reverse("workouts:routine"), reverse("workouts:now")]
        rotas += [
            reverse("workouts:ficha", args=[s.pk]) for s in plano.sessions.all()
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)

    def test_a_tela_nao_inventa_um_horario(self):
        """"19:00" não pode aparecer para quem não escolheu nada."""
        user = sem_horario(create_user(email="nao-inventa@exemplo.com"))
        services.create_routine(user)
        self.client.force_login(user)

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertNotIn("19:00", html)

    def test_o_perfil_diz_que_nao_ha_horario(self):
        """Silêncio não: a pessoa precisa saber que o campo está vazio."""
        user = sem_horario(create_user(email="perfil-hora@exemplo.com"))
        self.client.force_login(user)

        resposta = self.client.get(reverse("accounts:profile"))

        self.assertContains(resposta, "sem horário definido")


class OCardapioTemComportamentoExplicitoSemHorarioTests(TestCase):
    """O contrato compartilhado com Alimentação, dito por inteiro.

    `_training_end_for` devolve o fim do treino para `build_slots` não marcar
    refeição no meio dele. Sem horário não há janela, e a resposta é `None` — o
    MESMO caminho de quem não cadastrou dia de treino. Não é efeito colateral:
    é o comportamento declarado.
    """

    def test_sem_horario_nao_ha_fim_de_treino(self):
        from plans.meal_planner import _training_end_for

        user = sem_horario(create_user(email="cardapio@exemplo.com"))

        self.assertIsNone(_training_end_for(user))

    def test_com_horario_o_fim_continua_sendo_calculado(self):
        """Controle: sem isto, "sempre None" passaria no teste acima."""
        from plans.meal_planner import _training_end_for

        user = create_user(email="cardapio-2@exemplo.com")

        self.assertEqual(_training_end_for(user), time(20, 0))

    def test_um_dia_sem_horario_nao_apaga_o_horario_dos_outros(self):
        """Quem tem horário em alguns dias continua tendo janela.

        A consulta ordena por dia da semana e a primeira poderia ser a sem
        horário — daí o `exclude`. Sem ele, um único dia em branco cancelaria a
        janela de treino da semana inteira.
        """
        from plans.meal_planner import _training_end_for

        user = create_user(email="misto@exemplo.com", weekdays=(0, 2, 4))
        TrainingDay.objects.filter(user=user, weekday=0).update(start_time=None)

        self.assertEqual(_training_end_for(user), time(20, 0))


class OHorarioSalvoNaoESilenciosamenteApagadoTests(TestCase):
    """Retrocompatibilidade: quem já informou continua com o que informou."""

    def test_o_horario_existente_sobrevive(self):
        user = create_user(email="preserva@exemplo.com")

        for dia in TrainingDay.objects.filter(user=user):
            self.assertEqual(dia.start_time, time(19, 0))

    def test_o_passo_3_aceita_envio_sem_horario(self):
        from accounts.models import ONBOARDING_DONE, Profile

        user = create_user(email="passo3@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {
                "weekdays": ["1", "3"],
                "start_time": "",
                "duracao_treino": "padrao",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
        )

        dias = TrainingDay.objects.filter(user=user).order_by("weekday")
        self.assertEqual([d.weekday for d in dias], [1, 3])
        for dia in dias:
            self.assertIsNone(dia.start_time)

    def test_o_passo_3_continua_aceitando_horario(self):
        """Controle: o campo não virou decorativo."""
        from accounts.models import ONBOARDING_DONE, Profile

        user = create_user(email="passo3-com@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {
                "weekdays": ["1"],
                "start_time": "06:30",
                "duracao_treino": "padrao",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
        )

        dia = TrainingDay.objects.get(user=user, weekday=1)
        self.assertEqual(dia.start_time, time(6, 30))
