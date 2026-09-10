"""O PERFIL DE REFERÊNCIA da campanha, e as regras de prescrição que ele cobra.

Homem, 27 anos, 102 kg, 1,85 m, musculação regular, objetivo de massa, treino de
segunda a sexta, ~1h30 disponível por sessão.

Este arquivo existe porque a campanha nomeou um cenário concreto e proibiu
tratar a conta de exemplo do repositório — 36 anos, 81,2 kg, 1,75 m — como se
fosse ele. Um teste que medisse a outra pessoa passaria dizendo nada.

O QUE ELE GUARDA, e cada item foi um defeito medido em 08/09/2026:

  - **Supino reto com quatro séries de trabalho, nas duas sessões A.** Saía com
    duas. A causa não era falta de tempo: sobravam mais de sessenta minutos, e
    `distribuir_series` repartia a dose do catálogo entre as ocorrências da
    letra;
  - **`Remada curvada com barra` fora dos planos ativos.** Decisão de produto:
    a versão ativa do movimento também saiu do uso ativo, substituída por
    `Remada baixa na polia` — mesmo grupo, mesmo padrão de puxada horizontal;
  - **duração realista.** 29 séries diziam ~49 minutos, sem aquecimento nem
    transição honesta;
  - **volume semanal coerente**, com participação secundária contando metade;
  - **nenhum grupo apagado e nenhum dia esvaziado** pelo corte.
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import (
    ActivityLevel,
    Goal,
    ONBOARDING_DONE,
    Profile,
    Sex,
    TrainingDay,
    WeightEntry,
)
from workouts import services
from workouts.models import Exercise, ExerciseLog, SessionExercise

User = get_user_model()

APOSENTADO = "Remada curvada com barra"
SUBSTITUTO = "Remada baixa na polia"


def pessoa_de_referencia(email="referencia@exemplo.com", dias=5, duracao=90):
    """A pessoa que a campanha descreveu, e não a conta de exemplo do repo."""
    user = User.objects.create_user(email=email, password="x8Kd2Lm9Qp4z")
    Profile.objects.create(
        user=user,
        sex=Sex.MALE,
        birth_date=date(1999, 3, 1),
        height_cm=185,
        activity_level=ActivityLevel.ACTIVE,
        goal=Goal.BULK,
        wake_time=time(7, 0),
        sleep_time=time(23, 0),
        onboarding_step=ONBOARDING_DONE,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal("102"))
    for weekday in range(dias):
        TrainingDay.objects.create(
            user=user, weekday=weekday, start_time=time(19, 0), duration_min=duracao
        )
    return user


class OPerfilDeReferenciaRecebeUmaFichaDeVerdadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = pessoa_de_referencia()
        self.plano = services.create_routine(self.user)
        self.linhas = list(
            SessionExercise.objects.filter(session__plan=self.plano)
            .select_related("exercise", "session")
        )

    def _do_exercicio(self, nome):
        return [linha for linha in self.linhas if linha.exercise.name == nome]

    # ------------------------------------------------------------ o supino
    def test_o_supino_reto_tem_QUATRO_series_em_cada_sessao(self):
        """O caso que a campanha nomeou. Duas séries eram o defeito."""
        supinos = self._do_exercicio("Supino reto com barra")

        self.assertTrue(supinos, "o supino reto sumiu da ficha de referência")
        for linha in supinos:
            with self.subTest(dia=linha.session.weekday):
                self.assertEqual(
                    linha.sets, 4,
                    "supino reto com %s séries em vez de 4" % linha.sets,
                )

    def test_as_duas_sessoes_de_peito_trazem_exercicios_DIFERENTES(self):
        """Segunda e quinta: a divisão em cinco dias dá A duas vezes.

        REMIRADO EM 10/09/2026, e o contrato virou o contrário. Este teste
        exigia que o Supino reto aparecesse nas DUAS passagens — "o ganho da
        repetição é a segunda sessão do grupo". A auditoria de produção mostrou
        o preço disso: com o modelo inteiro entrando duas vezes, o teto semanal
        cortava variedade e a semana fechava com DOIS exercícios distintos de
        peito, dos quatro que o modelo lista.

        A regra agora é "não repetir enquanto houver opção não usada". O ganho
        da repetição continua existindo — peito é treinado duas vezes na
        semana —, e o que mudou é que a segunda sessão traz OUTROS exercícios.

        O que este teste guarda é o par: peito nas duas, sem repetir nenhum.
        """
        peitos = [
            item
            for sessao in self.plano.sessions.all().order_by("weekday")
            for item in sessao.exercises.select_related("exercise")
            if item.exercise.muscle_group == "chest"
        ]
        por_sessao = {}
        for item in peitos:
            por_sessao.setdefault(item.session_id, []).append(item.exercise.name)

        self.assertEqual(len(por_sessao), 2, "peito deixou de ter duas sessões")
        primeira, segunda = list(por_sessao.values())
        self.assertEqual(
            set(primeira) & set(segunda), set(),
            "as duas sessões de peito repetiram exercício",
        )

    def test_a_faixa_do_supino_fica_dentro_de_6_a_12(self):
        """Faixa de hipertrofia. O teste é sobre a FAIXA, não sobre um valor
        exato — o catálogo pode ajustar dentro dela sem quebrar nada."""
        supino = self._do_exercicio("Supino reto com barra")[0]

        self.assertGreaterEqual(supino.rep_min, 6)
        self.assertLessEqual(supino.rep_max, 12)
        self.assertLess(supino.rep_min, supino.rep_max)

    # ---------------------------------------------------- a remada curvada
    def test_a_remada_curvada_com_barra_NAO_entra_no_plano(self):
        """Decisão de produto: a versão ativa também saiu do uso ativo."""
        self.assertEqual(self._do_exercicio(APOSENTADO), [])

    def test_o_substituto_entra_no_lugar_dela_com_a_dose_de_principal(self):
        """Controle positivo: tirar sem repor deixaria o dia B sem puxada
        horizontal, e aí o teste acima passaria por empobrecimento."""
        substitutos = self._do_exercicio(SUBSTITUTO)

        self.assertTrue(substitutos, "o dia B ficou sem puxada horizontal")
        for linha in substitutos:
            with self.subTest(dia=linha.session.weekday):
                self.assertGreaterEqual(linha.sets, services.PISO_COMPOSTO)

    def test_o_exercicio_aposentado_continua_existindo_para_o_historico(self):
        """Aposentar é `is_active=False`, nunca `delete()`.

        `ExerciseLog.exercise` é CASCADE: apagar o exercício levaria junto o
        histórico de carga de quem já treinou com ele, em silêncio.
        """
        velho = Exercise.objects.filter(name=APOSENTADO).first()

        self.assertIsNotNone(velho, "o exercício foi APAGADO em vez de aposentado")
        self.assertFalse(velho.is_active)
        self.assertTrue(velho.video_url, "o vídeo do exercício aposentado sumiu")

    def test_o_historico_de_quem_treinou_com_ela_continua_acessivel(self):
        """A prova de que aposentar preserva dado: uma série registrada no
        exercício aposentado continua legível depois da desativação."""
        velho = Exercise.objects.get(name=APOSENTADO)
        log = ExerciseLog.objects.create(
            user=self.user, exercise=velho, date=self.plano.created_at.date(),
            set_number=1, weight_kg=Decimal("60"), reps=10,
        )

        de_volta = ExerciseLog.objects.select_related("exercise").get(pk=log.pk)

        self.assertEqual(de_volta.exercise.name, APOSENTADO)
        self.assertEqual(de_volta.weight_kg, Decimal("60"))

    def test_nenhum_OUTRO_exercicio_foi_substituido(self):
        """A substituição é por identidade, não por posição. Se ela tivesse
        pego a linha errada, algum exercício do catálogo teria sumido da
        semana sem motivo."""
        nomes = {linha.exercise.name for linha in self.linhas}

        for esperado in (
            "Supino reto com barra",
            "Puxada frente na polia",
            "Agachamento livre",
            "Stiff com barra",
        ):
            with self.subTest(exercicio=esperado):
                self.assertIn(esperado, nomes)

    def test_cada_exercicio_mantem_o_proprio_video(self):
        """"Não embaralhe vídeos" — a substituição troca a identidade da linha,
        e o vídeo vem do exercício, então ele viaja junto por construção. O
        teste existe para que uma futura "otimização" que copie campos entre
        exercícios seja pega."""
        for linha in self.linhas:
            if not linha.exercise.video_url:
                continue
            with self.subTest(exercicio=linha.exercise.name):
                do_catalogo = Exercise.objects.get(pk=linha.exercise_id)
                self.assertEqual(linha.exercise.video_url, do_catalogo.video_url)

    # ------------------------------------------------------------ o volume
    def test_nenhum_grupo_passa_do_teto_semanal_efetivo(self):
        efetivo = services.volume_efetivo(
            [
                (
                    linha.exercise.muscle_group,
                    linha.exercise.secondary_muscles or (),
                    Decimal(linha.sets),
                )
                for linha in self.linhas
            ]
        )

        acima = {
            g: v for g, v in efetivo.items() if v > services.TETO_SEMANAL_POR_GRUPO
        }
        self.assertEqual(acima, {}, "grupo acima do teto: %s" % acima)

    def test_nenhum_grupo_do_catalogo_desaparece_da_semana(self):
        previstos = {
            item.exercise.muscle_group
            for template in services.templates_for(self.plano.split)
            for item in template.items.all()
            if item.exercise.is_active
        }
        presentes = {linha.exercise.muscle_group for linha in self.linhas}

        self.assertEqual(previstos - presentes, set())

    def test_nenhum_dia_fica_vazio(self):
        for sessao in self.plano.sessions.all():
            with self.subTest(dia=sessao.weekday):
                self.assertGreaterEqual(sessao.exercises.count(), 3)

    # ----------------------------------------------------------- a duração
    def test_a_duracao_de_cada_sessao_e_realista_e_cabe_no_tempo(self):
        """Nem subdimensionada nem estourando o teto.

        O piso de 30 minutos era o que separava "sessão de musculação planejada"
        de lista de exercícios: as sessões de 21 a 26 minutos que este perfil
        recebia antes eram o sintoma, não a meta. O teto é o tempo informado
        mais a folga documentada — noventa minutos são limite, não alvo.

        O PISO DESCEU PARA 25 EM 10/09/2026, E O MOTIVO NÃO É AFROUXAR.
        `repartir_ocorrencia` passou a dividir os exercícios do modelo entre as
        passagens da letra, então A1 e A2 têm metade dos exercícios cada — e
        29 minutos, não os 45 de quando as duas recebiam o modelo inteiro. O
        volume da SEMANA não caiu; ele foi distribuído, que é o que a auditoria
        pediu.

        E a intenção do piso continua cobrada, agora pelo número que a
        expressava de verdade: o sintoma antigo eram sessões de DOIS ou TRÊS
        exercícios. A asserção de contagem abaixo é a que separa sessão de
        lista; o minuto sozinho nunca separou.
        """
        teto = float(services._teto_em_segundos(90)) / 60
        for sessao in self.plano.sessions.all():
            with self.subTest(dia=sessao.weekday, label=sessao.label):
                self.assertGreaterEqual(sessao.exercises.count(), 4)
                self.assertGreaterEqual(sessao.estimated_minutes, 25)
                self.assertLessEqual(sessao.estimated_minutes, teto)

    def test_a_duracao_conta_aquecimento_descanso_e_transicao(self):
        """A conta tem uma fonte só, e ela inclui o que a versão anterior
        ignorava. Sem aquecimento e com transição fixa de 45s, 29 séries davam
        ~49 minutos — o número que a campanha citou como irreal."""
        from workouts.models import (
            AQUECIMENTO_DO_COMPOSTO_SEGUNDOS,
            AQUECIMENTO_GERAL_SEGUNDOS,
            segundos_da_sessao,
        )

        so_execucao_e_descanso = 4 * 40 + 3 * 80
        com_tudo = segundos_da_sessao([(4, 80, True)])

        self.assertEqual(
            com_tudo,
            AQUECIMENTO_GERAL_SEGUNDOS
            + AQUECIMENTO_DO_COMPOSTO_SEGUNDOS
            + so_execucao_e_descanso,
        )
        self.assertGreater(com_tudo, so_execucao_e_descanso)

    def test_a_tela_e_o_gerador_usam_a_MESMA_conta(self):
        """Eram duas cópias, presas por um teste. Agora é uma função.

        A propriedade que importa: o número que decidiu o que entra na ficha é
        o número que a pessoa lê na tela.
        """
        from workouts.models import segundos_da_sessao

        for sessao in self.plano.sessions.all():
            itens = list(sessao.exercises.select_related("exercise"))
            esperado = round(
                segundos_da_sessao(
                    [(i.sets, i.rest_seconds, i.exercise.is_compound) for i in itens]
                )
                / 60
            )
            with self.subTest(dia=sessao.weekday):
                self.assertEqual(sessao.estimated_minutes, esperado)


class OGeradorNaoPrescreveExercicioAposentadoTests(TestCase):
    """A trava estrutural, medida com sabotagem controlada.

    Desativar um exercício não bastava: o modelo continuava apontando para ele
    e o gerador copiava sem perguntar. Este teste aposenta um exercício QUALQUER
    do catálogo e prova que ele some das prescrições novas.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_desativar_um_exercicio_o_tira_das_fichas_novas(self):
        alvo = Exercise.objects.get(name="Supino inclinado com halteres")
        antes = pessoa_de_referencia(email="antes@exemplo.com")
        plano_antes = services.create_routine(antes)
        estava = SessionExercise.objects.filter(
            session__plan=plano_antes, exercise=alvo
        ).exists()

        Exercise.objects.filter(pk=alvo.pk).update(is_active=False)

        depois = pessoa_de_referencia(email="depois@exemplo.com")
        plano_depois = services.create_routine(depois)
        continua = SessionExercise.objects.filter(
            session__plan=plano_depois, exercise=alvo
        ).exists()

        self.assertTrue(estava, "controle: o exercício nem estava na ficha antes")
        self.assertFalse(continua, "exercício aposentado entrou em plano novo")
