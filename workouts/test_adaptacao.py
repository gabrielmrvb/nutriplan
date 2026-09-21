# -*- coding: utf-8 -*-
"""A adaptação é um módulo PURO com estado nomeado (T2.1, 17/09/2026).

Três coisas que este arquivo prende, e o defeito que cada uma evita:

- PUREZA TEXTUAL de `workouts/adaptacao.py`: sem `django.db`, `timezone` e
  `requests`. Um módulo que "só lê" mas abre uma consulta ou olha o relógio
  não pode ser simulado por um ano em memória — e é a simulação que vai
  calibrar RETOMAR e ESTAGNADO (T2.3). O verificador tem controle positivo:
  ele reprova o próprio texto com uma linha de `django.db` inserida;
- FRASE == CAMPO: 60/60/55 com todas as reps no topo é MANTER com valor 60,
  a frase cita 60, e o campo abre com 60 — antes, a terceira série abria
  com 55 (mesma série da última vez) enquanto a frase falava de 60;
- `load_history` entrega `sessoes` (≤ 10 datas) e `ultimo_registro` do
  MESMO laço: a adaptação lê o que a tela já carregou, sem consulta a mais.

Os cinco casos de b14efff (13/09) continuam em `test_dupla_progressao.py`.
"""
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from workouts import adaptacao, services
from workouts.models import ExerciseLog, Measure, MuscleGroup
from workouts.test_dupla_progressao import _anterior, _Item, _Log
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts

FONTE = Path(__file__).resolve().parent / "adaptacao.py"
PROIBIDOS = ("django.db", "timezone", "requests", "from django", "import django")


def impurezas(texto):
    """As linhas de CÓDIGO (não de comentário nem docstring) que citam algo
    proibido. Docstrings são tiradas antes, porque o módulo explica em
    prosa exatamente o que ele não importa."""
    sem_docstrings = re.sub(r'"""[\s\S]*?"""', "", texto)
    return [
        linha.strip()
        for linha in sem_docstrings.splitlines()
        if not linha.lstrip().startswith("#") and any(p in linha for p in PROIBIDOS)
    ]


class OModuloEPuroTests(SimpleTestCase):
    def test_nao_importa_banco_relogio_nem_rede(self):
        self.assertEqual(impurezas(FONTE.read_text(encoding="utf-8")), [])

    def test_o_verificador_enxerga_uma_impureza(self):
        """Controle positivo: sem ele, um verificador quebrado passaria para
        sempre."""
        texto = FONTE.read_text(encoding="utf-8") + "\nfrom django.db import connection\n"
        self.assertEqual(impurezas(texto), ["from django.db import connection"])
        texto = FONTE.read_text(encoding="utf-8") + "\nfrom django.utils import timezone\n"
        self.assertTrue(impurezas(texto))

    def test_o_estado_tem_nome_e_imprime_como_o_template_espera(self):
        self.assertEqual(str(adaptacao.Estado.SUBIR), "subir")
        self.assertEqual(str(adaptacao.Estado.MANTER), "manter")
        self.assertEqual(adaptacao.Estado.SUBIR, "subir")
        self.assertEqual(adaptacao.MUDA_CARGA, frozenset({adaptacao.Estado.SUBIR}))
        self.assertNotIn(adaptacao.Estado.MANTER, adaptacao.MUDA_CARGA)

    def test_as_constantes_copiadas_batem_com_os_modelos(self):
        """`REPS` e `GRUPOS_INFERIORES` são cópias para o módulo não importar
        `models`; se os modelos mudarem, este teste avisa."""
        self.assertEqual(adaptacao.REPS, Measure.REPS)
        self.assertEqual(
            adaptacao.GRUPOS_INFERIORES,
            frozenset({MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES, MuscleGroup.CALVES}),
        )
        self.assertIs(services.GRUPOS_INFERIORES, adaptacao.GRUPOS_INFERIORES)
        self.assertIs(services.Progressao, adaptacao.Progressao)


