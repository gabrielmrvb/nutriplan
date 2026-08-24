"""Testes do PWA e das notificações.

O envio em si é mockado — o que interessa testar é a nossa regra: quem entra
na janela, quem é pulado, e o que acontece quando o navegador diz que a
assinatura morreu. Bater no servidor de push do Google num teste seria lento e
não provaria nada sobre o nosso código.
"""
import re
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActivityLevel, Goal, Profile, Sex, TrainingDay, User, WeightEntry
from plans import services
from plans.models import MealStatus
from plans.tests import CatalogFixture, create_complete_user
from pywebpush import WebPushException

from . import assets
from . import services as push_services
from .models import NotificationLog, PushSubscription

VAPID = {
    "VAPID_PUBLIC_KEY": "chave-publica-de-teste",
    "VAPID_PRIVATE_KEY": "chave-privada-de-teste",
    "VAPID_ADMIN_EMAIL": "dev@nutriplan.local",
}


def make_subscription(user, endpoint="https://push.exemplo.com/abc"):
    return PushSubscription.objects.create(
        user=user,
        endpoint=endpoint,
        p256dh_key="p256dh-de-teste",
        auth_key="auth-de-teste",
        user_agent="Firefox/Android",
    )


class PWAEndpointTests(TestCase):
    def test_manifest_describes_an_installable_app(self):
        response = self.client.get(reverse("manifest"))

        self.assertEqual(response.status_code, 200)
        manifest = response.json()
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(len(manifest["icons"]), 2)

    def test_service_worker_is_served_from_the_root(self):
        response = self.client.get("/sw.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        # Escopo: servido da raiz, controla o app inteiro.
        self.assertIn("addEventListener", response.content.decode())

    def test_service_worker_is_never_cached(self):
        response = self.client.get("/sw.js")
        self.assertIn("no-store", response["Cache-Control"])

    def test_style_and_script_are_fetched_before_the_cache(self):
        """Regressão de 24/08/2026: CSS velho servido junto com HTML novo.

        O service worker entregava qualquer coisa de /static/ do cache antes de
        olhar a rede. Depois de um deploy que muda o layout, isso não é "uma
        versão atrás" — é o app inteiro sem estilo, porque a marcação nova não
        casa com a folha antiga. CSS e JS passaram a ir à rede primeiro, e o
        cache virou o plano B para quando não há conexão.
        """
        source = self.client.get("/sw.js").content.decode()

        self.assertIn("isAppCode", source)
        # A ordem importa: a rede tem que vir antes, com o cache no catch.
        ramo = source.split("if (isAppCode(request))")[1].split("return;")[0]
        self.assertLess(ramo.index("fetch("), ramo.index("caches.match(request)"))
        # E a ida à rede precisa revalidar, senão o cache HTTP do navegador
        # responde no lugar do servidor e o CSS velho volta pela terceira porta.
        self.assertIn('cache: "no-cache"', ramo)

    def test_offline_page_works_without_login(self):
        response = self.client.get(reverse("offline"))
        self.assertContains(response, "sem conexão")


@override_settings(**VAPID)
class SubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="pessoa@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.payload = {
            "endpoint": "https://push.exemplo.com/abc",
            "keys": {"p256dh": "chave-p256dh", "auth": "chave-auth"},
        }

    def post(self, url, data):
        import json

        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_subscribing_stores_the_device(self):
        response = self.post(reverse("push:subscribe"), self.payload)

        self.assertEqual(response.status_code, 201)
        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.user, self.user)
        self.assertEqual(subscription.p256dh_key, "chave-p256dh")

    def test_subscribing_twice_updates_the_same_device(self):
        self.post(reverse("push:subscribe"), self.payload)
        self.post(reverse("push:subscribe"), self.payload)

        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_malformed_subscription_is_rejected(self):
        response = self.post(reverse("push:subscribe"), {"faltando": "tudo"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    def test_unsubscribing_deactivates_without_deleting(self):
        self.post(reverse("push:subscribe"), self.payload)
        self.post(reverse("push:unsubscribe"), {"endpoint": self.payload["endpoint"]})

        subscription = PushSubscription.objects.get()
        self.assertFalse(subscription.is_active)

    def test_anonymous_cannot_subscribe(self):
        self.client.logout()
        response = self.post(reverse("push:subscribe"), self.payload)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PushSubscription.objects.exists())

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_without_keys_the_endpoint_says_so_instead_of_breaking(self):
        response = self.post(reverse("push:subscribe"), self.payload)
        self.assertEqual(response.status_code, 503)


@override_settings(**VAPID)
class SendingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="pessoa@exemplo.com", password="senha-bem-forte-123"
        )
        self.subscription = make_subscription(self.user)

    @patch("push.services.webpush")
    def test_successful_send_records_the_use(self, webpush):
        delivered = push_services.notify_user(self.user, {"title": "oi"})

        self.assertEqual(delivered, 1)
        webpush.assert_called_once()
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.last_used_at)

    @patch("push.services.webpush")
    def test_dead_subscription_is_deactivated(self, webpush):
        class Response:
            status_code = 410

        webpush.side_effect = WebPushException("assinatura expirada", response=Response())

        delivered = push_services.notify_user(self.user, {"title": "oi"})

        self.assertEqual(delivered, 0)
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.is_active)

    @patch("push.services.webpush")
    def test_temporary_failure_keeps_the_subscription(self, webpush):
        class Response:
            status_code = 500

        webpush.side_effect = WebPushException("servidor fora", response=Response())

        push_services.notify_user(self.user, {"title": "oi"})

        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.is_active)

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    @patch("push.services.webpush")
    def test_nothing_is_sent_without_keys(self, webpush):
        self.assertEqual(push_services.notify_user(self.user, {"title": "oi"}), 0)
        webpush.assert_not_called()


