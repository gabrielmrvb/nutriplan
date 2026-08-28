"""O modo demo: público, somente leitura, e sem dado de ninguém.

O que estes testes protegem não é a aparência do demo — é a promessa dele. Um
ambiente público montado sobre o banco de produção só é seguro enquanto duas
coisas continuarem verdadeiras: nenhuma requisição dele escreve, e nenhuma
tela dele alcança outro usuário.
"""
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Profile, User
from demo.middleware import DEMO_EMAIL
from plans.models import HydrationLog, MealLog, MealStatus
from workouts.models import ExerciseLog

AREA = r'class="demo-area" href="([^"]+)"'
LINK = r'(?:href|action)="(/[^"]*)"'


def _semear():
    call_command("seed_catalog", verbosity=0)
    call_command("seed_workouts", verbosity=0)
    call_command("seed_demo", verbosity=0)


class DemoNavegacaoTests(TestCase):
    """Entrar em /demo e chegar em todo lugar, sem login."""

    @classmethod
    def setUpTestData(cls):
        _semear()

    def test_the_cover_opens_without_a_session(self):
        resposta = self.client.get("/demo/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Carlos")

    def test_every_area_on_the_cover_answers_without_a_login(self):
        """A regra mais importante do demo: nenhum caminho cai em tela de
        entrar. Um 302 para o login é o beco sem saída que o demo existe para
        não ter."""
        html = self.client.get("/demo/").content.decode()
        areas = re.findall(AREA, html)
        self.assertGreaterEqual(len(areas), 5, "a capa perdeu as áreas")

        for endereco in areas:
            with self.subTest(area=endereco):
                self.assertEqual(self.client.get(endereco).status_code, 200)

    def test_navigation_inside_the_demo_never_points_outside_it(self):
        """`set_script_prefix` é o que faz a barra de abas e os formulários do
        template REAL apontarem para dentro do demo sozinhos. Se ele parar de
        funcionar, o primeiro toque na navegação joga a pessoa no login."""
        for pagina in ("/demo/treino/", "/demo/hoje/", "/demo/historico/"):
            html = self.client.get(pagina).content.decode()
            fora = sorted(
                e
                for e in set(re.findall(LINK, html))
                if not e.startswith("/demo") and not e.startswith("/static")
            )
            with self.subTest(pagina=pagina):
                self.assertEqual(fora, [], f"link para fora do demo: {fora}")

    def test_the_badge_says_it_is_a_demo_on_every_screen(self):
        for pagina in ("/demo/", "/demo/hoje/", "/demo/treino/", "/demo/conta/perfil/"):
            with self.subTest(pagina=pagina):
                self.assertContains(self.client.get(pagina), "app-bar__demo")

    def test_the_about_page_says_the_data_is_invented(self):
        self.assertContains(self.client.get("/demo/sobre/"), "fict")

    def test_the_real_app_is_untouched_and_still_asks_for_a_login(self):
        """A trava mais importante do middleware: fora de `/demo/`, nada muda.
        Se o prefixo vazasse, o app inteiro ficaria público."""
        for pagina in ("/", "/treino/", "/conta/perfil/"):
            with self.subTest(pagina=pagina):
                resposta = self.client.get(pagina)
                self.assertEqual(resposta.status_code, 302)
                self.assertIn("entrar", resposta["Location"])


