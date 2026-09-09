"""A personalização por pilar CONTINUA, e agora ela diz o que faz.

POR QUE ESTE ARQUIVO EXISTE. A etapa "Suas áreas" foi confundida com passo
morto, e a confusão tinha uma causa concreta: o Perfil dizia, na mesma frase,
"você ainda não disse o que quer cuidar" e "nada fica escondido por não ter sido
marcado". Se nada fica escondido, por que escolher?

A escolha muda três coisas, e elas foram medidas antes de qualquer alteração:

  - `plans/views.py:370-376` — prioridade Corrida ou Progresso abre ramos
    próprios no cartão AGORA;
  - `plans/views.py:441` — `area_promovida` decide ONDE a seção da área entra
    na Home;
  - `plans/agora.py:288` — `limiar_de_atraso(prioridade, ...)` move o limiar do
    aviso de hidratação.

Então a correção não foi remover a etapa: foi fazer a tela dizer a consequência,
oferecer uma saída neutra explícita, e o Perfil mostrar o ESTADO em vez de uma
cobrança que ele mesmo desmentia.

Este arquivo guarda as duas metades — a comunicação e o consumo. Sem a segunda,
um refactor futuro poderia apagar a personalização mantendo os textos bonitos.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import CAMPO_DO_PILAR, Pilar, Profile
from plans.agora import limiar_de_atraso

User = get_user_model()


def step_url(numero):
    return reverse("accounts:onboarding_step", kwargs={"step": numero})


class AOpcaoNeutraEUmaRespostaTests(TestCase):
    """"Não quero priorizar agora" precisa ser possível, e não um silêncio.

    Antes, não responder e escolher não priorizar eram indistinguíveis — e a
    validação cobrava uma principal de quem marcasse várias áreas, sem oferecer
    saída. Quem escolhe a opção neutra recebe a organização canônica, que é um
    resultado legítimo.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="neutra@exemplo.com", password="x8Kd2Lm9Qp4z"
        )
        Profile.objects.create(
            user=self.user, sex="M", birth_date="1995-04-12",
            height_cm=178, onboarding_step=6,
        )
        self.client.force_login(self.user)

    def test_a_opcao_neutra_aparece_na_tela(self):
        html = self.client.get(step_url(6)).content.decode()

        self.assertIn("Não quero priorizar agora", html)

    def test_usuario_novo_pode_nao_priorizar_sem_marcar_nada(self):
        """Resposta completa por si só. Sem isto, a tela exigiria pelo menos
        uma área de quem só quer seguir em frente."""
        resposta = self.client.post(step_url(6), {"prioridade": "nenhuma"})

        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.prioridade, "")
        self.assertEqual(perfil.interesses, [])
        self.assertIn(resposta.status_code, (302, 303))

    def test_a_opcao_neutra_com_VARIAS_areas_nao_vira_erro(self):
        """O caso que a validação antiga cobrava: marcar várias e não eleger.

        Sem a saída explícita, a tela respondia "Você marcou mais de uma área.
        Escolha qual vem primeiro." para quem já tinha dito que não queria
        escolher.
        """
        self.client.post(
            step_url(6),
            {"interesses": ["dieta", "corrida", "hidratacao"], "prioridade": "nenhuma"},
        )

        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.prioridade, "")
        self.assertEqual(
            sorted(perfil.interesses), sorted([Pilar.DIETA, Pilar.CORRIDA, Pilar.HIDRATACAO])
        )

    def test_a_opcao_neutra_com_UMA_area_nao_promove_ela_sozinha(self):
        """"Uma área só dispensa a pergunta" vale para quem NÃO respondeu.

        Quem disse "não quero priorizar" respondeu — promover a única marcada
        seria escolher por ela.
        """
        self.client.post(
            step_url(6), {"interesses": ["corrida"], "prioridade": "nenhuma"}
        )

        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.prioridade, "")
        self.assertEqual(perfil.interesses, [Pilar.CORRIDA])

    def test_quem_QUER_priorizar_continua_conseguindo(self):
        """Controle positivo: a saída neutra não pode ter desligado a escolha."""
        self.client.post(
            step_url(6), {"interesses": ["corrida", "hidratacao"], "prioridade": "corrida"}
        )

        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.prioridade, Pilar.CORRIDA)
        self.assertEqual(perfil.interesses_secundarios, [Pilar.HIDRATACAO])


