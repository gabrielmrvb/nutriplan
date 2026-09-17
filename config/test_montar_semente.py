"""A semente do Claude Design é montada por script para ser reproduzível —
o roteiro do dono aponta para pastas com nomes fixos."""
import importlib
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MontarSementeTests(SimpleTestCase):
    def test_monta_as_seis_pastas_e_a_nota(self):
        modulo = importlib.import_module("scripts.montar_semente")
        raiz = Path(settings.BASE_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "seed"
            contagem = modulo.montar(raiz, destino, telas=[])
            for pasta in ("codigo", "telas", "marca", "fonts", "capturas"):
                self.assertTrue((destino / pasta).is_dir(), pasta)
            self.assertTrue((destino / "DESIGN.md").is_file())
            self.assertEqual((destino / "nota.txt").read_text(encoding="utf-8"), modulo.NOTA)
            self.assertTrue((destino / "codigo" / "app.css").is_file())
            self.assertTrue((destino / "codigo" / "base.html").is_file())
            self.assertTrue((destino / "codigo" / "partials" / "field.html").is_file())
            self.assertTrue((destino / "marca" / "icon-192.png").is_file())
            self.assertTrue((destino / "marca" / "icones.svg").is_file())
            self.assertGreaterEqual(contagem["codigo"], 10)
            # NERVURA (17/09/2026): as fontes próprias vão junto — o CSS
            # embutido nas telas aponta para `../fonts/`.
            self.assertTrue((destino / "fonts" / "big-shoulders-display-latin.woff2").is_file())
            self.assertTrue((destino / "fonts" / "archivo-latin.woff2").is_file())
            self.assertGreaterEqual(contagem["fonts"], 4)
            self.assertIn("NERVURA", modulo.NOTA)

    def test_o_sprite_vira_svg_puro(self):
        modulo = importlib.import_module("scripts.montar_semente")
        svg = modulo.sprite_como_svg(Path(settings.BASE_DIR))
        self.assertTrue(svg.lstrip().startswith("<svg"))
        self.assertNotIn("{%", svg)
        self.assertNotIn("{#", svg)
        self.assertIn("<symbol", svg)
