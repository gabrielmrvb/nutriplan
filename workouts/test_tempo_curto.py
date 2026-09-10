"""TREINO — o que "até 30 minutos" significa, dito de um jeito só e testável.

A CONTRADIÇÃO QUE ISTO RESOLVE. O relato da auditoria trazia, para o mesmo
perfil e a mesma faixa de tempo, duas queixas que puxam para lados opostos:

    "a ficha de 30 minutos virou agachamento e supino, e continuou se
     chamando corpo inteiro"
    "o supino reto caiu para duas séries num perfil normal"

A primeira pede que o corte reduza SÉRIE em vez de apagar exercício. A segunda
pede que ele apague exercício em vez de reduzir série. As duas estão certas —
sobre casos diferentes —, e enquanto a regra não estava escrita cada correção
desfazia a anterior.

A REGRA, EM CINCO CAMADAS, NESTA ORDEM (`escolher_para_o_tempo`):

    1. sai o EXCEDENTE do COMPLEMENTAR — o que a sessão traz além do que o
       título promete, e só enquanto o grupo tiver mais de um: a SEGUNDA
       panturrilha, o SEGUNDO abdominal, o segundo antebraço;
    2. sai o exercício EXCEDENTE do grupo ANUNCIADO mais cheio, do degrau de
       prioridade mais baixo — isolador antes de composto acessório, acessório
       antes de principal —, e nunca o último do grupo;
    3. quando todo grupo está com um exercício só, REDUZ SÉRIE, do mais alto
       para baixo, até o piso: três num composto, duas num isolado;
    4. sai o ÚLTIMO exercício de um grupo COMPLEMENTAR, e aí o grupo deixa a
       sessão;
    5. só com tudo isso esgotado é que um exercício ANUNCIADO sai. É a
       aritmética falando: `full A` tem nove grupos com um exercício cada, e os
       nove no piso ainda dão mais de 30 minutos. E aí o TÍTULO acompanha —
       `titulo_honesto` para de nomear o grupo que caiu.

O QUE CADA QUEIXA VIRA. "Supino com duas séries num perfil normal" é a camada 3
acontecendo onde a camada 2 ainda tinha o que ceder: com a ordem certa, o
perfil de 45 a 60 minutos não chega à camada 3. "Corpo inteiro com dois
exercícios" é a camada 5 sem a reescrita do título.

A CAMADA 4 JÁ FOI A CAMADA 1, e a diferença é grande. Com o complementar
cedendo INTEIRO antes de qualquer excedente anunciado, panturrilha e abdômen
ficavam órfãos da SEMANA em três, quatro e cinco dias no perfil de dois grupos
por dia — a letra C cai uma vez só nessas frequências, e o que saía dela não
voltava. Medido depois da correção: de 45 minutos para cima, nenhum grupo
complementar fica órfão em nenhuma frequência de 1 a 7 dias.
"""
from itertools import combinations

from django.core.management import call_command
from django.test import TestCase

from accounts.models import DuracaoTreino, SplitPreference

from . import services
from .models import MuscleGroup, Split, TrainingSession
from .services import ACESSORIO, ISOLADOR, PISO_COMPOSTO, PRINCIPAL
from .test_reparticao_semanal import perfil

#: Todas as divisões que o catálogo publica, com quantas letras cada uma tem.
DIVISOES = {
    Split.FULL: 1,
    Split.AB: 2,
    Split.ABC: 3,
    Split.ABC2: 3,
    Split.ABCD: 4,
    Split.ABCDE: 5,
}


