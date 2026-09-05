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
TETO_FONT_SIZE_CRU = 145
TETO_ESPACO_CRU = 292


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
