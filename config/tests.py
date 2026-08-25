"""Testes da configuração de produção.

O que quebra num deploy raramente é a regra de negócio — é a configuração:
estático sem manifesto, host fora da lista, redirecionamento em laço. Nada
disso aparece em desenvolvimento, e todos aparecem para o primeiro visitante.
Estes testes exercitam justamente o que só existe com `DEBUG=False`.
"""
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

RAIZ = Path(settings.BASE_DIR)


class DeployFilesTests(TestCase):
    """Os arquivos que a plataforma procura precisam existir e concordar."""

    def test_the_platform_entrypoints_exist(self):
        for nome in ("Procfile", "render.yaml", "railway.json", "scripts/build.sh"):
            with self.subTest(arquivo=nome):
                self.assertTrue((RAIZ / nome).exists(), f"{nome} não está na raiz")

    def test_every_start_command_points_at_the_same_wsgi(self):
        """Procfile, render.yaml e railway.json não podem divergir."""
        for nome in ("Procfile", "render.yaml", "railway.json"):
            with self.subTest(arquivo=nome):
                conteudo = (RAIZ / nome).read_text(encoding="utf-8")
                self.assertIn("config.wsgi:application", conteudo)
                self.assertIn("gunicorn", conteudo)

    def test_the_build_prepares_static_and_database(self):
        """Faltar um destes passos derruba o site no primeiro pedido."""
        build = (RAIZ / "scripts" / "build.sh").read_text(encoding="utf-8")

        for passo in ("pip install -r requirements.txt", "collectstatic", "migrate"):
            with self.subTest(passo=passo):
                self.assertIn(passo, build)

        # collectstatic ANTES de o site subir: com DEBUG desligado o Django usa
        # o storage com manifesto, e sem manifesto todo {% static %} explode.
        self.assertLess(build.index("collectstatic"), build.index("migrate"))
        # E o build tem que abortar no primeiro erro, senão publica quebrado.
        self.assertIn("set -o errexit", build)

    def test_the_build_seeds_the_catalog(self):
        """Sem seed o cadastro termina numa tela sem alimento e sem exercício."""
        build = (RAIZ / "scripts" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("seed_catalog", build)
        self.assertIn("seed_workouts", build)

    def test_requirements_carry_what_production_needs(self):
        pacotes = (RAIZ / "requirements.txt").read_text(encoding="utf-8").lower()
        for pacote in ("django", "gunicorn", "whitenoise", "psycopg", "django-environ"):
            with self.subTest(pacote=pacote):
                self.assertIn(pacote, pacotes)

    def test_the_env_example_documents_every_variable_the_deploy_needs(self):
        exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
        for variavel in (
            "DJANGO_SECRET_KEY",
            "DJANGO_DEBUG",
            "DJANGO_ALLOWED_HOSTS",
            "DATABASE_URL",
        ):
            with self.subTest(variavel=variavel):
                self.assertIn(variavel, exemplo)

    def test_the_secret_is_never_committed(self):
        """O .env fica de fora do git — é onde mora a chave e a senha do banco."""
        ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", ignorados)


class ProductionBehaviourTests(TestCase):
    """O comportamento que só existe com DEBUG desligado."""

    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["nutriplan.onrender.com"],
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_plain_http_is_redirected_to_https(self):
        resposta = Client(SERVER_NAME="nutriplan.onrender.com").get("/")

        self.assertEqual(resposta.status_code, 301)
        self.assertTrue(resposta["Location"].startswith("https://"))

    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["nutriplan.onrender.com"],
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_the_proxy_header_prevents_a_redirect_loop(self):
        """A plataforma termina o TLS e fala HTTP com o Django.

        Sem `SECURE_PROXY_SSL_HEADER` o app enxerga "http", manda para https,
        recebe o mesmo pedido de volta e o navegador desiste. Foi exatamente o
        que aconteceu num túnel que não enviava o cabeçalho — aqui está travado.
        """
        resposta = Client(SERVER_NAME="nutriplan.onrender.com").get(
            "/", HTTP_X_FORWARDED_PROTO="https"
        )

        self.assertNotEqual(resposta.status_code, 301)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["nutriplan.onrender.com"])
    def test_an_unknown_host_is_refused(self):
        """Cabeçalho Host é entrada do atacante: aceita-se só o que se conhece."""
        resposta = Client(SERVER_NAME="site-de-outra-pessoa.com").get("/")
        self.assertEqual(resposta.status_code, 400)

    def test_static_uses_the_manifest_storage_outside_debug(self):
        """Sem manifesto, o arquivo servido pode não ser o que a página pede.

        A regra é conferida na função, e não em `settings.STORAGES`: o valor
        efetivo é congelado na importação do módulo, então ler dele durante o
        teste (onde o runner já forçou DEBUG=False) diria respeito ao ambiente
        de quem rodou, não à regra.
        """
        from config.settings import staticfiles_backend

        self.assertEqual(
            staticfiles_backend(debug=False),
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )
        self.assertEqual(
            staticfiles_backend(debug=True),
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )

    def test_whitenoise_is_in_front_of_the_request(self):
        """Precisa vir logo depois do middleware de segurança para servir estático."""
        middleware = settings.MIDDLEWARE
        self.assertIn("whitenoise.middleware.WhiteNoiseMiddleware", middleware)
        self.assertEqual(
            middleware.index("whitenoise.middleware.WhiteNoiseMiddleware"),
            middleware.index("django.middleware.security.SecurityMiddleware") + 1,
        )