class AOrdemDaConcessaoTests(TestCase):
    """As cinco camadas, uma a uma, com entradas fabricadas para doer.

    UNIDADE E NÃO INTEGRAÇÃO, de propósito. Nos modelos reais vários passos
    dariam o mesmo resultado por coincidência — o mesmo problema que fez três
    sabotagens da repartição passarem verdes. Aqui cada entrada é escolhida
    para que trocar a ordem mude a saída.

    As tuplas são `(grupo, séries, descanso, grau)`, na ordem da ficha, que é o
    contrato de `escolher_para_o_tempo`.
    """

    def test_1_o_EXCEDENTE_do_complementar_sai_antes_do_anunciado(self):
        """A segunda panturrilha antes da terceira rosca — e só ela.

        É o caso medido em "Costas e bíceps": quatro costas, três bíceps, dois
        trapézios e dois antebraços. Pelo rodízio puro sairiam duas roscas,
        porque bíceps era o grupo mais cheio, e a ficha ficava com um bíceps só
        com bíceps no título.

        O QUE ESTE TESTE NÃO AFIRMA, e uma versão anterior dele afirmava: que o
        complementar sai INTEIRO nesta camada. Ele afirmava, e por isso passou
        verde enquanto o motor abandonava panturrilha e abdômen da semana
        inteira. A camada 1 tira o EXCEDENTE; a casa do grupo só cai na camada
        4, depois de a redução de série se esgotar.

        O teto de 48 minutos é escolhido para forçar EXATAMENTE duas remoções:
        a ficha cheia custa 57,3 e sem os dois excedentes custa 47,3.
        """
        itens = [
            ("back", 4, 80, PRINCIPAL),
            ("back", 3, 80, ACESSORIO),
            ("biceps", 3, 60, ISOLADOR),
            ("biceps", 3, 60, ISOLADOR),
            ("biceps", 3, 60, ISOLADOR),
            ("traps", 3, 60, ISOLADOR),
            ("traps", 3, 60, ISOLADOR),
            ("forearms", 3, 60, ISOLADOR),
            ("forearms", 3, 60, ISOLADOR),
        ]

        ficam = services.escolher_para_o_tempo(
            itens, 48, principais=["back", "biceps"]
        )

        grupos = [itens[i][0] for i, _ in ficam]
        self.assertEqual(grupos.count("biceps"), 3, "cedeu bíceps antes do excedente")
        self.assertEqual(grupos.count("back"), 2)
        self.assertEqual(grupos.count("traps"), 1, "trapézio não cedeu o excedente")
        self.assertEqual(grupos.count("forearms"), 1)

    def test_2_esgotado_o_complementar_cede_o_grupo_mais_CHEIO(self):
        """"Mais cheio" conta a sessão, não o degrau que está cedendo.

        Quadríceps com três exercícios, sendo dois compostos intocáveis, tem UM
        isolador elegível; ombro com dois tem um. Contando elegíveis os dois
        empatam e o desempate pela ordem da ficha tira o ombro — que foi o
        defeito real de "Pernas e ombros" com um ombro só.

        QUARENTA MINUTOS, E O NÚMERO IMPORTA. A primeira versão deste teste
        usava trinta e afirmava só `assertIn("shoulders", ...)`. A sabotagem
        que devolve a contagem por degrau passou VERDE nele, por dois motivos
        somados: em trinta minutos as duas versões devolvem a MESMA ficha —
        dois exercícios —, e "está presente" não distingue ombro com um de
        ombro com dois. Em quarenta a diferença aparece inteira:

            contando a sessão:   quads 2, ombro 2
            contando o degrau:   quads 3, ombro 1
        """
        itens = [
            ("quads", 4, 80, PRINCIPAL),
            ("quads", 4, 80, ACESSORIO),
            ("quads", 3, 60, ISOLADOR),
            ("shoulders", 3, 80, PRINCIPAL),
            ("shoulders", 3, 60, ISOLADOR),
        ]

        ficam = services.escolher_para_o_tempo(
            itens, 40, principais=["quads", "shoulders"]
        )

        grupos = [itens[i][0] for i, _ in ficam]
        self.assertEqual(grupos.count("shoulders"), 2, grupos)
        self.assertEqual(grupos.count("quads"), 2, grupos)

    def test_3_com_um_exercicio_por_grupo_REDUZ_SERIE(self):
        """Cinco grupos, um exercício cada: ninguém pode sair sem apagar músculo.

        É o corpo inteiro. A saída é baixar série — e o teste prova que ela
        acontece ANTES de qualquer remoção, porque os cinco continuam de pé.
        """
        itens = [
            ("quads", 4, 80, PRINCIPAL),
            ("chest", 4, 80, PRINCIPAL),
            ("back", 4, 80, PRINCIPAL),
            ("shoulders", 4, 80, PRINCIPAL),
            ("hamstrings", 4, 80, PRINCIPAL),
        ]

        ficam = services.escolher_para_o_tempo(
            itens, 45,
            principais=["quads", "chest", "back", "shoulders", "hamstrings"],
        )

        self.assertEqual(len(ficam), len(itens), "apagou músculo com série de sobra")
        self.assertTrue(any(series < 4 for _, series in ficam))
        for _, series in ficam:
            self.assertGreaterEqual(series, PISO_COMPOSTO)

    def test_4_so_no_fim_um_grupo_anunciado_cai(self):
        """Nove grupos no piso de série ainda não cabem em 30 minutos.

        Aqui o passo 4 tem de acontecer — e o teste guarda o preço: quem sobra
        está no PISO, prova de que a redução foi tentada até o fim antes de
        alguém sair.
        """
        grupos = ["quads", "chest", "back", "hamstrings", "shoulders",
                  "biceps", "triceps", "core", "calves"]
        itens = [(g, 4, 80, PRINCIPAL) for g in grupos]

        ficam = services.escolher_para_o_tempo(itens, 30, principais=grupos)

        self.assertLess(len(ficam), len(itens))
        for _, series in ficam:
            self.assertEqual(series, PISO_COMPOSTO)

    def test_4b_o_ultimo_complementar_so_sai_depois_da_REDUCAO(self):
        """A camada que faltava, e que custou a panturrilha da semana.

        Cinco grupos com um exercício cada — três anunciados, dois
        complementares — num teto que não comporta a dose cheia (44,2 min) mas
        comporta os cinco no piso de série (35,2 min).

        Com a ordem antiga, panturrilha e abdômen saíam primeiro e a sessão
        terminava com três exercícios em dose cheia. Com a ordem certa, os
        cinco grupos ficam e o que cede é a série. É a diferença entre a pessoa
        treinar panturrilha nesta semana e não treinar.
        """
        itens = [
            ("quads", 4, 80, PRINCIPAL),
            ("hamstrings", 4, 80, PRINCIPAL),
            ("shoulders", 3, 80, PRINCIPAL),
            ("calves", 4, 60, ISOLADOR),
            ("core", 3, 60, ISOLADOR),
        ]

        ficam = services.escolher_para_o_tempo(
            itens, 40, principais=["quads", "hamstrings", "shoulders"]
        )

        grupos = [itens[i][0] for i, _ in ficam]
        self.assertIn("calves", grupos, "a panturrilha saiu com série de sobra")
        self.assertIn("core", grupos, "o abdômen saiu com série de sobra")
        self.assertEqual(len(ficam), len(itens))
        self.assertTrue(any(series < itens[i][1] for i, series in ficam))

    def test_o_teto_e_duro_nas_cinco_camadas(self):
        """Nenhuma das saídas acima pode passar do tempo informado.

        Uma versão anterior do corte aceitava estourar o teto para preservar
        músculo, e sessenta testes ficaram vermelhos porque o teto é contrato:
        a tela promete "até 30" desde que `DuracaoTreino` virou faixa.
        """
        casos = [
            ([("back", 4, 80, PRINCIPAL), ("biceps", 3, 60, ISOLADOR),
              ("traps", 3, 60, ISOLADOR)], ["back", "biceps"]),
            ([(g, 4, 80, PRINCIPAL) for g in
              ("quads", "chest", "back", "shoulders")],
             ["quads", "chest", "back", "shoulders"]),
        ]
        for itens, principais in casos:
            for minutos in (15, 30, 45, 60):
                with self.subTest(minutos=minutos, itens=len(itens)):
                    ficam = services.escolher_para_o_tempo(
                        itens, minutos, principais=principais
                    )
                    segundos = services._segundos_da_sessao([
                        (series, itens[i][2], itens[i][3] >= ACESSORIO)
                        for i, series in ficam
                    ])

                    self.assertLessEqual(segundos / 60, minutos)


