"""Os papéis administrativos do NutriPlan e o que cada um pode fazer.

Menor privilégio, e a razão é concreta: com 52 contas em produção e uma pessoa
operando, a tentação é marcar `is_superuser` e seguir em frente. Superuser
ignora o sistema de permissões inteiro — quem tiver a sessão faz tudo, inclusive
o que ninguém pretendia autorizar. O custo de separar os papéis agora é uma
tabela; o custo de separar depois é revisar cada ação já tomada.

Os grupos são derivados dos MODELS, e não de uma lista de strings escrita à mão:
uma lista assim envelhece na primeira migration e ninguém percebe, porque
permissão que falta vira "acesso negado" e permissão que sobra não vira nada.
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

#: Quem administra o produto: contas, planos e catálogo.
ADMINISTRADORES = "Administradores NutriPlan"

#: Quem atende quem escreve. Existe declarado desde já porque a separação só
#: significa alguma coisa se nascer junto — criar "Suporte" depois, quando já
#: houver gente operando como administrador, é uma migração de hábito, não de
#: dados.
SUPORTE = "Suporte NutriPlan"

#: (app_label, model) que cada papel enxerga, e com qual profundidade.
#:
#: LEITURA é `view`. ESCRITA é `view`, `add` e `change` — nunca `delete`:
#: apagar conta é exclusão a pedido da pessoa, tem fluxo próprio em
#: `ExcluirContaView`, e não pode virar um botão de operação de rotina.
LEITURA = ("view",)
ESCRITA = ("view", "add", "change")

PAPEIS = {
    ADMINISTRADORES: {
        # Contas e o que sustenta o suporte.
        ("accounts", "user"): ESCRITA,
        ("accounts", "profile"): ESCRITA,
        ("accounts", "trainingday"): ESCRITA,
        ("accounts", "registroadministrativo"): LEITURA,
        # Catálogo: é conteúdo do produto e alguém precisa poder corrigir uma
        # receita errada sem abrir o banco.
        ("catalog", "food"): ESCRITA,
        ("catalog", "mealtemplate"): ESCRITA,
        ("catalog", "dietarytag"): ESCRITA,
        ("workouts", "exercise"): ESCRITA,
        ("workouts", "workouttemplate"): ESCRITA,
        ("supplements", "supplement"): ESCRITA,
        # Planos e registros: LEITURA. São retrato do que a pessoa fez, e
        # editá-los pelo painel reescreveria o histórico dela.
        ("plans", "nutritionplan"): LEITURA,
        ("plans", "meallog"): LEITURA,
        ("workouts", "trainingplan"): LEITURA,
        ("accounts", "weightentry"): LEITURA,
        ("achievements", "userachievement"): LEITURA,
    },
    SUPORTE: {
        # Suporte precisa ENCONTRAR a pessoa e entender o estado da conta.
        ("accounts", "user"): LEITURA,
        ("accounts", "profile"): LEITURA,
        ("accounts", "trainingday"): LEITURA,
        # E precisa ver se o plano existe, não o que ele contém em detalhe.
        ("plans", "nutritionplan"): LEITURA,
        ("workouts", "trainingplan"): LEITURA,
    },
}


def permissoes_de(papel) -> list:
    """As permissões do papel, resolvidas contra os models que existem HOJE."""
    desejadas = PAPEIS[papel]
    tipos = {
        (ct.app_label, ct.model): ct
        for ct in ContentType.objects.filter(
            app_label__in={app for app, _ in desejadas}
        )
    }
    codenames = []
    for (app, modelo), acoes in desejadas.items():
        tipo = tipos.get((app, modelo))
        if tipo is None:
            # O model sumiu ou foi renomeado. Não é erro de configuração do
            # grupo: é o catálogo de models mudando embaixo dele, e quem
            # descobre é o teste que compara os dois.
            continue
        codenames.extend(f"{acao}_{modelo}" for acao in acoes)
    return list(
        Permission.objects.filter(
            codename__in=codenames,
            content_type__app_label__in={app for app, _ in desejadas},
        )
    )


def sincronizar_papeis() -> dict:
    """Cria os grupos e ajusta as permissões deles ao estado atual do código.

    Idempotente por construção: `set()` no fim substitui o conjunto inteiro, em
    vez de acrescentar. Rodar duas vezes dá o mesmo resultado, e — o que importa
    mais — remover uma permissão daqui a REMOVE de quem já está no grupo. Uma
    função que só adiciona transforma o grupo num acúmulo histórico de tudo que
    alguém já achou necessário.
    """
    resumo = {}
    for papel in PAPEIS:
        grupo, _ = Group.objects.get_or_create(name=papel)
        permissoes = permissoes_de(papel)
        grupo.permissions.set(permissoes)
        resumo[papel] = len(permissoes)
    return resumo
