"""B5 — /gestao/: dois nomes que nao existiam, e uma soma que nao fechava.

O que este arquivo protege sao quatro achados medidos no navegador, e tres
deles tem a mesma forma: um nome errado num template do Django nao levanta
erro. Ele vira string vazia, e a tela passa a mentir em silencio.

1. `pessoa.profile.onboarding_completo` — a propriedade do `Profile` chama-se
   `onboarding_complete`, em ingles. Medido no navegador: a coluna
   "Onboarding" da tela de Pessoas dizia "nao" nas 41 contas, valor distinto
   nenhum, enquanto o Painel dizia "Terminaram o onboarding — 36" sobre os
   MESMOS dados. Depois do conserto: 36 "sim" e 5 "nao", e as duas telas
   passaram a concordar.

2. `class="nota"` — nao existe uma unica regra `.nota` na folha de estilo.
   Medido: as notas do painel renderizavam a 16px em `rgb(16,23,21)`, MAIORES
   e mais escuras que os rotulos dos numeros que elas explicam (14,4px,
   cinza). A classe de nota de rodape do app e `.hint`, e ela existe.

3. "Com acesso administrativo" morava dentro da lista de classificacoes, acima
   do "Total". Toda conta tem exatamente uma classificacao, entao as quatro
   linhas SOMAM o total — medido, 35+3+1+2=41 — e a linha de staff, no meio
   delas e com a mesma cara, fazia a coluna dar 44.

4. A tela de Atividade so tinha os dias que o banco devolveu: um dia em que
   ninguem abriu o app sumia da tabela. E a janela pegava 31 dias enquanto a
   frase da tela dizia 30.
"""
import re
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from plans.models import MealLog

from .tests import BaseDoPainel

CSS = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"


class ACollunaDeOnboardingDizAVerdadeTests(BaseDoPainel):
    """A tela de Pessoas e o Painel leem o mesmo dado e precisam concordar."""

    def setUp(self):
        self.client.force_login(self.operador())

    def test_conta_com_onboarding_completo_aparece_como_sim(self):
        quem = self.pessoa("terminou@exemplo.com")
        self.perfil(quem, completo=True)

        html = self.client.get("/gestao/pessoas/").content.decode()

        linha = self._linha(html, quem.email)
        self.assertIn("<td>sim</td>", linha, linha)

    def test_conta_com_onboarding_pela_metade_aparece_como_nao(self):
        """O contra-controle. Uma coluna que dissesse "sim" para todo mundo
        passaria no teste acima e continuaria sem informar nada."""
        quem = self.pessoa("no-meio@exemplo.com")
        self.perfil(quem, completo=False)

        html = self.client.get("/gestao/pessoas/").content.decode()

        self.assertIn("<td>não</td>", self._linha(html, quem.email))

    def test_a_coluna_tem_os_dois_valores_na_mesma_tela(self):
        """O defeito nao era "diz nao para quem terminou": era uma coluna com
        UM valor so. Com as duas contas na tela, a coluna precisa variar."""
        self.perfil(self.pessoa("a@exemplo.com"), completo=True)
        self.perfil(self.pessoa("b@exemplo.com"), completo=False)

        html = self.client.get("/gestao/pessoas/").content.decode()
        corpo = html[html.index("<tbody>"): html.index("</tbody>")]

        self.assertIn("<td>sim</td>", corpo)
        self.assertIn("<td>não</td>", corpo)

    def test_a_lista_concorda_com_o_numero_do_painel(self):
        """As duas telas leem o mesmo fato, e foi a divergencia entre elas que
        denunciou o defeito: o painel dizia 36, a lista dizia zero."""
        for i in range(3):
            self.perfil(self.pessoa("ok%d@exemplo.com" % i), completo=True)
        self.perfil(self.pessoa("parcial@exemplo.com"), completo=False)

        lista = self.client.get("/gestao/pessoas/").content.decode()
        corpo = lista[lista.index("<tbody>"): lista.index("</tbody>")]
        painel = self.client.get("/gestao/").context["onboarding_completo"]

        self.assertEqual(corpo.count("<td>sim</td>"), painel)

    def _linha(self, html, email):
        inicio = html.index(email)
        return html[html.rindex("<tr>", 0, inicio): html.index("</tr>", inicio)]


