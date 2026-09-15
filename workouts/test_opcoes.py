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
promessa: a sessão de "peito e tríceps" tem 4 exercícios porque o catálogo
tem 4 peitos e 3 tríceps — duas opções distintas de 3+3 pediriam 6 e 6.
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
from workouts.models import EscolhaDeTreino, ExerciseLog, SessionExercise, TrainingPlan

PERFIS = {
    "iniciante_3d_2g": ("iniciante", SplitPreference.DOIS, [0, 2, 4]),
    "intermediario_5d_2g": ("intermediario", SplitPreference.DOIS, [0, 1, 2, 3, 4]),
    "avancado_6d_2g": ("avancado", SplitPreference.DOIS, [0, 1, 2, 3, 4, 5]),
    "intermediario_4d_3g": ("intermediario", SplitPreference.TRES, [0, 1, 3, 4]),
    # Dois dias: o modelo "Superior" tem um exercício por grupo em quase
    # tudo — o catálogo não sustenta duas opções distintas para a letra A.
    "intermediario_2d": ("intermediario", SplitPreference.DOIS, [1, 4]),
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
        por grupo de diferença, ≤ 5 min, metade dos exercícios próprios."""
        for nome in PERFIS:
            plan = services.create_routine(pessoa(nome))
            for label, sessao in por_letra(plan).items():
                if not sessao.tem_duas_opcoes:
                    continue
                with self.subTest(perfil=nome, letra=label):
                    op1, op2 = sessao.da_opcao(1), sessao.da_opcao(2)
                    anunciados = set(sessao.main_groups)
                    for op in (op1, op2):
                        self.assertTrue(anunciados <= {i.exercise.muscle_group for i in op},
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
        """O número de hoje, com o catálogo de hoje — escrito, não prometido."""
        esperado = {
            "iniciante_3d_2g": {"A": 2, "B": 2, "C": 2},
            "intermediario_5d_2g": {"A": 2, "B": 2, "C": 2},
            "avancado_6d_2g": {"A": 2, "B": 2, "C": 2},
            "intermediario_4d_3g": {"A": 2, "B": 2, "C": 2},
            "intermediario_2d": {"A": 1, "B": 2},
        }
        for nome, por_label in esperado.items():
            plan = services.create_routine(pessoa(nome))
            for label, sessao in por_letra(plan).items():
                with self.subTest(perfil=nome, letra=label):
                    self.assertEqual(len(sessao.opcoes), por_label[label])

    def test_o_tamanho_das_sessoes_hoje(self):
        """13 a 22 séries e 30 a 52 minutos, e a razão está no catálogo e no
        teto: "peito e tríceps" tem 4 exercícios por opção porque o catálogo
        tem 4 peitos e 3 tríceps (duas opções distintas de 3+3 pediriam 6 e
        6), e com a letra duas vezes na semana o teto de 20 séries efetivas
        deixa ~10 por sessão para o tríceps, já contando o secundário dos
        supinos. A faixa é registrada para a próxima leitura não achar que
        houve regressão — e para o dia em que o catálogo crescer ficar visível.
        """
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        sessoes = por_letra(plan)
        for label, sessao in sessoes.items():
            for k in sessao.opcoes:
                with self.subTest(letra=label, opcao=k):
                    self.assertGreaterEqual(sessao.series_da_opcao(k), 13)
                    # C leva panturrilha e abdômen além dos anunciados: até 6 acima do teto da faixa.
                    self.assertLessEqual(sessao.series_da_opcao(k), opcoes.TETO_SERIES_COMPLETO + 6)
                    self.assertLessEqual(sessao.minutos_da_opcao(k), 60)
        self.assertEqual(len(sessoes["A"].da_opcao(1)), 4)

    def test_repetir_a_mesma_opcao_cabe_no_teto_semanal(self):
        """O pior caso — toda ocorrência da letra na opção mais pesada de cada
        grupo — fica no teto da pessoa, exceto o excesso que só um composto
        principal poderia resolver (teto de aparo, não promessa)."""
        for nome in PERFIS:
            user = pessoa(nome)
            plan = services.create_routine(user)
            teto = services.teto_semanal_de(user)
            pior = services.volume_da_semana(plan)
            for grupo, volume in pior.items():
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
        self.assertLessEqual(pior["chest"], 20)

    def test_a_ocorrencia_da_letra_carrega_as_mesmas_opcoes(self):
        """A de segunda e A de quinta são o MESMO treino com as mesmas duas
        opções — nunca mais A1 ≠ A2 como dias obrigatórios."""
        plan = services.create_routine(pessoa("intermediario_5d_2g"))
        sessoes = sorted(plan.sessions.prefetch_related("exercises"), key=lambda s: s.order)
        a1, a2 = [s for s in sessoes if s.label == "A"]
        assinatura = lambda s: [(i.opcao, i.exercise_id, i.sets) for i in s.exercises.all()]
        self.assertEqual(assinatura(a1), assinatura(a2))

    def test_sem_catalogo_para_duas_a_letra_sai_com_uma_e_inteira(self):
        """Dois dias: "Superior" tem um exercício em quase todo grupo. Uma
        opção só — e é o modelo inteiro no tempo, não a metade que sobrou."""
        plan = services.create_routine(pessoa("intermediario_2d"))
        a = por_letra(plan)["A"]
        self.assertEqual(a.opcoes, [1])
        self.assertGreaterEqual(len(a.da_opcao(1)), 6)

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
        user = pessoa("intermediario_5d_2g")
        plan = services.create_routine(user)
        self.assertTrue(services.routine_is_current(plan, user))
        # Uma linha da opção 2 mexida à mão: a ficha deixa de ser atual.
        item = SessionExercise.objects.filter(session__plan=plan, opcao=2).first()
        SessionExercise.objects.filter(pk=item.pk).update(sets=item.sets + 1)
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
        def __init__(self, pk, grupo, composto=False, secundarios=()):
            self.pk = pk
            self.muscle_group = grupo
            self.is_compound = composto
            self.secondary_muscles = list(secundarios)

    def __init__(self, pk, grupo, sets=3, composto=False, rest=60):
        self.exercise_id = pk
        self.exercise = Falso.Exercicio(pk, grupo, composto)
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
        self.sessao = self.plan.sessions.get(weekday=hoje)
        self.client.force_login(self.user)

    def test_sem_escolha_a_execucao_abre_a_recomendada_e_diz_isso(self):
        """A Home, o demo e um link antigo chegam à execução direto: ela
        abre a opção recomendada, avisa, e a porta para trocar é a ficha."""
        resposta = self.client.get(reverse("workouts:now"))
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertIn("a recomendada de hoje", html)
        self.assertIn(reverse("workouts:ficha", args=[self.sessao.pk]), html)
        self.assertEqual(resposta.context["estado"].opcao, services.opcao_recomendada(self.user, self.sessao))
        # A ficha, sem escolha, já tem as portas "Fazer" na recomendada.
        ficha = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode()
        self.assertIn('class="ficha-item__estado ficha-item__fazer', ficha)

    def test_a_ficha_mostra_as_duas_e_recomenda_a_menos_usada(self):
        html = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode()
        self.assertIn("Opção 1", html)
        self.assertIn("Opção 2", html)
        self.assertIn("Recomendada hoje", html)
        self.assertNotIn("Treino %s1" % self.sessao.label, html)
        # Ontem a pessoa fez a opção 1 desta letra: hoje a 2 é a recomendada.
        irma = self.plan.sessions.filter(label=self.sessao.label).exclude(pk=self.sessao.pk).first() or self.sessao
        EscolhaDeTreino.objects.create(
            user=self.user, date=timezone.localdate() - timedelta(days=3), session=irma, opcao=1
        )
        self.assertEqual(services.opcao_recomendada(self.user, self.sessao), 2)

    def test_comecar_esta_opcao_grava_a_escolha_e_abre_a_execucao(self):
        resposta = self.client.post(
            reverse("workouts:escolher", args=[self.sessao.pk]), {"opcao": 2, "versao": "completo"}
        )
        self.assertRedirects(resposta, reverse("workouts:now"))
        escolha = EscolhaDeTreino.objects.get(user=self.user, date=timezone.localdate())
        self.assertEqual((escolha.opcao, escolha.versao), (2, "completo"))
        estado = services.estado_do_treino(self.user)
        self.assertEqual(estado.opcao, 2)
        self.assertEqual({i.exercise_id for i in estado.itens}, {i.exercise_id for i in self.sessao.da_opcao(2)})

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

    def test_trocar_depois_da_primeira_serie_pede_confirmacao_e_nao_apaga(self):
        services.registrar_escolha(self.user, self.sessao, 1)
        item = self.sessao.da_opcao(1)[0]
        ExerciseLog.objects.create(user=self.user, exercise=item.exercise, date=timezone.localdate(), set_number=1, weight_kg=40)
        resposta = self.client.post(reverse("workouts:escolher", args=[self.sessao.pk]), {"opcao": 2})
        self.assertRedirects(resposta, reverse("workouts:ficha", args=[self.sessao.pk]) + "?trocar=2&versao=completo")
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user).opcao, 1, "sem confirmação, nada muda")
        html = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]) + "?trocar=2").content.decode()
        self.assertIn("Trocar para a opção 2?", html)
        resposta = self.client.post(reverse("workouts:escolher", args=[self.sessao.pk]), {"opcao": 2, "confirmar": "1"})
        self.assertRedirects(resposta, reverse("workouts:now"))
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user).opcao, 2)
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 1, "trocar não apaga registro")

    def test_a_versao_rapida_na_execucao_nomeia_o_que_ficou_de_fora(self):
        services.registrar_escolha(self.user, self.sessao, 1, versao="rapido")
        estado = services.estado_do_treino(self.user)
        self.assertTrue(estado.rapida)
        completa = self.sessao.da_opcao(1)
        self.assertLessEqual(sum(i.sets for i in estado.itens), sum(i.sets for i in completa))
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn("Opção 1", html)
        if estado.removidos:
            self.assertIn("Fora da versão rápida", html)
        # Nada foi gravado: a ficha continua com as séries completas.
        self.assertEqual(sum(i.sets for i in self.sessao.da_opcao(1)), sum(i.sets for i in completa))

    def test_a_ficha_de_outro_dia_nao_aceita_escolha(self):
        outra = self.plan.sessions.exclude(weekday=timezone.localdate().weekday()).first()
        self.assertEqual(
            self.client.post(reverse("workouts:escolher", args=[outra.pk]), {"opcao": 1}).status_code, 404
        )

    def test_o_painel_tem_um_cartao_por_letra_e_diz_duas_versoes(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertEqual(html.count('<a class="sessao-cartao'), 3)
        self.assertIn("Duas versões disponíveis", html)
        self.assertNotIn(">A1<", html)
        self.assertNotIn(">B2<", html)


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
