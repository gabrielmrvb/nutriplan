# -*- coding: utf-8 -*-
"""Cada série abre com um número que a pessoa já levantou — e com QUAL.

BENCHMARK-2026-09 (c): Hevy, Strong e Fitbod pré-preenchem cada série com a
MESMA série da última sessão. O NutriPlan faz isso na abertura da sessão, e
põe duas coisas na frente, por decisão escrita (`_sugestao_de_carga`, 30/08
e T2.3): a última série de HOJE (ninguém troca de carga entre a 1ª e a 2ª de
propósito) e a sugestão da adaptação (frase == campo). A mais pesada do
último treino é o ÚLTIMO recurso, nunca o primeiro.

Este arquivo pina a ordem — carga e reps lado a lado — para que ninguém a
"corrija" para o comportamento literal do Hevy sem ler o motivo.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class AOrdemDoPrefillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="prefill@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS and i.sets >= 3
        )

    def _log(self, dias_atras, serie, peso, reps):
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(str(peso)), reps=reps,
        )

    def _campos(self):
        # A tag inteira primeiro, o `value="…"` depois, em qualquer ordem de
        # atributo — presa a `name=` antes de `value=` no template, a regex
        # quebra em silêncio se algum dia o `value` vier primeiro (revisão de
        # 16/09/2026, achado 3).
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        import re

        def _valor(nome):
            tag = re.search(r'<input\b[^>]*\bname="%s"[^>]*>' % nome, html)
            if not tag:
                return ""
            valor = re.search(r'\bvalue="([^"]*)"', tag.group(0))
            return valor.group(1) if valor else ""

        return _valor("weight_kg"), _valor("reps")

    def _pastilhas(self, html):
        """Uma entrada por `<li class="series__item…">`, na ordem das séries
        (1, 2, 3…) — para checar o número DENTRO da pastilha certa, e não em
        qualquer lugar da página (revisão de 16/09/2026, achado 2)."""
        import re
        return re.findall(r'<li class="series__item[^"]*">(.*?)</li>', html, re.S)

    def test_sem_historico_a_carga_abre_vazia_e_as_reps_no_piso(self):
        # Reps no piso da faixa desde 22/09/2026: vazias, a série era gravada
        # sem repetição por quem tocava "Concluir" sem digitar.
        carga, reps = self._campos()
        self.assertEqual(carga, "")
        self.assertEqual(reps, str(self.item.rep_min))

    def test_na_abertura_a_serie_1_vem_da_mesma_serie_da_ultima_sessao_quando_nao_ha_sugestao(self):
        # Uma série só na última sessão: sem faixa fechada em todas, a
        # adaptação não sugere, e o que sobra é a mesma série da última vez.
        # `floatformat:'-2'` mantém as duas casas quando há fração — "57,50",
        # não "57,5" (conferido em `test_pastilha.py::…cita_o_mesmo_numero`).
        self._log(7, 1, 57.5, 9)
        self.assertEqual(self._campos(), ("57,50", "9"))

    def test_a_mesma_serie_da_ultima_sessao_vence_a_mais_pesada(self):
        self._log(7, 1, 50, 10)
        self._log(7, 2, 60, 8)   # a mais pesada foi a 2ª
        self.assertEqual(self._campos()[0], "50")  # série 1 abre com a série 1

    def test_a_serie_anterior_de_hoje_vence_tudo(self):
        self._log(7, 1, 60, 10)
        self._log(7, 2, 55, 10)
        self._log(0, 1, 62.5, 8)  # hoje a pessoa subiu
        self.assertEqual(self._campos(), ("62,50", "8"))  # a 2ª abre com a 1ª de hoje, não com 55

    def test_a_sugestao_da_adaptacao_vence_a_mesma_serie_da_ultima_sessao(self):
        # A faixa fechou na última sessão (todas as séries no rep_max, mesma
        # carga): `proxima_carga` devolve SUBIR, e é essa sugestão — não o
        # número puro da série 1 da última vez — quem abre o campo. Sem um
        # teste fechando a faixa em TODAS as séries, `item.progressao` nunca
        # sai de `None` e este degrau nunca é exercitado (revisão de
        # 16/09/2026, achado 1).
        for serie in range(1, self.item.sets + 1):
            self._log(3, serie, 60, self.item.rep_max)
        esperado = Decimal("60") + (
            Decimal("5") if self.item.exercise.muscle_group in services.GRUPOS_INFERIORES
            else Decimal("2.5")
        )
        carga, _ = self._campos()
        self.assertGreater(Decimal(carga.replace(",", ".")), Decimal("60"))
        self.assertEqual(Decimal(carga.replace(",", ".")), esperado)

    def test_com_serie_de_hoje_a_sugestao_some_e_hoje_manda(self):
        # A faixa fechou — sem a série de hoje, `ajuste` devolveria SUBIR — e
        # ainda assim o campo abre com o número de hoje. Não é só a ORDEM
        # dos degraus que resolve isso: a guarda de topo de `ajuste`
        # (`workouts/adaptacao.py`, "if (...).get('hoje'): return None`)
        # desliga a sugestão inteira quando há série anotada hoje, e
        # `estado.atual.progressao` fica `None` — não existe sugestão para
        # perder de nenhuma corrida. `_sugestao_de_carga` documenta a
        # decisão por extenso: "Hoje continua mandando — `ajuste` devolve
        # `None` com série anotada hoje" (revisão de 16/09/2026, achado 1 /
        # rodada 2 — o teste anterior pinava a ORDEM com uma sugestão que já
        # não existia no momento do assert).
        for serie in range(1, self.item.sets + 1):
            self._log(3, serie, 60, self.item.rep_max)
        self._log(0, 1, 61, 9)  # hoje, série 1: não seguiu a sugestão de subir

        estado = services.estado_do_treino(self.pessoa, escolhido=self.item.exercise_id)
        atual = estado.atual

        self.assertIsNone(atual.progressao)  # o discriminador: a guarda apagou a sugestão
        self.assertEqual(atual.sugestao_carga, Decimal("61"))
        self.assertEqual(atual.sugestao_reps, 9)
        # E a tela mostra o mesmo par — o campo é o retrato do que o serviço decidiu.
        self.assertEqual(self._campos(), ("61", "9"))

    def test_a_pastilha_pendente_mostra_a_mesma_serie_da_ultima_sessao(self):
        self._log(7, 1, 60, 10)
        self._log(7, 2, 55, 8)
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        itens = self._pastilhas(html)
        self.assertIn("60", itens[0])       # pastilha da série 1: a série 1 da última vez
        self.assertIn("55", itens[1])       # pastilha da série 2: a série 2 da última vez
        self.assertNotIn("55", itens[0])    # não a de outra série
        self.assertNotIn("60", itens[1])
