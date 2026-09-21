"""Uma letra, até duas opções completas e intercambiáveis (15/09/2026).

O problema, medido em produção no intermediário de cinco dias e dois grupos
por dia: A1 com 4 exercícios, 13 séries e ~36 minutos; A2 com 4, 13 e ~29 —
a mesma letra com conteúdos diferentes em dias diferentes, nomeada como dois
treinos obrigatórios. Aqui: o calendário só diz letras; cada letra oferece
até duas opções equivalentes (mesmos grupos, ≤ 1 série por grupo, ≤ 5 min,
metade dos exercícios próprios), a pessoa escolhe qual faz, repetir a
preferida cabe no teto semanal, a versão rápida sai da opção escolhida sem
tirar principal, e trocar depois da primeira série pede confirmação sem
apagar nada.

Os cinco perfis do brief são medidos um a um, e os números que o motor
entrega hoje (com o catálogo de hoje) ficam escritos nos testes, não em
promessa. Até 16/09/2026 a sessão de "peito e tríceps" tinha 4 exercícios
porque o catálogo tinha 4 peitos e 3 tríceps; desde 17/09, com 63 ativos e
a doutrina do `TREINO.md`, ela tem 4 de peito e 3 de tríceps POR OPÇÃO — o
teste dourado (`test_ficha_de_verdade`) é quem cobra a ficha de academia.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, Profile, SplitPreference, TrainingDay, User
from plans.tests import create_complete_user
from workouts import opcoes, services
from workouts.models import EscolhaDeTreino, ExerciseLog, SessionExercise, TrainingPlan, familia_de_opcoes

PERFIS = {
    "iniciante_3d_2g": ("iniciante", SplitPreference.DOIS, [0, 2, 4]),
    "intermediario_5d_2g": ("intermediario", SplitPreference.DOIS, [0, 1, 2, 3, 4]),
    "avancado_6d_2g": ("avancado", SplitPreference.DOIS, [0, 1, 2, 3, 4, 5]),
    "intermediario_4d_3g": ("intermediario", SplitPreference.TRES, [0, 1, 3, 4]),
    # Dois dias: até 16/09/2026 o modelo "Superior" tinha um exercício por
    # grupo em quase tudo e a letra A saía com UMA opção; os modelos
    # ganharam um segundo do mesmo padrão composto por grupo e as duas
    # letras saem com duas.
    "intermediario_2d": ("intermediario", SplitPreference.DOIS, [1, 4]),
    # Quatro dias, um grupo: `abcd C` "Pernas e ombros" saiu com UMA opção
    # até 16/09/2026 (uma pressão vertical ativa no modelo); com o
    # "Desenvolvimento na máquina" ativo desde 17/09 tem duas, e é o
    # perfil em que a regra "sem catálogo, uma opção inteira" é provada
    # desativando-o de novo.
    "intermediario_4d_1g": ("intermediario", SplitPreference.UM, [0, 1, 3, 4]),
}


def pessoa(nome, email=None):
    experiencia, preferencia, dias = PERFIS[nome]
    user = create_complete_user(
        email=email or f"{nome}@exemplo.com", experiencia=experiencia,
        split_preference=preferencia, split_preference_confirmada=True,
        duracao_treino=DuracaoTreino.PADRAO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in dias:
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


def letras(plan):
    return [s.label for s in sorted(plan.sessions.all(), key=lambda s: s.order)]


def por_letra(plan):
    vistos = {}
    for sessao in sorted(plan.sessions.prefetch_related("exercises__exercise"), key=lambda s: s.order):
        vistos.setdefault(sessao.label, sessao)
    return vistos


class Catalogo(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)


class CincoPerfisTests(Catalogo):
    """Cada perfil do brief, medido: letras, opções, equivalência, teto."""

    def test_o_calendario_so_tem_letras(self):
        esperado = {
            "iniciante_3d_2g": ["A", "B", "C"],
            "intermediario_5d_2g": ["A", "B", "C", "A", "B"],
            "avancado_6d_2g": ["A", "B", "C", "A", "B", "C"],
            "intermediario_4d_3g": ["A", "B", "C", "A"],
            "intermediario_2d": ["A", "B"],
        }
        for nome, calendario in esperado.items():
            with self.subTest(perfil=nome):
                plan = services.create_routine(pessoa(nome))
                self.assertEqual(letras(plan), calendario)

    def test_cada_letra_com_catalogo_tem_duas_opcoes_equivalentes(self):
        """Onde há catálogo, duas opções: mesmos grupos anunciados, ≤ 1 série
        por grupo de diferença, ≤ 5 min, metade dos exercícios próprios. O
        grupo é a FAMÍLIA (`models.FAMILIA_DE_OPCOES`): posterior e glúteo
        são uma cadeia entre as duas versões — o stiff numa, a elevação
        pélvica na outra (21/09/2026)."""
        for nome in PERFIS:
            plan = services.create_routine(pessoa(nome))
            for label, sessao in por_letra(plan).items():
                if not sessao.tem_duas_opcoes:
                    continue
                with self.subTest(perfil=nome, letra=label):
                    op1, op2 = sessao.da_opcao(1), sessao.da_opcao(2)
                    anunciados = {familia_de_opcoes(g) for g in sessao.main_groups}
                    for op in (op1, op2):
                        self.assertTrue(anunciados <= {familia_de_opcoes(i.exercise.muscle_group) for i in op},
                                        "um grupo anunciado ficou órfão")
                    direto = [opcoes._volume_direto([(i, i.sets, 0) for i in op]) for op in (op1, op2)]
                    for grupo in set(direto[0]) | set(direto[1]):
                        self.assertLessEqual(abs(direto[0].get(grupo, 0) - direto[1].get(grupo, 0)), 1, grupo)
                    self.assertLessEqual(abs(sessao.minutos_da_opcao(1) - sessao.minutos_da_opcao(2)), 5)
                    proprios = {i.exercise_id for i in op1} ^ {i.exercise_id for i in op2}
                    for op in (op1, op2):
                        self.assertGreaterEqual(
                            sum(1 for i in op if i.exercise_id in proprios) / len(op), 0.5,
                            "as opções são praticamente as mesmas",
                        )

    def test_quantas_opcoes_cada_perfil_recebe_hoje(self):
        """O número de hoje, com o catálogo de hoje — escrito, não prometido.

        "Inferior" de dois dias (`ab B`) TINHA duas opções até 16/09/2026, e
        elas não eram intercambiáveis: o stiff — a única extensão de quadril
        do modelo — ficava numa e a mesa flexora na outra. A régua dos
        padrões compostos compartilha o stiff e a letra caía para UMA opção;
        voltou a duas no mesmo dia, porque o modelo passou a listar a
        elevação pélvica (ativa) como segunda extensão de quadril. "Superior"
        (`ab A`) ganhou duas pelo mesmo caminho. `abcd C` esperou o
        "Desenvolvimento na máquina" até 17/09/2026, quando os 28 com foto
        conferida entraram ativos: hoje TODA letra tem duas, e é o gate de
        `opcoes_em_producao` (por letra) que impede uma de voltar a uma.
        """
        esperado = {
            "iniciante_3d_2g": {"A": 2, "B": 2, "C": 2},
            "intermediario_5d_2g": {"A": 2, "B": 2, "C": 2},
            "avancado_6d_2g": {"A": 2, "B": 2, "C": 2},
            "intermediario_4d_3g": {"A": 2, "B": 2, "C": 2},
            "intermediario_2d": {"A": 2, "B": 2},
            "intermediario_4d_1g": {"A": 2, "B": 2, "C": 2, "D": 2},
        }
        for nome, por_label in esperado.items():
            plan = services.create_routine(pessoa(nome))
            for label, sessao in por_letra(plan).items():
                with self.subTest(perfil=nome, letra=label):
                    self.assertEqual(len(sessao.opcoes), por_label[label])

    def test_o_tamanho_das_sessoes_hoje(self):
        """Com Padrão (até 60), o intermediário de cinco dias recebe sessões
        de 24 a 26 séries em 57 a 60 minutos, e "Peito e tríceps" tem SETE
        exercícios por opção — 4 de peito e 3 de tríceps (17/09/2026; até o
        dia anterior eram 4 exercícios, 13 séries e ~36 minutos, porque o
        catálogo tinha 4 peitos e 3 tríceps para as duas opções dividirem).
        A faixa é registrada para a próxima leitura não achar que houve
        regressão — o teste dourado cobra a letra A com precisão.
        """
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        sessoes = por_letra(plan)
        for label, sessao in sessoes.items():
            for k in sessao.opcoes:
                with self.subTest(letra=label, opcao=k):
                    self.assertGreaterEqual(sessao.series_da_opcao(k), opcoes.PISO_SERIES_COMPLETO)
                    # B e C levam complementares além dos anunciados
                    # (trapézio e antebraço; panturrilha e abdômen).
                    self.assertLessEqual(sessao.series_da_opcao(k), opcoes.TETO_SERIES_COMPLETO + 6)
                    self.assertLessEqual(sessao.minutos_da_opcao(k), 60)
                    self.assertGreaterEqual(sessao.minutos_da_opcao(k), 55)
        for k in sessoes["A"].opcoes:
            itens = sessoes["A"].da_opcao(k)
            self.assertEqual(len(itens), 7)
            self.assertEqual(sum(1 for i in itens if i.exercise.muscle_group == "chest"), 4)
            self.assertEqual(sum(1 for i in itens if i.exercise.muscle_group == "triceps"), 3)

    def test_repetir_a_mesma_opcao_cabe_no_teto_semanal(self):
        """O pior caso — toda ocorrência da letra na opção mais pesada de cada
        grupo — fica no teto da pessoa, exceto o excesso que só um composto
        principal poderia resolver (teto de aparo, não promessa)."""
        for nome in PERFIS:
            user = pessoa(nome)
            plan = services.create_routine(user)
            tetos = services.tetos_da_semana(plan)
            pior = services.volume_da_semana(plan)
            for grupo, volume in pior.items():
                teto = tetos[grupo]
                with self.subTest(perfil=nome, grupo=grupo):
                    if volume > teto:
                        # Só pode sobrar excesso irredutível: nenhuma opção
                        # tem isolador/acessório direto do grupo para ceder.
                        for sessao in por_letra(plan).values():
                            for k in sessao.opcoes:
                                itens = sessao.da_opcao(k)
                                graus = services.prioridades_da_sessao(itens)
                                diretos = [i for i, g in zip(itens, graus) if i.exercise.muscle_group == grupo]
                                cedem = [i for i, g in zip(itens, graus)
                                         if i.exercise.muscle_group == grupo and g < services.PRINCIPAL and i.sets > 2]
                                self.assertTrue(len(diretos) <= 1 or not cedem,
                                                f"{grupo} passa do teto ({volume} > {teto}) com o que ceder")

    def test_as_opcoes_nao_sao_somadas_no_volume(self):
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        pior = services.volume_da_semana(plan)
        soma = {}
        for sessao in plan.sessions.all():
            for item in sessao.exercises.select_related("exercise"):
                soma[item.exercise.muscle_group] = soma.get(item.exercise.muscle_group, 0) + item.sets
        # Somar as duas opções dá um número maior que o pior caso em todo
        # grupo com duas opções — é o treino que ninguém faz.
        self.assertGreater(soma["chest"], pior["chest"])
        self.assertLessEqual(pior["chest"], services.tetos_da_semana(plan)["chest"])

    def test_a_ocorrencia_da_letra_carrega_as_mesmas_opcoes(self):
        """A de segunda e A de quinta são o MESMO treino com as mesmas duas
        opções — nunca mais A1 ≠ A2 como dias obrigatórios."""
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        sessoes = sorted(plan.sessions.prefetch_related("exercises"), key=lambda s: s.order)
        a1, a2 = [s for s in sessoes if s.label == "A"]
        assinatura = lambda s: [(i.opcao, i.exercise_id, i.sets) for i in s.exercises.all()]
        self.assertEqual(assinatura(a1), assinatura(a2))

    def test_sem_catalogo_para_duas_a_letra_sai_com_uma_e_inteira(self):
        """Sem catálogo para duas opções distintas, a letra sai com UMA: o
        modelo inteiro no tempo, não a metade que sobrou.

        Até 16/09/2026 o exemplo real era `abcd C` (uma pressão vertical
        ativa); com os 63 ativos toda letra tem duas, então o estado é
        FABRICADO: "Peito" de cinco dias com o catálogo de peito reduzido a
        um supino e um crucifixo — os dois compartilhados, zero próprio, e
        a régua de `distintas_o_bastante` recusa a segunda opção."""
        from workouts.models import Exercise

        sobram = ("Supino reto com barra", "Crucifixo na máquina (voador)")
        Exercise.objects.filter(muscle_group="chest").exclude(name__in=sobram).update(is_active=False)
        user = create_complete_user(
            email="um-grupo-5d@exemplo.com", experiencia="intermediario",
            split_preference=SplitPreference.UM, split_preference_confirmada=True,
            duracao_treino=DuracaoTreino.PADRAO,
        )
        TrainingDay.objects.filter(user=user).delete()
        for d in range(5):
            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
        plan = services.create_routine(user)
        a = por_letra(plan)["A"]
        self.assertEqual(plan.split, "abcde")
        self.assertEqual(a.opcoes, [1])
        self.assertEqual(
            {i.exercise.name for i in a.da_opcao(1)},
            set(sobram) | {"Abdominal supra no solo"},
            "a opção única é o modelo inteiro que sobrou",
        )

    def test_a_regeneracao_preserva_o_historico(self):
        user = pessoa("intermediario_4d_3g")
        plan = services.create_routine(user)
        supino = SessionExercise.objects.filter(session__plan=plan).first().exercise
        ExerciseLog.objects.create(user=user, exercise=supino, date=timezone.localdate(), set_number=1, weight_kg=40)
        TrainingDay.objects.create(user=user, weekday=5, duration_min=60)
        novo = services.create_routine(user)
        self.assertNotEqual(novo.pk, plan.pk)
        self.assertTrue(TrainingPlan.objects.filter(pk=plan.pk).exists(), "plano antigo é retrato, não some")
        self.assertEqual(ExerciseLog.objects.filter(user=user).count(), 1)

    def test_a_conferencia_reconhece_a_propria_ficha(self):
        """`routine_is_current` compara opção a opção com o que sairia hoje —
        senão toda visita remontaria a ficha em laço."""
        from unittest import mock

        user = pessoa("intermediario_5d_2g")
        plan = services.create_routine(user)
        self.assertTrue(services.routine_is_current(plan, user))
        # Uma linha da opção 2 mexida à mão: a ficha deixa de ser atual —
        # quando a conferência exata roda, que desde 17/09/2026 é só para
        # ficha nascida de OUTRO catálogo (a impressão digital igual responde
        # "atual" sem represcrever).
        item = SessionExercise.objects.filter(session__plan=plan, opcao=2).first()
        SessionExercise.objects.filter(pk=item.pk).update(sets=item.sets + 1)
        self.assertTrue(services.routine_is_current(plan, user), "mesmo catálogo: não represcreve")
        with mock.patch.object(services, "versao_do_catalogo", return_value="catalogo-novo"):
            self.assertFalse(services.routine_is_current(plan, user))


class VersaoRapidaTests(Catalogo):
    def test_a_rapida_sai_da_opcao_escolhida_e_preserva_os_principais(self):
        plan = services.create_routine(pessoa("intermediario_4d_3g"))
        for label, sessao in por_letra(plan).items():
            for k in sessao.opcoes:
                itens = sessao.da_opcao(k)
                graus = services.prioridades_da_sessao(itens)
                ficam, removidos = opcoes.versao_rapida(
                    [(i, i.sets, g) for i, g in zip(itens, graus)], sessao.main_groups
                )
                with self.subTest(letra=label, opcao=k):
                    minutos = round(services.segundos_da_sessao(
                        [(s, i.rest_seconds, i.exercise.is_compound) for i, s in ficam]) / 60)
                    self.assertLessEqual(minutos, opcoes.TETO_RAPIDO_MIN)
                    principais = {i.exercise_id for i, g in zip(itens, graus) if g == services.PRINCIPAL}
                    self.assertTrue(principais <= {i.exercise_id for i, _ in ficam}, "a rápida removeu um principal")
                    # A ordem é a da ficha, e não há terceira ficha: tudo que
                    # fica estava na opção.
                    ordem = [i.exercise_id for i, _ in ficam]
                    self.assertEqual(ordem, [i.exercise_id for i in itens if i.exercise_id in ordem])
                    self.assertTrue({i.exercise_id for i in removidos} <= {i.exercise_id for i in itens})

    def test_o_complementar_nao_conta_como_foco(self):
        """No `abc2`, "Costas e bíceps" anuncia dois grupos e traz trapézio e
        antebraço junto: eles ficam na lista de complementares — separados e
        nomeados —, nunca contados como o foco da sessão."""
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        b = por_letra(plan)["B"]
        anunciados = set(b.main_groups)
        self.assertEqual(anunciados, {"back", "biceps"})
        for k in b.opcoes:
            complementares = b.complementares_da_opcao(k)
            self.assertTrue(complementares, "a opção %d perdeu os complementares" % k)
            for item in complementares:
                self.assertNotIn(item.exercise.muscle_group, anunciados)
            for item in b.principais_da_opcao(k):
                self.assertIn(item.exercise.muscle_group, anunciados)


class Falso:
    """Um item de catálogo de mentira, para os testes puros de `opcoes.py`."""

    class Exercicio:
        def __init__(self, pk, grupo, composto=False, secundarios=(), padrao=""):
            self.pk = pk
            self.muscle_group = grupo
            self.is_compound = composto
            self.secondary_muscles = list(secundarios)
            # O padrão de movimento (16/09/2026). Sem um explícito, o falso
            # segue a regra do catálogo — composto tem padrão composto —,
            # para os testes antigos continuarem coerentes.
            self.padrao = padrao or ("pressao_de_peito" if composto else "crucifixo")

    def __init__(self, pk, grupo, sets=3, composto=False, rest=60, padrao=""):
        self.exercise_id = pk
        self.exercise = Falso.Exercicio(pk, grupo, composto, padrao=padrao)
        self.sets = sets
        self.rest_seconds = rest


class EquivalenciaPuraTests(TestCase):
    """As réguas de equivalência e o equilíbrio, sobre itens de mentira —
    para a sabotagem que ignora a régua não passar por vacuidade quando os
    perfis reais já nascem equilibrados."""

    def _op(self, *linhas):
        return [(Falso(pk, grupo, sets=sets, composto=composto), sets, grau)
                for pk, grupo, sets, composto, grau in linhas]

    def test_duas_series_de_diferenca_num_grupo_reprovam(self):
        op1 = self._op((1, "chest", 4, True, 2), (2, "chest", 4, False, 0), (3, "triceps", 3, False, 0))
        op2 = self._op((4, "chest", 4, True, 2), (5, "chest", 2, False, 0), (6, "triceps", 3, False, 0))
        self.assertFalse(opcoes.equivalentes([op1, op2], ["chest", "triceps"]))
        op2[1] = (op2[1][0], 3, 0)
        self.assertTrue(opcoes.equivalentes([op1, op2], ["chest", "triceps"]))

    def test_os_mesmos_padroes_compostos_em_cada_grupo_anunciado(self):
        """Puxada + remada numa opção e duas puxadas na outra têm o MESMO
        volume, os MESMOS minutos e o grupo presente nas duas — e não são
        intercambiáveis: uma semana sem remada horizontal não é a mesma
        semana. A régua compara os padrões COMPOSTOS por grupo anunciado."""
        op1 = [
            (Falso(1, "back", sets=4, composto=True, padrao="puxada_vertical"), 4, 2),
            (Falso(2, "back", sets=3, composto=True, padrao="remada_horizontal"), 3, 1),
        ]
        op2 = [
            (Falso(3, "back", sets=4, composto=True, padrao="puxada_vertical"), 4, 2),
            (Falso(4, "back", sets=3, composto=True, padrao="puxada_vertical"), 3, 1),
        ]
        self.assertEqual(opcoes._minutos(op1), opcoes._minutos(op2))
        self.assertFalse(opcoes.equivalentes([op1, op2], ["back"]))
        # Com a remada dos dois lados, passa.
        op2[1] = (Falso(4, "back", sets=3, composto=True, padrao="remada_horizontal"), 3, 1)
        self.assertTrue(opcoes.equivalentes([op1, op2], ["back"]))

    def test_tres_supinos_contra_tres_crucifixos_reprovam(self):
        supinos = [
            (Falso(pk, "chest", sets=3, composto=True, padrao="pressao_de_peito"), 3, 1)
            for pk in (1, 2, 3)
        ]
        crucifixos = [
            (Falso(pk, "chest", sets=3, composto=False, padrao="crucifixo"), 3, 0)
            for pk in (4, 5, 6)
        ]
        self.assertFalse(opcoes.equivalentes([supinos, crucifixos], ["chest"]))

    def test_isoladores_diferentes_com_os_mesmos_compostos_passam(self):
        op1 = [
            (Falso(1, "chest", sets=4, composto=True, padrao="pressao_de_peito"), 4, 2),
            (Falso(2, "chest", sets=3, composto=False, padrao="crucifixo"), 3, 0),
        ]
        op2 = [
            (Falso(3, "chest", sets=4, composto=True, padrao="pressao_de_peito"), 4, 2),
            (Falso(4, "chest", sets=3, composto=False, padrao="crucifixo"), 3, 0),
        ]
        self.assertTrue(opcoes.equivalentes([op1, op2], ["chest"]))

    def test_grupo_complementar_nao_entra_na_regua_de_padrao(self):
        """A régua é dos grupos ANUNCIADOS: o trapézio complementar pode ter
        encolhimento numa opção e remada alta na outra, como
        `repartir_ocorrencia` sempre fez com B1 e B2."""
        op1 = [
            (Falso(1, "back", sets=4, composto=True, padrao="puxada_vertical"), 4, 2),
            (Falso(2, "traps", sets=3, composto=False, padrao="elevacao_escapular"), 3, 0),
        ]
        op2 = [
            (Falso(3, "back", sets=4, composto=True, padrao="puxada_vertical"), 4, 2),
            (Falso(4, "traps", sets=3, composto=False, padrao="remada_alta"), 3, 0),
        ]
        self.assertTrue(opcoes.equivalentes([op1, op2], ["back"]))

    def test_grupo_anunciado_ausente_reprova(self):
        op1 = self._op((1, "chest", 4, True, 2), (3, "triceps", 3, False, 0))
        op2 = self._op((4, "chest", 4, True, 2), (5, "chest", 3, False, 0))
        self.assertFalse(opcoes.equivalentes([op1, op2], ["chest", "triceps"]))

    def test_mais_de_cinco_minutos_reprova(self):
        curta = self._op((1, "chest", 4, True, 2), (3, "triceps", 3, False, 0))
        longa = self._op((4, "chest", 4, True, 2), (5, "triceps", 3, False, 0))
        longa[1] = (Falso(5, "triceps", sets=3, rest=300), 3, 0)
        self.assertGreater(abs(opcoes._minutos(curta) - opcoes._minutos(longa)), 5)
        self.assertFalse(opcoes.equivalentes([curta, longa], ["chest", "triceps"]))

    def test_equilibrar_da_serie_a_leve_antes_de_tirar_da_pesada(self):
        op1 = self._op((1, "chest", 4, True, 2), (2, "chest", 4, False, 0), (3, "triceps", 3, False, 0))
        op2 = self._op((4, "chest", 4, True, 2), (5, "chest", 2, False, 0), (6, "triceps", 3, False, 0))
        equilibradas = opcoes.equilibrar([op1, op2], ["chest", "triceps"], 65)
        self.assertTrue(opcoes.equivalentes(equilibradas, ["chest", "triceps"]))
        # A leve recebeu (2 → 3); a pesada ficou como estava.
        self.assertEqual(equilibradas[1][1][1], 3)
        self.assertEqual(equilibradas[0][1][1], 4)
        # Só tirando: a pesada cede.
        so_tirando = opcoes.equilibrar([op1, op2], ["chest", "triceps"], 65, dar=False)
        self.assertTrue(opcoes.equivalentes(so_tirando, ["chest", "triceps"]))
        self.assertEqual(so_tirando[0][1][1], 3)


class EscolhaDoDiaTests(Catalogo):
    def setUp(self):
        self.user = pessoa("intermediario_5d_2g", email="escolha@exemplo.com")
        hoje = timezone.localdate().weekday()
        TrainingDay.objects.get_or_create(user=self.user, weekday=hoje, defaults={"duration_min": 60})
        self.plan = services.create_routine(self.user)
        self.sessao = services.sessao_do_dia(self.plan, timezone.localdate())
        self.client.force_login(self.user)

    def test_a_primeira_serie_grava_a_escolha_e_a_repeticao_e_livre(self):
        estado = services.estado_do_treino(self.user, opcao=1)
        item = estado.itens[0]
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": item.exercise_id, "weight_kg": "40", "reps": "8",
            "sessao": self.sessao.pk, "opcao": 1, "versao": "completo", "op_id": "x1",
        })
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user).opcao, 1)
        # Repetir a mesma opção noutra ocorrência é permitido: nada obriga a alternar.
        outra = self.plan.sessions.filter(label=self.sessao.label).exclude(pk=self.sessao.pk).first()
        if outra is not None:
            amanha = timezone.localdate() + timedelta(days=1)
            services.registrar_escolha(self.user, outra, 1, dia=amanha)
            self.assertEqual(EscolhaDeTreino.objects.get(user=self.user, date=amanha).opcao, 1)

    def test_a_ficha_de_hoje_e_uma_lista_e_a_execucao_abre_a_mesma(self):
        """Ficha única (17/09/2026): a ficha de hoje desenha a variação do
        dia, sem "Opção", sem selo, sem botão de escolher; a execução abre
        exatamente essa lista — e um exercício que só está na outra versão
        não é executável hoje (`AEscolhaDoExercicioEEstritaTests`)."""
        from workouts.tests import sem_scripts

        opcao = services.opcao_do_dia(self.user, self.sessao, timezone.localdate())
        html = sem_scripts(self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode())
        self.assertNotIn("Opção 1", html)
        self.assertNotIn("Opção 2", html)
        self.assertNotIn("Recomendada hoje", html)
        self.assertNotIn("Começar esta opção", html)
        for item in self.sessao.da_opcao(opcao):
            self.assertIn(item.exercise.name, html)
        outra = next(k for k in self.sessao.opcoes if k != opcao)
        so_na_outra = [i for i in self.sessao.da_opcao(outra) if i.exercise_id not in {j.exercise_id for j in self.sessao.da_opcao(opcao)}]
        self.assertTrue(so_na_outra, "as duas versões precisam diferir para o teste medir")
        self.assertNotIn(so_na_outra[0].exercise.name, html)
        estado = services.estado_do_treino(self.user)
        self.assertEqual(estado.opcao, opcao)

    def test_o_painel_tem_um_cartao_por_letra_sem_falar_de_versoes(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertEqual(html.count('<a class="sessao-cartao'), 3)
        self.assertNotIn("versões disponíveis", html)
        self.assertNotIn(">A1<", html)

    def test_a_versao_rapida_na_execucao_nomeia_o_que_ficou_de_fora(self):
        services.registrar_escolha(self.user, self.sessao, 1, versao="rapido")
        estado = services.estado_do_treino(self.user)
        self.assertTrue(estado.rapida)
        completa = self.sessao.da_opcao(1)
        self.assertLessEqual(sum(i.sets for i in estado.itens), sum(i.sets for i in completa))
        html = self.client.get(reverse("workouts:now")).content.decode()
        if estado.removidos:
            self.assertIn("Fora da versão rápida", html)
        # Nada foi gravado: a ficha continua com as séries completas.
        self.assertEqual(sum(i.sets for i in self.sessao.da_opcao(1)), sum(i.sets for i in completa))



class PlanoAntigoTests(Catalogo):
    """Ficha anterior a 15/09/2026: tudo em `opcao=1`, continua legível."""

    def test_plano_ajustado_com_a1_diferente_de_a2_continua_com_dois_cartoes(self):
        user = pessoa("intermediario_5d_2g", email="antigo@exemplo.com")
        plan = services.create_routine(user)
        # Simula o plano antigo: só opção 1, e a segunda passagem diferente.
        SessionExercise.objects.filter(session__plan=plan, opcao=2).delete()
        segunda_a = sorted(plan.sessions.filter(label="A"), key=lambda s: s.order)[1]
        SessionExercise.objects.filter(session=segunda_a).first().delete()
        TrainingPlan.objects.filter(pk=plan.pk).update(customized_at=timezone.now())
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIn(">A1<", html)
        self.assertIn(">A2<", html)
        self.assertNotIn("Duas versões disponíveis", html)
        for sessao in plan.sessions.all():
            self.assertEqual(sessao.opcoes, [1])


class RepartirPorPadraoTests(TestCase):
    """`montar_opcoes` reparte o grupo ANUNCIADO por padrão composto —
    cada opção leva pelo menos um de cada — e o padrão composto único é
    compartilhado. Os isoladores continuam em rodízio, e podem diferir."""

    def _itens(self, *linhas):
        return [Falso(pk, grupo, composto=composto, padrao=padrao) for pk, grupo, composto, padrao in linhas]

    def test_cada_opcao_leva_uma_pressao_de_peito_sem_compartilhar(self):
        # Pressão nas posições 0 e 2: o rodízio cego por grupo daria as duas
        # pressões a uma opção e os dois crucifixos à outra — os "três
        # supinos contra três crucifixos" da régua.
        itens = self._itens(
            (1, "chest", True, "pressao_de_peito"), (2, "chest", False, "crucifixo"),
            (3, "chest", True, "pressao_de_peito"), (4, "chest", False, "crucifixo"),
        )
        ops, compartilhados = opcoes.montar_opcoes(itens, n=2, principais=["chest"])
        for op in ops:
            self.assertTrue(any(i.exercise.padrao == "pressao_de_peito" for i in op), op)
        self.assertEqual(compartilhados, set())
        self.assertEqual(sorted(len(op) for op in ops), [2, 2])

    def test_o_padrao_composto_unico_e_compartilhado(self):
        itens = self._itens(
            (1, "triceps", False, "extensao_de_cotovelo"), (2, "triceps", False, "extensao_de_cotovelo"),
            (3, "triceps", True, "pressao_fechada"),
        )
        ops, compartilhados = opcoes.montar_opcoes(itens, n=2, principais=["triceps"])
        self.assertEqual(compartilhados, {3})
        for op in ops:
            self.assertIn(3, [i.exercise_id for i in op])
        proprios = [[i.exercise_id for i in op if i.exercise_id != 3] for op in ops]
        self.assertEqual(sorted(sum(proprios, [])), [1, 2])

    def test_grupo_nao_anunciado_segue_o_rodizio_de_sempre(self):
        """Sem estar em `principais`, nada muda: é o rodízio por grupo, com o
        grupo ímpar emprestando o último."""
        itens = self._itens(
            (1, "traps", False, "elevacao_escapular"), (2, "traps", True, "remada_alta"),
            (3, "traps", False, "elevacao_escapular"), (4, "traps", True, "remada_alta"),
        )
        ops, compartilhados = opcoes.montar_opcoes(itens, n=2, principais=["back"])
        self.assertEqual(compartilhados, set())
        self.assertEqual([[i.exercise_id for i in op] for op in ops], [[1, 3], [2, 4]])

    def test_dois_compostos_diferentes_com_um_de_cada_ficam_nas_duas_opcoes(self):
        """Costas com UMA puxada e UMA remada: as duas são compartilhadas — e
        aí a régua de metade própria decide se a letra sai com duas opções."""
        itens = self._itens(
            (1, "back", True, "puxada_vertical"), (2, "back", True, "remada_horizontal"),
            (3, "back", False, "deltoide_posterior"), (4, "back", False, "deltoide_posterior"),
        )
        ops, compartilhados = opcoes.montar_opcoes(itens, n=2, principais=["back"])
        self.assertEqual(compartilhados, {1, 2})
        self.assertFalse(opcoes.distintas_o_bastante(ops, compartilhados))


class AparoEmLockstepTests(TestCase):
    """`aparar_opcoes` cede sem desfazer a equivalência: a irmã acompanha
    pelo volume DIRETO, e nenhuma opção perde o penúltimo exercício direto
    de um grupo — o excesso que só isso resolveria fica (teto de aparo)."""

    def _linhas(self, *itens):
        return [(Falso(pk, grupo, sets=sets, composto=composto, padrao=padrao), sets, grau)
                for pk, grupo, sets, composto, padrao, grau in itens]

    def test_a_irma_acompanha_a_remocao_pelo_volume_direto(self):
        """Uma opção carrega o supino (tríceps secundário) e por isso puxa o
        teto; o corte tira o acessório dela e deixa a irmã DUAS séries
        diretas acima — a irmã cede também, senão a letra perde a segunda
        opção por um corte que só uma delas pagou."""
        supino = Falso(1, "chest", sets=4, composto=True, padrao="pressao_de_peito")
        supino.exercise.secondary_muscles = ["triceps"]
        op1 = [(supino, 4, 2)] + self._linhas(
            (2, "triceps", 3, True, "pressao_fechada", 2),
            (3, "triceps", 2, False, "extensao_de_cotovelo", 0),
            (4, "triceps", 2, False, "extensao_de_cotovelo", 0),
        )
        op2 = self._linhas(
            (5, "chest", 4, False, "crucifixo", 2),
            (6, "triceps", 3, True, "pressao_fechada", 2),
            (7, "triceps", 2, False, "extensao_de_cotovelo", 0),
            (8, "triceps", 2, False, "extensao_de_cotovelo", 0),
        )
        aparado = opcoes.aparar_opcoes({"A": [op1, op2]}, {"A": 1}, teto=8, dose_do_catalogo=lambda i: i.sets)
        diretos = [opcoes._volume_direto(op).get("triceps") for op in aparado["A"]]
        self.assertEqual(diretos, [5, 5])
        self.assertTrue(opcoes.equivalentes(aparado["A"], ["triceps"]))

    def _peito_e_triceps(self):
        supino = Falso(1, "chest", sets=4, composto=True, padrao="pressao_de_peito")
        supino.exercise.secondary_muscles = ["triceps"]
        op1 = [(supino, 4, 2)] + self._linhas(
            (2, "triceps", 3, True, "pressao_fechada", 2),
            (3, "triceps", 2, False, "extensao_de_cotovelo", 0),
        )
        op2 = self._linhas(
            (5, "chest", 4, False, "crucifixo", 2),
            (2, "triceps", 3, True, "pressao_fechada", 2),
            (4, "triceps", 2, False, "extensao_de_cotovelo", 0),
        )
        return op1, op2

    def test_o_penultimo_direto_nao_sai_por_um_excesso_de_uma_serie(self):
        """Com duas opções, a corda não sai de uma opção que só tem mergulho
        e corda para cobrir UMA série de excesso: o tríceps ficaria só no
        composto compartilhado nas duas, e a semana com UM tríceps distinto.
        Pior caso: op1 = 3 + 2 + 2 (secundário do supino) = 7 por ocorrência,
        ×2 = 14 contra o teto 13 — um excesso de UMA série, muito abaixo de
        um quarto do teto. O excesso fica."""
        op1, op2 = self._peito_e_triceps()
        aparado = opcoes.aparar_opcoes({"A": [op1, op2]}, {"A": 2}, teto=13, dose_do_catalogo=lambda i: i.sets)
        self.assertEqual([len(op) for op in aparado["A"]], [3, 3])
        # Com UMA opção a trava é a de sempre: o último direto fica, o penúltimo sai.
        op1, _ = self._peito_e_triceps()
        sozinha = opcoes.aparar_opcoes({"A": [op1]}, {"A": 2}, teto=13, dose_do_catalogo=lambda i: i.sets)
        self.assertEqual(len(sozinha["A"][0]), 2)

    def test_o_penultimo_direto_sai_quando_o_excesso_e_grande(self):
        """O iniciante (teto 12) com o ombro em 21 não é o caso de uma série:
        14 contra um teto de 6 é mais que um quarto acima, o aparo que o
        nível pede acontece — a corda sai, a irmã acompanha, e o que sobra
        é o secundário dos pressões, irredutível."""
        op1, op2 = self._peito_e_triceps()
        aparado = opcoes.aparar_opcoes({"A": [op1, op2]}, {"A": 2}, teto=6, dose_do_catalogo=lambda i: i.sets)
        self.assertEqual([len(op) for op in aparado["A"]], [2, 2])
        self.assertTrue(opcoes.equivalentes(aparado["A"], ["triceps"]))

    def test_a_concessao_que_a_irma_nao_acompanha_nao_acontece(self):
        """Ensaiada numa cópia: se depois dela a irmã ficar mais de uma
        série direta acima SEM ter o que ceder, a concessão não vale e o
        excesso fica — cortar de um lado só era o que derrubava a letra
        para uma opção."""
        supino = Falso(1, "chest", sets=4, composto=True, padrao="pressao_de_peito")
        supino.exercise.secondary_muscles = ["triceps"]
        op1 = [(supino, 4, 2)] + self._linhas(
            (2, "triceps", 3, True, "pressao_fechada", 2),
            (3, "triceps", 2, False, "extensao_de_cotovelo", 0),
            (4, "triceps", 2, False, "extensao_de_cotovelo", 0),
        )
        # A irmã: composto principal e um acessório (grau 1) no piso de três
        # — nada que `_ceder` possa tirar sem passar do penúltimo direto.
        op2 = self._linhas(
            (5, "chest", 4, False, "crucifixo", 2),
            (6, "triceps", 4, True, "pressao_fechada", 2),
            (7, "triceps", 3, True, "pressao_fechada", 1),
        )
        aparado = opcoes.aparar_opcoes({"A": [op1, op2]}, {"A": 1}, teto=8, dose_do_catalogo=lambda i: i.sets)
        self.assertEqual([len(op) for op in aparado["A"]], [4, 3])
        diretos = [opcoes._volume_direto(op).get("triceps") for op in aparado["A"]]
        self.assertEqual(diretos, [7, 7])
