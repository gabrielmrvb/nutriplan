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
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from plans import graficos

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
#: 117 em 16/09/2026 (T3.2, a fonte própria): o `h1` passou a `--texto-2xl`
#: (era `2.5rem`, e `1.9rem` no desktop — o título nunca passa de 28).
#: 115 em 20/09/2026: `.resumo__nota { font-size: .74rem }` saiu com a nota
#: "a exportação gera um arquivo TCX" — a exportação saiu do produto.
#: 22/09/2026, DUAS reduções no mesmo dia e em campanhas diferentes — o
#: número final é o das duas somadas, e não o de nenhuma delas:
#: `.descanso__rotulo { font-size: .78rem }` virou degrau quando o cronômetro
#: cresceu (o relógio é `--texto-2xl` e o rótulo ao lado, `--texto-xs`), e a
#: linha `.resumo-dia` saiu inteira com o redesenho da Home, levando um
#: `font-size: .72rem` cru junto. A catraca só desce.
#: 109 em 23/09/2026: a opção do cardápio deixou de ser uma sanfona e virou
#: um card de receita — o bloco `.option*` inteiro saiu do arquivo, e com ele
#: quatro tamanhos crus (`.92rem` do nome, `.82rem` do kcal e da hora,
#: `.85rem` da lista de ingredientes). O que substituiu tudo nasceu em
#: token.
#: 25 em 28/09/2026 (dívida de sistema visual, lote 1): todo `font-size` cru
#: de regra que não é de treino virou degrau `--texto-*` (o mais perto; só
#: quatro andaram mais de 0,8 px). Sobram as regras de treino (Fase A), o
#: `h2` de 20,8 px (lote 4) e a barra de cima (lote 6).
TETO_FONT_SIZE_CRU = 25
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
#: 243 em 16/09/2026 (T3.6): o selo do treino concluído (`.fim__selo`, com
#: `margin: .2rem auto ...`) saiu com a folha de recompensa.
#: 241 em 20/09/2026: `.explicacao__head a` (`padding: 0 .4rem; margin: 0
#: -.4rem`) saiu com o "Editar" de dentro do `<summary>` (axe
#: `nested-interactive`); o link virou `.btn--quiet`, que já está na escala.
#: 238 em 22/09/2026: a ficha virou CARD e a execução ganhou cronômetro e
#: fecho — tudo nasceu na escala, e três crus antigos do bloco `.ficha-item`
#: (o `padding: 0` da linha, o `row-gap: 2px` e o `gap` das ações) saíram
#: junto com a linha de texto que eles vestiam.
#: 230 em 23/09/2026: o mesmo bloco `.option*` levou oito espaços crus
#: (`.8rem .85rem` do corpo e do resumo, `.45rem`, `.35rem .5rem`...). O
#: card de receita, a folha e o painel são todos escala.
#: 228 em 24/09/2026: `.btn--hoje { gap: .1rem }` saiu com o CTA do painel
#: de treino — o `gap` só existia para o `flex-direction: column` do eco
#: (o nome do exercício embaixo do verbo), removido em 22/09/2026; sem
#: coluna, sobrava cru e sem uso.
#: 62 em 28/09/2026 (dívida de sistema visual, lote 1): o espaço cru de regra
#: que não é de treino virou a escala da direção (`--e1`…`--e8`). Sobram as
#: regras de treino, o que passa de 56 px (é layout, não ritmo), `em`, `%`
#: e o `-1px` do `.vis-oculto`.
TETO_ESPACO_CRU = 62


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


