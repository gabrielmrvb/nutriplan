# -*- coding: utf-8 -*-
"""A duração do treino saiu da tela — e o dado de quem já respondeu não sai.

ESTE ARQUIVO EXISTE PORQUE A SUÍTE COMPLETA ACHOU O DEFEITO, e o defeito era
sutil: com a pergunta fora da configuração, `Profile.duracao_treino` continuava
nascendo em `LIVRE`, "sem limite rígido". Enquanto a pergunta existia isso
estava certo — presumir um teto que ninguém pediu é pior que não ter teto. Sem
a pergunta, o argumento se inverte: quem entra hoje NÃO PODE responder, e todo
perfil novo montaria ficha sem limite nenhum. Medido: `abc2 C` sem teto tem
doze exercícios e 88 minutos, que é a ficha inteira para quem nunca a pediu.

São DUAS mudanças, e elas fazem coisas diferentes de propósito:

    0029  RunPython: `duracao_treino=""` -> "padrao". É REDE, não conserto.
          `""` não acontece pelo ORM (o campo sempre teve default), e a `0026`
          já converteu quem existia a partir do `duration_min`. Ela cobre linha
          escrita fora do ORM — fixture, SQL à mão, carga antiga.
    0030  AlterField do `default`: `livre` -> `padrao`. É o conserto, e ela
          NÃO TOCA EM LINHA NENHUMA. `manage.py sqlmigrate accounts 0030`
          imprime `-- (no-op)`: o Django resolve `default` na aplicação, então
          o PostgreSQL não recebe DDL de valor e não há UPDATE em massa.

A distinção que este arquivo prende, e que é a razão de ele ser grande: o
default governa QUEM NASCE AGORA; ele nunca reescreve QUEM JÁ ESCOLHEU. Uma
"simplificação" que convertesse os `livre` existentes apagaria a resposta de
quem pediu a ficha completa — e não há como distinguir essa pessoa de quem
recebeu `livre` por omissão, que é exatamente por que a `0030` não tem
`RunPython`.
"""
from datetime import date, time

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.forms import MINUTOS_POR_DURACAO
from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    DuracaoTreino,
    Goal,
    Profile,
    Sex,
    TrainingDay,
    User,
)


def _pessoa(email):
    return User.objects.create_user(email=email, password="senha-bem-forte-123")


def _perfil(user, **extra):
    """O perfil mínimo que o onboarding produz, SEM tocar em `duracao_treino`.

    É esse silêncio que o arquivo inteiro mede: o campo não é passado, então
    quem responde é o `default` do modelo.
    """
    campos = dict(
        sex=Sex.MALE,
        birth_date=date(1995, 4, 12),
        height_cm=178,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.BULK,
        wake_time=time(7, 0),
        sleep_time=time(23, 0),
    )
    campos.update(extra)
    return Profile.objects.create(user=user, **campos)


