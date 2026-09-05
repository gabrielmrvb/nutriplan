# -*- coding: utf-8 -*-
"""A água entra no cartão AGORA por ESTADO, não por relógio.

Antes disto ela era prioridade 4: só aparecia depois de todas as refeições e do
treino — ou seja, quando o dia já tinha acabado. Hidratação é hábito
distribuído, e lembrar dela às 22h é lembrar tarde.

A regra mede o atraso contra o esperado PARA A HORA, dentro da janela do próprio
plano: da primeira refeição à última. Não há horário escrito à mão, e isso é
decisão — quem come às 5h30 e às 19h tem outra janela, e um "7h às 22h" fixo
estaria errado para essa pessoa todos os dias.

De manhã o esperado é baixo e o atraso não alcança o limiar. Beber desliga o
cartão NA HORA — e só na hora: quem continua atrás o vê de novo umas duas horas
depois, porque o esperado cresce com o relógio mais depressa do que 500 ml movem
o real. Num dia de 7h às 20h com meta de 3 L, bebendo 500 toda vez que ele pede,
são cinco aparições. `OCartaoVoltaSeAPessoaContinuaAtrasTests` prende essa
cadência, porque a primeira versão deste arquivo afirmava que ceder DESLIGAVA a
regra, e a medição desmentiu.

E ela não passa na frente do que tem hora marcada: sede não tem hora, refeição e
treino têm.
"""
from datetime import datetime, time

from django.test import SimpleTestCase
from django.utils import timezone

from plans import agora as motor
from plans.models import MealCategory, MealLog, MealSlot, MealStatus
from workouts import services as workout_services
from workouts.models import TrainingSession


class BaseDoAgora(SimpleTestCase):
    def slot(self, pk, nome, hora, log=None):
        s = MealSlot(
            name=nome,
            time=hora,
            target_kcal=400,
            target_protein_g=30,
            target_carb_g=40,
            target_fat_g=15,
            order=pk,
            category=MealCategory.MAIN,
        )
        s.pk = pk
        s.log = log
        return s

    def feito(self):
        return MealLog(status=MealStatus.DONE)

    def instante(self, h, m=0):
        return timezone.make_aware(
            datetime.combine(timezone.localdate(), time(h, m))
        )

    def dia(self, *, hora, bebido, meta=3000, pendentes=False, treino=None,
            prioridade="", convite_pesagem=False):
        """Refeições às 7h, 12h e 20h; as que já passaram, MARCADAS.

        Este é o dia em que a regra tem alguma chance de aparecer: nada
        vencido, próxima refeição no futuro. É de propósito, e o "de propósito"
        é a parte que importa —

        se TUDO estivesse marcado, o ramo 4 (a água que já existia, para quando
        não sobrou mais nada a fazer) devolveria `"agua"` sozinho, e todo teste
        aqui passaria ou falharia sem nunca tocar a regra nova. O que a regra
        nova disputa é o slot do "A SEGUIR" — então tem de haver um "a seguir".
        """
        horarios = [(1, "Café", time(7, 0)), (2, "Almoço", time(12, 0)),
                    (3, "Jantar", time(20, 0))]
        slots = [
            self.slot(
                pk, nome, h,
                log=None if (pendentes or h > time(hora, 0)) else self.feito(),
            )
            for pk, nome, h in horarios
        ]
        return motor.proxima_acao(
            slots=slots,
            treino=treino,
            meta_agua=meta,
            bebido=bebido,
            agora=self.instante(hora),
            prioridade=prioridade,
            convite_pesagem=convite_pesagem,
        )


