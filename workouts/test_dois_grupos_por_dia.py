"""TREINO — quem pede DOIS grupos por dia recebe A-B-C, e não A-B-C-D.

O RELATO, reproduzido em produção em 10/09/2026 com o perfil de referência
(homem, 27, 185 cm, 102 kg, intermediário, 45-60 min, segunda a sexta):

    preferência gravada  ->  2 grupos por dia
    divisão aplicada     ->  ABCD
    semana entregue      ->  A, B, C, D, A

O quarto dia se chama "Complementares" e é trapézio, antebraço, panturrilha,
glúteo e core. Não são dois grupos principais — são o resto. Quem pediu "peito e
tríceps, costas e bíceps, pernas e ombros" recebia um dia que não é nenhum dos
três, no meio da semana, sem nada explicando.

A CORREÇÃO NÃO É APAGAR OS COMPLEMENTARES. Eles têm casa:

    trapézio e antebraço          ->  dentro do dia de costas (B)
    panturrilha, glúteo e core    ->  dentro do dia de pernas (C)
    posterior de coxa             ->  já era perna, e continua em C

E ELES NÃO APARECEM TODA SESSÃO. `repartir_ocorrencia` divide os itens do
modelo entre as passagens da letra na semana, então B1 leva uns e B2 leva
outros. A objeção de que "integrar os complementares obrigaria sessões de onze
exercícios" está MEDIDA aqui, e o recorte importa: `abc2 B` tem onze itens e
`abc2 C` tem doze, e mesmo assim a maior sessão da semana tem NOVE no tempo
padrão (45 a 60) e CINCO no rápido (até 30). Doze só chega a quem escolheu
"Completo" ou "sem limite rígido" — ali a pessoa pediu a ficha inteira, e
entregá-la em 88 minutos, dentro do teto de 90, não é inchaço.

DESDE 15/09/2026 A REPARTIÇÃO É EM OPÇÕES, NÃO EM PASSAGENS
(`workouts/opcoes.py`): B1 e B2 são o MESMO treino com as mesmas duas
versões, e é entre as versões que os complementares se distribuem — a opção 1
de B leva o encolhimento e a rosca de punho, a opção 2 leva a remada alta e a
rosca inversa. A sessão gravada guarda as duas, então `exercises.count()` é a
soma de dois treinos: todo tamanho aqui é medido por OPÇÃO (`da_opcao`), e a
variedade da semana é a UNIÃO das opções, que é o que a pessoa alcança
alternando.
"""
from collections import defaultdict

from django.core.management import call_command
from django.test import TestCase

from accounts.models import (
    TETO_POR_DURACAO, DuracaoTreino, SplitPreference, TrainingDay,
)

from . import services
from .models import MuscleGroup, Split
from .test_reparticao_semanal import perfil, sessoes_por_letra

#: A semana que cada frequência tem de produzir. É o pedido, letra por letra.
SEQUENCIAS = {
    3: ["A", "B", "C"],
    4: ["A", "B", "C", "A"],
    5: ["A", "B", "C", "A", "B"],
    6: ["A", "B", "C", "A", "B", "C"],
    7: ["A", "B", "C", "A", "B", "C", "A"],
}

#: Os grupos que entram junto sem estar no nome do dia.
COMPLEMENTARES = {
    MuscleGroup.TRAPS,
    MuscleGroup.FOREARMS,
    MuscleGroup.CALVES,
    MuscleGroup.CORE,
}


class ASemanaDeDoisGruposEABCTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_sequencia_da_semana_e_a_pedida(self):
        """A-B-C, A-B-C-A, A-B-C-A-B, A-B-C-A-B-C, A-B-C-A-B-C-A."""
        for dias, esperada in SEQUENCIAS.items():
            with self.subTest(dias=dias):
                _, plano = perfil(dias, sufixo="-seq")

                letras = [
                    sessao.label
                    for sessao in plano.sessions.all().order_by("weekday")
                ]

                self.assertEqual(plano.split, Split.ABC2)
                self.assertEqual(letras, esperada)

    def test_nenhuma_semana_tem_treino_D(self):
        """A trava do relato, dita como trava.

        Uma reintrodução do ABCD nesta preferência passaria despercebida pelo
        teste da sequência se alguém mudasse `SEQUENCIAS` junto. Aqui a
        proibição é literal e não depende daquela tabela.
        """
        for dias in range(1, 8):
            with self.subTest(dias=dias):
                _, plano = perfil(dias, sufixo="-semd")

                letras = {s.label for s in plano.sessions.all()}
                nomes = {s.name for s in plano.sessions.all()}

                self.assertNotIn("D", letras)
                self.assertNotIn("Complementares", nomes)
                self.assertNotEqual(plano.split, Split.ABCD)

    def test_os_titulos_sao_os_tres_nomes_simples(self):
        """"Peito e tríceps", "Costas e bíceps", "Pernas e ombros".

        Com três dias nenhuma letra repete e o tempo padrão comporta os grupos
        anunciados, então nenhum título é reescrito: os três nomes que a pessoa
        vê são os três nomes curados do catálogo.
        """
        _, plano = perfil(3, sufixo="-titulos")

        nomes = [
            sessao.name for sessao in plano.sessions.all().order_by("weekday")
        ]

        self.assertEqual(
            nomes, ["Peito e tríceps", "Costas e bíceps", "Pernas e ombros"]
        )


