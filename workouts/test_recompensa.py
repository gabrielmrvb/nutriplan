# -*- coding: utf-8 -*-
"""A folha de recompensa da última série (CORTE, T3.6 — 16/09/2026).

O placar (`services.Placar`) é CONTAGEM sobre o que a tela já carregou —
carga total de hoje (peso × repetições, série a série), a mesma conta
sobre a última vez de cada exercício ("vs. última") e quantos exercícios
bateram a carga mais alta de qualquer data anterior —, sem consulta nova.
A tela do treino fechado nasce dentro da folha-lima: o número conta do
zero (`data-conta="zero"`), os números pequenos entram em cascata
(`data-escalonado` + `--mov-cascata`), os dois botões do contrato estão lá
("Ver o treino completo" primário — o verbo do repositório para a ficha —,
"Voltar para Hoje" contorno) e o
`prefers-reduced-motion` desliga a folha, o número e os botões.
"""
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import formats, timezone

from workouts import services
from workouts.tests import create_user, sem_scripts

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
JS = Path(settings.BASE_DIR) / "static" / "js" / "pwa.js"


def _log(peso, reps):
    return SimpleNamespace(weight_kg=None if peso is None else Decimal(peso), reps=reps)


def _item(hoje=(), anterior=(), melhor_hoje=None, recorde_anterior=None):
    return SimpleNamespace(load={
        "hoje": {i + 1: _log(*s) for i, s in enumerate(hoje)},
        "anterior": {i + 1: _log(*s) for i, s in enumerate(anterior)},
        "melhor_hoje": None if melhor_hoje is None else Decimal(melhor_hoje),
        "recorde_anterior": None if recorde_anterior is None else Decimal(recorde_anterior),
    })


class OPlacarEContagemTests(SimpleTestCase):
    def test_a_carga_total_e_peso_vezes_repeticoes_serie_a_serie(self):
        placar = services.placar_do_treino([
            _item(hoje=[("40", 10), ("40", 10), ("45", 8)]),
            _item(hoje=[("20", 12)]),
        ])
        self.assertEqual(placar.carga_total, Decimal("1400"))

    def test_peso_do_corpo_soma_zero_e_nao_some(self):
        placar = services.placar_do_treino([_item(hoje=[(None, 15), (None, 12)]), _item(hoje=[("30", 10)])])
        self.assertEqual(placar.carga_total, Decimal("300"))

    def test_vs_ultima_compara_com_a_ultima_vez_de_cada_exercicio(self):
        placar = services.placar_do_treino([
            _item(hoje=[("50", 10)], anterior=[("40", 10)]),
            _item(hoje=[("20", 10)], anterior=[("20", 10)]),
        ])
        self.assertEqual(placar.carga_anterior, Decimal("600"))
        self.assertEqual(placar.delta_pct, 17)

    def test_sem_passado_nao_ha_comparacao(self):
        placar = services.placar_do_treino([_item(hoje=[("50", 10)])])
        self.assertIsNone(placar.carga_anterior)
        self.assertIsNone(placar.delta_pct)

    def test_recorde_e_a_serie_mais_pesada_de_hoje_acima_de_qualquer_data(self):
        placar = services.placar_do_treino([
            _item(hoje=[("52.5", 8)], melhor_hoje="52.5", recorde_anterior="50"),
            _item(hoje=[("30", 10)], melhor_hoje="30", recorde_anterior="30"),
            _item(hoje=[("10", 10)], melhor_hoje="10", recorde_anterior=None),
        ])
        self.assertEqual(placar.recordes, 1)

    def test_item_sem_historico_carregado_nao_derruba(self):
        placar = services.placar_do_treino([SimpleNamespace()])
        self.assertEqual(placar.carga_total, Decimal("0"))


class ATelaDoTreinoFechadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="recompensa@exemplo.com", weekdays=(timezone.localdate().weekday(),))
        services.sync_active_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        estado = services.estado_do_treino(self.pessoa)
        self.itens = estado.itens
        for item in self.itens:
            for numero in range(1, item.sets + 1):
                services.record_load(self.pessoa, item.exercise, Decimal("40"), set_number=numero, reps=10)

    def test_o_placar_nasce_dentro_da_folha_com_os_dois_botoes_do_contrato(self):
        html = sem_scripts(self.client.get(reverse("workouts:now")).content.decode())
        folha = html.split('class="card fim recompensa"', 1)[1].split("</section>", 1)[0]
        esperado = sum(item.sets * 400 for item in self.itens)
        self.assertIn('data-conta="zero"', folha)
        # Com ponto de milhar (22/09/2026): "8008" na tela contra "8.008" no
        # cartão era o achado #16 das personas; o contador do pwa.js
        # preserva o formato que lê.
        agrupado = formats.number_format(esperado, decimal_pos=0, force_grouping=True)
        self.assertIn(">%s<" % agrupado, folha.replace(" ", "").replace("\n", ""))
        self.assertIn("kg levantados", folha)
        self.assertIn('data-escalonado', folha)
        self.assertIn("Ver o treino completo", folha)
        self.assertIn("Voltar para Hoje", folha)
        self.assertIn(reverse("plans:today"), folha)
        self.assertNotIn("kcal", folha)

    def test_o_estado_leva_o_placar_so_quando_concluido(self):
        estado = services.estado_do_treino(self.pessoa)
        self.assertTrue(estado.concluido)
        self.assertEqual(estado.placar.carga_total, Decimal(sum(item.sets * 400 for item in self.itens)))
        self.assertIsNone(estado.placar.carga_anterior, "primeira vez: sem 'vs. última'")

    def test_o_placar_nao_e_calculado_no_meio_do_treino(self):
        outra = create_user(email="meio@exemplo.com", weekdays=(timezone.localdate().weekday(),))
        services.sync_active_routine(outra)
        estado = services.estado_do_treino(outra)
        self.assertFalse(estado.concluido)
        self.assertIsNone(estado.placar)


class OMovimentoDaRecompensaTests(SimpleTestCase):
    def setUp(self):
        self.css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
        self.js = JS.read_text(encoding="utf-8")

    def test_os_tres_momentos_tem_keyframe_e_consumidor(self):
        """NERVURA (17/09/2026): a régua que ACENDE é o mesmo gesto nos três
        momentos — a linha da refeição registrada, o bloco da meta batida e
        o placar; o número cresce uma vez ao bater meta."""
        for nome, consumidor in (("nervura-acende", ".meal.is-recem::after"), ("nervura-acende", ".agua-card.is-meta::after"),
                                 ("numero-cresce", ".agua-card.is-meta [data-agua-total]")):
            with self.subTest(keyframe=nome, consumidor=consumidor):
                self.assertIn("@keyframes %s" % nome, self.css)
                self.assertRegex(self.css, re.escape(consumidor) + r"[^{]*\{[^}]*animation:\s*" + re.escape(nome))
        self.assertNotIn("@keyframes corte-abre", self.css)
        self.assertNotIn("@keyframes corte-desdobra", self.css)

    def test_os_tempos_sao_tokens(self):
        raiz = self.css.split(":root {", 1)[1].split("\n}", 1)[0]
        self.assertIn("--mov-nervura: .6s;", raiz)
        self.assertIn("--mov-cascata: .08s;", raiz)
        self.assertNotIn("--corte-aberto", raiz)
        regra = re.search(r"\.recompensa\s*\{([^}]*)\}", self.css).group(1)
        self.assertIn("border-radius: var(--quina-g)", regra)
        # A nervura que risca o placar é o ::before (NERVURA 3/3), e é ela
        # que leva o tempo; o bloco em si não se move.
        nervura = re.search(r"\.recompensa::before\s*\{([^}]*)\}", self.css).group(1)
        self.assertRegex(nervura, r"animation:\s*nervura-risca var\(--mov-nervura\)")
        self.assertIn("@keyframes nervura-risca", self.css)

    def test_menos_movimento_desliga_a_folha_o_numero_e_os_botoes(self):
        # Há mais de um bloco de menos-movimento no arquivo; o que importa é
        # que ALGUM deles desligue cada seletor.
        reduzido = "".join(self.css.split("@media (prefers-reduced-motion: reduce)")[1:])
        for sel in (".recompensa::before", ".recompensa .btn", ".meal.is-recem::after", ".agua-card.is-meta::after"):
            with self.subTest(seletor=sel):
                self.assertIn(sel, reduzido)

    def test_o_numero_conta_do_zero_e_a_meta_da_agua_desdobra(self):
        self.assertIn('getAttribute("data-conta") === "zero"', self.js)
        self.assertIn('classList.add("is-meta")', self.js)
        self.assertIn("de.valor < meta && ate.valor >= meta", self.js)

    def test_a_agua_da_home_diz_a_meta_no_markup(self):
        agua = (Path(settings.BASE_DIR) / "templates" / "plans" / "_agua.html").read_text(encoding="utf-8")
        self.assertIn('data-agua-meta="{{ hidratacao_ml }}"', agua)


