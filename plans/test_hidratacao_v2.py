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

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SyncedOperation
from plans.models import GoleDeAgua, HydrationLog
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
