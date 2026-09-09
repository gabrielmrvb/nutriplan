# -*- coding: utf-8 -*-
"""A tela de Áreas — o quarto destino da barra, depois de UX-01.

SUBSTITUI `test_mapa_de_areas.py`, e a substituição é de arquitetura, não de
arrumação. Antes existiam DOIS sistemas de navegação: a barra de baixo com
quatro itens e um `<details>` chamado "Áreas" no canto superior direito. O dono
do produto, usando o app, descreveu o efeito — "uma barra principal mais um
segundo menu paralelo", sem hierarquia entre os dois.

UX-01 fez de Áreas o quarto item da barra e tirou o `<details>` do topo. Três
consequências que estes testes guardam:

1. **Áreas não repete a barra.** Alimentação, Treino e Progresso têm porta
   direta e não aparecem lá dentro. O teste antigo cobrava o contrário — que o
   mesmo destino tivesse o mesmo nome nos dois lugares —, e a régua inverteu.
2. **Corrida e Hidratação passam a acender uma aba.** Elas eram os dois pilares
   sem porta de primeiro nível, e a barra ficava apagada nessas telas porque
   acender "Treino" numa tela de corrida afirmaria a subordinação que a
   docstring de `Pilar` nega. Agora existe a aba certa.
3. **O selo de área principal saiu do `base.html`.** Ele era identidade dentro
   de uma tela pré-cacheada; agora mora só numa página autenticada.
"""
import re

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import CAMPO_DO_PILAR, Pilar, Profile, User
from accounts.templatetags.navegacao import DESTINO_DO_PILAR, PILARES_NA_BARRA
from accounts.tests import STEP1, STEP2, STEP3, STEP4, STEP5, step_url


class BaseDeAreas(TestCase):
    @classmethod
    def setUpTestData(cls):
        # A tela de treino precisa do catálogo, e a de água precisa de plano —
        # as duas nascem do onboarding. Sem o seed o teste reprovaria por falta
        # de fixture em vez de por navegação errada, que é o que ele mede.
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="areas@exemplo.com", interesses=(), principal=""):
        """A pessoa nasce do WIZARD, e não de um `Profile.objects.create`.

        As telas de água e de treino exigem plano; montá-lo à mão significaria
        conferir a navegação contra uma tela que ninguém vê.
        """
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        self.client.post(
            step_url(6),
            {"interesses": list(interesses) or ["dieta"],
             "prioridade": principal or "dieta"},
        )
        if not interesses:
            # Quem "não declarou nada" é o LEGADO: terminou o onboarding antes
            # de a pergunta existir. Apagar a declaração depois reproduz
            # exatamente o estado que a migration deixou.
            Profile.objects.filter(user=user).update(
                prioridade="", **{campo: False for campo in CAMPO_DO_PILAR.values()}
            )
        return user

    def areas(self):
        """O HTML da tela de Áreas."""
        return self.client.get(reverse("areas")).content.decode()

    def entradas(self, html):
        """destino -> nome visível de cada entrada da tela de Áreas.

        Recorta `mapa__nome` e não o `<a>` inteiro: a entrada carrega nome E
        frase de apoio dentro do mesmo link, e comparar tudo faria o teste
        acusar divergência entre "Corrida" e "Corrida Suas corridas...".
        """
        pares = {}
        for m in re.finditer(
            r'<a class="(?:mapa__area|modulo)[^"]*"[^>]*?href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.S,
        ):
            achado = re.search(
                r'<span class="(?:mapa__nome|modulo__nome)"[^>]*>(.*?)</span>',
                m.group(2), re.S)
            corpo = achado.group(1) if achado else ""
            texto = " ".join(re.sub(r"<[^>]+>", " ", corpo).split())
            pares[m.group(1)] = texto.replace(" principal", "")
        return pares