class DemoSomenteLeituraTests(TestCase):
    """Nenhuma requisição do demo escreve. Nenhuma."""

    @classmethod
    def setUpTestData(cls):
        _semear()

    def _contagens(self):
        return (
            MealLog.objects.count(),
            HydrationLog.objects.count(),
            ExerciseLog.objects.count(),
            Profile.objects.count(),
            User.objects.count(),
        )

    def test_no_post_inside_the_demo_changes_anything(self):
        """A garantia vale por MÉTODO, e não por rota conferida uma a uma.

        Proteger botão por botão depende de eu lembrar de todos — hoje, e no
        próximo recurso. Recusar tudo que não é leitura não depende de memória.
        """
        antes = self._contagens()

        for endereco, dados in (
            ("/demo/agua/", {"ml": "250"}),
            ("/demo/refeicao/1/marcar/", {"status": "done", "option": "1"}),
            ("/demo/treino/exercicio/1/carga/", {"weight_kg": "100"}),
            ("/demo/conta/perfil/", {"height_cm": "999"}),
            ("/demo/conta/onboarding/1/", {"sex": "F", "height_cm": "150"}),
        ):
            with self.subTest(endereco=endereco):
                resposta = self.client.post(endereco, dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "somente leitura")

        self.assertEqual(self._contagens(), antes)

    def test_delete_and_put_are_refused_too(self):
        antes = self._contagens()
        self.assertEqual(self.client.delete("/demo/agua/").status_code, 200)
        self.assertEqual(self.client.put("/demo/agua/").status_code, 200)
        self.assertEqual(self._contagens(), antes)

    def test_the_demo_account_cannot_be_logged_into(self):
        """Senha inutilizável: a conta existe para o middleware LER, e não
        para alguém entrar nela pela tela de login."""
        usuario = get_user_model().objects.get(email=DEMO_EMAIL)
        self.assertFalse(usuario.has_usable_password())

    def test_no_other_user_is_ever_reachable_from_the_demo(self):
        """As telas leem sempre `request.user`, e no demo ele é sempre o
        Carlos. Este teste cria outra pessoa e confere que ela não aparece."""
        outra = User.objects.create_user(
            email="pessoa.real@exemplo.com",
            password="senha-bem-forte-123",
            first_name="Gabriela",
        )
        Profile.objects.create(
            user=outra,
            sex="F",
            birth_date="1990-01-01",
            height_cm=165,
            onboarding_step=99,
        )

        html = "".join(
            self.client.get(p).content.decode()
            for p in ("/demo/", "/demo/hoje/", "/demo/conta/perfil/", "/demo/historico/")
        )
        self.assertNotIn("Gabriela", html)
        self.assertNotIn(outra.email, html)
        self.assertIn("Carlos", html)


class DemoDadosTests(TestCase):
    """Carlos Silva sai do MOTOR, e não de valores escritos à mão."""

    @classmethod
    def setUpTestData(cls):
        _semear()

    def setUp(self):
        self.pessoa = get_user_model().objects.get(email=DEMO_EMAIL)

    def test_the_persona_matches_what_the_cover_promises(self):
        perfil = self.pessoa.profile
        self.assertEqual(self.pessoa.first_name, "Carlos")
        self.assertEqual(perfil.age, 28)
        self.assertEqual(perfil.height_cm, 178)
        self.assertEqual(perfil.current_weight, Decimal("78.00"))
        self.assertEqual(perfil.get_goal_display(), "Ganhar massa")

    def test_the_plan_and_the_routine_came_from_the_real_engine(self):
        """Se o plano fosse escrito à mão, o demo passaria a mostrar números
        que o app não produz — e divergiria mais a cada mudança do motor."""
        plano = self.pessoa.plans.get(is_active=True)
        ficha = self.pessoa.training_plans.get(is_active=True)

        self.assertGreater(plano.target_kcal, 2000)
        self.assertEqual(plano.slots.count(), 5)
        self.assertEqual(ficha.sessions.count(), 3)
        self.assertTrue(all(s.exercises.exists() for s in ficha.sessions.all()))

    def test_the_day_is_half_lived_so_both_states_are_visible(self):
        """Dia em branco esconde a barra de progresso e o cartão de refeição
        concluída; dia cheio esconde o botão de marcar. Metade mostra os dois.

        `date=hoje` e não todos os registros: quando as duas semanas de
        histórico entraram, este teste passou a contar 67 refeições contra 5
        horários e falhou — a pergunta dele sempre foi sobre HOJE.
        """
        hoje = timezone.localdate()
        registros = MealLog.objects.filter(user=self.pessoa, date=hoje)
        plano = self.pessoa.plans.get(is_active=True)

        self.assertGreater(registros.count(), 0)
        self.assertLess(registros.count(), plano.slots.count())

    def test_running_the_seed_twice_does_not_duplicate_the_persona(self):
        call_command("seed_demo", verbosity=0)
        self.assertEqual(get_user_model().objects.filter(email=DEMO_EMAIL).count(), 1)


