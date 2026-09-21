# -*- coding: utf-8 -*-
"""O relógio da suíte: data E hora congeladas por padrão (quarta 16/09, 12:00 +
decorrido), devolução exata.

Cada teste aqui é uma propriedade que, quebrada, faria a suíte medir o dia
em vez do código — o defeito de `plans.test_stress` na quarta 16/09 e o de
`test_a_ficha_de_OUTRO_dia` no fatiamento de 18/09. O módulo `config/
relogio.py` conta a história; estes testes cobram que ela continue verdade.
"""
import ast
import os
from datetime import date, datetime, timezone as fuso_utc
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from accounts.models import WeightEntry
from achievements.models import UserAchievement
from config import relogio

#: `default=timezone.localdate` lê `now()` do módulo na hora; `default=
#: timezone.now` guardou o objeto da função. Os dois têm de nascer no mesmo
#: dia, e é por isso que os dois estão aqui.
CAMPO_DE_DATA = WeightEntry._meta.get_field("date")
CAMPO_DE_DATA_HORA = UserAchievement._meta.get_field("unlocked_at")


def _dia_local(instante):
    return timezone.localtime(instante).date()


class ASuiteMedeUmDiaSoTests(SimpleTestCase):
    def test_hoje_e_a_data_que_o_relogio_declara(self):
        """O runner ligou o relógio antes deste teste rodar — ou disse que não.

        Por padrão (sem variável de ambiente) hoje é a quarta 16/09/2026; com
        `NUTRIPLAN_DATA_REAL=1` é o dia de verdade. Nos dois casos a suíte e
        `data_congelada()` têm de concordar, senão o log da noturna mente.
        """
        declarada = relogio.data_congelada()
        esperada = declarada if declarada is not None else _dia_local(relogio._agora_real())
        self.assertEqual(timezone.localdate(), esperada)
        if not os.environ.get(relogio.VARIAVEL_DATA_REAL) and not os.environ.get(relogio.VARIAVEL_DATA):
            self.assertEqual(timezone.localdate(), relogio.DATA_DA_SUITE)
            self.assertEqual(relogio.DATA_DA_SUITE.weekday(), 2, "quarta-feira, o pior estado medido")

    def test_a_hora_e_a_da_suite_e_continua_andando(self):
        """A hora NÃO é a da máquina (doutrina de 21/09/2026: nunca ler o
        relógio real): é `HORA_DA_SUITE` mais o decorrido desde que o runner
        ligou o relógio. `created_at` precisa continuar ordenando, e um
        teste que espera "agora > antes" precisa continuar verdadeiro."""
        if os.environ.get(relogio.VARIAVEL_DATA_REAL):
            self.skipTest("noturna: relógio real")
        antes = timezone.now()
        depois = timezone.now()
        self.assertGreaterEqual(depois, antes)
        congelada = timezone.localtime(timezone.now())
        self.assertEqual(congelada.hour, relogio.HORA_DA_SUITE.hour)
        # a suíte inteira roda em bem menos de uma hora; o minuto é o decorrido
        self.assertLess(congelada.minute, 60)

    def test_um_instante_exato_para_no_lugar(self):
        """`congelado_em(datetime)` é o que um teste de janela usa: dois
        `now()` seguidos são o MESMO instante, no fuso do projeto."""
        with relogio.congelado_em(datetime(2026, 9, 16, 14, 7, 30)):
            a = timezone.now()
            b = timezone.now()
            self.assertEqual(a, b)
            local = timezone.localtime(a)
            self.assertEqual((local.hour, local.minute, local.second), (14, 7, 30))
            self.assertEqual(timezone.localdate(), date(2026, 9, 16))

    def test_os_defaults_de_data_e_de_data_hora_nascem_no_mesmo_dia(self):
        """`WeightEntry.date` e `UserAchievement.unlocked_at` têm de concordar
        com `localdate()`: o primeiro lê `now()` na hora, o segundo guardou o
        objeto da função — e é o segundo que o relógio precisa trocar à mão."""
        hoje = timezone.localdate()
        self.assertEqual(CAMPO_DE_DATA.get_default(), hoje)
        self.assertEqual(_dia_local(CAMPO_DE_DATA_HORA.get_default()), hoje)


