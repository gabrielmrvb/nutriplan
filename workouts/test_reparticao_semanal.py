"""TREINO — a letra que repete distribui exercícios, e o relógio não apaga músculo.

DOIS DEFEITOS ESTRUTURAIS, reproduzidos em 10/09/2026 no perfil da auditoria
(homem, 27, 185 cm, 102 kg, intermediário, 45-60 min, 2 grupos por dia) e
confirmados em TODAS as frequências de 1 a 7 dias.

1. A LETRA REPETIDA RECEBIA A LISTA INTEIRA, DUAS VEZES. `prescrever_semana`
   calculava `indice = vistas.get(label, 0)` e **não usava**. As duas passagens
   nasciam idênticas, o volume dobrava, e `aparar_volume_semanal` cortava para
   o teto semanal caber — cortando VARIEDADE. Medido antes:

       5 dias  A1 e A2 repetiam Supino reto e Mergulho no banco
       6 dias  + B1/B2 repetiam Barra fixa e Rosca direta
       7 dias  + C1/C2 repetiam QUATRO: agachamento, leg press, stiff e
               desenvolvimento

   E a variedade PIORAVA com mais dias — o oposto do esperado:

       3 dias  costas 3, tríceps 1
       5 dias  peito 3, tríceps 2
       7 dias  peito 2, costas 2, tríceps 2, bíceps 2

   O catálogo não era o limite: `abcd A` já lista os QUATRO peitos e os TRÊS
   tríceps do contrato. Eles entravam duas vezes e o aparo os derrubava.

2. O CORTE POR TEMPO APAGAVA MÚSCULO ANUNCIADO. `escolher_para_o_tempo` fazia
   rodízio entre grupos mas não tinha a trava que `aparar_volume_semanal` tem —
   "nunca o último exercício direto de um grupo". Medido com "até 30 minutos":

       "Peito, tríceps e ombro"                -> Supino e Desenvolvimento,
                                                  ZERO tríceps, tríceps no título
       "Costas, bíceps, antebraço e trapézio"  -> perdia TRÊS dos quatro grupos

NENHUM DOS DOIS DEPENDE DE IDADE, PESO OU ALTURA: o primeiro é a ausência de um
argumento, o segundo é a ausência de uma trava. Os doze cenários da auditoria
falharam pelo mesmo motivo.
"""
from collections import defaultdict
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import (
    ActivityLevel, DuracaoTreino, Experiencia, Goal, ONBOARDING_DONE, Profile,
    Sex, SplitPreference, TrainingDay, WeightEntry,
)

from . import services
from .models import MuscleGroup
from .services import PISO_COMPOSTO

User = get_user_model()

#: O contrato de variedade semanal, para 45 min ou mais, do intermediário para
#: cima. Os números são do produto; o catálogo os comporta exatamente — peito e
#: costas têm 4 exercícios ativos, tríceps e bíceps têm 3.
MINIMOS_SEMANAIS = {
    MuscleGroup.CHEST: 4,
    MuscleGroup.BACK: 4,
    MuscleGroup.TRICEPS: 3,
    MuscleGroup.BICEPS: 3,
}


def perfil(dias, preferencia=SplitPreference.DOIS,
           duracao=DuracaoTreino.PADRAO,
           experiencia=Experiencia.INTERMEDIARIO, sufixo=""):
    """O perfil da auditoria, variando só o que o teste pede.

    Idade, peso e altura entram porque a auditoria os variou — e a prova de que
    o defeito não depende deles é que os testes abaixo passam com este perfil
    fixo e com os extremos, em `AsFalhasNaoDependemDoCorpoTests`.
    """
    email = "rep-%d-%s-%s-%s%s@exemplo.com" % (
        dias, preferencia, duracao, experiencia, sufixo)
    user = User.objects.create_user(email=email, password="senha-bem-forte-123")
    Profile.objects.create(
        user=user, sex=Sex.MALE, birth_date=date(1999, 7, 8), height_cm=185,
        activity_level=ActivityLevel.LIGHT, goal=Goal.CUT,
        wake_time=time(7, 0), sleep_time=time(23, 0),
        onboarding_step=ONBOARDING_DONE, experiencia=experiencia,
        duracao_treino=duracao, split_preference=preferencia,
        split_preference_confirmada=True,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal("102.0"))
    for dia in range(dias):
        TrainingDay.objects.create(
            user=user, weekday=dia, start_time=time(19, 0), duration_min=60)
    user = User.objects.get(pk=user.pk)
    return user, services.create_routine(user)


