"""Toda rota que a fila offline enfileira precisa honrar o contrato de replay.

A lista de rotas NÃO é repetida aqui: ela é lida do próprio `fila.js`. É essa
inversão que faz o teste valer alguma coisa. Uma quarta rota acrescentada lá
sem contrato declarado aqui derruba a suíte com o nome dela na mensagem, em vez
de entrar em silêncio e só aparecer quando alguém perder uma marcação.

O que cada rota precisa provar:

1. replay com dono de OUTRA pessoa não muta nada e é preservado;
2. o MESMO replay enviado duas vezes é aplicado uma vez só.

O item 2 é o que um endpoint novo erra com mais facilidade. O `CLAUDE.md` já
nomeia a armadilha: água SOMA, e por isso depende de `op_id`; marcação usa
`update_or_create` e é segura por construção. Trocar qualquer uma por um
contador quebra a fila em silêncio.

A CARGA DE TREINO esteve nesta lista e saiu em 05/09/2026 — e este teste é quem
avisou, ficando vermelho no instante em que a rota deixou `ROTAS` sem a entrada
daqui sair junto. É exatamente para isso que a lista é LIDA do `fila.js` em vez
de repetida. A carga não é mais enfileirada porque o corpo dela carrega um
contador defasado e o replay apaga série; ver
`workouts/test_carga_fora_da_fila.py` e `CAMPANHA — CARGA OFFLINE V2` no
BACKLOG. Note que ela tinha a propriedade de idempotência que este arquivo
exige: repetir o mesmo corpo era seguro. Chegar ATRASADO não era — e o contrato
daqui nunca mediu isso.

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
