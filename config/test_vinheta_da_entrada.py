"""O rodapé da entrada lê a 4,5:1 sobre o ponto mais escuro da vinheta.

DESIGN P1-07 / CT-18 (14/09/2026): `.auth--entrada::before` fecha as bordas
com uma vinheta de preto a 55 % no ponto mais forte — abaixo da borda
inferior da tela, mas o rodapé ("Esqueci minha senha", "Criar agora", os
links legais) mora justamente na borda, onde o preto ainda pesa ~48 %. As
réguas de contraste medem o texto sobre `--bg` liso, e passavam; a tela
real não era lisa ali.

Este teste LÊ a vinheta do CSS — a porcentagem de preto, o centro e o raio
da elipse, o ponto em que ela some — e calcula o fundo REAL na borda
inferior: `--bg` misturado com preto na opacidade que a vinheta tem lá.
Sobre esse fundo, `--text-dim` (`.muted`) e `--text-mute` (links legais)
precisam de 4,5:1. Controle positivo: com a vinheta a 40 %, o teste
reprova (sabotagem registrada).
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from config.tests import REGIME_PAPEL, _contraste, _tokens

CSS = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
MINIMO = 4.5


def _misturar(cor_hex, preto_alpha):
    """`cor` coberta por preto com opacidade `alpha`, em hex."""
    cor_hex = cor_hex.lstrip("#")
    canais = [int(cor_hex[i:i + 2], 16) * (1 - preto_alpha) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in canais)


def vinheta(css):
    """(alpha máximo, centro y em %, raio y em %, ponto em que some em %)."""
    bloco = css.split(".auth--entrada::before {", 1)[1].split("}", 1)[0]
    m = re.search(
        r"radial-gradient\((\d+)% (\d+)% at 50% (\d+)%,\s*"
        r"color-mix\(in srgb, #000 (\d+)%, transparent\) 0%,\s*transparent (\d+)%\)",
        bloco,
    )
    assert m, "a vinheta inferior mudou de forma; reescreva o parser"
    _, raio_y, centro_y, preto, some = (int(x) for x in m.groups())
    return preto / 100, centro_y, raio_y, some / 100


def alpha_na_borda(css):
    preto, centro_y, raio_y, some = vinheta(css)
    # Distância da borda inferior (100 %) ao centro, em fração do raio.
    distancia = (centro_y - 100) / raio_y
    if distancia >= some:
        return 0.0
    return preto * (1 - distancia / some)


class ORodapeDaEntradaLeSobreAVinhetaTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")
        # CORTE (16/09/2026): o Ferro é a base e o preto da vinheta só AJUDA
        # o texto claro; o regime em que a vinheta pode derrubar o rodapé é
        # o Papel — texto escuro sobre osso escurecido —, e é ele que se mede.
        self.tokens = _tokens(self.css, REGIME_PAPEL)

    def test_o_texto_do_rodape_le_no_ponto_mais_escuro_da_tela(self):
        alpha = alpha_na_borda(self.css)
        fundo = _misturar(self.tokens["--bg"], alpha)
        for nome in ("--text-dim", "--text-mute"):
            with self.subTest(token=nome, alpha=round(alpha, 3), fundo=fundo):
                self.assertGreaterEqual(_contraste(self.tokens[nome], fundo), MINIMO)

    def test_a_vinheta_nao_passa_de_15_por_cento(self):
        """A proposta do brief era ≤ 15 %; a 15 % os links legais ficam em
        4,39:1 e o teste de cima reprova — 12 % é o maior valor que passa.
        Este limite guarda a intenção (vinheta discreta) mesmo que os tokens
        de texto mudem e o cálculo acima passe a folgar."""
        preto, *_ = vinheta(self.css)
        self.assertLessEqual(preto, 0.15)

    def test_controle_positivo_a_vinheta_antiga_reprovava(self):
        """55 % era o valor de 13/09; sobre ele, `--text-mute` não chegava a 4,5."""
        fundo = _misturar(self.tokens["--bg"], 0.55 * (1 - (8 / 90) / 0.70))
        self.assertLess(_contraste(self.tokens["--text-mute"], fundo), MINIMO)
