"""A RÉGUA DA VOZ (`docs/VOZ.md`, pente-fino de qualidade, onda 6, 28/09/2026).

Varre o texto LITERAL de `templates/` — sem comentário de template,
`<script>`, `<style>`, comentário HTML, tag nem `{{ }}`/`{% %}` — contra a
lista de proibidos do guia. O que o servidor calcula não passa por aqui;
a régua pega o que alguém escreveu à mão numa tela.

O primeiro achado dela foi a FAQ da ofensiva: "o app diz o que faltou",
uma frase que a rodada 2 de 24/09 já tinha tirado da Home.
"""
import html
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES = Path(settings.BASE_DIR) / "templates"

#: Pastas e arquivos com exceção declarada no `docs/VOZ.md`.
EXCECOES = ("legal", "analytics", "gestao")
ARQUIVOS_EXCETUADOS = {"demo/sobre.html"}

PROIBIDOS = {
    "punição": re.compile(
        r"\b(você falhou|o que faltou|fracass\w*|preguiç\w*|sem desculpas?|desistiu|vergonha)\b",
        re.IGNORECASE,
    ),
    "contrato": re.compile(r"\bcombinad[oa]s?\b", re.IGNORECASE),
    "jargão de software": re.compile(
        r"\b(usuári[oa]s?|login|logout|view|requisição|endpoint|middleware|token)\b",
        re.IGNORECASE,
    ),
    # A sigla só vale entre parênteses, depois do termo em português.
    "sigla solta": re.compile(r"(?<!\()\b(TDEE|TMB|RIR|1RM)\b(?!\))"),
}


def texto_literal(fonte):
    fonte = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", " ", fonte, flags=re.S)
    fonte = re.sub(r"{#.*?#}", " ", fonte, flags=re.S)
    fonte = re.sub(r"<(script|style)\b.*?</\1>", " ", fonte, flags=re.S | re.I)
    fonte = re.sub(r"<!--.*?-->", " ", fonte, flags=re.S)
    # `{% translate "…" %}` é texto que a pessoa lê: o conteúdo fica.
    fonte = re.sub(r"{%\s*(?:translate|trans)\s+\"([^\"]*)\"[^%]*%}", r" \1 ", fonte)
    fonte = re.sub(r"{%.*?%}|{{.*?}}", " ", fonte, flags=re.S)
    fonte = re.sub(r"<[^>]+>", " ", fonte)
    return re.sub(r"\s+", " ", html.unescape(fonte))


def varrer():
    achados = []
    for caminho in sorted(TEMPLATES.rglob("*.html")):
        relativo = caminho.relative_to(TEMPLATES).as_posix()
        if relativo.split("/")[0] in EXCECOES or relativo in ARQUIVOS_EXCETUADOS:
            continue
        texto = texto_literal(caminho.read_text(encoding="utf-8"))
        for categoria, padrao in PROIBIDOS.items():
            for achado in padrao.finditer(texto):
                trecho = texto[max(0, achado.start() - 40):achado.end() + 30]
                achados.append("%s [%s]: …%s…" % (relativo, categoria, trecho))
    return achados


class AVozDasTelasTests(SimpleTestCase):
    def test_nenhum_template_usa_palavra_proibida_pelo_guia_de_voz(self):
        achados = varrer()
        self.assertEqual(achados, [], "\n" + "\n".join(achados))

    def test_controle_a_regua_enxerga_o_que_procura(self):
        """Controle positivo: cada categoria pega um exemplo escrito à mão —
        e o comentário de template e o `{{ }}` ficam de fora."""
        amostra = texto_literal(
            '<p>Ontem {% translate "o que faltou" %} para o usuário</p>'
            "<p>Gasto (TMB) e TDEE sozinho, dia combinado.</p>"
            "{% comment %}usuário{% endcomment %}{{ usuario }}"
        )
        for categoria in ("punição", "contrato", "jargão de software", "sigla solta"):
            self.assertTrue(PROIBIDOS[categoria].search(amostra), categoria)
        self.assertEqual(len(PROIBIDOS["jargão de software"].findall(amostra)), 1)
        self.assertEqual(PROIBIDOS["sigla solta"].findall(amostra), ["TDEE"])