class OsComplementaresTemCasaTests(TestCase):
    """Onde cada complementar mora, e a prova de que ele não sumiu."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)
        cls.modelos = {t.label: t for t in services.templates_for(Split.ABC2)}

    def _grupos_do_modelo(self, letra):
        return {
            item.exercise.muscle_group
            for item in self.modelos[letra].items.all()
        }

    def test_trapezio_e_antebraco_moram_no_dia_de_costas(self):
        grupos = self._grupos_do_modelo("B")

        self.assertIn(MuscleGroup.TRAPS, grupos)
        self.assertIn(MuscleGroup.FOREARMS, grupos)

    def test_panturrilha_gluteo_e_core_moram_no_dia_de_pernas(self):
        """Glúteo não é um grupo próprio no catálogo — é `hamstrings`.

        `Elevação pélvica` é o exercício de glúteo, e ele está classificado em
        "posterior de coxa e glúteo". Por isso o glúteo entra pelo mesmo grupo
        que o posterior, e o posterior já era perna: os dois ficam em C sem
        precisar de dia próprio.
        """
        grupos = self._grupos_do_modelo("C")
        nomes = {item.exercise.name for item in self.modelos["C"].items.all()}

        self.assertIn(MuscleGroup.CALVES, grupos)
        self.assertIn(MuscleGroup.CORE, grupos)
        self.assertIn(MuscleGroup.HAMSTRINGS, grupos)
        self.assertIn("Elevação pélvica", nomes)

    def test_complementar_nao_entra_no_titulo(self):
        """O nome do dia promete dois grupos, e são esses dois que ele tem.

        É a distinção que faz o corte por tempo ceder o encolhimento antes da
        rosca, e a que faz `titulo_honesto` não reescrever o nome quando a
        panturrilha não coube.
        """
        for letra in "ABC":
            with self.subTest(letra=letra):
                anunciados = set(self.modelos[letra].main_groups)

                self.assertEqual(anunciados & COMPLEMENTARES, set())
                self.assertLessEqual(
                    len(anunciados), 3,
                    "%s anuncia %s" % (letra, sorted(anunciados)),
                )

    def test_o_dia_A_nao_tem_complementar_nenhum(self):
        """Peito e tríceps é o dia sem sobra, e isso é decisão.

        O catálogo tem quatro peitos e três tríceps: sete itens, e a sessão de
        45 a 60 minutos comporta exatamente sete. Enfiar abdômen ali custaria
        um exercício de peito ou estouraria o tempo — e o abdômen tem casa em C.
        """
        self.assertEqual(self._grupos_do_modelo("A") & COMPLEMENTARES, set())


class OsComplementaresSeDistribuemTests(TestCase):
    """O falso dilema das "sessões de onze exercícios", medido.

    O modelo `abc2 B` tem onze itens e o `abc2 C` tem doze. Se cada passagem
    recebesse o modelo inteiro, a objeção estaria certa. Ela não está: a
    repartição em OPÇÕES divide os itens, e o que uma versão da letra não
    leva a outra leva — a pessoa alterna.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _complementares_por_opcao(self, plano, letra):
        """[{complementares da opção 1}, {da opção 2}] da letra."""
        sessao = sessoes_por_letra(plano)[letra]
        return [
            {
                item.exercise.name
                for item in sessao.da_opcao(opcao)
                if item.exercise.muscle_group in COMPLEMENTARES
            }
            for opcao in sessao.opcoes
        ]

    def test_as_duas_opcoes_de_B_levam_complementares_DIFERENTES(self):
        """Cinco dias: a letra B cai duas vezes, e o trapézio não é o mesmo.

        Era "B1 e B2": desde 15/09/2026 as duas ocorrências carregam as mesmas
        linhas, e quem se reveza são as OPÇÕES da letra — quem faz B na terça
        e na sexta alterna a versão, e não repete o encolhimento.
        """
        _, plano = perfil(5, sufixo="-b1b2")

        opcoes = self._complementares_por_opcao(plano, "B")

        self.assertEqual(len(opcoes), 2, "B saiu com uma opção só")
        primeira, segunda = opcoes
        self.assertTrue(primeira, "a opção 1 de B ficou sem complementar nenhum")
        self.assertTrue(segunda, "a opção 2 de B ficou sem complementar nenhum")
        self.assertEqual(
            primeira & segunda, set(),
            "as opções de B repetiram %s" % sorted(primeira & segunda),
        )

    def test_as_duas_opcoes_de_C_levam_complementares_DIFERENTES(self):
        """Seis dias: a letra C cai duas vezes, e a panturrilha se reveza.

        Era "C1 e C2"; a leitura por opções é a mesma da letra B acima. Seis
        dias continua sendo o cenário, porque é onde C repete: se a letra
        sair com UMA opção, quem treina C duas vezes na semana faz a mesma
        panturrilha nas duas — que é o que este teste existe para proibir.
        """
        _, plano = perfil(6, sufixo="-c1c2")

        opcoes = self._complementares_por_opcao(plano, "C")

        self.assertEqual(len(opcoes), 2, "C saiu com uma opção só em seis dias")
        primeira, segunda = opcoes
        self.assertTrue(primeira, "a opção 1 de C ficou sem complementar nenhum")
        self.assertTrue(segunda, "a opção 2 de C ficou sem complementar nenhum")
        self.assertEqual(
            primeira & segunda, set(),
            "as opções de C repetiram %s" % sorted(primeira & segunda),
        )

    def test_no_tempo_informado_a_sessao_nao_incha(self):
        """A objeção, refutada onde ela foi feita — e com o recorte certo.

        O modelo `abc2 C` tem DOZE itens. A objeção dizia que integrar os
        complementares obrigaria toda sessão a ter onze. Medido nas cinco
        frequências que usam esta divisão, com as faixas que têm teto:

            rápido (até 30)   maior sessão da semana: 5 exercícios
            padrão (45 a 60)  maior sessão da semana: 9 exercícios

        Nove, não onze — e sem perder o contrato: o dia de puxar entrega quatro
        costas, três bíceps, trapézio e antebraço em 60 minutos exatos, com as
        roscas em duas séries.

        DUAS VERSÕES ANTERIORES DESTE TESTE, e as duas mediram outra coisa. A
        primeira varria as quatro faixas e ficou vermelha em "completo" com
        doze — estava certa: ali a pessoa PEDIU a ficha inteira. A segunda
        cravou o teto em oito, que era o número da ordem de corte que
        sacrificava bíceps; com a ordem certa a sessão legitimamente chega a
        nove.

        O QUE IMPORTA NÃO É A CONTAGEM, É O TETO — e é ele que a segunda
        asserção cobra. Uma sessão de nove exercícios dentro dos 60 minutos
        combinados não é inchaço; é o orçamento sendo usado.

        POR OPÇÃO, desde 15/09/2026 — e os números foram REMEDIDOS. A sessão
        gravada guarda as duas versões da letra, e `exercises.count()` somaria
        os dois treinos. Medido opção a opção, nas cinco frequências:

            rápido (até 30)   maior opção da semana: 4 exercícios
            padrão (45 a 60)  maior opção da semana: 7 exercícios

        Sete e quatro, e não nove e cinco: cada opção é metade do modelo com a
        série subida ao piso, e não o modelo inteiro aparado. A catraca desce
        junto — um motor que voltasse a pôr nove numa versão reaparece aqui.
        """
        maximos = {DuracaoTreino.RAPIDO: 4, DuracaoTreino.PADRAO: 7}
        for duracao, teto_de_itens in maximos.items():
            for dias in range(3, 8):
                with self.subTest(duracao=duracao, dias=dias):
                    _, plano = perfil(dias, duracao=duracao, sufixo="-onze")
                    sessoes = list(plano.sessions.prefetch_related("exercises__exercise"))
                    maior = max(
                        len(sessao.da_opcao(opcao))
                        for sessao in sessoes
                        for opcao in sessao.opcoes
                    )

                    self.assertLessEqual(
                        maior, teto_de_itens,
                        "uma opção de %d dias saiu com %d exercícios"
                        % (dias, maior),
                    )
                    for sessao in sessoes:
                        for opcao in sessao.opcoes:
                            self.assertLessEqual(
                                sessao.minutos_da_opcao(opcao),
                                TETO_POR_DURACAO[duracao],
                                "%s opção %d passou do tempo combinado"
                                % (sessao.label, opcao),
                            )

    def test_quando_a_letra_repete_nenhuma_passagem_leva_o_modelo_inteiro(self):
        """A repartição, isolada do relógio.

        Vale com "sem limite rígido", que é a faixa mais folgada: se cada
        OPÇÃO da letra continua menor que o modelo, quem a encurtou foi a
        repartição em versões, não o tempo. (Desde 15/09/2026 "livre" recebe a
        sessão completa de `opcoes.TETO_COMPLETO_MIN` minutos em vez de
        nenhum teto — e o modelo inteiro de `abc2 C` são 88 minutos, então o
        relógio também o cortaria. O que a asserção pega é a opção que saiu
        do tamanho do modelo, que é o defeito da letra copiada inteira.)
        """
        for dias in (4, 5, 6, 7):
            with self.subTest(dias=dias):
                _, plano = perfil(dias, duracao=DuracaoTreino.LIVRE, sufixo="-parte")
                modelos = {t.label: t for t in services.templates_for(plano.split)}
                vezes = defaultdict(int)
                for sessao in plano.sessions.all():
                    vezes[sessao.label] += 1

                for sessao in plano.sessions.prefetch_related("exercises__exercise"):
                    if vezes[sessao.label] < 2:
                        continue
                    for opcao in sessao.opcoes:
                        self.assertLess(
                            len(sessao.da_opcao(opcao)),
                            modelos[sessao.label].items.count(),
                            "%s opção %d levou o modelo inteiro mesmo repetindo"
                            % (sessao.label, opcao),
                        )

    def test_a_ficha_cheia_so_vai_para_quem_pediu_tempo_para_ela(self):
        """Doze exercícios existem, e chegam inteiros a quem pediu tempo.

        Com "Completo — 60 a 90" e três dias, a letra C não repete e os doze
        itens do modelo chegam à pessoa. ATÉ 15/09/2026 chegavam numa sessão
        só — 88 minutos, dentro do teto de 90. Hoje chegam como DUAS versões
        equivalentes de ~50 minutos, e a união delas é o modelo inteiro: a
        pessoa que alterna faz os doze na quinzena. É a mesma doutrina de
        sempre — tempo é TETO, não cota —, e o que este teste proíbe é o
        contrário: uma versão da ficha cheia estourando o tempo combinado.
        """
        _, plano = perfil(3, duracao=DuracaoTreino.COMPLETO, sufixo="-cheia")
        modelo = {t.label: t for t in services.templates_for(plano.split)}["C"]
        sessao = sessoes_por_letra(plano)["C"]

        oferecidos = {
            item.exercise_id for opcao in sessao.opcoes for item in sessao.da_opcao(opcao)
        }
        self.assertEqual(
            oferecidos,
            {item.exercise_id for item in modelo.items.all() if item.exercise.is_active},
            "a letra C não oferece o modelo inteiro entre as opções",
        )
        self.assertEqual(len(oferecidos), 12)
        for s in plano.sessions.prefetch_related("exercises__exercise"):
            for opcao in s.opcoes:
                self.assertLessEqual(s.minutos_da_opcao(opcao), 90, "%s opção %d" % (s.label, opcao))

    def test_a_semana_de_seis_dias_treina_TODOS_os_complementares(self):
        """Com as duas passagens de B e de C, nada fica de fora."""
        _, plano = perfil(6, sufixo="-todos")

        presentes = {
            item.exercise.muscle_group
            for sessao in plano.sessions.all()
            for item in sessao.exercises.select_related("exercise")
        }

        self.assertEqual(COMPLEMENTARES - presentes, set())