class ODefaultNasceEmPadraoTests(TestCase):
    """Todo caminho que cria `Profile` sem responder a pergunta cai em PADRÃO.

    Os caminhos são medidos um a um porque eles NÃO passam pelo mesmo código:
    o onboarding usa `ProfileForm`, o admin e os helpers constroem o modelo
    direto, e `get_or_create`/`update_or_create` têm semântica própria. Um
    default que valesse só no `create()` deixaria três portas abertas.
    """

    def test_create_sem_o_campo_nasce_em_padrao(self):
        perfil = _perfil(_pessoa("create@exemplo.com"))

        self.assertEqual(perfil.duracao_treino, DuracaoTreino.PADRAO)
        perfil.refresh_from_db()
        self.assertEqual(perfil.duracao_treino, DuracaoTreino.PADRAO)

    def test_o_construtor_direto_tambem(self):
        """`Profile(user=...)` seguido de `save()` — o caminho do admin e o de
        qualquer helper que monte o objeto antes de gravar."""
        perfil = Profile(
            user=_pessoa("construtor@exemplo.com"),
            sex=Sex.FEMALE,
            birth_date=date(1990, 1, 1),
            height_cm=165,
            activity_level=ActivityLevel.ACTIVE,
            goal=Goal.CUT,
            wake_time=time(6, 0),
            sleep_time=time(22, 0),
        )
        perfil.save()
        perfil.refresh_from_db()

        self.assertEqual(perfil.duracao_treino, DuracaoTreino.PADRAO)

    def test_get_or_create_e_update_or_create_tambem(self):
        um, criado = Profile.objects.get_or_create(
            user=_pessoa("goc@exemplo.com"),
            defaults=dict(
                sex=Sex.MALE, birth_date=date(1992, 2, 2), height_cm=180,
                activity_level=ActivityLevel.LIGHT, goal=Goal.MAINTAIN,
                wake_time=time(7, 0), sleep_time=time(23, 0),
            ),
        )
        outro, _ = Profile.objects.update_or_create(
            user=_pessoa("uoc@exemplo.com"),
            defaults=dict(
                sex=Sex.MALE, birth_date=date(1993, 3, 3), height_cm=182,
                activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
                wake_time=time(7, 0), sleep_time=time(23, 0),
            ),
        )

        self.assertTrue(criado)
        self.assertEqual(um.duracao_treino, DuracaoTreino.PADRAO)
        self.assertEqual(outro.duracao_treino, DuracaoTreino.PADRAO)

    def test_o_onboarding_termina_em_padrao_e_SEM_horario(self):
        """O caminho real de quem se cadastra hoje, andado por HTTP.

        As duas asserções são a mesma decisão vista de dois lados: nem a
        duração nem o horário são perguntados, e nenhum dos dois pode ser
        inventado para completar a conta. O horário fica `None` — e
        `plans/meal_planner.py` volta a distribuir o cardápio pela janela de
        sono, o mesmo caminho de quem não cadastrou dia de treino.
        """
        user = _pessoa("onboarding@exemplo.com")
        self.client.force_login(user)

        def passo(n, dados):
            return self.client.post(
                reverse("accounts:onboarding_step", kwargs={"step": n}), dados
            )

        passo(1, {
            "sex": Sex.MALE, "birth_date": "1995-04-12", "height_cm": "178",
            "weight_kg": "80.0",
        })
        passo(2, {"activity_level": ActivityLevel.LIGHT, "goal": Goal.BULK})
        passo(3, {
            "weekdays": ["0", "2", "4"],
            "experiencia": "intermediario",
            "wake_time": "07:00",
            "sleep_time": "23:00",
        })

        perfil = Profile.objects.get(user=user)
        self.assertEqual(perfil.duracao_treino, DuracaoTreino.PADRAO)
        self.assertEqual(
            [d.start_time for d in TrainingDay.objects.filter(user=user)],
            [None, None, None],
        )

    def test_o_teto_que_o_motor_recebe_e_de_45_a_60(self):
        """PADRÃO não é um rótulo: ele vira 60 minutos no `TrainingDay`, e é
        esse número que `plans/meal_planner.py` soma ao horário."""
        self.assertEqual(MINUTOS_POR_DURACAO[DuracaoTreino.PADRAO], 60)

        user = _pessoa("teto@exemplo.com")
        _perfil(user)
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)
        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {"weekdays": ["0", "2"], "experiencia": "intermediario",
             "wake_time": "07:00", "sleep_time": "23:00"},
        )

        self.assertEqual(
            sorted({d.duration_min for d in TrainingDay.objects.filter(user=user)}),
            [60],
        )


class QuemJaEscolheuNaoEReescritoTests(TestCase):
    """As quatro faixas sobrevivem ao salvamento, e o POST não as troca.

    O risco não é teórico: `TrainingForm.save()` reescreve `TrainingDay` a cada
    visita ao passo 3, e ele deriva `duration_min` do perfil. Um `or PADRAO`
    escrito no lugar errado — ou um campo escondido que voltasse a aceitar
    valor — apagaria a escolha de quem pediu 30 ou 90 minutos.
    """

    def _salvar_dias(self, user, extra=None):
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)
        corpo = {
            "weekdays": ["1", "3"],
            "experiencia": "intermediario",
            "wake_time": "07:00",
            "sleep_time": "23:00",
        }
        corpo.update(extra or {})
        return self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}), corpo
        )

    def test_as_quatro_faixas_atravessam_o_salvamento(self):
        for faixa, minutos in (
            (DuracaoTreino.RAPIDO, 30),
            (DuracaoTreino.PADRAO, 60),
            (DuracaoTreino.COMPLETO, 90),
            (DuracaoTreino.LIVRE, 90),
        ):
            with self.subTest(faixa=faixa):
                user = _pessoa("faixa-%s@exemplo.com" % faixa)
                _perfil(user, duracao_treino=faixa)
                self._salvar_dias(user)

                user.profile.refresh_from_db()
                self.assertEqual(user.profile.duracao_treino, faixa)
                self.assertEqual(
                    sorted({d.duration_min
                            for d in TrainingDay.objects.filter(user=user)}),
                    [minutos],
                )

    def test_post_adulterado_nao_troca_a_faixa_de_quem_escolheu(self):
        """`livre`, `completo` e `duration_min` postados à mão são IGNORADOS.

        O campo saiu do formulário; ele não virou campo escondido nem campo
        somente-leitura. Um POST forjado é a forma mais barata de descobrir a
        diferença — e a diferença importa, porque "sem limite rígido" muda a
        ficha inteira de quem o receber sem pedir.
        """
        user = _pessoa("forjado@exemplo.com")
        _perfil(user, duracao_treino=DuracaoTreino.RAPIDO)

        self._salvar_dias(user, {
            "duracao_treino": DuracaoTreino.LIVRE,
            "duration_min": "90",
        })

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.duracao_treino, DuracaoTreino.RAPIDO)
        self.assertEqual(
            sorted({d.duration_min for d in TrainingDay.objects.filter(user=user)}),
            [30],
        )

    def test_post_adulterado_nao_ressuscita_o_horario(self):
        """A outra metade do mesmo forjamento — e a que protege o cardápio.

        O horário JÁ GRAVADO tem de sobreviver: `plans/meal_planner.py` soma
        `start_time + duration_min` para não marcar refeição no meio do treino,
        e `update_or_create` com `start_time=None` nos defaults apagaria isso
        em silêncio.
        """
        user = _pessoa("horario-forjado@exemplo.com")
        _perfil(user)
        TrainingDay.objects.create(
            user=user, weekday=1, start_time=time(19, 0), duration_min=60
        )

        self._salvar_dias(user, {"start_time": "06:30"})

        horarios = {d.weekday: d.start_time
                    for d in TrainingDay.objects.filter(user=user)}
        self.assertEqual(horarios[1], time(19, 0), "o POST forjado mudou o horário")
        # E o dia que NASCEU agora não recebe horário nenhum: não há de onde
        # tirar um, e inventar 19:00 foi o defeito que a campanha anterior
        # corrigiu.
        self.assertIsNone(horarios[3])


