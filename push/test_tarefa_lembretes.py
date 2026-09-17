# -*- coding: utf-8 -*-
"""`POST /tarefas/lembretes/`: o agendador de fora bate aqui, e o app dispara.

Nada pago (decisão do dono, 16/09/2026): em vez de um cron no Render, o
GitHub Actions chama esta rota de 5 em 5 minutos com um token no
`Authorization`. O endpoint é o `send_meal_reminders` atrás de um portão:

- **token**: `NUTRIPLAN_TAREFAS_TOKEN` (variável no Render, segredo no
  GitHub; nunca no repositório). Sem a variável, 503 — a tarefa não existe;
  header ausente ou errado, 403, sem dizer qual dos dois;
- **só POST**, sem sessão, sem CSRF (é servidor falando com servidor);
- **idempotente**: duas chamadas no mesmo minuto mandam UMA notificação —
  quem garante é a unicidade `(usuário, refeição, dia)` do `NotificationLog`;
- **barato para o Neon**: o banco dorme após 5 min parado e a cota gratuita
  é de 100 CU-h/mês; uma consulta a cada 5 min o manteria acordado o dia
  inteiro (182 CU-h). Depois de rodar, a tarefa calcula a PRÓXIMA refeição de
  quem tem assinatura ativa e DORME até 20 min antes dela (ou até 30 min, o
  que vier primeiro): nesse intervalo o POST responde sem tocar no banco. A
  pausa é por processo (dois workers, duas pausas) e some no restart.
"""
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from plans import services
from plans.tests import CatalogFixture, create_complete_user
from push import services as push_services
from push import tarefas
from push.models import NotificationLog
from push.tests import VAPID, make_subscription

TOKEN = "token-de-teste-com-tamanho-razoavel-0123456789"
COM_TOKEN = dict(VAPID, NUTRIPLAN_TAREFAS_TOKEN=TOKEN)


def _agora_do_aviso(slot):
    """O instante em que a janela vê a refeição: `lead` minutos antes."""
    return timezone.localtime().replace(
        hour=slot.time.hour, minute=slot.time.minute, second=0, microsecond=0
    ) - timedelta(minutes=push_services.REMINDER_LEAD_MINUTES)


@override_settings(**COM_TOKEN)
class OPortaoDaTarefaTests(TestCase):
    def setUp(self):
        tarefas.esquecer_pausa()
        self.url = reverse("tarefas_lembretes")

    def _post(self, token=TOKEN):
        extra = {"HTTP_AUTHORIZATION": "Bearer " + token} if token is not None else {}
        return self.client.post(self.url, **extra)

    def test_sem_header_e_403_e_nada_roda(self):
        with patch("push.tarefas.send_meal_reminders") as enviar:
            resposta = self._post(token=None)
        self.assertEqual(resposta.status_code, 403)
        enviar.assert_not_called()

    def test_token_errado_e_403(self):
        with patch("push.tarefas.send_meal_reminders") as enviar:
            resposta = self._post(token="outro")
        self.assertEqual(resposta.status_code, 403)
        enviar.assert_not_called()

    @override_settings(NUTRIPLAN_TAREFAS_TOKEN="")
    def test_sem_a_variavel_a_tarefa_nao_existe(self):
        with patch("push.tarefas.send_meal_reminders") as enviar:
            resposta = self._post()
        self.assertEqual(resposta.status_code, 503)
        enviar.assert_not_called()

    def test_get_nao_e_aceito(self):
        resposta = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer " + TOKEN)
        self.assertEqual(resposta.status_code, 405)

    def test_o_token_certo_roda_e_responde_a_contagem(self):
        with patch("push.tarefas.send_meal_reminders", return_value={"sent": 2, "skipped": 1, "failed": 0}) as enviar:
            resposta = self._post()
        self.assertEqual(resposta.status_code, 200)
        enviar.assert_called_once()
        corpo = resposta.json()
        self.assertEqual((corpo["enviadas"], corpo["puladas"], corpo["falhas"]), (2, 1, 0))
        self.assertIn("agora", corpo)


@override_settings(**COM_TOKEN)
class ATarefaDisparaEEIdempotenteTests(CatalogFixture):
    def setUp(self):
        tarefas.esquecer_pausa()
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.get(order=0)
        make_subscription(self.user)
        self.url = reverse("tarefas_lembretes")

    def _post(self):
        return self.client.post(self.url, HTTP_AUTHORIZATION="Bearer " + TOKEN)

    @patch("push.services.webpush")
    def test_a_refeicao_na_janela_recebe_um_aviso_so_mesmo_com_duas_chamadas(self, webpush):
        agora = _agora_do_aviso(self.slot)
        with patch("push.tarefas.timezone.localtime", return_value=agora):
            primeira = self._post().json()
            tarefas.esquecer_pausa()  # a segunda chamada vai ao banco de novo
            segunda = self._post().json()
        self.assertEqual(primeira["enviadas"], 1)
        self.assertEqual(segunda["enviadas"], 0)
        self.assertEqual(webpush.call_count, 1)
        self.assertEqual(NotificationLog.objects.filter(user=self.user, slot=self.slot).count(), 1)


