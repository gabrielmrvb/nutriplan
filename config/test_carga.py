# -*- coding: utf-8 -*-
"""O teste de carga do staging (21/09/2026): o fluxo manual e o roteiro do k6.

O k6 não roda aqui (é job manual, contra o staging); o que se prende é o
CONTRATO: só pelo botão, só contra o staging (o roteiro exige `"ambiente":
"staging"` e produção não aparece em lugar nenhum), só GET (nenhuma conta
nasce), p95 por rota e por degrau no relatório, o teto com o critério
escrito, e o relatório anexado mesmo quando um limiar estoura (código 99 do
k6 é resultado, não falha). Com `node` na máquina, a sintaxe do roteiro é
conferida de verdade.
"""
import re
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[1]
FLUXO = (RAIZ / ".github" / "workflows" / "carga.yml").read_text(encoding="utf-8")
ROTEIRO = (RAIZ / "scripts" / "carga" / "staging.js").read_text(encoding="utf-8")


def sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class OFluxoDeCargaTests(SimpleTestCase):
    def test_so_pelo_botao(self):
        corpo = sem_comentarios(FLUXO)
        self.assertIn("workflow_dispatch:", corpo)
        self.assertNotIn("schedule:", corpo, "carga não roda sozinha")
        self.assertNotIn("push:", corpo)
        self.assertNotIn("pull_request:", corpo)

    def test_so_contra_o_staging(self):
        corpo = sem_comentarios(FLUXO)
        self.assertIn("CARGA_BASE: https://nutriplan-staging.onrender.com", corpo)
        self.assertNotIn("nutriplan-xxfn", FLUXO)
        self.assertNotIn("nutriplan-xxfn", ROTEIRO)

    def test_os_degraus_e_a_duracao_sao_entradas_com_50_no_padrao(self):
        self.assertRegex(FLUXO, r'default:\s*"10,25,50,75,100"')
        self.assertIn("CARGA_DEGRAUS: ${{ github.event.inputs.degraus }}", FLUXO)
        self.assertIn("CARGA_DURACAO: ${{ github.event.inputs.duracao }}", FLUXO)

    def test_limiar_estourado_e_resultado_e_nao_falha_do_job(self):
        corpo = sem_comentarios(FLUXO)
        self.assertIn('[ "$codigo" -ne 99 ]', corpo)
        self.assertIn("test -s relatorio.md", corpo)

    def test_o_relatorio_vai_para_o_resumo_e_para_o_artefato_sempre(self):
        corpo = sem_comentarios(FLUXO)
        self.assertIn('cat relatorio.md >> "$GITHUB_STEP_SUMMARY"', corpo)
        artefato = corpo.index("upload-artifact")
        self.assertIn("if: always()", corpo[artefato - 300:artefato])
        self.assertIn("relatorio.md", corpo[artefato:])
        self.assertIn("resumo.json", corpo[artefato:])


class ORoteiroDoK6Tests(SimpleTestCase):
    def test_exige_staging_no_setup(self):
        self.assertIn('ambiente !== "staging"', ROTEIRO)
        self.assertIn("a carga só roda contra o staging", ROTEIRO)

    def test_so_get_nenhuma_conta_nasce(self):
        corpo = sem_comentarios(ROTEIRO)
        self.assertNotIn("http.post", corpo)
        self.assertNotIn("cadastro", corpo)
        self.assertIn("http.get", corpo)

    def test_as_rotas_cobrem_o_app_inteiro_pelo_demo(self):
        rotas = dict(re.findall(r'\["([\w-]+)", "([^"]+)"\]', ROTEIRO))
        for caminho in ("/", "/saude/vivo/", "/demo/hoje/", "/demo/treino/", "/demo/historico/"):
            self.assertIn(caminho, rotas.values(), caminho)
        self.assertNotIn("/saude/", rotas.values(), "o readiness consulta o banco e não é rota de gente")

    def test_p95_por_rota_e_por_degrau_e_o_teto_com_criterio(self):
        self.assertIn("http_req_duration{degrau:${n},rota:${rota}}", ROTEIRO)
        self.assertIn("http_req_failed{degrau:${n}}", ROTEIRO)
        self.assertIn("export function teto(", ROTEIRO)
        self.assertIn("TETO ENCONTRADO", ROTEIRO)
        self.assertIn('"relatorio.md": relatorio(data)', ROTEIRO)

    def test_a_sintaxe_do_roteiro_passa_no_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("sem node nesta máquina; o CI tem")
        r = subprocess.run([node, "--check", "--input-type=module", "-"], input=ROTEIRO, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
