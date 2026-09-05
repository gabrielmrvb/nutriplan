# -*- coding: utf-8 -*-
"""A ordem em que a fila offline drena MUDA o resultado.

Duas metades provam isto, e nenhuma sozinha basta:

1. **A fila drena fora de ordem.** Medido em IndexedDB de verdade, no
   navegador: a store usa `keyPath: "op_id"` e o `op_id` é um
   `crypto.randomUUID()`. `getAll()` devolve por ORDEM DE CHAVE, então a ordem
   de drenagem é a ordem dos UUIDs — que não tem relação nenhuma com a ordem em
   que a pessoa tocou. Trezentas rodadas: 51,7% de inversão com duas operações
   (teórico 50%) e 85,7% com três (teórico 83,3%).

2. **As operações de água não comutam.** É o que este arquivo prova, contra as
   views de verdade. Somar, zerar e desfazer não são permutáveis, e o servidor
   está certo em não fazê-las comutar — quem tem de entregar a ordem é a fila.

Juntas: a mesma sequência de toques produz estados finais diferentes conforme
a sorte do UUID. Estes testes existem para que a correção seja medida contra o
que a pessoa FEZ, e não contra o que o servidor recebeu.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import SyncedOperation
from plans.models import GoleDeAgua, HydrationLog
from plans.tests import create_complete_user

from django.utils import timezone


class BaseDaFila(TestCase):
    """Aplica uma sequência de operações como a fila aplicaria: em série."""

    def setUp(self):
        self.pessoa = create_complete_user("fila.dona@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()

    #: Os corpos que `fila.js` guarda. São exatamente os campos do formulário
    #: mais o `op_id` que ela carimba — ver `static/js/fila.js`.
    def somar(self, ml, op="op-" + "s"):
        return {"ml": str(ml), "op_id": op}

    def zerar(self, op="op-z"):
        return {"ml": "0", "op_id": op}

    def desfazer(self, op="op-d"):
        return {"acao": "desfazer", "op_id": op}

    def drenar(self, ops):
        """O laço de `drenar()`: em série, na ordem em que a lista vier."""
        for corpo in ops:
            self.client.post(reverse("plans:log_hydration"), corpo)
        return self.total()

    def total(self):
        registro = HydrationLog.objects.filter(
            user=self.pessoa, date=self.hoje
        ).first()
        return registro.ml if registro else 0

    def recomecar_o_mundo(self):
        """Volta ao dia zero para drenar a MESMA fila noutra ordem.

        `SyncedOperation` entra na limpeza, e a primeira versão deste helper a
        esquecia. O efeito foi pior que uma falha: a segunda drenagem reusava
        `op_id` já consumido, a trava de idempotência recusava tudo, e o total
        dava ZERO — que era exatamente o número que dois destes testes
        esperavam. Eles passaram VERDES provando outra coisa.

        Comparar duas ordens é comparar dois mundos onde a mesma fila drenou
        uma vez cada. Carregar as operações aplicadas de um mundo para o outro
        é o que não existe na realidade.
        """
        HydrationLog.objects.filter(user=self.pessoa, date=self.hoje).delete()
        GoleDeAgua.objects.filter(user=self.pessoa, dia=self.hoje).delete()
        SyncedOperation.objects.filter(user=self.pessoa).delete()


class AsOperacoesDeAguaNaoComutamTests(BaseDaFila):
    """Se comutassem, a ordem da fila não importaria e não haveria campanha.

    Cada teste calcula o estado CORRETO — o que a pessoa veria tendo feito os
    mesmos toques online — e mostra o que sai de uma ordem trocada.
    """

    def test_somar_somar_desfazer_depende_da_ordem(self):
        """+500 → +500 → desfazer termina em 500.

        A mesma trinca drenada como desfazer → +500 → +500 termina em 1.000: o
        desfazer chega num dia vazio, não acha gole, e não desfaz nada. A pessoa
        tocou "desfazer" e o dia ficou com os dois copos.
        """
        certo = self.drenar([
            self.somar(500, "a"), self.somar(500, "b"), self.desfazer("c")
        ])
        self.recomecar_o_mundo()
        torto = self.drenar([
            self.desfazer("c"), self.somar(500, "a"), self.somar(500, "b")
        ])

        self.assertEqual(certo, 500)
        self.assertEqual(torto, 1000)
        self.assertNotEqual(certo, torto)

    def test_somar_zerar_somar_depende_da_ordem(self):
        """+500 → zerar → +250 termina em 250.

        Drenada como +250 → +500 → zerar, termina em ZERO: a pessoa recomeçou o
        dia e depois registrou 250, e a fila apagou os 250.
        """
        certo = self.drenar([
            self.somar(500, "a"), self.zerar("b"), self.somar(250, "c")
        ])
        self.recomecar_o_mundo()
        torto = self.drenar([
            self.somar(250, "c"), self.somar(500, "a"), self.zerar("b")
        ])

        self.assertEqual(certo, 250)
        self.assertEqual(torto, 0)

    def test_zerar_somar_depende_da_ordem(self):
        """zerar → +500 termina em 500; +500 → zerar termina em 0."""
        certo = self.drenar([self.zerar("a"), self.somar(500, "b")])
        self.recomecar_o_mundo()
        torto = self.drenar([self.somar(500, "b"), self.zerar("a")])

        self.assertEqual(certo, 500)
        self.assertEqual(torto, 0)

    def test_somar_somar_desfazer_tira_o_gole_CERTO(self):
        """+250 → +750 → desfazer deixa 250, e não 750.

        Aqui a ordem muda QUAL gole sobra, não só o total — e um teste que só
        contasse o total passaria com o gole errado.
        """
        self.drenar([
            self.somar(250, "a"), self.somar(750, "b"), self.desfazer("c")
        ])

        restantes = list(GoleDeAgua.objects.filter(user=self.pessoa))
        self.assertEqual(len(restantes), 1)
        self.assertEqual(restantes[0].ml, 250)

    def test_o_controle_positivo_somar_com_somar_COMUTA(self):
        """Nem tudo depende da ordem, e é isso que dá sentido aos testes acima.

        Dois `somar` comutam — a soma no banco é associativa. Se ESTE teste
        ficasse vermelho, o problema não seria de ordem: seria o servidor
        perdendo escrita, que é outro defeito inteiramente.
        """
        um = self.drenar([self.somar(250, "a"), self.somar(750, "b")])
        self.recomecar_o_mundo()
        outro = self.drenar([self.somar(750, "b"), self.somar(250, "a")])

        self.assertEqual(um, outro)
        self.assertEqual(um, 1000)


class OnlineEOfflineTerminamNoMesmoLugarTests(BaseDaFila):
    """Dada a ordem dos toques, o servidor termina no mesmo lugar com e sem rede.

    **Estes testes NÃO provam que a fila entrega a ordem certa**, e a primeira
    versão desta docstring dizia que sim — "a propriedade que a campanha
    inteira existe para entregar". A ordem aqui é escrita por mim na chamada;
    `emOrdemDeToque` não roda em teste Python nenhum, porque é JavaScript e não
    existe Node neste ambiente.

    Quem prova a ordem é o navegador, e está medido: enfileirados +250, +500 e
    +750 no app real, o `getAll()` devolveu `500, 250, 750` e a drenagem enviou
    `250, 500, 750`, com a fila vazia no fim e o total subindo 1.500.

    O que ESTES testes provam é a outra metade, e ela também é necessária: o
    `op_id` não muda o resultado. O mesmo corpo aplicado pelo caminho da tela e
    pelo caminho do reenvio termina igual — a trava de idempotência não é uma
    segunda semântica.
    """

    def online(self, *pedidos):
        """Os toques com rede: sem `op_id`, porque a tela não manda um."""
        for corpo in pedidos:
            sem_op = {k: v for k, v in corpo.items() if k != "op_id"}
            self.client.post(reverse("plans:log_hydration"), sem_op)
        return self.total()

    def comparar(self, *pedidos):
        com_rede = self.online(*pedidos)
        self.recomecar_o_mundo()
        pela_fila = self.drenar(list(pedidos))
        return com_rede, pela_fila

    def test_somar_somar_desfazer(self):
        com_rede, pela_fila = self.comparar(
            self.somar(500, "a"), self.somar(500, "b"), self.desfazer("c")
        )

        self.assertEqual(com_rede, 500)
        self.assertEqual(pela_fila, com_rede)

    def test_somar_zerar_somar(self):
        com_rede, pela_fila = self.comparar(
            self.somar(500, "a"), self.zerar("b"), self.somar(250, "c")
        )

        self.assertEqual(com_rede, 250)
        self.assertEqual(pela_fila, com_rede)

    def test_zerar_somar(self):
        com_rede, pela_fila = self.comparar(self.zerar("a"), self.somar(500, "b"))

        self.assertEqual(com_rede, 500)
        self.assertEqual(pela_fila, com_rede)

    def test_somar_somar_somar_desfazer_desfazer(self):
        com_rede, pela_fila = self.comparar(
            self.somar(250, "a"), self.somar(500, "b"), self.somar(750, "c"),
            self.desfazer("d"), self.desfazer("e"),
        )

        self.assertEqual(com_rede, 250)
        self.assertEqual(pela_fila, com_rede)

    def test_a_comparacao_reprova_quando_a_ordem_muda(self):
        """Controle positivo da classe inteira.

        Sem ele, `comparar` poderia estar aplicando a MESMA lista duas vezes e
        todos os testes acima passariam sem provar equivalência nenhuma.
        """
        com_rede = self.online(
            self.somar(500, "a"), self.zerar("b"), self.somar(250, "c")
        )
        self.recomecar_o_mundo()
        fora_de_ordem = self.drenar([
            self.somar(250, "c"), self.somar(500, "a"), self.zerar("b")
        ])

        self.assertNotEqual(fora_de_ordem, com_rede)


class OReenvioDuplicadoNaoMudaNadaTests(BaseDaFila):
    """A fila reenvia quando a resposta se perde, e reenviar é o caso NORMAL.

    Idempotência protege contra repetição; ordenação protege contra ordem. As
    duas são necessárias e nenhuma cobre a outra — é por isso que estes testes
    ficam ao lado dos de ordem, e não no lugar deles.
    """

    def test_somar_reenviado_soma_uma_vez_so(self):
        self.drenar([self.somar(500, "a"), self.somar(500, "a")])

        self.assertEqual(self.total(), 500)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 1)

    def test_desfazer_reenviado_desfaz_uma_vez_so(self):
        """Subtrair duas vezes tiraria um gole que a pessoa não pediu para
        tirar — e sem erro nenhum no caminho."""
        self.drenar([
            self.somar(250, "a"), self.somar(500, "b"), self.somar(750, "c")
        ])

        self.drenar([self.desfazer("d"), self.desfazer("d")])

        self.assertEqual(self.total(), 750)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 2)

    def test_zerar_reenviado_e_inofensivo(self):
        self.drenar([self.somar(500, "a"), self.zerar("b"), self.zerar("b")])

        self.assertEqual(self.total(), 0)

    def test_op_ids_diferentes_continuam_aplicando_duas_vezes(self):
        """Controle positivo: uma trava que recusasse TUDO deixaria os três
        testes acima verdes sem deduplicar coisa nenhuma."""
        self.drenar([self.somar(500, "a"), self.somar(500, "b")])

        self.assertEqual(self.total(), 1000)


class OpIdQueimadoPorFalhaNaoPodePerderAOperacaoTests(BaseDaFila):
    """A trava grava o `op_id` ANTES de o efeito acontecer.

    `ja_aplicada` faz `get_or_create` e devolve numa chamada só — de propósito,
    para não abrir janela entre conferir e gravar. Mas `ATOMIC_REQUESTS` não
    está ligado neste projeto, então esse `get_or_create` commita sozinho.

    Se a escrita seguinte estourar, o `op_id` fica queimado e o efeito não
    aconteceu. A fila preserva o item (5xx) e reenvia — e no reenvio a trava
    responde "já aplicada", a view devolve redirect, a barreira de replay
    traduz para 200, e a fila APAGA o item.

    A pessoa registrou água, o servidor falhou, e o registro sumiu sem que
    nada em lugar nenhum tenha dito que falhou. É a invariante "falha
    intermediária não faz a fila avançar incorretamente", quebrada no ponto
    exato em que ela mais importa.
    """

    def test_o_reenvio_aplica_a_operacao_que_a_falha_engoliu(self):
        from unittest import mock

        with mock.patch(
            "plans.views.GoleDeAgua.objects.create",
            side_effect=RuntimeError("banco caiu no meio"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("plans:log_hydration"), self.somar(500, "op-falha")
                )

        self.assertEqual(self.total(), 0, "o efeito nao deveria ter sobrado")

        # A fila reenvia o MESMO corpo, porque 5xx preserva o item.
        self.client.post(reverse("plans:log_hydration"), self.somar(500, "op-falha"))

        self.assertEqual(self.total(), 500, "o op_id queimado engoliu o reenvio")
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 1)

    def test_a_trava_continua_barrando_o_reenvio_de_uma_operacao_que_DEU_CERTO(self):
        """Controle positivo: sem ele, "consertar" isto soltando a trava
        passaria — e cada reenvio somaria de novo."""
        self.drenar([self.somar(500, "op-boa"), self.somar(500, "op-boa")])

        self.assertEqual(self.total(), 500)
        self.assertEqual(GoleDeAgua.objects.filter(user=self.pessoa).count(), 1)
