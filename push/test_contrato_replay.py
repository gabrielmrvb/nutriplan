"""Toda rota que a fila offline enfileira precisa honrar o contrato de replay.

A lista de rotas NÃO é repetida aqui: ela é lida do próprio `fila.js`. É essa
inversão que faz o teste valer alguma coisa. Uma quarta rota acrescentada lá
sem contrato declarado aqui derruba a suíte com o nome dela na mensagem, em vez
de entrar em silêncio e só aparecer quando alguém perder uma marcação.

O que cada rota precisa provar:

1. replay com dono de OUTRA pessoa não muta nada e é preservado;
2. o MESMO replay enviado duas vezes é aplicado uma vez só.

O item 2 é o que um endpoint novo erra com mais facilidade. O `CLAUDE.md` já
nomeia a armadilha: água SOMA e suplemento ALTERNA, então as duas dependem de
`op_id`; marcação e carga usam `update_or_create` e são seguras por
construção. Trocar qualquer uma por um contador quebra a fila em silêncio.

Limite honesto da medição: o estado é lido como (soma de água, nº de marcações,
nº de séries). Isso pega linha duplicada e soma dobrada — não pegaria um campo
incrementado dentro de uma linha que já existe.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.db.models import Sum

from accounts.replay import STATUS_PRESERVA
from plans import services
from plans.models import HydrationLog, MealLog, MealStatus
from plans.tests import CatalogFixture, create_complete_user
from workouts.models import Exercise, ExerciseLog

RAIZ = Path(__file__).resolve().parent.parent


def rotas_declaradas_no_cliente():
    """As regex de `ROTAS` como o `fila.js` as escreve."""
    fonte = (RAIZ / "static" / "js" / "fila.js").read_text(encoding="utf-8")
    bloco = fonte[fonte.index("var ROTAS = [") : fonte.index("];", fonte.index("var ROTAS = ["))]
    return set(re.findall(r"/\^(.+?)\$/", bloco))


class ContratoDeReplayPorRotaTests(CatalogFixture):
    """Cada rota da fila, medida contra o contrato."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.a = create_complete_user(email="contrato-a@exemplo.com")
        self.b = create_complete_user(email="contrato-b@exemplo.com")
        self.plano = services.create_plan(self.b)
        self.slot = self.plano.slots.get(order=0)
        self.exercicio = Exercise.objects.filter(is_active=True).first()
        self.client.force_login(self.b)

    # A tabela. Chave = a regex escrita no `fila.js`, sem as âncoras.
    def contrato(self):
        return {
            r"\/agua\/": ("/agua/", {"ml": "250"}),
            r"\/refeicao\/\d+\/marcar\/": (
                "/refeicao/%d/marcar/" % self.slot.pk,
                {"status": MealStatus.SKIPPED},
            ),
            r"\/treino\/exercicio\/\d+\/carga\/": (
                "/treino/exercicio/%d/carga/" % self.exercicio.pk,
                {"weight_kg": "42,5", "set_number": "1"},
            ),
        }

    def estado(self):
        return (
            HydrationLog.objects.aggregate(t=Sum("ml"))["t"] or 0,
            MealLog.objects.count(),
            ExerciseLog.objects.count(),
        )

    def _replay(self, url, dados, dono, op_id):
        corpo = dict(dados, op_id=op_id)
        return self.client.post(
            url,
            corpo,
            HTTP_X_REQUESTED_WITH="fetch",
            HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(dono),
        )

    def test_toda_rota_da_fila_tem_contrato_declarado(self):
        """O guardrail. Rota nova no cliente sem contrato aqui = suíte vermelha.

        Sem isto, um quarto endpoint entraria na fila protegido só pelo
        middleware — que cobre dono e CSRF, mas não sabe nada sobre
        idempotência. Um endpoint que some em vez de sobrescrever passaria
        despercebido até alguém beber um litro que não bebeu.
        """
        no_cliente = rotas_declaradas_no_cliente()
        com_contrato = set(self.contrato())

        self.assertEqual(
            no_cliente,
            com_contrato,
            "rota de replay sem contrato declarado em push/test_contrato_replay.py: "
            "%s" % (no_cliente ^ com_contrato),
        )

    def test_dono_de_outra_pessoa_nao_muta_nada(self):
        for rota, (url, dados) in self.contrato().items():
            with self.subTest(rota=rota):
                antes = self.estado()

                r = self._replay(url, dados, dono=self.a.pk, op_id="alheia-%s" % rota)

                self.assertEqual(r.status_code, STATUS_PRESERVA)
                self.assertEqual(self.estado(), antes)

    def test_o_mesmo_replay_duas_vezes_e_aplicado_uma_vez(self):
        for rota, (url, dados) in self.contrato().items():
            with self.subTest(rota=rota):
                op = "repetida-%s" % rota
                antes = self.estado()

                self._replay(url, dados, dono=self.b.pk, op_id=op)
                depois_da_primeira = self.estado()
                self._replay(url, dados, dono=self.b.pk, op_id=op)

                self.assertNotEqual(
                    depois_da_primeira, antes, "controle positivo: a primeira gravou"
                )
                self.assertEqual(self.estado(), depois_da_primeira)
