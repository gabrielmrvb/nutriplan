"""Testes do PWA e das notificações.

O envio em si é mockado — o que interessa testar é a nossa regra: quem entra
na janela, quem é pulado, e o que acontece quando o navegador diz que a
assinatura morreu. Bater no servidor de push do Google num teste seria lento e
não provaria nada sobre o nosso código.
"""
import re
import struct
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
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


class InstallabilityTests(TestCase):
    """O que um navegador confere antes de oferecer "instalar".

    Não é uma lista de opinião: Chrome e Edge só disparam o
    `beforeinstallprompt` se o manifest tiver nome, `start_url`, `display`
    autônomo e um ícone de 192 e um de 512, e se houver service worker no
    escopo. Falhar um item não dá erro em lugar nenhum — o convite
    simplesmente nunca aparece, e é impossível adivinhar qual item faltou.
    Cada teste aqui é um desses itens.
    """

    def setUp(self):
        self.manifest = self.client.get(reverse("manifest")).json()

    def test_manifest_describes_an_installable_app(self):
        self.assertEqual(self.manifest["start_url"], "/")
        self.assertEqual(self.manifest["scope"], "/")
        self.assertIn(self.manifest["display"], {"standalone", "fullscreen", "minimal-ui"})
        self.assertTrue(self.manifest["name"])
        self.assertTrue(self.manifest["short_name"])

    def test_manifest_is_served_with_the_right_content_type(self):
        response = self.client.get(reverse("manifest"))
        self.assertEqual(response["Content-Type"], "application/manifest+json")

    def test_the_two_required_icon_sizes_are_declared(self):
        tamanhos = {icone["sizes"] for icone in self.manifest["icons"]}
        self.assertIn("192x192", tamanhos)
        self.assertIn("512x512", tamanhos)

    def test_maskable_icons_are_separate_files(self):
        """Declarar "any maskable" no mesmo arquivo é o erro clássico.

        O Android recorta o ícone maskable no formato do fabricante e só
        preserva o círculo central. Um arquivo desenhado para preencher a arte
        inteira aparece com as pontas cortadas — por isso são dois desenhos, um
        cheio e um com margem, cada um declarando um propósito só.
        """
        maskable = [i for i in self.manifest["icons"] if i["purpose"] == "maskable"]
        normais = [i for i in self.manifest["icons"] if i["purpose"] == "any"]

        self.assertEqual({i["sizes"] for i in maskable}, {"192x192", "512x512"})
        self.assertEqual({i["sizes"] for i in normais}, {"192x192", "512x512"})
        self.assertFalse(
            {i["src"] for i in maskable} & {i["src"] for i in normais},
            "o mesmo arquivo não pode servir aos dois propósitos",
        )

    def test_every_icon_file_exists_and_is_a_png_of_the_declared_size(self):
        """Um ícone quebrado invalida a instalação inteira, em silêncio."""
        for icone in self.manifest["icons"]:
            with self.subTest(icone=icone["src"]):
                relativo = icone["src"].split("/static/")[1].split("?")[0]
                caminho = Path(settings.BASE_DIR) / "static" / relativo
                self.assertTrue(caminho.exists(), "arquivo não encontrado")

                dados = caminho.read_bytes()
                self.assertEqual(dados[:8], b"\x89PNG\r\n\x1a\n", "não é PNG")
                # Largura e altura moram nos bytes 16..24, logo depois do IHDR.
                largura, altura = struct.unpack(">II", dados[16:24])
                declarado = int(icone["sizes"].split("x")[0])
                self.assertEqual((largura, altura), (declarado, declarado))

    def test_icon_urls_do_not_change_with_every_deploy(self):
        """Endereço do ícone é a identidade do app instalado.

        CSS e JS carregam o hash do conteúdo na URL, e é por isso que funcionam
        bem em cache. Pendurar o mesmo hash no ícone faria ele mudar de endereço
        a cada mudança de folha de estilo — e o que muda de endereço é baixado
        de novo, e no Android pode ser tratado como um ícone diferente.
        """
        for icone in self.manifest["icons"]:
            with self.subTest(icone=icone["src"]):
                self.assertNotIn("?v=", icone["src"])

    def test_the_theme_colour_matches_the_dark_interface(self):
        """Cor errada aqui vira uma faixa clara em volta do app escuro."""
        self.assertEqual(self.manifest["theme_color"], "#0b0f0e")
        self.assertEqual(self.manifest["background_color"], "#0b0f0e")

    def test_shortcuts_point_at_urls_that_answer(self):
        atalhos = self.manifest["shortcuts"]
        self.assertTrue(atalhos)
        for atalho in atalhos:
            with self.subTest(atalho=atalho["short_name"]):
                # Deslogado redireciona para o login; o que não pode é 404.
                resposta = self.client.get(atalho["url"])
                self.assertIn(resposta.status_code, {200, 302})

    def test_the_page_carries_the_tags_ios_needs(self):
        """iOS ignora o manifest inteiro: só estas metas fazem efeito lá."""
        html = self.client.get(reverse("accounts:login")).content.decode()

        self.assertIn('rel="manifest"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('name="apple-mobile-web-app-capable" content="yes"', html)
        self.assertIn(
            'name="apple-mobile-web-app-status-bar-style" content="black-translucent"',
            html,
        )
        self.assertIn('name="apple-mobile-web-app-title"', html)

    def test_the_viewport_reaches_under_the_translucent_status_bar(self):
        """`black-translucent` sem `viewport-fit=cover` corta o topo da tela."""
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn("viewport-fit=cover", html)

    def test_the_install_invitation_starts_hidden_even_for_a_visitor(self):
        """Nasce `hidden`: quem decide mostrar é o JS, depois de confirmar que
        dá para instalar. E aparece para quem ainda não tem conta também —
        instalar antes de cadastrar é um caminho legítimo."""
        html = self.client.get(reverse("accounts:login")).content.decode()

        self.assertIn("data-install", html)
        self.assertIn("data-install-go", html)
        self.assertRegex(html, r'<div class="install"[^>]*\shidden')

    def test_the_invitation_has_two_ways_out(self):
        """Queixa real de produção: "não possui um botão funcional de fechar".

        Eram dois problemas somados — o "×" tinha 30x30, abaixo do mínimo de
        44 para o dedo, e era a única saída. Quem não associa o símbolo a
        fechar não tinha alternativa nenhuma. Agora são duas, e a escrita por
        extenso é a que não depende de interpretar ícone.
        """
        html = self.client.get(reverse("accounts:login")).content.decode()

        self.assertEqual(html.count("data-install-close"), 2)
        self.assertIn("Agora não", html)
        self.assertIn('aria-label="Fechar o convite de instalação"', html)

    def test_the_touch_targets_are_big_enough_for_a_finger(self):
        """44x44 é o mínimo; abaixo disso o toque erra e o botão parece morto."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        bloco = css.split(".install__close {")[1].split("}")[0]

        self.assertIn("width: 2.75rem", bloco)   # 44px
        self.assertIn("height: 2.75rem", bloco)

        acoes = css.split(".install__later {")[1].split("}")[0]
        self.assertIn("min-height: 2.75rem", acoes)

    def test_the_page_reserves_room_for_the_fixed_bar(self):
        """Barra fixa não ocupa espaço no layout, então pousa em cima do
        conteúdo — na tela de entrar, bem em cima do "Criar agora"."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("body.tem-convite .container", css)

        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )
        # A classe entra quando o convite aparece e sai quando ele fecha; se
        # só entrasse, sobraria um vão em branco no rodapé para sempre.
        self.assertIn('classList.add("tem-convite")', js)
        self.assertIn('classList.remove("tem-convite")', js)

    def test_dismissing_is_remembered_for_seven_days_not_forever(self):
        """Guardar "1" fazia o convite sumir para sempre.

        Some cedo demais: quem fecha na primeira visita, antes de saber se o
        app presta, perde a oferta para sempre.
        """
        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("7 * 24 * 60 * 60 * 1000", js)
        self.assertIn("Date.now() - quando < SETE_DIAS", js)

    def test_the_service_worker_registers_for_a_visitor_too(self):
        """Sem service worker registrado na primeira página, não há convite."""
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn("js/pwa.js", html)