class AguaSobeQuandoOAtrasoERealTests(BaseDoAgora):
    def test_de_manha_cedo_a_agua_nao_toma_a_tela(self):
        """Às 8h o esperado é baixo: ninguém está atrasado por ainda não ter
        bebido, e um aviso ali seria barulho."""
        self.assertNotEqual(self.dia(hora=8, bebido=0).tipo, "agua")

    def test_ao_meio_dia_com_meio_copo_a_agua_sobe(self):
        acao = self.dia(hora=13, bebido=500)

        self.assertEqual(acao.tipo, "agua")
        self.assertIn("2500", acao.titulo)

    def test_quem_esta_indo_bem_nao_e_incomodado(self):
        """Mesma hora do teste acima, o triplo de água: o atraso cai abaixo do
        limiar e o cartão não aparece."""
        self.assertNotEqual(self.dia(hora=13, bebido=1500).tipo, "agua")

    def test_beber_desliga_o_aviso(self):
        """O salto de 500 para 2.000 aqui é grande DE PROPÓSITO, e por muito
        tempo ele foi o problema: o teste provava que ficar em dia desliga o
        cartão, e alguém leu isso como "beber desliga o cartão". São coisas
        diferentes, e `OCartaoVoltaSeAPessoaContinuaAtrasTests` prende a que
        falta."""
        self.assertEqual(self.dia(hora=15, bebido=500).tipo, "agua")
        self.assertNotEqual(self.dia(hora=15, bebido=2000).tipo, "agua")

    def test_faltando_pouco_nao_vale_tomar_a_tela(self):
        """Faltando 450 ml a pessoa não precisa de um cartão dizendo isso —
        precisa de um copo.

        A meta pequena aqui não é preguiça de escrever números: com meta de
        3 L, `faltam < 500` exige ter bebido mais de 83% e estar 25 pontos
        atrás ao mesmo tempo, o que pediria um esperado ACIMA de 100% — não
        existe. Só uma meta baixa separa esta guarda da outra, e sem separar
        não dá para saber qual das duas está segurando o cartão.
        """
        acao = self.dia(hora=18, bebido=550, meta=1000)

        self.assertNotEqual(acao.tipo, "agua")

    def test_o_controle_positivo_da_guarda_dos_500_ml(self):
        """Mesma hora, mesma meta, 50 ml a menos: agora faltam 500 e o cartão
        sobe. Sem este par, o teste acima passaria mesmo se fosse o LIMIAR DE
        ATRASO que estivesse segurando o cartão — e ele não está."""
        acao = self.dia(hora=18, bebido=500, meta=1000)

        self.assertEqual(acao.tipo, "agua")
        self.assertIn("500", acao.titulo)

    def test_meta_batida_nao_dispara(self):
        self.assertNotEqual(self.dia(hora=18, bebido=3000).tipo, "agua")

    def test_sem_meta_nao_dispara(self):
        self.assertNotEqual(self.dia(hora=18, bebido=0, meta=0).tipo, "agua")


class AguaNaoPassaNaFrenteDoQueTemHoraMarcadaTests(BaseDoAgora):
    def test_refeicao_vencida_ganha_da_agua(self):
        """13h, almoço das 12h ainda não marcado, zero de água: o atraso de
        hidratação é enorme e mesmo assim o almoço vence. Refeição passa; sede
        não."""
        self.assertEqual(self.dia(hora=13, bebido=0, pendentes=True).tipo, "refeicao")

    def test_treino_em_andamento_ganha_da_agua(self):
        """Ninguém entre séries quer ser mandado beber água."""
        sessao = TrainingSession(
            name="Peito", start_time=time(18, 30), weekday=0, label="A",
            duration_min=60,
        )
        estado = workout_services.EstadoDoTreino()
        estado.sessao = sessao
        estado.itens = [object()] * 7
        estado.total_exercicios = 7
        estado.series_feitas = 3
        estado.total_series = 20
        estado.concluido = False

        acao = self.dia(hora=19, bebido=0, treino=estado)

        self.assertEqual(acao.tipo, "treino")


