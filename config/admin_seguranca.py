"""Tira do Django Admin as telas que só servem para expor segredo.

O allauth registra três models por conta própria, e dois deles guardam
credencial:

    SocialToken  -> token, token_secret
    SocialApp    -> client_id, secret, key

Nenhum dos dois responde pergunta de suporte. "Esta conta entra pelo Google?"
se responde pelo `SocialAccount`; "o login está configurado?" se responde
tentando entrar. Token de acesso e segredo do app OAuth não são informação
operacional — são material de autenticação, e uma tela que os mostra é uma
forma de vazá-los com dois cliques.

Hoje o papel Administradores NutriPlan não tem permissão para eles, e a URL
responde 403. Isso é risco LATENTE, não exposição ativa: basta alguém conceder
a permissão um dia — ou criar um superuser — para as telas aparecerem com os
valores dentro. Desregistrar remove a superfície em vez de depender de a
permissão continuar ausente para sempre.

QUANDO isto roda importa. `accounts` vem antes de `allauth` em INSTALLED_APPS,
então `accounts/admin.py` é carregado primeiro e um `unregister` ali não
encontraria nada para tirar. `config/urls.py` é importado depois de o
`autodiscover` do admin ter passado por todos os apps, e é de lá que esta
função é chamada.

Desregistrar do Admin NÃO desliga o login social: o allauth lê essas tabelas em
tempo de execução e não depende da interface administrativa para nada.
"""
from django.apps import apps
from django.contrib import admin

#: Models de terceiros cuja tela administrativa expõe credencial.
SEM_TELA = (
    ("socialaccount", "SocialToken"),
    ("socialaccount", "SocialApp"),
    # `SocialAccount` não guarda token, e isso não o torna inofensivo:
    # `extra_data` é o perfil que o Google devolve — nome, foto, locale, o
    # `sub`. O próprio projeto já tinha concluído isso em `accounts/adapters.py`,
    # ao descobrir que `sociallogin.serialize()` carregava o blob junto com os
    # tokens. A pergunta de suporte — "esta conta entra por Google?" — virou
    # uma coluna derivada no UserAdmin, que é um booleano.
    ("socialaccount", "SocialAccount"),
    # `EmailAddress` guarda o endereço e o estado de verificação de cada conta.
    # Duas razões para não ter tela: o app roda com
    # `ACCOUNT_EMAIL_VERIFICATION = "none"`, então o model não responde nenhuma
    # pergunta de suporte; e o formulário dele EDITA o endereço — trocar o
    # e-mail de alguém e pedir recuperação de senha é uma tomada de conta em
    # dois passos. Ausência de permissão já bloqueava, mas segredo e tomada de
    # conta não devem depender só disso: basta alguém conceder a permissão um
    # dia.
    ("account", "EmailAddress"),
)


def esconder_segredos_de_terceiros() -> list:
    """Desregistra as telas que expõem credencial. Devolve o que saiu."""
    removidos = []
    for app_label, nome in SEM_TELA:
        modelo = apps.get_model(app_label, nome)
        if admin.site.is_registered(modelo):
            admin.site.unregister(modelo)
            removidos.append(f"{app_label}.{nome}")
    return removidos