def valores_crus_de_text_svg(raiz_templates):
    """`font-size="N"` escrito à mão num `<text>` de template de SVG.

    Devolve `(caminho, valor_float)` para todo valor LITERAL — ignora o que
    vem do servidor (`{{ tamanho_rotulo }}`), que é `graficos.TAMANHO_ROTULO`
    e tem o teste ao lado. Varre TODO template, não só os dois que usam
    `<text>` hoje (`_peso.html`, `_progresso_area.html`): a régua existe para
    o PRÓXIMO `<text>` escrito à mão nascer coberto, não para os dois atuais.
    """
    achados = []
    for caminho in sorted(Path(raiz_templates).rglob("*.html")):
        texto = caminho.read_text(encoding="utf-8")
        for tag in re.findall(r"<(?:text|tspan)\b[^>]*>", texto):
            casou = re.search(r"""font-size=["']([^"']*)["']""", tag)
            if not casou:
                continue
            valor = casou.group(1).strip()
            if "{{" in valor or "{%" in valor:
                continue
            try:
                achados.append((caminho, float(valor)))
            except ValueError:
                # VALOR QUE NÃO É NÚMERO VIRA ACHADO, e não silêncio. Era
                # `continue`, e `font-size="9px"` — o hábito de quem vem do
                # CSS — saía do radar: um rótulo ABAIXO do piso passava pela
                # régua sem sinal nenhum. Aqui ele vira `float("-inf")`, que
                # é menor que qualquer piso e aparece com o valor cru na
                # mensagem. Unidade em atributo de SVG também não é o que o
                # módulo de gráficos escreve; se um dia for, o teste é o
                # lugar de decidir isso em voz alta.
                achados.append((caminho, float("-inf")))
    return achados


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
            "Use um degrau de --e1…--e8.",
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

        # Desde 28/09/2026 a escala é a da direção (`--e1`…`--e8`); os
        # `--espaco-*` são legado de treino e podem ir sumindo sem buraco.
        for degrau in range(1, 9):
            with self.subTest(degrau=f"--e{degrau}"):
                self.assertIn(f"--e{degrau}:", self.css)
                self.assertIn(f"var(--e{degrau})", self.css)

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
        # 900 desde a NERVURA (17/09/2026): o peso do número herói na Big
        # Shoulders. Foi 760, 750 (todo tile) e 700 (Bodoni, na CORTE).
        self.assertIn("font-weight: 900", corpo)

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
        # `.semana__valor` saiu em 23/09/2026 com a lista semanal do
        # Progresso: o número agora mora no `<title>` da barra e no tile.
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
        # 9 -> 8 em 23/09/2026: `.semana__valor` saiu com a lista semanal do
        # Progresso. O piso é controle positivo (a lista não pode estar vazia
        # nem casar com qualquer coisa), e oito ainda o sustentam.
        self.assertGreaterEqual(len(self.VALORES), 8)
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
            # A pasta `templates/email/` (os avisos: boas-vindas, inatividade,
            # resumo semanal e a moldura deles) é e-mail tanto quanto o
            # `email_senha.html`: o nome do arquivo não carrega mais a palavra
            # porque a pasta já a carrega.
            if "email" in caminho.name or "/email/" in relativo or "/admin/" in relativo:
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
        hoje = (self.RAIZ_TEMPLATES / "plans" / "alimentacao.html").read_text(encoding="utf-8")

        self.assertIn("style=\"width: {{", hoje)

    def test_o_email_continua_com_estilo_inline(self):
        """Proibir estilo inline no e-mail quebraria o e-mail: cliente de
        e-mail não lê CSS externo. A exceção é técnica, não preguiça."""
        email = (
            self.RAIZ_TEMPLATES / "accounts" / "email_senha.html"
        ).read_text(encoding="utf-8")

        self.assertIn('style="', email)
        self.assertIn("#106632", email)  # o verde-floresta do Papel: e-mail é fundo claro

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
                self.assertIn("var(--e", bloco)  # a escala da direção desde 28/09/2026


# ---------------------------------------------------------------------------
# Botões (Onda 3, T3.4 — o que cabe sem trocar a pele dos cartões)
# ---------------------------------------------------------------------------

RAIZ_TEMPLATES = CSS.parent.parent.parent / "templates"
PWA_JS = CSS.parent.parent / "js" / "pwa.js"
#: A marca `data-arquivo` numa tag `<a …>`: precedida de espaço, seguida de
#: espaço, `>` ou `=` — `data-arquivos` ou uma classe parecida não contam.
DIZ_QUE_E_ARQUIVO = re.compile(r"\sdata-arquivo(\s|>|=)")


#: O que DIZ qual botão é. `btn--block`, `btn--sm` e `btn--hoje` são tamanho e
#: posição, não variante — um `btn btn--block` continua sendo o botão sem
#: decisão. `btn--google` é a variante do OAuth, com receita própria.
VARIANTES_DE_BOTAO = frozenset(
    {"btn--primary", "btn--ghost", "btn--quiet", "btn--perigo", "btn--google", "btn-link"}
)