class OPlacarDoPesoDoCorpoTests(SimpleTestCase):
    """"0 kg levantados" em 72 px para quem fez o treino inteiro com o peso
    do corpo — e "0 KG LEVANTADOS" em laranja no cartão de compartilhar
    (achado #5 das personas, 21/09/2026). O placar passa a contar as
    REPETIÇÕES, e quando não há carga nenhuma no dia elas são o herói."""

    def test_o_placar_conta_as_repeticoes(self):
        placar = services.placar_do_treino([_item(hoje=[(None, 15), (None, 12)]), _item(hoje=[("30", 10)])])
        self.assertEqual(placar.repeticoes, 37)
        self.assertTrue(placar.tem_carga)

    def test_sem_carga_o_heroi_e_a_repeticao(self):
        placar = services.placar_do_treino([_item(hoje=[(None, 15), (None, 12)])])
        self.assertFalse(placar.tem_carga)
        self.assertEqual(placar.heroi, (27, "repetições feitas"))

    def test_com_carga_o_heroi_continua_sendo_o_kg(self):
        placar = services.placar_do_treino([_item(hoje=[("30", 10)])])
        self.assertEqual(placar.heroi, (Decimal("300"), "kg levantados"))

    def test_a_folha_e_o_cartao_usam_o_heroi(self):
        html = (Path(settings.BASE_DIR) / "templates" / "workouts" / "agora.html").read_text(encoding="utf-8")
        self.assertIn("placar.heroi.0", html)
        self.assertIn("placar.heroi.1", html)
        self.assertIn("data-compartilhar-heroi", html)
        self.assertIn("data-compartilhar-heroi-rotulo", html)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("compartilharHeroiRotulo", js)
        self.assertNotIn('g.fillText("KG LEVANTADOS"', js)


class APrimeiraSerieJaVemComAsRepsTests(TestCase):
    """A primeira série de um exercício sem histórico abria com o campo de
    repetições VAZIO (só o placeholder "6-10"): quem tocava "Concluir" sem
    digitar gravava a série sem repetição nenhuma — e o placar do treino de
    peso do corpo fechava em "0 repetições feitas" (QA de 22/09/2026). O
    campo abre no PISO da faixa, a mesma regra da carga nova; a pessoa
    ajusta se fez mais."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_sem_historico_o_campo_abre_no_piso_da_faixa(self):
        pessoa = create_user(email="piso@exemplo.com", weekdays=(timezone.localdate().weekday(),))
        services.sync_active_routine(pessoa)
        self.client.force_login(pessoa)
        estado = services.estado_do_treino(pessoa)
        primeiro = estado.itens[0]
        html = sem_scripts(self.client.get(reverse("workouts:now")).content.decode())
        campo = html.split('name="reps"', 1)[1].split(">", 1)[0]
        self.assertIn('value="%d"' % primeiro.rep_min, campo)

    def test_sem_repeticao_e_sem_carga_o_heroi_sao_as_series(self):
        placar = services.placar_do_treino([_item(hoje=[(None, None), (None, 0)])])
        self.assertEqual(placar.heroi, (2, "séries feitas"))
