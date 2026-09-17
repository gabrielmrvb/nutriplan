# -*- coding: utf-8 -*-
"""O lembrete acompanha a cadência do agendador — e chega ANTES da refeição.

Até 16/09/2026 `send_meal_reminders` estava escrito para rodar de 5 em 5
minutos com janela de 10: cada rodada olhava `(agora, agora+10]`, e o aviso
saía de 0 a 10 minutos antes — inclusive "0 minutos antes", que não é
lembrete. Desde então quem chama a tarefa é o GitHub Actions
(`.github/workflows/lembretes.yml`, `*/5`), e o relógio do Actions ATRASA:
em hora cheia, 5 a 15 minutos de atraso são comuns. Com janela igual ao
intervalo, um atraso de 10 minutos deixa refeição sem aviso.

Propriedades que este módulo guarda, minuto a minuto:

- toda rodada que vê uma refeição a vê de 5 a `REMINDER_LEAD_MINUTES`
  minutos antes — nunca depois (é a forma da janela);
- com o agendador na cadência nominal OU atrasado até
  `ATRASO_TOLERADO_MINUTOS`, NENHUMA refeição fica sem rodada que a veja —
  sobreposição é permitida (a constraint do banco não deixa duplicar);
- o que o código diz é o que o fluxo agenda e o que a tela promete.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from push import services

RAIZ = Path(settings.BASE_DIR)
FLUXO = RAIZ / ".github" / "workflows" / "lembretes.yml"


def _janela(now):
    return services.janela_do_lembrete(now)


def _ve(janela, minuto):
    start, target = janela
    if start < target:
        return start < minuto <= target
    return minuto > start or minuto <= target


class ACadenciaCobreTodoMinutoTests(SimpleTestCase):
    def test_a_janela_tolera_o_atraso_do_agendador(self):
        self.assertGreaterEqual(services.REMINDER_WINDOW_MINUTES, services.CRON_INTERVALO_MINUTOS)
        self.assertGreaterEqual(services.ATRASO_TOLERADO_MINUTOS, 10)

    def test_nenhuma_refeicao_fica_sem_aviso_mesmo_com_o_agendador_atrasado(self):
        base = datetime(2026, 9, 16, 0, 0)
        pior = services.CRON_INTERVALO_MINUTOS + services.ATRASO_TOLERADO_MINUTOS
        for passo in range(services.CRON_INTERVALO_MINUTOS, pior + 1, 5):
            for fase in range(passo):
                rodadas = [base + timedelta(minutes=m) for m in range(fase, 24 * 60, passo)]
                for m in range(24 * 60):
                    refeicao = (base + timedelta(minutes=m)).time()
                    viram = [t for t in rodadas if _ve(_janela(t), refeicao)]
                    self.assertGreaterEqual(len(viram), 1, (passo, fase, m))
                    for t in viram:
                        antecedencia = (m - (t - base).total_seconds() / 60) % (24 * 60)
                        self.assertGreaterEqual(antecedencia, 5, (passo, fase, m))
                        self.assertLessEqual(antecedencia, services.REMINDER_LEAD_MINUTES, (passo, fase, m))


class OAgendadorEATelaDizemOMesmoTests(SimpleTestCase):
    def test_o_fluxo_do_actions_agenda_a_mesma_cadencia(self):
        yaml = FLUXO.read_text(encoding="utf-8")
        crons = re.findall(r'cron:\s*"([^"]+)"', yaml)
        self.assertEqual(len(crons), 1, crons)
        self.assertTrue(crons[0].startswith("*/%d " % services.CRON_INTERVALO_MINUTOS), crons[0])
        # E ele chama a rota certa, com o token vindo dos segredos — nunca do repositório.
        self.assertIn("/tarefas/lembretes/", yaml)
        self.assertIn("secrets.NUTRIPLAN_TAREFAS_TOKEN", yaml)
        self.assertIn("/saude/vivo/", yaml)
        self.assertNotIn("/saude/\"", yaml.replace("/saude/vivo/", ""))

    def test_o_render_yaml_nao_agenda_nada(self):
        """Nada pago: o cron do Render saiu do arquivo, inclusive como espelho."""
        yaml = (RAIZ / "render.yaml").read_text(encoding="utf-8")
        self.assertNotIn("type: cron", yaml)

    def test_a_tela_promete_a_antecedencia_que_o_codigo_entrega(self):
        promessa = "até %d minutos antes" % services.REMINDER_LEAD_MINUTES
        hoje = (RAIZ / "templates" / "plans" / "today.html").read_text(encoding="utf-8")
        pwa = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        self.assertIn(promessa, hoje)
        self.assertIn(promessa, pwa)
        for texto, nome in ((hoje, "today.html"), (pwa, "pwa.js")):
            self.assertNotIn("10 minutos antes", re.sub(r"/\*.*?\*/", "", texto, flags=re.S), nome)
