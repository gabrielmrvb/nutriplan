"""Um verbo, um destino — e o destino de "Começar treino" MUDOU em 24/09/2026.

A regra que este arquivo guarda nunca foi "o botão vai para a ficha": é **um
rótulo, um destino, em toda tela**. A auditoria de UX (P1-11, 14/09) achou o
mesmo rótulo com dois destinos — o cartão AGORA da Home mandava para a
execução e o painel para a ficha —, e "Continuar de onde parou" no painel
apontando para a ficha, que não é continuar nada. Quem lê o botão não tem como
saber para onde vai. Isso continua proibido.

O DESTINO de "Começar treino" era a ficha por requisito do dono de 13/09/2026
("leva à ficha, nunca abre o primeiro vídeo"), e o mesmo dono o reverteu em
24/09 depois da rodada 2 de experiência: quem já decidiu pagava dois toques
toda vez, e o segundo era numa tela que ela não ia ler. A ficha continua a um
toque, em "Ver ficha do Treino X · N exercícios", logo abaixo.

A regra é por VERBO, e vale em toda tela:

    "Começar treino"            -> workouts:now     (execução, o próximo pendente)
    "Continuar treino (n de N)" -> workouts:now     (o mesmo lugar, e o número diz onde parou)
    "Continuar de onde parou"   -> workouts:now     (execução, na ficha)
    "Ver ficha"                 -> workouts:ficha   (preparação, escolher)

O painel continua com destino FIXO (`test_the_destination_stays_put_because_the_target_screen_walks`,
em `workouts/tests.py`): o que muda ali é só o verbo. E a linha do resumo do
dia na Home ("Hoje · treino") abre o painel, que é a porta da área — a ficha e
a execução ficam um toque adiante, com o verbo certo.
"""

import re
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Pilar, Profile

from . import services
from .test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje

TEMPLATES = Path(settings.BASE_DIR) / "templates"


def _links(html):
    """Pares (href, texto visível) de todo `<a>` da página."""
    pares = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.S):
        texto = re.sub(r"<[^>]+>", " ", m.group(2))
        pares.append((m.group(1), " ".join(texto.split())))
    return pares


class VerbosDoTreinoTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("verbos@exemplo.com")
        Profile.objects.filter(user=self.user).update(
            interesse_treino=True, prioridade=Pilar.TREINO
        )
        self.sessao = tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.ficha = reverse("workouts:ficha", args=[self.sessao.pk])
        self.execucao = reverse("workouts:now")

    def _anotar_uma_serie(self):
        item = self.sessao.exercises.first()
        services.record_load(self.user, item.exercise, Decimal("40"), set_number=1, reps=10)

    def _home(self):
        # 19h30, sempre: o treino das 19h é o vencido mais recente e ganha o
        # cartão AGORA. Lendo a hora da máquina, depois do jantar a refeição
        # vencida passava na frente e a Home não oferecia "Começar treino" —
        # o `pre-push` de 14/09/2026 às 20h44 pegou. O que se prova aqui é o
        # DESTINO do verbo, não a escada do cartão (essa é de `plans/tests`).
        noite = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(19, 30))
        )
        with mock.patch("plans.views.relogio", return_value=noite):
            return self.client.get(reverse("plans:today")).content.decode()

    def _painel(self):
        return self.client.get(reverse("workouts:routine")).content.decode()

    def test_comecar_treino_tem_UM_destino_em_toda_porta(self):
        """A régua é UM RÓTULO, UM DESTINO — e desde 24/09/2026 o destino é a
        EXECUÇÃO. A Home continua com o verbo curto ("Começar") na célula do
        painel do dia; o que o teste cobra é que, onde o rótulo inteiro
        aparece, ele vá sempre para o mesmo lugar."""
        destinos = set()
        for nome, html in (("home", self._home()), ("painel", self._painel())):
            comecar = [href for href, texto in _links(html) if texto == "Começar treino"]
            destinos.update(comecar)
        self.assertTrue(destinos, "alguma tela tem de oferecer 'Começar treino' hoje")
        self.assertEqual(destinos, {self.execucao})

    def test_na_home_continuar_de_onde_parou_abre_a_execucao(self):
        self._anotar_uma_serie()
        links = _links(self._home())
        continuar = [href for href, texto in links if texto == "Continuar de onde parou"]
        self.assertEqual(continuar, [self.execucao])
        self.assertNotIn("Começar treino", [texto for _, texto in links])

    def test_no_painel_com_serie_anotada_o_verbo_muda_e_o_destino_fica(self):
        """O DESTINO FIXO continua sendo a regra: o que muda com a série
        anotada é só o verbo. Ele era "Abrir a ficha de hoje" → ficha, e
        virou "Continuar treino (n de N)" → execução em 24/09/2026 — o número
        é o que responde "de onde eu parei?" sem abrir nada."""
        self._anotar_uma_serie()
        links = _links(self._painel())
        continuar = [
            (href, texto) for href, texto in links if texto.startswith("Continuar treino")
        ]
        self.assertTrue(continuar, [t for _, t in links])
        self.assertEqual({href for href, _ in continuar}, {self.execucao})
        textos = [texto for _, texto in links]
        self.assertNotIn("Continuar de onde parou", textos)
        self.assertNotIn("Começar treino", textos)

    def test_o_cartao_de_treino_da_home_abre_o_treino(self):
        """A porta do treino na Home era uma coluna da linha `.resumo-dia`, de
        11px; desde 22/09/2026 é o cartão de Treino do painel do dia, que traz
        o fato (séries feitas de previstas, ou "Descanso") e o botão.

        O destino é o da SESSÃO de hoje quando há treino — a ficha — e a
        semana quando não há. As duas começam por `/treino/`, e é isso que
        este teste cobra: a porta existe e leva ao treino.
        """
        html = self._home()
        cartao = None
        for bloco in html.split('class="painel__cartao')[1:]:
            corpo = bloco.split("</section>", 1)[0]
            if "Treino" in corpo.split("</h3>", 1)[0]:
                cartao = corpo
        self.assertIsNotNone(cartao, "o cartão de Treino sumiu do painel")
        m = re.search(r'<a class="btn[^"]*" href="([^"]*)"', cartao)
        self.assertIsNotNone(m, cartao)
        self.assertTrue(
            m.group(1).startswith(reverse("workouts:routine")), m.group(1)
        )

    def test_na_leitura_o_verbo_e_fazer_este_exercicio(self):
        item = self.sessao.exercises.first()
        html = self.client.get(
            reverse("workouts:exercicio", args=[item.exercise_id])
        ).content.decode()
        alvo = "%s?exercicio=%d" % (self.execucao, item.exercise_id)
        self.assertIn((alvo, "Fazer este exercício"), _links(html))

    def test_ver_o_treino_completo_tem_um_destino_so(self):
        """As duas ocorrências do rótulo na execução apontam para a ficha DESTA sessão."""
        for item in self.sessao.exercises.all():
            for numero in range(1, item.sets + 1):
                services.record_load(
                    self.user, item.exercise, Decimal("40"), set_number=numero, reps=10
                )
        html = self.client.get(self.execucao).content.decode()
        destinos = {href for href, texto in _links(html) if texto == "Ver o treino completo"}
        self.assertEqual(destinos, {self.ficha})