class APreferenciaSobreviveAAdaptacaoTests(TestCase):
    """Frequência incompatível ADAPTA a divisão; ela não apaga a escolha."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_com_menos_de_tres_dias_a_escolha_continua_gravada(self):
        for dias, esperada in ((1, Split.FULL), (2, Split.AB)):
            with self.subTest(dias=dias):
                user, plano = perfil(dias, sufixo="-adapta")

                explicacao = services.divisao_explicada(user)

                self.assertEqual(plano.split, esperada)
                self.assertEqual(
                    user.profile.split_preference, SplitPreference.DOIS,
                    "a adaptação apagou a preferência",
                )
                self.assertTrue(explicacao["cedeu"])
                self.assertEqual(explicacao["pedida"], Split.ABC2)
                self.assertEqual(explicacao["dias_necessarios"], 3)
                self.assertIn("2 grupos por dia", explicacao["motivo"])
                self.assertIn(str(dias), explicacao["motivo"])

    def test_ao_voltar_para_tres_dias_a_divisao_se_restaura_sozinha(self):
        """Sem intervenção, sem botão, sem perder a escolha.

        É `sync_active_routine` quem faz: `routine_is_current` compara a divisão
        gravada com a que a preferência de hoje produz, e remonta quando
        divergem. O caminho é o mesmo de quem muda o dia de treino.
        """
        user, plano = perfil(2, sufixo="-volta")
        self.assertEqual(plano.split, Split.AB)

        TrainingDay.objects.create(
            user=user, weekday=4, start_time=plano.sessions.first().start_time,
            duration_min=60,
        )
        user = type(user).objects.get(pk=user.pk)

        nova, mudou = services.sync_active_routine(user)

        self.assertTrue(mudou)
        self.assertEqual(nova.split, Split.ABC2)
        self.assertFalse(services.divisao_explicada(user)["cedeu"])
        self.assertEqual(user.profile.split_preference, SplitPreference.DOIS)


class AVariedadeSemanalDeDoisGruposTests(TestCase):
    """O contrato de variedade, na divisão nova, no perfil da auditoria."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_de_cinco_a_sete_dias_a_semana_cumpre_quatro_quatro_tres_tres(self):
        """Lido sobre a UNIÃO das opções: a letra tem até duas versões e a
        pessoa faz uma por dia, então o que a semana OFERECE — que é do que o
        contrato 4/4/3/3 sempre falou — é o que se alcança alternando."""
        for dias in (5, 6, 7):
            with self.subTest(dias=dias):
                _, plano = perfil(dias, sufixo="-4433")
                distintos = defaultdict(set)
                for sessao in plano.sessions.all():
                    for item in sessao.exercises.select_related("exercise"):
                        distintos[item.exercise.muscle_group].add(
                            item.exercise.name
                        )

                # SETE DIAS É A EXCEÇÃO MEDIDA (15/09/2026): a letra A cai três
                # vezes, o teto de 20 séries efetivas por semana deixa ~6,7 de
                # peito por sessão, e o crucifixo — o quarto peito, compartilhado
                # pelas três opções equivalentes — não cabe em nenhuma delas.
                # Três exercícios distintos de peito é o que a semana oferece; o
                # contrato 4/4/3/3 vale de 3 a 6 dias (CLAUDE.md).
                self.assertGreaterEqual(len(distintos[MuscleGroup.CHEST]), 3 if dias == 7 else 4)
                self.assertGreaterEqual(len(distintos[MuscleGroup.BACK]), 4)
                self.assertGreaterEqual(len(distintos[MuscleGroup.TRICEPS]), 3)
                self.assertGreaterEqual(len(distintos[MuscleGroup.BICEPS]), 3)

    def test_a_variedade_nao_piora_quando_a_pessoa_treina_mais(self):
        """O sintoma mais absurdo do relato: mais dias, menos exercícios.

        Antes da repartição, sete dias entregavam DOIS peitos distintos e três
        dias entregavam três. Aqui a régua é monotônica por grupo — treinar
        mais nunca reduz a variedade de nenhum músculo.

        Variedade é a UNIÃO das opções da letra (ver o teste acima).
        """
        por_dias = {}
        for dias in range(3, 8):
            _, plano = perfil(dias, sufixo="-mono")
            distintos = defaultdict(set)
            for sessao in plano.sessions.all():
                for item in sessao.exercises.select_related("exercise"):
                    distintos[item.exercise.muscle_group].add(item.exercise.name)
            por_dias[dias] = distintos

        for dias in range(4, 8):
            for grupo in MuscleGroup.values:
                if dias == 7 and grupo == MuscleGroup.CHEST:
                    # A exceção medida de sete dias (ver o teste acima): o
                    # quarto peito não cabe no teto com a letra três vezes.
                    continue
                with self.subTest(dias=dias, grupo=grupo):
                    self.assertGreaterEqual(
                        len(por_dias[dias][grupo]),
                        len(por_dias[dias - 1][grupo]),
                        "%s caiu de %d para %d dias"
                        % (grupo, dias - 1, dias),
                    )