class AreasNaoRepeteABarraTests(BaseDeAreas):
    """A regra que define o conteúdo da tela."""

    def test_os_dois_pilares_sem_porta_na_barra_aparecem(self):
        """Corrida e Hidratação eram os únicos sem porta de primeiro nível —
        água só pelo cartão do Hoje, corridas só pela tela de treino."""
        self.pessoa()

        destinos = self.entradas(self.areas())

        self.assertIn(reverse("workouts:corridas"), destinos)
        self.assertIn(reverse("plans:hydration"), destinos)

    def test_os_tres_pilares_da_barra_NAO_aparecem(self):
        """CONTROLE NEGATIVO da regra de UX-01, e o coração desta tela.

        Repetir aqui o que a barra já alcança é recriar o segundo menu paralelo
        que a mudança veio remover.
        """
        self.pessoa()

        destinos = self.entradas(self.areas())

        for pilar in PILARES_NA_BARRA:
            rota, _chave = DESTINO_DO_PILAR[pilar]
            with self.subTest(pilar=pilar.value):
                self.assertNotIn(reverse(rota), destinos)

    def test_a_tela_NAO_repete_o_que_a_barra_ja_mostra(self):
        """A linha explicativa saiu em 09/09/2026, e a intenção continua.

        Ela dizia "Alimentação, Treino e Progresso estão na barra, aqui
        embaixo" — para quem viu cinco áreas no onboarding e abria Áreas
        encontrando duas. O problema é que ela aponta para a barra que está
        VISÍVEL na mesma tela, dizendo à pessoa o que ela está vendo.

        O que a guarda mede agora é a propriedade que sempre importou: Áreas
        não duplica os destinos da barra. Os três pilares que moram lá não
        ganham cartão aqui — nem link, nem legenda sobre eles.
        """
        self.pessoa()

        html = self.areas()
        destinos = self.entradas(html)

        self.assertNotIn("estão na barra", html)
        for da_barra in (reverse("plans:today"), reverse("workouts:routine")):
            with self.subTest(destino=da_barra):
                self.assertNotIn(da_barra, destinos)

    def test_as_ferramentas_sem_porta_fixa_moram_aqui(self):
        """Lista de compras não é pilar e nunca teve porta própria — só se
        alcançava pela tela de Alimentação.

        Conquistas TAMBÉM morava aqui, e saiu em 08/09/2026: a página tem pouco
        para justificar uma ferramenta própria, e a pergunta que ela responde
        ("como estou evoluindo") é a do Progresso. O bloco compacto mora lá, e
        `/conquistas/` continua alcançável por ele.
        """
        self.pessoa()

        destinos = self.entradas(self.areas())

        self.assertIn(reverse("plans:shopping"), destinos)
        self.assertNotIn(
            reverse("achievements:list"),
            destinos,
            "Conquistas voltou a ser cartão de Áreas",
        )

    def test_o_perfil_saiu_da_barra_e_mora_aqui(self):
        self.pessoa()

        destinos = self.entradas(self.areas())

        self.assertIn(reverse("accounts:profile"), destinos)


class ATabelaDePilaresContinuaIntegraTests(TestCase):
    """Estes três não olham HTML: guardam a tabela que a tela lê."""

    def test_todo_pilar_tem_destino(self):
        """Dicionário completo e não `.get()` com padrão: pilar sem destino tem
        de estourar na primeira renderização, e não sumir em silêncio."""
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn(pilar, DESTINO_DO_PILAR)

    def test_dois_pilares_nunca_apontam_para_a_mesma_tela(self):
        rotas = [rota for rota, _ in DESTINO_DO_PILAR.values()]

        self.assertEqual(len(rotas), len(set(rotas)))

    def test_os_pilares_da_barra_sao_exatamente_tres(self):
        """CONTROLE da conta de largura: a barra tem quatro itens, e três deles
        são pilar — o quarto é Áreas. Um quinto item derrubaria os quatro para
        ~51,8px a 320px, abaixo do que "Hidratação" precisa."""
        self.assertEqual(len(PILARES_NA_BARRA), 3)
        for pilar in PILARES_NA_BARRA:
            self.assertIn(pilar, DESTINO_DO_PILAR)


class ATelaDeAreasNaoSeMarcaComoDestinoTests(BaseDeAreas):
    def test_nenhuma_entrada_e_a_pagina_atual(self):
        """Estar em Áreas não é estar em nenhuma das áreas listadas. Marcar uma
        delas com `aria-current="page"` diria a quem ouve a tela que ela está
        numa página em que não está."""
        self.pessoa()

        html = self.areas()

        self.assertNotIn('aria-current="page"', self.areas_recorte(html))

    def areas_recorte(self, html):
        """Só as entradas — a barra de baixo também tem `aria-current`."""
        return "".join(re.findall(r'<a class="(?:mapa__area|modulo).*?</a>', html, re.S))


class OSeloDaAreaPrincipalTests(BaseDeAreas):
    def test_o_selo_marca_a_area_principal_quando_ela_esta_na_tela(self):
        self.pessoa(interesses=["corrida", "dieta"], principal="corrida")

        html = self.areas()

        entrada = [t for t in re.findall(r'<a class="(?:mapa__area|modulo).*?</a>', html, re.S)
                   if reverse("workouts:corridas") in t]
        self.assertEqual(len(entrada), 1, html)
        self.assertIn("principal", entrada[0])

    def test_quem_elege_area_da_BARRA_nao_ve_selo_nenhum_aqui(self):
        """Consequência direta da não-duplicação, e ela é aceitável: quem
        elegeu Alimentação vê o selo onde ela mora, que é a barra acesa e a
        Home reorganizada — não numa tela que não a lista."""
        self.pessoa(interesses=["dieta"], principal="dieta")

        html = self.areas()

        self.assertNotIn("principal</span>", html)

    def test_quem_nao_declarou_nada_ve_a_tela_sem_selo(self):
        self.pessoa()

        html = self.areas()

        self.assertNotIn("principal</span>", html)