def botoes_sem_variante(texto):
    """As ocorrências de `class="btn …"` em que nenhuma classe diz QUAL botão.

    Variante é uma de `VARIANTES_DE_BOTAO` — tamanho e posição não contam.
    Devolve o atributo inteiro, como está no HTML, para a mensagem do teste
    apontar a linha culpada sem que ninguém precise procurar.

    Fatorada para fora do teste de propósito: o controle positivo abaixo
    alimenta ESTA função com uma string sintética e cobra que ela acuse. Um
    regex que só roda dentro do laço da varredura fica verde quando a
    varredura deixa de achar arquivo — e ninguém vê.
    """
    culpados = []
    # Lógica de template dentro do atributo (`{% if %}btn--primary{% endif %}`)
    # sai antes de tokenizar: o que sobra é o literal comum aos ramos — um
    # `{% if %}` sem `else` que escondesse a única variante passaria, e os
    # dois casos reais têm `else`.
    limpo = re.sub(r"{%.*?%}", " ", texto)
    for m in re.finditer(r"class=([\"'])(.*?)\1", limpo):
        classes = m.group(2).split()
        if "btn" not in classes:
            continue
        if not any(c in VARIANTES_DE_BOTAO for c in classes):
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

    def test_o_js_respeita_a_marca_de_arquivo(self):
        """`data-arquivo` é a marca de um `<a class="btn">` cuja resposta é um
        arquivo (`Content-Disposition: attachment`): a página não troca, e o
        anel de `is-carregando` ficaria girando. Os dois links que a usavam
        (exportar TCX) saíram em 20/09/2026; o mecanismo fica em `pwa.js` para
        o próximo link de arquivo nascer marcado — e `DIZ_QUE_E_ARQUIVO` é a
        régua que o teste de baixo mantém afiada."""
        self.assertIn('hasAttribute("data-arquivo")', self.js)
        for arquivo in sorted(RAIZ_TEMPLATES.rglob("*.html")):
            self.assertNotIn("workouts:health_export", arquivo.read_text(encoding="utf-8"), arquivo.name)

    def test_o_leitor_enxerga_o_link_sem_marca(self):
        """Controle positivo do regex acima: um `<a>` de exportação sem a marca
        tem de ser flagrado, e `data-arquivos` (outra palavra) não conta."""
        self.assertIsNone(DIZ_QUE_E_ARQUIVO.search('<a class="btn" href="/treino/exportar/">'))
        self.assertIsNotNone(DIZ_QUE_E_ARQUIVO.search('<a class="btn" href="/treino/exportar/" data-arquivo>'))
        self.assertIsNone(DIZ_QUE_E_ARQUIVO.search('<a class="btn" data-arquivos="x" href="x">'))

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


