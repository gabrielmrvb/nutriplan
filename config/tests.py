"""Testes da configuração de produção.

O que quebra num deploy raramente é a regra de negócio — é a configuração:
estático sem manifesto, host fora da lista, redirecionamento em laço. Nada
disso aparece em desenvolvimento, e todos aparecem para o primeiro visitante.
Estes testes exercitam justamente o que só existe com `DEBUG=False`.
"""
import inspect
import re
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, TestCase, override_settings
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
    call_command("seed_supplements", verbosity=0)


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
        (".swap-open {", "min-height: 2.75rem"),
        (".shopping__check {", "min-height: 2.75rem"),
        (".set-row__input {", "min-height: 2.75rem"),
        (".install__close {", "height: 2.75rem"),
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

        # A barra empilhada do topo tem a mesma regra.
        self.assertIn(".macro-bar__part { transition: width .5s", self.css)

    def test_pressing_anything_uses_the_same_scale(self):
        """Duas escalas diferentes no mesmo gesto é o tipo de inconsistência
        que ninguém aponta e todo mundo sente. Já houve: a lista geral
        encolhia 2% e o cartão do onboarding, 1%."""
        escalas = set(re.findall(r":active[^{]*\{[^}]*transform:\s*scale\(([^)]+)\)", self.css))
        self.assertEqual(escalas, {".98"}, f"escalas de toque divergentes: {escalas}")

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
            ".set-row--done .set-row__label",
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
        for comando in ("seed_catalog", "seed_workouts", "seed_supplements"):
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
