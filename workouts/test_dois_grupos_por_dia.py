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
"""
from collections import defaultdict

from django.core.management import call_command
from django.test import TestCase

from accounts.models import (
    TETO_POR_DURACAO, DuracaoTreino, SplitPreference, TrainingDay,
)

from . import services
from .models import MuscleGroup, Split
from .test_reparticao_semanal import perfil

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
    repartição por ocorrência divide os itens, e o que uma passagem não leva a
    outra leva.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _complementares_por_passagem(self, plano, letra):
        saida = []
        for sessao in plano.sessions.all().order_by("weekday"):
            if sessao.label != letra:
                continue
            saida.append({
                item.exercise.name
                for item in sessao.exercises.select_related("exercise")
                if item.exercise.muscle_group in COMPLEMENTARES
            })
        return saida

    def test_B1_e_B2_levam_complementares_DIFERENTES(self):
        """Cinco dias: a letra B cai duas vezes, e o trapézio não é o mesmo."""
        _, plano = perfil(5, sufixo="-b1b2")

        primeira, segunda = self._complementares_por_passagem(plano, "B")

        self.assertTrue(primeira, "B1 ficou sem complementar nenhum")
        self.assertTrue(segunda, "B2 ficou sem complementar nenhum")
        self.assertEqual(
            primeira & segunda, set(),
            "B1 e B2 repetiram %s" % sorted(primeira & segunda),
        )

    def test_C1_e_C2_levam_complementares_DIFERENTES(self):
        """Seis dias: a letra C cai duas vezes, e a panturrilha se reveza."""
        _, plano = perfil(6, sufixo="-c1c2")

        primeira, segunda = self._complementares_por_passagem(plano, "C")

        self.assertTrue(primeira, "C1 ficou sem complementar nenhum")
        self.assertTrue(segunda, "C2 ficou sem complementar nenhum")
        self.assertEqual(
            primeira & segunda, set(),
            "C1 e C2 repetiram %s" % sorted(primeira & segunda),
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
        """
        maximos = {DuracaoTreino.RAPIDO: 5, DuracaoTreino.PADRAO: 9}
        for duracao, teto_de_itens in maximos.items():
            for dias in range(3, 8):
                with self.subTest(duracao=duracao, dias=dias):
                    _, plano = perfil(dias, duracao=duracao, sufixo="-onze")
                    maior = max(
                        sessao.exercises.count() for sessao in plano.sessions.all()
                    )

                    self.assertLessEqual(
                        maior, teto_de_itens,
                        "uma sessão de %d dias saiu com %d exercícios"
                        % (dias, maior),
                    )
                    for sessao in plano.sessions.all():
                        self.assertLessEqual(
                            sessao.estimated_minutes,
                            TETO_POR_DURACAO[duracao],
                            "%s passou do tempo combinado" % sessao.label,
                        )

    def test_quando_a_letra_repete_nenhuma_passagem_leva_o_modelo_inteiro(self):
        """A repartição, isolada do relógio.

        Vale com "sem limite rígido", que é onde o corte por tempo não existe:
        se a passagem continua menor que o modelo, quem a encurtou foi a
        divisão entre as ocorrências.
        """
        for dias in (4, 5, 6, 7):
            with self.subTest(dias=dias):
                _, plano = perfil(dias, duracao=DuracaoTreino.LIVRE, sufixo="-parte")
                modelos = {t.label: t for t in services.templates_for(plano.split)}
                vezes = defaultdict(int)
                for sessao in plano.sessions.all():
                    vezes[sessao.label] += 1

                for sessao in plano.sessions.all():
                    if vezes[sessao.label] < 2:
                        continue
                    self.assertLess(
                        sessao.exercises.count(),
                        modelos[sessao.label].items.count(),
                        "%s levou o modelo inteiro mesmo repetindo"
                        % sessao.label,
                    )

    def test_a_ficha_cheia_so_vai_para_quem_pediu_tempo_para_ela(self):
        """Doze exercícios existem, e só chegam a quem cabe.

        Com "Completo — 60 a 90" e três dias, a letra C não repete e leva os
        doze itens: 88 minutos estimados, dentro do teto de 90. É a mesma
        doutrina de sempre — tempo é TETO, não cota —, e o que este teste
        proíbe é o contrário: a ficha cheia estourando o tempo combinado.
        """
        _, plano = perfil(3, duracao=DuracaoTreino.COMPLETO, sufixo="-cheia")

        maior = max(s.exercises.count() for s in plano.sessions.all())

        self.assertEqual(maior, 12)
        for sessao in plano.sessions.all():
            self.assertLessEqual(sessao.estimated_minutes, 90, sessao.label)

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
        for dias in (5, 6, 7):
            with self.subTest(dias=dias):
                _, plano = perfil(dias, sufixo="-4433")
                distintos = defaultdict(set)
                for sessao in plano.sessions.all():
                    for item in sessao.exercises.select_related("exercise"):
                        distintos[item.exercise.muscle_group].add(
                            item.exercise.name
                        )

                self.assertGreaterEqual(len(distintos[MuscleGroup.CHEST]), 4)
                self.assertGreaterEqual(len(distintos[MuscleGroup.BACK]), 4)
                self.assertGreaterEqual(len(distintos[MuscleGroup.TRICEPS]), 3)
                self.assertGreaterEqual(len(distintos[MuscleGroup.BICEPS]), 3)

    def test_a_variedade_nao_piora_quando_a_pessoa_treina_mais(self):
        """O sintoma mais absurdo do relato: mais dias, menos exercícios.

        Antes da repartição, sete dias entregavam DOIS peitos distintos e três
        dias entregavam três. Aqui a régua é monotônica por grupo — treinar
        mais nunca reduz a variedade de nenhum músculo.
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
                with self.subTest(dias=dias, grupo=grupo):
                    self.assertGreaterEqual(
                        len(por_dias[dias][grupo]),
                        len(por_dias[dias - 1][grupo]),
                        "%s caiu de %d para %d dias"
                        % (grupo, dias - 1, dias),
                    )