def por_letra(plano):
    """{letra: [ [nomes da 1ª passagem], [nomes da 2ª], ... ]}"""
    saida = defaultdict(list)
    for sessao in plano.sessions.all().order_by("weekday"):
        saida[sessao.label].append([
            item.exercise.name
            for item in sessao.exercises.select_related("exercise")
        ])
    return saida


class ALetraRepetidaDistribuiExerciciosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_nenhuma_passagem_repete_enquanto_houver_opcao(self):
        """O defeito central, varrido de 1 a 7 dias.

        A regra não é "nunca repetir": é "não repetir enquanto o modelo ainda
        tiver exercício daquele grupo sem usar". Grupo com menos exercícios que
        passagens repete, e isso é a saída de último caso — a alternativa seria
        a segunda passagem anunciar um músculo que ela não treina.
        """
        for preferencia in SplitPreference.values:
          for dias in range(1, 8):
            with self.subTest(preferencia=preferencia, dias=dias):
                _, plano = perfil(dias, preferencia=preferencia, sufixo="-var")
                modelos = {t.label: t for t in services.templates_for(plano.split)}

                for letra, passagens in por_letra(plano).items():
                    if len(passagens) < 2:
                        continue
                    disponivel = defaultdict(set)
                    for item in modelos[letra].items.all():
                        if item.exercise.is_active:
                            disponivel[item.exercise.muscle_group].add(
                                item.exercise.name)

                    usados = defaultdict(list)
                    for nomes in passagens:
                        for nome in nomes:
                            usados[nome].append(1)
                    for nome, vezes in usados.items():
                        if len(vezes) == 1:
                            continue
                        grupo = next(
                            g for g, nomes in disponivel.items() if nome in nomes)
                        self.assertLess(
                            len(disponivel[grupo]), len(passagens),
                            "%s repetiu em %s com %d opções para %d passagens"
                            % (nome, letra, len(disponivel[grupo]), len(passagens)),
                        )

    def test_cada_passagem_recebe_uma_fatia_equilibrada_de_cada_grupo(self):
        """Repartir não é só "não repetir" — é repartir DIREITO.

        Com G exercícios de um grupo e N passagens, cada passagem leva entre
        `G//N` e `G//N + 1`. Sem isto, repartir a lista inteira sem olhar o
        grupo passa: as passagens não repetem e cobrem os grupos, mas uma leva
        três peitos e a outra um.
        """
        for preferencia in SplitPreference.values:
            for dias in range(4, 8):
                with self.subTest(preferencia=preferencia, dias=dias):
                    _, plano = perfil(dias, preferencia=preferencia, sufixo="-eq")
                    modelos = {
                        t.label: t for t in services.templates_for(plano.split)
                    }
                    contagem = defaultdict(lambda: defaultdict(int))
                    passagens = defaultdict(int)
                    for sessao in plano.sessions.all().order_by("weekday"):
                        passagens[sessao.label] += 1
                        chave = (sessao.label, passagens[sessao.label])
                        for item in sessao.exercises.select_related("exercise"):
                            contagem[chave][item.exercise.muscle_group] += 1

                    for letra, vezes in passagens.items():
                        if vezes < 2:
                            continue
                        do_modelo = defaultdict(int)
                        for item in modelos[letra].items.all():
                            if item.exercise.is_active:
                                do_modelo[item.exercise.muscle_group] += 1
                        for grupo, total in do_modelo.items():
                            piso = total // vezes
                            for i in range(1, vezes + 1):
                                recebido = contagem[(letra, i)][grupo]
                                self.assertGreaterEqual(recebido, max(1, piso) - 1)
                                self.assertLessEqual(
                                    recebido, piso + 1,
                                    "%s%d levou %d de %s, e o modelo tem %d "
                                    "para %d passagens"
                                    % (letra, i, recebido, grupo, total, vezes),
                                )

    def test_a_ficha_segue_a_ordem_do_modelo(self):
        """A ordem agrupa por REGIÃO, e o grau de prioridade sai dela.

        `prioridades_da_sessao` lê os itens NA ORDEM DA FICHA. Se a repartição
        devolvesse os itens agrupados por músculo, um exercício que não saiu do
        lugar mudaria de grau — e o corte por tempo passaria a ceder outro.
        """
        for dias in (5, 6, 7):
            with self.subTest(dias=dias):
                _, plano = perfil(dias, sufixo="-ordem")
                modelos = {
                    t.label: t for t in services.templates_for(plano.split)
                }
                for sessao in plano.sessions.all():
                    do_modelo = [
                        item.exercise_id for item in modelos[sessao.label].items.all()
                    ]
                    na_ficha = [
                        item.exercise_id
                        for item in sessao.exercises.all().order_by("order")
                    ]
                    posicoes = [do_modelo.index(e) for e in na_ficha]

                    self.assertEqual(
                        posicoes, sorted(posicoes),
                        "%s saiu fora da ordem do modelo" % sessao.label,
                    )

    def test_a_variedade_semanal_cumpre_o_contrato(self):
        """4 peito, 4 costas, 3 tríceps, 3 bíceps no ciclo da semana.

        Só de 4 dias para cima: com três dias a divisão aplicada é `abc`, cujo
        modelo B lista TRÊS costas — limitação do modelo, não do algoritmo, e
        está registrada em `AsLimitacoesQueSobramSaoDeCONTEUDOTests`.
        """
        for dias in range(4, 8):
            with self.subTest(dias=dias):
                _, plano = perfil(dias)
                distintos = defaultdict(set)
                for sessao in plano.sessions.all():
                    for item in sessao.exercises.select_related("exercise"):
                        distintos[item.exercise.muscle_group].add(item.exercise.name)

                for grupo, minimo in MINIMOS_SEMANAIS.items():
                    self.assertGreaterEqual(
                        len(distintos[grupo]), minimo,
                        "%s com %d exercícios distintos, contrato pede %d"
                        % (grupo, len(distintos[grupo]), minimo),
                    )

    def test_a_variedade_nao_piora_quando_a_frequencia_sobe(self):
        """A assinatura do defeito: mais dias davam MENOS movimentos distintos.

        Sete dias entregavam 2 exercícios de peito onde quatro dias entregavam
        4. Qualquer regressão que volte a duplicar a letra reaparece aqui.
        """
        distintos_por_dias = {}
        for dias in range(4, 8):
            _, plano = perfil(dias, sufixo="-monot")
            nomes = {
                item.exercise.name
                for sessao in plano.sessions.all()
                for item in sessao.exercises.select_related("exercise")
            }
            distintos_por_dias[dias] = len(nomes)

        for dias in range(5, 8):
            self.assertGreaterEqual(
                distintos_por_dias[dias], distintos_por_dias[4] - 1,
                "a semana encolheu de movimentos ao ganhar dias: %s"
                % distintos_por_dias,
            )

    def test_a_reparticao_e_deterministica(self):
        """Mesmo perfil, mesmo catálogo, mesma ficha — sempre.

        Recalcular não pode embaralhar: `_prescricao_confere` compara o que o
        motor devolve com o que está gravado, e uma divergência de um item faz
        a tela remontar a rotina em laço.
        """
        user, primeiro = perfil(6, sufixo="-det")
        receita = sorted(
            (s.label, s.weekday, i.exercise_id, i.sets)
            for s in primeiro.sessions.all()
            for i in s.exercises.all()
        )

        for _ in range(3):
            outro = services.create_routine(user)
            self.assertEqual(
                sorted((s.label, s.weekday, i.exercise_id, i.sets)
                       for s in outro.sessions.all()
                       for i in s.exercises.all()),
                receita,
            )

    def test_o_repartidor_devolve_a_lista_inteira_quando_nao_repete(self):
        """Controle: letra que ocorre uma vez não pode perder exercício."""
        class Falso:
            def __init__(self, grupo, ident):
                self.exercise = type("E", (), {"muscle_group": grupo})()
                self.ident = ident

        itens = [Falso("chest", i) for i in range(4)]

        self.assertEqual(services.repartir_ocorrencia(itens, 0, 1), itens)