class AsNotasDoPainelUsamAClasseQueExisteTests(BaseDoPainel):
    """Nota de rodape que renderiza maior que o dado nao e nota, e o defeito
    era um nome: `.nota` nao existe na folha de estilo."""

    def setUp(self):
        self.client.force_login(self.operador())
        self.css = CSS.read_text(encoding="utf-8")

    def test_a_classe_hint_existe_de_verdade(self):
        """A premissa. Trocar `nota` por outra classe inexistente nao
        consertaria nada, e o teste abaixo nao perceberia."""
        # `\b` NAO serve aqui: hifen e nao-palavra, entao `^\.hint\b` casa
        # tambem com `.hint-desativada` — a sabotagem que renomeia a classe
        # passou verde por causa disso. O seletor tem de terminar em `,` ou em
        # `{`, que e como uma regra CSS de fato fecha o nome.
        self.assertIsNotNone(
            re.search(r"(?m)^\.hint\s*[,{]", self.css),
            "a classe de nota do app sumiu da folha de estilo",
        )

    def test_nenhuma_tela_do_painel_usa_a_classe_que_nao_existe(self):
        for rota in ("/gestao/", "/gestao/pessoas/", "/gestao/atividade/"):
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertNotIn('class="nota"', html)

    def test_o_painel_continua_explicando_o_que_os_numeros_nao_sao(self):
        """As notas nao podiam sumir junto com a classe: e nelas que o painel
        diz que aquilo nao e retencao e que o peso do cadastro nao conta."""
        html = self.client.get("/gestao/").content.decode()

        self.assertIn("Isto não é retenção", html)
        self.assertIn("O peso do cadastro não conta", html)


class AsClassificacoesSomamOTotalTests(BaseDoPainel):
    """Uma coluna que termina em "Total" precisa fechar."""

    def setUp(self):
        self.client.force_login(self.operador())

    def test_a_lista_de_classificacoes_fecha_no_total(self):
        for i in range(3):
            self.pessoa("gente%d@exemplo.com" % i)

        contexto = self.client.get("/gestao/").context
        soma = sum(quantas for _, quantas in contexto["classificacao"])

        self.assertEqual(soma, contexto["contas"]["total"])

    def test_o_staff_nao_entra_na_lista_que_soma(self):
        html = self.client.get("/gestao/").content.decode()
        lista = html[html.index("data-list--total"): html.index("</dl>")]

        self.assertIn("Total", lista)
        self.assertNotIn("acesso administrativo", lista)

    def test_o_numero_de_staff_continua_na_tela(self):
        """Tirar da soma nao e esconder: o numero e operacional e fica."""
        html = self.client.get("/gestao/").content.decode()

        self.assertIn("acesso administrativo", html)
        self.assertIn("data-list--recorte", html)

    def test_o_recorte_tem_estilo_proprio(self):
        """Foi um nome sem CSS que criou o defeito das notas. Um modificador
        sem regra nenhuma repetiria o erro: sem separacao visual, a linha
        continua colada na soma e continua sendo lida como parte dela."""
        css = CSS.read_text(encoding="utf-8")

        regra = re.search(r"(?m)^\.data-list--recorte\s*\{([^}]*)\}", css)
        self.assertIsNotNone(regra, "o modificador ficou sem regra")
        self.assertIn("border-top", regra.group(1))


