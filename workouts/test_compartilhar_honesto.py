"""A imagem de compartilhar não diz "concluído" com 4 de 16 séries.

UX P1-12 (14/09/2026): o cartão de compartilhar aparece assim que existe
UMA série registrada, e a imagem desenhava "Treino concluído" em cima de
qualquer número — 4 de 16 séries viravam um treino concluído no story de
alguém. O título da imagem passa a depender de `estado.concluido`: com
série pendente é "Treino em andamento"; o botão, antes de concluir, diz
"Compartilhar o que já fiz" (D8). E a frase do rodapé ganha o acento que
o resto do app tem ("Minha evolução").

O servidor escreve `data-concluido` no cartão do resumo — `card.js` desenha
só o que vem de `data-`, e é isso que garante que peso e carga não entram
na imagem por acidente. O teste lê o HTML servido e o `card.js`.
"""

import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from . import services
from .test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje

CARD_JS = Path(settings.BASE_DIR) / "static" / "js" / "card.js"
ROUTINE = Path(settings.BASE_DIR) / "templates" / "workouts" / "routine.html"


class OCartaoDizOQueAconteceuTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("compartilhar@exemplo.com")
        self.sessao = tornar_hoje(self.user, "A")
        self.client.force_login(self.user)

    def _anotar(self, tudo):
        for item in self.sessao.exercises.all():
            series = item.sets if tudo else 1
            for numero in range(1, series + 1):
                services.record_load(
                    self.user, item.exercise, Decimal("40"), set_number=numero, reps=10
                )
            if not tudo:
                break

    def _resumo(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()
        m = re.search(r'<section class="card resumo" data-resumo(.*?)</section>', html, re.S)
        self.assertIsNotNone(m, "o cartão do resumo aparece com série registrada")
        return m.group(1)

    def test_com_serie_pendente_o_botao_e_a_imagem_nao_dizem_concluido(self):
        self._anotar(tudo=False)
        resumo = self._resumo()
        self.assertNotIn("data-concluido", resumo)
        self.assertIn("Compartilhar o que já fiz", resumo)
        self.assertNotIn("Compartilhar treino<", resumo.replace("\n", "").replace(" ", ""))

    def test_com_tudo_registrado_o_botao_diz_compartilhar_treino(self):
        self._anotar(tudo=True)
        resumo = self._resumo()
        self.assertIn('data-concluido="1"', resumo)
        self.assertIn("Compartilhar treino", resumo)
        self.assertNotIn("Compartilhar o que já fiz", resumo)


class OCardJsLeOEstadoTests(SimpleTestCase):
    def test_o_titulo_da_imagem_depende_do_estado(self):
        js = CARD_JS.read_text(encoding="utf-8")
        m = re.search(r"function desenharTreino\(g, f, cor, d\) \{(.*?)\n  \}", js, re.S)
        self.assertIsNotNone(m)
        corpo = m.group(1)
        self.assertIn('d.concluido ? "Treino concluído" : "Treino em andamento"', corpo)

    def test_a_pagina_manda_o_estado_e_a_frase_com_acento(self):
        html = ROUTINE.read_text(encoding="utf-8")
        self.assertIn("concluido: alvo.dataset.concluido", html)
        self.assertIn('frase: "Minha evolução. Meu plano."', html)
        self.assertNotIn("evolucao", html)