class ORotuloDoGraficoDeSvgRespeitaOPisoDeOnzePixelsTests(SimpleTestCase):
    """`test_o_piso_de_onze_pixels_continua_no_menor_degrau` só varre CSS
    (`--texto-xs`) — e o rótulo de eixo do gráfico SVG (o peso, o volume por
    semana em Progresso) nunca passou por ali: o tamanho sai como ATRIBUTO
    `font-size` do `<text>`, em `plans/graficos.py` (`TAMANHO_ROTULO`), não
    como regra de CSS. Com o valor antigo (9) o rótulo do peso ("83,4") e a
    data liam 9px de DECLARADO e 8,2px de PINTADO no celular — os dois abaixo
    do piso do `CLAUDE.md`, "texto de interface nunca abaixo de 11px".

    Esta régua mede o DECLARADO, e o `graficos.py` explica por quê, com a
    tabela medida no navegador: `getComputedStyle(text).fontSize` devolve a
    constante sem desconto, mas o glifo na tela é `declarado × largura/320`,
    porque o `viewBox` tem 320 unidades. Com 12, o celular chega a 11,0px
    pintados (era 8,2) e os gráficos de coluna do desktop ficam em 9,8 — o
    que sobra é geometria de `viewBox`, não tamanho de fonte, e está no
    relatório da missão. Um teste sem navegador não vê a escala; o que ele
    pode garantir é que a fonte de verdade da tela não volte abaixo do piso.
    """

    TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

    def test_o_tamanho_do_modulo_de_graficos_atinge_o_piso(self):
        """`graficos.TAMANHO_ROTULO` é a fonte de TODO `<text>` de gráfico
        hoje (`_peso.html`, `_progresso_area.html`) — subir só ele já cobre
        as duas telas, porque as duas leem a mesma constante. A comparação é
        direta contra 11 porque é o DECLARADO que esta régua alcança; o
        pintado depende da caixa e está medido no `graficos.py`."""
        self.assertGreaterEqual(
            graficos.TAMANHO_ROTULO,
            11,
            f"TAMANHO_ROTULO={graficos.TAMANHO_ROTULO} — abaixo do piso de 11px",
        )

    def test_nenhum_text_de_template_escreve_valor_cru_abaixo_do_piso(self):
        """O módulo de gráficos é a única fonte de `<text>` hoje, mas a
        régua varre TODO template — para o PRÓXIMO `<text>` escrito à mão
        (sem passar por `graficos.py`) nascer coberto, e não descoberto até
        alguém medir de novo na tela."""
        culpados = [
            "%s: font-size=%s" % (caminho.name, "ilegível" if valor == float("-inf") else "%g" % valor)
            for caminho, valor in valores_crus_de_text_svg(self.TEMPLATES)
            if valor < 11.0
        ]

        self.assertEqual(culpados, [], "rótulo de <text> abaixo do piso de 11px")

    def test_o_scanner_pega_valor_cru_e_ignora_variavel_do_servidor(self):
        """Controle positivo: sem ele, um regex quebrado — ou o filtro de
        `{{ }}` engolindo o que não devia — deixaria o teste acima verde
        para sempre, do jeito que o 9px do peso passou despercebido.

        As quatro formas que a revisão adversarial cobrou estão aqui: valor
        cru, aspas simples, `<tspan>` aninhado e valor com unidade — este
        último vira `-inf`, porque "não consigo ler" não pode ser o mesmo
        que "está acima do piso"."""
        with tempfile.TemporaryDirectory() as raiz:
            (Path(raiz) / "x.html").write_text(
                '<text font-size="8">baixo</text>'
                '<text font-size="12">ok</text>'
                "<text font-size='10'>aspas simples</text>"
                '<text font-size="{{ tamanho_rotulo }}">variável do servidor'
                '<tspan font-size="7">aninhado</tspan></text>'
                '<text font-size="9px">com unidade</text>',
                encoding="utf-8",
            )
            achados = sorted(valor for _, valor in valores_crus_de_text_svg(Path(raiz)))

        self.assertEqual(
            achados, [float("-inf"), 7.0, 8.0, 10.0, 12.0],
            "o scanner parou de achar valor cru, de ler aspas simples/tspan, ou passou a engolir unidade",
        )


# ---------------------------------------------------------------------------
# O SISTEMA VIRA A LEI (dívida de sistema visual, lote 1, 28/09/2026)
# ---------------------------------------------------------------------------
#
# Base: `achados/auditoria-visual-20260927.md` e o gate 1 do dono (28/09):
# a escala de espaço é a da DIREÇÃO (`--e1`…`--e8` = 4·8·12·16·20·24·32·48);
# os `--espaco-*` ficam como LEGADO só nas regras de treino (a Fase A mora em
# `templates/workouts/` e ninguém mexe lá agora); a entrelinha tem quatro
# degraus; as tintas de `--brand` e dos pilares têm nome. Tudo que sobrou cru
# é regra de treino ou exceção nomeada — e cada categoria tem catraca de folga
# zero, igual às duas de cima.

TEMPLATES = CSS.parent.parent.parent / "templates"

ESCALA_DA_DIRECAO = {
    "--e1": ".25rem", "--e2": ".5rem", "--e3": ".75rem", "--e4": "1rem",
    "--e5": "1.25rem", "--e6": "1.5rem", "--e7": "2rem", "--e8": "3rem",
}
TINTAS_DA_MARCA = {
    "--brand-tinta-fraca": 9, "--brand-tinta": 12, "--brand-linha": 24,
    "--brand-linha-forte": 32, "--brand-tinta-forte": 45,
}
#: Medidos em 28/09/2026 depois da migração do lote 1. O que sobra é regra de
#: treino (ledger) ou exceção com nome (a vinheta de 12 % da entrada, que
#: `config/test_vinheta_da_entrada.py` recalcula; o player de vídeo do treino).
TETO_ENTRELINHA_CRUA = 15  # 14 de treino + o `h2` (lote 4)
TETO_COR_LITERAL = 4  # a vinheta de 12 % da entrada + 3 de treino
#: 15: 8 de treino, a vinheta da entrada, e 6 misturas de cor POR ELEMENTO
#: (`--cor`, `--cor-area`, `--dia`), que o :root não tem como resolver.
TETO_TINTA_FORA_DO_ROOT = 15

