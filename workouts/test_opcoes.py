"""Uma letra, UMA variante (27/09/2026); até ali, até duas opções.

De 15 a 27/09/2026 cada letra saía com até duas opções equivalentes e a
pessoa alternava. Desde 27/09/2026 (decisão do dono: "Fichas novas com uma
variante só"; "letra repetida faz sempre o mesmo treino") a letra de ficha
nova é UMA lista montada por cota (`opcoes.variante_unica`), e a ficha
LEGADA com opção 2 continua lida (`FichaLegadaComDuasOpcoesTests`, fixture
`ficha_legada`). Os testes das réguas de equivalência, da repartição por
padrão e do aparo em lockstep saíram junto com o código que testavam.

Os perfis do brief são medidos um a um, e os números que o motor entrega
hoje (com o catálogo de hoje) ficam escritos nos testes, não em promessa. O
teste dourado (`test_ficha_de_verdade`) é quem cobra a ficha de academia.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, SplitPreference, TrainingDay
from plans.tests import create_complete_user
from workouts import opcoes, services
from workouts.models import EscolhaDeTreino, ExerciseLog, SessionExercise, TrainingPlan

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

    def test_quantas_opcoes_cada_perfil_recebe_hoje(self):
        """O número de hoje, com o catálogo de hoje — escrito, não prometido.

        Até 27/09/2026 era 2 em toda letra de todo perfil (o gate de 16/09).
        Desde a decisão do dono ("Fichas novas com uma variante só") é UMA em
        toda letra, e o gate invertido de `opcoes_em_producao` é quem impede
        uma letra de ganhar a segunda.
        """
        for nome in PERFIS:
            plan = services.create_routine(pessoa(nome))
            for label, sessao in por_letra(plan).items():
                with self.subTest(perfil=nome, letra=label):
                    self.assertEqual(len(sessao.opcoes), 1)

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

    def test_as_opcoes_da_ficha_legada_nao_sao_somadas_no_volume(self):
        """`volume_da_semana` é o pior caso por ocorrência, nunca a soma das
        opções — ninguém faz os dois treinos no mesmo dia. Com a variante
        única as duas contas coincidem; a diferença mora na ficha LEGADA com
        opção 2, que continua sendo lida (27/09/2026)."""
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        ficha_legada(plan, "A")
        pior = services.volume_da_semana(plan)
        soma = {}
        for sessao in plan.sessions.all():
            for item in sessao.exercises.select_related("exercise"):
                soma[item.exercise.muscle_group] = soma.get(item.exercise.muscle_group, 0) + item.sets
        # Somar as duas opções dá mais que o pior caso — é o treino que ninguém faz.
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
        """Com o catálogo de peito reduzido a um supino e um crucifixo, a
        letra "Peito" de cinco dias sai com UMA lista — o que sobrou do
        modelo, inteiro.

        Até 27/09/2026 o teste provava a régua que recusava a segunda opção
        sem exercícios próprios o bastante (apagada com a variante única).
        Hoje toda letra sai com uma lista só; o que continua valendo é que a
        cota não inventa exercício quando o catálogo não tem: dois peitos
        ativos, dois peitos na ficha, mais o complementar."""
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
        # Uma linha mexida à mão: a ficha deixa de ser atual — quando a
        # conferência exata roda, que desde 17/09/2026 é só para ficha
        # nascida de OUTRO catálogo (a impressão digital igual responde
        # "atual" sem represcrever). Era uma linha da opção 2; desde
        # 27/09/2026 a ficha nova só tem a 1.
        item = SessionExercise.objects.filter(session__plan=plan).first()
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
        não é executável hoje (`AEscolhaDoExercicioEEstritaTests`). Sobre
        uma ficha LEGADA desde 27/09/2026: a nova não tem outra versão."""
        from workouts.tests import sem_scripts

        ficha_legada(self.plan, self.sessao.label)
        self.sessao = services.sessao_do_dia(self.plan, timezone.localdate())
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


class AparoDaVarianteTests(TestCase):
    """`aparar_opcoes` sobre UMA lista por letra (27/09/2026): a letra que
    cai três vezes (abc2 a 7 dias) passa do teto na pior semana, e o aparo
    cede SÉRIE antes de exercício — "4 exercícios a 3 séries são 36, vale o
    teto de 45, e a sessão NÃO perde o quarto exercício" (TREINO.md, as três
    regras de leitura da tabela B). O principal nunca cede."""

    def _linhas(self, *itens):
        return [(Falso(pk, grupo, sets=sets, composto=composto, padrao=padrao), sets, grau)
                for pk, grupo, sets, composto, padrao, grau in itens]

    def test_o_acessorio_composto_desce_a_tres_antes_de_o_exercicio_sair(self):
        op = self._linhas(
            (1, "chest", 4, True, "pressao_de_peito", 2),
            (2, "chest", 4, True, "pressao_de_peito", 1),
            (3, "chest", 4, True, "pressao_de_peito", 1),
            (4, "chest", 3, False, "crucifixo", 0),
        )
        # 15 séries × 3 ocorrências = 45 contra um teto de 40.
        aparado = opcoes.aparar_opcoes({"A": [op]}, {"A": 3}, teto=40, dose_do_catalogo=lambda i: i.sets)
        lista = aparado["A"][0]
        self.assertEqual([i.exercise_id for i, _, _ in lista], [1, 2, 3, 4], "o quarto peito ficou")
        self.assertEqual(lista[0][1], 4, "o principal não cede")
        self.assertLessEqual(sum(s for _, s, _ in lista) * 3, 40)
        self.assertTrue(all(s >= 3 for _, s, g in lista if g >= 1), "composto no piso de três")

    def test_so_depois_do_piso_um_exercicio_sai_e_nunca_o_ultimo_direto(self):
        op = self._linhas(
            (1, "chest", 4, True, "pressao_de_peito", 2),
            (2, "chest", 3, True, "pressao_de_peito", 1),
            (3, "chest", 2, False, "crucifixo", 0),
        )
        aparado = opcoes.aparar_opcoes({"A": [op]}, {"A": 3}, teto=12, dose_do_catalogo=lambda i: i.sets)
        self.assertEqual([i.exercise_id for i, _, _ in aparado["A"][0]], [1], "sobra o principal, e o excesso fica")


