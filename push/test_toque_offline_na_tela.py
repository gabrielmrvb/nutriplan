"""O toque offline aparece na tela na hora — água, refeição e série.

UX P1-09 / E02 / E07 (14/09/2026): sem rede, `fila.js` guardava o pedido e
disparava `nutriplan:enfileirado`, e a tela só devolvia o botão. O número
da água não mudava, a série não entrava na pastilha, a refeição continuava
"pendente": parecia que não tinha funcionado, e a pessoa tocava de novo —
enfileirando duas vezes. Agora cada tela escreve o que o servidor
escreveria, com um selo "aguardando rede" que já existe no HTML,
escondido; a página recarregada mostra o que o servidor tem.

Como as outras asserções sobre JavaScript neste repositório, estas são
ESTRUTURAIS: sem Node, o comportamento foi provado no navegador com a rede
desligada pelo CDP (três toques → três pastilhas tracejadas, título de
"Série 2" a "Série 5", faixa da fila com 3; rede de volta → drenagem →
recarga com as três séries). O que elas impedem é a regra sumir do
arquivo sem ninguém notar.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)
PWA = BASE / "static" / "js" / "pwa.js"
FILA = BASE / "static" / "js" / "fila.js"
CSS = BASE / "static" / "css" / "app.css"
TEMPLATES = BASE / "templates"


def sem_comentarios(texto):
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", texto, flags=re.S)


class OToqueOfflineApareceNaTelaTests(SimpleTestCase):
    def setUp(self):
        self.pwa = sem_comentarios(PWA.read_text(encoding="utf-8"))

    def test_as_tres_telas_tem_a_nota_escondida(self):
        for arquivo in ("plans/_agua.html", "plans/today.html", "workouts/agora.html"):
            with self.subTest(arquivo=arquivo):
                html = sem_comentarios((TEMPLATES / arquivo).read_text(encoding="utf-8"))
                self.assertIn('data-aguardando-rede hidden', html)

    def test_o_pwa_reconhece_as_mesmas_rotas_da_fila(self):
        """As rotas que a fila aceita são as que a tela sabe responder — as
        mesmas três expressões, e não uma lista paralela que envelhece."""
        fila = sem_comentarios(FILA.read_text(encoding="utf-8"))
        rotas = re.search(r"var ROTAS = \[(.*?)\];", fila, re.S).group(1)
        for rota in ("/^\\/agua\\/$/", "/^\\/refeicao\\/\\d+\\/marcar\\/$/", "/^\\/treino\\/agora\\/serie\\/$/"):
            with self.subTest(rota=rota):
                self.assertIn(rota, rotas)
                self.assertIn(rota + ".test(acao)", self.pwa)

    def test_cada_tela_escreve_o_que_o_servidor_escreveria(self):
        self.assertIn("function aguaEnfileirada", self.pwa)
        self.assertIn("function refeicaoEnfileirada", self.pwa)
        self.assertIn("function serieEnfileirada", self.pwa)
        # A série entra na pastilha e o título avança; a água soma o número.
        self.assertIn('"series__item--feita", "series__item--pendente-rede"', self.pwa)
        self.assertIn('"Concluir série " + (n + 1)', self.pwa)
        self.assertIn("atual + ml", self.pwa)
        # Nada aqui grava: o único efeito é na tela.
        self.assertNotIn("fetch(", self.pwa.split("function aguaEnfileirada", 1)[1].split("nutriplan:enfileirado", 1)[0])

    def test_o_css_veste_o_selo_e_a_pastilha_pendente(self):
        css = sem_comentarios(CSS.read_text(encoding="utf-8"))
        self.assertRegex(css, r"\.aguardando-rede\s*\{")
        self.assertRegex(css, r"\.series__item--pendente-rede\s*\{[^}]*dashed")
