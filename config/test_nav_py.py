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

    def test_o_tema_sobrevive_entre_comandos_como_o_viewport(self):
        """Cada comando de `nav.py` é um processo novo, com uma conexão CDP
        nova: `Emulation.setEmulatedMedia` morre com ela. `tema` gravava só
        na conexão viva e nunca voltava depois de fechada — `tema escuro`
        seguido de `screenshot` capturava a tela CLARA em silêncio. A
        correção segue o padrão de `viewport`/`offline`: grava a escolha num
        arquivo por sessão e reaplica em todo `Sessao.__init__`."""
        fonte = NAV.read_text(encoding="utf-8")
        self.assertIn('"tema-" + self.nome + ".json"', fonte)
        self.assertIn("def _tema(self):", fonte)
