# -*- coding: utf-8 -*-
"""`scripts/qa/nav.py` sobe o PRIMEIRO Chrome que o sistema deixa rodar.

Em 20/09/2026 o Smart App Control do Windows passou a bloquear também o
`chrome.exe` que o agent-browser baixou (`WinError 4551` no `spawn`), e o
QA de navegador inteiro morreu no `Popen` — com o Google Chrome instalado
(assinado, mesmo motor) subindo headless normalmente ao lado. A lista de
candidatos e a queda para o próximo em `OSError` são o que estes testes
prendem; o arquivo é lido como MÓDULO (é um CLI, mas importável).
"""
import importlib.util
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

NAV = Path(__file__).resolve().parent.parent / "scripts" / "qa" / "nav.py"


def _carregar():
    spec = importlib.util.spec_from_file_location("nav_qa", NAV)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class OChromeQueSobeTests(SimpleTestCase):
    def setUp(self):
        self.nav = _carregar()

    def test_os_candidatos_vao_do_agent_browser_ao_chrome_instalado_e_ao_edge(self):
        nomes = [str(c).lower() for c in self.nav.CANDIDATOS]
        self.assertIn(".agent-browser", nomes[0])
        self.assertTrue(any("google" in n and n.endswith("chrome.exe") for n in nomes))
        self.assertTrue(any(n.endswith("msedge.exe") for n in nomes))

    def test_bloqueado_no_spawn_cai_para_o_proximo_candidato(self):
        """O bloqueio do Smart App Control é um `OSError` no `Popen` — não um
        arquivo que falta. O segundo candidato tem de ser tentado."""
        tentados = []

        def popen(args, **kwargs):
            tentados.append(args[0])
            if len(tentados) == 1:
                raise OSError(4551, "Uma política de Controle de Aplicativo bloqueou este arquivo")
            return mock.Mock()

        with mock.patch.object(self.nav.subprocess, "Popen", side_effect=popen), \
             mock.patch.object(self.nav, "_vivo", return_value=True), \
             mock.patch.object(self.nav, "CANDIDATOS", [Path("C:/um/chrome.exe"), Path("C:/dois/chrome.exe")]), \
             mock.patch.object(Path, "exists", return_value=True):
            self.nav._abrir_chrome("teste", 9999)

        self.assertEqual([t.replace("\\", "/") for t in tentados], ["C:/um/chrome.exe", "C:/dois/chrome.exe"])

    def test_sem_nenhum_candidato_que_suba_a_mensagem_diz_o_que_tentou(self):
        with mock.patch.object(self.nav.subprocess, "Popen", side_effect=OSError(4551, "bloqueado")), \
             mock.patch.object(self.nav, "CANDIDATOS", [Path("C:/um/chrome.exe")]), \
             mock.patch.object(Path, "exists", return_value=True):
            with self.assertRaises(SystemExit) as cm:
                self.nav._abrir_chrome("teste", 9999)
        self.assertIn("chrome.exe", str(cm.exception))
        self.assertIn("Smart App Control", str(cm.exception))
