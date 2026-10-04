"""A distância se escreve de um jeito só, em toda tela.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, M2).
A mesma corrida aparecia como "5,20 km" na lista e "5,2 km" na Home. Não
havia número errado: cada template escolhia o próprio formato (o filtro `km`
da corrida sempre imprimia duas casas; `floatformat:1` cortava a segunda).

A regra agora é uma função, `config.numeros.decimal_curto`: até duas casas,
sem zero à direita e com vírgula (5,2 · 5,23 · 10). Ela chega aos templates
pelo filtro embutido `distancia` (metros para km). A varredura abaixo impede
um template de voltar a formatar distância por conta própria. A carga (M1)
entrou na mesma régua na parte 2 (item 5, 28/09/2026, filtro `carga`, classe
`NenhumTemplateDeTreinoFormataCargaSozinhoTests` abaixo).
"""
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase

from config.numeros import carga, decimal_curto, distancia

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

    def test_o_filtro_carga(self):
        """Item 5 da parte 2 (28/09/2026): a carga usa a mesma função da
        distância — até duas casas, sem zero à direita, sempre vírgula.
        `floatformat:'-2'` mantinha o zero ("62,50"); vira ruído "62,5"."""
        self.assertEqual(carga(60), "60")
        self.assertEqual(carga(Decimal("42.50")), "42,5")
        self.assertEqual(carga(Decimal("62.25")), "62,25")
        self.assertEqual(carga(None), "—")

    def test_o_filtro_carga_com_numero_negativo(self):
        """Fix round 1 (achado da revisão, `task-A-review.md`, risco 2):
        `agora.html:864` renderiza `atual.load.delta|carga` quando a carga
        caiu ("▼ {{ delta }} kg") — um caminho de produção real com número
        negativo, sem teste até aqui. `-2,50` não pode virar "-0" nem perder
        o sinal."""
        self.assertEqual(carga(Decimal("-2.50")), "-2,5")
        self.assertEqual(carga(-10), "-10")
        self.assertEqual(carga(Decimal("-0.00")), "0")

    def test_o_filtro_carga_esta_em_todo_template_sem_load(self):
        html = Template("{{ p|carga }} kg").render(Context({"p": Decimal("59.50")}))
        self.assertEqual(html, "59,5 kg")


