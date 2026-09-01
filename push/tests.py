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
        # O vetor entrou com `sizes: any` — ele serve a qualquer tamanho,
        # que é o ponto dele. Os dois rasterizados continuam obrigatórios:
        # nem todo Android usa o SVG do manifesto, e sem eles a instalação
        # fica sem ícone justamente onde o vetor não é entendido.
        self.assertTrue({"192x192", "512x512"} <= {i["sizes"] for i in normais})
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

                if icone["type"] == "image/svg+xml":
                    # O vetor não tem tamanho para conferir. O que se
                    # confere é que ele É um SVG e que declara o `viewBox`,
                    # sem o qual ele não escala e o navegador desenha 100x100.
                    self.assertTrue(dados.lstrip().startswith(b"<svg"))
                    self.assertIn(b"viewBox=", dados)
                    continue

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
        """Cor errada aqui vira uma emenda visível em volta do app escuro.

        A cor é LIDA do `--bg` do CSS, e não escrita aqui. Escrita, este teste
        virava uma terceira cópia do mesmo valor — e foi exatamente o que
        aconteceu: a paleta passou para #0d0f12, as settings ficaram no
        verde-preto antigo, e este teste confirmou a cor velha com toda a
        confiança do mundo.

        Um teste que guarda cópia do valor não verifica nada: ele só concorda
        com quem esqueceu de mudar os dois lugares.
        """
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        raiz = css.split(":root {", 1)[1].split(chr(10) + "}", 1)[0]
        fundo = re.search(r"^\s*--bg:\s*(#[0-9a-f]{6});", raiz, re.M)
        self.assertIsNotNone(fundo, "--bg não é mais um hexadecimal em :root")

        self.assertEqual(self.manifest["theme_color"], fundo.group(1))
        self.assertEqual(self.manifest["background_color"], fundo.group(1))

    def test_the_meta_tag_and_the_manifest_agree(self):
        """Duas cópias do mesmo valor é como uma delas fica para trás. A meta
        do HTML e o manifesto saem da MESMA setting."""
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn(
            f'content="{self.manifest["theme_color"]}" '
            'media="(prefers-color-scheme: dark)"',
            html,
        )

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

    def test_the_invitation_never_depends_on_has_for_its_position(self):
        """A causa raiz do travamento, e a que ninguém veria em teste manual.

        O convite se posicionava com `body:has(.tabbar)`. Onde `:has()` não
        existe — Chrome < 105, Safari < 15.4, WebView Android antiga — a regra
        inteira é DESCARTADA pelo navegador, e o convite desce em cima da barra
        de navegação, cobrindo os quatro atalhos. O app parecia travado.

        Quem sabe se a barra existe é o template, então é o template que conta:
        a classe vem do servidor e não depende de suporte a seletor nenhum.
        """
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        # Nenhuma regra do convite pode voltar a depender de :has().
        for linha in css.splitlines():
            despido = linha.strip()
            if despido.startswith(("/*", "*")):
                continue
            if ":has(" in despido and "install" in despido:
                self.fail(f"o convite voltou a depender de :has(): {despido}")

        self.assertIn("body.tem-tabbar .install", css)

    def test_the_server_says_whether_the_tab_bar_is_there(self):
        anonimo = self.client.get(reverse("accounts:login")).content.decode()
        self.assertNotIn("tem-tabbar", anonimo, "visitante não tem barra inferior")

        User.objects.create_user(email="barra@exemplo.com", password="senha-bem-forte-123")
        self.client.login(email="barra@exemplo.com", password="senha-bem-forte-123")
        logado = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn('class="tem-tabbar"', logado)

    def test_the_invitation_never_wins_the_stacking_over_navigation(self):
        """Rede de segurança para o navegador que eu não previ.

        Se qualquer regra de posicionamento falhar, o pior caso tem que ser um
        convite parcialmente escondido atrás da barra — e não uma barra de
        navegação morta atrás do convite. Errar para o lado que deixa usável.
        """
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        def z(seletor):
            bloco = css.split("\n" + seletor, 1)[1].split("}", 1)[0]
            for linha in bloco.splitlines():
                despido = linha.strip()
                # O comentário logo acima da regra também cita "z-index".
                if despido.startswith(("/*", "*", "//")):
                    continue
                if despido.startswith("z-index"):
                    return int(despido.split(":")[1].strip().rstrip(";"))
            raise AssertionError(f"{seletor} sem z-index")

        self.assertLess(z(".install {"), z(".tabbar {"))

    def test_there_are_four_ways_out_and_all_survive_a_redraw(self):
        """Os fechamentos são delegados ao documento, não presos aos botões.

        Handler preso a um elemento depende de aquele elemento existir no
        instante em que o código roda. No documento, funciona mesmo que o
        cartão seja redesenhado — e um convite que não fecha é o pior defeito
        que este app já teve.
        """
        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('document.addEventListener("click"', js)
        self.assertIn('document.addEventListener("keydown"', js)
        self.assertIn('alvo.closest("[data-install-close]")', js)   # X e "Agora não"
        self.assertIn('!alvo.closest("[data-install]")', js)        # toque fora
        self.assertIn('evento.key === "Escape"', js)                # Esc

        # `closest` só existe em Element: sem a guarda, um clique nascido em nó
        # de texto quebraria o handler e prenderia o convite na tela.
        self.assertIn('typeof alvo.closest !== "function"', js)

    def test_no_dimming_overlay_is_used(self):
        """A cortina escura seria exatamente o bloqueio que o convite não pode
        causar. Toque fora fecha, mas o clique continua chegando ao que está
        embaixo."""
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertNotIn("install__overlay", html)
        self.assertNotIn("install-backdrop", html)

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

    def test_dismissing_is_final_and_survives_a_key_rename(self):
        """Fechou uma vez, não volta mais neste aparelho.

        Houve uma versão com prazo de sete dias, na ideia de que quem fecha na
        primeira visita ainda não sabe se o app presta. A prática desmentiu: um
        convite que reaparece é um convite que a pessoa já respondeu.

        As chaves antigas continuam sendo lidas — trocar o nome da chave não
        pode ressuscitar o convite justamente para quem já disse não.
        """
        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('var CHAVE = "nutriplan_pwa_dismissed"', js)
        self.assertIn('localStorage.setItem(CHAVE, "true")', js)
        self.assertIn("CHAVES_ANTIGAS", js)
        for antiga in ("pwa_prompt_dismissed", "nutriplan:convite-dispensado-em"):
            with self.subTest(chave=antiga):
                self.assertIn(antiga, js)

        # Sem prazo: nada de contagem de dias sobrou no caminho da decisão.
        self.assertNotIn("SETE_DIAS", js)

    def test_the_card_never_steals_a_click_from_the_page(self):
        """No desktop o convite pousa no canto inferior direito, e ali costuma
        haver conteúdo — no onboarding, as próprias opções que a pessoa precisa
        marcar. O cartão não intercepta toque; só os botões dele interceptam."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        cartao = css.split(chr(10) + ".install {", 1)[1].split("}", 1)[0]
        self.assertIn("pointer-events: none", cartao)

        # TODOS os blocos de cada seletor, e não o primeiro.
        #
        # `.install__go` passou a aparecer também na lista de retorno ao toque
        # da seção 10, que fica ANTES no arquivo. Um `split(marca, 1)` pegava
        # aquele bloco — que trata de `transform` e não de `pointer-events` —
        # e afirmava com segurança que a regra do cartão tinha sumido. É a
        # armadilha recorrente desta base: o seletor aparece em mais de um
        # lugar, e ler o primeiro responde a pergunta errada.
        for seletor in (".install__go", ".install__close"):
            with self.subTest(seletor=seletor):
                blocos = [
                    trecho.split("}", 1)[0]
                    for marca in (seletor + ",", seletor + " {")
                    for trecho in css.split(chr(10) + marca)[1:]
                ]
                self.assertTrue(
                    any("pointer-events: auto" in bloco for bloco in blocos),
                    f"{seletor} não recupera o toque em nenhuma das suas regras",
                )

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

    def test_pages_go_to_a_cache_of_their_own(self):
        """HTML de usuário logado carrega nome, peso e dieta.

        Este teste chamava-se "as páginas nunca são guardadas" e afirmava
        exatamente isso — enquanto o código já as guardava havia tempo, num
        cache separado, de propósito. Ele passava por um acidente de fatia: o
        `split("}")[0]` cortava no primeiro fecha-chaves e nunca chegava na
        linha que usa o cache.

        O que protege a privacidade não é não guardar: é guardar em cache
        SEPARADO e apagar esse cache ao sair. Guardar é o que faz o app abrir
        no metrô; apagar é o que impede o próximo dono do aparelho de ler a
        dieta de alguém.
        """
        navegacao = self.source.split('request.mode === "navigate"', 1)[1]
        navegacao = navegacao.split("request.mode", 1)[0]

        # A página do cache vem sempre do cache SEPARADO, e nunca do cache de
        # CSS e ícones, que não é apagado ao sair.
        self.assertIn("CACHE_PAGINAS", navegacao)
        self.assertNotIn("cacheName: CACHE }", navegacao)

    def test_logging_out_takes_the_pages_with_it(self):
        """A outra metade da mesma regra, e ela mora no pwa.js."""
        pwa = (
            Path(settings.BASE_DIR) / "static" / "js" / "pwa.js"
        ).read_text(encoding="utf-8")

        self.assertIn('dataset.autenticado === "0"', pwa)
        self.assertIn('indexOf("-paginas")', pwa)
        self.assertIn("caches.delete", pwa)

    def test_a_slow_network_does_not_hold_the_page_hostage(self):
        """Rede de academia raramente cai — ela demora.

        `fetch` não rejeita enquanto pendura, então rede-primeiro sozinha mostra
        tela branca por dez ou quinze segundos com uma cópia boa da página
        guardada ao lado.
        """
        navegacao = self.source.split('request.mode === "navigate"', 1)[1]
        navegacao = navegacao.split("request.mode", 1)[0]

        self.assertIn("setTimeout", navegacao)
        self.assertIn("PACIENCIA_MS", navegacao)
        # A rede continua correndo depois de o cache ter respondido: é ela que
        # atualiza o cache para a próxima abertura.
        self.assertIn("waitUntil", navegacao)

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


class FilaOfflineIndexedDBTests(TestCase):
    """Os dois lados da fila offline precisam concordar sobre o banco.

    `static/js/fila.js` (a página) e `templates/pwa/sw.js` (o service worker)
    abrem o MESMO IndexedDB. Isso já custou caro: o service worker abria
    `nutriplan-fila` na versão 1 SEM `onupgradeneeded`, e quando ele chegava
    primeiro — o que acontece num evento `sync` — o navegador criava o banco
    com ZERO object stores, porque não havia handler para criar nenhuma.

    A partir dali o banco ficava envenenado para sempre. `fila.js` abria na
    versão 1, encontrava um banco v1 existente, seu `onupgradeneeded` nunca
    disparava, e toda marcação de refeição, água ou carga feita sem rede morria
    com

        NotFoundError: One of the specified object stores was not found

    A versão nunca subia, então nada se recuperava sozinho — e o registro
    offline sumia sem ninguém ver.
    """

    PAGINA = Path(settings.BASE_DIR) / "static" / "js" / "fila.js"
    WORKER = Path(settings.BASE_DIR) / "templates" / "pwa" / "sw.js"

    def _constantes(self, texto, nomes):
        achados = {}
        for nome in nomes:
            m = re.search(
                r'\b%s\s*=\s*(?:"([^"]+)"|(\d+))' % nome, texto
            )
            if m:
                achados[nome] = m.group(1) if m.group(1) else m.group(2)
        return achados

    def setUp(self):
        self.pagina = self.PAGINA.read_text(encoding="utf-8")
        self.worker = self.WORKER.read_text(encoding="utf-8")

    def test_os_dois_lados_usam_o_mesmo_banco_e_a_mesma_loja(self):
        p = self._constantes(self.pagina, ["BANCO", "LOJA"])
        w = self._constantes(self.worker, ["FILA_BANCO", "FILA_LOJA"])

        self.assertEqual(p.get("BANCO"), w.get("FILA_BANCO"))
        self.assertEqual(p.get("LOJA"), w.get("FILA_LOJA"))

    def test_os_dois_lados_declaram_a_mesma_versao(self):
        """Divergir aqui faz o lado atrasado levar `VersionError` e parar.

        E parar em silêncio: quem ficou para trás não consegue abrir o banco,
        a fila não drena, e a pessoa continua achando que registrou.
        """
        p = self._constantes(self.pagina, ["VERSAO"])
        w = self._constantes(self.worker, ["FILA_VERSAO"])

        self.assertIsNotNone(p.get("VERSAO"), "fila.js precisa declarar VERSAO")
        self.assertIsNotNone(
            w.get("FILA_VERSAO"), "sw.js precisa declarar FILA_VERSAO"
        )
        self.assertEqual(p["VERSAO"], w["FILA_VERSAO"])

    def test_a_versao_passou_de_1_para_migrar_bancos_ja_envenenados(self):
        """Só subir a versão faz o `onupgradeneeded` rodar em quem já instalou.

        Quem usa o app hoje pode ter o banco v1 sem a store. Manter a versão em
        1 deixaria essas pessoas quebradas para sempre — e a alternativa que
        NÃO se aceita aqui é `deleteDatabase()`, que jogaria fora o que a
        pessoa registrou offline e ainda não foi enviado.
        """
        p = self._constantes(self.pagina, ["VERSAO"])
        self.assertGreaterEqual(int(p["VERSAO"]), 2)

    def test_o_service_worker_cria_a_store_ao_abrir(self):
        """Sem isto, ele volta a criar um banco vazio quando chegar primeiro."""
        trecho = self.worker.split("function abrirFila", 1)[1].split("\n}", 1)[0]

        self.assertIn("onupgradeneeded", trecho)
        self.assertIn("createObjectStore", trecho)

    def test_a_pagina_cria_a_store_ao_abrir(self):
        trecho = self.pagina.split("function abrir(", 1)[1].split("\n  }", 1)[0]

        self.assertIn("onupgradeneeded", trecho)
        self.assertIn("createObjectStore", trecho)

    def test_ninguem_apaga_o_banco_para_se_livrar_do_problema(self):
        """`deleteDatabase()` descartaria registro offline não enviado.

        É a correção tentadora e errada: resolve o erro no console e perde a
        água que a pessoa registrou no metrô. A migração por versão preserva
        as operações pendentes.
        """
        # `indexedDB.deleteDatabase`, e não a palavra solta: os dois arquivos
        # CITAM `deleteDatabase()` em comentário, explicando por que a correção
        # não foi essa. Procurar a palavra reprovaria a própria documentação da
        # decisão — que é o oposto do que este teste quer proteger.
        for texto, nome in ((self.pagina, "fila.js"), (self.worker, "sw.js")):
            self.assertNotRegex(texto, r"indexedDB\s*\.\s*deleteDatabase", nome)
