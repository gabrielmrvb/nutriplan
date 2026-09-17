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

    def test_o_movimento_e_emulado_junto_com_o_tema(self):
        """O Chrome headless desta máquina responde `prefers-reduced-motion:
        reduce` por padrão — toda captura de movimento saía com o quadro
        final pronto (T3.6, 16/09/2026). `movimento normal|reduzido` persiste
        como o tema, e as DUAS features vão na mesma chamada de
        `setEmulatedMedia`: ela escreve a lista inteira, e uma sozinha
        apagaria a outra."""
        fonte = NAV.read_text(encoding="utf-8")
        self.assertIn("nav.py <sessao> movimento normal|reduzido", fonte)
        self.assertIn('elif cmd == "movimento": out = s.movimento(args[0])', fonte)
        self.assertIn('"movimento-" + self.nome + ".json"', fonte)
        inicio = fonte.index("def _tema(self):")
        corpo = fonte[inicio:fonte.index("def ", inicio + 10)]
        self.assertIn('"prefers-reduced-motion"', corpo)
        self.assertIn('"prefers-color-scheme"', corpo)
        self.assertEqual(corpo.count("Emulation.setEmulatedMedia"), 1, "uma chamada, as duas features")

    def test_o_tema_espera_o_recalculo_antes_de_qualquer_comando(self):
        """Reaplicar a emulação não basta: o Chrome só refaz o estilo numa
        tarefa posterior. Medido em 16/09/2026 — `getComputedStyle(body).color`
        ainda era o de Mesa logo depois do `setEmulatedMedia` e virava Ferro
        34 ms depois; a captura nesse intervalo saía com texto claro sobre
        fundo escuro em `/treino/` e `/`, a 390 e a 1280. Dois
        `requestAnimationFrame` não bastaram; `_tema()` espera a cor do
        `body` MUDAR (ou um teto curto) antes de devolver a sessão."""
        fonte = NAV.read_text(encoding="utf-8")
        inicio = fonte.index("def _tema(self):")
        fim = fonte.index("def ", inicio + 10)
        corpo = fonte[inicio:fim]
        self.assertIn("Emulation.setEmulatedMedia", corpo)
        self.assertIn("getComputedStyle(document.body).color", corpo)
        self.assertIn("c !== c0", corpo, "a espera tem de ser por MUDANÇA, não por tempo fixo")
        self.assertLess(corpo.index("Emulation.setEmulatedMedia"), corpo.index("c !== c0"), "a espera vem DEPOIS de emular")
