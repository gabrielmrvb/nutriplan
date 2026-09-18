# -*- coding: utf-8 -*-
"""`GET /tarefas/lembretes/externo/<token>/`: o disparo PONTUAL dos lembretes.

O `schedule` do GitHub Actions ATRASA e PULA — MEDIDO em 18/09/2026: ~9
rodadas em 31 h (intervalos de 2 a 5,5 h), então os lembretes saíam a cada
~4,4 h em vez de 5 min. O UptimeRobot bate a cada 5 min e é pontual, mas o
plano free só manda GET/HEAD e sem cabeçalho — o token vem na URL.

O que este módulo guarda:

- **portão**: sem `NUTRIPLAN_DISPARO_TOKEN`, 503 (o disparo não existe);
  token errado, 403; só GET;
- **token na URL não vaza no log do Django**: `observabilidade.redigir` troca
  o segmento por `[REDIGIDO]` (no log de ACESSO do Render ele aparece, e é
  por isso que é um token SEPARADO, de baixo dano);
- **limite de taxa**: dois GETs em menos de `INTERVALO_MINIMO_EXTERNO` não
  acordam o Neon duas vezes;
- **fallback**: o POST do `schedule` se abstém quando um disparo externo
  cuidou há menos de `RESERVA_DO_FALLBACK` — e assume quando o externo para;
- **auditoria**: o log diz QUEM disparou (user-agent, origem), nunca o token.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config import observabilidade
from push import tarefas

TOKEN = "disparo-forte-com-tamanho-de-64-0123456789abcdef0123456789abcdef"
COM_TOKEN = {"NUTRIPLAN_DISPARO_TOKEN": TOKEN}


@override_settings(**COM_TOKEN)
class OPortaoDoDisparoExternoTests(TestCase):
    def setUp(self):
        tarefas.esquecer_pausa()
        tarefas.esquecer_externo()
        self.addCleanup(tarefas.esquecer_externo)
        self.addCleanup(tarefas.esquecer_pausa)
        self.url = reverse("disparo_externo", args=[TOKEN])

    def test_token_certo_roda_e_e_200(self):
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 0, "skipped": 0, "failed": 0}):
            with patch("push.tarefas.push_is_configured", return_value=True):
                resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("error", resposta.json())

    def test_token_errado_e_403_e_nada_roda(self):
        with patch("push.tarefas.send_meal_reminders") as enviar:
            resposta = self.client.get(reverse("disparo_externo", args=["errado"]))
        self.assertEqual(resposta.status_code, 403)
        enviar.assert_not_called()

    @override_settings(NUTRIPLAN_DISPARO_TOKEN="")
    def test_sem_variavel_e_503(self):
        with patch("push.tarefas.send_meal_reminders") as enviar:
            resposta = self.client.get(reverse("disparo_externo", args=[TOKEN]))
        self.assertEqual(resposta.status_code, 503)
        enviar.assert_not_called()

    def test_so_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.put(self.url).status_code, 405)

    def test_o_disparo_e_marcado_como_externo(self):
        """Um disparo pelo GET conta como EXTERNO: o fallback do POST vê que
        alguém pontual cuidou e se abstém."""
        tarefas.esquecer_pausa()
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 0, "skipped": 0, "failed": 0}):
            with patch("push.tarefas.push_is_configured", return_value=True):
                self.client.get(self.url)
        self.assertIsNotNone(tarefas.ultimo_externo())


class OLimiteDeTaxaTests(TestCase):
    def setUp(self):
        tarefas.esquecer_pausa()
        tarefas.esquecer_externo()
        self.addCleanup(tarefas.esquecer_externo)
        self.addCleanup(tarefas.esquecer_pausa)

    def test_dois_disparos_colados_o_segundo_e_limitado(self):
        agora = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 1, "skipped": 0, "failed": 0}) as enviar:
            with patch("push.tarefas.push_is_configured", return_value=True):
                with patch("push.tarefas.proxima_refeicao_com_assinatura", return_value=None):
                    primeiro = tarefas.rodar(now=agora, externo=True)
                    segundo = tarefas.rodar(now=agora + timedelta(seconds=10), externo=True)
        self.assertFalse(primeiro.get("limitada"))
        self.assertTrue(segundo.get("limitada"), segundo)
        # o envio só rodou uma vez
        self.assertEqual(enviar.call_count, 1)

    def test_passado_o_intervalo_dispara_de_novo(self):
        agora = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 0, "skipped": 0, "failed": 0}):
            with patch("push.tarefas.push_is_configured", return_value=True):
                with patch("push.tarefas.proxima_refeicao_com_assinatura", return_value=None):
                    tarefas.rodar(now=agora, externo=True)
                    depois = tarefas.rodar(now=agora + tarefas.INTERVALO_MINIMO_EXTERNO + timedelta(seconds=1), externo=True)
        self.assertFalse(depois.get("limitada"), depois)


class OFallbackSeAbstemTests(TestCase):
    def setUp(self):
        tarefas.esquecer_pausa()
        tarefas.esquecer_externo()
        self.addCleanup(tarefas.esquecer_externo)
        self.addCleanup(tarefas.esquecer_pausa)

    def test_o_fallback_se_abstem_quando_o_externo_cuidou_ha_pouco(self):
        agora = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 0, "skipped": 0, "failed": 0}) as enviar:
            with patch("push.tarefas.push_is_configured", return_value=True):
                with patch("push.tarefas.proxima_refeicao_com_assinatura", return_value=None):
                    tarefas.rodar(now=agora, externo=True)  # o pontual cuidou
                    fallback = tarefas.rodar(now=agora + timedelta(minutes=2), externo=False)
        self.assertTrue(fallback.get("fallback_dispensado"), fallback)
        self.assertEqual(enviar.call_count, 1, "o fallback não rodou de novo")

    def test_o_fallback_assume_quando_o_externo_parou(self):
        agora = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 0, "skipped": 0, "failed": 0}) as enviar:
            with patch("push.tarefas.push_is_configured", return_value=True):
                with patch("push.tarefas.proxima_refeicao_com_assinatura", return_value=None):
                    tarefas.rodar(now=agora, externo=True)
                    tarefas.esquecer_pausa()  # a pausa do externo não é o que este teste mede
                    tarde = tarefas.rodar(now=agora + tarefas.RESERVA_DO_FALLBACK + timedelta(minutes=1), externo=False)
        self.assertFalse(tarde.get("fallback_dispensado"), tarde)
        self.assertEqual(enviar.call_count, 2, "sem disparo externo recente, o fallback assume")


class OTokenNaoVazaNoLogTests(TestCase):
    def setUp(self):
        tarefas.esquecer_pausa()
        tarefas.esquecer_externo()
        self.addCleanup(tarefas.esquecer_externo)
        self.addCleanup(tarefas.esquecer_pausa)

    def test_o_token_do_caminho_e_redigido(self):
        caminho = "/tarefas/lembretes/externo/%s/" % TOKEN
        redigido = observabilidade.redigir("Internal Server Error: " + caminho)
        self.assertNotIn(TOKEN, redigido)
        self.assertIn("/tarefas/lembretes/externo/[REDIGIDO]", redigido)

    @override_settings(**COM_TOKEN)
    def test_o_log_do_disparo_nao_carrega_o_token(self):
        tarefas.esquecer_pausa()
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 0, "skipped": 0, "failed": 0}):
            with patch("push.tarefas.push_is_configured", return_value=True):
                with self.assertLogs("push.views", level="INFO") as capturado:
                    self.client.get(
                        reverse("disparo_externo", args=[TOKEN]),
                        HTTP_USER_AGENT="UptimeRobot/2.0",
                    )
        linha = "\n".join(capturado.output)
        self.assertIn("disparo externo", linha)
        self.assertIn("UptimeRobot", linha)
        self.assertNotIn(TOKEN, linha)
