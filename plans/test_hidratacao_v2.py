# -*- coding: utf-8 -*-
"""Desfazer UM gole de água, sem perder o dia inteiro.

O desfazer que existia era zerar: quem tocasse `+750` por engano depois de dois
litros escolhia entre um número errado e começar o dia do zero. Escolher entre
duas perdas não é desfazer.

`GoleDeAgua` é aditivo — `HydrationLog` continua sendo a fonte da verdade do
total do dia, porque a ofensiva, o histórico e a tela de hoje leem dele. A
tabela nova só registra a COMPOSIÇÃO, e só daqui para frente.

O que estes testes protegem, na ordem em que doem se quebrarem: ninguém desfaz o
gole de outra pessoa; desfazer tira o último e só ele; o total nunca fica
negativo; e o reenvio da fila offline não cria gole duplicado.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SyncedOperation, WeightEntry
from plans.models import GoleDeAgua, HydrationLog, MealLog, MealStatus
from plans.tests import create_complete_user


class Base(TestCase):
    def setUp(self):
        self.pessoa = create_complete_user("agua.dona@exemplo.com")
        self.outra = create_complete_user("agua.outra@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()

    def beber(self, ml, **extra):
        corpo = {"ml": ml}
        corpo.update(extra)
        return self.client.post(reverse("plans:log_hydration"), corpo)

    def desfazer(self):
        return self.client.post(
            reverse("plans:log_hydration"), {"acao": "desfazer"}
        )

    def total(self, quem=None):
        registro = HydrationLog.objects.filter(
            user=quem or self.pessoa, date=self.hoje
        ).first()
        return registro.ml if registro else 0


class RegistrarCriaOGoleTests(Base):
    def test_beber_registra_o_gole_e_soma_no_total(self):
        self.beber(500)

        self.assertEqual(self.total(), 500)
        gole = GoleDeAgua.objects.get(user=self.pessoa)
        self.assertEqual(gole.ml, 500)
        self.assertEqual(gole.dia, self.hoje)

    def test_tres_goles_viram_tres_linhas_e_uma_soma(self):
        """O total é UM por dia; os goles são três. Confundir os dois é o que
        faz o desfazer apagar o dia."""
        for ml in (250, 500, 750):
            self.beber(ml)

        self.assertEqual(self.total(), 1500)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 3)

    def test_quantidade_invalida_nao_cria_gole(self):
        """A view já recusava o valor. O que este teste protege é a linha órfã:
        recusar e registrar mesmo assim deixaria um gole que nunca somou."""
        resposta = self.beber(333)

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.total(), 0)
        self.assertFalse(GoleDeAgua.objects.exists())

    def test_zerar_nao_cria_gole(self):
        """Zerar é o oposto de beber. Se ele criasse um gole de 0 ml, o
        desfazer seguinte tiraria zero e pareceria quebrado."""
        self.beber(500)
        self.beber(0)

        self.assertEqual(self.total(), 0)
        self.assertEqual(GoleDeAgua.objects.filter(ml=0).count(), 0)


class DesfazerTiraOUltimoESoEleTests(Base):
    def test_desfazer_remove_o_ultimo_gole_e_desconta(self):
        self.beber(250)
        self.beber(750)

        self.desfazer()

        self.assertEqual(self.total(), 250)
        restantes = list(GoleDeAgua.objects.filter(user=self.pessoa))
        self.assertEqual(len(restantes), 1)
        self.assertEqual(restantes[0].ml, 250)

    def test_desfazer_pega_o_ULTIMO_e_nao_o_primeiro(self):
        """A asserção é sobre QUAL gole sobrou, não sobre a contagem.

        Com `250` e depois `750`, tirar o primeiro também deixaria um gole e um
        total diferente de zero — e um teste que só contasse linhas passaria
        com o comportamento errado.
        """
        self.beber(250)
        self.beber(750)

        self.desfazer()

        self.assertEqual(self.total(), 250, "desfez o gole errado")

    def test_desfazer_duas_vezes_volta_ao_zero(self):
        self.beber(250)
        self.beber(500)

        self.desfazer()
        self.desfazer()

        self.assertEqual(self.total(), 0)
        self.assertFalse(GoleDeAgua.objects.filter(user=self.pessoa).exists())

    def test_desfazer_sem_nada_para_desfazer_nao_muda_o_total(self):
        """Dia anterior à tabela de goles cai aqui, e é o caso normal para quem
        já usava o app: o total existe e a composição não."""
        HydrationLog.objects.create(user=self.pessoa, date=self.hoje, ml=2000)

        resposta = self.desfazer()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.total(), 2000, "desfez um gole que não existia")

    def test_o_total_nunca_fica_negativo(self):
        """O teto de 10 L faz o gole pedido poder ser maior que o aplicado.
        Descontar o pedido cheio não pode levar a linha abaixo de zero."""
        self.beber(750)
        HydrationLog.objects.filter(user=self.pessoa, date=self.hoje).update(ml=100)

        self.desfazer()

        self.assertEqual(self.total(), 0)


class NinguemDesfazOGoleDeOutraPessoaTests(Base):
    def test_desfazer_nao_alcanca_o_gole_alheio(self):
        """A pergunta que mais importa nesta tabela."""
        self.client.force_login(self.outra)
        self.beber(750)
        self.assertEqual(self.total(self.outra), 750)

        self.client.force_login(self.pessoa)
        self.beber(250)
        self.desfazer()

        self.assertEqual(self.total(self.outra), 750, "desfez água de outra conta")
        self.assertEqual(
            GoleDeAgua.objects.filter(user=self.outra).count(),
            1,
            "apagou o gole de outra conta",
        )

    def test_sem_gole_proprio_o_desfazer_nao_pega_o_de_outro(self):
        """Sem o filtro por dono, `.first()` devolveria o gole mais recente do
        BANCO — e o dia de outra pessoa encolheria."""
        self.client.force_login(self.outra)
        self.beber(500)

        self.client.force_login(self.pessoa)
        self.desfazer()

        self.assertEqual(self.total(self.outra), 500)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.outra).count(), 1)


class OGoleSegueODiaLocalTests(Base):
    def test_gole_criado_sem_dia_cai_no_dia_LOCAL(self):
        """A versão anterior deste teste comparava `gole.dia` com
        `registro.date` — e os dois saem da MESMA variável da view. Era
        tautológico: afirmava que uma variável é igual a si mesma, e a
        sabotagem que apagava o `default` do model passou verde.

        Este aqui cria o gole SEM passar o dia, que é o caminho de qualquer
        código futuro que não repita `timezone.localdate()` à mão. Se o default
        sumir ou virar `date.today()` do servidor, o dia diverge do que a tela
        mostra perto da meia-noite e o desfazer não acha o gole.
        """
        gole = GoleDeAgua.objects.create(user=self.pessoa, ml=250)

        self.assertEqual(gole.dia, timezone.localdate())

    def test_a_view_grava_o_gole_no_dia_que_a_tela_mostra(self):
        """Não tautológico: `self.hoje` é calculado no `setUp`, fora da view."""
        self.beber(500)

        self.assertEqual(GoleDeAgua.objects.get(user=self.pessoa).dia, self.hoje)

    def test_gole_de_ontem_nao_e_desfeito_hoje(self):
        ontem = self.hoje - timedelta(days=1)
        GoleDeAgua.objects.create(user=self.pessoa, dia=ontem, ml=500)
        HydrationLog.objects.create(user=self.pessoa, date=ontem, ml=500)

        self.desfazer()

        self.assertEqual(
            HydrationLog.objects.get(user=self.pessoa, date=ontem).ml,
            500,
            "desfazer alcançou o dia de ontem",
        )


class OReenvioDaFilaNaoDuplicaOGoleTests(Base):
    def test_mesmo_op_id_nao_cria_dois_goles(self):
        """A fila offline reenvia em rajada quando a rede volta. Água SOMA, e
        sem a trava o reenvio somaria de novo — e agora criaria um gole a mais,
        que o desfazer seguinte tiraria achando que era outro toque."""
        self.beber(500, op_id="op-agua-1")
        self.beber(500, op_id="op-agua-1")

        self.assertEqual(self.total(), 500)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 1)

    def test_op_ids_diferentes_criam_goles_diferentes(self):
        """Controle positivo do teste acima: sem ele, uma trava que recusasse
        TUDO passaria como se estivesse deduplicando."""
        self.beber(500, op_id="op-agua-1")
        self.beber(500, op_id="op-agua-2")

        self.assertEqual(self.total(), 1000)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 2)
        self.assertEqual(SyncedOperation.objects.filter(user=self.pessoa).count(), 2)


class TotalEGolesNaoDivergenTests(Base):
    def test_a_soma_dos_goles_bate_com_o_total_do_dia(self):
        """Num dia que nasceu depois da tabela, os dois têm de concordar.

        Não vale para dia anterior — lá o total existe e a composição não, e
        isso está declarado no model em vez de corrigido com backfill.
        """
        for ml in (250, 250, 500, 750):
            self.beber(ml)
        self.desfazer()

        soma = sum(
            g.ml for g in GoleDeAgua.objects.filter(user=self.pessoa, dia=self.hoje)
        )

        self.assertEqual(soma, self.total())
        self.assertEqual(soma, 1000)


class OErroDoDesfazerVaiParaOndeAMensagemAparece(Base):
    """Mensagem que a pessoa não vê é mensagem que não existe.

    A `.flash` é renderizada no topo da página. O sucesso do registro volta
    para `#hidratacao`, e ali o próprio número mudando é a confirmação — mas o
    ERRO não tem número para mudar: quem tenta desfazer sem ter o que desfazer
    precisa da frase, e a frase está a 2.300px dali.

    É a convenção que o B2 já tinha fixado para esta tela, e que a primeira
    versão deste desfazer violou.
    """

    def test_erro_de_desfazer_volta_ao_topo(self):
        resposta = self.desfazer()

        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn("#hidratacao", resposta["Location"])

    def test_sucesso_do_desfazer_volta_para_a_ancora(self):
        """Controle positivo do teste acima: se os dois fossem para o mesmo
        lugar, o primeiro passaria sem provar distinção nenhuma."""
        self.beber(250)

        resposta = self.desfazer()

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("#hidratacao", resposta["Location"])


class AQuantidadeLivreTests(Base):
    """Digitar o valor deixou de ser proibido — mas dentro de limites.

    A regra antiga aceitava SÓ 250, 500 e 750, e o comentário dizia por quê:
    "aceitar qualquer múltiplo de dez seria aceitar um valor que nenhuma tela
    produz". A tela de hidratação passou a produzir, e o motivo caiu com ela.

    O que estes testes seguram é a faixa: abaixo de 50 ml não é um gole, é um
    toque errado; acima de 2 L num registro só é quase sempre dedo escorregando
    — e o teto diário de 10 L não pega esse caso, porque 5.000 cabe folgado
    embaixo dele.
    """

    def test_a_garrafa_de_um_litro_entra(self):
        self.beber(1000)

        self.assertEqual(self.total(), 1000)
        self.assertEqual(GoleDeAgua.objects.get(user=self.pessoa).ml, 1000)

    def test_o_copo_de_200_do_trabalho_entra(self):
        self.beber(200)

        self.assertEqual(self.total(), 200)

    def test_abaixo_do_minimo_e_recusado(self):
        self.beber(40)

        self.assertEqual(self.total(), 0)
        self.assertFalse(GoleDeAgua.objects.exists())

    def test_acima_do_maximo_e_recusado(self):
        """Cinco litros num toque só é erro de digitação, e o teto diário de
        10 L nunca veria isso: 5.000 passa longe dele."""
        self.beber(5000)

        self.assertEqual(self.total(), 0)
        self.assertFalse(GoleDeAgua.objects.exists())

    def test_valor_fora_do_passo_de_dez_e_recusado(self):
        """255 não é uma quantidade que alguém mediu."""
        self.beber(255)

        self.assertEqual(self.total(), 0)

    def test_as_bordas_da_faixa_entram(self):
        """Controle positivo dos dois testes de recusa: se a faixa estivesse
        deslocada, os "recusa" passariam e ninguém saberia que 50 e 2000 —
        os valores que a tela oferece como limite — também estavam fora."""
        self.beber(50)
        self.beber(2000)

        self.assertEqual(self.total(), 2050)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 2)


class OVoltarDependeDeOndeOToqueVeioTests(Base):
    """Somar da tela de hidratação tem de voltar para a tela de hidratação.

    Sem isso, registrar um copo lá jogaria a pessoa no Hoje — quatro mil pixels
    acima do que ela estava lendo. E o campo por onde isso chega é uma LISTA
    FECHADA de nomes de tela, nunca a URL do pedido: `?next=` livre é
    redirecionamento aberto, e esta view aceita POST de qualquer sessão.
    """

    def _destino(self, resposta):
        return resposta["Location"]

    def test_do_hoje_volta_para_a_ancora_do_hoje(self):
        resposta = self.beber(500)

        self.assertIn("#hidratacao", self._destino(resposta))

    def test_da_tela_de_hidratacao_volta_para_ela(self):
        resposta = self.beber(500, de="hidratacao")

        self.assertEqual(self._destino(resposta), reverse("plans:hydration"))

    def test_o_erro_tambem_volta_para_a_tela_de_onde_veio(self):
        """Na tela de hidratação a mensagem cabe na primeira dobra, então o
        erro não precisa ir para o topo do Hoje — precisa ir para onde a pessoa
        está."""
        resposta = self.beber(41, de="hidratacao")

        self.assertEqual(self._destino(resposta), reverse("plans:hydration"))

    def test_url_estranha_no_campo_de_volta_e_ignorada(self):
        """A pergunta de segurança desta view: um POST forjado com
        `de=https://exemplo.invalido` não pode virar um redirect para fora."""
        resposta = self.beber(500, de="https://exemplo.invalido/roubo")

        destino = self._destino(resposta)
        self.assertNotIn("exemplo.invalido", destino)
        self.assertIn("#hidratacao", destino)

    def test_nome_de_tela_inexistente_e_ignorado(self):
        resposta = self.beber(500, de="plans:history")

        self.assertIn("#hidratacao", self._destino(resposta))


class ATelaDeHidratacaoTests(Base):
    def abrir(self):
        return self.client.get(reverse("plans:hydration"))

    def test_a_tela_abre_e_mostra_o_dia(self):
        self.beber(750)

        resposta = self.abrir()

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Hidratação")
        self.assertContains(resposta, "750")

    def test_sem_registro_a_tela_diz_isso_em_vez_de_mostrar_lista_vazia(self):
        resposta = self.abrir()

        self.assertContains(resposta, "empty-state")

    def test_a_lista_mostra_o_gole_de_hoje(self):
        self.beber(250)

        resposta = self.abrir()

        self.assertContains(resposta, "class=\"gole\"")

    def test_a_tela_nao_mostra_o_gole_de_outra_pessoa(self):
        """A mesma pergunta do desfazer, agora na leitura."""
        self.client.force_login(self.outra)
        self.beber(750)

        self.client.force_login(self.pessoa)
        resposta = self.abrir()

        self.assertNotContains(resposta, "class=\"gole\"")

    def test_quem_nao_entrou_nao_ve_a_tela(self):
        self.client.logout()

        resposta = self.abrir()

        self.assertEqual(resposta.status_code, 302)

    def test_a_meta_da_tela_e_a_MESMA_do_hoje(self):
        """Duas telas do mesmo app não podem mostrar duas metas.

        A tela nova chama `weight_trend.hidratacao_ml` em vez de copiar a
        conta; este teste é o que segura isso quando alguém "otimizar"
        guardando o número numa constante local.
        """
        do_hoje = self.client.get(reverse("plans:today")).context["hidratacao_ml"]
        da_tela = self.abrir().context["meta_ml"]

        self.assertEqual(da_tela, do_hoje)

    def test_a_meta_da_tela_acompanha_o_peso(self):
        """Controle positivo do teste acima, e ele nasceu de uma sabotagem.

        Trocar a chamada por `meta_ml = 3000` passou VERDE — porque o usuário
        de teste pesa 82,4 kg, e 82,4 x 35 arredondado para o meio litro dá
        exatamente 3.000. A comparação entre as duas telas continua certa; ela
        só não distingue uma constante que por acaso acertou o número.

        Trocar o peso desfaz qualquer coincidência: nenhuma constante segue
        102 kg até 3.500 ml.
        """
        antes = self.abrir().context["meta_ml"]

        # `update`, e não `create`: há uma pesagem por dia por restrição de
        # banco (`unique_weight_per_day`), e o usuário de teste já pesou hoje.
        WeightEntry.objects.filter(user=self.pessoa).update(weight_kg=Decimal("102"))
        depois = self.abrir().context["meta_ml"]

        self.assertNotEqual(depois, antes)
        self.assertEqual(depois, 3500)


class OsSeteDiasDaTelaTests(Base):
    """A semana da tela de hidratação, dia a dia.

    Ela responde outra pergunta que `agua_por_semana` — "como foi ESTA semana,
    dia a dia?" contra "como foram as últimas oito semanas?" — e por isso é
    outra função. O que as duas compartilham é a política honesta da média:
    sobre os dias COM registro, nunca sobre os sete.
    """

    def registrar(self, dias_atras, ml):
        from plans.models import HydrationLog as Log

        Log.objects.create(
            user=self.pessoa, date=self.hoje - timedelta(days=dias_atras), ml=ml
        )

    def semana(self, meta=3000):
        from plans import tracking

        return tracking.agua_dos_ultimos_dias(self.pessoa, meta, hoje=self.hoje)

    def test_a_janela_tem_sete_dias_e_termina_hoje(self):
        dados = self.semana()

        self.assertEqual(len(dados["linhas"]), 7)
        self.assertEqual(dados["linhas"][-1]["data"], self.hoje)
        self.assertTrue(dados["linhas"][-1]["e_hoje"])
        self.assertEqual(dados["linhas"][0]["data"], self.hoje - timedelta(days=6))

    def test_dia_sem_linha_aparece_como_dia_sem_registro(self):
        """E não como dia de zero ml. A tela diz a diferença em voz alta
        porque só o código sabendo dela não ajuda ninguém."""
        self.registrar(2, 2000)

        linhas = self.semana()["linhas"]

        self.assertFalse(linhas[0]["tem_registro"])
        self.assertEqual(linhas[0]["ml"], 0)
        self.assertTrue(linhas[4]["tem_registro"])

    def test_a_media_e_dos_dias_com_registro_e_nao_dos_sete(self):
        """3.000 em dois dias é média de 1.500, e não de 857. Dividir por sete
        descreveria um comportamento que não aconteceu."""
        self.registrar(1, 1000)
        self.registrar(2, 2000)

        self.assertEqual(self.semana()["media_ml"], 1500)
        self.assertEqual(self.semana()["com_registro"], 2)

    def test_conta_quantos_dias_bateram_a_meta(self):
        self.registrar(1, 3000)
        self.registrar(2, 2999)
        self.registrar(3, 4000)

        self.assertEqual(self.semana()["bateram"], 2)

    def test_a_barra_satura_em_cem_por_cento(self):
        """Quem bebeu 4 L de uma meta de 3 L não desenha barra maior que a
        caixa — mas o número ao lado continua sendo o real."""
        self.registrar(1, 6000)

        linha = self.semana()["linhas"][5]

        self.assertEqual(linha["pct"], 100)
        self.assertEqual(linha["ml"], 6000)

    def test_dia_de_fora_da_janela_nao_entra(self):
        """Contrato de comportamento, não de linha.

        Quem garante isto é o laço que gera as sete datas, e não o `date__gte`
        da consulta: tirar o filtro deixa este teste verde, porque a linha
        volta do banco e ninguém a procura. Está medido e escrito lá também,
        para o filtro não ser lido como guarda de correção.
        """
        self.registrar(7, 3000)

        dados = self.semana()

        self.assertEqual(dados["com_registro"], 0)
        self.assertEqual(dados["media_ml"], 0)

    def test_a_agua_de_outra_pessoa_nao_entra(self):
        from plans.models import HydrationLog as Log

        Log.objects.create(user=self.outra, date=self.hoje, ml=3000)

        self.assertEqual(self.semana()["com_registro"], 0)

    def test_sem_meta_a_barra_nao_inventa_porcentagem(self):
        """Divisão por zero seria o defeito óbvio; inventar 100% seria o
        silencioso."""
        self.registrar(1, 2000)

        dados = self.semana(meta=0)

        self.assertEqual(dados["linhas"][5]["pct"], 0)
        self.assertEqual(dados["bateram"], 0)


class ZerarLimpaODiaInteiroTests(Base):
    """Zerar é "recomeçar o dia" — e o dia é o total E a composição.

    Encontrado no navegador, não em teste: a tela de hidratação mostrava
    "Registrado 0 ml" com a lista de goles cheia logo abaixo. O `zerar` só
    mexia em `HydrationLog`, e os `GoleDeAgua` daquele dia ficavam órfãos.

    O estrago não é cosmético. Com goles órfãos, "desfazer" continua oferecido
    e apaga um gole de um dia que já está zerado — a pessoa toca em desfazer e
    o número não muda, porque `Greatest(..., 0)` segura o total no chão. Um
    botão que não faz nada visível é indistinguível de um botão quebrado.
    """

    def test_zerar_apaga_os_goles_do_dia(self):
        self.beber(250)
        self.beber(500)

        self.beber(0)

        self.assertEqual(self.total(), 0)
        self.assertFalse(GoleDeAgua.objects.filter(user=self.pessoa, dia=self.hoje).exists())

    def test_zerar_nao_alcanca_o_gole_de_ontem(self):
        """A intenção é recomeçar HOJE. Ontem não está sendo recomeçado."""
        ontem = self.hoje - timedelta(days=1)
        GoleDeAgua.objects.create(user=self.pessoa, dia=ontem, ml=500)

        self.beber(250)
        self.beber(0)

        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa, dia=ontem).count(), 1)

    def test_zerar_nao_alcanca_o_gole_de_outra_pessoa(self):
        self.client.force_login(self.outra)
        self.beber(750)

        self.client.force_login(self.pessoa)
        self.beber(250)
        self.beber(0)

        self.assertEqual(GoleDeAgua.objects.filter(user=self.outra).count(), 1)

    def test_depois_de_zerar_nao_sobra_o_que_desfazer(self):
        """A consequência visível do defeito: o botão continuava oferecido e
        não movia o número."""
        self.beber(500)
        self.beber(0)

        resposta = self.client.get(reverse("plans:today"))

        self.assertFalse(resposta.context["pode_desfazer_agua"])


class ODiaComTotalESemComposicaoTests(Base):
    """O dia de quem já usava o app antes da tabela de goles.

    Encontrado no navegador: a tela dizia "Nada registrado hoje ainda" a três
    centímetros de um painel escrito "500 · Registrado". Duas frases da mesma
    tela discordando sobre o mesmo dia — e a que mentia era a de baixo, porque
    o app sabia dos 500 ml.
    """

    def abrir(self):
        return self.client.get(reverse("plans:hydration"))

    def test_a_tela_nao_diz_que_nada_foi_registrado_quando_ha_total(self):
        HydrationLog.objects.create(user=self.pessoa, date=self.hoje, ml=500)

        resposta = self.abrir()

        self.assertContains(resposta, "500")
        self.assertNotContains(resposta, "Nada registrado hoje ainda")
        self.assertContains(resposta, "sem horário")

    def test_ela_explica_por_que_nao_ha_horario(self):
        HydrationLog.objects.create(user=self.pessoa, date=self.hoje, ml=500)

        # A frase quebra em duas linhas no template, e `assertContains` compara
        # o HTML cru: o trecho procurado tem de caber numa linha só. Não casou
        # na primeira escrita, e é por isso que está anotado.
        self.assertContains(self.abrir(), "passar a guardar cada gole separado")

    def test_o_dia_de_verdade_vazio_continua_dizendo_que_esta_vazio(self):
        """Controle positivo: sem ele, apagar a frase de vazio deixaria os dois
        testes acima verdes e a tela sem estado vazio nenhum."""
        self.assertContains(self.abrir(), "Nada registrado hoje ainda")


    def test_a_lista_soma_exatamente_o_total_do_painel(self):
        """O dia da virada: total antigo mais um gole novo.

        Encontrado no navegador — registrando 1.000 num dia que já tinha 500, a
        lista mostrava 1.000 embaixo de um painel de 1.500. Uma lista que não
        fecha com o próprio total é do tipo que faz alguém parar de confiar no
        número.
        """
        HydrationLog.objects.create(user=self.pessoa, date=self.hoje, ml=500)
        self.beber(1000)

        contexto = self.abrir().context

        soma = sum(g.ml for g in contexto["goles"]) + contexto["sem_horario"]
        self.assertEqual(soma, contexto["bebido"])
        self.assertEqual(contexto["sem_horario"], 500)

    def test_num_dia_que_nasceu_depois_da_tabela_nao_sobra_linha_sem_hora(self):
        """Controle positivo: se `sem_horario` fosse sempre o total, o teste
        acima passaria e toda tela ganharia uma linha fantasma."""
        self.beber(750)

        self.assertEqual(self.abrir().context["sem_horario"], 0)
        self.assertNotContains(self.abrir(), "sem horário")


class ODesfazerMoraOndeAListaEstaTests(Base):
    """A tela que mostra os goles é a tela que os desfaz.

    A primeira versão mandava a pessoa de volta ao painel do dia para tirar um
    gole — com a lista dele aberta na frente dela.
    """

    def abrir(self):
        return self.client.get(reverse("plans:hydration"))

    def test_com_gole_a_tela_oferece_o_desfazer(self):
        self.beber(250)

        self.assertContains(self.abrir(), "desfazer o último")

    def test_sem_gole_a_tela_nao_oferece_um_botao_que_so_pode_falhar(self):
        """Dia com total e sem composição cai aqui: a linha "sem horário" não é
        um gole, e desfazer ali só teria como dar erro."""
        HydrationLog.objects.create(user=self.pessoa, date=self.hoje, ml=500)

        resposta = self.abrir()

        self.assertContains(resposta, "sem horário")
        self.assertNotContains(resposta, "desfazer o último")

    def test_desfazer_daqui_desfaz_e_volta_para_ca(self):
        """O formulário RENDERIZADO, e não um POST montado à mão: o que quebra
        neste caminho é o nome de um campo do template, e um `client.post` com
        o dicionário certo passaria por cima disso sem ver."""
        self.beber(250)
        self.beber(750)

        html = self.abrir().content.decode()
        self.assertIn('name="acao" value="desfazer"', html)
        self.assertIn('name="de" value="hidratacao"', html)

        resposta = self.client.post(
            reverse("plans:log_hydration"), {"acao": "desfazer", "de": "hidratacao"}
        )

        self.assertEqual(resposta["Location"], reverse("plans:hydration"))
        self.assertEqual(self.total(), 250)


class CampoVazioNaoApagaODiaTests(Base):
    """Zero é uma INTENÇÃO — "recomeçar o dia" —, e não o que sobra quando a
    leitura falha.

    Achado ao reler o caminho novo, e ele só existe por causa dele: enquanto os
    emissores eram os três botões e o "zerar" (que manda `value="0"` de
    propósito), `ml` nunca chegava vazio. A tela de hidratação criou o emissor
    que faltava — um `<input type="number">` sem valor envia `ml=`, `int("")`
    estoura, e o `except` devolvia 0.

    O estrago seria máximo: tocar "Somar" com o campo em branco apagaria o dia
    inteiro, agora incluindo os goles, que o zerar passou a limpar junto.
    """

    def test_campo_vazio_nao_zera_o_dia(self):
        self.beber(750)

        self.beber("")

        self.assertEqual(self.total(), 750, "o campo vazio apagou o dia")
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 1)

    def test_ml_ausente_nao_zera_o_dia(self):
        self.beber(750)

        self.client.post(reverse("plans:log_hydration"), {"de": "hidratacao"})

        self.assertEqual(self.total(), 750)

    def test_texto_no_lugar_do_numero_nao_zera_o_dia(self):
        self.beber(500)

        self.beber("mil")

        self.assertEqual(self.total(), 500)

    def test_o_zerar_de_verdade_continua_zerando(self):
        """Controle positivo: sem ele, recusar TUDO passaria como se fosse a
        correção — e o botão "zerar" teria morrido em silêncio."""
        self.beber(500)

        self.beber(0)

        self.assertEqual(self.total(), 0)
        self.assertFalse(GoleDeAgua.objects.filter(user=self.pessoa).exists())


class ODesfazerNaoPodeSerAPLICADODUASVEZESTests(Base):
    """Desfazer SUBTRAI, e a fila offline reenvia.

    Achado por revisão adversarial. A trava de idempotência ficava DEPOIS do
    ramo do desfazer: `ja_aplicada` tinha um único ponto de chamada, e o
    `return self._desfazer(request)` passava por cima dele. O `CLAUDE.md` já
    dizia quem precisa da trava — "Água SOMA e suplemento ALTERNA — as duas
    precisam de op_id" —, e subtrair é a mesma família.

    O estrago: o servidor aplica, a resposta se perde, `fila.js` reenvia o
    mesmo corpo, e um SEGUNDO gole vai embora. Silenciosamente, porque não há
    erro nenhum nesse caminho.
    """

    def desfazer_com(self, op_id):
        return self.client.post(
            reverse("plans:log_hydration"), {"acao": "desfazer", "op_id": op_id}
        )

    def test_o_mesmo_op_id_nao_desfaz_dois_goles(self):
        self.beber(250)
        self.beber(500)
        self.beber(750)

        self.desfazer_com("op-desfazer-1")
        self.desfazer_com("op-desfazer-1")

        self.assertEqual(self.total(), 750, "o reenvio desfez um segundo gole")
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 2)

    def test_op_ids_diferentes_desfazem_dois_goles(self):
        """Controle positivo: sem ele, uma trava que recusasse TODO desfazer
        passaria como se estivesse deduplicando."""
        self.beber(250)
        self.beber(500)
        self.beber(750)

        self.desfazer_com("op-desfazer-1")
        self.desfazer_com("op-desfazer-2")

        self.assertEqual(self.total(), 250)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 1)

    def test_sem_op_id_o_desfazer_da_tela_continua_funcionando(self):
        """A tela normal não manda `op_id`, e `ja_aplicada` devolve `False`
        para vazio de propósito. Se ela travasse o vazio, o botão morreria."""
        self.beber(250)
        self.beber(500)

        self.desfazer()
        self.desfazer()

        self.assertEqual(self.total(), 0)


class OTetoDeDezLitrosEOUnicoLugarOndeAListaNaoFechaTests(Base):
    """A exceção declarada, provada em vez de prometida.

    O gole guarda o que foi PEDIDO; o total guarda o que coube abaixo do teto
    diário de 10 L. Acima dele os dois divergem, e nada reconcilia — reconciliar
    seria reescrever números que a pessoa registrou.
    """

    def test_acima_do_teto_a_soma_das_linhas_passa_do_painel(self):
        for _ in range(6):
            self.beber(2000)

        contexto = self.client.get(reverse("plans:hydration")).context

        self.assertEqual(contexto["bebido"], 10000, "o teto diário mudou")
        self.assertEqual(sum(g.ml for g in contexto["goles"]), 12000)
        self.assertEqual(contexto["sem_horario"], 0, "sem_horario ficou negativo")

    def test_abaixo_do_teto_ela_fecha(self):
        """Controle positivo do teste acima: a divergência é DO TETO, e não uma
        propriedade geral da tela."""
        for _ in range(4):
            self.beber(2000)

        contexto = self.client.get(reverse("plans:hydration")).context

        self.assertEqual(sum(g.ml for g in contexto["goles"]), contexto["bebido"])


class OCTADoCartaoAgoraNaoJogaAPessoaParaBaixoTests(Base):
    """O botão de água do cartão AGORA fica no TOPO da tela.

    A âncora `#hidratacao` foi desenhada para quem já estava no cartão de água,
    2.500px abaixo — medido no navegador em 375x812 e registrado em `_hoje_em`.
    Ela continua certa para os botões de lá.

    O ramo novo pôs o mesmo formulário no topo, e várias vezes ao dia. Sem
    `de=topo`, tocar "Registrar 500 ml" jogaria a pessoa para o fim da página,
    longe do cartão que ela acabou de obedecer. Achado por revisão adversarial.
    """

    def cartao_agora(self):
        """O HTML do cartão AGORA, e só dele.

        A primeira versão deste teste procurava `name="ml" value="500"` na
        página inteira e casava com o botão "+500" do cartão de água, lá
        embaixo — o mesmo par de atributos, outro formulário. Recortar a seção
        é o que faz a asserção falar do cartão que ela diz medir.
        """
        html = self.client.get(reverse("plans:today")).content.decode()
        inicio = html.index("agora-card")
        return html[inicio : html.index("</section>", inicio)]

    def resolver_as_refeicoes(self):
        """Sem refeição pendente, o cartão do topo fala de água."""
        # O plano sai do CONTEXTO da tela, e não de uma consulta própria:
        # `PlanRequiredMixin` é quem o cria/sincroniza na entrada, e antes do
        # primeiro GET ele pode nem existir.
        plano = self.client.get(reverse("plans:today")).context["plan"]
        for slot in plano.slots.all():
            MealLog.objects.create(
                user=self.pessoa, slot=slot, date=self.hoje, status=MealStatus.DONE
            )

    def test_o_formulario_do_cartao_manda_de_topo(self):
        """No HTML RENDERIZADO. Um teste que só chamasse a view com o
        dicionário certo nunca veria o campo faltando no template."""
        self.resolver_as_refeicoes()

        cartao = self.cartao_agora()

        self.assertIn("agora-card--agua", cartao, "o cartão do topo não é o de água")
        self.assertIn('name="de" value="topo"', cartao)

    def test_o_recorte_do_cartao_realmente_exclui_o_de_agua(self):
        """Controle positivo do recorte: sem refeição resolvida o cartão do topo
        NÃO é de água, e o `de=topo` não pode aparecer nele. Se `cartao_agora`
        estivesse devolvendo a página toda, este teste ficaria vermelho."""
        cartao = self.cartao_agora()

        self.assertNotIn("agora-card--agua", cartao)
        self.assertNotIn('name="de" value="topo"', cartao)

    def test_de_topo_volta_para_o_hoje_sem_ancora(self):
        resposta = self.beber(500, de="topo")

        self.assertEqual(resposta["Location"], reverse("plans:today"))
        self.assertNotIn("#", resposta["Location"])

    def test_os_botoes_do_cartao_de_agua_continuam_indo_para_a_ancora(self):
        """Controle positivo: se `de` passasse a valer para todo mundo, quem
        toca +250 lá embaixo seria jogado para o topo a cada copo — que é o
        problema que a âncora resolveu em primeiro lugar."""
        resposta = self.beber(250)

        self.assertIn("#hidratacao", resposta["Location"])