class PreencherEmRodizioPorGrupoTests(TestCase):
    """As séries que sobram até a faixa vão em RODÍZIO pelos grupos
    anunciados (decisão do dono, 27/09/2026): uma para o peito, uma para o
    tríceps, e não as duas para o peito. Com a lista única, o peito do
    perfil do dourado chegava a 16 séries por sessão — 26,7 na média do
    ciclo, acima do teto de 26 —, porque o acessório de peito (a flexão) e
    o crucifixo recebiam primeiro."""

    def test_as_series_de_sobra_alternam_entre_os_grupos(self):
        def linha(pk, grupo, sets, composto, grau):
            return (Falso(pk, grupo, sets=sets, composto=composto), sets, grau)

        linhas = [
            linha(1, "chest", 4, True, 2), linha(2, "chest", 4, True, 1),
            linha(3, "chest", 3, True, 1), linha(4, "chest", 3, False, 0),
            linha(5, "triceps", 3, True, 2), linha(6, "triceps", 3, False, 0),
            linha(7, "triceps", 3, False, 0),
        ]
        cheias = opcoes.preencher_ate_a_faixa(linhas, None, ["chest", "triceps"], faixa=(21, 25))
        por_grupo = {}
        for item, series, _ in cheias:
            por_grupo[item.exercise.muscle_group] = por_grupo.get(item.exercise.muscle_group, 0) + series
        self.assertEqual(por_grupo, {"chest": 15, "triceps": 10})
        # Dentro do grupo, o acessório antes do isolador, como sempre.
        self.assertEqual([s for _, s, _ in cheias], [4, 4, 4, 3, 3, 4, 3])


class CorpoInteiroPrecisaDe75MinutosTests(Catalogo):
    """Corpo inteiro uma vez por semana EXIGE 75 minutos (decisão do dono,
    27/09/2026, literal: "(c) 1 série pra panturrilha e core se couber em 60
    min; se não couber, (b) EXIGIR 75 min, com o texto na tela e na
    doutrina. NÃO (a)" — (a) era aceitar os dois grupos fora a 60 min com
    aviso). A saída (c) foi medida primeiro: os dez grupos no piso, com
    panturrilha e core em UMA série, dão 62,7 minutos e não cabem em 60.

    OS DOIS CAMINHOS (28/09/2026, decisão do dono). O princípio: essa sessão
    é a semana inteira da pessoa, e os dez grupos só cabem a partir de 75.
    (ii) Onde a duração se escolhe — a área de Treino; o cadastro e o Perfil
    não perguntam a duração desde 10/09 —, quem treina o corpo inteiro uma
    vez por semana não recebe oferta abaixo de 75, e a tela diz por quê com
    a palavra "tempo". (i) Quem JÁ tinha uma faixa menor recebe a ficha
    montada com 75, e a nota avisa, também com "tempo" e o motivo."""

    FRASE = "Sua ficha tem 75 minutos: corpo inteiro uma vez por semana precisa desse tempo para caber todos os grupos."
    REGRA = "Corpo inteiro uma vez por semana precisa de pelo menos 75 minutos de tempo de treino para caber todos os grupos."

    def _pessoa(self, email, dias, duracao):
        user = create_complete_user(
            email=email, experiencia="intermediario", split_preference=SplitPreference.DOIS,
            split_preference_confirmada=True, duracao_treino=duracao,
        )
        TrainingDay.objects.filter(user=user).delete()
        for d in range(dias):
            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
        return user

    @staticmethod
    def _oferta(resposta, valor):
        return '<input type="radio" name="duracao_treino" value="%s"' % valor in resposta.content.decode()

    def test_a_tela_nao_oferece_menos_de_75_e_diz_por_que(self):
        """(ii) A oferta: só faixas de 75 para cima (hoje, "Completo"), a
        regra escrita com "tempo" e o teto em vigor, 75."""
        uma_vez = self._pessoa("corpo-1x@exemplo.com", 1, DuracaoTreino.PADRAO)
        plan = services.create_routine(uma_vez)
        self.assertEqual((plan.split, plan.days_per_week), ("full", 1))
        self.client.force_login(uma_vez)
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertContains(resposta, self.REGRA)
        self.assertContains(resposta, 'até <span class="num">75</span> min por sessão')
        self.assertFalse(self._oferta(resposta, DuracaoTreino.RAPIDO))
        self.assertFalse(self._oferta(resposta, DuracaoTreino.PADRAO))
        self.assertTrue(self._oferta(resposta, DuracaoTreino.COMPLETO))
        # Controle: quem treina três vezes vê as três faixas, não lê a regra,
        # e o teto é o dele.
        tres = self._pessoa("corpo-3x@exemplo.com", 3, DuracaoTreino.PADRAO)
        services.create_routine(tres)
        self.client.force_login(tres)
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertNotContains(resposta, self.REGRA)
        self.assertContains(resposta, 'até <span class="num">60</span> min por sessão')
        for faixa in (DuracaoTreino.RAPIDO, DuracaoTreino.PADRAO, DuracaoTreino.COMPLETO):
            self.assertTrue(self._oferta(resposta, faixa), faixa)

    def test_um_envio_abaixo_de_75_nao_e_aceito(self):
        """(ii) no servidor: a lista fechada é a mesma da tela. Um formulário
        velho (ou forjado) com "Rápido" não grava a faixa e diz a regra."""
        uma_vez = self._pessoa("corpo-envio@exemplo.com", 1, DuracaoTreino.COMPLETO)
        services.create_routine(uma_vez)
        self.client.force_login(uma_vez)
        resposta = self.client.post(reverse("workouts:duracao"), {"duracao_treino": DuracaoTreino.RAPIDO}, follow=True)
        uma_vez.profile.refresh_from_db()
        self.assertEqual(uma_vez.profile.duracao_treino, DuracaoTreino.COMPLETO)
        # A mensagem, e não a página: a regra já está escrita no formulário.
        self.assertIn(self.REGRA, [str(m) for m in resposta.context["messages"]])
        # Controle: a mesma pessoa pode ficar no "Completo", e quem treina
        # três vezes pode escolher "Rápido".
        tres = self._pessoa("corpo-envio-3x@exemplo.com", 3, DuracaoTreino.PADRAO)
        services.create_routine(tres)
        self.client.force_login(tres)
        self.client.post(reverse("workouts:duracao"), {"duracao_treino": DuracaoTreino.RAPIDO})
        tres.profile.refresh_from_db()
        self.assertEqual(tres.profile.duracao_treino, DuracaoTreino.RAPIDO)

    def test_com_padrao_a_ficha_nasce_com_75_minutos_e_todos_os_grupos(self):
        """Autorizado pelo dono (27/09/2026): este teste prendia a saída (a) —
        "em 60 minutos o corpo inteiro tem de ceder algum grupo". Agora prende
        a (b): com "Padrão" (60) ou "Rápido" (30), o corpo inteiro de uma vez
        por semana é montado com 75 minutos, com os dez grupos, e a nota diz
        por quê. É o caminho (i) de 28/09/2026: a conta que JÁ tinha uma faixa
        menor — a tela não a oferece mais, mas ela continua gravada."""
        modelo = {i.exercise.muscle_group for t in services.templates_for("full") for i in t.items.all() if i.exercise.is_active}
        for duracao in (DuracaoTreino.PADRAO, DuracaoTreino.RAPIDO):
            with self.subTest(duracao=duracao):
                user = self._pessoa("corpo-%s@exemplo.com" % duracao, 1, duracao)
                plan = services.create_routine(user)
                presentes = {i.exercise.muscle_group for s in plan.sessions.all() for i in s.exercises.all()}
                self.assertEqual(modelo - presentes, set(), "nenhum grupo fora")
                minutos = max(s.estimated_minutes for s in plan.sessions.all())
                self.assertGreater(minutos, 60)
                self.assertLessEqual(minutos, 75)
                self.assertIn(self.FRASE, plan.notes)
        # Com "Completo" (90) a faixa já passa do mínimo: nada muda, e a nota
        # não fala dos 75.
        completo = self._pessoa("corpo-90@exemplo.com", 1, DuracaoTreino.COMPLETO)
        plan = services.create_routine(completo)
        presentes = {i.exercise.muscle_group for s in plan.sessions.all() for i in s.exercises.all()}
        self.assertEqual(modelo - presentes, set())
        self.assertLessEqual(max(s.estimated_minutes for s in plan.sessions.all()), 90)
        self.assertNotIn(self.FRASE, plan.notes)
        # E a ficha nascida com 75 é a que o motor produz hoje (não fica
        # "desatualizada" na conferência exata).
        from unittest import mock

        user = self._pessoa("corpo-confere@exemplo.com", 1, DuracaoTreino.PADRAO)
        plan = services.create_routine(user)
        with mock.patch.object(services, "versao_do_catalogo", return_value="catalogo-novo"):
            self.assertFalse(services.rotina_desatualizada(plan, user))