def semear():
    """O mesmo par de comandos que `scripts/build.sh` roda em cada deploy."""
    call_command("seed_catalog", verbosity=0)
    call_command("seed_workouts", verbosity=0)


class HealthTests(TestCase):
    """O endpoint que responde se a aplicação subiu inteira.

    O caso que ele existe para pegar não é o site fora do ar — esse qualquer um
    percebe. É o site no ar com o banco vazio: tudo responde 200, o cadastro
    funciona, e a pessoa termina o onboarding numa tela sem um alimento sequer.
    """

    def test_a_seeded_install_reports_ok(self):
        """Roda o seed de verdade: é o mesmo comando que o build do Render
        executa, então o teste falha se o seed parar de popular alguma coisa."""
        semear()

        resposta = self.client.get(reverse("health"))

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["status"], "ok")
        self.assertGreater(corpo["catalogo"]["alimentos"], 0)
        self.assertGreater(corpo["catalogo"]["modelos_de_refeicao"], 0)

    def test_retired_food_does_not_inflate_the_count(self):
        """O número tem que responder o que o usuário encontra, não o que a
        tabela guarda. Alimento aposentado continua no banco para o histórico
        não virar buraco — e sumiu da tela, então some da conta."""
        from catalog.models import Food

        semear()
        antes = self.client.get(reverse("health")).json()["catalogo"]["alimentos"]

        alvo = Food.objects.filter(is_active=True).order_by("pk").first()
        alvo.is_active = False
        alvo.save(update_fields=["is_active"])

        depois = self.client.get(reverse("health")).json()["catalogo"]["alimentos"]
        self.assertEqual(depois, antes - 1)

    def test_an_empty_catalog_is_reported_as_unhealthy(self):
        """Sem seed, a plataforma precisa tratar o deploy como falho.

        Responder 200 aqui seria publicar um site que só decepciona quem entra:
        nada quebra, e nada funciona.
        """
        resposta = self.client.get(reverse("health"))

        self.assertEqual(resposta.status_code, 503)
        corpo = resposta.json()
        self.assertEqual(corpo["status"], "catalogo incompleto")
        self.assertIn("alimentos", corpo["faltando"])

    def test_a_database_that_does_not_answer_is_a_failure(self):
        with patch(
            "config.health.connection.ensure_connection",
            side_effect=OperationalError("conexão recusada"),
        ):
            resposta = self.client.get(reverse("health"))

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json()["status"], "sem banco")

    def test_it_answers_without_login(self):
        """A plataforma consulta sem sessão; exigir login viraria um health
        check que responde 302 para sempre e nunca detecta nada."""
        semear()

        resposta = Client().get(reverse("health"))

        self.assertEqual(resposta.status_code, 200)

    def test_it_reveals_nothing_about_people(self):
        semear()

        corpo = self.client.get(reverse("health")).json()

        self.assertEqual(set(corpo), {"status", "catalogo"})
        for chave in corpo["catalogo"]:
            with self.subTest(chave=chave):
                self.assertNotIn("usuario", chave)

    def test_the_platform_health_check_points_here(self):
        """Um healthCheckPath apontando para outra rota reabre o buraco."""
        for nome in ("render.yaml", "railway.json"):
            with self.subTest(arquivo=nome):
                conteudo = (RAIZ / nome).read_text(encoding="utf-8")
                self.assertIn("/saude/", conteudo)