class OTesteQueTrocaDeDiaTests(SimpleTestCase):
    def test_congelar_outra_data_por_cima_vale_no_trecho_e_e_devolvido(self):
        """`congelado_em` é o que um teste usa para "hoje é segunda"; ao sair,
        a suíte volta ao dia dela — inclusive os defaults de campo."""
        dia_da_suite = timezone.localdate()
        default_antes = CAMPO_DE_DATA_HORA.default
        with relogio.congelado_em(date(2026, 1, 5)):
            self.assertEqual(timezone.localdate(), date(2026, 1, 5))
            self.assertEqual(CAMPO_DE_DATA.get_default(), date(2026, 1, 5))
            self.assertEqual(_dia_local(CAMPO_DE_DATA_HORA.get_default()), date(2026, 1, 5))
        self.assertEqual(timezone.localdate(), dia_da_suite)
        self.assertIs(CAMPO_DE_DATA_HORA.default, default_antes)
        self.assertEqual(_dia_local(CAMPO_DE_DATA_HORA.get_default()), dia_da_suite)

    def test_o_relogio_real_suspende_o_congelamento_so_no_trecho(self):
        dia_da_suite = timezone.localdate()
        with relogio.relogio_real():
            self.assertEqual(timezone.localdate(), _dia_local(relogio._agora_real()))
            self.assertEqual(_dia_local(CAMPO_DE_DATA_HORA.get_default()), _dia_local(relogio._agora_real()))
        self.assertEqual(timezone.localdate(), dia_da_suite)

    def test_a_hora_da_suite_e_montada_no_fuso_do_projeto_e_nao_em_utc(self):
        """12:00 de Brasília são 15:00 UTC. Montar o instante em UTC daria
        12:00 UTC = 9:00 locais, e a hora da suíte deixaria de ser a que o
        módulo declara. E o decorrido soma de verdade: uma hora e meia depois
        de ligar, são 13:30."""
        inicio = datetime(2026, 9, 21, 20, 0, tzinfo=fuso_utc.utc)
        congelado = relogio.agora_congelado(date(2026, 9, 16), inicio=inicio, agora_real=inicio)
        local = timezone.localtime(congelado)
        self.assertEqual(local.date(), date(2026, 9, 16))
        self.assertEqual((local.hour, local.minute), (12, 0))
        self.assertEqual(congelado.astimezone(fuso_utc.utc).hour, 15)
        depois = relogio.agora_congelado(date(2026, 9, 16), inicio=inicio, agora_real=inicio + timezone.timedelta(minutes=90))
        self.assertEqual((timezone.localtime(depois).hour, timezone.localtime(depois).minute), (13, 30))