class ORepartidorEmUnidadeTests(TestCase):
    """O repartidor sozinho, com entradas escolhidas para doer.

    POR QUE UNIDADE E NÃO SÓ INTEGRAÇÃO. Três sabotagens da primeira bateria
    passaram VERDES pelos testes de ponta a ponta, e a causa não era o teste
    fraco em todas: duas eram INOFENSIVAS nos modelos reais.

      - repartir a lista inteira em vez de por grupo dá o mesmo resultado em
        `abcd A`, porque lá os quatro peitos vêm antes dos três tríceps e o
        rodízio alterna igual;
      - devolver sem reordenar dá o mesmo resultado, porque agrupar por músculo
        já reproduz a ordem do modelo nesses catálogos;
      - e o ramo do grupo esgotado só existe em `abc B`, com a preferência de
        três grupos e quatro dias ou mais.

    Sabotagem que não muda comportamento não prova nada sobre o teste. Aqui as
    entradas são fabricadas para que cada regra tenha consequência.
    """

    class Item:
        """O mínimo que `repartir_ocorrencia` lê de um item de modelo."""

        def __init__(self, grupo, marca):
            self.exercise = type("E", (), {"muscle_group": grupo})()
            self.marca = marca

        def __repr__(self):
            return self.marca

    def _lista(self, *pares):
        return [self.Item(grupo, marca) for grupo, marca in pares]

    def test_reparte_DENTRO_de_cada_grupo(self):
        """Peito e tríceps INTERCALADOS na ordem do modelo.

        É a entrada que separa "repartir por grupo" de "repartir a lista": com
        os grupos alternados, dividir a lista inteira daria a uma passagem
        todos os peitos e à outra todos os tríceps.
        """
        itens = self._lista(
            ("chest", "peito1"), ("triceps", "tri1"),
            ("chest", "peito2"), ("triceps", "tri2"),
            ("chest", "peito3"), ("triceps", "tri3"),
        )

        primeira = services.repartir_ocorrencia(itens, 0, 2)
        segunda = services.repartir_ocorrencia(itens, 1, 2)

        self.assertEqual([i.marca for i in primeira], ["peito1", "tri1", "peito3", "tri3"])
        self.assertEqual([i.marca for i in segunda], ["peito2", "tri2"])

    def test_grupo_esgotado_CICLA_em_vez_de_sumir(self):
        """Um antebraço para duas passagens: as duas recebem.

        É `abc B`, que tem um antebraço e um trapézio. Sem o ciclo, a segunda
        passagem anuncia dois músculos que não treina.
        """
        itens = self._lista(
            ("back", "costas1"), ("back", "costas2"), ("forearms", "antebraco"),
        )

        primeira = services.repartir_ocorrencia(itens, 0, 2)
        segunda = services.repartir_ocorrencia(itens, 1, 2)

        self.assertIn("antebraco", [i.marca for i in primeira])
        self.assertIn("antebraco", [i.marca for i in segunda])
        self.assertEqual([i.marca for i in primeira], ["costas1", "antebraco"])
        self.assertEqual([i.marca for i in segunda], ["costas2", "antebraco"])

    def test_devolve_na_ORDEM_do_modelo(self):
        """A ordem agrupa por região, e o grau de prioridade sai dela.

        Entrada com os grupos fora de bloco: se o repartidor devolvesse
        agrupado por músculo, a saída viria reordenada e
        `prioridades_da_sessao` daria outro grau ao mesmo exercício.
        """
        itens = self._lista(
            ("quads", "agacho"), ("hamstrings", "stiff"),
            ("quads", "leg"), ("hamstrings", "mesa"),
        )

        saida = services.repartir_ocorrencia(itens, 0, 2)

        self.assertEqual([i.marca for i in saida], ["agacho", "stiff"])

    def test_tres_passagens_repartem_em_tres(self):
        """Sete dias com a preferência de três grupos dão A três vezes."""
        itens = self._lista(*[("chest", "p%d" % i) for i in range(1, 7)])

        fatias = [services.repartir_ocorrencia(itens, i, 3) for i in range(3)]

        self.assertEqual([[i.marca for i in f] for f in fatias],
                         [["p1", "p4"], ["p2", "p5"], ["p3", "p6"]])
        self.assertEqual(
            sorted(i.marca for f in fatias for i in f),
            ["p1", "p2", "p3", "p4", "p5", "p6"],
            "a união das passagens tem de ser o modelo inteiro, sem repetir",
        )

    def test_uma_passagem_devolve_tudo(self):
        """Controle: letra que não repete não pode perder exercício."""
        itens = self._lista(("chest", "a"), ("triceps", "b"))

        self.assertEqual(services.repartir_ocorrencia(itens, 0, 1), itens)


class ORelogioNaoApagaMusculoAnunciadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_todo_grupo_do_modelo_sobrevive_ao_corte(self):
        """A ficha não pode prometer no título o que não entrega.

        Varre as QUATRO faixas de duração e as sete frequências: o corte por
        tempo pode reduzir exercício, nunca zerar um grupo que o modelo lista.
        """
        for duracao in DuracaoTreino.values:
            for dias in range(1, 8):
                with self.subTest(duracao=duracao, dias=dias):
                    _, plano = perfil(dias, duracao=duracao, sufixo="-tempo")
                    modelos = {
                        t.label: t for t in services.templates_for(plano.split)
                    }
                    for sessao in plano.sessions.all():
                        prometidos = {
                            item.exercise.muscle_group
                            for item in modelos[sessao.label].items.all()
                            if item.exercise.is_active
                        }
                        entregues = {
                            item.exercise.muscle_group
                            for item in sessao.exercises.select_related("exercise")
                        }
                        # TODO GRUPO DO MODELO, EM TODA PASSAGEM — menos onde
                        # a aritmética proíbe, e aí a regra é OUTRA.
                        #
                        # A repartição garante a entrada: grupo com opções de
                        # sobra é dividido em rodízio, e grupo com menos
                        # exercícios que passagens é ciclado, então nenhuma
                        # passagem nasce sem ele. A trava do relógio garante a
                        # saída, e é ela que pega as sabotagens.
                        #
                        # O QUE A PRIMEIRA VERSÃO DESTE TESTE ERRAVA: exigia a
                        # invariante em TODA faixa. Medido, "até 30 minutos"
                        # não comporta: `ab A` tem oito exercícios em SETE
                        # grupos, e sete exercícios no PISO de série ainda dão
                        # 42 minutos. Não existe ficha que respeite os dois
                        # contratos ali, e afirmar que existe era o teste
                        # mentindo.
                        #
                        # A regra verdadeira, e é ela que o corte cumpre:
                        # músculo só sai depois de a redução de série se
                        # esgotar. Abaixo, a faixa curta cobra isso; as outras
                        # cobram a invariante inteira.
                        if duracao == DuracaoTreino.RAPIDO:
                            no_piso = [
                                item.sets <= (PISO_COMPOSTO
                                              if item.exercise.is_compound else 2)
                                for item in sessao.exercises.select_related("exercise")
                            ]
                            if prometidos - entregues:
                                self.assertTrue(
                                    all(no_piso),
                                    "%s perdeu %s com série de sobra em %s"
                                    % (sessao.label,
                                       sorted(prometidos - entregues),
                                       [i.sets for i in sessao.exercises.all()]),
                                )
                            continue

                        self.assertEqual(
                            prometidos - entregues, set(),
                            "%s %s prometia %s e entregou %s"
                            % (plano.split, sessao.label,
                               sorted(prometidos), sorted(entregues)),
                        )

    def test_nenhuma_sessao_fica_com_menos_de_dois_exercicios(self):
        """"Corpo inteiro com dois exercícios" era o sintoma de 1 dia."""
        for dias in range(1, 8):
            for duracao in DuracaoTreino.values:
                with self.subTest(dias=dias, duracao=duracao):
                    _, plano = perfil(dias, duracao=duracao, sufixo="-piso")
                    for sessao in plano.sessions.all():
                        self.assertGreaterEqual(sessao.exercises.count(), 2)