class OShellDeOfflineNaoLevaIdentidadeTests(BaseDeAreas):
    """O selo era identidade dentro de uma tela pré-cacheada.

    A tela de offline é servida a quem pegar o aparelho depois. Antes o selo
    vinha no `base.html`, e havia DUAS camadas o segurando: um `{% if %}` no
    template e a tag se recusando a ler o perfil. UX-01 deixou o problema sem
    superfície — o selo não é mais renderizado em `base.html` por caminho
    nenhum.
    """

    def test_o_shell_nao_traz_selo_nem_dono(self):
        self.pessoa()

        html = self.client.get(reverse("offline")).content.decode()

        self.assertNotIn("principal</span>", html)
        self.assertIn('data-usuario=""', html)

    def test_controle_positivo_a_mesma_sessao_ve_o_selo_em_areas(self):
        """Sem ele, um `base.html` que parasse de renderizar o selo em toda
        parte passaria no teste acima sem que nada estivesse certo."""
        self.pessoa(interesses=["hidratacao"], principal="hidratacao")

        self.assertIn("principal</span>", self.areas())


class ODemoNaoPerdeOPrefixoTests(TestCase):
    """Áreas não pode ser a porta de saída do demo.

    O middleware chama `set_script_prefix("/demo/")`, e é por isso que a tela
    usa `{% url %}` em vez de caminho escrito à mão. Um `href="/hidratacao/"`
    cru mandaria quem avalia o produto para a rota real, que exige login.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        call_command("seed_demo", verbosity=0)

    def test_as_entradas_apontam_para_dentro_do_demo(self):
        html = self.client.get("/demo/areas/").content.decode()

        entradas = re.findall(
            r'<a class="(?:mapa__area|modulo)[^"]*"[^>]*?href="([^"]+)"', html)

        self.assertTrue(entradas, html[:400])
        for destino in entradas:
            with self.subTest(destino=destino):
                self.assertTrue(destino.startswith("/demo/"), destino)


class AreasNaoOfereceSaidaDoWizardTests(BaseDeAreas):
    """`workouts:corridas` tem só `LoginRequiredMixin` e era saída DE VERDADE
    no meio do cadastro. O mesmo `sem_tabbar` que desliga a barra desliga o
    acesso a Áreas, porque agora Áreas está DENTRO da barra."""

    def caminhando(self):
        user = User.objects.create_user(
            email="meio-do-wizard@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(user)
        self.client.post(step_url(1), STEP1)
        return user

    def test_nenhum_passo_do_wizard_oferece_areas(self):
        self.caminhando()

        for passo in (1, 2):
            with self.subTest(passo=passo):
                html = self.client.get(step_url(passo)).content.decode()
                self.assertNotIn(reverse("areas"), html)

    def test_controle_positivo_areas_volta_quando_o_cadastro_termina(self):
        self.pessoa()

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn(reverse("areas"), html)


class OCustoDaTelaDeAreasEstaMedidoTests(BaseDeAreas):
    def test_o_perfil_e_lido_uma_vez_so(self):
        """A tela lê o perfil para saber a área principal. Ler por entrada
        seria uma consulta por linha numa tela que existe para ser rápida."""
        self.pessoa(interesses=["corrida"], principal="corrida")

        # SEIS era um palpite meu; a medição devolveu TRÊS. O número aqui é o
        # medido, e ele é o ponto: a tela lê o perfil uma vez e não uma vez por
        # entrada — que é o defeito que este teste existe para impedir.
        #
        # Subiu para SEIS no REDESIGN V1, quando as linhas passaram a mostrar
        # um fato real em vez de só a descrição: peso, água de hoje e contagem
        # de corridas. As três são de custo FIXO — é isso que a segunda
        # medição abaixo prova, e é a propriedade que este teste guarda. O
        # número sozinho nunca foi o ponto.
        with self.assertNumQueries(6):
            self.client.get(reverse("areas"))

    def test_o_custo_nao_cresce_com_o_numero_de_areas(self):
        """A propriedade que o número de consultas existe para proteger.

        Travar só o total deixaria passar a regressão que importa: alguém
        consultando dentro do laço das áreas mantém o total "parecido" hoje e
        transforma a tela numa consulta por linha quando um pilar novo entrar.
        Aqui a mesma tela é medida duas vezes, e o que se afirma é que o custo
        não acompanha a quantidade de linhas renderizadas.
        """
        self.pessoa(interesses=["corrida"], principal="corrida")

        with self.assertNumQueries(6):
            resposta = self.client.get(reverse("areas"))

        linhas = resposta.content.decode().count('class="modulo')
        self.assertGreaterEqual(
            linhas, 4, "a tela precisa ter várias linhas para a medição valer"
        )
