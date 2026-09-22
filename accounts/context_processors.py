"""O que as telas de entrada precisam saber e não vem da view.

Duas coisas: se o login com Google está configurado, e se os documentos legais
já são documentos — ou ainda são rascunho, esperando a identificação de quem
responde pelos dados.

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
        # Só a casca nativa usa (Sign in with Apple, iOS); a web não tem botão.
        "apple_login_enabled": settings.APPLE_LOGIN_ENABLED,
        "google_ios_client_id": settings.GOOGLE_IOS_CLIENT_ID,
        "google_client_id": settings.GOOGLE_CLIENT_ID,
    }


def legal(request):
    """Se as páginas legais podem ser oferecidas como documento.

    Enquanto forem rascunho — sem responsável e sem contato —, o cadastro e o
    login NÃO as linkam. Oferecer "leia nossa Política de Privacidade" e
    entregar um texto que se declara incompleto é pior que não oferecer: a
    pessoa clica confiando, e encontra um aviso de que aquilo não vale.

    As páginas seguem acessíveis por URL direta, para revisão.
    """
    return {"legal_publicado": settings.LEGAL_PUBLICADO}


def freemium(request):
    """O que o template pode perguntar sobre o plano: `recursos.<nome>` e `plano`.

    Um dicionário por pedido, e não uma consulta: `recursos_de` lê o perfil
    que já está em `request.user` (ou devolve tudo `True` para quem não tem
    perfil). A regra mora em `accounts/gates.py`; aqui só se entrega.
    """
    from django.utils.functional import SimpleLazyObject

    from accounts.gates import plano_de, recursos_de

    usuario = getattr(request, "user", None)
    # PREGUIÇOSO, e a razão está medida: `plano_de` lê `user.profile`, que é
    # uma consulta quando a view buscou o perfil por outro caminho — e este
    # processor roda em TODA resposta. `OCustoDaTelaDeAreasEstaMedidoTests`
    # pegou o +1 na primeira execução. Com `SimpleLazyObject` a consulta só
    # acontece se um template usar `plano` ou `recursos`.
    return {
        "recursos": SimpleLazyObject(lambda: recursos_de(usuario)),
        "plano": SimpleLazyObject(lambda: plano_de(usuario)),
    }
