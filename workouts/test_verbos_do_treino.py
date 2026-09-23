"""Um verbo, um destino: "Começar treino" abre a FICHA; "Continuar de onde parou" abre a EXECUÇÃO.

Requisito fechado do dono (13/09/2026): "Começar treino" leva à ficha, nunca
abre o primeiro vídeo. A auditoria de UX (P1-11, 14/09) achou o mesmo rótulo
com dois destinos — o cartão AGORA da Home mandava para a execução e o painel
para a ficha — e "Continuar de onde parou" no painel apontando para a ficha,
que não é continuar nada. Quem lê o botão não tem como saber para onde vai.

A regra é por VERBO, e vale em toda tela:

    "Começar treino"            -> workouts:ficha   (preparação, escolher)
    "Continuar de onde parou"   -> workouts:now     (execução, o próximo pendente)
    "Abrir a ficha de hoje"     -> workouts:ficha   (painel com série já anotada)

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

    def test_comecar_treino_abre_a_ficha_em_toda_porta(self):
        for nome, html in (("home", self._home()), ("painel", self._painel())):
            comecar = [href for href, texto in _links(html) if texto == "Começar treino"]
            with self.subTest(tela=nome):
                self.assertTrue(comecar, "a tela tem de oferecer 'Começar treino' hoje")
                self.assertEqual(set(comecar), {self.ficha})

    def test_na_home_continuar_de_onde_parou_abre_a_execucao(self):
        self._anotar_uma_serie()
        links = _links(self._home())
        continuar = [href for href, texto in links if texto == "Continuar de onde parou"]
        self.assertEqual(continuar, [self.execucao])
        self.assertNotIn("Começar treino", [texto for _, texto in links])

    def test_no_painel_com_serie_anotada_o_verbo_muda_e_o_destino_fica(self):
        self._anotar_uma_serie()
        links = _links(self._painel())
        self.assertIn((self.ficha, "Abrir a ficha de hoje"), links)
        textos = [texto for _, texto in links]
        self.assertNotIn("Continuar de onde parou", textos)
        self.assertNotIn("Começar treino", textos)

    def test_a_linha_do_resumo_do_dia_abre_o_painel(self):
        html = self._home()
        m = re.search(r'<a class="resumo-dia__treino" href="([^"]*)"', html)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), reverse("workouts:routine"))

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
        "workouts/routine.html": "workouts:ficha",
        # A Home também tem o rótulo, no cartão da área promovida, e o
        # destino dela é o mesmo do painel: a ficha.
        "plans/_area_promovida.html": "workouts:ficha",
        "workouts/ficha.html": "workouts:now",
    }

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
        # o teste verde e o caminho de novo com dois nomes.
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
