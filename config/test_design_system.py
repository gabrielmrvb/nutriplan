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
- **`style=` no template.** Já existe um caso vivo em
  `templates/accounts/conectar_google.html`, e nada no repositório proíbe;
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
TETO_FONT_SIZE_CRU = 144
TETO_ESPACO_CRU = 291


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
        self.assertIn("font-weight: 760", corpo)

        self.assertIsNone(
            self._regra(".seletor-que-nao-existe-em-lugar-nenhum"),
            "o leitor de regra devolve corpo para seletor inexistente",
        )


class MetricaNaoDependeDoTemplateParaSerMonoTests(SimpleTestCase):
    """A tipografia de um número é do CSS, nunca do HTML que o escreve.

    `.fim__valor` e `.conquistas__numero` eram monoespaçadas só porque o
    template escrevia `class="... num"`. As outras famílias de métrica declaram
    a própria família. Um bloco novo copiado sem o `num` ficava proporcional, e
    o defeito só aparecia quando o número atualizava e dançava de lugar — que é
    exatamente o que `tabular-nums` existe para impedir.

    `.num` continua no HTML e continua útil: ele marca "isto é número" para
    quem lê o template. O que não pode é a família DEPENDER dele.
    """

    #: Toda classe que é o VALOR de uma métrica. Não inclui rótulos — eles são
    #: texto e usam a fonte de texto de propósito.
    VALORES = (
        ".tile__value",
        ".fim__valor",
        ".equation__value",
        ".drawer__numero-valor",
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

    def test_todo_valor_de_metrica_declara_a_propria_fonte(self):
        for seletor in self.VALORES:
            with self.subTest(seletor=seletor):
                corpo = self._regra(seletor)
                self.assertIsNotNone(corpo, f"a regra {seletor} sumiu")
                self.assertIn(
                    "font-family: var(--font-mono)",
                    corpo,
                    f"{seletor} depende do `num` do template para ser mono",
                )

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
