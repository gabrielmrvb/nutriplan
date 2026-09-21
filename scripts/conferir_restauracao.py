# -*- coding: utf-8 -*-
"""A conferência que fecha o drill mensal de restauração (21/09/2026): o banco
RESTAURADO contra a ORIGEM, tabela a tabela.

    ORIGEM_URL='postgres://...' DESTINO_URL='postgres://...' python scripts/conferir_restauracao.py

As duas URLs entram por AMBIENTE, nunca por argumento (argumento aparece em
`ps` e no log do runner). O que se confere, e por quê:

* **toda tabela de `public` da origem existe no destino** com a MESMA
  contagem, salvo uma tolerância pequena (`TOLERANCIA`: 1 % ou 5 linhas, o
  que for maior) — o dump é um retrato de um instante e a origem continua
  viva: quem registra água às 6h da manhã do dia 1 não pode disparar alarme
  de backup quebrado. Tabela que SUMIU ou divergiu além disso é falha;
* **as migrações são as mesmas** (o conjunto de `django_migrations`): um
  dump de outro schema restaura "com sucesso" e não serve para o app que
  está no ar;
* **há gente**: `accounts_user` com pelo menos uma linha. Um dump vazio que
  restaura limpo é a esperança que o `backup.sh` já aprendeu a não aceitar.

Sai com 0 quando tudo confere e 1 com a lista do que divergiu. Nada aqui
lê CONTEÚDO de linha — só `count(*)` e nomes de tabela: o dump tem e-mail,
peso e histórico de treino de gente real, e o log do Actions é público.
"""
import os
import sys

TOLERANCIA_FRACAO = 0.01
TOLERANCIA_LINHAS = 5
#: Tabelas que o próprio drill/serviço muda o tempo todo e não medem nada.
IGNORADAS = {"django_session"}


def tolerancia(origem):
    return max(TOLERANCIA_LINHAS, int(origem * TOLERANCIA_FRACAO))


def comparar(origem, destino):
    """(divergências, resumo) a partir de dois dicionários {tabela: contagem}."""
    divergencias = []
    for tabela, na_origem in sorted(origem.items()):
        if tabela in IGNORADAS:
            continue
        no_destino = destino.get(tabela)
        if no_destino is None:
            divergencias.append("%s: existe na origem (%d linhas) e NÃO no restaurado" % (tabela, na_origem))
        elif abs(na_origem - no_destino) > tolerancia(na_origem):
            divergencias.append("%s: origem %d, restaurado %d (tolerância %d)" % (tabela, na_origem, no_destino, tolerancia(na_origem)))
    return divergencias, {"tabelas": len(origem), "linhas_origem": sum(origem.values()), "linhas_restauradas": sum(destino.values())}


def conferir(origem, destino, migracoes_origem, migracoes_destino, usuarios):
    """Todas as réguas de uma vez; devolve a lista de falhas (vazia = confere)."""
    falhas, _ = comparar(origem, destino)
    if set(migracoes_origem) != set(migracoes_destino):
        faltam = sorted(set(migracoes_origem) - set(migracoes_destino))
        sobram = sorted(set(migracoes_destino) - set(migracoes_origem))
        falhas.append("django_migrations difere: faltam %s, sobram %s" % (faltam[:5], sobram[:5]))
    if usuarios < 1:
        falhas.append("accounts_user restaurada com %d linhas — dump vazio não é backup" % usuarios)
    return falhas


def _contagens(conexao):
    tabelas = [r[0] for r in conexao.execute(
        "select tablename from pg_tables where schemaname = 'public' order by 1").fetchall()]
    resultado = {}
    for tabela in tabelas:
        resultado[tabela] = conexao.execute('select count(*) from "%s"' % tabela.replace('"', '""')).fetchone()[0]
    return resultado


def _migracoes(conexao):
    return [(a, n) for a, n in conexao.execute("select app, name from django_migrations").fetchall()]


def main():
    import psycopg

    origem_url, destino_url = os.environ.get("ORIGEM_URL", ""), os.environ.get("DESTINO_URL", "")
    if not origem_url or not destino_url:
        raise SystemExit("defina ORIGEM_URL e DESTINO_URL no ambiente (nunca como argumento).")
    with psycopg.connect(origem_url, connect_timeout=60) as origem, psycopg.connect(destino_url, connect_timeout=60) as destino:
        contagens_origem, contagens_destino = _contagens(origem), _contagens(destino)
        migracoes_origem, migracoes_destino = _migracoes(origem), _migracoes(destino)
        usuarios = destino.execute("select count(*) from accounts_user").fetchone()[0]
    falhas = conferir(contagens_origem, contagens_destino, migracoes_origem, migracoes_destino, usuarios)
    _, resumo = comparar(contagens_origem, contagens_destino)
    print("tabelas na origem: %(tabelas)d | linhas: origem %(linhas_origem)d, restaurado %(linhas_restauradas)d" % resumo)
    print("migrações: %d na origem, %d no restaurado | usuários restaurados: %d" % (len(migracoes_origem), len(migracoes_destino), usuarios))
    if falhas:
        print("RESTAURAÇÃO NÃO CONFERE:")
        for falha in falhas:
            print("  -", falha)
        return 1
    print("RESTAURAÇÃO CONFERE: o backup de hoje volta inteiro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
