"""Quase vazio de propósito, e por pouco tempo.

O módulo de acompanhamento profissional foi removido. Este arquivo e a pasta
`migrations/` sobrevivem a um deploy para que a migração 0002 derrube as
tabelas em produção — um app apagado do disco não roda migração nenhuma, e o
schema ficaria órfão para sempre.

Somem no commit seguinte, depois de o deploy confirmar que as tabelas caíram.
"""


def gerar_codigo() -> str:
    """Sobrevive porque a migração 0001 aponta para ela pelo nome.

    Django grava o caminho da função no arquivo de migração, e recusa carregar
    a migração se o caminho não resolver — mesmo que o valor nunca mais seja
    usado, que é o caso: a 0002 apaga a tabela inteira.
    """
    return ""
