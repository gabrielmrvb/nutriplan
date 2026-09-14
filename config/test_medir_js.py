"""`scripts/qa/medir.js` e o baseline que ele produziu concordam nas chaves.

O script é a régua da auditoria de design (14/09/2026): roda no navegador,
conta tamanhos de fonte, pesos, raios, sombras, fundos e botões de uma tela,
e o JSON em `docs/design-audit/` é a Home a 390 px ANTES da fundação de
design. Toda onda que mexer em `app.css` compara o depois com esse antes.

O que pode envelhecer em silêncio é o par: alguém acrescenta uma métrica ao
script e o baseline continua sem ela — e a comparação "antes × depois" passa
a comparar chaves diferentes. Este teste lê as chaves do PRÓPRIO script (do
objeto que ele devolve) e cobra cada uma no JSON. Sabotagem que precisa ficar
vermelha: apagar `pageH` do JSON, ou acrescentar `foo:` ao `return` do script.
"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SCRIPT = Path(settings.BASE_DIR) / "scripts" / "qa" / "medir.js"
BASELINE = Path(settings.BASE_DIR) / "docs" / "design-audit" / "baseline-home-390.json"


def chaves_emitidas(fonte):
    """As chaves do objeto literal devolvido pelo script.

    O `return { ... }` é o último bloco do arquivo; dentro dele, cada chave
    é um identificador seguido de dois-pontos no início de um item — `url:`,
    `pageH:`, `h1: h1 ? {...}`. Chaves abreviadas (`cards,` sem valor) também
    são chaves, e o regex as pega pelo separador.
    """
    inicio = fonte.rfind("return {")
    corpo = fonte[inicio + len("return {"):]
    corpo = corpo[: corpo.rfind("}")]
    # Remove objetos aninhados (o `h1: {...}`) para não ler `txt:` como chave.
    corpo = re.sub(r"\{[^{}]*\}", "{}", corpo)
    return set(re.findall(r"(?:^|[,\n]\s*)([A-Za-z_]\w*)\s*(?=[:,\n])", corpo))


class MedirJsTests(SimpleTestCase):
    def test_o_script_devolve_as_metricas_da_auditoria(self):
        chaves = chaves_emitidas(SCRIPT.read_text(encoding="utf-8"))
        # Controle positivo: o regex enxerga as chaves que o script tem hoje.
        self.assertTrue({"url", "pageH", "sizes", "weights", "radii", "shadowed", "bgs", "btns"} <= chaves, chaves)

    def test_o_baseline_tem_toda_chave_que_o_script_emite(self):
        chaves = chaves_emitidas(SCRIPT.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertIsInstance(baseline, dict, "o baseline foi gravado como string JSON dentro de JSON")
        faltam = sorted(chaves - set(baseline))
        self.assertEqual(faltam, [], "o script emite chaves que o baseline não tem: %s" % faltam)

    def test_o_baseline_e_a_home_a_390_com_altura_medida(self):
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(baseline["url"], "/")
        self.assertGreater(baseline["pageH"], 0)
        self.assertIn("390", baseline["_tela"])
