# -*- coding: utf-8 -*-
"""`nav.py` é a régua de QA de navegador deste repositório; o comando `tema`
é o que permite capturar o tema escuro sem mexer no sistema operacional.
O teste lê a fonte porque o módulo abre um Chrome ao ser usado."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

NAV = Path(settings.BASE_DIR) / "scripts" / "qa" / "nav.py"


class ComandoTemaTests(SimpleTestCase):
    def test_o_comando_esta_documentado_e_despachado(self):
        fonte = NAV.read_text(encoding="utf-8")
        self.assertIn("nav.py <sessao> tema claro|escuro", fonte)
        self.assertIn('elif cmd == "tema": out = s.tema(args[0])', fonte)
        self.assertIn("Emulation.setEmulatedMedia", fonte)
        self.assertIn('"prefers-color-scheme"', fonte)
