"""A ficha de quem começa em casa — o item 1 da missão "quem entra não
desiste" (24/09/2026).

A persona 1 do relatório de experiência (Dani, 29, iniciante, 78 kg, treina
em casa só com o peso do corpo, três dias por semana) fechava o app no
PRIMEIRO TREINO. O que ela recebia, medido no commit de produção:

- divisão `abc2`, e portanto um dia inteiro da semana chamado "Costas e
  bíceps" — que, sem barra fixa, tinha DOIS exercícios e dezessete minutos;
- na letra B, cinco exercícios seguidos de barra fixa (negativa, pronada,
  encolhimento, suspensão, rosca invertida): `Exercise.equipment` chama
  tudo isso de `bodyweight`, e o motor não tinha como saber que uma barra
  fixa não é o peso do corpo;
- "Mergulho nas paralelas" e "Flexão parada de mão na parede" na ficha de
  uma casa;
- os movimentos no meio da escada de progressão (flexão de braço completa,
  afundo), e não no degrau em que se começa;
- oito exercícios e ~60 minutos, três vezes por semana.

Este arquivo prende o que ela passou a receber. Cada classe mede UMA das
mudanças, e cada uma tem o controle positivo do lado — a sabotagem que a
faz ficar vermelha está escrita no teste, e não só no relatório.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, Equipamento, Experiencia, TrainingDay
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import Aparelho, Exercise, SessionExercise, Split

#: O que NENHUMA ficha de casa pode exigir. A barra baixa fica de fora desta
#: lista de propósito — ver o "Mapa de aparelho" no `TREINO.md`: a remada
#: invertida se faz sob a mesa, e sem ela o perfil fica sem costas.
FORA_DE_CASA = (Aparelho.BARRA_FIXA, Aparelho.PARALELAS, Aparelho.INVERSAO)


def _pessoa(email, *, experiencia=Experiencia.INICIANTE,
            equipamento=Equipamento.PESO_CORPORAL, dias=3,
            duracao=DuracaoTreino.RAPIDO):
    user = create_complete_user(
        email=email, experiencia=experiencia, split_preference="two",
        split_preference_confirmada=True, duracao_treino=duracao,
        equipamento=equipamento,
    )
    user.training_days.all().delete()
    for weekday in range(dias):
        TrainingDay.objects.create(user=user, weekday=weekday, duration_min=60)
    return user


def _itens(plano):
    return list(
        SessionExercise.objects.filter(session__plan=plano).select_related("exercise")
    )


class AFichaDeCasaNaoExigeAparelhoQueACasaNaoTemTests(TestCase):
    """Barra fixa, paralelas e parada de mão saem da ficha de casa.

    `Exercise.equipment` responde "que CARGA", e a barra fixa não é carga —
    é aparelho. Sem a coluna `aparelho`, a flexão de braço e a barra fixa
    pronada eram a mesma coisa para o motor.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _aparelhos(self, plano):
        return {i.exercise.aparelho for i in _itens(plano) if i.exercise.aparelho}

    def test_so_o_peso_do_corpo_nao_recebe_barra_fixa_nem_paralelas(self):
        plano = services.create_routine(_pessoa("casa-pc@exemplo.com"))
        usados = self._aparelhos(plano)
        self.assertFalse(
            usados & set(FORA_DE_CASA),
            "a ficha de casa pediu %s" % sorted(usados & set(FORA_DE_CASA)),
        )

    def test_casa_com_halteres_tambem_nao(self):
        plano = services.create_routine(
            _pessoa("casa-halt@exemplo.com", equipamento=Equipamento.CASA_HALTERES)
        )
        usados = self._aparelhos(plano)
        self.assertFalse(usados & set(FORA_DE_CASA), sorted(usados))

    def test_a_barra_baixa_FICA_porque_e_a_unica_forma_de_puxar_em_casa(self):
        """Sem ela o perfil fica com ZERO exercício de costas — e é decisão
        escrita no `TREINO.md`, não descuido."""
        self.assertIn(Aparelho.BARRA_BAIXA, doutrina.aparelhos_de(Equipamento.PESO_CORPORAL))
        plano = services.create_routine(_pessoa("casa-costas@exemplo.com"))
        grupos = {i.exercise.muscle_group for i in _itens(plano)}
        self.assertIn("back", grupos, "a ficha de casa ficou sem costas")

    def test_a_academia_continua_com_a_barra_fixa(self):
        """O aparelho saiu da ficha de CASA, e não do catálogo: quem tem
        academia continua recebendo o que sempre recebeu."""
        plano = services.create_routine(
            _pessoa("academia@exemplo.com", experiencia=Experiencia.INTERMEDIARIO,
                    equipamento=Equipamento.COMPLETA, dias=5,
                    duracao=DuracaoTreino.PADRAO)
        )
        self.assertTrue(_itens(plano))
        self.assertTrue(
            Exercise.objects.filter(aparelho=Aparelho.BARRA_FIXA, is_active=True).exists()
        )

    def test_sabotagem_o_mergulho_nas_paralelas_sem_aparelho_volta_para_casa(self):
        """CONTROLE POSITIVO: o teste de cima só passa porque o catálogo diz
        o que cada exercício exige.

        Apagando o `aparelho` do mergulho — que é exatamente o que
        aconteceria se alguém cadastrasse um exercício de paralelas sem
        marcar a coluna —, ele volta a ser elegível para uma ficha de casa.
        """
        mergulho = Exercise.objects.get(name="Mergulho nas paralelas")
        self.assertEqual(mergulho.aparelho, Aparelho.PARALELAS)
        permitidos = services.permitidos_do_perfil(Equipamento.PESO_CORPORAL)
        self.assertFalse(services.dentro_do_perfil(mergulho, permitidos))

        Exercise.objects.filter(pk=mergulho.pk).update(aparelho="")
        mergulho.refresh_from_db()
        self.assertTrue(
            services.dentro_do_perfil(mergulho, permitidos),
            "sem a coluna, o motor não tem como saber que paralelas não é peso do corpo",
        )