class ServiceWorkerTests(TestCase):
    def setUp(self):
        self.source = self.client.get("/sw.js").content.decode()

    def test_service_worker_is_served_from_the_root(self):
        response = self.client.get("/sw.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        # Escopo: servido da raiz, controla o app inteiro.
        self.assertIn("addEventListener", self.source)

    def test_service_worker_is_never_cached(self):
        response = self.client.get("/sw.js")
        self.assertIn("no-store", response["Cache-Control"])

    def test_the_shell_cached_on_install_uses_the_versioned_urls(self):
        """O que entra no cache na instalação tem que ser a mesma URL que a
        página pede — senão o app guarda uma cópia que nunca é usada."""
        versao = assets.version()
        self.assertIn(f"css/app.css?v={versao}", self.source)
        self.assertIn(f"js/pwa.js?v={versao}", self.source)

    def test_versioned_files_are_served_from_the_cache_first(self):
        """É daqui que vem o carregamento instantâneo na segunda abertura.

        Seguro porque o endereço carrega o hash do conteúdo: uma URL versionada
        responde sempre a mesma coisa, então servir do cache não pode servir
        algo diferente do que a página pediu.
        """
        self.assertIn("isVersioned", self.source)
        # A ida à rede fica atrás do cache no ramo final.
        final = self.source.split("if (isAppCode(request) && !isVersioned(request))")[1]
        # O último respondWith do arquivo: o ramo que cai por padrão.
        final = final.split("event.respondWith(")[-1]
        self.assertLess(final.index("caches.match(request)"), final.index("fetch(request)"))

    def test_unversioned_style_and_script_still_revalidate(self):
        """Regressão de 24/08/2026: CSS velho servido junto com HTML novo.

        O service worker entregava qualquer coisa de /static/ do cache antes de
        olhar a rede. Depois de um deploy que muda o layout, isso não é "uma
        versão atrás" — é o app inteiro sem estilo, porque a marcação nova não
        casa com a folha antiga. Hoje o caso normal está resolvido na origem
        (a URL muda com o conteúdo), mas o caminho sem `?v=` não promete nada
        sobre o que serve, e por isso continua indo à rede primeiro.
        """
        self.assertIn("isAppCode", self.source)
        ramo = self.source.split("if (isAppCode(request) && !isVersioned(request))")[1]
        ramo = ramo.split("return;")[0]
        self.assertLess(ramo.index("fetch("), ramo.index("caches.match(request)"))
        # E a ida à rede precisa revalidar, senão o cache HTTP do navegador
        # responde no lugar do servidor e o CSS velho volta pela terceira porta.
        self.assertIn('cache: "no-cache"', ramo)

    def test_the_activation_throws_away_older_builds(self):
        """Cache-first sem poda vira cache que só cresce.

        Numa máquina de desenvolvimento o cache acumulou nove pares de CSS e JS
        — um por build — porque cada `?v=` diferente é um registro novo e nada
        apagava os anteriores. O usuário nunca vê o problema: só o disco dele.
        """
        versao = assets.version()
        self.assertIn(f'const VERSAO = "{versao}"', self.source)

        ativacao = self.source.split('addEventListener("activate"')[1]
        self.assertIn("limpar()", ativacao)

        limpeza = self.source.split("function limpar()")[1].split("\nself.")[0]
        # Apaga gerações antigas do cache inteiro...
        self.assertIn("caches.delete(k)", limpeza)
        # ...e, dentro da geração atual, o que veio de builds anteriores.
        self.assertIn('searchParams.get("v")', limpeza)
        self.assertIn("versao !== VERSAO", limpeza)

    def test_pages_are_never_cached(self):
        """HTML de usuário logado no cache seria mostrar o dia de uma pessoa
        para outra no mesmo aparelho."""
        navegacao = self.source.split('request.mode === "navigate"')[1].split("}")[0]
        self.assertIn("fetch(request)", navegacao)
        self.assertNotIn("caches.match(request)", navegacao)

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
