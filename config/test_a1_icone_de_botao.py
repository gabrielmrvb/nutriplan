"""O ícone dentro de um botão tem tamanho — achado A1 da auditoria visual.

O caso real: `Compartilhar treino`, em `/treino/`, renderizava o `<svg>` a
**176,35 × 176,35 px** em produção. Medido com `getBoundingClientRect()`, não
estimado. Os outros ícones de botão da MESMA tela mediam 18 e 34. O botão
ficava com 200px de altura no lugar dos 52 do `.btn`, e o rótulo quebrava no
meio da palavra: "Compartilha / r treino".

Por que ninguém viu antes: o defeito mora a 4.686px de uma página de 5.530px.
Contagem de elementos não pega — só medição pega.

A causa não era daquele botão. O app dimensiona TODO SVG por classe de
invólucro, e nunca houve regra para `<svg>` direto dentro de `.btn`. Sem
width/height e dentro de um `inline-flex`, o SVG estica.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css" / "app.css"
TEMPLATES = RAIZ / "templates"


def sem_comentarios(texto):
    """O texto sem comentários de CSS.

    Obrigatório aqui, e não é zelo: o comentário que explica esta correção
    CITA `.btn > svg` e `.pill svg` por extenso. Sem remover comentário, o
    teste passaria por causa da prosa que descreve a regra — exatamente o
    modo de falhar que o `CLAUDE.md` registra como recorrente neste projeto.
    """
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


class OIconeDeBotaoTemTamanhoTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_existe_regra_dimensionando_svg_dentro_de_botao(self):
        """A regra que fecha a classe inteira do defeito."""
        regra = re.search(r"\.btn\s*>\s*svg\s*\{([^}]*)\}", self.css)

        self.assertIsNotNone(
            regra,
            "sumiu a regra `.btn > svg`. Sem ela, um <svg> sem width/height "
            "dentro de um .btn volta a esticar — foi o achado A1.",
        )
        corpo = regra.group(1)
        self.assertIn("width:", corpo)
        self.assertIn("height:", corpo)

    def test_o_icone_nao_encolhe_quando_o_rotulo_e_longo(self):
        """`flex: none` é o que impede o outro lado do mesmo defeito.

        `.btn` é `inline-flex`. Sem `flex: none`, um rótulo longo comprime o
        ícone em vez de quebrar a linha — o ícone deixa de esticar e passa a
        sumir. Dimensionar sem travar o encolhimento troca um defeito por
        outro.
        """
        regra = re.search(r"\.btn\s*>\s*svg\s*\{([^}]*)\}", self.css)
        self.assertIn("flex: none", regra.group(1))

    def test_todo_svg_solto_dentro_de_botao_esta_coberto(self):
        """Controle positivo: o defeito era um `<svg>` SEM classe.

        Uma regra `.btn > svg` cobre o caso por posição, e este teste existe
        para provar que a cobertura é real — ele encontra os `<svg>` nus
        dentro de `.btn` nos templates e falha se algum deixar de casar com
        o seletor. Se amanhã alguém trocar a regra por `.btn__icone svg`, um
        ícone sem classe volta a ficar descoberto e este teste avisa.
        """
        nus = []
        for tpl in TEMPLATES.rglob("*.html"):
            html = tpl.read_text(encoding="utf-8")
            for m in re.finditer(r'class="[^"]*\bbtn\b[^"]*"', html):
                trecho = html[m.end():m.end() + 700]
                # o proximo elemento aberto depois do atributo de classe
                prox = re.search(r"<(\w+)([^>]*)>", trecho)
                if prox and prox.group(1) == "svg":
                    attrs = prox.group(2)
                    tem_classe = re.search(r"\sclass=", attrs)
                    # `\swidth=` e nao `width=`: o proprio botao do achado A1
                    # traz `stroke-width="1.9"`, e a busca por substring dava
                    # esse SVG como dimensionado. O teste passou a primeira
                    # vez justamente por nao achar o caso que veio medir.
                    tem_medida = re.search(r"\swidth=", attrs)
                    if not tem_classe and not tem_medida:
                        nus.append(f"{tpl.relative_to(RAIZ)}")

        self.assertTrue(
            nus,
            "nenhum <svg> nu dentro de .btn foi encontrado nos templates. "
            "Ou o markup mudou, ou este teste parou de medir o que diz medir "
            "— e um teste que não encontra o caso não prova a cobertura.",
        )
        self.assertRegex(self.css, r"\.btn\s*>\s*svg")
