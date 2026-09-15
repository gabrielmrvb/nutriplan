"""A família de classes do peso é `.pesagem`; `.semana` é só a barra semanal.

DESIGN CA-02 / SBS-01 (14/09/2026): `.semana` era usada por DOIS componentes
— a linha de média de peso (`_peso.html`) e a barra de dias por semana de
treino e água (`_progresso_*.html`, `hydration.html`). A regra do peso se
escopava como `.semanas > .semana` para vencer a colisão, e vencia demais:
as listas de treino e água também são `<ul class="semanas"><li
class="semana">`, e ganhavam o padding, o fundo e o grid de duas colunas do
peso — 552 px de altura para oito linhas de 32 (medido a 390).

Renomear é a correção: o peso vira `.pesagens > .pesagem`, e `.semana` volta
a ter uma única definição. Sabotagem que precisa ficar vermelha: qualquer
regra `.semanas > .semana` voltar, ou `.semana {` ganhar `padding`/`background`.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
PESO = Path(settings.BASE_DIR) / "templates" / "plans" / "_peso.html"


def sem_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class UmaClasseUmComponenteTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_o_peso_nao_se_veste_de_semana(self):
        self.assertNotIn(".semanas > .semana", self.css)
        self.assertIn(".pesagens > .pesagem {", self.css)
        self.assertNotIn('class="semana', PESO.read_text(encoding="utf-8"))
        self.assertIn('class="pesagens"', PESO.read_text(encoding="utf-8"))

    def test_a_barra_semanal_continua_leve(self):
        m = re.search(r"(?:^|\})\s*\.semana\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertNotIn("padding", m.group(1))
        self.assertNotIn("background", m.group(1))
        self.assertIn("grid-template-columns: 3.2rem 1fr auto", m.group(1))