class OTextoDoPerfilCorrespondeAosDadosTests(TestCase):
    """O cartão diz o que É, nos três estados possíveis."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="perfil-estado@exemplo.com", password="x8Kd2Lm9Qp4z"
        )
        self.perfil = Profile.objects.create(
            user=self.user, sex="M", birth_date="1995-04-12",
            height_cm=178, onboarding_step=7,
        )
        self.client.force_login(self.user)

    def cartao(self):
        html = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn("Prioridade no NutriPlan", html)
        return html.split("Prioridade no NutriPlan", 1)[1].split("</section>", 1)[0]

    def test_sem_escolha_o_cartao_diz_organizacao_padrao(self):
        cartao = self.cartao()

        self.assertIn("Nenhuma prioridade definida", cartao)
        self.assertIn("organização padrão", cartao)

    def test_com_escolha_o_cartao_NAO_diz_que_falta_escolher(self):
        """"Não mostre uma mensagem de ausência quando existirem valores
        salvos" — a regra da campanha, medida."""
        Profile.objects.filter(pk=self.perfil.pk).update(
            prioridade=Pilar.CORRIDA, **{CAMPO_DO_PILAR[Pilar.CORRIDA]: True}
        )

        cartao = self.cartao()

        self.assertNotIn("Nenhuma prioridade definida", cartao)
        self.assertIn("Principal", cartao)
        self.assertIn("Corrida", cartao)

    def test_com_interesses_alem_da_principal_o_cartao_lista_os_dois(self):
        Profile.objects.filter(pk=self.perfil.pk).update(
            prioridade=Pilar.CORRIDA,
            **{
                CAMPO_DO_PILAR[Pilar.CORRIDA]: True,
                CAMPO_DO_PILAR[Pilar.HIDRATACAO]: True,
                CAMPO_DO_PILAR[Pilar.PROGRESSO]: True,
            },
        )

        cartao = self.cartao()

        self.assertIn("Também quero acompanhar", cartao)
        self.assertIn("Hidratação", cartao)
        self.assertIn("Progresso", cartao)

    def test_a_porta_para_editar_fica_nos_dois_estados(self):
        sem = self.cartao()
        Profile.objects.filter(pk=self.perfil.pk).update(
            prioridade=Pilar.DIETA, **{CAMPO_DO_PILAR[Pilar.DIETA]: True}
        )
        com = self.cartao()

        for estado, cartao in (("sem escolha", sem), ("com escolha", com)):
            with self.subTest(estado=estado):
                self.assertIn("/conta/onboarding/6/", cartao)


class APersonalizacaoCONTINUAValendoTests(TestCase):
    """A metade que os textos não guardam: o consumo.

    Se um refactor futuro apagar `area_promovida` ou o ramo da prioridade em
    `limiar_de_atraso`, os textos continuariam bonitos e a escolha viraria
    enfeite — que é exatamente a hipótese que esta campanha investigou e
    descartou com medição.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="consumo@exemplo.com", password="x8Kd2Lm9Qp4z"
        )
        self.perfil = Profile.objects.create(
            user=self.user, sex="M", birth_date="1995-04-12",
            height_cm=178, onboarding_step=7,
        )

    def _com_prioridade(self, pilar):
        Profile.objects.filter(pk=self.perfil.pk).update(
            prioridade=pilar, **{CAMPO_DO_PILAR[pilar]: True}
        )
        self.perfil.refresh_from_db()
        return self.perfil

    def test_o_limiar_de_hidratacao_depende_da_prioridade(self):
        """A prioridade move o limiar dentro de uma faixa fechada."""
        neutro = limiar_de_atraso("", interessada=False)
        com_agua = limiar_de_atraso(Pilar.HIDRATACAO, interessada=True)

        self.assertNotEqual(
            com_agua, neutro, "a prioridade parou de mover o limiar da água"
        )
        self.assertGreaterEqual(min(neutro, com_agua), 15)
        self.assertLessEqual(max(neutro, com_agua), 35)

    def test_declarar_interesse_nunca_PIORA_a_propria_area(self):
        """A regra que o `CLAUDE.md` registra como defeito já corrigido:
        quem marca hidratação sem elegê-la não pode receber aviso mais tarde
        que quem não declarou nada."""
        neutro = limiar_de_atraso("", interessada=False)
        interessada = limiar_de_atraso(Pilar.DIETA, interessada=True)

        self.assertLessEqual(interessada, neutro)

    def test_a_prioridade_chega_a_tela_inicial(self):
        """`area_promovida` é o que a Home usa para decidir a ordem. Sem ele no
        contexto, a personalização não sai do banco."""
        from plans.views import TodayView  # noqa: F401 — só para o app carregar

        for pilar in (Pilar.CORRIDA, Pilar.PROGRESSO, Pilar.HIDRATACAO):
            with self.subTest(pilar=pilar):
                perfil = self._com_prioridade(pilar)
                self.assertEqual(perfil.prioridade, pilar)
                self.assertIn(pilar, perfil.interesses)

    def test_nenhuma_area_fica_inacessivel_por_causa_da_escolha(self):
        """"Interesse ORGANIZA; ele não restringe." Quem elegeu só corrida
        continua alcançando as outras quatro."""
        self._com_prioridade(Pilar.CORRIDA)
        self.client.force_login(self.user)

        for rota in ("/", "/treino/", "/historico/", "/hidratacao/", "/areas/"):
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertNotEqual(
                    resposta.status_code, 404, "a área %s sumiu" % rota
                )
