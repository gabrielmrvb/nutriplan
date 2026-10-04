# -*- coding: utf-8 -*-
"""Um runner de cada vez, verificado em vez de combinado.

O contrato do B9 diz, com todas as letras: "NUNCA rodar suíte dirigida enquanto
suíte completa estiver usando o mesmo test_nutriplan. Antes de qualquer nova
execução: verificar se existe runner ativo."

Isso era uma regra escrita, e regra escrita depende de alguém lembrar. Ela
falhou duas vezes na mesma sessão, das duas formas possíveis:

  * uma suíte dirigida disparada durante a completa, e as duas brigando pelo
    mesmo `test_nutriplan`;
  * uma execução interrompida deixando conexão órfã, e o hook de push morrendo
    com `database "test_nutriplan" is being accessed by other users` — uma
    mensagem que fala de banco quando o problema é de processo.

O `--noinput` do hook não resolve o segundo caso: ele responde "sim, pode
apagar", e o Postgres continua recusando porque ALGUÉM está conectado.

Este runner verifica antes de criar o banco, e a mensagem diz o que fazer.
Verificar, e não matar: derrubar a conexão de uma suíte legítima em andamento
trocaria um erro claro por um resultado errado.
"""
import multiprocessing
import os
import re
import sys
import threading

from django.conf import settings
from django.db import connections
from django.test.runner import DiscoverRunner, ParallelTestSuite

from config import branch, relogio

#: Escotilha de emergência. Existe porque um guardrail sem saída, num projeto de
#: uma pessoa, é um jeito de ficar sem poder publicar num sábado à noite. Usar
#: isto com uma suíte de verdade rodando produz resultado corrompido — é essa a
#: troca, e ela fica escrita aqui.
IGNORAR = "NUTRIPLAN_IGNORAR_RUNNER_UNICO"


def nome_do_banco_de_teste(conexao):
    """O nome que o Django vai usar, e não um palpite com prefixo.

    `TEST.NAME` no settings vence; sem ele, o da branch (`config/branch.py`).
    """
    configurado = conexao.settings_dict.get("TEST", {}).get("NAME")
    if configurado:
        return configurado
    return branch.banco_de_teste("test_" + conexao.settings_dict["NAME"], settings.BASE_DIR)