class UmVerboUmDestinoNosTemplatesTests(TestCase):
    """Guarda textual: o rótulo nunca volta a aparecer com o destino errado."""

    def _ocorrencias(self, rotulo):
        achados = []
        for caminho in TEMPLATES.rglob("*.html"):
            texto = caminho.read_text(encoding="utf-8")
            for m in re.finditer(r"<a\b[^>]*>(?:(?!</a>).)*?" + re.escape(rotulo), texto, re.S):
                achados.append((caminho.relative_to(TEMPLATES).as_posix(), m.group(0)))
        return achados

    #: "COMEÇAR TREINO" PASSOU A VALER NAS DUAS TELAS (pedido do dono,
    #: 22/09/2026), e o destino é o que cada uma pode oferecer: do painel,
    #: a FICHA (onde se prepara); da ficha, a EXECUÇÃO (onde se começa de
    #: verdade). Antes eram dois rótulos para o mesmo ato — "Começar
    #: treino" no painel e "Começar pelo primeiro" na ficha —, e era isso
    #: que confundia. A régua continua existindo e continua estrita: o
    #: rótulo não pode aparecer em NENHUM outro arquivo, nem apontar para
    #: um terceiro destino.
    DESTINO_DE_COMECAR = {
        # O painel passou de `ficha` para `now` em 24/09/2026 (decisão do
        # dono, rodada 2): um clique para treinar. A ficha continua logo
        # abaixo, com o próprio rótulo.
        "workouts/routine.html": "workouts:now",
        "workouts/ficha.html": "workouts:now",
    }
    #: A HOME SAIU DESTE MAPA EM 22/09/2026, e não por descuido.
    #:
    #: O rótulo vivia em `plans/_area_promovida.html`, o cartão de meia tela
    #: da área principal. Aquele cartão virou uma CÉLULA do painel do dia
    #: (~162px a 390px), e ali o botão diz só "Começar": o `<h3>` da célula já
    #: diz "Treino" a dois centímetros de distância, e "Começar treino" numa
    #: coluna de 162px quebra em duas linhas para repetir a palavra que está
    #: logo acima.
    #:
    #: O que a régua protege continua protegido: o DESTINO é o mesmo dos
    #: outros dois ("a ficha de hoje"), e quem cobra isso é
    #: `plans.test_home_adaptativa.AAreaPrincipalSobeTests.
    #: test_cada_cartao_leva_a_porta_da_sua_area`. O que este mapa proíbe —
    #: o rótulo inteiro aparecendo num terceiro arquivo, ou apontando para um
    #: terceiro destino — não mudou.

    def test_comecar_treino_so_com_workouts_ficha(self):
        achados = self._ocorrencias("Começar treino")
        self.assertTrue(achados)  # controle positivo: o rótulo existe
        for arquivo, trecho in achados:
            with self.subTest(arquivo=arquivo):
                esperado = self.DESTINO_DE_COMECAR.get(arquivo)
                self.assertIsNotNone(esperado, "rótulo em arquivo não previsto: %s" % arquivo)
                self.assertIn(esperado, trecho)
                outro = "workouts:now" if esperado == "workouts:ficha" else "workouts:ficha"
                self.assertNotIn(outro, trecho)
        # As DUAS telas têm o rótulo: sem isto, apagar o do painel deixaria
        # o teste verde e o caminho de novo com dois nomes. (A Home tem a
        # porta, com o verbo curto — ver o comentário de `DESTINO_DE_COMECAR`.)
        self.assertEqual(
            {arquivo for arquivo, _ in achados}, set(self.DESTINO_DE_COMECAR)
        )

    def test_continuar_de_onde_parou_so_com_workouts_now(self):
        achados = self._ocorrencias("Continuar de onde parou")
        self.assertTrue(achados)
        for arquivo, trecho in achados:
            with self.subTest(arquivo=arquivo):
                self.assertIn("workouts:now", trecho)
                self.assertNotIn("workouts:ficha", trecho)