@override_settings(**COM_TOKEN)
class ATarefaDeixaONeonDormirTests(CatalogFixture):
    """Depois de rodar, a tarefa sabe quando é a próxima refeição de quem tem
    assinatura e não volta ao banco antes disso."""

    def setUp(self):
        tarefas.esquecer_pausa()
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        make_subscription(self.user)
        self.url = reverse("tarefas_lembretes")

    def _post(self):
        return self.client.post(self.url, HTTP_AUTHORIZATION="Bearer " + TOKEN)

    @patch("push.services.webpush")
    def test_entre_refeicoes_o_post_responde_sem_consulta(self, webpush):
        primeiro = self.plan.slots.order_by("time").first()
        # Uma hora antes da primeira refeição: nada na janela, próxima em 60 min.
        agora = _agora_do_aviso(primeiro) - timedelta(minutes=40)
        with patch("push.tarefas.timezone.localtime", return_value=agora):
            self._post()
            with CaptureQueriesContext(connection) as consultas:
                corpo = self._post().json()
        self.assertEqual(len(consultas.captured_queries), 0)
        self.assertTrue(corpo["pausada"])

    @patch("push.services.webpush")
    def test_a_pausa_acaba_a_tempo_da_proxima_refeicao(self, webpush):
        primeiro = self.plan.slots.order_by("time").first()
        agora = _agora_do_aviso(primeiro) - timedelta(minutes=40)
        with patch("push.tarefas.timezone.localtime", return_value=agora):
            self._post()
        # No instante da janela da refeição, a tarefa volta ao banco e envia.
        with patch("push.tarefas.timezone.localtime", return_value=_agora_do_aviso(primeiro)):
            corpo = self._post().json()
        self.assertFalse(corpo["pausada"])
        self.assertEqual(corpo["enviadas"], 1)

    @patch("push.services.webpush")
    def test_a_pausa_nunca_passa_de_30_minutos(self, webpush):
        """Assinatura nova ou plano novo têm de ser vistos em no máximo meia
        hora — é o preço de não consultar a cada 5 minutos."""
        primeiro = self.plan.slots.order_by("time").first()
        agora = _agora_do_aviso(primeiro) - timedelta(hours=3)
        with patch("push.tarefas.timezone.localtime", return_value=agora):
            self._post()
        self.assertLessEqual(tarefas.pausa_ate() - agora, timedelta(minutes=30))

    def test_sem_assinatura_nenhuma_a_pausa_e_a_maxima(self):
        from push.models import PushSubscription
        PushSubscription.objects.all().delete()
        agora = timezone.localtime()
        with patch("push.tarefas.timezone.localtime", return_value=agora):
            corpo = self._post().json()
        self.assertEqual(corpo["enviadas"], 0)
        self.assertEqual(tarefas.pausa_ate() - agora, timedelta(minutes=30))


@override_settings(**COM_TOKEN)
class SoQuemTemAssinaturaEntraNaRodadaTests(CatalogFixture):
    """Vista na prova de produção de 16/09/2026: a rodada disse `falhas: 3`
    — três refeições de contas SEM assinatura, cada uma ganhando um
    `NotificationLog` de falha por dia. Quem nunca ativou lembrete não é
    falha: não entra na rodada, não gera linha, não gera consulta de envio."""

    def setUp(self):
        tarefas.esquecer_pausa()
        self.sem = create_complete_user("sem.assinatura@exemplo.com")
        self.plano_sem = services.create_plan(self.sem)
        self.com = create_complete_user("com.assinatura@exemplo.com")
        self.plano_com = services.create_plan(self.com)
        make_subscription(self.com, endpoint="https://push.exemplo.com/com")

    @patch("push.services.webpush")
    def test_quem_nao_tem_assinatura_nao_gera_registro_de_falha(self, webpush):
        slot_sem = self.plano_sem.slots.get(order=0)
        slot_com = self.plano_com.slots.get(order=0)
        self.assertEqual(slot_sem.time, slot_com.time)  # mesma rotina, mesma janela
        resultado = push_services.send_meal_reminders(_agora_do_aviso(slot_com))
        self.assertEqual((resultado["sent"], resultado["failed"]), (1, 0))
        self.assertFalse(NotificationLog.objects.filter(user=self.sem).exists())
        self.assertTrue(NotificationLog.objects.filter(user=self.com, success=True).exists())

    @patch("push.services.webpush")
    def test_assinatura_desativada_conta_como_sem_assinatura(self, webpush):
        from push.models import PushSubscription
        PushSubscription.objects.filter(user=self.com).update(is_active=False)
        slot_com = self.plano_com.slots.get(order=0)
        resultado = push_services.send_meal_reminders(_agora_do_aviso(slot_com))
        self.assertEqual((resultado["sent"], resultado["failed"], resultado["skipped"]), (0, 0, 0))
        self.assertFalse(NotificationLog.objects.exists())
