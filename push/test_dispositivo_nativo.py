"""Push NATIVO (Fase 2 da missão Capacitor, 22/09/2026): o app instalado
não tem Web Push — o WebView do Android não expõe `PushManager` e o
WKWebView do iPhone também não. A casca registra um token do FCM
(`@capacitor-firebase/messaging`; no iOS o FCM encaminha ao APNs com a
chave que o dono sobe no Firebase) em `DispositivoNativo`, e o servidor
manda pelo FCM HTTP v1 com a conta de serviço do projeto Firebase
(`FIREBASE_SERVICE_ACCOUNT_JSON`). Os lembretes de refeição são os MESMOS:
`due_slots` passa a contar quem só tem dispositivo nativo, e `notify_user`
manda para os dois mundos.

Sem a conta de serviço nada sai (e nada quebra): é o estado até o projeto
Firebase existir.
"""
import json
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from datetime import timedelta

from django.utils import timezone

from plans import services as plan_services
from plans.tests import create_complete_user
from push import fcm, services
from push.models import DispositivoNativo

CONTA_DE_SERVICO = json.dumps({
    "type": "service_account", "project_id": "nutriplan-teste", "private_key_id": "k1",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END PRIVATE KEY-----\n",
    "client_email": "fcm@nutriplan-teste.iam.gserviceaccount.com", "token_uri": "https://oauth2.googleapis.com/token",
})


class RegistrarDispositivoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="app@exemplo.com")
        self.client.force_login(self.user)
        self.url = reverse("push:dispositivo_registrar")

    def _registrar(self, token="fcm-token-1", plataforma="android"):
        return self.client.post(self.url, json.dumps({"token": token, "plataforma": plataforma}), content_type="application/json")

    def test_registra_o_token_do_aparelho(self):
        resposta = self._registrar()
        self.assertEqual(resposta.status_code, 201)
        d = DispositivoNativo.objects.get(token="fcm-token-1")
        self.assertEqual(d.user, self.user)
        self.assertEqual(d.plataforma, "android")
        self.assertTrue(d.ativo)

    def test_registrar_de_novo_e_idempotente_e_reativa(self):
        self._registrar()
        DispositivoNativo.objects.update(ativo=False)
        resposta = self._registrar()
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(DispositivoNativo.objects.count(), 1)
        self.assertTrue(DispositivoNativo.objects.get().ativo)

    def test_o_token_que_muda_de_conta_muda_de_dono(self):
        """Aparelho compartilhado: quem entrou por último é quem recebe."""
        self._registrar()
        outra = create_complete_user(email="outra@exemplo.com")
        self.client.force_login(outra)
        self._registrar()
        self.assertEqual(DispositivoNativo.objects.get(token="fcm-token-1").user, outra)

    def test_token_ou_plataforma_invalidos_sao_400(self):
        self.assertEqual(self._registrar(token="").status_code, 400)
        self.assertEqual(self._registrar(plataforma="windows").status_code, 400)

    def test_anonimo_nao_registra(self):
        c = Client()
        resposta = c.post(self.url, json.dumps({"token": "x", "plataforma": "ios"}), content_type="application/json")
        self.assertIn(resposta.status_code, (302, 403))
        self.assertFalse(DispositivoNativo.objects.exists())

    def test_remover_desativa_sem_apagar(self):
        self._registrar()
        resposta = self.client.post(reverse("push:dispositivo_remover"), json.dumps({"token": "fcm-token-1"}), content_type="application/json")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DispositivoNativo.objects.get().ativo)


class OsLembretesChegamAoAparelhoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="app@exemplo.com")
        self.plano = plan_services.create_plan(self.user)
        self.dispositivo = DispositivoNativo.objects.create(user=self.user, token="t1", plataforma="ios")

    def test_quem_so_tem_dispositivo_nativo_entra_nas_refeicoes_da_vez(self):
        slot = self.plano.slots.get(order=0)
        # "agora" é o momento do aviso: `REMINDER_LEAD_MINUTES` antes da refeição
        agora = timezone.localtime().replace(hour=slot.time.hour, minute=slot.time.minute, second=0, microsecond=0) - timedelta(minutes=services.REMINDER_LEAD_MINUTES)
        self.assertIn(slot, list(services.due_slots(agora)))
        self.assertIsNotNone(services.proxima_refeicao_com_assinatura(agora))

    def test_sem_nenhum_dispositivo_nao_e_assinante(self):
        DispositivoNativo.objects.all().delete()
        slot = self.plano.slots.get(order=0)
        agora = timezone.localtime().replace(hour=slot.time.hour, minute=slot.time.minute, second=0, microsecond=0) - timedelta(minutes=services.REMINDER_LEAD_MINUTES)
        self.assertNotIn(slot, list(services.due_slots(agora)))

    def test_notify_user_manda_ao_fcm_alem_do_web_push(self):
        with mock.patch("push.fcm.enviar", return_value=True) as enviar:
            entregues = services.notify_user(self.user, {"title": "Almoço", "body": "x", "url": "/", "tag": "meal-1"})
        self.assertEqual(entregues, 1)
        dispositivo, payload = enviar.call_args[0]
        self.assertEqual(dispositivo, self.dispositivo)
        self.assertEqual(payload["title"], "Almoço")

    def test_dispositivo_desativado_nao_recebe(self):
        DispositivoNativo.objects.update(ativo=False)
        with mock.patch("push.fcm.enviar", return_value=True) as enviar:
            services.notify_user(self.user, {"title": "x", "body": "y", "url": "/", "tag": "t"})
        enviar.assert_not_called()


class OEnvioPeloFcmTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="app@exemplo.com")
        self.dispositivo = DispositivoNativo.objects.create(user=self.user, token="t1", plataforma="android")
        self.payload = {"title": "Almoço — 12:30", "body": "Frango com arroz", "url": "/#slot-3", "tag": "meal-3"}

    def test_sem_conta_de_servico_nao_manda_e_nao_quebra(self):
        with self.settings(FIREBASE_SERVICE_ACCOUNT_JSON=""):
            self.assertFalse(fcm.configurado())
            self.assertFalse(fcm.enviar(self.dispositivo, self.payload))

    @override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=CONTA_DE_SERVICO)
    def test_a_mensagem_v1_leva_titulo_corpo_url_canal_e_som(self):
        with mock.patch("push.fcm._token_de_acesso", return_value="ya29.teste"), \
             mock.patch("push.fcm.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"name": "projects/nutriplan-teste/messages/1"}
            self.assertTrue(fcm.enviar(self.dispositivo, self.payload))
        url = post.call_args[0][0]
        corpo = post.call_args[1]["json"]["message"]
        self.assertEqual(url, "https://fcm.googleapis.com/v1/projects/nutriplan-teste/messages:send")
        self.assertEqual(post.call_args[1]["headers"]["Authorization"], "Bearer ya29.teste")
        self.assertEqual(corpo["token"], "t1")
        self.assertEqual(corpo["notification"], {"title": "Almoço — 12:30", "body": "Frango com arroz"})
        self.assertEqual(corpo["data"]["url"], "/#slot-3")
        self.assertEqual(corpo["android"]["notification"]["channel_id"], "lembretes")
        self.assertEqual(corpo["apns"]["payload"]["aps"]["sound"], "default")
        self.dispositivo.refresh_from_db()
        self.assertIsNotNone(self.dispositivo.visto_em)

    @override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=CONTA_DE_SERVICO)
    def test_token_que_o_fcm_diz_morto_e_desativado(self):
        with mock.patch("push.fcm._token_de_acesso", return_value="ya29.teste"), \
             mock.patch("push.fcm.requests.post") as post:
            post.return_value.status_code = 404
            post.return_value.json.return_value = {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}
            self.assertFalse(fcm.enviar(self.dispositivo, self.payload))
        self.dispositivo.refresh_from_db()
        self.assertFalse(self.dispositivo.ativo)

    @override_settings(FIREBASE_SERVICE_ACCOUNT_JSON=CONTA_DE_SERVICO)
    def test_rede_fora_nao_derruba_a_rodada(self):
        with mock.patch("push.fcm._token_de_acesso", return_value="ya29.teste"), \
             mock.patch("push.fcm.requests.post", side_effect=OSError("sem rede")):
            self.assertFalse(fcm.enviar(self.dispositivo, self.payload))
        self.dispositivo.refresh_from_db()
        self.assertTrue(self.dispositivo.ativo, "falha de rede não é token morto")
