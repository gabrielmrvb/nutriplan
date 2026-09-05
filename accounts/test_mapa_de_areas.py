# -*- coding: utf-8 -*-
"""O mapa das cinco áreas, e as duas mentiras que ele desfaz.

A barra de baixo tem QUATRO itens e continua com quatro: medido a 320px, cinco
colunas deixam 51,8px úteis e "Hidratação" precisa de 60. Ela responde
FREQUÊNCIA. O mapa responde ESTRUTURA — e a estrutura estava dizendo o
contrário do produto em dois lugares: a tela de água acendia a aba "Dieta" e a
de corridas acendia "Treino". A docstring de `Pilar` diz, com todas as letras,
que hidratação não é subfunção de dieta e corrida não é subfunção de treino.

Duas dessas áreas também não tinham porta de primeiro nível nenhuma: água só
pelo cartão do Hoje, corridas só pela tela de treino.
"""
import re

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import CAMPO_DO_PILAR, Pilar, Profile, User
from accounts.templatetags.navegacao import DESTINO_DO_PILAR
from accounts.tests import STEP1, STEP2, STEP3, STEP4, STEP5, step_url


class BaseDoMapa(TestCase):
    @classmethod
    def setUpTestData(cls):
        # A tela de treino precisa do catálogo de exercícios, e a de água
        # precisa de plano alimentar — as duas nascem do onboarding. Sem o
        # seed o teste reprovaria por falta de fixture em vez de por mapa
        # errado, que é o que ele mede.
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="mapa@exemplo.com", interesses=(), principal=""):
        """A pessoa nasce do WIZARD, e não de um `Profile.objects.create`.

        As telas de água e de treino exigem plano; montá-lo à mão significaria
        montar um estado que o produto nunca produz, e o mapa seria conferido
        contra uma tela que ninguém vê.
        """
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        # O passo 6 e OBRIGATORIO para o onboarding fechar, e sem ele todas as
        # telas redirecionam - foi o que esta funcao fez na primeira execucao,
        # e os cinco erros apontaram para o recorte do mapa em vez de para a
        # causa. Quem "nao declarou nada" e o LEGADO: terminou o onboarding
        # antes de a pergunta existir. Reproduzo esse estado apagando a
        # declaracao depois, que e exatamente o que a migration deixou.
        self.client.post(
            step_url(6),
            {"interesses": list(interesses) or ["dieta"],
             "prioridade": principal or "dieta"},
        )
        if not interesses:
            Profile.objects.filter(user=user).update(
                prioridade="", **{campo: False for campo in CAMPO_DO_PILAR.values()}
            )
        return user

    def mapa(self, url=None):
        """O trecho do HTML que é o mapa — e só ele.

        Recortar importa: "Corrida" e "Progresso" também aparecem na barra de
        baixo e no corpo das telas, e uma asserção sobre a página inteira
        passaria por causa delas.
        """
        html = self.client.get(url or reverse("plans:history")).content.decode()
        return html.split('class="mapa"')[1].split("</details>")[0]


class OMapaMostraAsCincoAreasTests(BaseDoMapa):
    def test_todo_pilar_tem_destino(self):
        """A tabela é completa por construção, e um pilar novo sem destino tem
        de estourar aqui e não sumir do mapa em silêncio."""
        self.assertEqual(set(DESTINO_DO_PILAR), set(Pilar))

    def test_as_cinco_aparecem_com_o_href_resolvido(self):
        self.pessoa()

        mapa = self.mapa()

        for pilar in Pilar:
            rota, _chave = DESTINO_DO_PILAR[pilar]
            with self.subTest(pilar=pilar.value):
                self.assertIn('href="%s"' % reverse(rota), mapa)
                self.assertIn(pilar.label, mapa)

    def test_a_ordem_e_a_canonica_e_nao_muda_por_pessoa(self):
        """O mapa mostra de que o app é feito, e isso é igual para todo mundo.

        Um menu que se reordena por pessoa é um mapa pior — a personalização de
        ORDEM é da tela Hoje, onde a pergunta é "o que faço agora?".
        """
        self.pessoa(interesses=("progresso", "dieta"), principal="progresso")

        mapa = self.mapa()
        posicoes = [mapa.index(p.label) for p in Pilar]

        self.assertEqual(posicoes, sorted(posicoes))


class OMapaDizOndeAPessoaEstaTests(BaseDoMapa):
    def test_a_area_da_vez_leva_aria_current(self):
        self.pessoa()

        mapa = self.mapa(reverse("plans:hydration"))
        atual = [t for t in mapa.split("<a ") if 'aria-current="page"' in t]

        self.assertEqual(len(atual), 1, mapa)
        self.assertIn(reverse("plans:hydration"), atual[0])

    def test_nenhuma_area_marcada_quando_a_tela_nao_e_de_nenhuma(self):
        """O perfil não é pilar. Marcar uma área ali seria dizer que ele é."""
        self.pessoa()

        mapa = self.mapa(reverse("accounts:profile"))

        self.assertNotIn('aria-current="page"', mapa)


