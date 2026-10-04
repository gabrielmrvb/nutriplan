# -*- coding: utf-8 -*-
"""O worker do `--parallel` mede o MESMO dia que o processo principal.

No Windows o `multiprocessing` usa `spawn`: o worker nasce vazio, importa tudo
do zero e NÃO passa por `RunnerUnico.setup_test_environment`, que é onde o
relógio da suíte era ligado. Resultado visto em 28/09/2026: numa segunda-feira
de verdade, `manage.py test --parallel 4` rodava os workers na data real e
`plans.test_progresso_tela` e `workouts.test_ficha_da_letra_repetida` caíam —
e, sem `tblib`, a primeira falha derrubava a corrida paralela inteira.

Estes testes sobem um interpretador vazio DE VERDADE e chamam o inicializador
do jeito que `ParallelTestSuite.run` chama (`init_worker.__func__` + os
mesmos `initargs`), em vez de inspecionar atributos: o que importa é a data
que o worker enxerga, e ela só aparece do lado de lá do processo.
"""
import os
import pickle
import subprocess
import sys
from datetime import date
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase
from django.utils.module_loading import import_string

from config import relogio

#: Nenhuma data que a máquina real vá ter de novo, e uma segunda-feira: a
#: data congelada de PADRÃO (quarta 16/09) não prova que o ambiente chegou ao
#: worker — um worker que ignorasse a variável cairia nela por acaso.
DATA_ESCOLHIDA = date(2026, 1, 5)

#: O que o worker `spawn` faz ao nascer: um interpretador vazio roda o
#: `init_worker` da suíte (que sobe o Django e, no nosso, liga o relógio) e só
#: então o primeiro teste. `used_aliases=set()` pula a troca de banco do
#: worker; o resto é o que `ParallelTestSuite.run` entrega ao `initializer`.
_WORKER = """
import ctypes, multiprocessing, sys
from django.utils import timezone
from django.utils.module_loading import import_string

multiprocessing.set_start_method("spawn")
suite = import_string(sys.argv[1]).parallel_test_suite([], 2)
suite.init_worker.__func__(
    multiprocessing.Value(ctypes.c_int, 0), {}, {},
    suite.process_setup.__func__, suite.process_setup_args, False, set(),
)
print(timezone.localdate().isoformat())
"""


def _data_no_worker_de(runner):
    """A data que um worker `spawn` do `runner` enxerga, em processo de verdade.

    Subprocesso e não `multiprocessing.Pool`: sob `--parallel` este teste roda
    DENTRO de um worker, e worker é daemon — `daemonic processes are not
    allowed to have children` (visto na primeira corrida paralela inteira).
    """
    suite = import_string(runner).parallel_test_suite([], 2)
    # O `spawn` entrega o inicializador ao worker por pickle, por referência:
    # função aninhada ou lambda mataria a corrida paralela já na largada.
    pickle.loads(pickle.dumps(suite.init_worker.__func__))
    saida = subprocess.run(
        [sys.executable, "-c", _WORKER, runner],
        cwd=settings.BASE_DIR, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120, check=True,
    ).stdout
    return date.fromisoformat(saida.strip().splitlines()[-1])


class RelogioNoWorkerDoParaleloTests(SimpleTestCase):
    def setUp(self):
        ambiente = mock.patch.dict(os.environ, {relogio.VARIAVEL_DATA: DATA_ESCOLHIDA.isoformat()})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        # A noturna roda com `NUTRIPLAN_DATA_REAL=1`; aqui o ambiente do worker
        # é o que o teste escreve, não o que a corrida herdou.
        os.environ.pop(relogio.VARIAVEL_DATA_REAL, None)

    def test_o_worker_do_runner_mede_a_data_congelada(self):
        """O defeito de 28/09/2026: a suíte paralela media o dia de HOJE."""
        self.assertEqual(_data_no_worker_de("config.runner.RunnerUnico"), DATA_ESCOLHIDA)

    def test_o_worker_do_django_puro_mede_o_dia_real(self):
        """Controle positivo: sem a subclasse o worker `spawn` ESTÁ na data real.

        Se este teste ficasse verde com o relógio ligado por outro caminho, o
        de cima não provaria nada — ele só vale porque o mesmo procedimento,
        com o `ParallelTestSuite` de fábrica, enxerga o defeito.
        """
        self.assertNotEqual(_data_no_worker_de("django.test.runner.DiscoverRunner"), DATA_ESCOLHIDA)
