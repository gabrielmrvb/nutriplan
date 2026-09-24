"""A taxonomia — a lista FECHADA do que o produto registra.

Por que fechada: analytics sem disciplina vira lixo em três semanas. Um nome
digitado errado (`treino.inciado`) cria um evento paralelo que ninguém acha;
uma propriedade livre enche o banco de PII sem querer. Aqui o nome é `dominio.
acao`, as propriedades são declaradas, e um teste (`analytics/test_taxonomia.py`)
recusa qualquer nome usado no código que não esteja aqui.

`props` lista as propriedades ESPERADAS (documentação e conferência do painel);
não é um esquema rígido — um evento pode chegar sem uma delas. O que a ingestão
recusa é o NOME fora da lista.

`auto=True` marca o que o cliente dispara sozinho (toda tela, instalação, erro);
o resto é de negócio, disparado no ponto onde a ação acontece.

NUNCA declare aqui uma propriedade de PII: e-mail, nome, peso exato. Peso vira
faixa (`progresso.peso_registrado` leva `faixa`, não `kg`).
"""

CATALOGO = {
    # --- Automáticos (o cliente dispara) ---
    "tela.vista": {"auto": True, "props": [], "desc": "Uma rota foi vista."},
    "tela.interativa": {
        "auto": True,
        "props": ["ms"],
        "desc": "Tempo até a tela ficar interativa (TTI), em ms.",
    },
    "pwa.instalada": {"auto": True, "props": [], "desc": "O app foi instalado (standalone)."},
    "erro.js": {
        "auto": True,
        "props": ["mensagem", "rota"],
        "desc": "Um erro de JavaScript na tela.",
    },
    # --- Entrada ---
    #
    # O PRIMEIRO DEGRAU DO FUNIL, e ele é do SERVIDOR (24/09/2026). O cliente
    # já dispara `tela.vista` em toda rota, e dava para filtrar por `route` —
    # mas um degrau de funil preso ao texto de uma rota quebra em silêncio no
    # dia em que a rota muda de nome, e a landing é a única tela cujo papel no
    # produto é ser o topo do funil. Nome próprio, disparado onde a tela é
    # servida: some se a landing sumir, e não se ela mudar de endereço.
    "site.landing_vista": {"props": [], "desc": "Alguém abriu a landing."},
    # --- Onboarding ---
    "onboarding.iniciado": {"props": [], "desc": "Abriu a primeira etapa."},
    "onboarding.etapa_concluida": {"props": ["etapa"], "desc": "Concluiu uma etapa (1-3)."},
    "onboarding.concluido": {"props": [], "desc": "Terminou o cadastro e ganhou o plano."},
    "onboarding.abandonado": {"props": ["etapa"], "desc": "Saiu no meio de uma etapa."},
    # --- Dieta ---
    "dieta.refeicao_registrada": {"props": ["opcao"], "desc": "Marcou uma refeição do plano."},
    "dieta.pulou": {"props": [], "desc": "Marcou 'pulei' uma refeição."},
    "dieta.comeu_outra_coisa": {"props": [], "desc": "Marcou 'comi outra coisa'."},
    # --- Treino ---
    "treino.iniciado": {"props": ["letra"], "desc": "Começou uma sessão de treino."},
    "treino.serie_concluida": {
        "props": ["exercicio", "carga", "reps"],
        "desc": "Concluiu uma série.",
    },
    "treino.concluido": {"props": ["duracao"], "desc": "Fechou o treino do dia."},
    "treino.troca": {"props": ["de", "para"], "desc": "Trocou a forma de um exercício."},
    # --- Corrida / água / progresso ---
    "corrida.registrada": {"props": ["origem"], "desc": "Registrou uma corrida (manual ou arquivo)."},
    "agua.registrada": {"props": [], "desc": "Registrou água."},
    "progresso.peso_registrado": {"props": ["faixa"], "desc": "Registrou o peso (faixa, nunca o kg exato)."},
    # --- Conquista ---
    "conquista.desbloqueada": {"props": ["nome"], "desc": "Desbloqueou uma conquista."},
    # --- Conta ---
    "conta.criada": {"props": [], "desc": "Criou a conta."},
    "conta.login": {"props": [], "desc": "Entrou."},
    "conta.excluida": {"props": [], "desc": "Excluiu a conta."},
    # --- Lembrete ---
    "lembrete.recebido": {"props": [], "desc": "Uma notificação de lembrete foi exibida."},
    "lembrete.clicado": {"props": [], "desc": "Tocou num lembrete."},
}


def existe(nome):
    """O nome está na taxonomia? A ingestão e a instrumentação perguntam isso."""
    return nome in CATALOGO


def automaticos():
    return {n for n, v in CATALOGO.items() if v.get("auto")}