class DemoSemSaidaParaLoginTests(TestCase):
    """Nenhuma tela do demo oferece uma porta para a tela de entrar.

    Este e o defeito que estava EM PRODUCAO e so apareceu quando eu testei a
    URL publica: a capa rodava por fora do prefixo de script, entao ela
    renderizava com visitante anonimo — e a barra de cima, vendo visitante,
    mostrava "Entrar" e "Criar conta".

    Duas saidas do demo direto para o login, na primeira tela que a pessoa ve.
    Os testes anteriores nao pegavam porque conferiam a navegacao DENTRO das
    telas do app, onde o usuario ja era o Carlos.
    """

    @classmethod
    def setUpTestData(cls):
        _semear()

    TELAS = (
        "/demo/",
        "/demo/sobre/",
        "/demo/hoje/",
        "/demo/treino/",
        "/demo/suplementos/",
        "/demo/historico/",
        "/demo/lista-de-compras/",
        "/demo/conta/perfil/",
    )

    def test_no_demo_screen_links_to_the_login_or_the_signup(self):
        for tela in self.TELAS:
            html = self.client.get(tela).content.decode()
            with self.subTest(tela=tela):
                self.assertNotIn("/conta/entrar/", html)
                self.assertNotIn("/conta/cadastro/", html)

    def test_the_cover_renders_as_the_demo_person_and_not_as_a_visitor(self):
        """O sintoma foi a barra de cima; a causa foi o usuario. Travar o
        usuario e travar a familia inteira de defeitos."""
        html = self.client.get("/demo/").content.decode()
        self.assertIn("app-bar__demo", html)
        self.assertIn("Sobre o demo", html)
        self.assertNotIn("Criar conta", html)

    def test_there_is_no_logout_button_to_press(self):
        """Nao ha sessao para encerrar, e o formulario e um POST — que o
        middleware recusa. Botao que devolve pagina de erro e pior que botao
        nenhum."""
        for tela in ("/demo/", "/demo/treino/"):
            with self.subTest(tela=tela):
                self.assertNotIn(
                    "accounts:logout", self.client.get(tela).content.decode()
                )
                self.assertNotIn("/conta/sair/", self.client.get(tela).content.decode())

    def test_every_screen_says_the_data_is_invented(self):
        for tela in self.TELAS:
            with self.subTest(tela=tela):
                self.assertContains(self.client.get(tela), "dados apresentados")