def _luminancia(hexa):
    """Luminância relativa da WCAG, para 0-1."""
    hexa = hexa.lstrip("#")
    canais = []
    for i in (0, 2, 4):
        v = int(hexa[i : i + 2], 16) / 255
        canais.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste(cor, fundo):
    a, b = _luminancia(cor), _luminancia(fundo)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def _tokens(css, escopo):
    """Lê as variáveis de cor de um bloco `:root` (ou do bloco do tema claro)."""
    trecho = css.split(escopo, 1)[1].split("}", 1)[0]
    valores = {}
    for linha in trecho.splitlines():
        linha = linha.strip()
        if linha.startswith("--") and ":" in linha:
            nome, valor = linha.split(":", 1)
            valor = valor.split(";")[0].strip()
            if valor.startswith("#") and len(valor) == 7:
                valores[nome.strip()] = valor
    return valores


class ContrastTests(TestCase):
    """Contraste medido, não julgado a olho.

    O teste recalcula a razão da WCAG a partir dos tokens do CSS em vez de
    comparar com uma cor fixa: assim ele continua valendo quando a paleta
    mudar, e falha exatamente quando alguém escolher um cinza bonito e
    ilegível. O mínimo AA para texto pequeno é 4.5:1.
    """

    MINIMO = 4.5

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def _conferir(self, escopo, rotulo):
        tokens = _tokens(self.css, escopo)
        fundos = [
            tokens[nome]
            for nome in ("--bg", "--surface", "--surface-2", "--surface-3")
            if nome in tokens
        ]
        self.assertTrue(fundos, f"{rotulo}: nenhum fundo encontrado")

        for nome in ("--text", "--text-dim", "--text-mute"):
            cor = tokens.get(nome)
            if not cor:
                continue
            for fundo in fundos:
                with self.subTest(tema=rotulo, texto=nome, fundo=fundo):
                    razao = _contraste(cor, fundo)
                    self.assertGreaterEqual(
                        razao,
                        self.MINIMO,
                        f"{nome} ({cor}) sobre {fundo} dá {razao:.2f}:1",
                    )

    def test_dark_theme_text_is_readable_on_every_surface(self):
        self._conferir(":root {", "escuro")

    def test_light_theme_text_is_readable_on_every_surface(self):
        """O tema claro estava pior que o escuro: 3.33:1 no texto discreto."""
        self._conferir("prefers-color-scheme: light) {\n  :root {", "claro")


class TouchTargetTests(TestCase):
    """44x44 é o mínimo em que o dedo acerta.

    Medido no navegador, em 375px e 320px, o app tinha alvos de 19, 20, 21, 25,
    30, 34, 40 e 43 pixels — sendo o de 21px justamente o botão mais usado da
    tela de dieta. Aqui ficam travadas as regras que corrigiram cada um; a
    medida de verdade continua sendo o navegador, isto é a rede de proteção
    contra alguém baixar um valor de novo sem perceber.
    """

    ALVOS = [
        (".btn {", "min-height: 2.95rem"),
        (".btn--sm {", "min-height: 2.75rem"),
        (".btn--quiet {", "min-height: 2.75rem"),
        (".app-bar__quiet {", "min-height: 2.75rem"),
        (".card__head a {", "min-height: 2.75rem"),
        (".swap-open {", "min-height: 2.75rem"),
        (".shopping__check {", "min-height: 2.75rem"),
        (".set-row__input {", "min-height: 2.75rem"),
        (".install__close {", "height: 2.75rem"),
    ]

    def test_every_interactive_element_reaches_44px(self):
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

        for seletor, regra in self.ALVOS:
            with self.subTest(seletor=seletor):
                # Ancorado no início da linha: sem isso, ".btn {" casaria
                # antes com ".sets .btn {" e o teste leria o bloco errado.
                ancora = "\n" + seletor
                self.assertIn(ancora, css, "seletor sumiu do CSS")
                bloco = css.split(ancora, 1)[1].split("}", 1)[0]
                self.assertIn(regra, bloco, f"{seletor} abaixo de 44px")

    def test_nothing_declares_the_old_43px_height(self):
        """2.7rem = 43px: um pixel a menos, e o dedo sente."""
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        linhas = [
            linha.strip()
            for linha in css.splitlines()
            if "2.7rem" in linha and not linha.strip().startswith(("/*", "*", "//"))
        ]
        self.assertEqual(linhas, [], f"ainda há alvos de 43px: {linhas}")
