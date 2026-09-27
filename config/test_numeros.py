"""A distância se escreve de um jeito só, em toda tela.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, M2).
A mesma corrida aparecia como "5,20 km" na lista e "5,2 km" na Home. Não
havia número errado: cada template escolhia o próprio formato (o filtro `km`
da corrida sempre imprimia duas casas; `floatformat:1` cortava a segunda).

A regra agora é uma função, `config.numeros.decimal_curto`: até duas casas,
sem zero à direita e com vírgula (5,2 · 5,23 · 10). Ela chega aos templates
pelo filtro embutido `distancia` (metros para km). A varredura abaixo impede
um template de voltar a formatar distância por conta própria. A carga (M1)
entra na mesma régua na parte 2, quando `workouts/` estiver livre.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase

from config.numeros import decimal_curto, distancia

TEMPLATES = Path(settings.BASE_DIR) / "templates"


def _sem_comentarios(fonte):
    fonte = re.sub(r"{% comment %}.*?{% endcomment %}", "", fonte, flags=re.S)
    return re.sub(r"{#.*?#}", "", fonte, flags=re.S)


class AFuncaoTests(SimpleTestCase):
    def test_ate_duas_casas_sem_zero_a_direita(self):
        casos = {40: "40", Decimal("42.50"): "42,5", 1.25: "1,25", Decimal("0.00"): "0",
                 5.2: "5,2", 5.234: "5,23", 10.0: "10", 1234.5: "1234,5"}
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(decimal_curto(valor), esperado)

    def test_os_filtros(self):
        self.assertEqual(distancia(5200), "5,2")
        self.assertEqual(distancia(5230), "5,23")
        self.assertEqual(distancia(None), "—")
        self.assertEqual(distancia("lixo"), "—")

    def test_os_filtros_estao_em_todo_template_sem_load(self):
        html = Template("{{ m|distancia }} km").render(Context({"m": 5200}))
        self.assertEqual(html, "5,2 km")


class NenhumTemplateFormataDistanciaSozinhoTests(SimpleTestCase):
    PROIBIDO = [
        (re.compile(r"\|km\b"), "o |km da corrida imprime '5,20'; use |distancia"),
        (re.compile(r"_km\|floatformat"), "km com floatformat; use |distancia"),
    ]

    def test_varredura(self):
        achados = []
        for arquivo in sorted(TEMPLATES.rglob("*.html")):
            if "email" in arquivo.parts:
                continue
            fonte = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
            for regra, motivo in self.PROIBIDO:
                for casou in regra.finditer(fonte):
                    linha = fonte.count("\n", 0, casou.start()) + 1
                    achados.append("%s:%d — %s" % (arquivo.relative_to(TEMPLATES), linha, motivo))
        self.assertEqual(achados, [])

    def test_a_varredura_enxerga_o_defeito(self):
        """Controle positivo: as regras casam com as formas que existiam."""
        fontes = ["{{ c.distancia_m|km }}", "{{ corrida_km|floatformat:1 }}"]
        for fonte in fontes:
            with self.subTest(fonte=fonte):
                self.assertTrue(any(r.search(fonte) for r, _ in self.PROIBIDO))