class OAtrasoEMedidoNaJanelaDoPlanoTests(SimpleTestCase):
    """A função pura, sozinha — sem passar pelo cartão."""

    def slots(self, *horas):
        saida = []
        for i, h in enumerate(horas, start=1):
            s = MealSlot(
                name="R%d" % i, time=time(h, 0), target_kcal=400,
                target_protein_g=30, target_carb_g=40, target_fat_g=15,
                order=i, category=MealCategory.MAIN,
            )
            s.pk = i
            saida.append(s)
        return saida

    def atraso(self, hora, bebido, meta=3000, horas=(7, 20)):
        return motor.atraso_de_hidratacao(
            slots=self.slots(*horas),
            meta_agua=meta,
            bebido=bebido,
            agora=timezone.make_aware(
                datetime.combine(timezone.localdate(), time(hora, 0))
            ),
        )

    def test_antes_da_primeira_refeicao_nao_se_espera_nada(self):
        self.assertLessEqual(self.atraso(6, 0), 0)

    def test_no_meio_da_janela_o_esperado_e_proporcional(self):
        """Das 7h às 20h são 13 horas; às 13h passaram 6, pouco menos da
        metade. O número exato é o controle positivo desta função: se ela
        devolvesse sempre zero, este teste cairia."""
        self.assertAlmostEqual(self.atraso(13, 0), 46.15, places=1)

    def test_depois_da_ultima_refeicao_espera_se_a_meta_inteira(self):
        self.assertAlmostEqual(self.atraso(22, 0), 100.0, places=1)

    def test_quem_bebeu_adiantado_tem_atraso_negativo(self):
        """Negativo é informação: garante que a regra nunca dispare para quem
        está à frente."""
        self.assertLess(self.atraso(10, 2900), 0)

    def test_sem_janela_nao_ha_o_que_medir(self):
        """Uma refeição só não define janela, e chutar uma seria pior que não
        responder.

        Este é um contrato de COMPORTAMENTO, e não de linha: `len(horarios) < 2`
        e `fim <= inicio` chegam os dois na mesma resposta para este caso, e
        derrubar qualquer um deles sozinho deixa o teste verde. Foi medido —
        `< 2` virou `< 1` na sabotagem e nada aconteceu.

        Fica escrito para ninguém ler o verde como prova de que a primeira
        linha está protegida. Ela não está sozinha; a resposta está.
        """
        self.assertEqual(self.atraso(13, 0, horas=(7,)), 0.0)

    def test_beber_alem_da_meta_nao_vira_credito(self):
        """`min(bebido/meta, 1)` existe para isto: quem bebeu o dobro não fica
        com 100 pontos de crédito para o dia seguinte da conta."""
        self.assertAlmostEqual(self.atraso(22, 6000), 0.0, places=1)


class OCartaoVoltaSeAPessoaContinuaAtrasTests(BaseDoAgora):
    """A cadência real da regra, presa por teste.

    Nasceu de uma revisão adversarial que derrubou uma frase minha. Eu havia
    escrito, no código e na documentação, que "ceder a ela é o que a desliga" —
    e usei isso como o argumento de que a regra não domina o AGORA. A simulação
    do dia inteiro mostrou outra coisa: beber desliga o cartão NA HORA, sempre,
    mas quem continua atrás o vê de novo umas duas horas depois.

    Cinco lembretes espaçados não são wallpaper, e a regra fica como está. O que
    não podia ficar era a frase. Estes testes existem para que a próxima pessoa
    leia a cadência em vez de deduzi-la de um comentário otimista.
    """

    def test_beber_desliga_o_cartao_no_mesmo_instante(self):
        self.assertEqual(self.dia(hora=15, bebido=1000).tipo, "agua")
        self.assertNotEqual(self.dia(hora=15, bebido=1500).tipo, "agua")

    def test_mas_ele_volta_duas_horas_depois(self):
        """Mesmos 1.500 ml que calaram o cartão às 15h já não bastam às 17h.

        Não é defeito: às 17h faltam três horas de janela para 1.500 ml, e a
        pessoa ESTÁ atrás. É a cadência, e ela precisa estar escrita.
        """
        self.assertNotEqual(self.dia(hora=15, bebido=1500).tipo, "agua")
        self.assertEqual(self.dia(hora=17, bebido=1500).tipo, "agua")

    def test_quem_alcanca_a_meta_nao_ouve_mais_falar(self):
        """O outro extremo, e o controle positivo do teste acima: se o cartão
        voltasse de qualquer jeito com o passar da hora, este ficaria vermelho.
        Ficar em dia desliga a regra de verdade."""
        for hora in (13, 15, 17, 19):
            with self.subTest(hora=hora):
                bebido = int(3000 * (hora - 7) / 13)
                self.assertNotEqual(self.dia(hora=hora, bebido=bebido).tipo, "agua")