class AsAbasParamDeMentirTests(BaseDoMapa):
    """As duas correções que motivaram a unidade.

    A asserção é sobre a BARRA, recortada do resto: `aria-current` também
    aparece no mapa, e uma asserção sobre a página inteira passaria por causa
    dele — que é justamente o marcador certo no lugar certo.
    """

    def barra(self, url):
        html = self.client.get(url).content.decode()
        return html.split('class="tabbar"')[1].split("</nav>")[0]

    def test_a_tela_de_agua_nao_acende_mais_a_aba_dieta(self):
        self.pessoa()

        barra = self.barra(reverse("plans:hydration"))

        self.assertNotIn('aria-current="page"', barra)
        self.assertNotIn("is-active", barra)

    def test_a_tela_de_corridas_nao_acende_mais_a_aba_treino(self):
        self.pessoa()

        barra = self.barra(reverse("workouts:corridas"))

        self.assertNotIn('aria-current="page"', barra)
        self.assertNotIn("is-active", barra)

    def test_controle_positivo_a_barra_AINDA_acende_onde_deve(self):
        """Sem este, "não acende" passaria com a barra quebrada para sempre."""
        self.pessoa()

        barra = self.barra(reverse("plans:history"))

        self.assertIn('aria-current="page"', barra)
        self.assertIn("is-active", barra)


class OSeloDaAreaPrincipalTests(BaseDoMapa):
    def test_o_selo_marca_uma_area_e_so_ela(self):
        self.pessoa(interesses=("corrida", "dieta"), principal="corrida")

        mapa = self.mapa()
        com_selo = [t for t in mapa.split("<a ") if "principal</span>" in t]

        self.assertEqual(len(com_selo), 1, mapa)
        self.assertIn(reverse("workouts:corridas"), com_selo[0])

    def test_quem_nao_declarou_ve_o_mapa_inteiro_sem_selo(self):
        """Interesse organiza, não tranca — e ausência de resposta não esconde
        área nenhuma."""
        self.pessoa()

        mapa = self.mapa()

        self.assertNotIn("principal</span>", mapa)
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn(pilar.label, mapa)


class OShellDeOfflineNaoLevaOMapaTests(BaseDoMapa):
    """A tela de offline é pré-cacheada e servida a QUALQUER pessoa que pegue o
    aparelho depois — é por isso que `data-usuario` sai de lá.

    O selo de área principal é da mesma natureza: dizer "Corrida · principal"
    numa tela gravada no cache sem prazo entrega a preferência de quem instalou
    o app para quem usar o aparelho amanhã.
    """

    def test_o_shell_nao_traz_o_mapa(self):
        self.pessoa(interesses=("corrida",), principal="corrida")

        html = self.client.get("/offline/").content.decode()

        self.assertNotIn('class="mapa"', html)
        self.assertNotIn("principal</span>", html)

    def test_controle_positivo_a_mesma_sessao_ve_o_mapa_nas_outras_telas(self):
        """Sem ele, um mapa que nunca renderizasse passaria no teste acima."""
        self.pessoa(interesses=("corrida",), principal="corrida")

        html = self.client.get(reverse("plans:history")).content.decode()

        self.assertIn('class="mapa"', html)
        self.assertIn("principal</span>", html)


class ODemoNaoPerdeOPrefixoTests(TestCase):
    """O mapa não pode ser a porta de saída do demo.

    O middleware do demo chama `set_script_prefix("/demo/")`, e é por isso que
    o mapa usa `{% url %}` em vez de caminho escrito à mão: o prefixo entra
    sozinho. Um `href="/hidratacao/"` cru mandaria quem está no demo para a
    rota real, que exige login — exatamente o beco sem saída que o demo existe
    para não ter, e que a própria docstring do middleware nomeia.
    """

    @classmethod
    def setUpTestData(cls):
        # O demo é uma persona SEMEADA — sem o seed a rota responde sem a barra
        # de sessão, e o teste reprovaria por falta de fixture em vez de por
        # prefixo perdido, que é o que ele mede.
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        call_command("seed_demo", verbosity=0)

    def test_as_cinco_apontam_para_dentro_do_demo(self):
        html = self.client.get("/demo/hoje/").content.decode()
        mapa = html.split('class="mapa"')[1].split("</details>")[0]

        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn(pilar.label, mapa)
        # Cinco `href`, e todos sob `/demo/`. A contagem importa: sem ela, um
        # mapa com uma área a menos passaria.
        enderecos = re.findall(r'href="([^"]+)"', mapa)
        self.assertEqual(len(enderecos), 5, enderecos)
        for endereco in enderecos:
            with self.subTest(endereco=endereco):
                self.assertTrue(endereco.startswith("/demo/"), endereco)

    def test_o_demo_nao_carrega_selo_de_ninguem(self):
        """O demo é anônimo por fora e uma conta fictícia por dentro. Selo ali
        seria preferência de um personagem apresentada como do visitante."""
        html = self.client.get("/demo/hoje/").content.decode()

        self.assertNotIn("principal</span>", html)