class NenhumTemplateFormataDistanciaSozinhoTests(SimpleTestCase):
    PROIBIDO = [
        (re.compile(r"\|km\b"), "o |km da corrida imprime '5,20'; use |distancia"),
        (re.compile(r"_km\|floatformat"), "km com floatformat; use |distancia"),
        (re.compile(r"floatformat:\s*['\"]-2['\"]"), "floatformat:'-2' imprime '42,50'; use |carga"),
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
        fontes = ["{{ c.distancia_m|km }}", "{{ corrida_km|floatformat:1 }}", "{{ x|floatformat:'-2' }}", '{{ x|floatformat:"-2" }}']
        for fonte in fontes:
            with self.subTest(fonte=fonte):
                self.assertTrue(any(r.search(fonte) for r, _ in self.PROIBIDO))


class NenhumTemplateDeTreinoFormataCargaSozinhoTests(SimpleTestCase):
    """A carga se escreve de um jeito só, no mesmo molde da distância (item 5,
    parte 2, 28/09/2026): `floatformat:'-2'` era o jeito ad hoc, repetido em
    12+ lugares de `templates/workouts/`, que mantinha o zero à direita
    ("62,50"). O filtro `carga` (`config/numeros.py`) descarta esse zero. A
    varredura impede que outro template de `templates/workouts/` volte a
    formatar carga por conta própria.

    Fix round 1 (28/09/2026, achados da revisão em `task-A-review.md`):

    1. A régua original só pegava o argumento literal `-2`/`-2g` — um
       `floatformat:2` (sem o sinal, mantém o zero) ou um `floatformat`/
       `stringformat` puro passariam batidos. Agora ela olha o NOME da
       variável formatada (contém `carga`, `peso`, `weight`, `load` ou
       `referencia`), não o argumento do filtro — pega qualquer
       `floatformat`/`stringformat` numa variável de carga, e não confunde
       reps, segundos, km nem percentual (nomes sem essas palavras) com
       carga.
    2. A exclusão do volume era um sufixo genérico, `(?<!volume)`, que
       pouparia qualquer identificador terminado em "...volume". Vira uma
       lista NOMEADA com as exceções reais, todas totais de SESSÃO (Σ
       peso×reps) ou coordenada de gráfico, nunca a carga de uma série:
       `estado.placar.carga_total` (`agora.html`) e `sessao.volume`
       (`_series_do_dia.html`) são o total do dia, com separador de milhar
       por decisão própria (achado #16 das personas); `curva_carga.ultimo.0`
       e `.1` (`exercicio.html`) são o PONTO do gráfico em pixels — usam
       `stringformat:'g'` só para não interpolar em notação científica, não
       são kg.
    """

    VARIAVEL_DE_CARGA = re.compile(r"carga|peso|weight|load|referencia", re.IGNORECASE)
    USO_DE_FORMATADOR = re.compile(r"([\w.]+)\s*\|\s*(?:float|string)format\b")
    NAO_E_CARGA_DE_SERIE = {
        "estado.placar.carga_total",  # total do dia, não de uma série
        "sessao.volume",              # total do dia, mesmo molde (achado #16)
        "curva_carga.ultimo.0",       # coordenada do gráfico, não kg
        "curva_carga.ultimo.1",       # coordenada do gráfico, não kg
    }

    def test_varredura(self):
        achados = []
        for arquivo in sorted((TEMPLATES / "workouts").rglob("*.html")):
            fonte = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
            for casou in self.USO_DE_FORMATADOR.finditer(fonte):
                variavel = casou.group(1)
                if not self.VARIAVEL_DE_CARGA.search(variavel):
                    continue
                if variavel in self.NAO_E_CARGA_DE_SERIE:
                    continue
                linha = fonte.count("\n", 0, casou.start()) + 1
                achados.append("%s:%d — %s" % (arquivo.relative_to(TEMPLATES), linha, variavel))
        self.assertEqual(achados, [])

    def test_a_varredura_enxerga_qualquer_formatador_alem_do_literal_menos_dois(self):
        """Controle positivo, achado 1 da revisão: não só '-2'/'-2g' — QUALQUER
        floatformat/stringformat numa variável de carga é pego."""
        fontes = [
            "{{ peso|floatformat:'-2' }}",         # forma antiga
            "{{ peso|floatformat:2 }}",             # sem sinal, mantém o zero
            "{{ atual.load.delta|floatformat }}",   # sem argumento nenhum
            "{{ serie.carga|stringformat:'.2f' }}",
        ]
        for fonte in fontes:
            with self.subTest(fonte=fonte):
                casou = self.USO_DE_FORMATADOR.search(fonte)
                self.assertIsNotNone(casou, fonte)
                self.assertTrue(self.VARIAVEL_DE_CARGA.search(casou.group(1)), fonte)

    def test_a_varredura_nao_marca_reps_segundos_km_ou_percentual(self):
        """Controle negativo: nomes sem carga/peso/weight/load/referencia não
        disparam a régua, mesmo formatados com floatformat/stringformat."""
        fontes = [
            "{{ linha.reps|floatformat:0 }}",
            "{{ atual.segundos|floatformat:0 }}",
            "{{ corrida_km|floatformat:1 }}",
            "{{ progresso.pct|floatformat:0 }}",
        ]
        for fonte in fontes:
            with self.subTest(fonte=fonte):
                casou = self.USO_DE_FORMATADOR.search(fonte)
                self.assertIsNotNone(casou, fonte)
                self.assertIsNone(self.VARIAVEL_DE_CARGA.search(casou.group(1)), fonte)

    def test_a_varredura_nao_marca_os_totais_de_sessao_nem_o_ponto_do_grafico(self):
        """Controle negativo, achado 2 da revisão: exceções NOMEADAS, não um
        sufixo genérico tipo `(?<!volume)` que pouparia qualquer
        `..._volume`. As três formatam com um nome que CONTÉM "carga", mas
        nenhuma é a carga de uma série."""
        fontes = [
            "{{ estado.placar.carga_total|floatformat:'0g' }}",
            '{{ sessao.volume|floatformat:"-2g" }}',
            "{{ curva_carga.ultimo.0|stringformat:'g' }}",
        ]
        for fonte in fontes:
            with self.subTest(fonte=fonte):
                casou = self.USO_DE_FORMATADOR.search(fonte)
                self.assertIsNotNone(casou, fonte)
                self.assertIn(casou.group(1), self.NAO_E_CARGA_DE_SERIE)