class OPilarDeclaradoMOVE_O_LIMIAR_E_NAO_A_ORDEM_Tests(BaseDoAgora):
    """A preferência é MAIS UM SINAL, e o formato dela é essa frase.

    Ela não abre um atalho na ordem de decisão: move um corte dentro de uma
    faixa fechada. Quem escolheu Corrida continua sendo avisado da água — só
    mais tarde. Quem escolheu Hidratação é avisado mais cedo. Ninguém deixa de
    ser avisado, e é isso que separa "personalizar" de "esconder".

    Os números vêm da mesma janela de 7h às 20h com meta de 3 L que o resto
    deste arquivo usa. Às 10h o atraso de quem não bebeu nada é 23,08 pontos:
    acima do chão de 15 e abaixo do padrão de 25. É o instante que separa os
    três limiares, e é por isso que ele aparece nos testes.
    """

    def test_hidratacao_como_pilar_ANTECIPA_o_aviso(self):
        self.assertEqual(
            self.dia(hora=10, bebido=0, prioridade="hidratacao").tipo, "agua"
        )

    def test_sem_pilar_declarado_o_mesmo_instante_fica_calado(self):
        """O par do teste acima, e o que prova influência: mesma hora, mesma
        água, resultado diferente. Sem este, o de cima passaria mesmo se a
        regra ignorasse o pilar e simplesmente disparasse às 10h."""
        self.assertNotEqual(self.dia(hora=10, bebido=0).tipo, "agua")

    def test_outro_pilar_ADIA_o_aviso(self):
        """Às 11h o atraso é 30,77: passa o padrão de 25 e não o teto de 35."""
        self.assertEqual(self.dia(hora=11, bebido=0).tipo, "agua")
        self.assertNotEqual(self.dia(hora=11, bebido=0, prioridade="corrida").tipo, "agua")

    def test_nenhum_pilar_DESLIGA_a_agua(self):
        """O teto existe para isso. Quem escolheu Corrida e não bebe nada
        continua sendo avisado — às 19h o atraso é 92 pontos, e nenhum pilar
        chega perto disso."""
        for prioridade in ("", "dieta", "treino", "corrida", "hidratacao", "progresso"):
            with self.subTest(prioridade=prioridade):
                self.assertEqual(
                    self.dia(hora=19, bebido=0, prioridade=prioridade).tipo, "agua"
                )

    def test_o_limiar_nunca_sai_da_faixa(self):
        """Uma edição futura do tipo "pilar X → 5 pontos" fica vermelha aqui.

        Sem este teste o chão não é protegido por nada: nenhum outro caso deste
        arquivo chega perto de 15, então baixar `ATRASO_MINIMO_PP` passaria
        despercebido — e a regra voltaria a disparar no ruído que ela mesma
        documenta como ruído.
        """
        # Os NÚMEROS, e não as constantes. A primeira versão deste teste
        # importava `ATRASO_MINIMO_PP` e comparava o limiar com ele — ou seja,
        # comparava o valor consigo mesmo. Baixar a constante para 5 passava
        # verde, e a sabotagem provou isso.
        #
        # 15 é o chão porque `plans/agora.py` documenta 13 pontos como ruído:
        # quem bebeu 1 L às 13h de uma meta de 3 L chega lá sem ninguém avisar.
        # Um limiar abaixo disso faz a regra disparar exatamente no caso que
        # ela existe para não incomodar.
        for prioridade in ("", "dieta", "treino", "corrida", "hidratacao", "progresso"):
            with self.subTest(prioridade=prioridade):
                limiar = motor.limiar_de_atraso(prioridade)
                self.assertGreaterEqual(limiar, 15, "o limiar desceu para o ruído")
                self.assertLessEqual(limiar, 35, "o limiar subiu e a regra some")