class OTempoCurtoNaoMenteTests(TestCase):
    """As invariantes de tela, varridas nas seis divisões e nas sete semanas."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _semanas(self, sufixo):
        """Uma semana por preferência e frequência, sempre em "até 30 min"."""
        for preferencia in SplitPreference.values:
            for dias in range(1, 8):
                _, plano = perfil(
                    dias, preferencia=preferencia,
                    duracao=DuracaoTreino.RAPIDO, sufixo=sufixo,
                )
                yield preferencia, dias, plano

    def test_nenhuma_sessao_passa_de_trinta_minutos(self):
        for preferencia, dias, plano in self._semanas("-teto"):
            for sessao in plano.sessions.all():
                with self.subTest(preferencia=preferencia, dias=dias,
                                  letra=sessao.label):
                    self.assertLessEqual(
                        sessao.estimated_minutes, 30,
                        "%s %s saiu com %d min"
                        % (plano.split, sessao.label, sessao.estimated_minutes),
                    )

    def test_o_titulo_nunca_diz_corpo_inteiro_sem_ser(self):
        """"Corpo inteiro" com três exercícios era o pior sintoma do relato.

        A régua não é a contagem: é a cobertura. Uma sessão só pode se chamar
        corpo inteiro se entregar TODOS os grupos que o modelo do corpo inteiro
        anuncia — empurrar, puxar e perna inclusive.
        """
        modelo = {t.label: t for t in services.templates_for(Split.FULL)}["A"]
        for preferencia, dias, plano in self._semanas("-inteiro"):
            for sessao in plano.sessions.all():
                if sessao.name != modelo.name:
                    continue
                with self.subTest(preferencia=preferencia, dias=dias):
                    entregues = {
                        item.exercise.muscle_group
                        for item in sessao.exercises.select_related("exercise")
                    }
                    self.assertEqual(
                        set(modelo.main_groups) - entregues, set(),
                        "%r com %s" % (sessao.name, sorted(entregues)),
                    )

    def test_toda_sessao_curta_avisa_que_foi_apertada(self):
        """Silêncio faria a pessoa comparar a ficha dela com a de outra pessoa
        na mesma divisão e concluir que falta exercício."""
        for preferencia, dias, plano in self._semanas("-aviso"):
            with self.subTest(preferencia=preferencia, dias=dias):
                self.assertIn("tempo", plano.notes)


class OPerfilNormalNaoSofreReducaoDeEmergenciaTests(TestCase):
    """45 a 60 minutos é tempo de sobra, e o supino tem de mostrar isso.

    A queixa era literal — "o supino reto caiu para duas séries num perfil
    normal" —, e a causa era a ordem: o corte reduzia série antes de gastar os
    exercícios excedentes. Com a ordem certa, o perfil de referência não chega
    ao passo 3 em nenhuma divisão que tenha supino.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_supino_reto_mantem_quatro_series_e_a_faixa_do_catalogo(self):
        for preferencia in SplitPreference.values:
            for dias in range(3, 8):
                with self.subTest(preferencia=preferencia, dias=dias):
                    _, plano = perfil(
                        dias, preferencia=preferencia,
                        duracao=DuracaoTreino.PADRAO, sufixo="-supino",
                    )
                    supinos = [
                        item
                        for sessao in plano.sessions.all()
                        for item in sessao.exercises.select_related("exercise")
                        if item.exercise.name == "Supino reto com barra"
                    ]

                    self.assertTrue(supinos, "o supino sumiu da semana")
                    for item in supinos:
                        self.assertEqual(item.sets, 4)
                        self.assertGreaterEqual(item.rep_min, 6)
                        self.assertLessEqual(item.rep_max, 12)

    def test_nenhum_principal_de_peito_ou_perna_vira_aquecimento(self):
        """Composto abaixo de três séries é aquecimento, e o piso guarda isso.

        Vale nas quatro faixas: mesmo em "até 30 minutos" a redução para no
        piso — abaixo dele o corte prefere remover, que é o passo 4.
        """
        for duracao in DuracaoTreino.values:
            for dias in range(1, 8):
                with self.subTest(duracao=duracao, dias=dias):
                    _, plano = perfil(dias, duracao=duracao, sufixo="-piso-comp")
                    for sessao in plano.sessions.all():
                        for item in sessao.exercises.select_related("exercise"):
                            if not item.exercise.is_compound:
                                continue
                            self.assertGreaterEqual(
                                item.sets, PISO_COMPOSTO,
                                "%s com %d séries"
                                % (item.exercise.name, item.sets),
                            )