#: Um bloco de TOKEN: cada parte do seletor é o próprio `:root`, no máximo
#: com classe, atributo ou `:not()` — `:root .x { … }` é regra de componente
#: e conta (achado da revisão do lote 1).
_ROOT_PARTE = re.compile(r"\s*:root(?:\.[\w-]+|\[[^\]]*\]|:not\([^)]*\))*\s*")


def eh_root(sel):
    return all(_ROOT_PARTE.fullmatch(p) for p in sel.split(","))
COR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")


def _regras(css):
    """(seletor, corpo) de cada bloco mais interno — o `@media` em volta não
    entra no seletor."""
    for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        yield " ".join(m.group(1).split()), m.group(2)


def _declaracoes(corpo):
    for pedaco in corpo.split(";"):
        prop, sep, valor = pedaco.partition(":")
        if sep:
            yield prop.strip(), valor.strip()


def entrelinhas_cruas(css):
    """`line-height` escrito à mão; `1`, `normal` e `inherit` não são degrau
    e continuam livres."""
    achados = []
    for sel, corpo in _regras(css):
        if eh_root(sel) or sel.startswith("@"):
            continue
        for prop, valor in _declaracoes(corpo):
            if prop == "line-height" and "var(" not in valor and valor not in ("1", "normal", "inherit"):
                achados.append((sel, valor))
    return achados


def cores_literais(css):
    """Cor escrita à mão fora dos blocos `:root` (onde as duas paletas moram)."""
    achados = []
    for sel, corpo in _regras(css):
        if eh_root(sel) or sel.startswith("@"):
            continue
        for prop, valor in _declaracoes(corpo):
            if prop == "content":
                continue
            achados += [(sel, prop, c) for c in COR_LITERAL.findall(re.sub(r"url\([^)]*\)", "", valor))]
    return achados


def tintas_fora_do_root(css):
    """`color-mix()` fora do `:root`: a tinta que não virou token."""
    return [(sel, n) for sel, corpo in _regras(css) if not eh_root(sel)
            for n in range(corpo.count("color-mix("))]


def _elementos_de(texto):
    """Os conjuntos de classes de cada elemento de um template — o que está
    em `class="…"`, não a palavra solta no texto ("hoje" é classe e é
    palavra). Pedaço dinâmico (`meal--{{ estado }}`) entra como prefixo,
    marcado com `*` no fim."""
    elementos = []
    for attr in re.findall(r'class\s*=\s*"([^"]*)"', texto):
        classes = set()
        for token in re.sub(r"\{%.*?%\}", " ", attr).split():
            if "{{" in token:
                base = token.split("{{", 1)[0]
                if base:
                    classes.add(base + "*")
            elif not token.startswith("{"):
                classes.add(token)
        if classes:
            elementos.append(classes)
    return elementos


def _textos_de_template():
    fora, treino = [], []
    for p in TEMPLATES.rglob("*.html"):
        (treino if "workouts" in p.parts else fora).extend(_elementos_de(p.read_text(encoding="utf-8")))
    return fora, treino


def _tem(elemento, classe):
    return classe in elemento or any(c.endswith("*") and classe.startswith(c[:-1]) for c in elemento)


def _algum_elemento_com(classes, elementos):
    return any(all(_tem(e, c) for c in classes) for e in elementos)


def so_de_treino(seletor, fora, treino):
    """Cada parte do seletor tem um seletor simples (as classes de UM
    elemento, como `.card.hoje`) que só existe em templates de treino. É a
    mesma definição que a migração do lote 1 usou para decidir o que ficava
    para a Fase A."""
    partes = [p for p in seletor.split(",") if p.strip()]
    if not partes:
        return False
    for parte in partes:
        simples = [set(re.findall(r"\.([a-zA-Z_][\w-]*)", s)) for s in re.split(r"[\s>+~]+", parte)]
        if not any(c and _algum_elemento_com(c, treino) and not _algum_elemento_com(c, fora) for c in simples):
            return False
    return True


class OSistemaViraALeiTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))
        self.bruto = CSS.read_text(encoding="utf-8")

    def test_os_oito_degraus_da_direcao_existem_com_os_valores_do_design_md(self):
        for token, valor in ESCALA_DA_DIRECAO.items():
            with self.subTest(token=token):
                self.assertRegex(self.css, r"%s:\s*%s;" % (re.escape(token), re.escape(valor)))

    def test_pad_e_gap_apontam_para_a_escala_da_direcao(self):
        """Os dois apelidos que o app já usava continuam valendo — e agora são
        degraus da direção, não números soltos."""
        self.assertRegex(self.css, r"--pad:\s*var\(--e5\);")
        self.assertRegex(self.css, r"--gap:\s*var\(--e4\);")

    def test_o_legado_esta_marcado_e_datado(self):
        """`--espaco-*` continua existindo porque as regras de treino ainda o
        usam; o comentário logo acima diz isso, com a data, para o próximo
        leitor não achar que é a escala do app."""
        bloco = self.bruto.split("--espaco-1:", 1)[0][-900:]
        self.assertIn("LEGADO", bloco)
        self.assertIn("28/09/2026", bloco)

    def test_o_legado_so_mora_em_regra_de_treino(self):
        fora, treino = _textos_de_template()
        invasores = [sel for sel, corpo in _regras(self.css)
                     if "var(--espaco-" in corpo and not eh_root(sel) and not so_de_treino(sel, fora, treino)]
        self.assertEqual(invasores, [], "regra fora de treino usando --espaco-*: use --e1…--e8")

    def test_a_regra_do_legado_enxerga_uma_regra_de_fora_do_treino(self):
        """Controle positivo: `.card` existe fora do treino, `.hoje` só dentro."""
        fora, treino = _textos_de_template()
        self.assertFalse(so_de_treino(".card", fora, treino))
        self.assertTrue(so_de_treino(".card.hoje", fora, treino))

    def test_as_cinco_tintas_da_marca_tem_nome_e_porcentagem(self):
        for token, pct in TINTAS_DA_MARCA.items():
            with self.subTest(token=token):
                self.assertRegex(self.css, r"%s:\s*color-mix\(in srgb, var\(--brand\) %d%%, transparent\);" % (re.escape(token), pct))

    def test_a_divida_de_entrelinha_nao_cresce_e_o_teto_nao_folga(self):
        self.assertEqual(len(entrelinhas_cruas(self.css)), TETO_ENTRELINHA_CRUA,
                         "use --entrelinha-numero/-display/-titulo ou --entrelinha")

    def test_a_divida_de_cor_literal_nao_cresce_e_o_teto_nao_folga(self):
        self.assertEqual(len(cores_literais(self.css)), TETO_COR_LITERAL,
                         "cor escrita à mão fora do :root — dê nome a ela no :root")

    def test_a_divida_de_tinta_fora_do_root_nao_cresce_e_o_teto_nao_folga(self):
        self.assertEqual(len(tintas_fora_do_root(self.css)), TETO_TINTA_FORA_DO_ROOT,
                         "color-mix() fora do :root — use --brand-tinta* ou a tinta do pilar")

    def test_os_leitores_enxergam_o_que_procuram(self):
        """Controle positivo dos três contadores, num CSS de mentira."""
        falso = (":root { --x: #fff; --y: color-mix(in srgb, red 5%, transparent); }\n"
                 ".a { line-height: 1.4; color: #123456; background: color-mix(in srgb, var(--z) 9%, transparent); }\n"
                 ".b { line-height: var(--entrelinha); line-height: 1; }")
        self.assertEqual(len(entrelinhas_cruas(falso)), 1)
        self.assertEqual(len(cores_literais(falso)), 1)
        self.assertEqual(len(tintas_fora_do_root(falso)), 1)
        # e `:root .x` é componente, não bloco de token (revisão do lote 1)
        self.assertEqual(len(cores_literais(":root .x { color: #fff; }")), 1)

    def test_estilo_embutido_so_na_pagina_de_erro(self):
        """A página de 500 carrega o próprio `<style>` porque é servida quando
        o resto pode estar quebrado; nenhuma outra tela do app faz isso."""
        com_style = sorted(p.relative_to(TEMPLATES).as_posix() for p in TEMPLATES.rglob("*.html")
                           if "<style" in p.read_text(encoding="utf-8") and "email" not in p.parts)
        self.assertEqual(com_style, ["500.html"])


