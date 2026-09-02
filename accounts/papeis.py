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
#: LEITURA é `view`. EDICAO é `view` e `change`. ESCRITA acrescenta `add`.
#:
#: Nenhum inclui `delete`: apagar conta é exclusão a pedido da pessoa, tem
#: fluxo próprio em `ExcluirContaView`, e não pode virar botão de rotina.
#:
#: EDICAO existe separada de ESCRITA por causa de `accounts.user`. A pergunta
#: que a criou: qual é o caso operacional para um administrador CRIAR conta?
#: Não há. O cadastro é auto-serviço, e conta criada pelo painel nasce sem
#: perfil, sem plano e sem senha escolhida pela pessoa — um registro que o app
#: não sabe usar. O bootstrap administrativo já recusa criar conta pela mesma
#: razão: um typo viraria conta fantasma.
#:
#: O catálogo continua com ESCRITA porque ali `add` tem uso real — alguém
#: acrescenta um alimento que faltava. Separar as constantes é o que permite
#: tirar `add` de um lado sem tirar do outro.
LEITURA = ("view",)
EDICAO = ("view", "change")
ESCRITA = ("view", "add", "change")

PAPEIS = {
    ADMINISTRADORES: {
        # Contas: ver e corrigir, nunca criar.
        ("accounts", "user"): EDICAO,
        # `change_profile` fica porque a ação "solicitar nova escolha de
        # divisão" grava no perfil. O FORMULÁRIO não oferece campo editável
        # nenhum — a única escrita possível passa pela ação, que é auditada.
        ("accounts", "profile"): LEITURA,
        ("accounts", "trainingday"): LEITURA,
        ("accounts", "registroadministrativo"): LEITURA,
        # Catálogo: é conteúdo do produto e alguém precisa poder corrigir uma
        # receita errada — ou acrescentar um alimento — sem abrir o banco.
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


#: Permissões de PROPÓSITO, que não seguem o padrão `acao_model`.
#:
#: `pedir_nova_escolha_de_divisao` existe porque a única escrita administrativa
#: aprovada sobre o perfil é uma operação específica, e não "mexer no perfil".
#: `change_profile` cobriria vinte campos para autorizar um.
EXTRAS = {
    ADMINISTRADORES: ("pedir_nova_escolha_de_divisao",),
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
    codenames = list(EXTRAS.get(papel, ()))
    for (app, modelo), acoes in desejadas.items():
        tipo = tipos.get((app, modelo))
        if tipo is None:
            # O model sumiu ou foi renomeado. Não é erro de configuração do
            # grupo: é o catálogo de models mudando embaixo dele, e quem
            # descobre é o teste que compara os dois.
            continue
        codenames.extend(f"{acao}_{modelo}" for acao in acoes)
    apps_do_papel = {app for app, _ in desejadas} | {"accounts"}
    return list(
        Permission.objects.filter(
            codename__in=codenames,
            content_type__app_label__in=apps_do_papel,
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