class AAtividadeMostraOsDiasZeradosTests(BaseDoPainel):
    """Dia em que ninguem abriu o app e informacao, nao ausencia.

    A tela de Metricas ja tinha decidido isso para as semanas — "buraco na
    serie e informacao" —, e o painel de gestao dizia o contrario: so listava
    os dias que o banco devolveu.
    """

    def setUp(self):
        self.client.force_login(self.operador())
        self.hoje = timezone.localdate()

    def _dias(self):
        return self.client.get("/gestao/atividade/").context["dias"]

    def test_a_janela_vem_inteira(self):
        from .views import AtividadeView

        dias = self._dias()

        self.assertEqual(len(dias), AtividadeView.DIAS)

    def test_a_janela_comeca_hoje_e_termina_vinte_e_nove_dias_atras(self):
        """"Últimos 30 dias" são 30 datas COM hoje dentro — nem 29 nem 31.

        A borda é onde este tipo de janela erra: `hoje - 30` dá 31 datas
        inclusive, e foi o que a tela entregava enquanto a frase dizia 30.
        """
        from .views import AtividadeView

        datas = [dia for dia, _ in self._dias()]

        self.assertEqual(len(datas), 30)
        self.assertEqual(datas[0], self.hoje)
        self.assertEqual(datas[-1], self.hoje - timedelta(days=29))
        self.assertEqual(AtividadeView.DIAS, 30)

    def test_nao_falta_nenhum_dia_entre_as_pontas(self):
        """Contar 30 linhas não basta: 30 datas com um buraco e uma repetida
        também dariam 30. A sequência precisa ser contínua."""
        datas = [dia for dia, _ in self._dias()]

        esperadas = [self.hoje - timedelta(days=n) for n in range(30)]
        self.assertEqual(datas, esperadas)

    def test_a_janela_tem_o_tamanho_que_a_tela_promete(self):
        """Ela pegava 31 dias com a frase dizendo 30 — uma linha a mais do que
        o texto prometia."""
        resposta = self.client.get("/gestao/atividade/")

        self.assertEqual(len(resposta.context["dias"]), resposta.context["janela"])

    def test_o_dia_sem_ninguem_aparece_zerado_entre_os_outros(self):
        quem = self.pessoa("intermitente@exemplo.com")
        for atras in (0, 2):
            MealLog.objects.create(
                user=quem, date=self.hoje - timedelta(days=atras),
                status="eaten", slot_name="almoço",
            )

        por_data = dict(self._dias())
        vazio = self.hoje - timedelta(days=1)

        self.assertIn(vazio, por_data, "o dia sem registro sumiu da tabela")
        self.assertEqual(por_data[vazio], [0, 0, 0, 0])
        self.assertEqual(por_data[self.hoje][0], 1)

    def test_os_dias_vem_do_mais_recente_para_o_mais_antigo(self):
        datas = [dia for dia, _ in self._dias()]

        self.assertEqual(datas, sorted(datas, reverse=True))
        self.assertEqual(datas[0], self.hoje)

    def test_sem_registro_nenhum_a_tela_diz_isso_em_vez_de_trinta_zeros(self):
        """O estado vazio precisou de uma pergunta nova.

        Com a janela inteira, `dias` tem sempre 30 itens — `{% if dias %}`
        seria verdadeiro num banco recem-criado, o estado vazio viraria codigo
        morto e a tela responderia com trinta linhas de zero.
        """
        resposta = self.client.get("/gestao/atividade/")

        self.assertFalse(resposta.context["tem_atividade"])
        self.assertContains(resposta, "Ninguém registrou nada")
        self.assertNotContains(resposta, "<tbody>")

    def test_com_um_registro_so_a_tabela_aparece(self):
        """O controle. Um `tem_atividade` sempre falso esconderia a tabela
        para sempre e passaria no teste acima."""
        MealLog.objects.create(
            user=self.pessoa("um@exemplo.com"), date=self.hoje,
            status="eaten", slot_name="almoço",
        )

        resposta = self.client.get("/gestao/atividade/")

        self.assertTrue(resposta.context["tem_atividade"])
        self.assertContains(resposta, "<tbody>")

    def test_preencher_a_janela_nao_custa_consulta_nenhuma(self):
        """O painel mede custo desde a primeira versão. Trinta datas em
        memória não podem virar trinta idas ao banco."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for i in range(8):
            MealLog.objects.create(
                user=self.pessoa("carga%d@exemplo.com" % i),
                date=self.hoje - timedelta(days=i % 5),
                status="eaten", slot_name="almoço",
            )

        with CaptureQueriesContext(connection) as consultas:
            self.client.get("/gestao/atividade/")
        com_oito = len(consultas.captured_queries)

        for i in range(8, 24):
            MealLog.objects.create(
                user=self.pessoa("carga%d@exemplo.com" % i),
                date=self.hoje - timedelta(days=i % 17),
                status="eaten", slot_name="almoço",
            )

        with CaptureQueriesContext(connection) as consultas:
            self.client.get("/gestao/atividade/")

        self.assertEqual(len(consultas.captured_queries), com_oito)


class ASuperficieDeTabelaEMaisLargaTests(BaseDoPainel):
    """O painel não é o app, e a tabela dele precisa de largura.

    Medido a 1280px, antes: o container ficava com 480px e a tabela de Pessoas
    rolava dentro de uma janela de 440 — três colunas de sete por vez, na
    máquina em que um painel de fato é lido. Depois: container de 960, janela
    de 918, as sete colunas sem rolagem nenhuma.
    """

    def setUp(self):
        self.client.force_login(self.operador())
        self.css = CSS.read_text(encoding="utf-8")

    def test_as_telas_de_tabela_pedem_a_superficie_larga(self):
        for rota in ("/gestao/pessoas/", "/gestao/atividade/"):
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertIn('class="container gestao-tabela"', html)

    def test_o_painel_continua_na_largura_do_app(self):
        """O contra-controle, e não é simetria por simetria: os cartões do
        Painel são pares rótulo/número em `space-between`, e a 920px o número
        ficaria a 900px do próprio rótulo."""
        html = self.client.get("/gestao/").content.decode()

        self.assertNotIn("gestao-tabela", html)

    def test_a_largura_maior_nao_pode_valer_no_celular(self):
        """A garantia de que 375 e 430 não mudaram é ESTRUTURAL, não medida:
        `max-width` maior que a tela não faz nada. Se alguém trocar a regra por
        `width` ou por `min-width`, o celular passa a rolar na horizontal — e é
        isso que este teste proíbe.
        """
        regra = re.search(
            r"(?m)^\.container\.gestao-tabela\s*\{([^}]*)\}", self.css
        )

        self.assertIsNotNone(regra, "a regra da superfície larga sumiu")
        corpo = regra.group(1)
        self.assertIn("max-width", corpo)
        self.assertNotIn("min-width", corpo)
        self.assertNotIn("width:", corpo.replace("max-width:", ""))

    def test_a_tabela_continua_rolando_por_dentro_e_nunca_a_pagina(self):
        """A regra do app inteiro, e a tela larga não a revoga: no celular a
        tabela continua maior que a janela, e quem rola é o container."""
        regra = re.search(r"(?m)^\.tabela-rolavel\s*\{([^}]*)\}", self.css)

        self.assertIsNotNone(regra)
        self.assertIn("overflow-x: auto", regra.group(1))
        self.assertIn("min-width: 0", regra.group(1))