class AVariavelDeAmbienteTests(SimpleTestCase):
    def test_sem_variavel_a_data_e_a_quarta_da_suite(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(relogio.VARIAVEL_DATA_REAL, None)
            os.environ.pop(relogio.VARIAVEL_DATA, None)
            self.assertEqual(relogio.data_congelada(), relogio.DATA_DA_SUITE)

    def test_a_data_da_suite_pode_ser_escolhida(self):
        """`NUTRIPLAN_DATA_DA_SUITE=2026-09-21` é como se reproduz o que a
        noturna achou numa segunda, sem esperar a segunda."""
        with mock.patch.dict(os.environ, {relogio.VARIAVEL_DATA: "2026-09-21"}):
            os.environ.pop(relogio.VARIAVEL_DATA_REAL, None)
            self.assertEqual(relogio.data_congelada(), date(2026, 9, 21))

    def test_a_data_real_vence_qualquer_data_escolhida(self):
        with mock.patch.dict(os.environ, {relogio.VARIAVEL_DATA_REAL: "1", relogio.VARIAVEL_DATA: "2026-09-21"}):
            self.assertIsNone(relogio.data_congelada())

    def test_o_runner_diz_no_log_qual_relogio_valeu(self):
        """A frase é a prova, num run do Actions, de que a noturna mediu a
        data real e o gate mediu a congelada."""
        linhas = []
        with mock.patch.dict(os.environ, {relogio.VARIAVEL_DATA_REAL: "1"}):
            self.assertIsNone(relogio.ligar_para_a_suite(escrever=linhas.append))
        self.assertIn("DATA REAL", linhas[-1])
        with mock.patch.dict(os.environ, {relogio.VARIAVEL_DATA: "2026-09-21"}):
            os.environ.pop(relogio.VARIAVEL_DATA_REAL, None)
            ligado = relogio.ligar_para_a_suite(escrever=linhas.append)
        try:
            self.assertIn("2026-09-21 (segunda)", linhas[-1])
            self.assertEqual(timezone.localdate(), date(2026, 9, 21))
        finally:
            ligado.desligar()
        self.assertEqual(timezone.localdate(), relogio.data_congelada() or _dia_local(relogio._agora_real()))


class ORunnerLigaORelogioTests(SimpleTestCase):
    def test_o_runner_liga_antes_dos_testes_e_desliga_no_fim(self):
        """Controle textual do ponto de ligação: é `setup_test_environment`,
        antes de qualquer fixture, e não `setup_databases` — o `default` de
        toda linha criada pelo seed de teste nasce no dia da suíte."""
        fonte = (Path(__file__).resolve().parent / "runner.py").read_text(encoding="utf-8")
        setup = fonte.index("def setup_test_environment")
        bancos = fonte.index("def setup_databases")
        self.assertLess(setup, bancos)
        self.assertIn("relogio.ligar_para_a_suite()", fonte[setup:bancos])
        self.assertIn("def teardown_test_environment", fonte)
        self.assertIn("self._relogio.desligar()", fonte)


RAIZ = Path(__file__).resolve().parent.parent
NOTURNA = RAIZ / ".github" / "workflows" / "noturna.yml"
GATE = RAIZ / ".github" / "workflows" / "suite.yml"


def _sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class ANoturnaTests(SimpleTestCase):
    """Textuais, como os de `test_ci.py`: o fluxo não roda aqui, mas o
    contrato dele — data real, mesmo comando, prova no log, alerta que abre
    e fecha — fica preso. O gate continua CONGELADO: é a outra metade."""

    def _noturna(self):
        return _sem_comentarios(NOTURNA.read_text(encoding="utf-8"))

    def test_roda_toda_madrugada_e_a_mao(self):
        fluxo = self._noturna()
        self.assertIn("schedule:", fluxo)
        self.assertRegex(fluxo, r'cron: "\d+ \d+ \* \* \*"')
        self.assertIn("workflow_dispatch:", fluxo)

    def test_e_a_suite_inteira_com_o_relogio_real_e_o_log_prova(self):
        """A variável liga o relógio real; o `grep` no log prova que ESTE run
        o usou — uma variável renomeada deixaria a noturna verde medindo a
        data congelada, e ninguém veria."""
        fluxo = self._noturna()
        self.assertIn('%s: "1"' % relogio.VARIAVEL_DATA_REAL, fluxo)
        self.assertIn("python manage.py test --verbosity=1 --noinput 2>&1 | tee noturna.log", fluxo)
        self.assertIn("set -o pipefail", fluxo)
        self.assertIn('grep -q "Relógio: DATA REAL" noturna.log', fluxo)
        linhas = []
        with mock.patch.dict(os.environ, {relogio.VARIAVEL_DATA_REAL: "1"}):
            relogio.ligar_para_a_suite(escrever=linhas.append)
        self.assertIn("Relógio: DATA REAL", linhas[-1], "o grep do fluxo procura a frase que o runner escreve")

    def test_o_alerta_abre_comenta_e_fecha_e_so_escreve_issue(self):
        fluxo = self._noturna()
        self.assertIn("issues: write", fluxo)
        self.assertIn("contents: read", fluxo)
        self.assertNotIn("contents: write", fluxo)
        self.assertNotIn("actions: write", fluxo)
        self.assertNotIn("secrets.", fluxo)
        alerta = fluxo[fluxo.index("  alerta:"):]
        self.assertIn("needs: [suite]", alerta)
        self.assertIn("if: ${{ always() }}", alerta)
        self.assertIn("github.rest.issues.create(", alerta)
        self.assertIn("github.rest.issues.createComment(", alerta)
        self.assertIn('state: "closed"', alerta)
        self.assertIn('resultado === "failure"', alerta)

    def test_o_controle_positivo_do_alerta_existe_e_nao_roda_a_suite(self):
        """`simular_falha` falha ANTES do checkout: é como se prova que a
        issue abre sem esperar uma madrugada vermelha de verdade."""
        fluxo = self._noturna()
        self.assertIn("simular_falha:", fluxo)
        falha = fluxo.index("inputs.simular_falha == true")
        self.assertLess(falha, fluxo.index("actions/checkout@v4"))
        self.assertIn("exit 1", fluxo[falha:falha + 400])

    def test_o_gate_continua_congelado(self):
        """A outra metade do contrato: `suite.yml` NÃO liga o relógio real.
        O gate mede sempre a mesma quarta; só a noturna vê o dia."""
        self.assertNotIn(relogio.VARIAVEL_DATA_REAL, _sem_comentarios(GATE.read_text(encoding="utf-8")))


class OTesteNaoLeAMaquinaTests(SimpleTestCase):
    """Com a data congelada, `date.today()` num teste é a data da MÁQUINA e
    `localdate()` no app é a da suíte: o teste passa a medir a diferença
    entre os dois. Achievements, test_movimento e plans.tests faziam isso
    (convertidos em 18/09/2026); a catraca impede que volte."""

    #: `PasswordResetTokenGenerator._now` é `datetime.now()` de verdade, e o
    #: teste que adianta o verificador em quatro horas precisa partir do
    #: MESMO relógio que o gerador — o real. É a única exceção, e é nomeada.
    EXCECOES = {"accounts/tests.py": {"datetime.now()": 1}}

    @staticmethod
    def _chamadas_ao_relogio_da_maquina(texto):
        """`date.today()`, `datetime.today()`, `datetime.now()`, `datetime.
        utcnow()` e `time.time()` no CÓDIGO — pela árvore, para docstring que
        cita a chamada não contar. `time.monotonic()`/`perf_counter()` ficam
        de fora: medem duração, não dizem que horas são."""
        achadas = []
        for no in ast.walk(ast.parse(texto)):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                continue
            base = no.func.value
            if not isinstance(base, ast.Name):
                continue
            if base.id in ("date", "datetime") and no.func.attr in ("today", "now", "utcnow"):
                achadas.append("%s.%s()" % (base.id, no.func.attr))
            if base.id == "time" and no.func.attr == "time":
                achadas.append("time.time()")
        return achadas

    def test_nenhum_teste_chama_o_relogio_da_maquina(self):
        achados = {}
        for caminho in sorted(RAIZ.glob("*/test*.py")):
            relativo = caminho.relative_to(RAIZ).as_posix()
            chamadas = self._chamadas_ao_relogio_da_maquina(caminho.read_text(encoding="utf-8"))
            for chamada in set(chamadas):
                n = chamadas.count(chamada)
                if n > self.EXCECOES.get(relativo, {}).get(chamada, 0):
                    achados[(relativo, chamada)] = n
        self.assertEqual(achados, {}, "teste lendo o relógio da máquina; use timezone.now()/localdate() (congelados) ou relogio.congelado_em(datetime)")