def conexoes_ativas(conexao, nome_de_teste):
    """Quem está conectado ao banco de teste AGORA.

    Inclui os clones do `--parallel` (`test_nutriplan_1`, `_2`, ...): uma
    execução paralela também é uma execução, e brigar com ela dá o mesmo
    resultado embaralhado. E SÓ os clones numéricos: ``LIKE 'test_nutriplan\\_%'``
    casava com `test_nutriplan_design`, o banco de teste de outro worktree,
    que não disputa nada com este — e recusava uma execução legítima.

    E SÓ cliente: com `--keepdb` o banco do push persiste, e um autovacuum
    trabalhando nele aparecia aqui como "alguém conectado" e recusava o push.

    Devolve `None` quando não dá para saber — banco fora do ar, backend que não
    é Postgres, permissão negada. Não saber não é motivo para impedir a pessoa
    de rodar teste; é motivo para não afirmar nada.
    """
    if conexao.vendor != "postgresql":
        return None
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT pid,
                       datname,
                       COALESCE(state, 'desconhecido'),
                       COALESCE(EXTRACT(EPOCH FROM (now() - state_change)), 0)
                  FROM pg_stat_activity
                 WHERE pid <> pg_backend_pid()
                   AND backend_type = 'client backend'
                   AND (datname = %s OR datname ~ %s)
                 ORDER BY pid
                """,
                [nome_de_teste, "^" + re.escape(nome_de_teste) + "_[0-9]+$"],
            )
            return cursor.fetchall()
    except Exception:
        # Amplo de propósito: qualquer falha ao PERGUNTAR não pode virar falha
        # ao RODAR. O pior caso desta função é não saber, e não saber já está
        # tratado — o runner segue.
        return None


def intrusos(nome_de_teste, etiqueta):
    """Quem está no banco de teste e NÃO é desta rodada.

    A rodada se reconhece pela etiqueta (`PGAPPNAME`, que os clones do
    `--parallel` herdam). Pergunta pelo banco de manutenção, nunca pelo de
    teste: o vigia conectado no banco de teste travaria o DROP do fim.

    `None` quando não dá para saber — a mesma filosofia de `conexoes_ativas`.
    """
    try:
        with connections["default"]._nodb_cursor() as cursor:
            cursor.execute(
                """
                SELECT pid, COALESCE(application_name, '')
                  FROM pg_stat_activity
                 WHERE backend_type = 'client backend'
                   AND (datname = %s OR datname ~ %s)
                   AND COALESCE(application_name, '') <> %s
                 ORDER BY pid
                """,
                [nome_de_teste, "^" + re.escape(nome_de_teste) + "_[0-9]+$", etiqueta],
            )
            return cursor.fetchall()
    except Exception:
        return None


def descrever(linhas, nome_de_teste):
    """A mensagem que a pessoa lê às onze da noite.

    Ela precisa responder três coisas, nesta ordem: o que está acontecendo,
    como confirmar, e como sair. Um "runner ativo detectado" sozinho manda a
    pessoa procurar no histórico o comando que ela não anotou.
    """
    quem = "\n".join(
        "    pid %s em %s — %s há %d s" % (pid, banco, estado, segundos)
        for pid, banco, estado, segundos in linhas
    )
    return (
        "Já existe alguém conectado a %(banco)s:\n\n%(quem)s\n\n"
        "Rodar agora embaralharia as duas execuções — é a regra do B9.\n\n"
        "Se for uma suíte de verdade em andamento, espere ela terminar.\n"
        "Se for sobra de uma execução interrompida, derrube só as conexões\n"
        "DESTE banco — o banco real fica intocado, o nome abaixo começa com\n"
        "test_:\n\n"
        "    psql -U postgres -d postgres -c "
        "\"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname LIKE '%(banco)s%%'\"\n\n"
        "Em último caso, %(ignorar)s=1 pula esta checagem — e aceita o\n"
        "resultado embaralhado que ela existe para evitar."
        % {"banco": nome_de_teste, "quem": quem, "ignorar": IGNORAR}
    )


def _init_worker_com_relogio(*args, **kwargs):
    """O `init_worker` do Django, mais o relógio da suíte no worker.

    No `spawn` (Windows, macOS) o worker nasce vazio e não passa por
    `RunnerUnico.setup_test_environment`: sem isto ele roda na data REAL, e a
    corrida paralela mede o dia de hoje em vez do dia da suíte. O ambiente
    (`NUTRIPLAN_DATA_REAL`, `NUTRIPLAN_DATA_DA_SUITE`) o worker herda do
    processo principal. Só no `fork` o relógio já veio na cópia da memória
    (`forkserver`, o padrão do Linux a partir do Python 3.14, também nasce vazio).
    """
    ParallelTestSuite.init_worker(*args, **kwargs)
    if multiprocessing.get_start_method() != "fork":
        relogio.ligar_para_a_suite()


class SuiteParalelaComRelogio(ParallelTestSuite):
    # Sem `staticmethod`: o Django lê `self.init_worker.__func__`.
    init_worker = _init_worker_com_relogio


class RunnerUnico(DiscoverRunner):
    """O `DiscoverRunner` de sempre, com a verificação antes de criar o banco.

    E com o RELÓGIO da suíte (`config/relogio.py`): a data congelada por
    padrão, a real com `NUTRIPLAN_DATA_REAL=1`. Liga em
    `setup_test_environment`, antes de qualquer fixture, para o `default`
    de `DateField` e o `auto_now_add` de toda linha criada nascerem no dia
    que a suíte mede.
    """

    parallel_test_suite = SuiteParalelaComRelogio
    _relogio = None
    _vigia = None
    _intruso = False
    #: Segundos entre uma pergunta do vigia e a próxima.
    intervalo_do_vigia = 15

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._relogio = relogio.ligar_para_a_suite()

    def teardown_test_environment(self, **kwargs):
        if self._relogio is not None:
            self._relogio.desligar()
            self._relogio = None
        super().teardown_test_environment(**kwargs)

    def setup_databases(self, **kwargs):
        # A etiqueta ANTES de qualquer conexão: a libpq lê `PGAPPNAME` ao
        # conectar, e os clones do `--parallel` herdam o ambiente.
        etiqueta = os.environ["PGAPPNAME"] = "nutriplan-teste-%d" % os.getpid()
        # O nome da branch vira o `TEST.NAME` — senão o Django criaria o
        # `test_` + NAME de sempre e a checagem olharia outro banco.
        padrao = connections["default"]
        padrao.settings_dict.setdefault("TEST", {})["NAME"] = nome_do_banco_de_teste(padrao)
        if not os.environ.get(IGNORAR):
            for alias in connections:
                conexao = connections[alias]
                nome = nome_do_banco_de_teste(conexao)
                linhas = conexoes_ativas(conexao, nome)
                if linhas:
                    raise SystemExit(descrever(linhas, nome))
        criados = super().setup_databases(**kwargs)
        # Sem banco criado não há o que vigiar; com a escotilha, o vigia
        # reprovaria justamente a rodada que ela existe para deixar passar.
        if criados and not os.environ.get(IGNORAR):
            self._parar = threading.Event()
            self._vigia = threading.Thread(
                target=self._vigiar,
                args=(padrao.settings_dict["TEST"]["NAME"], etiqueta),
                daemon=True,
            )
            self._vigia.start()
        return criados

    def _vigiar(self, nome, etiqueta):
        """A checagem de antes, repetida DURANTE a rodada.

        Conferir só antes de criar o banco deixava passar quem entrasse
        depois — um `psql` aberto, a suíte de outra sessão com o mesmo nome —
        e a rodada saía verde medindo o dado de outro.
        """
        try:
            while not self._intruso and not self._parar.wait(self.intervalo_do_vigia):
                self._conferir(nome, etiqueta)
        finally:
            connections.close_all()

    def _conferir(self, nome, etiqueta):
        linhas = intrusos(nome, etiqueta)
        if linhas:
            pid, app = linhas[0]
            sys.stderr.write(
                "INTRUSO no banco de teste %s: pid %s (app '%s') — o resultado desta "
                "rodada não vale.\n" % (nome, pid, app)
            )
            self._intruso = True

    def teardown_databases(self, old_config, **kwargs):
        if self._vigia is not None:
            self._parar.set()
            # Com teto: um connect pendurado no vigia não pode segurar o fim
            # da rodada — a thread é daemon e morre junto com o processo.
            self._vigia.join(timeout=30)
            self._vigia = None
        super().teardown_databases(old_config, **kwargs)

    def run_tests(self, *args, **kwargs):
        falhas = super().run_tests(*args, **kwargs)
        return falhas + 1 if self._intruso else falhas