class NenhumPilarAtropelaUrgenciaTests(BaseDoAgora):
    """O que a preferência NUNCA ultrapassa, varrido nos seis valores.

    Varre em vez de testar um: uma condição escrita à mão erra num dos ramos, e
    o teste de um pilar só não veria. E um pilar futuro entra no laço sozinho.
    """

    TODOS = ("", "dieta", "treino", "corrida", "hidratacao", "progresso")

    def test_refeicao_vencida_ganha_de_qualquer_pilar(self):
        """Refeição tem hora marcada e a hora passa. Sede não passa, e o pilar
        continua verdadeiro amanhã."""
        for prioridade in self.TODOS:
            with self.subTest(prioridade=prioridade):
                acao = self.dia(
                    hora=13, bebido=0, pendentes=True,
                    prioridade=prioridade, convite_pesagem=True,
                )
                self.assertEqual(acao.tipo, "refeicao")

    def test_treino_em_andamento_ganha_de_qualquer_pilar(self):
        """É estado, não agenda: há série anotada hoje. É a única coisa neste
        módulo que o app OBSERVOU acontecer."""
        sessao = TrainingSession(
            name="Peito", start_time=time(18, 30), weekday=0, label="A",
            duration_min=60,
        )
        estado = workout_services.EstadoDoTreino()
        estado.sessao = sessao
        estado.itens = [object()] * 7
        estado.total_exercicios = 7
        estado.series_feitas = 3
        estado.total_series = 20
        estado.concluido = False

        for prioridade in self.TODOS:
            with self.subTest(prioridade=prioridade):
                acao = self.dia(
                    hora=19, bebido=0, treino=estado,
                    prioridade=prioridade, convite_pesagem=True,
                )
                self.assertEqual(acao.tipo, "treino")


class OProgressoSoSOBE_COM_FATO_Tests(BaseDoAgora):
    """O ramo do Progresso existe porque há um fato por trás dele.

    `convidar_a_pesar` já dizia, no mesmo `TodayView`, que a semana está abaixo
    da meta de pesagens e que hoje ainda não tem uma. O pilar muda o LUGAR
    dessa ação, não a existência dela.

    Sem o convite o ramo não existe — e essa é a diferença entre responder à
    preferência de alguém e fabricar tarefa. O módulo já diz, no topo: quando
    não há o que fazer, ele diz isso, não preenche o espaço.
    """

    def test_com_convite_a_pesagem_sobe(self):
        acao = self.dia(hora=15, bebido=3000, prioridade="progresso", convite_pesagem=True)

        self.assertEqual(acao.tipo, "pesagem")
        self.assertEqual(acao.url, "#pesar")

    def test_SEM_convite_o_pilar_progresso_nao_muda_nada(self):
        """Num dia em que a pessoa já se pesou, Progresso não inventa cartão."""
        acao = self.dia(hora=15, bebido=3000, prioridade="progresso", convite_pesagem=False)

        self.assertNotEqual(acao.tipo, "pesagem")

    def test_o_convite_sozinho_nao_basta(self):
        """Controle positivo do ramo: quem não declarou Progresso não recebe o
        cartão de pesagem, mesmo com o convite ligado. Sem isto, o ramo poderia
        estar ignorando o pilar e respondendo só ao convite."""
        for prioridade in ("", "dieta", "treino", "corrida", "hidratacao"):
            with self.subTest(prioridade=prioridade):
                acao = self.dia(
                    hora=15, bebido=3000, prioridade=prioridade, convite_pesagem=True
                )
                self.assertNotEqual(acao.tipo, "pesagem")