class AsMigrationsDaDuracaoSaoPortaoDeDadosTests(TransactionTestCase):
    """As duas migrations rodadas DE VERDADE sobre linhas que já existem.

    `TransactionTestCase` porque migrar exige DDL, e DDL dentro da transação
    que o `TestCase` mantém aberta não se comporta. É o mesmo padrão de
    `plans.tests.MigracaoDoRankTests`.

    O que este teste prova é a rota do banco EXISTENTE: partir de `0028`,
    escrever uma linha de cada faixa mais uma linha em branco escrita fora do
    ORM, aplicar `0029` e `0030`, e conferir que só a linha em branco mudou.
    A rota do banco NOVO é o próprio banco de teste, que nasce rodando todas as
    migrations desde zero — e é ela que `ODefaultNasceEmPadraoTests` mede.
    """

    ANTES = ("accounts", "0028_experiencia_de_treino")
    DEPOIS = ("accounts", "0030_duracao_padrao_para_perfil_novo")

    def _migrar(self, alvo):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([alvo])
        return executor.loader.project_state([alvo]).apps

    def tearDown(self):
        # Devolve o banco ao estado final, senão os testes seguintes rodam
        # contra um schema anterior.
        self._migrar(self.DEPOIS)

    def test_so_a_linha_em_branco_muda_e_as_quatro_faixas_ficam(self):
        velho = self._migrar(self.ANTES)
        Usuario = velho.get_model("accounts", "User")
        PerfilVelho = velho.get_model("accounts", "Profile")

        escolhas = {
            "rapido": "rapido",
            "padrao": "padrao",
            "completo": "completo",
            "livre": "livre",
            "vazio": "",
        }
        pks = {}
        for nome, valor in escolhas.items():
            u = Usuario.objects.create(
                email="migracao-%s@exemplo.com" % nome, password="x"
            )
            p = PerfilVelho.objects.create(
                user=u, sex="M", birth_date=date(1995, 4, 12), height_cm=178,
                activity_level="light", goal="bulk",
                wake_time=time(7, 0), sleep_time=time(23, 0),
            )
            # DIRETO NO BANCO para o vazio: o ORM não consegue escrever `""`
            # neste campo, porque o default entra antes. É exatamente por isso
            # que a `0029` existe — a linha em branco só chega por fora.
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE accounts_profile SET duracao_treino = %s WHERE id = %s",
                    [valor, p.pk],
                )
            pks[nome] = p.pk

        novo = self._migrar(self.DEPOIS)
        PerfilNovo = novo.get_model("accounts", "Profile")
        depois = {
            nome: PerfilNovo.objects.get(pk=pk).duracao_treino
            for nome, pk in pks.items()
        }

        self.assertEqual(depois["rapido"], "rapido")
        self.assertEqual(depois["padrao"], "padrao")
        self.assertEqual(depois["completo"], "completo")
        self.assertEqual(
            depois["livre"], "livre",
            "quem escolheu 'sem limite rígido' foi reescrito pela migration",
        )
        self.assertEqual(
            depois["vazio"], "padrao",
            "a linha em branco não foi convertida pela 0029",
        )

    def test_a_migration_nao_regenera_rotina_nenhuma(self):
        """`AlterField` de default não escreve linha, e nada remonta ficha.

        A remontagem é da VISITA (`sync_active_routine`), e não da migration.
        Uma migration que tocasse `Profile` em massa e disparasse remontagem
        trocaria a ficha de todo mundo no deploy, no meio de um treino.
        """
        from workouts.models import TrainingPlan

        velho = self._migrar(self.ANTES)
        Usuario = velho.get_model("accounts", "User")
        PerfilVelho = velho.get_model("accounts", "Profile")
        u = Usuario.objects.create(email="rotina@exemplo.com", password="x")
        PerfilVelho.objects.create(
            user=u, sex="M", birth_date=date(1995, 4, 12), height_cm=178,
            activity_level="light", goal="bulk",
            wake_time=time(7, 0), sleep_time=time(23, 0),
            duracao_treino="completo",
        )
        antes = TrainingPlan.objects.count()

        self._migrar(self.DEPOIS)

        self.assertEqual(TrainingPlan.objects.count(), antes)
        self.assertEqual(
            PerfilVelho._default_manager.filter(pk=u.profile.pk).count(), 1
        )
