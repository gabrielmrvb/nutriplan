"""Todo nome de evento usado no código está no catálogo.

Analytics vira lixo por dois caminhos: um nome digitado errado
(`treino.inciado`) que cria um evento fantasma, e um nome que ninguém documentou.
Este teste fecha o primeiro: ele VARRE o código atrás de todo lugar que dispara
um evento — a chamada de servidor `evento(request, "…")`, o `npTrack("…")` do
cliente e o `data-evento="…"` do template — e exige que cada nome esteja em
`catalogo.CATALOGO`.

Um nome fora do catálogo reprova aqui, na hora de escrever, e não seis semanas
depois quando o painel mostra dois eventos que deviam ser um.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

from analytics import catalogo

RAIZ = Path(__file__).resolve().parent.parent

# `evento(request, "x")` e `evento_anonimo(request, "x")`, `npTrack("x")`,
# `data-evento="x"`.
PADROES = [
    re.compile(r"""evento(?:_anonimo)?\(\s*[\w.]+\s*,\s*["']([^"']+)["']"""),
    re.compile(r"""npTrack\(\s*["']([^"']+)["']"""),
    re.compile(r"""data-evento=["']([^"']+)["']"""),
]

# Onde procurar, e o que ignorar (o próprio catálogo, os testes, o helper).
PASTAS = ["accounts", "plans", "workouts", "achievements", "push", "static", "templates"]
IGNORAR = {"catalogo.py", "test_taxonomia.py", "servidor.py", "analytics.js"}


def nomes_no_codigo():
    achados = {}
    for pasta in PASTAS:
        base = RAIZ / pasta
        if not base.exists():
            continue
        for caminho in base.rglob("*"):
            if caminho.suffix not in (".py", ".js", ".html"):
                continue
            if caminho.name in IGNORAR:
                continue
            texto = caminho.read_text(encoding="utf-8", errors="replace")
            for padrao in PADROES:
                for nome in padrao.findall(texto):
                    achados.setdefault(nome, caminho.relative_to(RAIZ).as_posix())
    return achados


class TaxonomiaFechadaTests(SimpleTestCase):
    def test_todo_nome_usado_no_codigo_esta_no_catalogo(self):
        fora = {
            nome: onde
            for nome, onde in nomes_no_codigo().items()
            if not catalogo.existe(nome)
        }
        self.assertEqual(
            fora, {}, "nomes de evento fora do catálogo (analytics/catalogo.py): %s" % fora
        )

    def test_o_teste_enxerga_os_eventos_de_verdade(self):
        """Controle positivo: se a varredura não achasse nada, o teste acima
        passaria por vazio. Exige que ela encontre os eventos que instrumentamos
        de fato — senão o guarda não guarda."""
        achados = set(nomes_no_codigo())
        for esperado in ("conta.criada", "dieta.refeicao_registrada", "treino.serie_concluida"):
            self.assertIn(esperado, achados)
