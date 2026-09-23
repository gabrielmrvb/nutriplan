"""A ficha nasce quando a pessoa termina de responder; zero dias desliga a rotina.

Achado P1-01 da auditoria de UX (14/09/2026): a PRIMEIRA Home depois do
"Concluir" negava o treino de hoje. `sync_active_routine` só rodava na
entrada das telas de Treino (`workouts/views.py`, painel e execução), e a Home
consome `estado_do_treino` sem montar nada — de propósito, para a tela de
comida não criar ficha como efeito colateral de uma visita. O resultado era
que quem marcou treino hoje, escolheu Treino como área principal e tocou
"Concluir" lia "Hoje não tem treino na sua ficha" e "— descanso" no resumo,
até abrir a aba de Treino por conta própria.

O lugar certo de montar é o fim do wizard e a edição dos dias (P1-02 / Q-02):
é ali que a entrada acabou de mudar. E a outra metade do mesmo achado é o
inverso — quem REMOVE todos os dias continua com o plano ativo, e a Home
(e a ofensiva, que lê `_dias_de_treino` do plano ativo) seguem cobrando um
treino que a pessoa disse que não vai fazer. Plano é retrato: ele não é
apagado, é desligado.

O controle positivo é a Home continuar SEM poder de criar ficha.
"""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, User
from accounts.tests import ETAPA2, STEP1, STEP5, step_url
from plans.streaks import _dias_de_treino
from workouts.models import TrainingPlan

HOJE = str(timezone.localdate().weekday())
#: A etapa 3 (comida + áreas) com Treino como área principal.
ETAPA3_TREINO = {**STEP5, "interesses": ["treino"], "prioridade": "treino"}


def _dias(*weekdays):
    """A etapa 2 com estes dias. A divisão vai junto e só é lida quando os
    dias pedem (três ou mais); com zero dias o servidor a ignora."""
    return {**ETAPA2, "weekdays": [str(d) for d in weekdays], "musculacao": "sim"}


class FichaNasceNoConcluirTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="concluir@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)

    def concluir(self, etapa2):
        # Três etapas fixas desde 15/09/2026: a rotina (com a divisão, quando
        # os dias pedem) é a 2, e "Calcular minha estimativa" é o POST da 3.
        resposta = self.client.post(step_url(2), etapa2)
        self.assertRedirects(resposta, step_url(3))
        return self.client.post(step_url(3), ETAPA3_TREINO)

    def test_a_primeira_home_depois_do_concluir_ja_tem_o_treino_de_hoje(self):
        # Hoje mais dois dias — o caso que chegava à Home sem ficha.
        hoje = int(HOJE)
        resposta = self.concluir(_dias(hoje, (hoje + 2) % 7, (hoje + 4) % 7))
        self.assertRedirects(resposta, reverse("plans:today"))

        self.assertTrue(TrainingPlan.objects.filter(user=self.user, is_active=True).exists())
        home = self.client.get(reverse("plans:today"))
        self.assertEqual(home.status_code, 200)
        # O CARTÃO DE TREINO DO PAINEL, e não a linha `.resumo-dia` de 11px
        # que a Home tinha até 22/09/2026: com treino hoje ele mostra as
        # séries e o botão; sem, diz "Descanso"; sem ficha, "Sem ficha".
        self.assertNotContains(home, "Descanso")
        self.assertNotContains(home, "Sem ficha")
        self.assertContains(home, "séries</span></p>")

    def test_concluir_com_zero_dias_nao_monta_ficha_e_nao_quebra(self):
        resposta = self.concluir(_dias())
        self.assertRedirects(resposta, reverse("plans:today"))

        self.assertFalse(TrainingPlan.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)
        self.assertTrue(Profile.objects.get(user=self.user).onboarding_complete)

    def test_editar_os_dias_para_nenhum_desliga_a_rotina(self):
        hoje = int(HOJE)
        self.concluir(_dias(hoje, (hoje + 2) % 7, (hoje + 4) % 7))
        plano = TrainingPlan.objects.get(user=self.user, is_active=True)

        resposta = self.client.post(step_url(2), _dias())
        self.assertEqual(resposta.status_code, 302)

        plano.refresh_from_db()
        self.assertFalse(plano.is_active, "plano é retrato: desligado, não apagado")
        self.assertTrue(TrainingPlan.objects.filter(pk=plano.pk).exists())
        self.assertEqual(_dias_de_treino(self.user), set())
        home = self.client.get(reverse("plans:today"))
        self.assertContains(home, "Sem ficha")
        self.assertNotContains(home, "séries</span></p>")

    def test_editar_os_dias_remonta_a_ficha_na_hora(self):
        hoje = int(HOJE)
        self.concluir(_dias((hoje + 1) % 7, (hoje + 3) % 7, (hoje + 5) % 7))
        antigo = TrainingPlan.objects.get(user=self.user, is_active=True)
        self.assertNotContains(
            self.client.get(reverse("plans:today")), "séries</span></p>"
        )

        self.client.post(step_url(2), _dias(hoje, (hoje + 2) % 7, (hoje + 4) % 7))

        novo = TrainingPlan.objects.get(user=self.user, is_active=True)
        self.assertNotEqual(novo.pk, antigo.pk)
        self.assertContains(
            self.client.get(reverse("plans:today")), "séries</span></p>"
        )

    def test_dia_de_descanso_de_verdade_continua_dizendo_que_a_semana_esta_la(self):
        hoje = int(HOJE)
        self.concluir(_dias((hoje + 1) % 7, (hoje + 3) % 7, (hoje + 5) % 7))
        # "Descanso" mais o PRÓXIMO treino: a frase antiga ("Hoje não tem
        # treino na sua ficha. A semana inteira está lá.") vivia no cartão de
        # área promovida, que saiu em 22/09/2026 — e ela não dizia QUANDO o
        # treino volta, que é a pergunta real de quem lê isso.
        home = self.client.get(reverse("plans:today"))
        self.assertContains(home, "Descanso")
        self.assertNotContains(home, "Sem ficha")

    def test_controle_a_home_continua_sem_poder_de_criar_ficha(self):
        """A Home consome o estado e não monta nada — a decisão de `plans/views.py`.

        Com dias cadastrados e o plano ativo desligado à mão, abrir a Home não
        cria plano nenhum; abrir o painel de Treino cria. É o que separa
        "montar no Concluir" de "montar em qualquer visita".
        """
        hoje = int(HOJE)
        self.concluir(_dias(hoje, (hoje + 2) % 7, (hoje + 4) % 7))
        TrainingPlan.objects.filter(user=self.user).update(is_active=False)

        home = self.client.get(reverse("plans:today"))
        self.assertFalse(TrainingPlan.objects.filter(user=self.user, is_active=True).exists())
        # E a Home não finge descanso: sem plano ativo o cartão diz "Sem
        # ficha" e oferece montar, e não "Descanso", que seria afirmar um
        # plano de descanso que ninguém fez. (As frases longas do cartão de
        # área promovida saíram em 22/09/2026 com o próprio cartão.)
        self.assertContains(home, "Sem ficha")
        self.assertContains(home, "Montar treino")
        self.assertNotContains(home, "Descanso")

        self.client.get(reverse("workouts:routine"))
        self.assertTrue(TrainingPlan.objects.filter(user=self.user, is_active=True).exists())


class SemCatalogoTests(TestCase):
    """O catálogo faltar não pode transformar o "Concluir" num 500.

    `create_routine` levanta `NoTrainingDays` quando a divisão não tem modelo
    — é o que acontece num banco sem `seed_workouts`. Quem veio pela comida
    termina o cadastro do mesmo jeito; o aviso fica no log com o identificador
    do pedido, e a aba de Treino levanta o mesmo erro ao abrir, como sempre.
    """

    def test_concluir_sem_catalogo_termina_o_cadastro_e_avisa_no_log(self):
        user = User.objects.create_user(
            email="sem-catalogo@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(user)
        self.client.post(step_url(1), STEP1)
        hoje = int(HOJE)
        self.client.post(step_url(2), _dias(hoje, (hoje + 2) % 7, (hoje + 4) % 7))

        with self.assertLogs("accounts.views", level="WARNING") as log:
            resposta = self.client.post(step_url(3), ETAPA3_TREINO)

        self.assertRedirects(resposta, reverse("plans:today"))
        self.assertFalse(TrainingPlan.objects.filter(user=user).exists())
        self.assertIn("ficha não montada", log.output[0])
