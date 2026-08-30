"""O que as telas de entrada precisam saber e não vem da view.

Uma coisa só: se o login com Google está configurado.

É processador de contexto e não contexto de view porque quem pergunta são
DUAS telas — entrar e criar conta — pelo mesmo parcial, e um dia serão três.
Passar por cada view seria a mesma linha repetida em cada uma, esperando que
alguém esqueça a terceira e mostre um botão que leva a um erro do Google.
"""
from django.conf import settings


def google_login(request):
    return {
        # Só o booleano. O `client_id` não é segredo, mas também não tem nada
        # que fazer no HTML: o fluxo é todo de servidor, e nenhum JavaScript
        # daqui fala com o Google.
        "google_login_enabled": settings.GOOGLE_LOGIN_ENABLED,
    }
