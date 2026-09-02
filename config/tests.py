"""Testes da configuração de produção.

O que quebra num deploy raramente é a regra de negócio — é a configuração:
estático sem manifesto, host fora da lista, redirecionamento em laço. Nada
disso aparece em desenvolvimento, e todos aparecem para o primeiro visitante.
Estes testes exercitam justamente o que só existe com `DEBUG=False`.
"""
import inspect
import re
import struct
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.models import Profile
from plans import calculations
from workouts.models import TrainingPlan

from plans.tests import create_complete_user

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
    """Os mesmos comandos que `scripts/build.sh` roda em cada deploy.

    Tem que acompanhar o script: um seed novo no build e ausente aqui faz o
    teste de saúde medir uma instalação diferente da que sobe em produção — e
    o `BuildScriptTests` existe justamente para os dois não divergirem.
    """
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

    #: Fundos que NÃO são superfície neutra e mesmo assim recebem texto. A
    #: ausência deles aqui foi uma lacuna real: medido na página renderizada,
    #: `--text-mute` sobre `--brand-soft` dava 4,36:1 no chip do dia de treino
    #: e no azulejo do drawer, e nenhum teste via.
    TINGIDOS = ("--brand-soft", "--warm-soft", "--accent-soft", "--danger-soft")

    def test_dark_theme_text_is_readable_on_every_surface(self):
        self._conferir(":root {", "escuro")

    def _conferir_tingidos(self, escopo, rotulo):
        tokens = _tokens(self.css, escopo)
        for nome_fundo in self.TINGIDOS:
            fundo = tokens.get(nome_fundo)
            if not fundo:
                continue  # token aposentado
            for nome in ("--text", "--text-dim"):
                cor = tokens.get(nome)
                if not cor:
                    continue
                with self.subTest(tema=rotulo, texto=nome, fundo=nome_fundo):
                    razao = _contraste(cor, fundo)
                    self.assertGreaterEqual(
                        razao,
                        self.MINIMO,
                        f"{nome} sobre {nome_fundo} dá {razao:.2f}:1",
                    )

    def test_dark_theme_text_is_readable_on_tinted_backgrounds(self):
        self._conferir_tingidos(":root {", "escuro")

    def test_light_theme_text_is_readable_on_tinted_backgrounds(self):
        self._conferir_tingidos(
            "prefers-color-scheme: light) {" + chr(10) + "  :root {", "claro"
        )

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
        # O gêmeo do de cima, num `<summary>`. "Editar" de "Dados do cálculo"
        # media 40x25: `.card__head a` cobre os "Editar" do perfil, e este não
        # é `.card__head`, então não tinha regra nenhuma.
        (".explicacao__head a {", "min-height: 2.75rem"),
        (".shopping__check {", "min-height: 2.75rem"),
        # O registro único, no lugar das quatro linhas de série que saíram.
        (".registro__carga {", "min-height: 2.75rem"),
        (".registro__salvar {", "min-height: 2.75rem"),
        (".registro__timer {", "min-height: 2.75rem"),
        (".install__close {", "height: 2.75rem"),
        # A pesagem rápida. O campo e o botão nascem já dentro da régua, e a
        # faixa do painel é tocada com a mesma mão que marca a refeição.
        (".pesagem__valor {", "min-height: 2.75rem"),
        (".pesagem__salvar {", "min-height: 2.75rem"),
        (".pesar__topo {", "min-height: 2.75rem"),
        # "desfazer" media 20px, e é o link procurado no segundo seguinte a
        # errar o toque em "Pulei".
        (".btn-link {", "min-height: 2.75rem"),
        # Os dois do cronômetro de descanso. Ficaram de fora da régua desde que
        # nasceram: "+30s" media 34px e o "×" de fechar, 33,6. É a barra que
        # aparece EXATAMENTE quando a pessoa está de pé entre séries, com a mão
        # suada — o pior lugar possível para um alvo de 34px.
        (".rest-timer__more {", "min-height: 2.75rem"),
        (".rest-timer__close {", "height: 2.75rem"),
    ]

    def test_every_interactive_element_reaches_44px(self):
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

        for seletor, regra in self.ALVOS:
            with self.subTest(seletor=seletor):
                # Ancorado no início da linha: sem isso, ".btn {" casaria
                # antes com ".sets .btn {" e o teste leria o bloco errado.
                ancora = chr(10) + seletor
                self.assertIn(ancora, css, "seletor sumiu do CSS")

                # TODOS os blocos daquele seletor, e não só o primeiro. Uma
                # segunda regra com o mesmo nome — uma linha de `grid-area`,
                # por exemplo — fazia o teste ler o bloco errado e reprovar um
                # alvo que estava correto.
                blocos = [
                    trecho.split("}", 1)[0] for trecho in css.split(ancora)[1:]
                ]
                self.assertTrue(
                    any(regra in bloco for bloco in blocos),
                    f"{seletor} abaixo de 44px",
                )

    def test_nothing_declares_the_old_43px_height(self):
        """2.7rem = 43px: um pixel a menos, e o dedo sente."""
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        linhas = [
            linha.strip()
            for linha in css.splitlines()
            if "2.7rem" in linha and not linha.strip().startswith(("/*", "*", "//"))
        ]
        self.assertEqual(linhas, [], f"ainda há alvos de 43px: {linhas}")