class NenhumComplementarFicaSemDestinoTests(TestCase):
    """Complementar pode faltar numa SESSÃO; não pode sumir da SEMANA calado.

    O QUE ESTA CLASSE CORRIGE, e é uma conclusão minha que estava errada. Eu
    havia afirmado que panturrilha e abdômen "só aparecem a partir de seis
    dias" no perfil de dois grupos por dia, e chamado isso de limitação
    aritmética. Não era: era a ordem do corte. A primeira versão derrubava o
    grupo complementar INTEIRO na primeira camada, antes de tocar em qualquer
    excedente anunciado — e como a letra C cai uma vez só em três, quatro e
    cinco dias, o que saía dela não voltava em lugar nenhum.

    Medido depois da correção, varrendo três preferências × sete frequências ×
    quatro faixas de duração: **de 45 minutos para cima, ZERO grupo
    complementar fica órfão**, em qualquer frequência. Antes eram quatro
    órfãos em três dias e dois em cinco.

    O que sobra é "até 30 minutos", e ali a conta é outra — ver
    `test_no_tempo_curto_o_que_nao_coube_e_DITO`.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _complementares(self, plano):
        """Os grupos que os modelos DESTA ficha trazem sem anunciar."""
        declarados, entregues = set(), set()
        modelos = {t.label: t for t in services.templates_for(plano.split)}
        for sessao in plano.sessions.all():
            modelo = modelos[sessao.label]
            anunciados = set(modelo.main_groups)
            for item in modelo.items.all():
                if item.exercise.is_active:
                    if item.exercise.muscle_group not in anunciados:
                        declarados.add(item.exercise.muscle_group)
            for item in sessao.exercises.select_related("exercise"):
                entregues.add(item.exercise.muscle_group)
        return declarados, declarados - entregues

    def test_de_45_minutos_para_cima_nenhum_complementar_fica_orfao(self):
        """A régua forte, e ela vale para 1 a 7 dias nas três preferências.

        "Padrão", "Completo" e "sem limite rígido" são as três faixas em que o
        contrato não abre exceção: todo grupo que o modelo traz aparece pelo
        menos uma vez na semana.
        """
        # CONTROLE POSITIVO. `abcd` é a divisão em que o dia D se chama
        # "Complementares" e ANUNCIA trapézio, antebraço, panturrilha e core —
        # lá não existe grupo complementar nenhum, e a varredura passaria por
        # ele sem medir nada. O acumulador abaixo garante que a varredura viu
        # complementar de verdade em algum cenário: sem ele, esvaziar
        # `main_groups` no catálogo inteiro deixaria este teste verde.
        vistos = set()
        for duracao in (DuracaoTreino.PADRAO, DuracaoTreino.COMPLETO,
                        DuracaoTreino.LIVRE):
            for preferencia in SplitPreference.values:
                for dias in range(1, 8):
                    with self.subTest(duracao=duracao, preferencia=preferencia,
                                      dias=dias):
                        _, plano = perfil(
                            dias, preferencia=preferencia, duracao=duracao,
                            sufixo="-orfao",
                        )
                        declarados, orfaos = self._complementares(plano)
                        vistos |= declarados

                        self.assertEqual(
                            orfaos, set(),
                            "%s com %d dias abandonou %s"
                            % (plano.split, dias, sorted(orfaos)),
                        )

        self.assertEqual(
            {MuscleGroup.TRAPS, MuscleGroup.FOREARMS,
             MuscleGroup.CALVES, MuscleGroup.CORE} - vistos,
            set(),
            "a varredura não chegou a medir todos os complementares: %s"
            % sorted(vistos),
        )

    def test_no_tempo_curto_o_que_nao_coube_e_DITO(self):
        """Em "até 30 minutos" pode faltar — desde que a ficha diga qual.

        A ARITMÉTICA, no caso que sobra. `abc2 C` anuncia quadríceps, posterior
        e ombro, e traz panturrilha e abdômen como complementares. Os três
        compostos principais no PISO de série custam 28,2 minutos; o
        complementar mais barato do catálogo custa mais 3,6, e a sessão iria a
        31,8 contra um teto de 30.

        Cabe cinco grupos em 20,7 minutos se a ficha for cinco isoladores —
        cadeira extensora, mesa flexora, elevação lateral, panturrilha sentado
        e prancha. Isso não é um dia de perna: é o oposto do que o contrato
        manda, que é justamente NÃO derrubar o exercício principal para
        encaixar o relógio. Então a escolha é consciente, e o preço dela é
        dizer o que ficou fora.
        """
        for preferencia in SplitPreference.values:
            for dias in range(1, 8):
                with self.subTest(preferencia=preferencia, dias=dias):
                    _, plano = perfil(
                        dias, preferencia=preferencia,
                        duracao=DuracaoTreino.RAPIDO, sufixo="-curto-orfao",
                    )
                    _, orfaos = self._complementares(plano)
                    if not orfaos:
                        continue

                    # A FRASE DA SEMANA, e não qualquer frase que cite o
                    # músculo. A sabotagem que desliga o ramo do órfão passou
                    # VERDE quando este teste só procurava o nome do grupo: o
                    # ramo seguinte — "ficou para outra sessão da semana" —
                    # nomeia os mesmos músculos, e a pessoa lia que a
                    # panturrilha voltaria noutro dia quando ela não volta em
                    # dia nenhum. Duas mensagens diferentes para dois fatos
                    # diferentes, e o teste tem de saber qual leu.
                    self.assertIn("em nenhuma sessão desta semana", plano.notes)
                    for grupo in orfaos:
                        self.assertIn(
                            services.NOME_CURTO_DO_GRUPO[grupo],
                            plano.notes.lower(),
                            "%s sumiu da semana e a ficha não disse: %r"
                            % (grupo, plano.notes),
                        )

    def test_toda_divisao_de_tres_letras_ou_mais_da_casa_aos_QUATRO(self):
        """Trapézio, antebraço, panturrilha e abdômen têm destino em cada uma.

        É a régua estrutural, e ela é o par da régua de comportamento: mesmo
        que o relógio nunca corte nada, um complementar sem casa em NENHUM
        modelo da divisão nunca seria treinado. `full` e `ab` ficam de fora de
        propósito — uma sessão semanal não comporta os onze grupos, e fingir
        que comporta seria a mentira que este arquivo existe para impedir.
        """
        complementares = {
            MuscleGroup.TRAPS, MuscleGroup.FOREARMS,
            MuscleGroup.CALVES, MuscleGroup.CORE,
        }
        for split, letras in DIVISOES.items():
            if letras < 3:
                continue
            with self.subTest(split=split):
                grupos = {
                    item.exercise.muscle_group
                    for modelo in services.templates_for(split)
                    for item in modelo.items.all()
                }

                self.assertEqual(
                    complementares - grupos, set(),
                    "%s não tem casa para %s"
                    % (split, sorted(complementares - grupos)),
                )


class ATabelaDeDivisoesEstaCompletaTests(TestCase):
    """Toda divisão publicada declara os grupos que anuncia.

    Sem `main_groups` o corte volta ao comportamento antigo em silêncio — não
    quebra nada, só para de proteger o título. Uma divisão nova sem a lista
    passaria despercebida, e é isso que este teste impede.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_nenhum_titulo_gerado_estoura_a_coluna(self):
        """`name` tem 60 caracteres e `focus` tem 120 — e o título é MONTADO.

        Enquanto o nome vinha do catálogo, caber era responsabilidade de quem
        escrevia o catálogo. `titulo_honesto` monta a partir dos grupos que
        sobreviveram, e uma lista de nomes cresce: medido, a pior combinação
        possível dos ONZE grupos daria 94 caracteres. O PostgreSQL não trunca
        `varchar` — ele recusa a linha —, então isso não seria um título feio,
        seria a montagem da ficha estourando.

        No catálogo de hoje a pior combinação real dá 51 e 88, com folga de
        nove e trinta e dois. A folga é pequena o bastante para uma divisão
        nova gastá-la sem ninguém perceber, e é por isso que este teste varre
        TODOS os subconjuntos em vez de conferir só o caso que acontece.
        """
        limite_nome = TrainingSession._meta.get_field("name").max_length
        limite_foco = TrainingSession._meta.get_field("focus").max_length
        for split in DIVISOES:
            for modelo in services.templates_for(split):
                grupos = []
                for item in modelo.items.all():
                    if item.exercise.muscle_group not in grupos:
                        grupos.append(item.exercise.muscle_group)
                with self.subTest(split=split, letra=modelo.label):
                    for quantos in range(1, len(modelo.main_groups) + 1):
                        for combo in combinations(modelo.main_groups, quantos):
                            nome = services.titulo_honesto(
                                modelo.name, modelo.main_groups, list(combo)
                            )
                            self.assertLessEqual(
                                len(nome), limite_nome, repr(nome)
                            )
                    for quantos in range(1, len(grupos) + 1):
                        for combo in combinations(grupos, quantos):
                            foco = services.foco_honesto(list(combo))
                            self.assertLessEqual(
                                len(foco), limite_foco, repr(foco)
                            )

    def test_o_titulo_ENCURTA_quando_a_lista_nao_cabe(self):
        """O caminho que o catálogo de hoje nunca exercita — e por isso este
        teste fabrica a entrada.

        A sabotagem que faz `_frase_que_cabe` ignorar o limite passou VERDE na
        varredura do catálogo real, e estava certa em passar: a pior combinação
        real dá 51 contra os 60 da coluna, então não há o que estourar. Uma
        quebra que não muda comportamento não prova nada sobre o teste.

        Aqui os ONZE grupos entram de uma vez, que é a pior combinação
        possível — 94 caracteres sem encurtar. O que se cobra é o contrato do
        encurtamento: cabe, diz quantos ficaram de fora, e não corta palavra
        pela metade.
        """
        todos = list(MuscleGroup.values)
        limite = TrainingSession._meta.get_field("name").max_length

        nome = services.titulo_honesto("Corpo inteiro", todos + ["ausente"], todos)

        self.assertLessEqual(len(nome), limite, nome)
        self.assertIn("e mais", nome)
        self.assertNotIn(" e e ", nome)
        # Nenhuma palavra cortada: tudo que sobrou é nome inteiro de grupo.
        nomeados = nome.lower().split(" e mais ")[0].split(", ")
        conhecidos = set(services.NOME_CURTO_DO_GRUPO.values()) | {"pernas"}
        for palavra in nomeados:
            self.assertIn(palavra, conhecidos, nome)

    def test_toda_letra_de_toda_divisao_declara_o_que_promete(self):
        for split, letras in DIVISOES.items():
            modelos = services.templates_for(split)
            with self.subTest(split=split):
                self.assertEqual(len(modelos), letras)
            for modelo in modelos:
                with self.subTest(split=split, letra=modelo.label):
                    self.assertTrue(
                        modelo.main_groups,
                        "%s %s não declara `main_groups`" % (split, modelo.label),
                    )
                    for grupo in modelo.main_groups:
                        self.assertIn(grupo, MuscleGroup.values)
                    presentes = {
                        item.exercise.muscle_group for item in modelo.items.all()
                    }
                    self.assertEqual(
                        set(modelo.main_groups) - presentes, set(),
                        "%s %s anuncia grupo que não tem exercício"
                        % (split, modelo.label),
                    )
