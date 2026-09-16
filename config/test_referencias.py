# -*- coding: utf-8 -*-
"""Imagem no repositório tem teto: as 14 MB de shots de 14/09 ficaram fora,
e estas seis só entram porque cabem (≤ 250 KB cada, spec §8). São os mockups
do Claude Design a 390 px — a referência visual da direção C, não a tela do
app — e não trazem dado de conta real: nasceram de prompt, não de captura."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

PASTA = Path(settings.BASE_DIR) / "docs" / "briefs" / "design" / "referencias" / "claude-design"
ESPERADAS = ("hoje-mesa", "treino-painel-mesa", "treino-ficha-mesa", "treino-execucao-ferro", "progresso-mesa", "entrada-mesa")
TETO = 250 * 1024


class ReferenciasTests(SimpleTestCase):
    def test_as_seis_existem_e_cabem(self):
        for nome in ESPERADAS:
            arquivo = PASTA / (nome + ".png")
            with self.subTest(nome=nome):
                self.assertTrue(arquivo.is_file(), arquivo)
                self.assertLessEqual(arquivo.stat().st_size, TETO, f"{nome}: {arquivo.stat().st_size} bytes")

    def test_nada_alem_das_seis_na_pasta(self):
        """A pasta é fechada: um sétimo PNG entra pelo mesmo caminho e pelo
        mesmo teto, e não como sobra de uma captura esquecida."""
        extras = sorted(p.name for p in PASTA.iterdir() if p.name not in {n + ".png" for n in ESPERADAS})
        self.assertEqual(extras, [], f"arquivos fora da lista: {extras}")
