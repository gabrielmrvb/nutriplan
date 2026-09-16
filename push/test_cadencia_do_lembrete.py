# -*- coding: utf-8 -*-
"""O lembrete acompanha a cadência do agendador — e chega ANTES da refeição.

Até 16/09/2026 `send_meal_reminders` estava escrito para rodar de 5 em 5
minutos (janela de 10, antecedência de 10): cada rodada olhava `(agora,
agora+10]`, e o aviso saía de 0 a 10 minutos antes. O cron do Render que
liga os lembretes (B7 da avaliação) roda de 15 em 15 — de 5 em 5 manteria o
banco do Neon acordado o dia inteiro e a cota gratuita (100 CU-h) acabaria
no meio do mês (`CLAUDE.md`, "Monitor externo"). Com a janela de 10 e a
cadência de 15, uma refeição em cada três ficaria SEM aviso: as janelas
`(T, T+10]` e `(T+15, T+25]` deixam `(T+10, T+15]` descoberto.

A propriedade que este módulo guarda: para QUALQUER minuto do dia e QUALQUER
fase do agendador, exatamente uma rodada vê a refeição, e ela acontece de 5 a
`REMINDER_LEAD_MINUTES` minutos antes — nunca depois. E o que o código diz é
o que o `render.yaml` agenda e o que a tela promete.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from push import services

RAIZ = Path(settings.BASE_DIR)


def _janela(now):
    """`(start, target)` como `due_slots` calcula — a mesma função, exposta."""
    return services.janela_do_lembrete(now)


def _ve(janela, minuto):
    start, target = janela
    if start < target:
        return start < minuto <= target
    return minuto > start or minuto <= target


class ACadenciaCobreTodoMinutoTests(SimpleTestCase):
    def test_a_janela_nao_e_menor_que_o_intervalo_do_agendador(self):
        self.assertGreaterEqual(
            services.REMINDER_WINDOW_MINUTES, services.CRON_INTERVALO_MINUTOS
        )

    def test_toda_refeicao_e_vista_uma_vez_e_de_5_a_20_minutos_antes(self):
        base = datetime(2026, 9, 16, 0, 0)
        intervalo = services.CRON_INTERVALO_MINUTOS
        for fase in range(intervalo):
            rodadas = [base + timedelta(minutes=m) for m in range(fase, 24 * 60, intervalo)]
            for m in range(24 * 60):
                refeicao = (base + timedelta(minutes=m)).time()
                viram = [t for t in rodadas if _ve(_janela(t), refeicao)]
                # O dia é circular: a rodada das 23:45 vê a refeição de 00:00
                # (janela cruza a meia-noite), e a antecedência é medida
                # módulo 24 h.
                self.assertEqual(len(viram), 1, (fase, m, viram))
                antecedencia = (m - (viram[0] - base).total_seconds() / 60) % (24 * 60)
                self.assertGreaterEqual(antecedencia, 5, (fase, m))
                self.assertLessEqual(antecedencia, services.REMINDER_LEAD_MINUTES, (fase, m))


class OAgendadorEATelaDizemOMesmoTests(SimpleTestCase):
    def test_o_render_yaml_agenda_a_mesma_cadencia(self):
        yaml = (RAIZ / "render.yaml").read_text(encoding="utf-8")
        casou = re.search(r'schedule:\s*"([^"]+)"', yaml)
        self.assertIsNotNone(casou, "o bloco do cron sumiu do render.yaml")
        self.assertTrue(
            casou.group(1).startswith("*/%d " % services.CRON_INTERVALO_MINUTOS),
            casou.group(1),
        )

    def test_a_tela_promete_a_antecedencia_que_o_codigo_entrega(self):
        promessa = "até %d minutos antes" % services.REMINDER_LEAD_MINUTES
        hoje = (RAIZ / "templates" / "plans" / "today.html").read_text(encoding="utf-8")
        pwa = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        self.assertIn(promessa, hoje)
        self.assertIn(promessa, pwa)
        for texto, nome in ((hoje, "today.html"), (pwa, "pwa.js")):
            self.assertNotIn("10 minutos antes", re.sub(r"/\*.*?\*/", "", texto, flags=re.S), nome)