class OCorteDoRelogioTests(TestCase):
    """Duas regras do corte por tempo (`services.escolher_para_o_tempo`),
    decisões do dono de 27/09/2026, lidas LITERALMENTE:

    1. o complementar de fora do título (panturrilha, antebraço, core…)
       desce a UMA série antes de qualquer PRINCIPAL perder série — o
       isolador e o acessório do título continuam cedendo primeiro, até o
       piso de sempre;
    2. o exercício de um grupo acima do contrato semanal sai antes SÓ
       quando a alternativa é um principal perder série (o caso do dono: o
       supino fica em quatro e a letra A perde o ombro).
    """

    @staticmethod
    def _minutos(itens, ficam):
        return services._segundos_da_sessao(
            [(s, itens[i][2], itens[i][3] >= services.ACESSORIO) for i, s in ficam]
        ) / 60

    @staticmethod
    def _pernas():
        return [
            ("quads", 4, 80, services.PRINCIPAL), ("quads", 3, 60, services.ISOLADOR),
            ("hamstrings", 4, 80, services.PRINCIPAL), ("hamstrings", 3, 60, services.ISOLADOR),
            ("calves", 3, 60, services.ISOLADOR), ("core", 3, 60, services.ISOLADOR),
        ]

    def _cheio(self, itens):
        return services._segundos_da_sessao([(s, r, g >= services.ACESSORIO) for _, s, r, g in itens]) / 60

    def test_sem_principal_em_jogo_o_complementar_fica_no_piso_de_sempre(self):
        """Seis minutos a cortar: os quatro isoladores descem ao piso de
        duas — o título e o complementar juntos — e ninguém vai a uma."""
        itens = self._pernas()
        series = dict(services.escolher_para_o_tempo(itens, int(self._cheio(itens) - 6), principais=["quads", "hamstrings"]))
        self.assertEqual((series[0], series[2]), (4, 4), "os principais na dose")
        self.assertEqual((series[1], series[3], series[4], series[5]), (2, 2, 2, 2))

    def test_antes_de_o_principal_perder_serie_o_complementar_desce_a_uma(self):
        """Nove minutos: com todo isolador no piso ainda passa, e a próxima
        concessão seria o agachamento. Antes dela, o complementar desce a
        UMA série — e o principal fica na dose."""
        itens = self._pernas()
        series = dict(services.escolher_para_o_tempo(itens, int(self._cheio(itens) - 9), principais=["quads", "hamstrings"]))
        self.assertEqual((series[0], series[2]), (4, 4), "os principais na dose")
        self.assertEqual((series[4], series[5]), (1, 1), "o complementar desceu a uma série")
        self.assertEqual((series[1], series[3]), (2, 2), "o isolador do título no piso de sempre")

    def test_o_composto_complementar_fica_no_piso_de_composto(self):
        """A remada alta do trapézio é complementar em "Costas e bíceps", mas
        é composto: cede antes do principal do título, e desce a três, nunca a
        uma — abaixo de três o composto vira aquecimento (`PISO_COMPOSTO`)."""
        itens = [
            ("back", 4, 80, services.PRINCIPAL), ("biceps", 3, 60, services.ISOLADOR),
            ("traps", 4, 80, services.PRINCIPAL), ("forearms", 3, 60, services.ISOLADOR),
        ]
        ficam = dict(services.escolher_para_o_tempo(itens, 30, principais=["back", "biceps"]))
        self.assertEqual(ficam.get(2), 3, "o composto complementar cedeu até três, e não abaixo")
        self.assertEqual(ficam.get(0), 4, "e cedeu ANTES do principal do título")

    def _peito_triceps_ombro(self):
        return [
            ("chest", 4, 80, services.PRINCIPAL), ("chest", 3, 80, services.ACESSORIO),
            ("chest", 3, 80, services.ACESSORIO), ("shoulders", 3, 80, services.PRINCIPAL),
            ("chest", 2, 60, services.ISOLADOR), ("shoulders", 2, 60, services.ISOLADOR),
            ("triceps", 2, 60, services.ISOLADOR), ("triceps", 3, 80, services.PRINCIPAL),
            ("triceps", 2, 60, services.ISOLADOR),
        ]

    def test_na_sessao_de_academia_o_supino_fica_em_quatro_e_sai_o_segundo_ombro(self):
        itens = self._peito_triceps_ombro()
        ficam = services.escolher_para_o_tempo(itens, 60, principais=["chest", "triceps", "shoulders"])
        series = dict(ficam)
        self.assertEqual(series[0], 4, "o supino manteve as quatro séries")
        self.assertNotIn(5, series, "o segundo exercício de ombro saiu")
        grupos = [itens[i][0] for i, _ in ficam]
        self.assertEqual((grupos.count("chest"), grupos.count("triceps"), grupos.count("shoulders")), (4, 3, 1))
        self.assertLessEqual(self._minutos(itens, ficam), 60)

    def test_o_unico_exercicio_de_um_grupo_do_titulo_nao_e_excedente(self):
        """O glúteo é família do posterior para o relógio, mas é GRUPO do
        título: a elevação pélvica, único glúteo, não é "excedente sem
        contrato" do posterior (dono, 27/09/2026: todo grupo do título tem
        pelo menos um exercício). Quem sai é o segundo quadríceps."""
        itens = [
            ("quads", 4, 80, services.PRINCIPAL), ("quads", 3, 80, services.ACESSORIO),
            ("hamstrings", 4, 80, services.PRINCIPAL), ("glutes", 3, 80, services.ACESSORIO),
            ("shoulders", 3, 80, services.PRINCIPAL), ("calves", 3, 60, services.ISOLADOR),
            ("core", 3, 60, services.ISOLADOR),
        ]
        ficam = dict(services.escolher_para_o_tempo(
            itens, 45, principais=["quads", "hamstrings", "glutes", "shoulders"],
        ))
        self.assertIn(3, ficam, "a elevação pélvica ficou")
        self.assertNotIn(1, ficam, "saiu o segundo quadríceps")
        self.assertEqual((ficam[0], ficam[2]), (4, 4), "os principais na dose")

    def test_sem_principal_para_perder_serie_o_complementar_nao_desce_a_uma(self):
        """O ALCANCE da regra 1, lido literalmente: "desce a 1 série antes de
        qualquer PRINCIPAL perder série". Com todo principal já no piso
        (três), não há principal para perder série e a regra não fala — vale
        a ordem de sempre: o complementar sai inteiro (camada 3) em vez de
        ficar com uma série. É um efeito que o dono não viu: está no
        relatório da rodada 3."""
        itens = [
            ("chest", 3, 80, services.PRINCIPAL), ("chest", 2, 60, services.ISOLADOR),
            ("triceps", 2, 60, services.ISOLADOR), ("core", 2, 60, services.ISOLADOR),
        ]
        total = services._segundos_da_sessao([(s, r, g >= services.ACESSORIO) for _, s, r, g in itens])
        teto = (total - 1) // 60
        self.assertLessEqual(total - 100, teto * 60, "uma série a menos no core caberia")
        ficam = dict(services.escolher_para_o_tempo(itens, teto, principais=["chest", "triceps"]))
        self.assertNotIn(3, ficam, "o complementar saiu inteiro")

    def test_no_rapido_a_ordem_e_a_de_sempre(self):
        """Controle que DISCRIMINA: abaixo de 45 minutos o principal desce a
        três antes de um exercício anunciado sair. O caso é montado para que
        tirar o segundo ombro também coubesse — se a regra 2 valesse no
        Rápido, o supino ficaria em quatro e este teste ficaria vermelho."""
        itens = [
            ("chest", 4, 80, services.PRINCIPAL), ("chest", 3, 80, services.ACESSORIO),
            ("shoulders", 3, 80, services.PRINCIPAL), ("shoulders", 2, 60, services.ISOLADOR),
            ("triceps", 2, 60, services.ISOLADOR),
        ]
        total = services._segundos_da_sessao([(s, r, g >= services.ACESSORIO) for _, s, r, g in itens])
        teto = (total - 1) // 60
        self.assertLess(teto, 45)
        self.assertLessEqual(total - 200, teto * 60, "tirar o segundo ombro também caberia")
        ficam = dict(services.escolher_para_o_tempo(itens, teto, principais=["chest", "triceps", "shoulders"]))
        self.assertEqual(ficam[0], 3)
        self.assertIn(3, ficam, "o segundo ombro ficou")

    def test_sem_principal_para_perder_serie_o_segundo_ombro_nao_sai_antes_do_complementar(self):
        """A regra 2 dispara SÓ quando a alternativa é um principal perder
        série. Com todo principal já no piso (três), a ordem de sempre vale:
        o complementar sai inteiro (camada 3) antes de o título perder
        variedade — e aqui isso basta."""
        itens = [
            ("chest", 3, 80, services.PRINCIPAL), ("chest", 3, 80, services.ACESSORIO),
            ("shoulders", 3, 80, services.PRINCIPAL), ("shoulders", 2, 60, services.ISOLADOR),
            ("back", 3, 80, services.PRINCIPAL), ("back", 3, 80, services.ACESSORIO),
            ("core", 1, 60, services.ISOLADOR),
        ]
        total = services._segundos_da_sessao([(s, r, g >= services.ACESSORIO) for _, s, r, g in itens])
        sem_core = services._segundos_da_sessao([(s, r, g >= services.ACESSORIO) for _, s, r, g in itens[:-1]])
        teto = -(-sem_core // 60)
        self.assertGreaterEqual(teto, 45)
        self.assertLess(teto * 60, total)
        ficam = dict(services.escolher_para_o_tempo(itens, teto, principais=["chest", "shoulders", "back"]))
        self.assertNotIn(6, ficam, "o complementar saiu")
        self.assertIn(3, ficam, "o segundo ombro ficou")

    def test_ab_b_em_30_minutos_guarda_um_de_cada_grupo_do_titulo(self):
        """"Inferior" em Rápido: agachamento, stiff e elevação pélvica — os
        três grupos do título —, e não dois quadríceps com o glúteo fora. O
        glúteo é família do posterior, mas é GRUPO do título: a camada 4
        conta por grupo de verdade (revisão B, 27/09/2026)."""
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        user = create_complete_user(
            email="ab-b-30@exemplo.com", experiencia="intermediario", split_preference=SplitPreference.DOIS,
            split_preference_confirmada=True, duracao_treino=DuracaoTreino.RAPIDO,
        )
        TrainingDay.objects.filter(user=user).delete()
        for d in (1, 4):
            TrainingDay.objects.create(user=user, weekday=d, duration_min=30)
        plan = services.create_routine(user)
        b = next(s for s in plan.sessions.prefetch_related("exercises__exercise") if s.label == "B")
        nomes = {i.exercise.name for i in b.da_opcao(1)}
        for nome in ("Agachamento livre", "Stiff com barra", "Elevação pélvica"):
            self.assertIn(nome, nomes)
        self.assertLessEqual(b.minutos_da_opcao(1), 30)


def ficha_legada(plano, letra):
    """Devolve à letra de uma ficha nova a forma de ANTES de 27/09/2026: uma
    segunda opção gravada em `opcao=2`, com os exercícios do modelo que a
    opção 1 não usa (mesmo grupo, a dose do modelo) e, esgotado o grupo, o
    mesmo exercício — como `montar_opcoes` fazia. As 12 fichas ativas com
    opção 2 em 27/09/2026 têm esta forma; o motor não gera mais nenhuma."""
    modelo = next(t for t in services.templates_for(plano.split) if t.label == letra)
    do_modelo = [i for i in modelo.items.all() if i.exercise.is_active]
    for sessao in plano.sessions.filter(label=letra):
        op1 = list(sessao.exercises.filter(opcao=1).select_related("exercise").order_by("order"))
        usados = {linha.exercise_id for linha in op1}
        novas = []
        for linha in op1:
            troca = next(
                (i for i in do_modelo
                 if i.exercise.muscle_group == linha.exercise.muscle_group and i.exercise_id not in usados),
                None,
            )
            origem = troca or linha
            if troca is not None:
                usados.add(troca.exercise_id)
            novas.append(SessionExercise(
                session=sessao, exercise_id=origem.exercise_id, sets=origem.sets,
                rep_min=origem.rep_min, rep_max=origem.rep_max, measure=origem.measure,
                rest_seconds=origem.rest_seconds, order=linha.order, opcao=2,
            ))
        SessionExercise.objects.bulk_create(novas)


class FichaLegadaComDuasOpcoesTests(Catalogo):
    """"Motor lê as duas formas até a última sumir, com teste" (decisão do
    dono, 27/09/2026). A ficha NOVA sai só com `opcao=1`; a ficha LEGADA —
    linhas `opcao=2` gravadas antes — continua lida por `TrainingSession.
    opcoes`/`da_opcao`, pela variação por presença (`variacao_do_dia`), pela
    opção do dia (`opcao_do_dia`) e pela ficha renderizada."""

    def test_a_ficha_nova_so_tem_a_opcao_1(self):
        plan = services.create_routine(pessoa("intermediario_5d_2g", email="nova-uma@exemplo.com"))
        self.assertEqual(
            set(SessionExercise.objects.filter(session__plan=plan).values_list("opcao", flat=True)), {1},
        )
        for sessao in plan.sessions.all():
            self.assertEqual(sessao.opcoes, [1])

    def test_a_ficha_legada_continua_lendo_a_opcao_2(self):
        from workouts.test_sequencia import fazer

        user = pessoa("intermediario_5d_2g", email="legada@exemplo.com")
        plan = services.create_routine(user)
        ficha_legada(plan, "A")
        sessoes = list(plan.sessions.prefetch_related("exercises__exercise"))
        a = sorted((s for s in sessoes if s.label == "A"), key=lambda s: s.order)[0]
        self.assertEqual(a.opcoes, [1, 2])
        so_na_2 = {i.exercise_id for i in a.da_opcao(2)} - {i.exercise_id for i in a.da_opcao(1)}
        self.assertTrue(so_na_2, "a opção 2 legada precisa diferir para o teste medir")

        hoje = timezone.localdate()
        # Sem histórico, a primeira; com a letra feita uma vez, a SEGUNDA.
        self.assertEqual(services.variacao_do_dia(plan, hoje, a, sessoes, user=user), 1)
        fazer(user, plan, "A", hoje - timedelta(days=1))
        self.assertEqual(services.variacao_do_dia(plan, hoje, a, sessoes, user=user), 2)
        self.assertEqual(services.opcao_do_dia(user, a, hoje, sessoes=sessoes), 2)

        # A ficha da letra desenha a opção 2 — o exercício que só ela tem.
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:ficha", args=[a.pk])).content.decode()
        nomes_so_na_2 = [i.exercise.name for i in a.da_opcao(2) if i.exercise_id in so_na_2]
        self.assertTrue(any(nome in html for nome in nomes_so_na_2), nomes_so_na_2)


class VarianteUnicaPorCotaTests(TestCase):
    """A variante única (27/09/2026): UMA lista por letra, montada pela cota
    de exercícios por grupo do `TREINO.md` (tabela A, "Tipos de dia") — o
    principal de cada grupo primeiro, todo grupo anunciado coberto, o resto
    da cota na ordem do modelo, e um exercício de cada complementar (o
    principal dele, quando tem). Substitui "N opções de meio modelo"."""

    def test_as_cotas_saem_da_tabela_a_e_dos_tipos_de_dia(self):
        from workouts import doutrina

        casos = (
            (["chest", "triceps"], doutrina.DOIS_GRUPOS, {("chest",): 4, ("triceps",): 3}),
            # Quadríceps e posterior dividem o grande; o glúteo anunciado tem
            # a vaga DELE (dono, 27/09/2026: todo grupo do título tem pelo
            # menos um exercício — não come a cota do grande).
            (["quads", "hamstrings", "glutes", "shoulders"], doutrina.DOIS_GRUPOS,
             {("quads", "hamstrings"): 4, ("glutes",): 1, ("shoulders",): 3}),
            (["biceps", "triceps"], doutrina.DOIS_GRUPOS, {("biceps",): 3, ("triceps",): 3}),
            # O contrato semanal 4/4/3/3 vence a tabela A (dono, 27/09/2026):
            # a mesma lista em toda ocorrência, então a variedade da semana é
            # a da lista — três bíceps, e não os dois da tabela.
            (["back", "biceps", "forearms", "traps"], doutrina.TRES_GRUPOS,
             {("back",): 4, ("biceps",): 3, ("forearms", "traps"): 2}),
            (["chest", "triceps", "shoulders"], doutrina.TRES_GRUPOS,
             {("chest",): 4, ("triceps",): 3, ("shoulders",): 2}),
            (["quads", "hamstrings", "glutes", "calves"], doutrina.TRES_GRUPOS,
             {("quads", "hamstrings"): 4, ("glutes",): 1, ("calves",): 2}),
            (["quads", "hamstrings", "glutes"], doutrina.INFERIOR, {("quads",): 3, ("hamstrings", "glutes"): 3}),
            (["chest", "back", "shoulders", "biceps", "triceps"], doutrina.SUPERIOR,
             {("chest",): 2, ("back",): 2, ("shoulders",): 1, ("biceps",): 1, ("triceps",): 1}),
            # Posterior e glúteo dividem UMA cota de grande, mas os dois são
            # anunciados: a cota sobe para cobrir os dois.
            (["quads", "chest", "back", "hamstrings", "glutes", "shoulders", "biceps", "triceps"], doutrina.FULL,
             {("quads",): 1, ("chest",): 1, ("back",): 1, ("hamstrings", "glutes"): 2,
              ("shoulders",): 1, ("biceps",): 1, ("triceps",): 1}),
            # "Ombros": o trapézio anunciado tem cota 0 de pequeno e entra
            # como complementar — um.
            (["shoulders", "traps"], doutrina.UM_GRUPO, {("shoulders",): 4, ("traps",): 1}),
            # `abcd D`, fora do contrato: o máximo do complementar, dois.
            (["hamstrings", "glutes", "traps", "calves", "forearms", "core"], None,
             {("hamstrings", "glutes"): 2, ("traps",): 2, ("calves",): 2, ("forearms",): 2, ("core",): 2}),
        )
        for principais, tipo, esperado in casos:
            with self.subTest(principais=principais, tipo=tipo):
                self.assertEqual(dict(opcoes.cotas(principais, tipo, "intermediario")), esperado)
        # "Semanal vence: 3 de tríceps QUANDO A LETRA É 1× POR SEMANA" (dono,
        # 27/09/2026, literal): a letra que repete fica com a tabela A.
        self.assertEqual(dict(opcoes.cotas(["chest", "triceps", "shoulders"], doutrina.TRES_GRUPOS, "intermediario", vezes=2)),
                         {("chest",): 4, ("triceps",): 2, ("shoulders",): 2})
        # O nível muda a dose: o iniciante tem 3 de grande em dois grupos —
        # e o contrato 4/4/3/3 é do intermediário para cima.
        self.assertEqual(dict(opcoes.cotas(["chest", "triceps"], doutrina.DOIS_GRUPOS, "iniciante")),
                         {("chest",): 3, ("triceps",): 2})
        self.assertEqual(dict(opcoes.cotas(["chest", "triceps", "shoulders"], doutrina.TRES_GRUPOS, "iniciante")),
                         {("chest",): 3, ("triceps",): 2, ("shoulders",): 2})

    def _itens(self, *linhas):
        return [Falso(pk, grupo, sets=sets, composto=composto) for pk, grupo, sets, composto in linhas]

    def test_o_principal_primeiro_todo_anunciado_coberto_e_o_padrao_novo_antes_do_repetido(self):
        """"Pernas e ombros": a cota do grande (4) é de quadríceps e
        posterior, e o glúteo anunciado tem a vaga DELE (dono, 27/09/2026).
        O agachamento e o stiff (principais) entram, e o resto da cota é do
        grupo menos servido preferindo um PADRÃO que o grupo ainda não tem: a
        cadeira extensora (extensão de joelho) e a mesa flexora (flexão de
        joelho), e não o leg press (outro agachamento). No ombro, a elevação
        e o deltoide posterior antes do segundo desenvolvimento — três
        padrões, três porções do ombro. A opção 1 de antes perdia o stiff
        para a opção 2."""
        from workouts import doutrina

        linhas = (
            (1, "quads", 4, True, "agachamento"), (2, "quads", 4, True, "agachamento"),
            (3, "quads", 3, False, "extensao_de_joelho"), (4, "hamstrings", 4, True, "extensao_de_quadril"),
            (5, "hamstrings", 3, False, "flexao_de_joelho"), (6, "glutes", 3, True, "extensao_de_quadril"),
            (7, "shoulders", 3, True, "pressao_vertical"), (8, "shoulders", 3, False, "elevacao"),
            (9, "shoulders", 3, True, "pressao_vertical"), (10, "shoulders", 3, False, "deltoide_posterior"),
            (11, "calves", 4, False, "flexao_plantar"), (12, "calves", 3, False, "flexao_plantar"),
            (13, "core", 3, False, "anti_extensao"), (14, "core", 3, False, "flexao_de_tronco"),
        )
        itens = [Falso(pk, grupo, sets=sets, composto=composto, padrao=padrao)
                 for pk, grupo, sets, composto, padrao in linhas]
        variante = opcoes.variante_unica(
            itens, ["quads", "hamstrings", "glutes", "shoulders"], doutrina.DOIS_GRUPOS, "intermediario",
        )
        self.assertEqual([i.exercise_id for i in variante], [1, 3, 4, 5, 6, 7, 8, 10, 11, 13])

    def test_quadriceps_e_posterior_dividem_o_grande_e_o_gluteo_tem_a_vaga_dele(self):
        """"Pernas completo" (`abc C`): a cota do grande (4) é de quadríceps
        e posterior — dois de cada, o principal e um padrão novo (a mesa
        flexora; a cadeira extensora) — e o glúteo anunciado tem a vaga DELE
        (dono, 27/09/2026: todo grupo do título tem pelo menos um exercício;
        TREINO.md: "o glúteo direto é UM exercício por letra de perna").
        Quando o glúteo comia uma das quatro vagas, a semana de três dias
        ficava com UM quadríceps ou UM posterior."""
        from workouts import doutrina

        linhas = (
            (1, "quads", 4, True, "agachamento"), (2, "quads", 4, True, "agachamento"),
            (3, "hamstrings", 4, True, "extensao_de_quadril"), (4, "hamstrings", 3, False, "flexao_de_joelho"),
            (5, "calves", 4, False, "flexao_plantar"), (6, "calves", 3, False, "flexao_plantar"),
            (7, "core", 3, False, "anti_extensao"), (8, "quads", 4, True, "agachamento"),
            (9, "quads", 3, False, "extensao_de_joelho"), (10, "glutes", 3, True, "extensao_de_quadril"),
        )
        itens = [Falso(pk, grupo, sets=sets, composto=composto, padrao=padrao)
                 for pk, grupo, sets, composto, padrao in linhas]
        variante = opcoes.variante_unica(
            itens, ["quads", "hamstrings", "glutes", "calves"], doutrina.TRES_GRUPOS, "intermediario",
        )
        self.assertEqual([i.exercise_id for i in variante], [1, 3, 4, 5, 6, 7, 9, 10])

    def test_no_grande_de_um_grupo_so_a_ordem_do_modelo_fica(self):
        """"Peito e tríceps" do iniciante (3 + 2): o peito é o grande de UM
        grupo só, e a ordem do modelo — supino reto, inclinado, flexão — é a
        curadoria da ficha e fica; o crucifixo (padrão novo) não passa na
        frente da flexão. Com o padrão novo primeiro também aqui, a letra A do
        iniciante caía a 38 minutos e o dourado (40) reprovava. No tríceps
        (pequeno) o padrão novo vem antes: mergulho e testa, não dois
        mergulhos."""
        from workouts import doutrina

        linhas = (
            (1, "chest", 4, True, "pressao_de_peito"), (2, "chest", 4, True, "pressao_de_peito"),
            (3, "chest", 3, True, "pressao_de_peito"), (4, "chest", 3, False, "crucifixo"),
            (5, "triceps", 3, True, "pressao_fechada"), (6, "triceps", 3, True, "pressao_fechada"),
            (7, "triceps", 3, False, "extensao_de_cotovelo"),
        )
        itens = [Falso(pk, grupo, sets=sets, composto=composto, padrao=padrao)
                 for pk, grupo, sets, composto, padrao in linhas]
        variante = opcoes.variante_unica(itens, ["chest", "triceps"], doutrina.DOIS_GRUPOS, "iniciante")
        self.assertEqual([i.exercise_id for i in variante], [1, 2, 3, 5, 7])

    def test_o_iniciante_comeca_pelo_degrau_mais_baixo_da_escada(self):
        """TREINO.md, "O degrau do iniciante": no peso do corpo ele começa
        pelo degrau mais fácil. Entre flexões do mesmo grupo, depois do
        principal, a de joelhos apoiados (degrau 1) vem antes da flexão
        (degrau 3) — o intermediário segue a ordem do modelo."""
        from workouts import doutrina

        linhas = ((1, 4, 3), (2, 4, 2), (3, 3, 3), (4, 4, 1))
        itens = []
        for pk, sets, degrau in linhas:
            item = Falso(pk, "chest", sets=sets, composto=True, padrao="pressao_de_peito")
            item.exercise.progressao = {"nivel": degrau, "movimento": "flexao"}
            itens.append(item)
        iniciante = opcoes.variante_unica(itens, ["chest"], doutrina.DOIS_GRUPOS, "iniciante")
        self.assertEqual([i.exercise_id for i in iniciante], [1, 2, 4])
        intermediario = opcoes.variante_unica(itens, ["chest"], doutrina.DOIS_GRUPOS, "intermediario")
        self.assertEqual([i.exercise_id for i in intermediario], [1, 2, 3, 4])

    def test_esgotados_os_padroes_o_segundo_composto_do_mesmo_padrao_vem_por_ultimo(self):
        """"Peito, tríceps e ombro" com o contrato semanal (3 tríceps): depois
        do mergulho (principal) e da corda (padrão novo), o terceiro repete um
        padrão — e repetir a extensão de cotovelo (a testa) vem antes do
        SEGUNDO composto de pressão fechada (o supino fechado). O modelo
        lista dois de cada padrão composto porque cada antiga opção
        precisava de um: esse segundo não é variedade, é a opção 2 que não
        existe mais. Com o supino fechado a letra A não cabia em 60 minutos
        e o relógio tirava o quarto peito."""
        from workouts import doutrina

        linhas = (
            (1, "chest", 4, True, "pressao_de_peito"), (2, "chest", 4, True, "pressao_de_peito"),
            (3, "chest", 3, True, "pressao_de_peito"), (4, "chest", 3, False, "crucifixo"),
            (5, "triceps", 3, False, "extensao_de_cotovelo"), (6, "triceps", 3, True, "pressao_fechada"),
            (7, "triceps", 3, True, "pressao_fechada"), (8, "triceps", 3, False, "extensao_de_cotovelo"),
        )
        itens = [Falso(pk, grupo, sets=sets, composto=composto, padrao=padrao)
                 for pk, grupo, sets, composto, padrao in linhas]
        variante = opcoes.variante_unica(itens, ["chest", "triceps"], doutrina.TRES_GRUPOS, "intermediario")
        self.assertEqual([i.exercise_id for i in variante], [1, 2, 3, 4, 5, 6, 8])

    def test_o_complementar_nao_anunciado_fica_em_ate_tres_series(self):
        """TREINO.md, tabela A: "o complementar não anunciado (zero a dois por
        opção, de duas a três séries)". A panturrilha em pé do catálogo pede
        quatro — a dose de quem a ANUNCIA ("Pernas completo", até quatro);
        em "Pernas e ombros" ela é complementar e entra com três."""
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        user = pessoa("intermediario_5d_2g", email="complementar-3@exemplo.com")
        from accounts.models import Profile

        Profile.objects.filter(user=user).update(duracao_treino=DuracaoTreino.COMPLETO)
        user.refresh_from_db()
        plan = services.create_routine(user)
        c = por_letra(plan)["C"]
        complementares = [i for i in c.da_opcao(1) if i.exercise.muscle_group not in c.main_groups]
        self.assertTrue(complementares)
        for item in complementares:
            with self.subTest(exercicio=item.exercise.name):
                self.assertLessEqual(item.sets, 3)

    def test_o_complementar_entra_pelo_principal_dele(self):
        """Trapézio complementar em "Costas e bíceps": o encolhimento vem
        antes no modelo, mas a remada alta é o PRINCIPAL do grupo — e o
        principal da divisão tem de aparecer na semana."""
        from workouts import doutrina

        itens = self._itens(
            (1, "back", 4, True), (2, "back", 4, True), (3, "back", 3, True), (4, "back", 3, True),
            (5, "back", 3, True), (6, "biceps", 3, False), (7, "biceps", 3, False), (8, "biceps", 3, False),
            (9, "biceps", 3, False), (10, "traps", 3, False), (11, "traps", 3, True),
            (12, "forearms", 3, False), (13, "forearms", 3, False),
        )
        variante = opcoes.variante_unica(itens, ["back", "biceps"], doutrina.DOIS_GRUPOS, "intermediario")
        self.assertEqual([i.exercise_id for i in variante], [1, 2, 3, 4, 6, 7, 8, 11, 12])

    def test_toda_letra_de_ficha_nova_e_uma_lista_com_a_cota(self):
        """O perfil do dourado com o catálogo real: uma opção por letra, a
        MESMA em toda ocorrência, com a cota da tabela A nos anunciados e o
        principal de cada grupo do modelo presente."""
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        plan = services.create_routine(pessoa("intermediario_5d_2g", email="cota@exemplo.com"))
        sessoes = sorted(plan.sessions.prefetch_related("exercises__exercise"), key=lambda s: s.order)
        for letra in ("A", "B", "C"):
            da_letra = [s for s in sessoes if s.label == letra]
            assinaturas = {tuple((i.opcao, i.exercise_id, i.sets) for i in s.exercises.all()) for s in da_letra}
            with self.subTest(letra=letra):
                self.assertEqual(len(assinaturas), 1, "a letra repetida é o mesmo treino")
                self.assertEqual(da_letra[0].opcoes, [1])
        a = next(s for s in sessoes if s.label == "A")
        grupos = [i.exercise.muscle_group for i in a.da_opcao(1)]
        self.assertEqual((grupos.count("chest"), grupos.count("triceps")), (4, 3))
        nomes = {i.exercise.name for s in sessoes for i in s.exercises.all()}
        for principal in ("Supino reto com barra", "Barra fixa assistida", "Remada alta com barra",
                          "Agachamento livre", "Stiff com barra", "Desenvolvimento com halteres"):
            self.assertIn(principal, nomes)