class ARegraComEstadoNomeadoTests(SimpleTestCase):
    def _ajuste(self, *series, hoje=None, **item):
        anterior = _anterior(*series)
        return adaptacao.ajuste(_Item(**item), [(date(2026, 9, 13), anterior)], anterior[max(anterior)], hoje or date(2026, 9, 16))

    def test_fechou_na_mesma_carga_sobe(self):
        p = self._ajuste((60, 10), (60, 10), (60, 10))
        self.assertIs(p.estado, adaptacao.Estado.SUBIR)
        self.assertEqual(p.valor, Decimal("62.5"))

    def test_sessenta_sessenta_cinquenta_e_cinco_mantem_sessenta_e_diz_por_que(self):
        """A terceira série foi mais leve: não fechou a faixa A 60. O valor
        é 60 (a maior) e a frase cita 60 e 55."""
        p = self._ajuste((60, 10), (60, 10), (55, 10))
        self.assertIs(p.estado, adaptacao.Estado.MANTER)
        self.assertEqual(p.valor, Decimal("60"))
        self.assertIn("série 3", p.razao)
        self.assertIn("55 kg", p.razao)
        self.assertIn("60 kg", p.razao)

    def test_faltou_rep_e_serie_mais_leve_a_rep_fala_primeiro(self):
        p = self._ajuste((60, 10), (60, 9), (55, 10))
        self.assertIs(p.estado, adaptacao.Estado.MANTER)
        self.assertIn("faltaram 1 rep na série 2", p.razao)

    def test_a_frase_escreve_a_carga_com_virgula(self):
        p = self._ajuste((62.5, 10), (62.5, 10), (60, 10))
        self.assertIn("60 kg", p.razao)
        self.assertIn("62,5 kg", p.razao)

    def test_so_a_sessao_mais_recente_decide_em_t21(self):
        """Com várias datas, a primeira da lista (a mais recente) é a que
        conta; as outras já chegam para T2.3."""
        recente = _anterior((60, 10), (60, 10), (60, 9))
        antiga = _anterior((60, 10), (60, 10), (60, 10))
        p = adaptacao.ajuste(
            _Item(), [(date(2026, 9, 13), recente), (date(2026, 9, 10), antiga)], recente[3], date(2026, 9, 16),
        )
        self.assertIs(p.estado, adaptacao.Estado.MANTER)

    def test_sem_sessoes_hoje_ou_sem_anilha_nao_ha_o_que_dizer(self):
        self.assertIsNone(adaptacao.ajuste(_Item(), [], None, date(2026, 9, 16)))
        anterior = _anterior((60, 10), (60, 10), (60, 10))
        self.assertIsNone(adaptacao.ajuste(_Item(load={"hoje": {1: _Log(60, 8)}}), [(date(2026, 9, 13), anterior)], anterior[3], date(2026, 9, 16)))
        self.assertIsNone(adaptacao.ajuste(_Item(equipment="bodyweight"), [(date(2026, 9, 13), anterior)], anterior[3], date(2026, 9, 16)))
        self.assertIsNone(adaptacao.ajuste(_Item(measure=Measure.SECONDS), [(date(2026, 9, 13), anterior)], anterior[3], date(2026, 9, 16)))

    def test_o_alias_de_services_aceita_o_load_antigo(self):
        """`proxima_carga` com um `load` que só tem `anterior` (os dublês de
        13/09) continua respondendo — e o mesmo `load` com `sessoes` também."""
        item = _Item(load={"anterior": _anterior((60, 10), (60, 10), (55, 10)), "hoje": {}})
        self.assertIs(services.proxima_carga(item).estado, adaptacao.Estado.MANTER)
        self.assertEqual(services.proxima_carga(item).valor, Decimal("60"))


class OHistoricoEntregaAsSessoesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="sessoes@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _registra(self, dias_atras, pesos_e_reps):
        for n, (peso, reps) in enumerate(pesos_e_reps, start=1):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=dias_atras),
                set_number=n, weight_kg=Decimal(peso), reps=reps,
            )

    def test_sessoes_vem_do_mesmo_laco_ate_dez_datas_e_o_ultimo_registro(self):
        for dias in range(3, 3 + 14 * 3, 3):  # 14 datas, a cada três dias
            self._registra(dias, [("60", 10), ("60", 10), ("60", 10)])
        with CaptureQueriesContext(connection) as ctx:
            load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)[self.item.exercise_id]
        self.assertEqual(len(ctx.captured_queries), 1, "o histórico é UMA consulta")
        # Dez, LITERAL: o contrato do plano (T2.1) é "≤ 10 datas", e comparar
        # com a constante deixaria uma sabotagem da constante passar.
        self.assertEqual(adaptacao.SESSOES_LIDAS, 10)
        self.assertEqual(len(load["sessoes"]), 10)
        datas = [d for d, _ in load["sessoes"]]
        self.assertEqual(datas, sorted(datas, reverse=True), "da mais recente para trás")
        self.assertEqual(datas[0], self.hoje - timedelta(days=3))
        self.assertEqual(set(load["sessoes"][0][1]), {1, 2, 3})
        self.assertEqual(load["ultimo_registro"].date, self.hoje - timedelta(days=3))
        self.assertEqual(load["dia"], self.hoje)

    def test_sem_historico_as_chaves_existem_vazias(self):
        load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)
        self.assertEqual(load, {})
        self._registra(0, [("60", 10)])
        load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)[self.item.exercise_id]
        self.assertEqual(load["sessoes"], [])
        self.assertIsNone(load["ultimo_registro"])


class ATelaConcordaComOModuloTests(TestCase):
    """60/60/55 na tela: o campo abre com 60 em toda série e a frase cita 60."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="tela-adaptacao@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS and i.sets >= 3
        )

    def _html(self):
        return sem_scripts(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode())

    def test_sessenta_sessenta_cinquenta_e_cinco_frase_igual_ao_campo(self):
        pesos = ["60"] * self.item.sets
        pesos[-1] = "55"
        for n, peso in enumerate(pesos, start=1):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=3),
                set_number=n, weight_kg=Decimal(peso), reps=self.item.rep_max,
            )
        html = self._html()
        campo = re.search(r'name="weight_kg"[^>]*value="([^"]*)"', html).group(1)
        sugestao = html.split('class="agora__anterior-sugestao"', 1)[1].split("</span>", 1)[0]
        numero_da_frase = re.search(r'<b class="num">([^<]*) kg</b>', sugestao).group(1)
        self.assertEqual(campo, "60")
        self.assertEqual(numero_da_frase, "60")
        self.assertIn("manter", sugestao)
        self.assertIn("série %d" % self.item.sets, sugestao)
        self.assertIn("55 kg", sugestao)