class AsFalhasNaoDependemDoCorpoTests(TestCase):
    """A auditoria variou idade, peso e altura em doze cenários e o erro
    apareceu nos doze. A correção não pode depender de nenhum dos três."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_os_extremos_de_corpo_dao_a_mesma_ficha(self):
        receitas = []
        for i, (nascimento, altura, peso) in enumerate((
            (date(2008, 1, 1), 160, Decimal("60")),
            (date(1961, 1, 1), 195, Decimal("120")),
            (date(1999, 7, 8), 185, Decimal("102")),
        )):
            user, plano = perfil(6, sufixo="-corpo%d" % i)
            Profile.objects.filter(user=user).update(
                birth_date=nascimento, height_cm=altura)
            WeightEntry.objects.filter(user=user).update(weight_kg=peso)
            user = User.objects.get(pk=user.pk)
            novo = services.create_routine(user)
            receitas.append(sorted(
                (s.label, item.exercise_id)
                for s in novo.sessions.all() for item in s.exercises.all()))

        self.assertEqual(receitas[0], receitas[1])
        self.assertEqual(receitas[1], receitas[2])


class AsLimitacoesQueSobramSaoDeCONTEUDOTests(TestCase):
    """O que a correção NÃO resolve, separado do que ela resolve.

    A missão pede a separação explícita entre defeito de algoritmo e limitação
    real. Depois da repartição e da trava do relógio, o que sobra é conteúdo:

    `abc B` — a divisão aplicada a quem pede 2 grupos e treina TRÊS dias —
    lista três exercícios de costas, e o catálogo tem quatro. O contrato pede
    quatro no ciclo semanal, e nenhum algoritmo cria o quarto: ele não está no
    modelo.

    Este teste CONGELA a lacuna. No dia em que o modelo ganhar o quarto, ele
    fica vermelho e avisa que o contrato passou a caber em três dias também.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_modelo_de_tres_dias_nao_lista_costas_suficiente(self):
        modelos = {t.label: t for t in services.templates_for("abc")}
        costas = [
            item.exercise.name
            for item in modelos["B"].items.all()
            if item.exercise.muscle_group == MuscleGroup.BACK
        ]

        self.assertEqual(
            len(costas), 3,
            "o modelo `abc B` mudou de tamanho — reveja o contrato de variedade",
        )
        self.assertLess(len(costas), MINIMOS_SEMANAIS[MuscleGroup.BACK])
