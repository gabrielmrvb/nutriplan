# -*- coding: utf-8 -*-
"""Imagem no repositório tem teto: as 14 MB de shots de 14/09 ficaram fora,
e estas sete só entram porque cabem (≤ 250 KB cada, spec §8). Desde o veto
de 17/09/2026 (NERVURA · ANDAIME) são CAPTURAS da NERVURA implementada — o
app local com o demo (`joao@demo.local`) e um usuário de QA descartável para
a execução e o placar —, a 390 px no tema padrão (Ferro), quantizadas a 96
cores e cortadas a 1600 px de altura: a referência visual do sistema
principal para o Claude Design (`scripts/montar_semente.py`) é o próprio
app, porque a direção 1 do Claude Design só desenhou três telas
(`referencias/direcoes/d1-*`). Sem dado de conta real. Até 17/09 eram os
sete mockups da CORTE, nascidos de prompt; as seis da direção C (Mesa &
Ferro fiel) saíram em 16/09/2026 junto com ela."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

PASTA = Path(settings.BASE_DIR) / "docs" / "briefs" / "design" / "referencias" / "claude-design"
ESPERADAS = ("entrar-ferro", "hoje-ferro", "hidratacao-ferro", "ficha-ferro", "execucao-ferro", "progresso-ferro", "recompensa-ferro")
TETO = 250 * 1024


class ReferenciasTests(SimpleTestCase):
    def test_as_sete_existem_e_cabem(self):
        for nome in ESPERADAS:
            arquivo = PASTA / (nome + ".png")
            with self.subTest(nome=nome):
                self.assertTrue(arquivo.is_file(), arquivo)
                self.assertLessEqual(arquivo.stat().st_size, TETO, f"{nome}: {arquivo.stat().st_size} bytes")

    def test_nada_alem_das_sete_na_pasta(self):
        """A pasta é fechada: um oitavo PNG entra pelo mesmo caminho e pelo
        mesmo teto, e não como sobra de uma captura esquecida."""
        extras = sorted(p.name for p in PASTA.iterdir() if p.name not in {n + ".png" for n in ESPERADAS})
        self.assertEqual(extras, [], f"arquivos fora da lista: {extras}")


class DirecoesTests(SimpleTestCase):
    """As três direções lado a lado em `DIRECAO-ESCOLHIDA.md` (Home, execução
    e recompensa de cada, escuro): nove PNGs recortados e quantizados, cada
    um abaixo do mesmo teto de 250 KB — o comparativo inteiro fica fora do
    git (`scratchpad/shots-design/direcoes.html`)."""

    PASTA = Path(settings.BASE_DIR) / "docs" / "briefs" / "design" / "referencias" / "direcoes"
    ESPERADAS = tuple(f"d{d}-{tela}-escuro" for d in (1, 2, 3) for tela in ("hoje", "execucao", "recompensa"))

    def test_as_nove_existem_e_cabem(self):
        for nome in self.ESPERADAS:
            arquivo = self.PASTA / (nome + ".png")
            with self.subTest(nome=nome):
                self.assertTrue(arquivo.is_file(), arquivo)
                self.assertLessEqual(arquivo.stat().st_size, TETO, f"{nome}: {arquivo.stat().st_size} bytes")

    def test_o_documento_da_escolha_aponta_para_elas(self):
        doc = (Path(settings.BASE_DIR) / "docs" / "briefs" / "design" / "DIRECAO-ESCOLHIDA.md").read_text(encoding="utf-8")
        for nome in self.ESPERADAS:
            with self.subTest(nome=nome):
                self.assertIn(f"referencias/direcoes/{nome}.png", doc)
        self.assertIn("Direção escolhida:", doc)
