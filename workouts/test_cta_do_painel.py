# -*- coding: utf-8 -*-
"""O CTA do painel de treino renderiza numa linha só (24/09/2026).

Medido em produção, 390×844 e 1280×900, nos dois temas: o botão principal
do painel (`/treino/`) quebrava em CINCO linhas quando havia série hoje —

    CONTINUAR TREINO (
    1
    DE
    7
    )

— e o `)` caía fora do `clip-path` inclinado do botão primário. Duas
causas juntas: `.btn` é `inline-flex`, e cada trecho de texto solto entre
os `<span class="num">` do rótulo virava um item de flex PRÓPRIO (cinco no
total — "Continuar treino (", o primeiro número, " de ", o segundo número,
")"); e `.btn--hoje` ainda declarava `flex-direction: column`, sobra do
desenho antigo em que o botão tinha um "eco" com o nome do exercício
embaixo — removido em 22/09/2026, quando a ficha virou lista.

Este arquivo prende as duas pontas: o MARKUP (o rótulo inteiro é UM filho
de primeiro nível dentro do `<a data-hoje-cta>`, então não sobra item para
o flexbox empilhar) e a REGRA DE CSS (`.btn--hoje` não volta a declarar
`column`). A âncora é o marcador `data-hoje-cta`, nunca o texto do botão —
o CSS o escreve em caixa alta.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user


class FilhosDePrimeiroNivel(HTMLParser):
    """Conta os elementos filhos DIRETOS de um trecho de HTML.

    Texto solto não conta — o que importa aqui é quantos ITENS o flexbox
    do `.btn` enxerga, e um item de flex é sempre um elemento (texto entre
    elementos vira item também, mas span único por dentro do `<a>` não
    deixa texto solto no nível de fora).
    """

    def __init__(self):
        super().__init__()
        self.profundidade = 0
        self.filhos = []

    def handle_starttag(self, tag, attrs):
        if self.profundidade == 0:
            self.filhos.append(tag)
        self.profundidade += 1

    def handle_startendtag(self, tag, attrs):
        # Tag autofechada (ex.: <br/>) — não aparece no rótulo de hoje, mas
        # a contagem tem de ficar certa se um dia aparecer.
        if self.profundidade == 0:
            self.filhos.append(tag)

    def handle_endtag(self, tag):
        if self.profundidade > 0:
            self.profundidade -= 1


def _html_do_cta(html):
    """O conteúdo do `<a data-hoje-cta>`, sem o resto da página."""
    casa = re.search(r"<a\b[^>]*\bdata-hoje-cta\b[^>]*>(.*?)</a>", html, re.S)
    assert casa is not None, "o painel não tem o <a data-hoje-cta>"
    return casa.group(1)


def _filhos_do_cta(html):
    parser = FilhosDePrimeiroNivel()
    parser.feed(_html_do_cta(html))
    return parser.filhos


class OCTADoPainelTemUmFilhoTests(TestCase):
    """O rótulo do CTA vira UM item de flex, com ou sem série hoje."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)
        self.url = reverse("workouts:routine")

    def test_sem_serie_hoje_o_cta_tem_um_filho(self):
        """"Começar treino" — texto simples, mas ainda assim dentro de UM
        elemento, para nenhuma direção de flex voltar a quebrá-lo."""
        response = self.client.get(self.url)

        self.assertContains(response, "data-hoje-cta")
        filhos = _filhos_do_cta(response.content.decode())

        self.assertEqual(
            len(filhos), 1,
            "o <a data-hoje-cta> tem %d filhos de primeiro nível; era para ter 1" % len(filhos),
        )

    def test_com_serie_hoje_o_cta_continua_com_um_filho(self):
        """"Continuar treino (1 de N)": os `<span class="num">` ficam DENTRO
        do filho único — irmãos dele é que quebravam a linha."""
        plano, _ = services.sync_active_routine(self.user)
        sessao = services.sessao_do_dia(plano, timezone.localdate())
        item = sessao.exercises.select_related("exercise").order_by("order").first()
        ExerciseLog.objects.create(
            user=self.user, exercise=item.exercise, date=timezone.localdate(),
            set_number=1, weight_kg=40, reps=8,
        )

        response = self.client.get(self.url)
        interno = _html_do_cta(response.content.decode())
        filhos = _filhos_do_cta(response.content.decode())

        self.assertIn("Continuar treino", interno)
        self.assertIn('class="num"', interno)
        self.assertEqual(
            len(filhos), 1,
            "o <a data-hoje-cta> tem %d filhos de primeiro nível; era para ter 1" % len(filhos),
        )


class ARegraDoBotaoDeHojeNaoTemColunaTests(SimpleTestCase):
    """A regra `.btn--hoje` do CSS real não pode voltar a empilhar.

    `flex-direction: column` era o que fazia cada item de flex (ver a
    classe acima) virar uma linha própria. Não depende de banco nem de
    navegador — lê o arquivo servido de verdade.
    """

    def test_btn_hoje_nao_declara_column(self):
        caminho = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
        css = caminho.read_text(encoding="utf-8")
        bloco = re.search(r"\.btn--hoje\s*\{([^}]*)\}", css)

        self.assertIsNotNone(bloco, "a regra .btn--hoje sumiu do app.css")
        self.assertNotIn("column", bloco.group(1))