class DemoTelasNaoFicamVaziasTests(TestCase):
    """Nenhuma tela do demo mostra um grafico de uma barra so.

    O demo existe para ser analisado, e tela vazia nao mostra o que o app faz.
    Pior: a de metricas mostrava numero VERDADEIRO com conclusao errada — com
    so o dia de hoje registrado, ela anunciava "os ultimos 14 dias" e uma media
    de 966 kcal/dia contra a meta de 2765.
    """

    @classmethod
    def setUpTestData(cls):
        _semear()

    def setUp(self):
        self.pessoa = get_user_model().objects.get(email=DEMO_EMAIL)

    def test_the_metrics_screen_has_two_weeks_of_days_to_draw(self):
        dias = (
            MealLog.objects.filter(user=self.pessoa)
            .values("date")
            .distinct()
            .count()
        )
        self.assertGreaterEqual(dias, 14)

    def test_the_history_shows_all_three_states_a_meal_can_be_in(self):
        """Concluida, pulada e "comi outra coisa". Duas semanas com 100% de
        aderencia nao provam que a tela sabe desenhar as outras duas."""
        estados = set(
            MealLog.objects.filter(user=self.pessoa).values_list("status", flat=True)
        )
        self.assertEqual(
            estados,
            {MealStatus.DONE, MealStatus.SKIPPED, MealStatus.OFF_PLAN},
        )

    def test_the_adherence_is_high_but_not_perfect(self):
        """100% em duas semanas le como dado inventado — porque e."""
        total = MealLog.objects.filter(user=self.pessoa).count()
        no_plano = MealLog.objects.filter(
            user=self.pessoa, status=MealStatus.DONE
        ).count()
        taxa = no_plano / total
        self.assertGreater(taxa, 0.8)
        self.assertLess(taxa, 1.0)

    def test_every_exercise_of_every_day_has_a_previous_load(self):
        """"Ultimo treino" e a seta de progressao sao o que a tela de treino
        tem de mais proprio. A primeira versao semeava so a sessao de segunda,
        e quem abrisse numa quarta caia num dia de tracos."""
        ficha = self.pessoa.training_plans.get(is_active=True)
        for sessao in ficha.sessions.all():
            for item in sessao.exercises.select_related("exercise").all():
                if item.exercise.equipment == "bodyweight":
                    continue  # peso do corpo nao registra carga
                with self.subTest(dia=sessao.label, exercicio=item.exercise.name):
                    self.assertTrue(
                        ExerciseLog.objects.filter(
                            user=self.pessoa, exercise=item.exercise
                        ).exists()
                    )

    def test_no_load_is_a_weight_a_gym_cannot_assemble(self):
        """Academia tem anilha de 2,5 em 2,5. "26,22 kg" e o tipo de numero que
        entrega que a tela foi semeada."""
        for peso in ExerciseLog.objects.filter(user=self.pessoa).values_list(
            "weight_kg", flat=True
        ):
            with self.subTest(peso=peso):
                self.assertEqual(peso % Decimal("2.5"), 0)

    def test_bodyweight_exercises_never_get_a_load(self):
        """Registrar quilo numa flexao mentiria sobre o que foi feito, e o
        traco na tela e a informacao certa."""
        for log in ExerciseLog.objects.filter(user=self.pessoa).select_related(
            "exercise"
        ):
            with self.subTest(exercicio=log.exercise.name):
                self.assertNotEqual(log.exercise.equipment, "bodyweight")

    def test_the_screens_all_have_something_to_read(self):
        """A regra bruta contra tela em branco: se o miolo tem menos de 400
        caracteres, alguma coisa nao carregou."""
        for tela in (
            "/demo/",
            "/demo/hoje/",
            "/demo/treino/",
            "/demo/historico/",
            "/demo/suplementos/",
            "/demo/lista-de-compras/",
            "/demo/conta/perfil/",
        ):
            html = self.client.get(tela).content.decode()
            miolo = html.split('<main class="container', 1)[1].split("</main>", 1)[0]
            texto = re.sub(r"<[^>]+>", " ", miolo)
            texto = re.sub(r"\s+", " ", texto).strip()
            with self.subTest(tela=tela):
                self.assertGreater(len(texto), 400, f"{tela} parece vazia")


class DemoCadaRotaMostraSuaTelaTests(TestCase):
    """Cada endereço do demo mostra a tela que promete.

    Este teste existe por uma regressão que foi para PRODUÇÃO. Quando a capa
    passou a rodar dentro do prefixo de script, ela passou a ocupar `/` — e o
    apelido `/hoje/`, que aponta para `/`, passou a servir a capa em vez do
    painel do dia.

    Os testes anteriores não viram porque conferiam o CÓDIGO DE RESPOSTA. As
    duas rotas devolviam 200, com o mesmo HTML, e ninguém perguntou qual HTML.
    """

    @classmethod
    def setUpTestData(cls):
        _semear()

    #: (rota, um trecho que só aquela tela tem)
    TELAS = (
        ("/demo/", "As telas do aplicativo"),
        ("/demo/sobre/", "Sobre esta demonstra"),
        ("/demo/hoje/", "kcal hoje"),
        ("/demo/treino/", "exercise__ver"),
        ("/demo/historico/", "Ader"),
        ("/demo/lista-de-compras/", "shopping"),
        ("/demo/conta/perfil/", "Meu perfil"),
    )

    def test_each_route_renders_its_own_screen(self):
        for rota, marca in self.TELAS:
            with self.subTest(rota=rota):
                self.assertContains(self.client.get(rota), marca)

    def test_no_two_routes_return_the_same_page(self):
        """A prova direta da regressão: duas rotas com o mesmo HTML significa
        que uma delas perdeu a própria tela."""
        vistos = {}
        for rota, _ in self.TELAS:
            corpo = self.client.get(rota).content
            anterior = vistos.get(corpo)
            self.assertIsNone(
                anterior, f"{rota} devolve exatamente o mesmo HTML que {anterior}"
            )
            vistos[corpo] = rota

    def test_the_dashboard_alias_is_the_dashboard_and_not_the_cover(self):
        painel = self.client.get("/demo/hoje/").content.decode()
        capa = self.client.get("/demo/").content.decode()

        self.assertIn("<title>Hoje", painel)
        self.assertIn("Demonstra", capa.split("<title>", 1)[1][:40])


