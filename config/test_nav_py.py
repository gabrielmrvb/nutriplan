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
        arquivo por sessão e reaplica em todo `Sessao.__init__`.

        Apagar a chamada em `__init__` é exatamente reverter a correção, e as
        duas strings antigas continuariam no arquivo — por isso o teste
        deve âncora na presença de `self._tema()` DENTRO do `__init__`."""
        fonte = NAV.read_text(encoding="utf-8")
        self.assertIn('"tema-" + self.nome + ".json"', fonte)
        self.assertIn("def _tema(self):", fonte)

        # Slice do __init__ e verifica que _tema() é chamado ali
        linhas = fonte.split("\n")
        inicio = None
        fim = None
        for i, linha in enumerate(linhas):
            if linha.strip().startswith("def __init__(self, nome):"):
                inicio = i
            elif inicio is not None and linha.strip().startswith("def ") and "def __init__" not in linha:
                fim = i
                break

        self.assertIsNotNone(inicio, "def __init__ não encontrado")
        self.assertIsNotNone(fim, "próximo método após __init__ não encontrado")

        init_source = "\n".join(linhas[inicio:fim])
        self.assertIn("self._tema()", init_source,
                      "self._tema() não é chamado dentro de __init__ — a wiring foi quebrada")
