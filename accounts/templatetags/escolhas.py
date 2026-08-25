"""Título, subtítulo e ícone de cada opção do onboarding.

Por que aqui e não no modelo: `Goal.CUT.label` é "Emagrecer", e esse texto é
usado no perfil, no plano e no admin. O cartão precisa de três coisas — um
título curto, uma linha de explicação e um desenho — e nenhuma delas é o nome
do objetivo. Enfiar isso no `TextChoices` faria a camada de dados carregar
decisão de tela.

O ícone é o `id` de um `<symbol>` do sprite em `partials/icones.html`. Repetir
o mesmo desenho em vários lugares custaria bytes e desencontraria versões.
"""
from django import template

register = template.Library()

#: valor da escolha -> (ícone, título do cartão, linha de apoio)
DETALHES = {
    # accounts.models.Goal
    "cut": (
        "chama",
        "Emagrecer",
        "Perder gordura mantendo o máximo de músculo.",
    ),
    "bulk": (
        "halter",
        "Ganhar massa",
        "Construir músculo com superávit controlado.",
    ),
    "recomp": (
        "raio",
        "Os dois ao mesmo tempo",
        "Perder gordura e ganhar músculo — mais lento, e possível.",
    ),
    "maintain": (
        "balanca",
        "Manter o peso",
        "Ficar onde está, comendo o que gasta.",
    ),
    # accounts.models.ActivityLevel
    "sedentary": (
        "escrivaninha",
        "Sedentário / pouco ativo",
        "Passo a maior parte do dia sentado — escritório, home office ou "
        "dirigindo — e me movimento pouco.",
    ),
    "light": (
        "bicicleta",
        "Moderadamente ativo",
        "Faço caminhadas diárias, tarefas domésticas frequentes ou passo boa "
        "parte do dia em pé.",
    ),
    "active": (
        "ferramentas",
        "Altamente ativo",
        "Trabalho braçal, fico em pé o dia todo ou tenho alto gasto físico "
        "diário.",
    ),
}


@register.filter
def detalhe(valor):
    """O que desenhar no cartão desta opção.

    Devolve `None` para valor desconhecido, e o template cai no rótulo comum —
    uma escolha nova aparece sem ícone em vez de sumir da tela.
    """
    dados = DETALHES.get(str(valor))
    if not dados:
        return None
    icone, titulo, apoio = dados
    return {"icone": icone, "titulo": titulo, "apoio": apoio}
