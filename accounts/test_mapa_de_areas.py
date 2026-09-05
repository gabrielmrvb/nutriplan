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

    #: O destino de cada área, escrito AQUI e não lido de `DESTINO_DO_PILAR`.
    #:
    #: Ler a tabela sob teste faria o esperado e o obtido saírem da mesma
    #: fonte: trocar o destino de um pilar moveria os dois lados juntos e o
    #: teste continuaria verde. Foi uma revisão adversarial que mediu — com a
    #: versão anterior, apontar Progresso para o Hoje não ficava vermelho em
    #: teste nenhum deste arquivo.
    DESTINOS = {
        "dieta": "plans:today",
        "treino": "workouts:routine",
        "corrida": "workouts:corridas",
        "hidratacao": "plans:hydration",
        "progresso": "plans:history",
    }

    def test_as_cinco_aparecem_com_o_href_resolvido(self):
        self.pessoa()

        mapa = self.mapa()

        self.assertEqual(set(self.DESTINOS), {p.value for p in Pilar})
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn(
                    'href="%s"' % reverse(self.DESTINOS[pilar.value]), mapa
                )
                self.assertIn(pilar.label, mapa)

    def test_dois_pilares_nunca_apontam_para_a_mesma_tela(self):
        """A outra metade do de cima: cinco `href` e cinco telas distintas.

        Sem isto, apontar dois pilares para o mesmo lugar passaria — as cinco
        asserções de `assertIn` continuariam verdadeiras, porque `assertIn` não
        conta.
        """
        self.pessoa()

        mapa = self.mapa()
        enderecos = re.findall(r'href="([^"]+)"', mapa)

        self.assertEqual(len(enderecos), 5, enderecos)
        self.assertEqual(len(set(enderecos)), 5, enderecos)

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
        # E o prefixo não basta: `plans:today` mora na RAIZ, então sob o demo
        # ele reverte para `/demo/` — que NÃO é a tela Hoje, é a capa. O mapa
        # mandava quem estava avaliando o produto para a página de marketing,
        # e ainda anunciava "você está aqui" ao fazê-lo. `/demo/hoje/` é o
        # apelido que o middleware traduz.
        self.assertIn("/demo/hoje/", enderecos)
        self.assertNotIn("/demo/", enderecos)

    def test_a_persona_do_demo_nao_declara_area_nenhuma(self):
        """O que este teste mede é o SEED, e a versão anterior dizia outra coisa.

        Ela afirmava que o demo "não carrega selo de ninguém", como se houvesse
        guarda. Não há: a tag lê `context["user"]`, e no demo o usuário é o
        Carlos autenticado. O único motivo de o selo não sair é que
        `seed_demo` nunca escreve `prioridade` nem `interesse_*`.

        Ficou como está de propósito. O selo mostraria a preferência da
        PERSONA, que é o que o demo faz com todo o resto (refeições, peso,
        treinos) — não é vazamento, é o personagem. Mas a afirmação tinha de
        dizer o que mede: no dia em que alguém enriquecer o Carlos, este teste
        fica vermelho e a decisão é tomada ali, de olho aberto.
        """
        html = self.client.get("/demo/hoje/").content.decode()

        self.assertNotIn("principal</span>", html)
        # O que de fato garante o de cima, dito onde dá para conferir.
        semente = (
            __import__("pathlib").Path(__file__).resolve().parent
            / ".." / "demo" / "management" / "commands" / "seed_demo.py"
        ).read_text(encoding="utf-8")
        for campo in ("prioridade", "interesse_"):
            with self.subTest(campo=campo):
                self.assertNotIn(campo, semente)


class OMapaNaoOfereceSaidaDoWizardTests(BaseDoMapa):
    """A barra de baixo é desligada no onboarding, e o motivo está escrito em
    `accounts/views.py`: os destinos dela devolvem quem ainda não terminou.

    O mapa reintroduzia exatamente esses destinos na barra de CIMA — e um
    deles, `workouts:corridas`, tem só `LoginRequiredMixin`, sem
    `OnboardingRequiredMixin`. Era saída de verdade no meio do cadastro, para
    uma lista vazia, com quatro links mortos ao lado. Foi uma revisão
    adversarial que encontrou.
    """

    def a_meio_cadastro(self):
        user = User.objects.create_user(
            email="meio@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(user)
        self.client.post(step_url(1), STEP1)
        return user

    def test_o_mapa_nao_aparece_em_passo_nenhum(self):
        self.a_meio_cadastro()

        for passo in range(1, 7):
            with self.subTest(passo=passo):
                html = self.client.get(step_url(passo)).content.decode()
                self.assertNotIn('class="mapa"', html)

    def test_a_saida_sem_guarda_nao_e_oferecida(self):
        """A que doía: as outras quatro áreas devolvem para o wizard, esta não."""
        self.a_meio_cadastro()

        html = self.client.get(step_url(2)).content.decode()

        self.assertNotIn(reverse("workouts:corridas"), html)

    def test_controle_positivo_o_mapa_volta_quando_o_cadastro_termina(self):
        """Sem ele, um mapa que nunca renderizasse passaria nos dois acima."""
        self.pessoa("terminou@exemplo.com", ("dieta",), "dieta")

        html = self.client.get(reverse("plans:history")).content.decode()

        self.assertIn('class="mapa"', html)
        self.assertIn(reverse("workouts:corridas"), html)


class OCustoDoMapaEstaMedidoTests(BaseDoMapa):
    """Quanto o mapa cobra por página, e por que o número está escrito.

    Ele lê `user.profile` para saber qual área leva o selo, e `profile` é um
    descritor reverso: dispara um SELECT na primeira leitura de cada pedido.
    Em telas que já carregam o perfil isso sai de graça pelo cache do
    descritor; em `/treino/corridas/`, que não carregava, é consulta nova.

    Uma revisão adversarial apontou que o agregado do painel ganhou teste de
    contagem e esta consulta — que roda em TODA página autenticada — não ganhou
    nenhum. O número abaixo é medido, e é teto: um teste que quebra ao melhorar
    ensina a ignorá-lo.
    """

    def test_o_mapa_custa_no_maximo_uma_consulta_a_mais(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.pessoa("custo@exemplo.com", ("corrida",), "corrida")
        url = reverse("workouts:corridas")
        self.client.get(url)  # aquece o que é cacheado por processo

        with CaptureQueriesContext(connection) as com_mapa:
            resposta = self.client.get(url)

        self.assertEqual(resposta.status_code, 200)
        # Medido em 05/09/2026: 7 consultas na tela de corridas com o mapa.
        # Teto, não valor exato.
        self.assertLessEqual(len(com_mapa.captured_queries), 8,
                             [c["sql"][:90] for c in com_mapa.captured_queries])

    def test_o_perfil_e_lido_uma_vez_so(self):
        """A pergunta que importa não é "quantas ao todo", é "o mapa repete?".

        Se alguém trocar a `inclusion_tag` por algo que rode por item, isto
        vira cinco consultas e o teto acima ainda passaria numa tela pequena.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.pessoa("custo2@exemplo.com", ("corrida",), "corrida")
        url = reverse("workouts:corridas")
        self.client.get(url)

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(url)

        do_perfil = [
            c for c in ctx.captured_queries if "accounts_profile" in c["sql"]
        ]
        self.assertEqual(len(do_perfil), 1, [c["sql"][:120] for c in do_perfil])
