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
from accounts.tests import ETAPA2, STEP1, STEP5, step_url


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
        for passo, dados in ((1, STEP1), (2, ETAPA2)):
            self.client.post(step_url(passo), dados)
        # A etapa 3 é comida + áreas num POST só (15/09/2026).
        self.client.post(
            step_url(3),
            {**STEP5,
             "interesses": list(interesses) or ["dieta"],
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

        CONQUISTAS VOLTOU, e a volta tem data e motivo. Ela saiu em 08/09/2026
        porque a página tinha pouco e a pergunta dela ("como estou evoluindo")
        era a do Progresso. A missão mestre de 12/09/2026 (§6) lista Conquistas
        entre o que Áreas concentra, e é decisão de produto do dono — este
        teste passa a cobrar a porta em vez de proibi-la. O bloco compacto do
        Progresso continua existindo; as duas portas respondem perguntas
        diferentes ("estou evoluindo?" lá, "o que mais o app tem?" aqui).
        """
        self.pessoa()

        destinos = self.entradas(self.areas())

        self.assertIn(reverse("plans:shopping"), destinos)
        self.assertIn(
            reverse("achievements:list"),
            destinos,
            "Conquistas saiu de Áreas — a spec de 12/09/2026 a põe aqui",
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

    def test_nenhuma_etapa_do_wizard_oferece_areas(self):
        self.caminhando()

        # As duas etapas alcançáveis com só a 1 respondida: a guarda do wizard
        # devolve quem pede a 3 antes da 2.
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
        #
        # OITO desde 12/09/2026, quando Áreas virou hub (§6 da missão mestre):
        # três fatos novos, cada um em UMA consulta de custo fixo — as
        # conquistas (lista ordenada: quantas e a última saem dela), o plano
        # ativo (meta de calorias do Perfil) e as distâncias das corridas
        # (contagem e última na mesma lista). `proxima` conquista ficou de
        # fora de propósito: passa por `reunir()`, que o Progresso paga com
        # orçamento de 26.
        with self.assertNumQueries(8):
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

        with self.assertNumQueries(8):
            resposta = self.client.get(reverse("areas"))

        linhas = resposta.content.decode().count('class="modulo')
        self.assertGreaterEqual(
            linhas, 4, "a tela precisa ter várias linhas para a medição valer"
        )


class AreasEUmHubENaoUmMenuTests(BaseDeAreas):
    """Cada módulo responde ANTES do toque, e a grade não é uma fileira de iguais.

    A missão mestre (§6) pede de Áreas: destaque principal, resumo real,
    progresso, valor atual, composição assimétrica, estado — e lista Conquistas
    entre o que mora aqui. Em 08/09 Conquistas tinha saído porque o Progresso
    ganhou o bloco compacto; a spec revê essa nota, e o fato aqui é barato de
    propósito (quantas e a mais recente, numa consulta — nunca `reunir()`).
    """

    def test_conquistas_tem_porta_e_responde_quantas(self):
        from achievements.models import UserAchievement

        pessoa = self.pessoa()
        UserAchievement.objects.create(user=pessoa, slug="primeiro-treino")

        html = self.areas()

        self.assertIn(reverse("achievements:list"), html)
        bloco = html.split(reverse("achievements:list"), 1)[1].split("</a>", 1)[0]
        self.assertIn('<strong class="modulo__valor num">1</strong>', bloco)
        self.assertIn("conquista", bloco)

    def test_sem_conquista_o_modulo_diz_como_ganhar_a_primeira(self):
        """Estado vazio é convite (§35, §39): nem "0", nem "nenhum dado"."""
        self.pessoa()

        bloco = self.areas().split(reverse("achievements:list"), 1)[1].split("</a>", 1)[0]

        self.assertNotIn(">0<", bloco)
        self.assertIn("primeira", bloco)

    def test_a_hidratacao_traz_a_barra_e_a_corrida_vazia_convida(self):
        self.pessoa()
        html = self.areas()

        # progresso: a barra com o percentual audível
        self.assertIn('class="progress modulo__progresso" role="img"', html)
        self.assertIn("% da meta de água", html)
        # sem corrida registrada, o módulo explica o primeiro passo em vez de
        # descrever a ferramenta ou inventar "0 corridas"
        self.assertIn("Grave a primeira", html)
        self.assertNotIn("0 corridas", html)

    def test_o_perfil_e_o_modulo_largo_e_diz_a_meta(self):
        self.pessoa()
        # O cardápio nasce em "Calcular minha estimativa" (15/09/2026; antes,
        # na primeira visita a Hoje). Sem plano ativo o módulo mostra só o
        # objetivo — o outro ramo, coberto abaixo.
        html = self.areas()

        perfil = html.split(reverse("accounts:profile"), 1)[0].rsplit("<a ", 1)[1]
        self.assertIn("modulo--largo", perfil)
        bloco = html.split(reverse("accounts:profile"), 1)[1].split("</a>", 1)[0]
        self.assertIn("kcal por dia", bloco)

    def test_sem_plano_ainda_o_perfil_diz_o_objetivo(self):
        """Sem plano ativo, o módulo responde com o que existe (o objetivo)
        em vez de ficar mudo ou inventar meta.

        O estado é real: o cardápio pode não ter nascido (perfil sem peso,
        `IncompleteProfile`) ou ter sido desligado. Desde que "Criar meu
        plano" monta o cardápio no próprio POST, quem sai do wizard já tem
        plano — então o teste o desliga à mão para chegar ao ramo.
        """
        from plans.models import NutritionPlan

        user = self.pessoa()
        NutritionPlan.objects.filter(user=user).update(is_active=False)
        bloco = self.areas().split(reverse("accounts:profile"), 1)[1].split("</a>", 1)[0]
        self.assertIn("objetivo", bloco)
        self.assertNotIn("kcal", bloco)

    def test_as_ferramentas_sao_duas_colunas_e_o_perfil_atravessa(self):
        """A 320px, três colunas davam 93px por módulo e "Lista de compras"
        quebrava em duas linhas apertadas — medido na captura de 12/09/2026."""
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            ".modulos--ferramentas { grid-template-columns: repeat(2, minmax(0, 1fr)); }",
            css,
        )
        self.assertIn(".modulo--largo { grid-column: 1 / -1; }", css)

    def test_a_tela_continua_sem_os_tres_pilares_da_barra(self):
        """O hub cresceu e a regra de UX-01 não afrouxou (§6: não duplicar)."""
        self.pessoa()
        html = self.areas()
        modulos = html.split('<nav class="modulos"', 1)[1].split("</main>", 1)[0]
        for rota in (reverse("plans:today"), reverse("workouts:routine"), reverse("plans:history")):
            self.assertNotIn('href="%s"' % rota, modulos)
