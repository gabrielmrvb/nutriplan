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

    def test_o_perfil_nao_exibe_horario_nenhum(self):
        """O Perfil parou de mostrar horário, com valor ou sem.

        ERA "sem horário definido", e a frase estava certa enquanto o campo
        existia: dizer o dia e parar era melhor que inventar um padrão. O campo
        saiu da interface em 10/09/2026 — ele nunca participou da montagem da
        ficha, e repetia "19:00" em todo cartão como se fosse a rotina da
        pessoa. Exibir um valor que não dá para editar faz procurar o botão que
        não existe.

        O DADO CONTINUA NO BANCO: `plans/meal_planner.py` soma
        `start_time + duration_min` para não marcar refeição no meio do treino.
        Quem guarda isso é
        `OHorarioSalvoNaoESilenciosamenteApagadoTests` e o teste de
        preservação em `workouts/test_fluxo_do_treino.py`.
        """
        user = create_user(email='perfil-sem-horario@exemplo.com')
        services.create_routine(user)
        self.client.force_login(user)

        resposta = self.client.get(reverse('accounts:profile'))

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'sem horário definido')
        self.assertNotContains(resposta, '19:00')

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

    def test_o_passo_3_NAO_aceita_mais_horario_e_preserva_o_existente(self):
        """O controle virou o contrário, e o contrário é o contrato novo.

        ELE ERA "o campo não virou decorativo": postar 06:30 tinha de gravar
        06:30. O campo saiu da tela em 10/09/2026 — ele nunca participou da
        montagem da ficha (`create_routine` jamais leu `start_time`) e repetia
        "19:00" em todo cartão como se fosse a rotina da pessoa.

        Agora são DUAS afirmações, e a segunda é a que protege o cardápio:

          - o formulário IGNORA um horário postado. Não é campo escondido nem
            decorativo: ele não existe, e um POST forjado não o ressuscita;
          - o horário JÁ GRAVADO sobrevive ao salvamento. `plans/meal_planner.py`
            soma `start_time + duration_min` para não marcar refeição no meio do
            treino, e `update_or_create` com `start_time=None` nos defaults
            apagaria isso em silêncio — mudando o cardápio de quem já usa o app.
        """
        from accounts.models import ONBOARDING_DONE, Profile

        user = create_user(email="passo3-com@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        TrainingDay.objects.filter(user=user).update(start_time=time(19, 0))
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {
                "weekdays": [str(d.weekday) for d in user.training_days.all()],
                "start_time": "06:30",
                "experiencia": "intermediario",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
        )

        horarios = {d.start_time for d in user.training_days.all()}
        self.assertEqual(
            horarios, {time(19, 0)},
            "o POST forjado mudou o horário, ou o salvamento o apagou",
        )