class DemoNaoApodreceComOTempoTests(TestCase):
    """O dia do Carlos se refaz quando a data vira.

    O seed escreve "hoje" no dia em que roda, e o Render só roda o seed em
    deploy. Um dia depois, "hoje" é ontem: o painel abre com o anel em zero,
    nenhuma refeição marcada e nenhuma água. Quem chegasse ao demo veria um app
    que parece nunca ter sido usado — e foi assim que eu encontrei o defeito,
    abrindo a tela no dia seguinte ao da semeadura.
    """

    @classmethod
    def setUpTestData(cls):
        _semear()

    def setUp(self):
        self.pessoa = get_user_model().objects.get(email=DEMO_EMAIL)

    def test_an_empty_day_is_refilled_when_someone_opens_the_demo(self):
        hoje = timezone.localdate()
        MealLog.objects.filter(user=self.pessoa, date=hoje).delete()
        HydrationLog.objects.filter(user=self.pessoa, date=hoje).delete()

        self.client.get("/demo/hoje/")

        self.assertTrue(MealLog.objects.filter(user=self.pessoa, date=hoje).exists())
        self.assertTrue(
            HydrationLog.objects.filter(user=self.pessoa, date=hoje).exists()
        )

    def test_the_refill_keeps_the_day_half_lived(self):
        """Meio dia, e não o dia inteiro: em branco esconde a barra de
        progresso e o cartão de refeição concluída; cheio esconde o botão de
        marcar."""
        hoje = timezone.localdate()
        MealLog.objects.filter(user=self.pessoa, date=hoje).delete()
        self.client.get("/demo/hoje/")

        plano = self.pessoa.plans.get(is_active=True)
        marcadas = MealLog.objects.filter(user=self.pessoa, date=hoje).count()
        self.assertGreater(marcadas, 0)
        self.assertLess(marcadas, plano.slots.count())

    def test_a_day_that_is_already_full_is_left_alone(self):
        """A recarga é só para o dia VAZIO. Refazer a cada visita apagaria o
        que a semeadura acabou de montar, a cada pedido."""
        hoje = timezone.localdate()
        self.client.get("/demo/hoje/")
        antes = set(
            MealLog.objects.filter(user=self.pessoa, date=hoje).values_list(
                "pk", flat=True
            )
        )

        self.client.get("/demo/hoje/")
        depois = set(
            MealLog.objects.filter(user=self.pessoa, date=hoje).values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(antes, depois)

    def test_the_refill_never_reaches_anyone_else(self):
        """A recarga é uma escrita num pedido de leitura, que é o que o
        middleware recusa logo acima dela. O que a torna aceitável é o alcance:
        só o usuário fictício, só o dia de hoje."""
        outra = User.objects.create_user(
            email="pessoa.real2@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=outra, sex="M", birth_date="1990-01-01", height_cm=180,
            onboarding_step=99,
        )
        antes = MealLog.objects.filter(user=outra).count()

        MealLog.objects.filter(user=self.pessoa, date=timezone.localdate()).delete()
        self.client.get("/demo/hoje/")

        self.assertEqual(MealLog.objects.filter(user=outra).count(), antes)
