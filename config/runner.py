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
import os

from django.db import connections
from django.test.runner import DiscoverRunner

#: Escotilha de emergência. Existe porque um guardrail sem saída, num projeto de
#: uma pessoa, é um jeito de ficar sem poder publicar num sábado à noite. Usar
#: isto com uma suíte de verdade rodando produz resultado corrompido — é essa a
#: troca, e ela fica escrita aqui.
IGNORAR = "NUTRIPLAN_IGNORAR_RUNNER_UNICO"


def nome_do_banco_de_teste(conexao):
    """O nome que o Django vai usar, e não um palpite com prefixo."""
    configurado = conexao.settings_dict.get("TEST", {}).get("NAME")
    if configurado:
        return configurado
    return "test_" + conexao.settings_dict["NAME"]


def conexoes_ativas(conexao, nome_de_teste):
    """Quem está conectado ao banco de teste AGORA.

    Inclui os clones do `--parallel` (`test_nutriplan_1`, `_2`, ...): uma
    execução paralela também é uma execução, e brigar com ela dá o mesmo
    resultado embaralhado.

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
                   AND (datname = %s OR datname LIKE %s)
                 ORDER BY pid
                """,
                [nome_de_teste, nome_de_teste + r"\_%"],
            )
            return cursor.fetchall()
    except Exception:
        # Amplo de propósito: qualquer falha ao PERGUNTAR não pode virar falha
        # ao RODAR. O pior caso desta função é não saber, e não saber já está
        # tratado — o runner segue.
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


class RunnerUnico(DiscoverRunner):
    """O `DiscoverRunner` de sempre, com a verificação antes de criar o banco."""

    def setup_databases(self, **kwargs):
        if not os.environ.get(IGNORAR):
            for alias in connections:
                conexao = connections[alias]
                nome = nome_do_banco_de_teste(conexao)
                linhas = conexoes_ativas(conexao, nome)
                if linhas:
                    raise SystemExit(descrever(linhas, nome))
        return super().setup_databases(**kwargs)