@override_settings(**VAPID)
class MealReminderTests(CatalogFixture):
    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.get(order=0)
        make_subscription(self.user)
        # "Agora" é 10 minutos antes do horário da refeição — o momento do aviso.
        self.now = timezone.localtime().replace(
            hour=self.slot.time.hour, minute=self.slot.time.minute, second=0, microsecond=0
        ) - timedelta(minutes=push_services.REMINDER_LEAD_MINUTES)

    @patch("push.services.webpush")
    def test_reminder_goes_out_before_the_meal(self, webpush):
        result = push_services.send_meal_reminders(self.now)

        self.assertEqual(result["sent"], 1)
        webpush.assert_called_once()
        self.assertTrue(
            NotificationLog.objects.filter(user=self.user, slot=self.slot).exists()
        )

    @patch("push.services.webpush")
    def test_running_twice_does_not_notify_twice(self, webpush):
        push_services.send_meal_reminders(self.now)
        second = push_services.send_meal_reminders(self.now)

        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(webpush.call_count, 1)
        self.assertEqual(NotificationLog.objects.count(), 1)

    @patch("push.services.webpush")
    def test_meal_already_marked_is_not_reminded(self, webpush):
        from plans import tracking

        tracking.log_meal(
            self.user, self.slot, MealStatus.DONE, self.slot.options.first(),
            day=self.now.date(),
        )

        result = push_services.send_meal_reminders(self.now)

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped"], 1)
        webpush.assert_not_called()

    @patch("push.services.webpush")
    def test_failure_is_recorded_in_the_log(self, webpush):
        class Response:
            status_code = 500

        webpush.side_effect = WebPushException("fora do ar", response=Response())

        result = push_services.send_meal_reminders(self.now)

        self.assertEqual(result["failed"], 1)
        log = NotificationLog.objects.get()
        self.assertFalse(log.success)
        self.assertTrue(log.error)

    @patch("push.services.webpush")
    def test_meals_outside_the_window_are_left_alone(self, webpush):
        far_from_any_meal = self.now - timedelta(hours=2)

        result = push_services.send_meal_reminders(far_from_any_meal)

        self.assertEqual(result["sent"], 0)
        webpush.assert_not_called()

    def test_payload_offers_the_two_options(self):
        payload = push_services.meal_payload(self.slot)

        self.assertIn(self.slot.name, payload["title"])
        for option in self.slot.options.all():
            self.assertIn(option.template.name, payload["body"])

    @patch("push.services.webpush")
    def test_command_reports_what_it_did(self, webpush):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("send_meal_reminders", "--dry-run", stdout=out)

        self.assertIn("refeição(ões) na janela", out.getvalue())
        webpush.assert_not_called()

    @patch("push.services.webpush")
    def test_network_error_does_not_stop_the_other_devices(self, webpush):
        # Um segundo dispositivo da mesma pessoa: o primeiro estoura erro de
        # rede (que não é WebPushException), o segundo tem que receber assim
        # mesmo — senão um celular com problema deixa a pessoa sem lembrete.
        make_subscription(self.user, endpoint="https://push.exemplo.com/def")
        webpush.side_effect = [ConnectionError("DNS fora do ar"), None]

        delivered = push_services.notify_user(self.user, {"title": "oi"})

        self.assertEqual(delivered, 1)
        self.assertEqual(webpush.call_count, 2)
        # Erro de rede é temporário: nenhuma assinatura foi desativada.
        self.assertEqual(PushSubscription.objects.filter(is_active=True).count(), 2)


