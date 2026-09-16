# -*- coding: utf-8 -*-
"""A catraca do sistema visual: a dívida de valor cru pode cair, nunca subir.

POR QUE CATRACA, E NÃO PROIBIÇÃO

O jeito óbvio de travar um eixo de design é proibir valor cru — é o que
`config.tests` já faz com `border-radius`, e funciona: **zero** raios crus no
arquivo inteiro.

Isso só foi possível porque a escala de quina nasceu junto com as primeiras
quinas. Texto e espaço não tiveram essa sorte: quando os tokens foram criados,
em 05/09/2026, já existiam 214 declarações de `font-size` e 458 valores de
espaçamento escritos à mão. Proibir de uma vez exigiria reescrever 6.000 linhas
num commit só, que é exatamente o "troca gigantesca" que quebra 30 telas.

Então a régua é outra: **a dívida tem teto, e o teto é o que ela vale hoje.**
Tela nova que escreva `font-size: .83rem` empurra o número para cima e fica
vermelha. Migração empurra para baixo, e aí o número novo é registrado aqui.

É a única forma que faz a promessa "telas futuras nascem consistentes" ser
cumprida por máquina em vez de por lembrança.

QUANDO ESTE ARQUIVO FICAR VERMELHO

Se subiu: você escreveu valor cru. Use um degrau de `--texto-*` ou `--espaco-*`.
Se nenhum degrau serve, o degrau que falta precisa nascer com justificativa —
e não com um valor solto.

Se DESCEU: parabéns, você migrou. Baixe os números abaixo para o novo valor.
Deixar o teto velho aceitaria dívida que já não existe, e a catraca pararia de
apertar.

O QUE ESTA CATRACA NÃO PEGA

Dito porque uma trava com buraco não declarado é pior que nenhuma — quem confia
nela para de olhar:

- **`font-size: 83%`** e outras medidas relativas em porcentagem;
- ~~**`style=` no template.**~~ Deixou de ser buraco: 05/09/2026, quando as
  intenções de espaçamento ganharam nome e
  `OEspacamentoNaoVoltaParaODentroDoHTMLTests`, no fim deste arquivo, passou a
  proibir estático em template do app. Duas exceções declaradas lá: valor
  calculado pelo servidor e template de e-mail;
- **um arquivo `.css` novo.** O caminho aqui é fixo em `app.css`, e todos os
  leitores de CSS deste repositório abrem esse arquivo por nome;
- **a direção.** `TETO_*` é constante editável, e subir o teto é a mesma edição
  de uma linha que baixá-lo. Esta catraca pega o autor distraído, não o
  determinado — e a diferença aparece na revisão do commit, não aqui.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

CSS = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"

#: Medido em 05/09/2026, depois de migrar os 251 valores que casavam
#: EXATAMENTE com um degrau. A migração exata foi escolhida de propósito: ela
#: não move um pixel, e a prova está no commit — a assinatura de estilo
#: computado de `/treino/` (461 elementos) ficou idêntica, 849639245 antes e
#: depois, com o CSS servido conferido para não medir cache velho.
#: Desceu para 141 na V3: a família monoespaçada saiu de 34 regras de métrica,
#: e com ela os `font-size` crus que só existiam para compensar a mono
#: desenhar maior que a fonte de texto no mesmo tamanho. Desceu de novo quando
#: `.exercise__cue` saiu — a dica virou componente com token. A catraca só
#: desce: quando a dívida cai, o teto cai junto, senão ela volta sem ninguém ver.
#: 134 no REDESIGN V1: o aviso da tela de corridas trocou `.85rem` cru pelo
#: degrau `--texto-sm` ao virar ressalva, e a oferta que nasceu acima dele já
#: nasceu na escala.
#: 133 quando `.agora__sessao` saiu: o nome da sessão virou sobretítulo com
#: token, e a regra antiga levava embora o último `1.28rem` cru dela.
#: 132 quando a sanfona das fichas da semana foi removida: o paredão saiu da
#: tela de Treino, `.session__name` ficou sem elemento e levou junto o
#: `font-size: 1.08rem` cru dela.
#: 120 no REDESIGN DO FLUXO DE TREINO: `_exercicio.html`, `_drawer.html` e
#: `_cronometro.html` saíram do repositório sem `{% include %}` nenhum, e com
#: eles 645 linhas de CSS das famílias `.exercise`, `.drawer` e `.rest-timer`.
#: Doze `font-size` crus moravam ali — os números do drawer, os rótulos do
#: cronômetro e o cabeçalho do cartão. A lista que entrou no lugar
#: (`.ficha-item`) nasceu inteira na escala de tokens.
#: 119 em 15/09/2026: `.anatomia__botao { font-size: .84rem }` saiu com o
#: segundo player da execução (um player por página; músculos como texto).
TETO_FONT_SIZE_CRU = 119
#: 287 na V3: a reconstrução da linha de metadados do hero trocou dois
#: espaçamentos crus por degraus da escala. Desce junto, pelo mesmo motivo.
#: 276 no REDESIGN V1: o separador do resumo do dia deixou de ser um "·" com
#: `margin-right: .3rem` e virou régua de 1px com `padding-left` na escala.
#: A troca conserta um desalinhamento real — o "·" era inline dentro de um
#: item `display: block` e roubava uma linha inteira das três últimas colunas.
#: 275 quando o tile de Progresso deixou de ser cartão dentro de cartão: o
#: padding dele virou degrau da escala junto com a moldura que saiu.
#: 270 no REDESIGN V2: a barra de baixo flutuante, o aviso do demo sem caixa e
#: o bloco de água em volta do anel nasceram todos na escala, e substituíram
#: paddings crus que vinham do desenho antigo.
#: 268 quando o saldo do painel do dia deixou de ser pílula: a cápsula levava
#: padding cru dos dois eixos, e o filete que a substituiu usa a escala.
#: 267 quando o grupo de carga da tela de execução perdeu a caixa: o padding
#: cru dele saiu junto com o fundo e a borda.
#: 262 com a sanfona das fichas da semana: `.ficha__resumo`, `.ficha__corpo`,
#: `.session__head` e companhia ficaram sem elemento quando as sessões viraram
#: cartões que levam à ficha, e os cinco espaçamentos crus delas saíram junto.
#: A ressalva da divisão, que entrou na mesma rodada, é toda em tokens.
#: 249 no mesmo corte, e pelo mesmo motivo: treze espaçamentos crus saíram
#: junto com as três famílias. A catraca só desce.
#: 247 com o POSTER da execução (13/09/2026): `.agora__media` e `.agora__cue`
#: saíram — a demonstração virou a faixa `.demo`, que nasceu na escala — e
#: com elas dois `margin-bottom: .55rem` crus.
#: 246 com o vão dos botões de água (14/09/2026): `gap: .4rem` era 6,4 px
#: entre três alvos tocados de pé (MOB-13), e virou `var(--espaco-3)`.
#: 244 em 15/09/2026: `.anatomia { margin-bottom: .8rem }` e
#: `.anatomia__botao { gap: .45rem }` saíram com o segundo player.
TETO_ESPACO_CRU = 244


def sem_comentarios(texto):
    """O CSS sem comentários.

    Obrigatório aqui: os comentários deste arquivo DISCUTEM os valores que a
    asserção procura — o bloco que explica a escala cita `.74`, `.75` e `.76`
    por extenso. Contar comentário inflaria a dívida e o teto passaria a
    proteger prosa.
    """
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


#: Unidades que contam como medida crua. `%` fica de fora e isso é limitação
#: declarada, não descuido — ver `O QUE ESTA CATRACA NÃO PEGA`.
UNIDADE = r"(?:rem|em|px|pt)"


def _valores(declaracoes):
    """Os valores crus de uma lista de declarações, VALOR A VALOR.

    A primeira versão desta função descartava a declaração inteira quando ela
    continha `var()`. Parecia razoável e estava errado de um jeito que se
    agrava sozinho: `padding: .83rem var(--espaco-3)` ficava INVISÍVEL.

    E é exatamente a forma que uma migração parcial produz. O commit que criou
    esta catraca migrou só os valores que casavam com um degrau, e com isso
    fabricou 42 declarações mistas escondendo 46 valores crus — a régua nova
    nasceu cega para a dívida que ela própria acabara de criar.

    Contar valor a valor é o conserto, e ele subiu o teto de 242 para o número
    real. Um teto menor que a dívida não é rigor: é uma folga disfarçada de
    precisão.
    """
    return [v for d in declaracoes for v in re.findall(r"([0-9.]+)" + UNIDADE, d)]


def font_sizes_crus(css):
    """Tamanhos de texto escritos à mão, inclusive dentro de `calc()` e do
    atalho `font:`, que a primeira versão não via."""
    diretos = re.findall(r"font-size:\s*([^;{}]+)[;}]", css)
    atalho = re.findall(r"(?<![-a-z])font:\s*([^;{}]+)[;}]", css)
    return _valores(diretos + atalho)


def espacos_crus(css):
    """Espaçamentos escritos à mão, em qualquer unidade e mesmo ao lado de um
    `var()` na mesma declaração."""
    return _valores(
        re.findall(
            r"(?:padding|margin|gap|row-gap|column-gap)[a-z-]*:\s*([^;{}]+)[;}]", css
        )
    )


class ACatracaDoSistemaVisualTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_a_divida_de_tamanho_de_texto_nao_cresce(self):
        atual = len(font_sizes_crus(self.css))

        self.assertLessEqual(
            atual,
            TETO_FONT_SIZE_CRU,
            f"{atual} tamanhos de texto crus, e o teto é {TETO_FONT_SIZE_CRU}. "
            "Use um degrau de --texto-xs..3xl.",
        )

    def test_a_divida_de_espacamento_nao_cresce(self):
        atual = len(espacos_crus(self.css))

        self.assertLessEqual(
            atual,
            TETO_ESPACO_CRU,
            f"{atual} espaçamentos crus, e o teto é {TETO_ESPACO_CRU}. "
            "Use um degrau de --espaco-1..7.",
        )

    def test_o_teto_registrado_nao_esta_folgado(self):
        """O teto tem de ser o valor REAL, não um número redondo com folga.

        Sem isto, alguém que migrasse 40 declarações deixaria o teto velho, e a
        catraca aceitaria 40 valores crus novos sem reclamar — que é o oposto
        de catraca. A folga máxima é zero: o teto É a dívida.
        """
        self.assertEqual(len(font_sizes_crus(self.css)), TETO_FONT_SIZE_CRU)
        self.assertEqual(len(espacos_crus(self.css)), TETO_ESPACO_CRU)

    def test_os_degraus_existem_e_sao_usados(self):
        """Escala declarada e não usada é decoração.

        `ImpeccableStyleTests` já recusa token órfão, e este teste diz a MESMA
        coisa de outro ângulo: aqui a asserção é sobre o eixo inteiro, para que
        apagar um degrau no meio da escala apareça como buraco e não como
        token a menos.
        """
        for degrau in ("xs", "sm", "md", "base", "lg", "xl", "2xl", "3xl"):
            with self.subTest(degrau=f"--texto-{degrau}"):
                self.assertIn(f"--texto-{degrau}:", self.css)
                self.assertIn(f"var(--texto-{degrau})", self.css)

        for degrau in range(1, 8):
            with self.subTest(degrau=f"--espaco-{degrau}"):
                self.assertIn(f"--espaco-{degrau}:", self.css)
                self.assertIn(f"var(--espaco-{degrau})", self.css)

    def test_o_piso_de_onze_pixels_continua_no_menor_degrau(self):
        """`--texto-xs` é o menor degrau, e ele carrega uma regra do produto:
        texto de interface nunca abaixo de 11px. Se alguém baixar este degrau,
        baixa o piso de legibilidade do app inteiro de uma vez."""
        casou = re.search(r"--texto-xs:\s*([0-9.]+)rem", self.css)

        self.assertIsNotNone(casou, "--texto-xs sumiu da escala")
        self.assertGreaterEqual(float(casou.group(1)) * 16, 11.0)


class PapelDeDialogoSoEmDialogoDeVerdadeTests(SimpleTestCase):
    """`role="dialog"` promete foco preso. Quem não prende, não promete.

    O convite de instalação declarava `role="dialog"` sendo uma `<div>` sem
    `aria-modal`, sem `<dialog>` nativo e sem gerenciar foco. Medido no
    navegador com o convite aberto: 3 elementos focáveis dentro dele e **68
    ainda alcançáveis por Tab do lado de fora**.

    O leitor de tela anuncia "diálogo" e o teclado sai andando pela página —
    papel que promete o que o comportamento não cumpre é pior que papel
    nenhum, porque ele desliga o cuidado de quem confia no anúncio.

    Não prender foco ali é DECISÃO deste projeto, escrita também no cartão de
    conquista: um convite não rouba o que a pessoa está fazendo. Então o
    conserto é o papel, não o comportamento.

    A regra que fica: `role="dialog"` só em `<dialog>` de verdade, que prende
    foco pelo navegador quando aberto com `showModal()`.
    """

    TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

    def test_nenhuma_div_se_declara_dialogo(self):
        culpados = []
        for arquivo in self.TEMPLATES.rglob("*.html"):
            texto = arquivo.read_text(encoding="utf-8")
            for trecho in re.findall(r"<(\w+)[^>]*?\brole=[\"']dialog[\"'][^>]*>", texto):
                if trecho.lower() != "dialog":
                    culpados.append(f"{arquivo.name}: <{trecho} role=\"dialog\">")

        self.assertEqual(
            culpados,
            [],
            "role=\"dialog\" fora de um <dialog> nativo — ou prenda o foco, ou "
            "use um papel que descreva o que a peça faz: " + "; ".join(culpados),
        )


class NumeroDeMetricaNaoQuebraNoMeioTests(SimpleTestCase):
    """Número grande em coluna estreita não pode partir em duas linhas.

    O caso que motivou: `.corrida-numero__valor` era `1.9rem` fixo em três
    colunas de 90px a 375px. Seis caracteres ocupam 101px, então `100:00` — uma
    corrida de 1h40 — quebrava no meio, e `123,45` também. Maratona leva de três
    a cinco horas: o caso é comum, não exótico.

    POR QUE NENHUMA RÉGUA EXISTENTE PEGOU

    `overflow-x: hidden` no `html`/`body` faz "nada rola na horizontal"
    continuar verde: o texto QUEBRA em vez de vazar, então não há rolagem para
    detectar. E `scrollWidth` também não acusa, pelo mesmo motivo — só medir a
    ALTURA do elemento revela (33px contra 67px).

    Por isso a guarda é sobre a DECLARAÇÃO e não sobre o sintoma: um número que
    declara `white-space: nowrap` não tem como quebrar, e aí a única falha
    possível vira estouro, que as réguas de rolagem já cobrem.
    """

    #: Valores que ocupam a coluna inteira. São os que a tela mostra de verdade:
    #: um cronômetro passando de 99 minutos e uma distância de três dígitos.
    VALORES_LONGOS = ("100:00", "123,45")

    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def _regra(self, seletor):
        casou = re.search(
            r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", self.css
        )
        return casou.group(1) if casou else None

    def test_o_numero_da_corrida_nao_quebra(self):
        corpo = self._regra(".corrida-numero__valor")

        self.assertIsNotNone(corpo, "a regra .corrida-numero__valor sumiu")
        self.assertIn(
            "white-space: nowrap",
            corpo,
            f"sem nowrap, {self.VALORES_LONGOS} partem em duas linhas a 375px",
        )

    def test_o_tamanho_do_numero_da_corrida_cede_em_tela_estreita(self):
        """`min()` com `vw` é o que faz o número caber a 320px.

        Um tamanho fixo que caiba em 320px seria pequeno demais no desktop, e um
        que sirva ao desktop quebra no celular estreito. O teto é o degrau da
        escala; o `vw` só entra quando a tela não comporta o teto.
        """
        corpo = self._regra(".corrida-numero__valor")

        self.assertIsNotNone(corpo)
        self.assertRegex(
            corpo,
            r"font-size:\s*min\(\s*var\(--texto-2xl\)\s*,\s*[\d.]+vw\s*\)",
            "o tamanho voltou a ser fixo — a 320px ele não cabe",
        )

    def test_a_regra_lida_e_mesmo_a_da_corrida(self):
        """Controle positivo: sem isto, um seletor que não casa deixaria os dois
        testes acima verdes por não encontrar nada que contrarie."""
        corpo = self._regra(".corrida-numero__valor")

        self.assertIsNotNone(corpo)
        self.assertIn("font-variant-numeric: tabular-nums", corpo)
        # 750 desde 16/09/2026: é o peso do número em todo tile (`.tile__value`,
        # `.balance__value`, `.agua__valor b`); 760 era um degrau só destes dois.
        self.assertIn("font-weight: 750", corpo)

        self.assertIsNone(
            self._regra(".seletor-que-nao-existe-em-lugar-nenhum"),
            "o leitor de regra devolve corpo para seletor inexistente",
        )


class NumeroDoTileNaoQuebraNoMeioTests(SimpleTestCase):
    """O valor do tile é `<strong>`, e `strong` herda `overflow-wrap: anywhere`
    do seletor global (nome de alimento e de exercício precisam quebrar dentro
    da palavra). Número não: "12.345" partido em "12.3 / 45" é outro número.

    Medido em 16/09/2026 a 390 px: 3 colunas de 97 px, caixa de 74 px; o maior
    valor real ("10000" ml, "20000" kg) ocupa 61,6 px. A guarda é sobre a
    DECLARAÇÃO, como a da corrida: `nowrap` não tem como quebrar, e o estouro
    — que nenhum valor real produz — é assunto de formatação."""

    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def _regra(self, seletor):
        casou = re.search(r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", self.css)
        return casou.group(1) if casou else None

    def test_o_valor_do_tile_nao_quebra(self):
        corpo = self._regra(".tile__value")
        self.assertIsNotNone(corpo, "a regra .tile__value sumiu")
        self.assertIn("white-space: nowrap", corpo)
        self.assertIn("overflow-wrap: normal", corpo)

    def test_a_regra_lida_e_mesmo_a_do_tile(self):
        corpo = self._regra(".tile__value")
        self.assertIsNotNone(corpo)
        self.assertIn("font-variant-numeric: tabular-nums", corpo)


class MetricaNaoDependeDoTemplateParaSerTabularTests(SimpleTestCase):
    """A tipografia de um número é do CSS, nunca do HTML que o escreve.

    `.fim__valor` e `.conquistas__numero` dependiam de o template lembrar de
    escrever `class="... num"`. Um bloco novo copiado sem o `num` ficava
    proporcional, e o defeito só aparecia quando o número atualizava e dançava
    de lugar — que é exatamente o que `tabular-nums` existe para impedir.

    O INVARIANTE NÃO MUDOU NA V3; a implementação dele mudou. Antes a marca de
    "isto é métrica" era a família monoespaçada, e ela cobrava caro: zero
    cortado, peso aparente maior que o do rótulo ao lado, e um "19:00" que lia
    como saída de terminal dentro de uma interface que quer parecer aplicativo.
    Agora a marca é `font-variant-numeric: tabular-nums` na fonte de texto —
    que é o que sempre resolveu o problema real, o alinhamento.

    `.num` continua no HTML e continua útil: ele marca "isto é número" para
    quem lê o template. O que não pode é o CSS DEPENDER dele.
    """

    #: Toda classe que é o VALOR de uma métrica. Não inclui rótulos — eles são
    #: texto e usam a fonte de texto de propósito.
    VALORES = (
        ".tile__value",
        ".fim__valor",
        ".equation__value",
        ".corrida-numero__valor",
        ".conquistas__numero",
        ".semana__valor",
        ".balance__value",
        ".ring__value",
        ".gole__valor",
    )

    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def _regra(self, seletor):
        casou = re.search(
            r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", self.css
        )
        return casou.group(1) if casou else None

    def test_todo_valor_de_metrica_declara_o_proprio_tratamento(self):
        for seletor in self.VALORES:
            with self.subTest(seletor=seletor):
                corpo = self._regra(seletor)
                self.assertIsNotNone(corpo, f"a regra {seletor} sumiu")
                self.assertIn(
                    "tabular-nums",
                    corpo,
                    f"{seletor} depende do `num` do template para alinhar",
                )

    def test_nenhuma_metrica_volta_para_a_monoespacada(self):
        """CONTROLE da decisão: a mono saiu da interface na V3, e voltar com
        ela numa métrica traria de volta o zero cortado e o desalinhamento de
        peso contra o rótulo vizinho."""
        for seletor in self.VALORES:
            with self.subTest(seletor=seletor):
                corpo = self._regra(seletor) or ""
                self.assertNotIn("var(--font-mono)", corpo)

    def test_todo_valor_de_metrica_e_tabular(self):
        """Sem `tabular-nums` o número muda de largura ao atualizar, e um
        cronômetro que dança é ilegível em movimento."""
        for seletor in self.VALORES:
            with self.subTest(seletor=seletor):
                corpo = self._regra(seletor)
                self.assertIsNotNone(corpo)
                self.assertIn("font-variant-numeric: tabular-nums", corpo)

    def test_a_lista_de_valores_nao_esta_vazia_nem_casando_com_qualquer_coisa(self):
        """Controle positivo: se `_regra` devolvesse corpo para qualquer
        seletor, os dois testes acima passariam sem inspecionar nada."""
        self.assertGreaterEqual(len(self.VALORES), 9)
        self.assertIsNone(self._regra(".metrica-que-nao-existe"))


class AEscalaDeEmpilhamentoTests(SimpleTestCase):
    """A elevação é vocabulário, e não nove números escritos à mão.

    Era a única escala do sistema visual sem token: 1, 2, 20, 25, 26, 28, 30,
    40, 40 e 60 espalhados, a ordem em lugar nenhum, e DOIS componentes
    disputando o mesmo 40. A falta disto custou um defeito nesta base — o
    painel do mapa declarava "40, acima da tabbar, que é 30" e perdia, porque
    ele vive dentro da barra de cima, que cria contexto de empilhamento.

    A régua olha o CSS: quem empilha usa a escala, e as exceções são nomeadas
    aqui uma a uma, com o motivo. Uma exceção nova entra por decisão, não por
    esquecimento — que é a mesma disciplina de `TouchFeedbackTests.ISENTOS`.
    """

    #: Os degraus, do fundo para a frente. A ordem é a do produto.
    ESCALA = (
        "--camada-conteudo",
        "--camada-barra-topo",
        "--camada-flutuante",
        "--camada-navegacao",
        "--camada-aviso",
        "--camada-bloqueio",
    )

    #: `z-index` que NÃO usa a escala, e por quê.
    ISENTOS = {
        "body::before": "o halo fica ATRÁS de tudo; -1 não é um degrau da escala",
    }

    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def degraus(self):
        """Os degraus da escala, lidos do `:root`.

        Leitor próprio, e não o `_tokens` de `config.tests`: aquele mora noutro
        módulo e existe para COR. Importar entre arquivos de teste amarraria
        duas réguas que mudam por motivos diferentes.
        """
        trecho = self.css.split(":root {", 1)[1].split("}", 1)[0]
        valores = {}
        for linha in trecho.splitlines():
            linha = linha.strip()
            if linha.startswith("--camada") and ":" in linha:
                nome, valor = linha.split(":", 1)
                valores[nome.strip()] = valor.split(";")[0].strip()
        return valores

    def test_a_escala_existe_e_sobe(self):
        tokens = self.degraus()
        valores = []
        for nome in self.ESCALA:
            with self.subTest(token=nome):
                self.assertIn(nome, tokens, "degrau ausente da escala")
                valores.append(int(tokens[nome]))

        self.assertEqual(valores, sorted(valores), valores)
        self.assertEqual(len(set(valores)), len(valores), "dois degraus com o mesmo valor")

    def test_todo_z_index_usa_a_escala_ou_esta_declarado_como_excecao(self):
        linhas = self.css.split(chr(10))
        fora = []
        for i, linha in enumerate(linhas):
            achado = re.search(r"z-index:\s*([^;]+);", linha)
            if not achado or "var(--camada" in achado.group(1):
                continue
            seletor = ""
            for j in range(i, max(0, i - 30), -1):
                if "{" in linhas[j]:
                    seletor = linhas[j].split("{")[0].strip()
                    if seletor:
                        break
            if not any(isento in seletor for isento in self.ISENTOS):
                fora.append("%s → %s" % (seletor[:60], achado.group(1).strip()))

        self.assertEqual(fora, [], "z-index fora da escala e sem isenção declarada")

    def test_nada_cobre_a_barra_de_navegacao(self):
        """As duas barras NÃO estão no mesmo degrau, e isso é regra de produto.

        A primeira versão desta escala colapsou as duas num degrau só, o que
        inverteu o par convite/navegação — e `push/tests.py` pegou: o convite
        de instalação cobriu a barra uma vez, e não pode cobrir de novo. A
        barra de cima pode ser coberta por um flutuante; a de baixo, não.
        """
        tokens = self.degraus()

        self.assertLess(
            int(tokens["--camada-barra-topo"]), int(tokens["--camada-flutuante"])
        )
        self.assertLess(
            int(tokens["--camada-flutuante"]), int(tokens["--camada-navegacao"])
        )
        for seletor, degrau in ((".app-bar {", "--camada-barra-topo"),
                                (".tabbar {", "--camada-navegacao")):
            with self.subTest(seletor=seletor):
                bloco = self.css.split(seletor, 1)[1].split("}", 1)[0]
                self.assertIn("var(%s)" % degrau, bloco)

    def test_o_que_bloqueia_a_tela_fica_acima_do_que_so_avisa(self):
        """A ordem não é estética: a montagem do plano toma a tela inteira e
        não pode ser coberta pelo cartão de conquista, que é um aviso."""
        tokens = self.degraus()

        self.assertGreater(
            int(tokens["--camada-bloqueio"]), int(tokens["--camada-aviso"])
        )
        self.assertGreater(
            int(tokens["--camada-aviso"]), int(tokens["--camada-flutuante"])
        )


class OEspacamentoNaoVoltaParaODentroDoHTMLTests(SimpleTestCase):
    """Espaçamento mora no CSS, com nome. Não em `style=` espalhado.

    Medido antes desta régua: 23 `style=` estáticos em 12 templates, usando
    `1.25rem`, `1rem`, `.9rem`, `.8rem`, `.6rem` e `0` para CINCO intenções
    distintas — e três daqueles valores nem estavam na escala de espaçamento.
    O mesmo rodapé de cartão de entrada aparecia com dois valores diferentes
    em telas irmãs.

    A saída não foi utilitária genérica (`.mt-4` e parentes): utilitária só
    muda o lugar onde o número arbitrário é escrito. Cada intenção ganhou nome
    — `.form__nota`, `.acao-solta`, `.chip-row--conteudo`, `.acoes-empilhadas`,
    `.nota-do-botao` — e o valor passou a ser um só.

    DUAS EXCEÇÕES, e as duas são obrigatórias:

    - **valor calculado pelo servidor** (`style="width: {{ pct }}%"`): não há
      classe possível para um número que muda a cada resposta;
    - **template de e-mail**: cliente de e-mail não lê CSS externo nem
      variável CSS. Ali o estilo inline com hex literal é a técnica correta, e
      proibi-lo quebraria o e-mail de recuperação de senha.
    """

    RAIZ_TEMPLATES = CSS.parent.parent.parent / "templates"

    def templates_do_app(self):
        for caminho in sorted(self.RAIZ_TEMPLATES.rglob("*.html")):
            relativo = str(caminho).replace("\\", "/")
            if "email" in caminho.name or "/admin/" in relativo:
                continue
            yield caminho

    def test_nenhum_template_do_app_carrega_estilo_estatico(self):
        fora = []
        for caminho in self.templates_do_app():
            texto = caminho.read_text(encoding="utf-8")
            for achado in re.finditer(r'style="([^"]*)"', texto):
                valor = achado.group(1)
                if "{{" in valor or "{%" in valor:
                    continue
                fora.append("%s → %s" % (caminho.name, valor))

        self.assertEqual(fora, [], "espaçamento voltou para dentro do HTML")

    def test_o_controle_positivo_le_arquivo_de_verdade(self):
        """A régua acima só vale se o caminho de leitura funcionar.

        A primeira versão deste controle rodava o regex contra uma STRING
        LOCAL — `re.search(padrao, 'style="..."')` — que é verdadeira por
        construção. Com `read_text()` devolvendo vazio, com o filtro de
        exclusão engolindo tudo, ou com o corpo do laço apagado, ele
        continuaria verde. Uma revisão adversarial pegou.

        Agora ele percorre o MESMO caminho da régua — arquivo em disco, mesma
        leitura, mesmo regex — sobre o template de e-mail, que tem estilo
        inline de propósito e é o único excluído por conteúdo.
        """
        arquivos = list(self.templates_do_app())
        self.assertGreater(len(arquivos), 30, "a varredura parou de achar template")

        email = self.RAIZ_TEMPLATES / "accounts" / "email_senha.html"
        achados = [
            m.group(1)
            for m in re.finditer(r'style="([^"]*)"', email.read_text(encoding="utf-8"))
            if "{{" not in m.group(1)
        ]

        self.assertGreater(len(achados), 3, "a leitura de arquivo parou de enxergar")
        self.assertNotIn(email, arquivos, "o e-mail tem de ficar FORA da régua")

    def test_o_estilo_calculado_continua_permitido(self):
        """A barra de progresso não tem outro jeito: a largura é o dado."""
        hoje = (self.RAIZ_TEMPLATES / "plans" / "today.html").read_text(encoding="utf-8")

        self.assertIn("style=\"width: {{", hoje)

    def test_o_email_continua_com_estilo_inline(self):
        """Proibir estilo inline no e-mail quebraria o e-mail: cliente de
        e-mail não lê CSS externo. A exceção é técnica, não preguiça."""
        email = (
            self.RAIZ_TEMPLATES / "accounts" / "email_senha.html"
        ).read_text(encoding="utf-8")

        self.assertIn('style="', email)
        self.assertIn("#0c6b40", email)

    def test_as_intencoes_nomeadas_existem_no_css(self):
        css = sem_comentarios(CSS.read_text(encoding="utf-8"))

        for classe in (
            ".form__nota",
            ".form__nota--perto",
            ".acao-solta",
            ".chip-row--conteudo",
            ".acoes-empilhadas",
            ".acao-com-nota",
            ".nota-do-botao",
            ".card--prosa",
        ):
            with self.subTest(classe=classe):
                self.assertIn(classe, css)

    def test_toda_intencao_nomeada_e_usada_por_algum_template(self):
        """Classe que não é usada é CSS morto vendido como sistema.

        `.chip-row--inicio` nasceu neste lote e não fazia nada: `.chip-row`
        nunca declarou `justify-content`, e `flex-start` já é o valor inicial
        de um container flex — a classe e o `style=` que ela substituiu eram
        os dois no-op. Uma revisão adversarial pegou, e a classe saiu.
        """
        html = ""
        for caminho in self.templates_do_app():
            html += caminho.read_text(encoding="utf-8")

        for classe in (
            "form__nota",
            "form__nota--perto",
            "acao-solta",
            "chip-row--conteudo",
            "acoes-empilhadas",
            "acao-com-nota",
            "nota-do-botao",
            "card--prosa",
        ):
            with self.subTest(classe=classe):
                self.assertIn(classe, html, "classe declarada e nunca usada")

    def test_cada_intencao_usa_a_escala_de_espacamento(self):
        """O valor tem de sair de um degrau. Nomear a intenção e escrever
        `1.25rem` dentro dela só teria mudado o arbitrário de lugar."""
        css = sem_comentarios(CSS.read_text(encoding="utf-8"))

        for classe in (".form__nota", ".form__nota--perto", ".acao-solta",
                       ".chip-row--conteudo", ".acoes-empilhadas",
                       ".nota-do-botao"):
            with self.subTest(classe=classe):
                bloco = css.split(classe, 1)[1].split("}", 1)[0]
                self.assertIn("var(--espaco-", bloco)


# ---------------------------------------------------------------------------
# Botões (Onda 3, T3.4 — o que cabe sem trocar a pele dos cartões)
# ---------------------------------------------------------------------------

RAIZ_TEMPLATES = CSS.parent.parent.parent / "templates"
PWA_JS = CSS.parent.parent / "js" / "pwa.js"
#: O atributo `download` numa tag `<a …>`: precedido de espaço, seguido de
#: espaço, `>` ou `=` — `downloads` numa classe não conta.
TEM_DOWNLOAD = re.compile(r"\sdownload(\s|>|=)")


def botoes_sem_variante(texto):
    """As ocorrências de `class="btn …"` em que nenhuma classe diz QUAL botão.

    Variante é `btn--*` (primário, fantasma, perigo, bloco…) ou `btn-link`.
    Devolve o atributo inteiro, como está no HTML, para a mensagem do teste
    apontar a linha culpada sem que ninguém precise procurar.

    Fatorada para fora do teste de propósito: o controle positivo abaixo
    alimenta ESTA função com uma string sintética e cobra que ela acuse. Um
    regex que só roda dentro do laço da varredura fica verde quando a
    varredura deixa de achar arquivo — e ninguém vê.
    """
    culpados = []
    for m in re.finditer(r'class="btn(?:\s+[^"]*)?"', texto):
        classes = m.group(0)[len('class="'):-1].split()
        if not any(c.startswith("btn--") or c == "btn-link" for c in classes):
            culpados.append(m.group(0))
    return culpados


class BotaoTemVarianteTests(SimpleTestCase):
    """`.btn` sozinho é o botão "sem decisão": nem primário, nem tonal, nem
    texto. DV-B pede que toda ocorrência diga o que é. Havia UMA — a porta da
    tela de erro 500, que é autocontida e nem carrega o `app.css`; o rótulo
    ali não pinta nada, e é justamente por isso que ele tem de estar escrito:
    a régua vale para o HTML, não para o efeito."""

    def test_nenhum_botao_sem_variante(self):
        culpados = []
        for arquivo in sorted(RAIZ_TEMPLATES.rglob("*.html")):
            texto = arquivo.read_text(encoding="utf-8")
            for atributo in botoes_sem_variante(texto):
                culpados.append(f"{arquivo.relative_to(RAIZ_TEMPLATES)}: {atributo}")
        self.assertEqual(culpados, [], "botão sem variante")

    def test_o_controle_positivo_acusa_o_botao_nu(self):
        """A função enxerga o que a varredura procura — e só isso."""
        self.assertEqual(botoes_sem_variante('<a class="btn" href="/">'), ['class="btn"'])
        self.assertEqual(
            botoes_sem_variante('<a class="btn card__acao" href="/">'),
            ['class="btn card__acao"'],
        )
        self.assertEqual(botoes_sem_variante('<a class="btn btn--primary" href="/">'), [])
        self.assertEqual(botoes_sem_variante('<a class="btn btn--ghost btn--block">'), [])
        self.assertEqual(botoes_sem_variante('<a class="btn-link" href="/">'), [])
        self.assertEqual(botoes_sem_variante('<span class="btn-row">'), [])

    def test_a_varredura_le_a_pasta_de_verdade(self):
        arquivos = list(RAIZ_TEMPLATES.rglob("*.html"))
        self.assertGreater(len(arquivos), 30, "a varredura parou de achar template")
        com_btn = [a for a in arquivos if 'class="btn' in a.read_text(encoding="utf-8")]
        self.assertGreater(len(com_btn), 10, "a leitura de arquivo parou de enxergar botão")


class LinkBotaoAvisaQueEstaIndoTests(SimpleTestCase):
    """`pwa.js` já escreve `aria-busy` no `<button type=submit>`; o `<a class="btn">`
    que leva a outra tela ficava mudo entre o toque e a página nova. Mesma
    receita visual, mesmo nome de estado — a classe é o gancho do CSS, o
    atributo é o que o leitor de tela anuncia, e a página nova É a
    confirmação: o estado só cobre o intervalo."""

    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))
        self.js = re.sub(r"/\*.*?\*/", "", PWA_JS.read_text(encoding="utf-8"), flags=re.S)

    def test_o_js_marca_o_link_botao(self):
        self.assertIn("is-carregando", self.js)
        self.assertRegex(self.js, r"a\.btn\[href\]|a\.btn")
        # Um ouvinte delegado no `document`, como o resto do arquivo, e não
        # um `addEventListener` por link: o painel de Treino tem um por sessão.
        self.assertRegex(
            self.js,
            r'document\.addEventListener\("click", function \(evento\) \{[^}]*?closest\("a\.btn\[href\]"\)',
            "o clique em a.btn[href] não é delegado no document",
        )
        self.assertRegex(self.js, r'classList\.add\("is-carregando"\)')
        self.assertRegex(self.js, r'setAttribute\("aria-busy", "true"\)')

    def test_o_link_que_baixa_arquivo_diz_download(self):
        """`workouts:health_export` responde `Content-Disposition: attachment`:
        a página NÃO troca, o arquivo salva. Sem `download` no `<a class="btn">`,
        o anel de `is-carregando` ficaria girando depois de o TCX salvar — foi
        o primeiro caso que a N5 achou ao testar no navegador."""
        raiz = CSS.parent.parent.parent / "templates"
        sem_download = []
        for arquivo in sorted(raiz.rglob("*.html")):
            texto = arquivo.read_text(encoding="utf-8")
            for m in re.finditer(r"<a [^>]*workouts:health_export[^>]*>", texto):
                if not TEM_DOWNLOAD.search(m.group(0)):
                    sem_download.append(f"{arquivo.relative_to(raiz)}: {m.group(0)}")
        self.assertEqual(sem_download, [], "link que baixa arquivo sem `download`")

    def test_o_leitor_enxerga_o_link_sem_download(self):
        """Controle positivo do regex acima: um `<a>` de exportação sem o
        atributo tem de ser flagrado, e `downloads` (outra palavra) não conta."""
        self.assertIsNone(TEM_DOWNLOAD.search('<a class="btn" href="/treino/exportar/">'))
        self.assertIsNotNone(TEM_DOWNLOAD.search('<a class="btn" href="/treino/exportar/" download>'))
        self.assertIsNone(TEM_DOWNLOAD.search('<a class="downloads" href="x">'))

    def test_o_que_nao_troca_de_pagina_fica_de_fora(self):
        """`target` abre outra aba, `download` guarda arquivo, `#` fica na
        tela, `mailto:` abre outro app; clique com modificador abre nova aba
        e esta fica. Em todos, marcar o link seria prometer uma página que não
        vem — e o estado nunca seria limpo."""
        for guarda in ('hasAttribute("target")', 'hasAttribute("download")',
                       "defaultPrevented", "button !== 0",
                       "ctrlKey", "metaKey", "shiftKey", "altKey"):
            with self.subTest(guarda=guarda):
                self.assertIn(guarda, self.js)
        self.assertIn("mailto:", self.js)
        self.assertIn("javascript:", self.js)

    def test_voltar_pelo_historico_limpa_o_link(self):
        """A página do bfcache volta exatamente como saiu — com o link
        marcado. Mesmo caminho de volta que o botão de envio já tem."""
        self.assertRegex(
            self.js,
            r'addEventListener\("pageshow", function \(\) \{\s*document\.querySelectorAll\("\.btn\.is-carregando"\)'
            r'[\s\S]*?classList\.remove\("is-carregando"\)[\s\S]*?removeAttribute\("aria-busy"\)',
        )

    def test_o_css_tem_a_receita(self):
        self.assertRegex(self.css, r"\.btn\.is-carregando[^{]*\{")

    def test_a_receita_e_a_mesma_do_aria_busy_e_nao_uma_copia(self):
        """`.btn.is-carregando` entra como PAR do seletor `[aria-busy]`, nunca
        como bloco próprio: dois blocos divergiriam na primeira mudança do
        anel. Conferido nos dois lugares em que a receita existe — o anel e a
        saída de movimento reduzido, porque o anel gira."""
        anel = re.search(
            r"([^{}]*\.btn\.is-carregando::after[^{]*)\{([^}]*)\}", self.css
        )
        self.assertIsNotNone(anel, "o anel não tem o par .btn.is-carregando::after")
        self.assertIn('.btn[aria-busy="true"]::after', anel.group(1))
        self.assertIn("montagem-gira", anel.group(2))

        reduzido = self.css.split("prefers-reduced-motion")[1:]
        self.assertTrue(
            any(
                re.search(r"\.btn\.is-carregando::after[^{]*\{\s*animation: none", trecho)
                for trecho in reduzido
            ),
            "o anel do link-botão continua girando para quem pediu menos movimento",
        )

    def test_o_mapa_de_areas_toca_na_mesma_escala(self):
        """O mapa afundava por regra PRÓPRIA, com o mesmo `.96` escrito de
        novo. Mesmo valor não é mesma lista: a lista única existe para que a
        próxima mudança de escala mude tudo de uma vez."""
        regras = re.findall(
            r"([^{}]*:active[^{]*)\{([^}]*transform:\s*scale\([^)]*\)[^}]*)\}", self.css
        )
        proprias = [sel for sel, _ in regras if sel.strip() == ".mapa__area:active"]
        self.assertEqual(proprias, [], "o mapa tem regra própria de :active; entra na lista única")

        # E o controle positivo: ele ESTÁ na lista — a que tem `.btn:active`.
        lista = [
            {s.strip() for s in sel.split(",")}
            for sel, _ in regras
            if ".btn:active" in {s.strip() for s in sel.split(",")}
        ]
        self.assertEqual(len(lista), 1, "a lista única de :active deixou de ser única")
        self.assertIn(".mapa__area:active", lista[0])
