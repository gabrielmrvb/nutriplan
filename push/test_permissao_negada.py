"""Permissão negada é um estado que a tela mostra — e não apaga 0,1 ms depois.

UX P1-05 (14/09/2026, observado com MutationObserver): com notificações
bloqueadas, "Ativar lembretes" escrevia "Permissão negada. Dá para liberar
nas configurações do navegador." e, em seguida, `render(registration, null)`
caía no ramo sem inscrição e sobrescrevia com a frase padrão. Botão e texto
voltavam ao estado inicial; o recurso ficava inalcançável sem diagnóstico.

O mesmo achado no GPS (E10): "Sem permissão de localização. A corrida não
pode ser registrada." dizia o que não dá, e não o que fazer; e sem
`geolocation` o script saía em silêncio, deixando um botão "Começar" que não
faz nada.

Os contratos moram nos arquivos de JavaScript e no template, e o teste os
lê lá — como `push/tests.py` faz com `sw.js`. Sabotagem que precisa ficar
vermelha: voltar `render(registration, next)` sem a guarda; tirar "nas
configurações do navegador" do GPS; voltar o `return` mudo sem geolocation.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)
PWA = BASE / "static" / "js" / "pwa.js"
CORRIDA = BASE / "static" / "js" / "corrida.js"


def sem_comentarios_js(texto):
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", texto)


class PermissaoNegadaNaoESobrescritaTests(SimpleTestCase):
    def setUp(self):
        self.pwa = sem_comentarios_js(PWA.read_text(encoding="utf-8"))

    def test_negar_a_permissao_devolve_um_estado_e_nao_null(self):
        self.assertIn("var NEGADA", self.pwa)
        m = re.search(r'permission !== "granted"\) \{(.*?)\}', self.pwa, re.S)
        self.assertIsNotNone(m)
        self.assertIn("return NEGADA", m.group(1))
        self.assertNotIn("return null", m.group(1))

    def test_o_clique_nao_renderiza_de_novo_quando_a_permissao_foi_negada(self):
        m = re.search(r"\.then\(function \(next\) \{(.*?)\n\s*\}\)", self.pwa, re.S)
        self.assertIsNotNone(m)
        corpo = m.group(1)
        self.assertLess(corpo.index("next === NEGADA"), corpo.index("render(registration, next)"))

    def test_quem_ja_negou_le_a_frase_certa_ao_abrir_a_tela(self):
        m = re.search(r"function render\(registration, subscription\) \{(.*?)\n  \}", self.pwa, re.S)
        self.assertIsNotNone(m)
        self.assertIn('Notification.permission === "denied"', m.group(1))
        self.assertIn("Permissão negada", m.group(1))


class GpsNegadoDizComoLiberarTests(SimpleTestCase):
    def setUp(self):
        self.js = sem_comentarios_js(CORRIDA.read_text(encoding="utf-8"))

    def test_a_frase_diz_o_que_fazer(self):
        m = re.search(r"function erroDoGps\(erro\) \{(.*?)\n  \}", self.js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("configurações do navegador", m.group(1))

    def test_sem_geolocation_o_botao_e_desabilitado_com_a_razao(self):
        m = re.search(r'if \(!\("geolocation" in navigator\)\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m, "o script saía mudo sem geolocation")
        self.assertIn("disabled = true", m.group(1))
        self.assertIn("textContent", m.group(1))