class ServiceWorkerContentTests(TestCase):
    """O conteúdo do sw.js é template, então dá para testar as regras dele."""

    def setUp(self):
        self.source = self.client.get("/sw.js").content.decode()

    def test_only_static_files_are_cached_at_runtime(self):
        # HTML de usuário logado não pode entrar no cache do dispositivo.
        self.assertIn('pathname.startsWith("/static/")', self.source)

    def test_navigation_falls_back_to_the_offline_page(self):
        self.assertIn('caches.match(OFFLINE_URL)', self.source)

    def test_old_cache_versions_are_deleted_on_activate(self):
        self.assertIn("caches.delete", self.source)

    def test_it_handles_push_and_notification_click(self):
        self.assertIn('addEventListener("push"', self.source)
        self.assertIn('addEventListener("notificationclick"', self.source)


@override_settings(**VAPID)
class TestPushCommandTests(TestCase):
    """O comando de diagnóstico precisa explicar o que está faltando."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="pessoa@exemplo.com", password="senha-bem-forte-123"
        )

    def run_command(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out, err = StringIO(), StringIO()
        call_command("send_test_push", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    @patch("push.services.webpush")
    def test_sends_to_the_registered_devices(self, webpush):
        make_subscription(self.user)

        out, _ = self.run_command(self.user.email)

        webpush.assert_called_once()
        self.assertIn("Enviada para 1", out)

    def test_without_devices_it_says_how_to_subscribe(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError) as ctx:
            self.run_command(self.user.email)
        self.assertIn("Ativar lembretes", str(ctx.exception))

    def test_unknown_email_is_a_clear_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError) as ctx:
            self.run_command("ninguem@exemplo.com")
        self.assertIn("Nenhum usuário", str(ctx.exception))


class AssetVersionTests(TestCase):
    """A URL do CSS muda quando o CSS muda — a defesa contra cache velho.

    O bug de 24/08/2026 foi HTML novo com folha de estilo antiga: o app abriu
    sem estilo nenhum. Nenhuma camada de cache erra se o endereço do arquivo
    novo for diferente do endereço do velho, e é isso que estes testes travam.
    """

    def setUp(self):
        assets.reset_cache()

    def tearDown(self):
        assets.reset_cache()

    def test_the_page_asks_for_a_versioned_stylesheet(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertRegex(
            response.content.decode(), r"/static/css/app\.css\?v=[0-9a-f]{8}"
        )

    def test_changing_the_file_changes_the_version(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "css" / "app.css"
            arquivo.parent.mkdir()
            arquivo.write_text("body { color: red }", encoding="utf-8")

            with override_settings(STATICFILES_DIRS=[pasta]):
                antes = assets.version()
                # Tamanho diferente de propósito: no Windows dois writes no mesmo
                # milissegundo podem carimbar a mesma data, e o teste ficaria
                # instável se a única diferença fosse o conteúdo.
                arquivo.write_text("body { color: rebeccapurple }", encoding="utf-8")
                depois = assets.version()

        self.assertNotEqual(antes, depois)

    def test_the_same_file_keeps_the_same_version(self):
        """Estável entre requisições e entre processos — senão nada seria cacheado."""
        primeira = assets.version()
        assets.reset_cache()
        self.assertEqual(primeira, assets.version())

    def test_the_version_is_not_frozen_for_the_life_of_the_process(self):
        """Regressão da primeira tentativa de conserto.

        O hash era calculado uma vez e guardado no módulo. Como o `runserver`
        não reinicia quando o CSS muda, a URL continuava a mesma para um arquivo
        novo — ou seja, o bug original de volta, só que em desenvolvimento.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "css" / "app.css"
            arquivo.parent.mkdir()
            arquivo.write_text("a{}", encoding="utf-8")

            with override_settings(STATICFILES_DIRS=[pasta]):
                antes = assets.version()
                arquivo.write_text("a{color:red}", encoding="utf-8")
                # Sem reset_cache(): é exatamente isso que o servidor em pé faz.
                self.assertNotEqual(antes, assets.version())

    def test_the_service_worker_caches_the_same_url_the_page_asks_for(self):
        """Duas URLs para o mesmo arquivo seria cachear duas cópias que divergem."""
        pagina = self.client.get(reverse("accounts:login")).content.decode()
        worker = self.client.get("/sw.js").content.decode()

        css = re.search(r"/static/css/app\.css\?v=[0-9a-f]{8}", pagina).group()
        self.assertIn(css, worker)