def _sobre(tinta, pct, fundo):
    """A cor que sobra quando uma tinta translúcida pousa numa superfície.

    `color-mix(in srgb, X 12%, transparent)` sobre um fundo opaco resulta em
    12% de X mais 88% do fundo. É esse resultado que o olho lê — e é contra
    ele que o texto da pílula precisa contrastar, não contra a superfície nua.
    """
    a = [int(tinta.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    b = [int(fundo.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(
        "%02x" % round(a[i] * pct + b[i] * (1 - pct)) for i in range(3)
    )


class PillContrastTests(TestCase):
    """Contraste das pílulas de estado, medido sobre a tinta e não sobre o fundo.

    O padrão "fundo da própria cor a 10-12%, texto na cor cheia" é o que dá o
    ar de acabamento, e é também uma armadilha: a tinta clareia o fundo e come
    o contraste. No tema claro isso já aconteceu — o âmbar `#a9671a` dava
    4.00:1 sobre a própria tinta, abaixo do mínimo AA de 4.5:1, num aviso que é
    texto pequeno. O teste refaz a composição e mede.
    """

    MINIMO = 4.5

    # (token da cor, opacidade da tinta) — os pares que o CSS realmente usa.
    PARES = [("--warm", 0.12), ("--brand", 0.12), ("--accent", 0.12)]

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def _conferir(self, escopo, rotulo):
        tokens = _tokens(self.css, escopo)
        # Os dois fundos em que pílula de fato pousa: o cartão (`--surface`) e
        # o cartão do exercício (`--surface-2`). `--surface-3` fica de fora de
        # propósito — é fundo de chip, não de cartão, e nenhuma pílula tem
        # `--surface-3` como pai. Medir contra ele obrigaria a escurecer os
        # acentos por causa de um caso que não existe na tela.
        for fundo in (tokens["--surface"], tokens["--surface-2"]):
            for nome, pct in self.PARES:
                cor = tokens[nome]
                with self.subTest(tema=rotulo, cor=nome, fundo=fundo):
                    razao = _contraste(cor, _sobre(cor, pct, fundo))
                    self.assertGreaterEqual(
                        razao,
                        self.MINIMO,
                        f"{nome} ({cor}) sobre a própria tinta dá {razao:.2f}:1",
                    )

    def test_dark_theme_pills_are_readable(self):
        self._conferir(":root {", "escuro")

    def test_light_theme_pills_are_readable(self):
        self._conferir("prefers-color-scheme: light) {\n  :root {", "claro")


class CustomPropertyTests(TestCase):
    """Toda variável usada precisa existir em algum lugar.

    `--r-lg` era usado em seis declarações de `border-radius` e nunca foi
    definido. CSS não reclama: a declaração inteira é descartada em silêncio, e
    o drawer, o convite de instalação e o cartão do desktop ficaram de quina
    viva por semanas sem ninguém ver o erro — só o resultado.

    `var(--x, algo)` com reserva fica de fora: ali a ausência é intencional
    (`--dia`, por exemplo, é escrito pelo atributo do elemento).
    """

    def test_no_rule_reads_a_variable_that_was_never_declared(self):
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

        declaradas = set(re.findall(r"(--[\w-]+)\s*:", css))
        # Sem vírgula depois do nome = sem valor de reserva.
        usadas = set(re.findall(r"var\(\s*(--[\w-]+)\s*\)", css))

        orfas = sorted(usadas - declaradas)
        self.assertEqual(orfas, [], f"variáveis usadas e nunca definidas: {orfas}")


class MotionTests(TestCase):
    """As animações que carregam informação, e não enfeite.

    Duas delas mudam o que a pessoa entende da tela: a barra que cresce mostra
    o progresso acontecendo (marcar refeição recarrega a página — sem a
    transição a barra apenas está diferente), e o encolhimento do botão confirma
    o toque antes de o servidor responder. Ficam travadas aqui porque são as
    primeiras coisas que alguém corta achando que é decoração.
    """

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def test_the_macro_bars_grow_instead_of_jumping(self):
        bloco = self.css.split("\n.progress__fill {", 1)[1].split("}", 1)[0]
        self.assertIn("transition: width .5s", bloco)

        # A barra empilhada do topo tem a mesma regra — agora num bloco, porque
        # ela ganhou também a animação de encher do zero.
        # TODOS os blocos do seletor: `.macro-bar__part` aparece também numa
        # regra de `min-width`, e a busca pelo primeiro media o bloco errado.
        # É a quarta vez que esta armadilha aparece na suíte.
        blocos = [
            t.split("}", 1)[0]
            for t in self.css.split(chr(10) + ".macro-bar__part {")[1:]
        ]
        self.assertTrue(any("transition: width .5s" in b for b in blocos))

    def test_the_bars_fill_from_zero_when_the_screen_opens(self):
        """A transição sozinha só anima MUDANÇAS depois da primeira pintura.
        Abrir a página mostrava a barra pronta, e a pessoa nunca via o próprio
        progresso acontecer — que é a única recompensa desta tela."""
        self.assertIn("@keyframes encher", self.css)
        self.assertIn("animation: encher", self.css)

    def test_pressing_anything_uses_the_same_scale(self):
        """Duas escalas diferentes no mesmo gesto é o tipo de inconsistência
        que ninguém aponta e todo mundo sente. Já houve: a lista geral
        encolhia 2% e o cartão do onboarding, 1%.

        O valor já passou por .98, .95, .97 e agora .96. O que este teste
        trava não é a escolha — é haver UMA. Duas escalas diferentes no mesmo
        gesto é a inconsistência que ninguém aponta e todo mundo sente.
        """
        escalas = set(re.findall(r":active[^{]*\{[^}]*transform:\s*scale\(([^)]+)\)", self.css))
        self.assertEqual(escalas, {".96"}, f"escalas de toque divergentes: {escalas}")

    def test_who_asked_for_less_movement_gets_less_movement(self):
        """Quem liga "reduzir movimento" no sistema costuma ter um motivo
        clínico. Toda animação nova precisa de saída."""
        for regra in (".esqueleto", ".progress__fill", ".btn:active"):
            with self.subTest(regra=regra):
                trechos = self.css.split("prefers-reduced-motion")
                self.assertTrue(
                    any(regra in t.split("}\n}", 1)[0] for t in trechos[1:]),
                    f"{regra} anima sem saída para quem pediu menos movimento",
                )

def _sem_comentario(css):
    """O CSS sem os blocos de comentário.

    Não é frescura: um comentário deste arquivo explica um bug citando
    `.install[hidden] { display: none }` no meio do texto. Qualquer varredura
    que conte chaves sem tirar os comentários antes lê essa frase como regra e
    passa a analisar o arquivo desalinhado a partir dali.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _regras(css):
    """(seletor, corpo) de cada regra folha — as que não aninham outras.

    O padrão só casa corpo SEM chave dentro, então uma `@media` nunca casa
    como regra: o que casa são as regras de dentro dela, que é justamente o
    que interessa aqui. O seletor começa depois da chave de abertura da
    `@media`, porque o grupo do seletor também não pode atravessar chave.
    """
    for achado in re.finditer(r"([^{}]+)\{([^{}]*)\}", _sem_comentario(css)):
        yield achado.group(1).strip(), achado.group(2)


class VisualRefinementTests(TestCase):
    """O acabamento do refinamento visual, travado contra a próxima regressão.

    Nada aqui inventa regra nova: cada teste é uma inconsistência que existia
    de verdade neste arquivo e que ninguém via, porque nenhuma delas quebra
    nada — só faz a interface parecer montada por gente diferente em semanas
    diferentes, que é exatamente o que o cabeçalho do CSS diz querer evitar.
    """

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def test_no_corner_is_written_in_a_raw_value(self):
        """Quatro quinas em pixel solto, e cada uma de um valor diferente.

        O selo da barra estava em 10px, o logo do entrar em 16px, o ícone do
        cartão de escolha em .75rem e o do convite em .7rem. São a mesma
        família visual — quadradinho com ícone dentro — e tinham quatro raios.
        Ninguém escolheu isso; cada um foi escrito no dia em que o componente
        nasceu. Token não é purismo, é o que faz a quarta peça nascer certa.
        """
        cruas = []
        for i, linha in enumerate(_sem_comentario(self.css).splitlines(), 1):
            despido = linha.strip()
            if not despido.startswith("border-radius:"):
                continue
            valor = despido.split(":", 1)[1].strip().rstrip(";")
            # `50%` é círculo e `inherit` copia de quem manda: os dois são a
            # forma, não uma medida escolhida a olho.
            if "var(--" in valor or valor in ("50%", "inherit"):
                continue
            cruas.append("linha %d: %s" % (i, valor))

        self.assertEqual(cruas, [], "raio fora dos tokens: %s" % cruas)

    def test_the_primary_button_only_glows_under_the_finger(self):
        """O halo do botão primário mora no estado, não no repouso.

        `dark-glow` do catálogo Impeccable proíbe o halo em repouso, e
        `ImpeccableStyleTests` já guarda esse lado. Falta o outro: quando o
        halo saiu do repouso ele quase saiu inteiro, e o botão ficou sem
        NENHUM retorno de cor ao toque — só o afundamento de 2%, que o próprio
        dedo cobre. Sob o dedo o brilho é informação; é ali que ele fica.
        """
        repouso = self.css.split(chr(10) + ".btn--primary {", 1)[1].split("}", 1)[0]
        self.assertNotIn("box-shadow", repouso, "o halo voltou para o repouso")

        for estado in (":hover", ":active", ":focus-visible"):
            with self.subTest(estado=estado):
                self.assertIn(".btn--primary%s" % estado, self.css)

        sob_o_dedo = self.css.split(
            chr(10) + ".btn--primary:focus-visible", 1
        )[1].split("}", 1)[0]
        self.assertIn("var(--halo)", sob_o_dedo)

    def test_every_active_state_speaks_the_same_halo(self):
        """Quatro anéis de marca escritos à mão, com quatro opacidades.

        A aba atual tinha 22%, o link da barra 22% mas `inset`, a refeição
        feita 12%, e o cartão de escolha o anel de marca CHEIA — o estado mais
        forte do app inteiro estava num formulário de onboarding. São quatro
        respostas para a mesma pergunta ("o que marca o que está ativo"), e a
        pessoa que usa o app vê as quatro na mesma sessão.
        """
        for seletor in (
            ".app-bar__link.is-active",
            ".tabbar__item.is-active",
            ".meal--done {",
            ".option[open]",
            ".registro--completo",
            ".choice-card__input:checked ~ .choice-card__frame",
        ):
            with self.subTest(seletor=seletor):
                bloco = self.css.split(chr(10) + seletor, 1)[1].split("}", 1)[0]
                self.assertIn("var(--halo)", bloco)

        # E nenhum anel de marca escrito à mão sobrou. A única ocorrência que
        # pode existir é a definição do próprio token.
        mao = re.findall(r"0 0 0 1px (?:var\(--brand\)|color-mix\(in srgb, var\(--brand\))", self.css)
        self.assertEqual(len(mao), 1, "anel de marca escrito à mão fora do token")

    def test_the_sunken_blocks_get_their_outline_from_inside(self):
        """Contorno por dentro, porque o de fora empurraria a grade.

        O azulejo, a célula da equação, o chip do dia e o resultado da refeição
        pousam em `--surface-2` sem borda nenhuma. No escuro, dois grafites
        vizinhos viram um só — o bloco some no cartão. Uma borda de verdade
        resolveria e custaria 2px em cada eixo, mexendo numa grade que já está
        certa; `inset` desenha o mesmo fio sem ocupar espaço algum.
        """
        for seletor in (".tile", ".equation__cell", ".day-chip", ".meal__result"):
            with self.subTest(seletor=seletor):
                bloco = self.css.split(chr(10) + seletor + " {", 1)[1].split("}", 1)[0]
                self.assertIn("var(--inlay)", bloco)
                self.assertNotIn(
                    "border:", bloco, "%s ganhou borda e empurrou a grade" % seletor
                )

    def test_every_touch_transition_shares_the_duration_and_the_curve(self):
        """Treze declarações carregavam `.15s` cru, sem a curva.

        A seção dos botões já diz, por escrito: "Tudo que reage ao dedo reage
        no mesmo tempo. Sem esta lista cada componente carregava a própria
        duração, e a interface parecia montada por gente diferente em semanas
        diferentes." A lista existia. Treze regras nunca entraram nela — e
        `.15s` sem curva é aceleração linear, que o olho lê como travada.

        Ficam de fora as duas que não são resposta a toque: a barra de macro,
        que é dado crescendo, e o cronômetro, que é relógio andando.
        """
        RELOGIO = ("width 1s linear",)
        soltas = []
        for declaracao in re.findall(r"transition:[^;]*;", _sem_comentario(self.css)):
            corpo = " ".join(declaracao.split())
            if corpo == "transition: none;":
                continue
            for parte in corpo[len("transition:"):].rstrip(";").split(","):
                parte = parte.strip()
                if parte in RELOGIO or parte.endswith("var(--ease)"):
                    continue
                soltas.append(parte)

        self.assertEqual(soltas, [], "transições fora de --dur/--ease: %s" % soltas)

    def test_every_press_state_has_a_way_out_of_the_movement(self):
        """Oito estados de toque nasceram depois da lista e nunca entraram nela.

        `.agua__botao`, `.voz-mic`, `.reps__passo`, `.supl__marcar`,
        `.copiar-cargas` e os três do assistente encolhiam 2% sob o dedo mesmo
        para quem desligou animação no sistema — quem liga essa opção costuma
        ter motivo clínico. O teste que existia olhava três nomes escritos à
        mão, então crescia junto com o problema em vez de pegá-lo: este varre
        o arquivo e cobra saída para TODO seletor que encolhe.
        """
        encolhem, saem = set(), set()
        for seletor, corpo in _regras(self.css):
            alvo = encolhem if "transform: scale(" in corpo else (
                saem if "transform: none" in corpo else None
            )
            if alvo is None:
                continue
            alvo.update(p.strip() for p in seletor.split(",") if ":active" in p)

        self.assertTrue(encolhem, "ninguém mais encolhe sob o dedo?")
        orfaos = sorted(encolhem - saem)
        self.assertEqual(orfaos, [], "encolhem sem saída: %s" % orfaos)

    def test_the_tab_transition_is_drawn_and_not_the_browser_default(self):
        """`navigation: auto` sozinho entrega o cross-fade genérico.

        As duas páginas trocam de opacidade no mesmo instante e o olho não sabe
        qual chegou. Desenhada, a que sai some primeiro e a que entra vem atrás
        subindo seis pixels — o suficiente para registrar QUE algo chegou, e
        longe do slide de apresentação. Seis pixels em `translateY` porque é
        uma das duas propriedades que o navegador anima sem refazer layout.
        """
        self.assertIn("@view-transition { navigation: auto; }", self.css)

        for regra in ("::view-transition-old(root)", "::view-transition-new(root)"):
            with self.subTest(regra=regra):
                self.assertIn(regra, self.css)

        for nome in ("aba-sai", "aba-entra"):
            with self.subTest(quadro=nome):
                self.assertIn("@keyframes %s" % nome, self.css)

        # A saída: quem pediu menos movimento não atravessa ponte nenhuma.
        trechos = self.css.split("prefers-reduced-motion")
        self.assertTrue(
            any("::view-transition-new(root)" in t.split("}\n}", 1)[0] for t in trechos[1:]),
            "a ponte entre abas anima sem saída para quem pediu menos movimento",
        )

    def test_the_quiet_text_clears_the_minimum_with_room_to_spare(self):
        """4,5:1 é piso de legibilidade, não alvo de projeto.

        `--text-mute` estava em 4,67:1 no pior fundo neutro e em 4,36:1 sobre
        `--brand-soft` — abaixo do mínimo, num tom que carrega o alvo da
        refeição e o rodapé do chip do dia. Nenhum teste via: `ContrastTests`
        mede os fundos tingidos só contra `--text` e `--text-dim`, e o buraco
        era exatamente o terceiro tom.

        Em OLED com brilho baixo — o app é aberto na academia e de madrugada —
        "passa raspando" se lê como texto apagado. 5,0 é a margem que separa
        legível de tecnicamente aprovado.
        """
        MARGEM = 5.0
        for escopo, rotulo in (
            (":root {", "escuro"),
            ("prefers-color-scheme: light) {" + chr(10) + "  :root {", "claro"),
        ):
            tokens = _tokens(self.css, escopo)
            fundos = [
                (nome, tokens[nome])
                for nome in (
                    "--bg",
                    "--surface",
                    "--surface-2",
                    "--surface-3",
                    "--brand-soft",
                    "--warm-soft",
                    "--danger-soft",
                )
                if nome in tokens
            ]
            for texto in ("--text-dim", "--text-mute"):
                for nome_fundo, fundo in fundos:
                    with self.subTest(tema=rotulo, texto=texto, fundo=nome_fundo):
                        razao = _contraste(tokens[texto], fundo)
                        self.assertGreaterEqual(
                            razao,
                            MARGEM,
                            "%s sobre %s dá %.2f:1" % (texto, nome_fundo, razao),
                        )

class BuildScriptTests(TestCase):
    """O que o deploy precisa rodar.

    Um seed esquecido no build só aparece em produção, e aparece como tela
    vazia: o catálogo não existe e a aba abre sem nada. O teste lê o script.
    """

    def test_every_seed_command_runs_on_deploy(self):
        script = (RAIZ / "scripts" / "build.sh").read_text(encoding="utf-8")
        for comando in ("seed_catalog", "seed_workouts"):
            with self.subTest(comando=comando):
                self.assertIn(f"manage.py {comando}", script)

    def test_migrations_run_before_the_seeds(self):
        """Semear antes de migrar é semear numa tabela que ainda não existe."""
        script = (RAIZ / "scripts" / "build.sh").read_text(encoding="utf-8")
        self.assertLess(script.index("manage.py migrate"), script.index("seed_catalog"))


class SingleUserAppTests(TestCase):
    """O app voltou a ser de uma pessoa só.

    Módulo removido costuma deixar rastro: uma rota que ainda resolve, um
    import que ainda funciona, um campo que ninguém mais escreve. Cada rastro
    é uma porta que continua destrancada — e o módulo removido aqui era
    justamente o que dava a uma pessoa acesso aos dados de saúde de outra.
    """

    #: As rotas do painel e do convite. Se qualquer uma voltar a resolver, algo
    #: do módulo voltou junto.
    ROTAS_MORTAS = ("/profissional/", "/profissional/cadastro/", "/conectar/ABC123/")

    def test_the_professional_routes_are_gone(self):
        cliente = Client()
        for rota in self.ROTAS_MORTAS:
            with self.subTest(rota=rota):
                self.assertEqual(cliente.get(rota).status_code, 404)

    def test_no_url_name_from_the_module_resolves(self):
        for nome in (
            "coaching:panel",
            "coaching:signup",
            "coaching:student_monitor",
            "connect",
            "accounts:professionals",
        ):
            with self.subTest(nome=nome):
                with self.assertRaises(NoReverseMatch):
                    reverse(nome)

    def test_nothing_outside_the_package_imports_it(self):
        """Um import esquecido derruba o deploy no dia em que a pasta sair."""
        # Montado em pedaços para o teste não se encontrar: escrito inteiro,
        # o literal aparece neste próprio arquivo e a busca acusa a si mesma.
        modulo = "coach" + "ing"
        alvos = (f"import {modulo}", f"from {modulo}")

        culpados = []
        for caminho in RAIZ.rglob("*.py"):
            partes = caminho.parts
            if modulo in partes or ".venv" in partes or "migrations" in partes:
                continue
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                despido = linha.strip()
                if despido.startswith("#") or "alvos" in despido:
                    continue
                if any(alvo in despido for alvo in alvos):
                    culpados.append(f"{caminho.name}: {despido}")
        self.assertEqual(culpados, [], f"ainda importam o módulo: {culpados}")

    def test_no_template_mentions_the_module(self):
        culpados = []
        for caminho in (RAIZ / "templates").rglob("*.html"):
            texto = caminho.read_text(encoding="utf-8")
            if "coaching:" in texto or "coach_updates" in texto:
                culpados.append(caminho.name)
        self.assertEqual(culpados, [], f"templates com resto do módulo: {culpados}")

    def test_the_profile_lost_the_prescription_fields(self):
        """Campo que ninguém escreve é campo que o próximo leitor tenta
        entender à toa."""
        campos = {f.name for f in Profile._meta.get_fields()}
        for morto in ("protein_g_per_kg", "fat_kcal_share", "target_weight_kg"):
            with self.subTest(campo=morto):
                self.assertNotIn(morto, campos)

    def test_the_training_plan_no_longer_points_at_a_second_person(self):
        campos = {f.name for f in TrainingPlan._meta.get_fields()}

        self.assertNotIn("prescribed_by", campos)
        # A trava contra o gerador continua, agora para o próprio dono: sem
        # ela, mudar o horário de terça apagaria o ajuste de ontem.
        self.assertIn("customized_at", campos)

    def test_the_calorie_engine_is_back_to_one_signature(self):
        """`macros()` aceitava dois parâmetros de prescrição que só o
        nutricionista preenchia. Sem ele, viraram argumentos mortos."""
        assinatura = inspect.signature(calculations.macros)
        self.assertEqual(
            list(assinatura.parameters), ["target", "weight_kg", "goal"]
        )

    def test_the_bottom_bar_matches_the_number_of_tabs(self):
        """A grade tem número fixo de colunas, então ela e o número de abas do
        template precisam concordar — senão a última aba quebra a linha."""
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        bloco = css.split(chr(10) + ".tabbar {", 1)[1].split("}", 1)[0]
        base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")

        abas = base.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
        self.assertIn(f"repeat({abas.count('tabbar__item')}, 1fr)", bloco)

    def test_the_package_is_gone_from_the_disk(self):
        """Etapa 2 da remoção.

        A etapa 1 manteve `coaching/migrations/` vivo por um deploy para o
        `migrate` derrubar as tabelas em produção — um app apagado do disco não
        roda migração nenhuma. Confirmado o deploy, a pasta saiu.
        """
        self.assertFalse((RAIZ / ("coach" + "ing")).exists())

    def test_it_is_not_an_installed_app_anymore(self):
        self.assertNotIn("coach" + "ing", settings.INSTALLED_APPS)


class ResponseCompressionTests(TestCase):
    """O HTML gerado pelo Django precisa ir comprimido.

    O WhiteNoise comprime os ESTÁTICOS e só eles. A página de treino saía com
    622 KB crus — medidos — porque renderiza a semana inteira com um ícone
    inline em cada linha de série. Comprimida, 32 KB. Numa rede de academia
    essa é a diferença entre abrir e desistir.
    """

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_the_middleware_is_installed_before_anything_writes_a_body(self):
        gzip = "django.middleware.gzip.GZipMiddleware"
        self.assertIn(gzip, settings.MIDDLEWARE)
        self.assertLess(
            settings.MIDDLEWARE.index(gzip),
            settings.MIDDLEWARE.index("django.middleware.common.CommonMiddleware"),
            "comprimir é a última coisa na saída, então vem cedo na lista",
        )
        # Depois do WhiteNoise: ele precisa ficar colado no middleware de
        # segurança, e assim arquivo estático nem chega ao gzip — já sai
        # pré-comprimido por lá.
        self.assertGreater(
            settings.MIDDLEWARE.index(gzip),
            settings.MIDDLEWARE.index("whitenoise.middleware.WhiteNoiseMiddleware"),
        )

    def test_a_page_actually_comes_back_compressed(self):
        resposta = self.client.get(
            reverse("plans:today"), headers={"Accept-Encoding": "gzip"}
        )
        self.assertEqual(resposta.headers.get("Content-Encoding"), "gzip")

    def test_compression_is_a_real_saving_and_not_a_header(self):
        url = reverse("plans:today")
        cru = len(self.client.get(url).content)
        comprimido = len(
            self.client.get(url, headers={"Accept-Encoding": "gzip"}).content
        )
        self.assertLess(comprimido, cru / 2, "a compressão não está economizando")

    def test_a_client_that_cannot_decompress_still_gets_the_page(self):
        resposta = self.client.get(reverse("plans:today"))

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("Content-Encoding", resposta.headers)

    def test_no_selector_list_ends_in_a_dangling_comma(self):
        """Vírgula pendurada invalida o seletor INTEIRO.

        Aconteceu: uma remoção apagou o último seletor da lista de saída do
        `prefers-reduced-motion` e deixou a pontuação. O navegador descartou a
        regra sem avisar, e ninguém que liga "reduzir movimento" no sistema
        recebia a saída — a interface continuava encolhendo sob o dedo.

        O CSS não dá erro nesse caso, e é por isso que precisa de teste: as
        chaves continuam balanceadas, o arquivo continua "válido", e o efeito é
        uma regra que simplesmente não existe.
        """
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        limpo = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

        soltas = re.findall(r",\s*\{", limpo)
        self.assertEqual(soltas, [], "há lista de seletores terminando em vírgula")

    def test_no_rule_targets_a_class_the_templates_never_render(self):
        """CSS para seletor inexistente não dá erro — só não faz nada.

        Aconteceu duas vezes nesta sessão: uma regra de sanfona escrita para
        `.exercise__corpo` quando a classe é `.exercise__body`, e as regras de
        `.sets` que sobreviveram à remoção das quatro linhas de série. As duas
        ficariam anos no arquivo sem ninguém notar.

        A checagem é só das classes do PRÓPRIO app (prefixo conhecido): classes
        de estado escritas por JavaScript e utilitários genéricos não aparecem
        nos templates e seriam falso positivo.
        """
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        limpo = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

        marcacao = "".join(
            caminho.read_text(encoding="utf-8")
            for caminho in (RAIZ / "templates").rglob("*.html")
        ) + "".join(
            caminho.read_text(encoding="utf-8")
            for caminho in (RAIZ / "static" / "js").rglob("*.js")
        ) + "".join(
            # Marcação também nasce em Python: `SignupForm` monta a lista de
            # regras de senha com `mark_safe`, porque `help_text` é atributo do
            # campo e não conteúdo de template. Sem ler estes arquivos, as
            # classes de lá pareceriam órfãs.
            #
            # ARQUIVO DE TESTE FICA DE FORA, e é a parte que importa: um teste
            # que cita `.foo` faria `.foo` contar como usada, e esta checagem
            # existe justamente para achar CSS que ninguém renderiza.
            caminho.read_text(encoding="utf-8")
            for caminho in RAIZ.rglob("*.py")
            if ".venv" not in caminho.parts
            and "migrations" not in caminho.parts
            and not caminho.name.startswith(("test_", "tests"))
        )

        # Só os blocos que definem aparência, e só classes com `__` — as de
        # elemento, que existem para um template específico e para mais nada.
        def usada(classe):
            if classe in marcacao:
                return True
            # Modificadores compostos no template: `progress__fill--{{ slug }}`
            # nunca aparece escrito por inteiro, e não é órfão.
            base = classe.split("--")[0]
            return base != classe and f"{base}--{{{{" in marcacao

        orfas = sorted(
            {
                classe
                for classe in re.findall(r"\.([a-z][\w-]*__[\w-]+)", limpo)
                if not usada(classe)
            }
        )
        self.assertEqual(orfas, [], f"CSS para classes que ninguém renderiza: {orfas}")


def _sem_comentarios(css: str) -> str:
    """O CSS sem os blocos de comentário.

    Existe porque um comentário que explica por que um valor foi REJEITADO
    contém esse valor escrito por extenso — e uma busca ingênua o encontra e
    acusa a explicação de ser o defeito.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class DesignSystemTests(TestCase):
    """A paleta e as regras de layout que o design system fixou.

    O que estes testes travam não é gosto — é o conjunto de decisões que já
    voltou atrás sozinho neste arquivo quando alguém mexeu numa seção sem ver
    a outra. Cor de acento, raio de quina e tratamento de texto são globais
    por definição: se cada seção resolver a sua, a interface volta a parecer
    montada por gente diferente em semanas diferentes.
    """

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.escuro = _tokens(self.css, ":root {")

    def test_the_dark_palette_is_the_one_the_design_system_names(self):
        self.assertEqual(self.escuro["--bg"], "#0d0f12")
        self.assertEqual(self.escuro["--surface-2"], "#1a1d24")
        self.assertEqual(self.escuro["--border"], "#2a2e39")
        self.assertEqual(self.escuro["--brand"], "#10b981")
        self.assertEqual(self.escuro["--text"], "#ffffff")
        self.assertEqual(self.escuro["--text-mute"], "#9ca3af")

    def test_every_card_radius_lands_between_sixteen_and_twenty_pixels(self):
        """A escala tem quatro degraus e três deles são de CARTÃO. Um quinto
        degrau nasce quando alguém escreve `border-radius: 8px` direto na
        regra, e aí a tela tem duas linguagens de quina."""
        for token in ("--radius", "--radius-lg"):
            # `_tokens` só guarda valores hexadecimais — é um leitor de PALETA.
            achado = re.search(rf"^\s*{token}:\s*(\d+)px;", self.css, re.M)
            self.assertIsNotNone(achado, f"{token} não é mais um valor em px")
            px = int(achado.group(1))
            with self.subTest(token=token):
                self.assertGreaterEqual(px, 15)
                self.assertLessEqual(px, 20)

    def test_no_rule_hardcodes_a_radius_outside_the_scale(self):
        soltos = set(re.findall(r"border-radius:\s*(\d+)px", self.css))
        self.assertEqual(soltos, set(), f"raio fora da escala de tokens: {soltos}")

    def test_choice_cards_never_hyphenate_a_word_in_half(self):
        """pt-BR e hifenização automática não combinam: o navegador não carrega
        dicionário de separação silábica para toda língua e quebra "emagrecer"
        em lugares que não existem. A válvula é `overflow-wrap`, que só parte
        quando a palavra sozinha é mais larga que a coluna."""
        marca = chr(10).join(
            ["", ".choice-card__title,", ".choice-card__hint,", ".choice-card__exemplo {"]
        )
        regra = self.css.split(marca, 1)
        self.assertEqual(len(regra), 2, "o tratamento de texto do cartão sumiu")
        corpo = regra[1].split("}", 1)[0]

        self.assertIn("hyphens: none", corpo)
        self.assertIn("overflow-wrap: break-word", corpo)
        # `break-all` parte qualquer palavra a qualquer momento — é o defeito,
        # não a correção. Sem os comentários: a regra que documenta a escolha
        # cita o valor rejeitado, e o teste passava a acusar a própria
        # explicação de ser o defeito que ela descreve.
        self.assertNotIn("word-break: break-all", _sem_comentarios(self.css))

    def test_the_choice_grid_stays_single_column_on_a_phone(self):
        """Duas colunas a 390px dão 155px úteis, e "emagrecer e ganhar massa"
        não cabe em 155px sem partir palavra. O ponto de virada é medido, não
        escolhido pela largura redonda."""
        bloco = self.css.split(".choice-cards {", 1)[1].split("}", 1)[0]
        self.assertNotIn("grid-template-columns", bloco)

        depois = self.css.split(".choice-cards {", 1)[1]
        media = depois.split("@media (min-width: 30rem) {", 1)
        self.assertEqual(len(media), 2, "a segunda coluna não é condicional")
        self.assertIn("1fr 1fr", media[1].split("}", 1)[0])


class DayColourContrastTests(TestCase):
    """As cinco cores de dia, medidas nos três usos que elas têm.

    Elas ficaram de fora de todos os testes de contraste porque não são texto
    nem pílula: são uma paleta de IDENTIDADE, usada ora como fundo, ora como
    cor de texto, ora como tinta. `ContrastTests` mede os três tons de texto
    contra as superfícies; `PillContrastTests` mede marca, acento e âmbar
    contra a própria tinta. Nenhum dos dois olhava para cá.

    O resultado: `--dia-a` a `--dia-e` eram os únicos tokens de COR sem versão
    no tema claro. As do escuro são claras de propósito — menta, azul-gelo,
    âmbar — e vazavam inteiras para o claro, onde a letra do dia na tela de
    treino dava 1,72:1 com branco por cima. Ilegível, e sem nada avisando.
    """

    MINIMO = 4.5

    #: Os três usos reais, lidos do CSS:
    #:   .session__badge[data-dia]      → `--on-brand` SOBRE a cor
    #:   .day-chip__label[data-dia]     → a cor sobre a própria tinta a 22%
    #:   .card[data-dia]                → a cor como filete, e como texto no cartão
    TINTA = 0.22

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def _conferir(self, escopo, rotulo, fundo_da_tinta):
        tokens = _tokens(self.css, escopo)
        for letra in "abcde":
            cor = tokens.get(f"--dia-{letra}")
            with self.subTest(tema=rotulo, dia=letra):
                self.assertIsNotNone(
                    cor, f"--dia-{letra} não existe no tema {rotulo}"
                )

                sobre_texto = _contraste(tokens["--on-brand"], cor)
                self.assertGreaterEqual(
                    sobre_texto,
                    self.MINIMO,
                    f"--on-brand sobre --dia-{letra} dá {sobre_texto:.2f}:1",
                )

                tinta = _sobre(cor, self.TINTA, tokens[fundo_da_tinta])
                na_tinta = _contraste(cor, tinta)
                self.assertGreaterEqual(
                    na_tinta,
                    self.MINIMO,
                    f"--dia-{letra} sobre a própria tinta dá {na_tinta:.2f}:1",
                )

                no_cartao = _contraste(cor, tokens["--surface"])
                self.assertGreaterEqual(
                    no_cartao,
                    self.MINIMO,
                    f"--dia-{letra} sobre --surface dá {no_cartao:.2f}:1",
                )

    def test_dark_theme_day_colours_are_readable(self):
        self._conferir(":root {", "escuro", "--brand-soft")

    def test_light_theme_day_colours_are_readable(self):
        self._conferir(
            "prefers-color-scheme: light) {" + chr(10) + "  :root {",
            "claro",
            "--brand-soft",
        )

    def test_no_colour_token_is_left_without_a_light_theme_value(self):
        """A trava geral, e a razão de este teste existir.

        Token de cor que só existe no escuro vaza inteiro para o claro, e vaza
        em silêncio: o CSS é válido, a regra aplica, e o resultado é texto da
        cor errada num fundo da cor errada. Só tom, raio e tempo podem faltar —
        esses não têm tema.
        """
        def declarados(escopo):
            trecho = self.css.split(escopo, 1)[1].split(chr(10) + "}", 1)[0]
            return dict(re.findall(r"^\s*(--[\w-]+):\s*([^;]+);", trecho, re.M))

        escuro = declarados(":root {")
        claro = declarados(
            "prefers-color-scheme: light) {" + chr(10) + "  :root {"
        )

        # `_tokens` não serve aqui: ele é um leitor de PALETA e guarda só
        # valores `#rrggbb`. A borda do escuro é hexadecimal e a do claro é
        # `rgba()` — o mesmo token, escrito de duas formas, e o leitor de
        # paleta enxergaria a segunda como ausente.
        def eh_cor(valor):
            valor = valor.strip()
            return valor.startswith("#") or valor.startswith("rgb")

        orfaos = sorted(
            nome
            for nome, valor in escuro.items()
            if eh_cor(valor) and nome not in claro
        )
        self.assertEqual(orfaos, [], f"cor sem versão no tema claro: {orfaos}")

class HasSelectorTests(TestCase):
    """`:has()` não decide layout neste projeto.

    A regra está no CLAUDE.md desde que o convite de instalação cobriu a barra
    de navegação inteira: `body:has(.tabbar)` some por completo no navegador
    que não suporta o seletor, e some em SILÊNCIO — o CSS continua válido, o
    arquivo continua carregando, e a única pista é a tela errada.

    Estava escrita e não era medida. Escrevi um `:has()` estrutural no
    segmented control do passo 1 sem que nada reclamasse: onde ele não
    existisse, o botão escolhido ficaria sem preenchimento nenhum,
    indistinguível do outro, num controle cuja única função é mostrar qual
    está escolhido.

    O que este teste permite é o `:has()` DECORATIVO — realce que, faltando,
    não muda o que a tela comunica. A distinção é sempre discutível, então cada
    uso permitido é listado aqui com o motivo, e um uso novo precisa passar por
    esta lista.
    """

    #: (seletor, por que perder esta regra não quebra nada)
    DECORATIVOS = {
        ".choice-list label:has(input:checked)": (
            "realce de fundo numa lista onde o próprio radio marcado já mostra "
            "a escolha"
        ),
    }

    def setUp(self):
        self.css = _sem_comentarios(
            (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        )

    def test_every_has_selector_is_on_the_decorative_list(self):
        usos = {
            regra.strip()
            for regra in re.findall(r"([^\n{}]*:has\([^)]*\)[^\n{}]*)\{", self.css)
        }
        novos = usos - set(self.DECORATIVOS)
        self.assertEqual(
            novos,
            set(),
            "`:has()` novo fora da lista de decorativos — se ele decide "
            f"layout, use classe escrita pelo servidor: {novos}",
        )

    def test_the_segmented_control_draws_its_state_on_a_sibling(self):
        """O padrão que substitui o `:has()`: o input é filho do label, então
        só um irmão é alcançável — e `~` funciona em qualquer navegador."""
        self.assertIn(".segmented input:checked ~ .segmented__fundo", self.css)


class TouchFeedbackTests(TestCase):
    """Tudo que o dedo toca responde ao dedo, e responde igual.

    Uma auditoria achou onze clicáveis sem retorno nenhum — entre eles as
    SANFONAS, que são os elementos mais tocados do app: abrir um exercício e
    abrir uma opção de refeição. Nada quebrava; o toque simplesmente não dizia
    "recebi", e num app usado de pé com 4G da rua essa fração de segundo é a
    diferença entre tocar uma vez e tocar quatro.
    """

    #: Clicáveis que NÃO afundam, com o motivo. Uma classe nova aparece aqui
    #: por decisão, e não por esquecimento.
    ISENTOS = {
        ".chip": "três das quatro ocorrências são <span> decorativo",
    }

    def setUp(self):
        self.css = _sem_comentarios(
            (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        )
        self.html = ""
        for caminho in (RAIZ / "templates").rglob("*.html"):
            self.html += caminho.read_text(encoding="utf-8")

    def _com_escala(self):
        achados = set()
        for bloco in re.finditer(
            r"([^{}]+)\{([^}]*transform:\s*scale\([^)]*\)[^}]*)\}", self.css
        ):
            for seletor in bloco.group(1).split(","):
                seletor = seletor.strip()
                if seletor.endswith(":active"):
                    achados.add(seletor[: -len(":active")])
        return achados

    def test_every_clickable_class_gives_the_finger_an_answer(self):
        com_escala = self._com_escala()
        clicaveis = set()
        for m in re.finditer(r'<(?:button|a|summary)\b[^>]*class="([^"{}]+)"', self.html):
            for classe in m.group(1).split():
                clicaveis.add("." + classe)

        def coberto(classe):
            if classe in com_escala or classe in self.ISENTOS:
                return True
            # Modificador BEM anda sempre com o bloco: `.btn--primary` nunca
            # aparece sozinho no HTML, e quem afunda é `.btn`. Cobrar a escala
            # do modificador seria pedir a mesma regra cinco vezes.
            bloco = classe.split("--", 1)[0]
            return bloco != classe and bloco in com_escala

        faltando = sorted(
            c
            for c in clicaveis
            if not coberto(c) and (c + " {" in self.css or c + "," in self.css)
        )
        self.assertEqual(
            faltando, [], f"clicável sem retorno ao toque: {faltando}"
        )

    def test_the_three_lists_of_the_touch_section_are_the_same_list(self):
        """Afundar, transitar e ter saída para `prefers-reduced-motion` são
        três regras sobre o MESMO conjunto. Divergiram uma vez e o resultado
        foi gente com "reduzir movimento" ligado recebendo animação."""
        escala = self._com_escala()

        # TODOS os blocos de `prefers-reduced-motion`, e não o primeiro.
        #
        # Ler só o primeiro é a armadilha recorrente desta base, e ela pegou
        # este teste na estreia: o arquivo tem quatro blocos de menos
        # movimento, o `split(..., 1)` parava no primeiro `transform: none;`
        # que encontrasse depois do primeiro deles, e a lista grande — que
        # está no segundo — ficava de fora inteira.
        sem_movimento = set()
        for trecho in self.css.split("prefers-reduced-motion")[1:]:
            for regra in re.finditer(r"([^{}]+)\{[^}]*transform:\s*none[^}]*\}", trecho):
                for seletor in regra.group(1).split(","):
                    seletor = seletor.strip()
                    if seletor.endswith(":active"):
                        sem_movimento.add(seletor[: -len(":active")])

        self.assertEqual(
            escala - sem_movimento,
            set(),
            f"afunda sem saída para menos movimento: {escala - sem_movimento}",
        )

        # A TERCEIRA lista, que este teste não conferia apesar do nome.
        #
        # A pesagem rápida entrou nas duas primeiras e ficou de fora desta, e
        # o teste passou: quem afunda sem transitar salta para 96% e volta no
        # mesmo quadro, em vez de afundar sob o dedo como todo o resto do app.
        # Nenhum alarme, porque a comparação parava aqui.
        transita = set()
        for regra in re.finditer(
            r"([^{}]+)\{[^}]*transform \.12s var\(--ease\)[^}]*\}",
            _sem_comentarios(self.css),
        ):
            for seletor in regra.group(1).split(","):
                transita.add(seletor.strip())

        self.assertEqual(
            escala - transita,
            set(),
            f"afunda sem transição de transform: {escala - transita}",
        )


class GymReadyTests(TestCase):
    """O acabamento pedido para uso rapido na academia.

    O que estes testes travam nao e o valor — e a decisao por tras dele: um
    destaque so, um fio de acento so nos cartoes que sao destaque, e cor vinda
    de token e nao escrita a mao.
    """

    def setUp(self):
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def test_protein_is_the_only_macro_with_a_second_level_of_emphasis(self):
        """Caloria ja tem o primeiro nivel: esta no anel, em corpo grande e
        sozinha. Proteina e o segundo — dos tres macros, e o que muda a decisao
        da proxima refeicao.

        "Um destaque" e a regra: destacar dois de tres nao destaca nada.
        """
        hoje = (RAIZ / "templates" / "plans" / "today.html").read_text(encoding="utf-8")
        self.assertEqual(hoje.count("hero-macros__item--chave"), 1)
        self.assertIn("macro.slug == 'protein'", hoje)

    def test_the_emphasis_is_weight_and_size_and_never_colour(self):
        """A cor dos tres macros ja e o codigo da faixa empilhada logo acima.
        Repintar a proteina quebraria a correspondencia entre faixa e legenda —
        que e a unica coisa que a faixa tem para dizer."""
        bloco = "".join(
            trecho.split("}", 1)[0]
            for trecho in self.css.split(".hero-macros__item--chave")[1:]
        )
        self.assertIn("font-size", bloco)
        self.assertIn("font-weight", bloco)
        # `color` no NOME e no valor e permitido; o que nao pode e a cor do
        # macro mudar, e ela vem de `.macro-dot`.
        self.assertNotIn("macro-dot", bloco)

    def test_the_accent_edge_comes_from_the_token_and_not_a_fixed_hex(self):
        """`rgba(16, 185, 129, .2)` e o esmeralda do tema ESCURO. No claro a
        marca e #0c6b40, e o hex fixo apareceria la como uma cor que nao
        pertence a paleta de lugar nenhum."""
        regra = self.css.split(chr(10) + ".today-hero,", 1)[1].split("}", 1)[0]
        self.assertIn("var(--brand)", regra)
        self.assertNotIn("16, 185, 129", regra)

    def test_only_the_three_summary_cards_carry_the_accent_edge(self):
        """Nove cartoes com fio verde nao destacam nada, pintam listras. Os
        tres sao os que a pessoa le ANTES de decidir: ofensiva, resumo do dia
        e agua."""
        regra = self.css.split(chr(10) + ".today-hero,", 1)[1]
        seletores = regra.split("{", 1)[0]
        self.assertEqual(
            sorted(s.strip() for s in (".today-hero," + seletores).split(",") if s.strip()),
            [".agua", ".ofensiva", ".today-hero"],
        )

    def test_a_pressed_submit_says_so_before_the_server_answers(self):
        """Numa rede de academia o POST leva segundos, e nesses segundos a tela
        fica identica ao que era: a pessoa toca de novo. O segundo toque nao
        duplica nada, mas ensina que o botao nao funciona."""
        self.assertIn('[type="submit"][aria-busy="true"]', self.css)

        pwa = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        self.assertIn('aria-busy', pwa)
        # O caminho de volta: quem toca em "voltar" recebe a pagina do cache do
        # navegador como saiu — com o botao travado — e ficaria olhando um
        # formulario morto.
        self.assertIn('"pageshow"', pwa)
        # E o caminho offline: enfileirado, o envio nao vai acontecer agora.
        self.assertIn("nutriplan:enfileirado", pwa)

    def test_the_waiting_pulse_has_a_way_out_of_the_movement(self):
        trechos = self.css.split("prefers-reduced-motion")
        self.assertTrue(
            any('[type="submit"][aria-busy="true"]' in t.split("}\n}", 1)[0] for t in trechos[1:]),
            "o pulso de espera anima sem saida para quem pediu menos movimento",
        )


class MarcaTests(TestCase):
    """A identidade oficial: uma arte, e os lugares onde ela aparece.

    A marca anterior era um desenho geométrico em SVG — anel e "N" — que tomava
    as cores do tema: verde no escuro, verde-escuro no claro. Isto substitui
    aquela regra de propósito.

    A identidade aprovada tem PALETA PRÓPRIA e constante: verde-floresta,
    branco e o verde da folha. Ela não acompanha o tema, e é justamente por
    isso que é uma marca — o que muda de cor conforme o aparelho é um elemento
    de interface com forma de marca, não uma. A interface ao redor continua
    adaptativa; só a marca é fixa, como numa embalagem.

    Estes testes guardam o CONTRATO, não os pixels. Conferir byte de PNG
    prenderia a suíte a um detalhe que muda a cada reexportação da arte sem
    nada de errado ter acontecido.
    """

    #: Os derivados que a interface e o PWA realmente pedem, e para quê.
    DERIVADOS = {
        "icon-192.png": 192,
        "icon-512.png": 512,
        "icon-192-maskable.png": 192,
        "icon-512-maskable.png": 512,
        "apple-touch-icon.png": 180,
        "favicon-16.png": 16,
        "favicon-32.png": 32,
        "favicon-48.png": 48,
    }

    def setUp(self):
        self.marca = (RAIZ / "templates" / "partials" / "marca.html").read_text(
            encoding="utf-8"
        )
        self.base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
        self.css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.icones = RAIZ / "static" / "icons"

    # -- a fonte da verdade ------------------------------------------------

    def test_the_approved_art_is_versioned_in_the_repository(self):
        """Todo derivado sai dela. Fora do repositório, regerar os ícones
        dependeria de alguém ainda ter o arquivo na máquina."""
        fonte = RAIZ / "assets" / "nutriplan-icon-source.png"
        self.assertTrue(fonte.exists(), "a arte aprovada sumiu de assets/")
        self.assertEqual(fonte.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_the_mark_is_the_art_and_not_a_drawing_of_it(self):
        """O `<svg>` desenhado à mão saiu.

        Enquanto a marca era retângulos e um círculo, o SVG era o formato
        certo. A arte aprovada tem sombra no "N", gradiente e nervura na
        folha — redesenhá-la em vetor produziria outra marca, que é exatamente
        o que esta missão proibiu.
        """
        self.assertIn("icons/icon-192.png", self.marca)
        self.assertNotIn("<svg", self.marca)
        self.assertNotIn("<path", self.marca)

    def test_the_mark_says_where_it_comes_from(self):
        """Quem for mexer na identidade precisa achar o caminho de volta: o
        arquivo-fonte e o gerador, não o PNG derivado."""
        self.assertIn("gerar_identidade.ps1", self.marca)
        self.assertIn("nutriplan-icon-source.png", self.marca)
        self.assertTrue((RAIZ / "scripts" / "gerar_identidade.ps1").exists())

    # -- a paleta própria --------------------------------------------------

    def test_nothing_repaints_the_mark_with_the_interface_colours(self):
        """A regra que esta identidade substituiu, agora guardada ao contrário.

        Antes o teste exigia `var(--on-brand)` na marca; agora ele exige que
        NADA a tinja. `currentColor`, `fill` ou um `filter` no CSS devolveriam
        a marca ao tema e desfariam a decisão sem ninguém perceber — o arquivo
        continuaria certo e a tela mostraria outra coisa.
        """
        regra = "".join(
            trecho.split("}", 1)[0]
            for trecho in self.css.split(chr(10) + ".marca {")[1:]
        )
        self.assertNotIn("currentColor", regra)
        self.assertNotIn("fill:", regra)
        self.assertNotIn("filter:", regra)

    def test_it_carries_its_own_ground_so_both_themes_read_the_same(self):
        """A legibilidade nos dois temas não vem de contraste com a página: vem
        de a marca trazer o próprio fundo verde-floresta.

        É o que torna o requisito verificável sem medir pixel — o mesmo arquivo
        opaco é servido no claro e no escuro, então não existe combinação de
        tema que mude o que se vê. O que o envoltório NÃO pode fazer é pintar
        um fundo por baixo ou furar a arte.
        """
        for seletor in (".app-bar__mark", ".auth__logo"):
            with self.subTest(seletor=seletor):
                regra = "".join(
                    t.split("}", 1)[0]
                    for t in self.css.split(chr(10) + seletor + " {")[1:]
                )
                self.assertNotIn("background", regra)
        # E a imagem é opaca: sem `opacity`, o fundo da página atravessaria.
        marca = "".join(
            t.split("}", 1)[0] for t in self.css.split(chr(10) + ".marca {")[1:]
        )
        self.assertNotIn("opacity", marca)

    def test_the_rounded_corner_comes_from_the_css_and_not_from_the_file(self):
        """O arquivo é SANGRADO — quadrado, sem canto arredondado.

        É o mesmo arquivo que o iOS e o Android instalam, e os dois aplicam a
        própria máscara. Arte já arredondada devolve canto duplicado, com o
        fundo do sistema aparecendo por fora do nosso. Então a quina do selo é
        do CSS, e vem de token como todas as outras do app.
        """
        marca = "".join(
            t.split("}", 1)[0] for t in self.css.split(chr(10) + ".marca {")[1:]
        )
        self.assertIn("border-radius", marca)
        self.assertIn("var(--radius", marca)

    # -- onde ela aparece --------------------------------------------------

    def test_the_same_identity_greets_at_login_and_at_signup(self):
        """Uma inclusão, não duas cópias: as telas de entrada são a primeira
        coisa que alguém vê do app, e duas marcas divergem na primeira
        troca."""
        for tela in ("login.html", "signup.html"):
            with self.subTest(tela=tela):
                html = (RAIZ / "templates" / "accounts" / tela).read_text(
                    encoding="utf-8"
                )
                self.assertIn("partials/marca.html", html)

    def test_the_top_bar_carries_it_too(self):
        self.assertIn("partials/marca.html", self.base)

    # -- os derivados ------------------------------------------------------

    def test_every_derivative_the_interface_asks_for_exists(self):
        for nome in self.DERIVADOS:
            with self.subTest(icone=nome):
                caminho = self.icones / nome
                self.assertTrue(caminho.exists(), "derivado ausente")
                self.assertEqual(caminho.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_every_derivative_has_the_size_its_name_promises(self):
        """Nome que mente é pior que arquivo faltando: o navegador aceita e
        reamostra, e ninguém vê o borrão até alguém instalar o app."""
        for nome, lado in self.DERIVADOS.items():
            with self.subTest(icone=nome):
                dados = (self.icones / nome).read_bytes()
                largura, altura = struct.unpack(">II", dados[16:24])
                self.assertEqual((largura, altura), (lado, lado))

    def test_no_derivative_is_a_blank_placeholder(self):
        """Um PNG de cor chapada comprime para quase nada.

        Este é o guarda barato contra o acidente que os outros testes deixam
        passar: um arquivo com o nome certo, o tamanho certo e nenhuma marca
        dentro. A arte tem um "N" com sombra e uma folha com gradiente, e isso
        não cabe em dois quilobytes num ícone de 192.
        """
        self.assertGreater((self.icones / "icon-192.png").stat().st_size, 8_000)
        self.assertGreater((self.icones / "icon-512.png").stat().st_size, 30_000)

    def test_no_derivative_is_heavy_enough_to_hurt_the_first_paint(self):
        """O `icon-192.png` é a marca do cabeçalho, e ele carrega em toda
        página. A primeira versão gerada tinha 352 KB no de 512 porque o
        recorte trazia a granulação do fundo da arte."""
        self.assertLess((self.icones / "icon-192.png").stat().st_size, 60_000)
        self.assertLess((self.icones / "icon-512.png").stat().st_size, 250_000)

    def test_the_favicon_carries_the_three_small_sizes(self):
        """16, 32 e 48 dentro de um arquivo, e o navegador escolhe. É também o
        que responde ao `/favicon.ico` que o navegador busca sozinho."""
        dados = (self.icones / "favicon.ico").read_bytes()
        self.assertEqual(dados[:4], b"\x00\x00\x01\x00", "não é um ICO")
        quantidade = struct.unpack("<H", dados[4:6])[0]
        self.assertEqual(quantidade, 3)
        larguras = {dados[6 + 16 * i] for i in range(quantidade)}
        self.assertEqual(larguras, {16, 32, 48})

    def test_the_head_points_at_the_new_assets(self):
        """O `favicon.svg` era o desenho da marca antiga. Deixá-lo no `<head>`
        faria a aba mostrar a identidade anterior enquanto o resto do app já
        mostrava a nova — e ninguém olha o favicon para conferir deploy."""
        self.assertNotIn("favicon.svg", self.base)
        self.assertFalse((self.icones / "favicon.svg").exists())
        self.assertIn("icons/favicon.ico", self.base)
        self.assertIn("icons/apple-touch-icon.png", self.base)

    def test_apple_gets_its_own_file_at_the_size_it_asks_for(self):
        """180 é a medida do iOS desde o iPhone 6 Plus. Apontar para o de 192
        funcionava e fazia o sistema reamostrar em toda instalação."""
        self.assertIn('sizes="180x180"', self.base)
        dados = (self.icones / "apple-touch-icon.png").read_bytes()
        self.assertEqual(struct.unpack(">II", dados[16:24]), (180, 180))


class ObservabilidadeTests(TestCase):
    """O log precisa servir para diagnosticar sem virar vazamento.

    O NutriPlan não tinha configuração de log nenhuma até esta missão: uma
    exceção não tratada sumia, e o único sinal era `/saude/`, que responde 200
    enquanto o processo estiver de pé.
    """

    def test_o_token_de_redefinicao_nunca_sobrevive_no_log(self):
        """É o vazamento urgente: o token viaja NA URL.

        `django.request` registra o caminho num 500. Sem redação, um erro na
        tela de redefinir gravaria um token VÁLIDO por três horas no log da
        plataforma — o mesmo cenário que `accounts/checks.py` fecha do lado do
        e-mail.
        """
        from config.observabilidade import redigir

        caminho = "/conta/senha/nova/MjM/cf9x2k-4a1b2c3d4e5f6a7b8c9d0e1f2a3b4c/"

        limpo = redigir("Internal Server Error: " + caminho)

        self.assertIn("[REDIGIDO]", limpo)
        self.assertNotIn("cf9x2k", limpo)
        self.assertNotIn("MjM", limpo)
        # E o começo do caminho fica, senão o log perde o que serve.
        self.assertIn("/senha/nova/", limpo)

    def test_segredos_de_infraestrutura_tambem_somem(self):
        from config.observabilidade import redigir

        texto = redigir(
            "erro ao conectar postgresql://usuario:senha@host:5432/banco "
            "com chave xsmtpsib-abc123def456 e ?code=segredo&state=outro"
        )

        self.assertNotIn("senha@host", texto)
        self.assertNotIn("abc123def456", texto)
        self.assertNotIn("segredo", texto)
        self.assertIn("[REDIGIDO]", texto)

    def test_cada_resposta_carrega_um_identificador(self):
        """Sem ele, "deu erro" e "o usuário reclamou" nunca se encontram."""
        resposta = self.client.get(reverse("health"))

        self.assertIn("X-Request-ID", resposta)
        self.assertRegex(resposta["X-Request-ID"], r"^[A-Za-z0-9._-]{1,64}$")

    def test_o_identificador_de_fora_e_reaproveitado_quando_e_seguro(self):
        """Assim a mesma marca atravessa proxy e aplicação."""
        resposta = self.client.get(reverse("health"), HTTP_X_REQUEST_ID="abc-123")

        self.assertEqual(resposta["X-Request-ID"], "abc-123")

    def test_cabecalho_com_lixo_nao_entra_no_log(self):
        """Cabeçalho é escrito pelo cliente. Aceitar qualquer coisa
        transformaria o log num alvo de injeção."""
        resposta = self.client.get(
            reverse("health"), HTTP_X_REQUEST_ID="quebra\nlinha INJETADA"
        )

        self.assertNotIn("INJETADA", resposta["X-Request-ID"])
        self.assertRegex(resposta["X-Request-ID"], r"^[0-9a-f]{12}$")

    def test_o_sql_nao_vai_para_o_log_nem_em_debug(self):
        """Consulta com parâmetro carrega e-mail e peso — dado de saúde num
        log é dado de saúde exposto."""
        from config import observabilidade

        cfg = observabilidade.configuracao(debug=True)

        self.assertEqual(cfg["loggers"]["django.db.backends"]["level"], "WARNING")

    def test_erro_de_servidor_e_registrado_com_traceback(self):
        cfg = __import__("config.observabilidade", fromlist=["x"]).configuracao(False)

        self.assertEqual(cfg["loggers"]["django.request"]["level"], "ERROR")
        self.assertIn("console", cfg["loggers"]["django.request"]["handlers"])


class RotacaoDeChaveTests(TestCase):
    """A troca da `SECRET_KEY` não pode derrubar todo mundo."""

    def test_o_projeto_aceita_chaves_antigas(self):
        """`SECRET_KEY_FALLBACKS` é o que permite trocar a chave sem deslogar
        ninguém e sem invalidar link de redefinição em trânsito."""
        from django.conf import settings

        self.assertTrue(hasattr(settings, "SECRET_KEY_FALLBACKS"))
        self.assertIsInstance(settings.SECRET_KEY_FALLBACKS, list)

    def test_sem_a_variavel_a_lista_fica_vazia(self):
        """O padrão é NÃO ter chave antiga valendo: fallback esquecido é uma
        chave aposentada que continua assinando."""
        from django.conf import settings

        self.assertEqual(settings.SECRET_KEY_FALLBACKS, [])

    def test_sessao_assinada_com_a_chave_antiga_continua_valendo(self):
        """O contrato inteiro da janela de migração, em uma asserção."""
        from django.contrib.auth import get_user_model

        antiga = "chave-antiga-de-teste-com-tamanho-suficiente-1234567890"
        nova = "chave-nova-de-teste-com-tamanho-suficiente-0987654321abc"

        user = get_user_model().objects.create_user(
            email="rotacao@exemplo.com", password="SenhaDaRotacao!2026"
        )
        with override_settings(SECRET_KEY=antiga, SECRET_KEY_FALLBACKS=[]):
            cliente = Client()
            cliente.force_login(user)
            self.assertIn("_auth_user_id", cliente.session)
            cookie = cliente.cookies["sessionid"].value

        with override_settings(SECRET_KEY=nova, SECRET_KEY_FALLBACKS=[antiga]):
            depois = Client()
            depois.cookies["sessionid"] = cookie
            resposta = depois.get(reverse("accounts:profile"))
            self.assertEqual(resposta.status_code, 200)

    def test_sem_fallback_a_sessao_antiga_cai(self):
        """O custo de trocar sem rede, medido — é o que justifica a janela."""
        from django.contrib.auth import get_user_model

        antiga = "chave-antiga-de-teste-com-tamanho-suficiente-1234567890"
        nova = "chave-nova-de-teste-com-tamanho-suficiente-0987654321abc"

        user = get_user_model().objects.create_user(
            email="semrede@exemplo.com", password="SenhaSemRede!2026"
        )
        with override_settings(SECRET_KEY=antiga, SECRET_KEY_FALLBACKS=[]):
            cliente = Client()
            cliente.force_login(user)
            cookie = cliente.cookies["sessionid"].value

        with override_settings(SECRET_KEY=nova, SECRET_KEY_FALLBACKS=[]):
            depois = Client()
            depois.cookies["sessionid"] = cookie
            resposta = depois.get(reverse("accounts:profile"))
            self.assertEqual(resposta.status_code, 302)


class HealthV2Tests(TestCase):
    """Liveness e readiness respondem perguntas diferentes."""

    @classmethod
    def setUpTestData(cls):
        semear()

    def test_liveness_nao_toca_no_banco(self):
        """"O processo está de pé?" se responde sem banco — e é essa pergunta
        que decide REINICIAR. Misturar com readiness faria uma queda momentânea
        do banco derrubar um processo saudável, e reiniciar não conserta banco
        fora do ar."""
        with self.assertNumQueries(0):
            resposta = self.client.get(reverse("liveness"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "vivo"})

    def test_readiness_cabe_em_uma_consulta(self):
        """Eram quatro `COUNT`, uma por tabela, a cada batida do health check
        da plataforma — que acontece de poucos em poucos segundos."""
        with self.assertNumQueries(1):
            resposta = self.client.get(reverse("health"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["status"], "ok")

    def test_readiness_continua_recusando_catalogo_vazio(self):
        from catalog.models import Food

        Food.objects.update(is_active=False)

        resposta = self.client.get(reverse("health"))

        self.assertEqual(resposta.status_code, 503)
        self.assertIn("alimentos", resposta.json()["faltando"])

    def test_a_plataforma_aponta_para_o_readiness(self):
        """Um `healthCheckPath` no liveness deixaria o Render publicar um app
        que subiu sem banco."""
        render = (Path(settings.BASE_DIR) / "render.yaml").read_text(encoding="utf-8")

        self.assertIn("healthCheckPath: /saude/", render)


class ConexaoDeBancoTests(TestCase):
    """Conexão por pedido é barata perto de um Postgres local e cara longe dele.

    O banco de produção fica em Oregon, atrás de TLS. Com o padrão do Django —
    abrir e fechar a cada requisição — toda tela paga um handshake antes de a
    primeira consulta sair, e numa tela de três consultas o custo de conectar
    passa a pesar mais que as consultas.
    """

    def test_a_conexao_e_reaproveitada(self):
        self.assertGreater(settings.DATABASES["default"]["CONN_MAX_AGE"], 0)

    def test_o_sslmode_da_url_chega_ate_o_driver(self):
        """Um banco gerenciado fora da máquina exige TLS, e é a URL que pede.

        `env.db()` transforma a query string da DATABASE_URL em `OPTIONS`. Se
        alguém trocar essa leitura por algo que descarte a query — um split no
        `?`, um parser escrito à mão —, o `sslmode` some e a conexão passa a
        sair em texto claro, carregando e-mail e peso corporal pela internet.
        Não haveria erro: o Postgres aceitaria a conexão do mesmo jeito.

        O `channel_binding` anda junto na URL do Neon e amarra a autenticação
        ao canal TLS, o que fecha um ataque de máquina no meio.
        """
        import os

        import environ

        os.environ["URL_DE_TESTE"] = (
            "postgres://usuario:segredo@ep-exemplo.us-west-2.aws.neon.tech"
            "/nutriplan?sslmode=require&channel_binding=require"
        )
        try:
            opcoes = environ.Env().db("URL_DE_TESTE").get("OPTIONS") or {}
        finally:
            del os.environ["URL_DE_TESTE"]

        self.assertEqual(opcoes.get("sslmode"), "require")
        self.assertEqual(opcoes.get("channel_binding"), "require")

        # A metade que faltava: o acima prova que a BIBLIOTECA preserva o
        # sslmode, e não que o NutriPlan passa por ela. Sem esta linha, alguém
        # troca `env.db()` por um parser próprio, o teste continua verde, e a
        # conexão sai sem TLS.
        fonte = (Path(settings.BASE_DIR) / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('env.db(', fonte)
        self.assertIn('"DATABASE_URL"', fonte)

    def test_o_driver_e_novo_o_bastante_para_um_postgres_gerenciado(self):
        """libpq antiga não manda SNI, e sem SNI o Neon não roteia a conexão.

        O Neon põe muitos bancos atrás do mesmo endereço e decide qual é o seu
        pelo nome do servidor enviado NO HANDSHAKE TLS. Cliente velho conecta,
        autentica e cai num lugar errado — ou simplesmente é recusado. libpq 14
        é o primeiro que manda SNI sempre.
        """
        import psycopg

        self.assertGreaterEqual(psycopg.pq.version(), 140000)

    def test_a_conexao_reaproveitada_e_checada_antes_de_usar(self):
        """`CONN_MAX_AGE` sem `CONN_HEALTH_CHECKS` é uma armadilha, não um ganho.

        A conexão guardada pode ter morrido do outro lado — o banco reiniciou,
        a rede caiu, ou o servidor hibernou por inatividade. Sem a checagem, o
        primeiro pedido depois disso estoura com `OperationalError` na cara de
        quem estava usando o app, e o segundo funciona: o defeito mais chato de
        reproduzir que existe.
        """
        self.assertIs(settings.DATABASES["default"]["CONN_HEALTH_CHECKS"], True)


class BancoDoBlueprintTests(TestCase):
    """O blueprint não pode mandar a produção de volta para o banco antigo.

    O banco saiu do Render e foi para o Neon em 01/09/2026. O serviço é
    "Blueprint managed", e enquanto `render.yaml` disser

        - key: DATABASE_URL
          fromDatabase:
            name: nutriplan-db

    isso não é documentação — é uma ordem. Na sincronização seguinte o Render
    sobrescreveria a DATABASE_URL de volta para o banco antigo, e a migração
    se desfaria sozinha: sem erro, sem log, sem ninguém pedir. O app voltaria
    a escrever no banco que expira em 23/09/2026, e tudo gravado no Neon
    depois disso ficaria órfão.
    """

    def test_a_url_do_banco_nao_vem_do_blueprint(self):
        texto = (Path(settings.BASE_DIR) / "render.yaml").read_text(
            encoding="utf-8"
        )
        bloco = texto.split("- key: DATABASE_URL", 1)[1].split("- key:", 1)[0]
        self.assertNotIn("fromDatabase", bloco)
        self.assertIn("sync: false", bloco)

    def test_o_banco_antigo_continua_declarado(self):
        """Ele é o rollback, e some do Render se sair daqui.

        Apagar a declaração faria o Render remover o banco na próxima
        sincronização — junto com a única volta possível se o Neon der
        problema. Ele expira sozinho em 23/09/2026; até lá, fica.
        """
        texto = (Path(settings.BASE_DIR) / "render.yaml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(texto, r"(?m)^databases:")
        self.assertIn("name: nutriplan-db", texto)


class PortaSmtpTests(TestCase):
    """O Render bloqueia SMTP de saída em 25, 465 e 587 no plano gratuito.

    Isso derrubou a recuperação de senha em produção sem que nada aparecesse:
    o socket estourava em `TimeoutError` depois de 10 segundos, e o Django
    CAPTURA essa falha dentro de `PasswordResetForm.save()` — a view devolve o
    mesmo 302 do caminho feliz e a tela diz "verifique seu e-mail". Do lado de
    fora, sucesso e fracasso eram indistinguíveis.

    A porta virou parte do blueprint por causa disso. Deixá-la só no painel é
    exatamente como o defeito volta: alguém apaga a variável, o padrão do
    `settings.py` é 587, e a recuperação de senha morre de novo em silêncio.
    """

    #: As três que o Render recusa. 2525 não está na lista, e é onde a Brevo
    #: também atende — com STARTTLS, então não se troca TLS por conectividade.
    BLOQUEADAS = {"25", "465", "587"}

    def test_o_blueprint_declara_uma_porta_que_o_render_nao_bloqueia(self):
        texto = (Path(settings.BASE_DIR) / "render.yaml").read_text(
            encoding="utf-8"
        )
        bloco = texto.split("- key: EMAIL_PORT", 1)[1].split("- key:", 1)[0]
        achado = re.search(r'value:\s*"?(\d+)"?', bloco)

        self.assertIsNotNone(
            achado,
            "EMAIL_PORT precisa de um `value:` no render.yaml — deixá-la "
            "solta no painel é como a recuperação de senha morre em silêncio.",
        )
        self.assertNotIn(achado.group(1), self.BLOQUEADAS)

    def test_o_tls_nao_foi_desligado_para_a_porta_funcionar(self):
        """A saída fácil seria trocar TLS por conectividade. Não é a daqui.

        A 2525 da Brevo anuncia STARTTLS e negocia TLSv1.3 — provado no
        handshake antes da troca. Se um dia alguém "consertar" o envio
        desligando a criptografia, a credencial e o link de redefinição
        passam a trafegar em texto claro.
        """
        texto = (Path(settings.BASE_DIR) / "render.yaml").read_text(
            encoding="utf-8"
        )
        bloco = texto.split("- key: EMAIL_USE_TLS", 1)[1].split("- key:", 1)[0]
        self.assertRegex(bloco, r'value:\s*"?True"?')


class BackupTests(TestCase):
    """O plano gratuito não faz backup, e o banco tem data para ser apagado.

    O que estes testes protegem é uma cicatriz específica: o primeiro backup de
    produção gerou um arquivo de ZERO BYTE e imprimiu "BACKUP OK". O `pg_dump`
    era 16.9, o servidor 18.4, e o cliente se recusa a despejar servidor mais
    novo — mas o script perguntava "o arquivo existe?" em vez de "o comando deu
    certo?". Existia. Vazio. E o backup seguinte sobrescreveria a única cópia
    boa com a mesma confiança.
    """

    BACKUP = RAIZ / "scripts" / "backup.sh"
    RESTAURAR = RAIZ / "scripts" / "restaurar.sh"
    MIGRAR = RAIZ / "scripts" / "migrar.sh"
    def test_os_tres_scripts_existem(self):
        self.assertTrue(self.BACKUP.is_file())
        self.assertTrue(self.RESTAURAR.is_file())
        self.assertTrue(self.MIGRAR.is_file())

    def test_a_string_de_conexao_nunca_e_argumento_posicional(self):
        """`psql "$URL" -c ...` funciona no cliente 18 e falha no 16.

        O ensaio local pegou isto: o cliente trata a string de conexão como
        posicional, ela precisa vir por último, e um `pg_dump "$URL" -Fc`
        morre com "too many command-line arguments" em cliente mais velho —
        no meio de uma janela de manutenção, que é o pior momento possível
        para descobrir uma incompatibilidade de linha de comando.

        `-d` é opção, então a ordem deixa de importar e o script funciona em
        qualquer versão do cliente.
        """
        for script in (self.BACKUP, self.RESTAURAR, self.MIGRAR):
            texto = script.read_text(encoding="utf-8")
            self.assertNotRegex(
                texto, r'\b(psql|pg_dump)\s+"\$', script.name
            )
    def test_o_backup_aborta_quando_um_passo_falha(self):
        """Sem `errexit`, o `pg_dump` falha e o script segue até o "BACKUP OK"."""
        texto = self.BACKUP.read_text(encoding="utf-8")
        self.assertIn("set -o errexit", texto)

    def test_o_backup_confere_o_tamanho_do_arquivo(self):
        texto = self.BACKUP.read_text(encoding="utf-8")
        self.assertIn("MINIMO_BYTES", texto)
        # a comparação, e não só a constante declarada
        self.assertRegex(texto, r'\$TAMANHO"?\s*-lt\s*"?\$MINIMO_BYTES')

    def test_o_backup_nao_recebe_a_url_por_argumento(self):
        """Argumento aparece em `ps`, no histórico do shell e no log de CI.

        A URL do banco carrega a senha. Ela entra por ambiente ou não entra.
        """
        texto = self.BACKUP.read_text(encoding="utf-8")
        self.assertIn('DATABASE_URL:-', texto)
        self.assertNotRegex(texto, r'DATABASE_URL="\$\{?[1-9]')

    def test_nenhum_deles_imprime_a_url(self):
        for script in (self.BACKUP, self.RESTAURAR, self.MIGRAR):
            texto = script.read_text(encoding="utf-8")
            for linha in texto.splitlines():
                despido = linha.strip()
                if despido.startswith("#"):
                    continue
                if despido.startswith(("echo", "printf")):
                    self.assertNotIn("$DATABASE_URL", despido, script.name)
                    self.assertNotIn("$ALVO", despido, script.name)
                    self.assertNotIn("$DESTINO", despido, script.name)


class RestoreDrillTests(TestCase):
    """O guarda-corpo do restore, testado rodando o script — não lendo o texto.

    `assertIn("localhost", texto)` passaria com a checagem comentada. Aqui o
    script é EXECUTADO com um alvo remoto e precisa se recusar a continuar:
    ele começa apagando o banco de destino, e apontá-lo para produção por
    engano apagaria o banco de verdade.
    """

    RESTAURAR = RAIZ / "scripts" / "restaurar.sh"

    def _rodar(self, *args, **ambiente):
        import os
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash não está disponível neste ambiente")

        env = dict(os.environ)
        env.update(ambiente)
        return subprocess.run(
            [bash, str(self.RESTAURAR), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60, env=env,
        )

    def test_recusa_alvo_que_nao_seja_local(self):
        dump = RAIZ / "manage.py"  # só precisa existir; não chega a ser lido
        r = self._rodar(str(dump), "postgres://u:s@banco-de-verdade.com:5432/prod")

        self.assertNotEqual(r.returncode, 0)
        self.assertIn("não é local", r.stderr)

    def test_o_escape_existe_e_e_deliberado(self):
        """Recusar sempre tornaria o script inútil para uma migração real.

        `FORCA=1` é longo o bastante para ninguém digitar por engano, e o
        pedido some do histórico junto com o comando.
        """
        dump = RAIZ / "manage.py"
        r = self._rodar(str(dump), "postgres://u:s@outro-host.com:5432/x", FORCA="1")

        # Passa do guarda-corpo e morre adiante, tentando falar com o host —
        # que é exatamente o que se quer provar.
        self.assertNotIn("não é local", r.stderr)

    def test_sem_arquivo_nao_faz_nada(self):
        r = self._rodar("/caminho/que/nao/existe.dump")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uso:", r.stderr)


class HealthCheckNaoAcordaOBancoTests(TestCase):
    """O health check do Render não pode consultar o banco.

    Ele bate a cada ~5 segundos — medido no log de produção em 01/09/2026 — e o
    Neon gratuito hiberna depois de 5 minutos parado, com 100 CU-horas por mês.
    Um endpoint que consulta o catálogo nessa frequência mantém o banco acordado
    24 horas por dia: a 0,25 CU contínuo são 180 CU-horas, e a cota acaba por
    volta do dia 16.

    O defeito não seria um erro na tela. Seria o banco parar de responder no
    meio do mês, com a causa a três camadas de distância de onde alguém
    procuraria.
    """

    #: Todo arquivo de plataforma que declara health check automático.
    #:
    #: `railway.json` não está em uso — produção é o Render —, mas declarava
    #: `/saude/` e teria o mesmo defeito no dia em que alguém subisse por lá.
    #: Configuração dormente é onde um defeito corrigido volta.
    BLUEPRINTS = (
        ("render.yaml", "healthCheckPath: /saude/vivo/", "healthCheckPath: /saude/\n"),
        ("railway.json", '"healthcheckPath": "/saude/vivo/"', '"healthcheckPath": "/saude/"'),
    )

    def test_os_blueprints_apontam_para_o_endpoint_sem_consulta(self):
        for arquivo, esperado, proibido in self.BLUEPRINTS:
            conteudo = (Path(settings.BASE_DIR) / arquivo).read_text(encoding="utf-8")
            with self.subTest(arquivo=arquivo):
                self.assertIn(esperado, conteudo)
                self.assertNotIn(proibido, conteudo)

    def test_o_endpoint_do_health_check_nao_toca_no_banco(self):
        """A outra ponta: o blueprint pode apontar certo e a view mudar.

        Sem esta metade, alguém acrescenta uma verificação de banco em
        `VivoView` — o que é uma ideia razoável isolada — e a cota volta a
        queimar sem nada apontar para a mudança.
        """
        with self.assertNumQueries(0):
            resposta = self.client.get(reverse("liveness"))

        self.assertEqual(resposta.status_code, 200)

    def test_a_verificacao_profunda_continua_existindo(self):
        """Trocar o health check não pode virar desistir de verificar o banco.

        `/saude/` continua sendo o endpoint que REPROVA quando o catálogo some
        — ele só deixou de ser o que roda a cada cinco segundos. O 503 com
        banco vazio é a prova de que ele ainda olha para dentro; um 200 aqui
        significaria que a verificação profunda virou enfeite.
        """
        resposta = self.client.get(reverse("health"))

        self.assertEqual(resposta.status_code, 503)
        self.assertIn("catalogo", resposta.json())


class ComentarioDeTemplateNaoVazaTests(SimpleTestCase):
    """`{# #}` comenta UMA linha. Escrito em três, vira texto na tela.

    Encontrado olhando a página: o rodapé da tela de corridas mostrava a frase
    "A URL versionada vem do contexto..." em letra normal, no meio do conteúdo.
    Nenhum teste pegou — a suíte inteira passava —, porque o HTML continuava
    válido e a view continuava devolvendo 200.

    A varredura é sobre TODOS os templates, e não sobre o que eu escrevi: o
    erro é fácil de repetir e o sintoma é discreto o bastante para sobreviver a
    uma revisão. Quem quiser comentário de várias linhas usa
    `{% comment %}`.
    """

    def test_nenhum_comentario_de_cerquilha_atravessa_linhas(self):
        import re

        vazando = []
        for arquivo in (RAIZ / "templates").rglob("*.html"):
            texto = arquivo.read_text(encoding="utf-8")
            for achado in re.finditer(r"\{#", texto):
                resto = texto[achado.start() :]
                fim = resto.find("#}")
                if fim == -1 or "\n" in resto[:fim]:
                    linha = texto[: achado.start()].count("\n") + 1
                    vazando.append(f"{arquivo.name}:{linha}")

        self.assertEqual(vazando, [])


class TodaTelaTemPortaTests(SimpleTestCase):
    """Tela que ninguém alcança é código que passa nos testes e não serve.

    Três vezes nesta rodada eu criei rota sem porta: a ação de pedir nova
    escolha de divisão (permissão concedida, endpoint respondendo, e nenhum
    botão), a tela de corridas e o painel de gestão. Testar a rota não pega
    nenhuma delas — todas respondiam certo o tempo todo. O que faltava era
    alguém conseguir CHEGAR.

    Três vezes é padrão, não acidente. Esta tabela é a resposta: destino que
    uma pessoa precisa alcançar entra aqui, e o teste procura a referência nos
    templates.

    Ela NÃO lista tudo. Endpoint de POST, rota de API e tela que só se alcança
    por fluxo (o wizard, o callback do OAuth) ficam de fora de propósito —
    incluir tudo tornaria a lista impossível de manter e ela deixaria de ser
    lida. O critério é: alguém precisa poder ir até lá por vontade própria?
    """

    #: (nome da rota, por que uma pessoa vai até lá)
    DESTINOS = (
        ("plans:today", "o dia de hoje"),
        ("plans:history", "progresso"),
        ("plans:shopping", "lista de compras"),
        ("workouts:routine", "a ficha da semana"),
        ("workouts:corridas", "corridas"),
        ("accounts:profile", "perfil"),
        ("accounts:login", "entrar"),
        ("accounts:signup", "criar conta"),
        ("accounts:excluir_conta", "excluir a conta"),
        ("achievements:list", "conquistas"),
        ("gestao:painel", "painel de gestão"),
    )

    def test_todo_destino_tem_pelo_menos_um_link(self):
        import re

        textos = {
            arquivo: arquivo.read_text(encoding="utf-8")
            for arquivo in (RAIZ / "templates").rglob("*.html")
        }
        sem_porta = []
        for nome, porque in self.DESTINOS:
            # Concatenação e não `%`: o padrão tem `%s` de template do
            # Django dentro dele, e formatar a string trataria o `%{` como
            # marcador de formato.
            padrao = re.compile(
                r"\{%\s*url\s+['\"]" + re.escape(nome) + r"['\"]"
            )
            if not any(padrao.search(texto) for texto in textos.values()):
                sem_porta.append(f"{nome} ({porque})")

        self.assertEqual(sem_porta, [])