# ---------------------------------------------------------------------------
# UM BOTÃO PRIMÁRIO SÓ (dívida de sistema visual, lote 2, 28/09/2026)
# ---------------------------------------------------------------------------
#
# A auditoria achou três primários: o da NERVURA (display 22,4, inclinado), o
# `btn--sm` dele (Archivo — a display nunca desce de 20 px, e é regra) e o
# `.pesagem__salvar`, um verde cheio escrito à parte, sem inclinação, no
# Progresso e na faixa de peso da Home. E o aviso de conquista punha um
# SEGUNDO primário na execução, embaixo do CONCLUIR SÉRIE.

#: O que pinta `--brand` cheio com texto `--on-brand` e NÃO é botão.
PREENCHIDOS_QUE_NAO_SAO_BOTAO = {".choice-card__mark"}  # o visto do cartão escolhido


def _sem_comentario_django(texto):
    return re.sub(r"\{% comment %\}.*?\{% endcomment %\}", "", texto, flags=re.S)


class UmBotaoPrimarioSoTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_fora_do_treino_so_o_primario_pinta_a_marca_cheia(self):
        fora, treino = _textos_de_template()
        paralelos = [
            sel for sel, corpo in _regras(self.css)
            if not eh_root(sel) and not sel.startswith("@")
            and re.search(r"background(-color)?:\s*var\(--brand\)", corpo) and "var(--on-brand)" in corpo
            and sel not in PREENCHIDOS_QUE_NAO_SAO_BOTAO and not so_de_treino(sel, fora, treino)
        ]
        self.assertEqual(paralelos, [], "botão verde cheio fora do `.btn--primary`: use `btn btn--primary` (ou `--sm`)")

    def test_a_pesagem_usa_o_primario_pequeno(self):
        html = (TEMPLATES / "plans" / "_peso_campo.html").read_text(encoding="utf-8")
        botao = re.search(r"<button\b[^>]*type=\"submit\"[^>]*>", html).group(0)
        self.assertIn('class="btn btn--primary btn--sm"', botao)
        self.assertNotIn(".pesagem__salvar", self.css)

    def test_o_aviso_de_conquista_nao_traz_um_segundo_primario(self):
        """Ele aparece EMBAIXO do CONCLUIR SÉRIE, na execução: o primário da
        tela é concluir, e compartilhar é contorno — como na lista de
        Conquistas, onde ele sempre foi."""
        html = _sem_comentario_django((TEMPLATES / "partials" / "_conquista.html").read_text(encoding="utf-8"))
        self.assertNotIn("btn--primary", html)
        self.assertRegex(html, r'class="btn btn--ghost conquista__compartilhar"')

    def test_a_home_so_tem_o_primario_do_agora(self):
        """O aviso de regenerar a ficha aparece DEPOIS do AGORA, e com ele
        a Home tinha dois primários. O primário é o do AGORA (`_agora.html`);
        o aviso é uma oferta, e oferta é contorno."""
        html = _sem_comentario_django((TEMPLATES / "plans" / "today.html").read_text(encoding="utf-8"))
        self.assertNotIn("btn--primary", html)
        self.assertIn("btn--primary", (TEMPLATES / "plans" / "_agora.html").read_text(encoding="utf-8"))

    def test_o_selo_da_vez_nao_encolhe(self):
        """"Agora" virava "Ag…" a 390 px (caixa de 46, texto de 50, medido na
        auditoria). A regra de 25/09 que deixa o selo ceder antes do nome
        continua valendo para os selos longos; o da vez tem cinco letras."""
        self.assertRegex(self.css, r"\.meal__linha \.meal__marca--agora\s*\{[^}]*flex-shrink:\s*0")

    def test_o_primario_pequeno_fica_nos_pesos_da_archivo(self):
        """A display nunca desce de 20 px, então o `btn--sm` volta à Archivo —
        e o 800 que ele herdava do primário é peso da display."""
        regra = re.search(r"\.btn--primary\.btn--sm\s*\{([^}]*)\}", self.css).group(1)
        self.assertIn("font-family: var(--font)", regra)
        self.assertRegex(regra, r"font-weight:\s*(400|500|600|700)\b")

    def test_o_controle_positivo_acha_um_primario_paralelo(self):
        falso = ".x { background: var(--brand); color: var(--on-brand); }"
        achados = [sel for sel, corpo in _regras(falso)
                   if re.search(r"background(-color)?:\s*var\(--brand\)", corpo) and "var(--on-brand)" in corpo]
        self.assertEqual(achados, [".x"])
