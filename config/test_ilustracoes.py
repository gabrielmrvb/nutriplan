"""O sprite das ilustrações de receita (`partials/ilustracoes_de_receita.html`).

Onze cenas, uma por família de receita, que o card de refeição clona com
`<use href="#ilu-familia">`. É o segundo sprite do repositório — o primeiro é
`partials/icones.html`, guardado por `config/test_sprite.py` —, e este arquivo
guarda o que é diferente nele: a grade 4:3 da faixa do card, o traço mais fino
da ilustração e a massa de preenchimento que o ícone não tem.

Por que um teste que lê o disco em vez de olhar a tela: o sprite é clonado, e
erro de sprite não aparece como erro. `id` duplicado ou trocado não levanta
exceção nenhuma — o `<use>` resolve para o primeiro, ou para nada, e o card
desenha um retângulo vazio. Só a leitura do arquivo pega isso antes.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ARQUIVO = Path(settings.BASE_DIR) / "templates" / "partials" / "ilustracoes_de_receita.html"

#: As onze famílias, escritas à mão. Ler a lista do próprio arquivo provaria
#: apenas que ele é igual a si mesmo; o que se quer prender é o contrato com
#: quem consome — o card pede `ilu-<familia>` e a família vem da receita.
IDS = (
    "ilu-cuscuz",
    "ilu-mingau",
    "ilu-ovos",
    "ilu-pao",
    "ilu-tapioca",
    "ilu-vitamina",
    "ilu-prato",
    "ilu-macarrao",
    "ilu-iogurte",
    "ilu-fruta",
    "ilu-salada",
)

GRADE = 'viewBox="0 0 48 36"'
TRACO = 'stroke-width="1.6"'

#: O sprite é servido em toda página que desenha refeição, e ele viaja no HTML
#: — não é arquivo estático com cache próprio. O teto é folgado para onze
#: cenas de traço e apertado para gravura: quem precisar de mais bytes está
#: desenhando demais para 96×72 px.
TETO_DE_BYTES = 8192

#: Massa: `fill-opacity` entre estes dois, e `fill="currentColor"`. Abaixo de
#: .12 a massa some no tema claro; acima de .2 ela compete com o traço.
MASSA_MIN, MASSA_MAX = 0.12, 0.2

FILL_PERMITIDO = {"none", "currentColor"}

PROIBIDOS_NO_DEFS = ("<image", "<text", "<filter", "<animate", "style=", "class=")

COR_CRUA = re.compile(r"#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(")


def cores_cruas(texto):
    """Toda cor escrita à mão no texto. Ver o controle positivo lá embaixo."""
    return COR_CRUA.findall(texto)


def fills_fora_do_contrato(texto):
    """Todo valor de `fill=` que não seja `none` nem `currentColor`.

    `fill-opacity="…"` NÃO cai aqui, e isso é de propósito: o padrão `fill="`
    não ocorre dentro de `fill-opacity="`.
    """
    return [v for v in re.findall(r'fill="([^"]*)"', texto) if v not in FILL_PERMITIDO]


def _texto():
    return ARQUIVO.read_text(encoding="utf-8")


def _simbolos(texto):
    return re.findall(r"<symbol\b.*?</symbol>", texto, flags=re.S)


def _defs(texto):
    """Só o miolo do sprite. A raiz `<svg class="sprite">` fica de fora: a
    classe dela é legítima (é o que esconde o sprite da tela), e é dentro do
    `<defs>` que a régua vale."""
    return texto[texto.index("<defs>"):texto.index("</defs>")]


def _sem_comentario(texto):
    texto = re.sub(r"{% comment %}.*?{% endcomment %}", "", texto, flags=re.S)
    return re.sub(r"{#.*?#}", "", texto, flags=re.S).strip()


class SpriteDasIlustracoesTests(SimpleTestCase):
    def setUp(self):
        self.texto = _texto()
        self.simbolos = _simbolos(self.texto)

    def test_as_onze_familias_existem_e_so_elas(self):
        """O card pede a cena pelo nome da família da receita. Família sem
        símbolo desenha um retângulo vazio, sem erro no console; símbolo a mais
        é peso morto que ninguém mais remove, porque ninguém sabe se alguém o
        usa. A contagem é EXATA pelos dois motivos."""
        encontrados = re.findall(r'<symbol id="([^"]+)"', self.texto)
        self.assertEqual(encontrados, list(IDS))
        self.assertEqual(len(self.simbolos), len(IDS), "símbolo sem id, ou `<symbol>` sem fechar")

    def test_toda_cena_desenha_na_grade_de_48_por_36(self):
        """A faixa do card é 4:3. Uma cena desenhada noutra grade não erra —
        ela ESTICA: o `<use>` ajusta a caixa e o traço sai grosso num eixo e
        fino no outro, que é o defeito que ninguém reporta e todo mundo vê."""
        for tag in self.simbolos:
            with self.subTest(simbolo=tag[:40]):
                self.assertIn(GRADE, tag)

    def test_toda_cena_declara_o_traco_nela_mesma(self):
        """O `<use>` clona o símbolo para dentro do consumidor, e o clone herda
        do CONSUMIDOR — nunca da raiz deste arquivo. Medido no sprite dos
        ícones em 16/09/2026: com a espessura só na raiz, o desenho saía com
        traço 1 (1 397 px de tinta contra 2 789). Aqui a raiz nem declara
        espessura, para ninguém confiar num atributo inerte."""
        for tag in self.simbolos:
            with self.subTest(simbolo=tag[:40]):
                self.assertIn(TRACO, tag)

    def test_nenhuma_cor_escrita_a_mao(self):
        """O app tem dois regimes (Ferro escuro e Papel claro) e a cena herda a
        cor de quem a consome. Uma cor fixa aqui ficaria certa num regime e
        invisível no outro — e o consumidor não teria como corrigir, porque o
        atributo do símbolo vence o dele."""
        self.assertEqual(cores_cruas(self.texto), [])
        self.assertEqual(fills_fora_do_contrato(self.texto), [])

    def test_cada_cena_tem_no_maximo_uma_massa_e_ela_obedece_a_faixa(self):
        """A massa dá peso ao prato sem chapar o desenho. Ela é `fill-opacity`
        e não `opacity` porque `opacity` apaga o contorno junto — o traço é o
        que define a cena. Duas massas por cena já é ilustração pintada, que é
        outra linguagem visual."""
        com_massa = 0
        for tag in self.simbolos:
            with self.subTest(simbolo=tag[:40]):
                massas = re.findall(r'fill-opacity="([^"]+)"', tag)
                self.assertLessEqual(len(massas), 1, "mais de um preenchimento na mesma cena")
                self.assertEqual(
                    tag.count('fill="currentColor"'),
                    len(massas),
                    "preenchimento sem `fill-opacity`, ou opacidade sem preenchimento",
                )
                for valor in massas:
                    self.assertTrue(
                        MASSA_MIN <= float(valor) <= MASSA_MAX,
                        f"massa fora da faixa {MASSA_MIN}–{MASSA_MAX}: {valor}",
                    )
                com_massa += len(massas)
        self.assertTrue(com_massa, "nenhuma cena usa massa: a régua acima deixou de medir algo")

    def test_o_defs_nao_tem_imagem_texto_filtro_animacao_estilo_nem_classe(self):
        """Ilustração de interface: traço e nada mais. `<image>` traria um bitmap
        que não acompanha a cor do tema; `<text>` traria frase sem tradução e
        sem `{% translate %}`; `<filter>` e `<animate>` custam quadros em cada
        card de uma lista; `style=` e `class=` furam o sistema de tokens e
        fariam a cena depender do CSS estar carregado."""
        defs = _defs(self.texto)
        for proibido in PROIBIDOS_NO_DEFS:
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, defs)

    def test_o_arquivo_cabe_no_orcamento_de_bytes(self):
        """O sprite viaja no HTML de toda página com refeição — não é estático
        com cache próprio.

        A conta inclui o fim de linha do CHECKOUT: com `core.autocrlf` ligado
        (esta máquina) são ~132 bytes a mais que no runner Linux do CI, um por
        linha. O teto tem folga para os dois, e é de propósito que o teste não
        normaliza antes de medir — o que o navegador baixa é o arquivo como
        ele está no disco de quem serve."""
        tamanho = len(ARQUIVO.read_bytes())
        self.assertLess(
            tamanho,
            TETO_DE_BYTES,
            f"o sprite tem {tamanho} bytes, teto {TETO_DE_BYTES}",
        )
        # A folga aparece no log para a próxima pessoa saber quanto ainda cabe
        # antes de precisar decidir entre cortar cena ou subir o teto.
        print(f"\nilustracoes_de_receita.html: {tamanho} bytes, folga de {TETO_DE_BYTES - tamanho}")

    def test_o_sprite_e_xml_bem_formado(self):
        """Tag sem fechar ou aspas trocadas não param o navegador: ele conserta
        à sua maneira e o `<use>` passa a apontar para um símbolo que absorveu
        o vizinho. Os testes de texto acima continuariam verdes."""
        raiz = ET.fromstring(_sem_comentario(self.texto))
        self.assertEqual([s.get("id") for s in raiz.findall(".//symbol")], list(IDS))
        for simbolo in raiz.findall(".//symbol"):
            with self.subTest(simbolo=simbolo.get("id")):
                self.assertTrue(len(list(simbolo)), "cena vazia")


class ControlePositivoDaReguaTests(SimpleTestCase):
    """Régua que não acusa nada passa verde para sempre — inclusive no dia em
    que alguém escrever `#ff0000` no sprite. Estes dois testes provam que as
    funções de cima ENXERGAM o que dizem enxergar."""

    def test_a_regua_enxerga_cor_escrita_a_mao(self):
        self.assertEqual(cores_cruas('<path fill="#ff0000"/>'), ["#ff0000"])
        self.assertEqual(cores_cruas('<path stroke="rgb(20, 20, 20)"/>'), ["rgb("])
        self.assertEqual(cores_cruas('<path stroke="hsl(90 10% 10%)"/>'), ["hsl("])
        self.assertEqual(cores_cruas('<path stroke="currentColor"/>'), [])

    def test_a_regua_enxerga_preenchimento_fora_do_contrato(self):
        self.assertEqual(fills_fora_do_contrato('<path fill="red"/>'), ["red"])
        self.assertEqual(fills_fora_do_contrato('<path fill="#0f0"/>'), ["#0f0"])
        self.assertEqual(fills_fora_do_contrato('<path fill="none"/>'), [])
        # A massa legítima não pode ser confundida com um `fill` proibido: o
        # padrão `fill="` não ocorre dentro de `fill-opacity="`.
        self.assertEqual(fills_fora_do_contrato('<path fill="currentColor" fill-opacity=".15"/>'), [])