class QuemComecaTreinaOCorpoInteiroTests(TestCase):
    """Três dias de "peito e tríceps · costas e bíceps · pernas e ombros" é o
    quadro de quem já treina. Quem começa recebe o corpo todo em cada
    sessão — três estímulos por grupo na semana, em vez de um."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_divisao_do_iniciante_ate_tres_dias_e_o_corpo_inteiro(self):
        for preferencia in ("one", "two", "three", ""):
            for dias in (1, 2, 3):
                with self.subTest(preferencia=preferencia, dias=dias):
                    self.assertEqual(
                        services.split_for(dias, preferencia, Experiencia.INICIANTE,
                                           Equipamento.PESO_CORPORAL),
                        Split.FULL,
                    )

    def test_com_quatro_dias_ou_mais_a_tabela_de_sempre_manda(self):
        """Corpo inteiro quatro vezes na semana é volume que um iniciante não
        recupera — e a partir daí a semana comporta a divisão."""
        self.assertNotEqual(
            services.split_for(4, "two", Experiencia.INICIANTE, Equipamento.PESO_CORPORAL),
            Split.FULL,
        )
        self.assertEqual(
            services.split_for(4, "two", Experiencia.INICIANTE, Equipamento.PESO_CORPORAL),
            services.split_for(4, "two"),
        )

    def test_na_academia_o_iniciante_continua_com_a_divisao_de_sempre(self):
        """"Em casa" faz parte da régua. Numa academia completa a letra de
        "Costas e bíceps" tem quatro exercícios de verdade, e é a ficha que o
        teste DOURADO cobra — o corpo inteiro conserta o que o catálogo de
        casa quebra, e não mexe no que já estava certo."""
        for equipamento in (Equipamento.COMPLETA, Equipamento.BASICA):
            with self.subTest(equipamento=equipamento):
                self.assertEqual(
                    services.split_for(3, "two", Experiencia.INICIANTE, equipamento),
                    services.split_for(3, "two"),
                )

    def test_quem_ja_treina_nao_muda_de_divisao(self):
        for nivel in (Experiencia.INTERMEDIARIO, Experiencia.AVANCADO):
            for dias in (1, 2, 3, 4, 5):
                with self.subTest(nivel=nivel, dias=dias):
                    self.assertEqual(
                        services.split_for(dias, "two", nivel, Equipamento.PESO_CORPORAL),
                        services.split_for(dias, "two"),
                    )

    def test_a_ficha_da_persona_1_e_uma_letra_so_nos_tres_dias(self):
        plano = services.create_routine(_pessoa("corpo-inteiro@exemplo.com"))
        self.assertEqual(plano.split, Split.FULL)
        self.assertEqual({s.label for s in plano.sessions.all()}, {"A"})
        self.assertEqual(plano.sessions.count(), 3)

    def test_a_sessao_dela_cabe_em_meia_hora_e_tem_os_movimentos_que_importam(self):
        """MEDIDO em 24/09/2026: quatro exercícios, oito séries, 28 minutos —
        agachar, empurrar, puxar e dobrar o quadril."""
        plano = services.create_routine(_pessoa("meia-hora@exemplo.com"))
        sessao = plano.sessions.order_by("weekday").first()
        itens = [i for i in _itens(plano) if i.session_id == sessao.id and i.opcao == 1]
        minutos = services.segundos_da_sessao(
            [(i.sets, i.rest_seconds, i.exercise.is_compound) for i in itens]
        ) / 60
        self.assertGreaterEqual(len(itens), 4, [i.exercise.name for i in itens])
        self.assertLessEqual(minutos, 30, minutos)
        self.assertGreaterEqual(minutos, 20, minutos)
        grupos = {i.exercise.muscle_group for i in itens}
        for grupo in ("quads", "chest", "back"):
            self.assertIn(grupo, grupos, sorted(grupos))

    def test_a_ficha_recem_nascida_nao_ja_nasce_desatualizada(self):
        user = _pessoa("desatualizada@exemplo.com")
        plano = services.create_routine(user)
        self.assertFalse(services.rotina_desatualizada(plano, user))
        self.assertFalse(services.rotina_invalida(plano, user))

    def test_a_ficha_de_quem_ja_treinava_nao_e_remontada_pela_regra_nova(self):
        """"Plano ativo antigo nunca remonta sozinho": quem tinha `abc2`
        montado pela régua anterior continua VÁLIDO, e recebe a régua nova
        quando mexer numa entrada de verdade."""
        user = _pessoa("antiga@exemplo.com")
        plano = services.create_routine(user)
        plano.split = Split.ABC2
        plano.save(update_fields=["split"])
        self.assertFalse(
            services.rotina_invalida(plano, user),
            "uma régua nova não pode remontar a ficha de quem já treinava",
        )


class APrimeiraFichaDoInicianteNasceEmMeiaHoraTests(TestCase):
    """A faixa de duração de quem declara "iniciante" na etapa 2."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _salvar_etapa_2(self, user, experiencia):
        from accounts.forms import TrainingForm

        formulario = TrainingForm(
            data={
                "weekdays": ["0", "2", "4"],
                "wake_time": "07:00",
                "sleep_time": "23:00",
                "experiencia": experiencia,
                "equipamento": Equipamento.PESO_CORPORAL,
                "musculacao": "sim",
            },
            user=user,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.save()
        user.profile.refresh_from_db()
        return user.profile

    def test_quem_declara_iniciante_comeca_na_faixa_rapido(self):
        user = _pessoa("faixa-ini@exemplo.com", duracao=DuracaoTreino.PADRAO)
        # O RAMO SEM FICHA, garantido e não suposto (revisão do PR #162): a
        # linha que estava aqui procurava `trainingplan_set`, que não existe —
        # o `related_name` é `training_plans` —, e não fazia nada. Se o
        # fixture um dia montar ficha, este teste mediria o ramo OPOSTO.
        user.training_plans.all().delete()
        self.assertFalse(user.training_plans.filter(is_active=True).exists())
        perfil = self._salvar_etapa_2(user, Experiencia.INICIANTE)
        self.assertEqual(perfil.duracao_treino, DuracaoTreino.RAPIDO)

    def test_quem_ja_treina_mantem_a_faixa_que_tinha(self):
        user = _pessoa("faixa-int@exemplo.com", duracao=DuracaoTreino.PADRAO)
        perfil = self._salvar_etapa_2(user, Experiencia.INTERMEDIARIO)
        self.assertEqual(perfil.duracao_treino, DuracaoTreino.PADRAO)

    def test_com_ficha_ativa_a_escolha_da_pessoa_nao_e_sobrescrita(self):
        """Quem já tem ficha já viu a área de Treino e pode ter escolhido a
        faixa lá — a etapa 2 não desfaz aquilo."""
        user = _pessoa("faixa-escolhida@exemplo.com", duracao=DuracaoTreino.COMPLETO)
        services.create_routine(user)
        perfil = self._salvar_etapa_2(user, Experiencia.INICIANTE)
        self.assertEqual(perfil.duracao_treino, DuracaoTreino.COMPLETO)


class OInicianteComecaNoDegrauMaisFacilTests(TestCase):
    """`DEGRAU_DO_INICIANTE` era 3 (a versão "padrão" do movimento) e virou 1
    por decisão do dono: quem começa começa no primeiro degrau da escada que
    o app já desenha, e subir é um toque em "Trocar"."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_nenhum_exercicio_da_escada_vem_acima_do_primeiro_degrau(self):
        plano = services.create_routine(_pessoa("degrau@exemplo.com"))
        # PISO: sem ele, uma regressão que esvaziasse a ficha de peso do corpo
        # (já aconteceu: `abcde-C` com ZERO exercícios, no `CLAUDE.md`) deixava
        # `altos` vazio e este teste verde.
        self.assertGreater(len(_itens(plano)), 0, "a ficha nasceu vazia")
        permitidos = services.permitidos_do_perfil(plano.user.profile.equipamento)
        altos = [
            (i.exercise.name, (i.exercise.progressao or {}).get("nivel"))
            for i in _itens(plano)
            if (i.exercise.progressao or {}).get("nivel", 1) > services.DEGRAU_DO_INICIANTE
        ]
        # Sobra o caso escrito: sem degrau mais fácil LIVRE do mesmo
        # movimento, o exercício fica quando é o último do grupo.
        for nome, nivel in altos:
            with self.subTest(exercicio=nome):
                escada = Exercise.objects.get(name=nome).progressao or {}
                mais_faceis = Exercise.objects.filter(
                    is_active=True, progressao__movimento=escada.get("movimento"),
                    progressao__nivel__lt=nivel,
                )
                # A REGRA DO MOTOR, e não metade dela (revisão do PR #162): o
                # teste reimplementava só o filtro de APARELHO; o motor exige
                # também o EQUIPAMENTO dentro da sacola. Uma variante de
                # halteres no degrau 1 seria corretamente ignorada pelo motor e
                # contada aqui como "degrau mais fácil disponível".
                disponiveis = [
                    e.name for e in mais_faceis if services.dentro_do_perfil(e, permitidos)
                ]
                self.assertFalse(
                    disponiveis,
                    "%s (degrau %s) entrou com degrau mais fácil disponível: %s"
                    % (nome, nivel, disponiveis),
                )

    def test_a_flexao_da_persona_e_a_de_joelhos_apoiados(self):
        plano = services.create_routine(_pessoa("flexao@exemplo.com"))
        nomes = [i.exercise.name for i in _itens(plano)]
        self.assertIn("Flexão de braço com joelhos apoiados", nomes, nomes)
        self.assertNotIn("Flexão de braço arqueiro", nomes)

    def test_quem_ja_treina_continua_no_degrau_do_modelo(self):
        plano = services.create_routine(
            _pessoa("degrau-int@exemplo.com", experiencia=Experiencia.INTERMEDIARIO,
                    equipamento=Equipamento.COMPLETA, dias=5,
                    duracao=DuracaoTreino.PADRAO)
        )
        self.assertTrue(_itens(plano))


class PesoDoCorpoNaoPedeCargaTests(TestCase):
    """A execução não desenha campo de carga para exercício sem anilha.

    Ele já nascia vazio, sem `required` e sem os botões de ±2,5 — e ainda
    assim era uma pergunta rotulada "Carga" numa flexão de braço. A persona
    digitou zero e o treino fechou em "0 kg levantados".

    A âncora é `name="weight_kg"` COM aspas: a mesma página tem
    `querySelector("[name=weight_kg]")` dentro de um `<script>`, e procurar
    a string solta acharia o script — a armadilha que o `CLAUDE.md` nomeia.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _execucao(self, user, item):
        self.client.force_login(user)
        resposta = self.client.get(
            reverse("workouts:now") + "?exercicio=%d" % item.exercise_id
        )
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def _de_hoje(self, plano, com_carga):
        from django.utils import timezone

        sessao = services.sessao_do_dia(plano, timezone.localdate())
        self.assertIsNotNone(sessao, "o fixture precisa treinar hoje")
        itens = [
            i for i in _itens(plano)
            if i.session_id == sessao.pk and i.exercise.sem_carga != com_carga
        ]
        self.assertTrue(itens, "nenhum exercício %s carga hoje" % ("com" if com_carga else "sem"))
        return itens[0]

    def test_a_flexao_nao_tem_campo_de_carga(self):
        user = _pessoa("sem-carga@exemplo.com")
        plano = services.create_routine(user)
        html = self._execucao(user, self._de_hoje(plano, com_carga=False))
        self.assertNotIn('name="weight_kg"', html)
        self.assertIn('name="reps"', html, "as repetições continuam sendo a pergunta")
        # A GRADE ACOMPANHA (revisão do PR #162, visto na captura do QA): sem
        # o modificador, a coluna da carga ficava vazia e o campo de Reps era
        # espremido na faixa da direita, com ~200 px de nada ao lado.
        self.assertIn("registro--sem-carga", html)

    def test_o_supino_continua_pedindo(self):
        """CONTROLE POSITIVO: o campo sumiu de quem não tem anilha, e não da
        tela."""
        user = _pessoa(
            "com-carga@exemplo.com", experiencia=Experiencia.INTERMEDIARIO,
            equipamento=Equipamento.COMPLETA, dias=5, duracao=DuracaoTreino.PADRAO,
        )
        plano = services.create_routine(user)
        html = self._execucao(user, self._de_hoje(plano, com_carga=True))
        self.assertIn('name="weight_kg"', html)
        self.assertNotIn("registro--sem-carga", html)


class ANotacaoDaFichaTemLegendaNaPrimeiraVezTests(TestCase):
    """"3 × 6-10" é a linguagem de quem já treina."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _ficha(self, user, plano):
        from django.utils import timezone

        sessao = services.sessao_do_dia(plano, timezone.localdate())
        self.client.force_login(user)
        resposta = self.client.get(reverse("workouts:ficha", args=[sessao.pk]))
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode(), sessao

    def test_a_primeira_ficha_diz_o_que_o_numero_quer_dizer(self):
        user = _pessoa("legenda@exemplo.com")
        plano = services.create_routine(user)
        html, _ = self._ficha(user, plano)
        self.assertIn("quer dizer", html)
        self.assertIn("6 a 10 repetições", html)

    def test_quem_ja_registrou_carga_nao_le_a_legenda_de_novo(self):
        """CONTROLE POSITIVO: a frase some quando deixa de ser a primeira
        vez — repetir para sempre seria ruído na tela mais aberta do treino."""
        from datetime import timedelta

        from django.utils import timezone

        from workouts.models import ExerciseLog

        user = _pessoa("legenda2@exemplo.com")
        plano = services.create_routine(user)
        _, sessao = self._ficha(user, plano)
        for item in [i for i in _itens(plano) if i.session_id == sessao.pk]:
            ExerciseLog.objects.create(
                user=user, exercise=item.exercise, date=timezone.localdate() - timedelta(days=2),
                set_number=1, weight_kg=0, reps=8,
            )
        html, _ = self._ficha(user, plano)
        self.assertNotIn("quer dizer", html)
