"""As três provas da landing pesam em WebP, com o PNG de reserva.

Medido pelas personas (21/09/2026): no 3G a landing levava 9,6 s para
terminar de carregar — os três PNG de ~90 KB (267 KB) eram quase tudo.
Em WebP a 90 de qualidade os mesmos quadros pesam ~24 KB cada (73 KB): o
`<picture>` serve o WebP a quem entende e o PNG a quem não. O comando
`capturas_landing` gera os dois de uma vez.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

PASTA = Path(settings.BASE_DIR) / "static" / "img" / "landing"
PROVAS = ("prova-dia", "prova-treino", "prova-progresso")


class ProvasEmWebpTests(TestCase):
    def test_cada_prova_tem_webp_leve_ao_lado_do_png(self):
        for nome in PROVAS:
            with self.subTest(nome=nome):
                webp = PASTA / ("%s.webp" % nome)
                self.assertTrue(webp.exists(), webp)
                self.assertLess(webp.stat().st_size, 40 * 1024, "%s pesa %d KB" % (nome, webp.stat().st_size // 1024))
                self.assertTrue((PASTA / ("%s.png" % nome)).exists())

    def test_a_landing_oferece_o_webp_com_o_png_de_reserva(self):
        html = self.client.get("/").content.decode()
        self.assertEqual(html.count("<picture"), 3)
        for nome in PROVAS:
            self.assertIn("img/landing/%s.webp" % nome, html)
            self.assertIn("img/landing/%s.png" % nome, html)
        self.assertEqual(html.count('type="image/webp"'), 3)
        self.assertEqual(html.count('loading="lazy"'), 3)
