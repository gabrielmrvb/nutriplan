"""A porta de entrada do Django Admin passa pelo login do NutriPlan.

O primeiro operador administrativo entra por Google e NÃO tem senha utilizável
— `has_usable_password()` é False, confirmado no banco de produção. O formulário
de login do Django Admin autentica por senha, e a recuperação de senha não
atende essa conta de propósito: o `get_users()` do Django filtra por senha
utilizável, o que é a decisão certa e não vai mudar por causa do Admin.

Então o Admin deixa de ter formulário próprio de login e reaproveita o do app,
que já faz Google E senha, já tem limite de abuso, e já é testado. A separação
que isso preserva:

    o login do app prova QUEM é a pessoa;
    o AdminSite decide O QUE ela pode ver.

Nada de autorização muda. `admin_view` continua exigindo `is_active` e
`is_staff` em toda view, e as permissões por model continuam valendo. O que sai
é uma segunda tela de login, mais fraca, para um usuário que não consegue usá-la.

A integração é uma rota, e não middleware: um middleware que intercepta
qualquer URL com `/admin/` age no projeto inteiro para resolver um problema de
uma tela só. Aqui `config/urls.py` registra este caminho ANTES de
`admin.site.urls`, e como `reverse("admin:login")` devolve o mesmo `/admin/login/`,
o redirecionamento interno do Admin cai exatamente aqui.
"""
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def _destino_seguro(request) -> str:
    """Para onde voltar depois de autenticar, sem virar redirecionamento aberto.

    `next` vem da URL e é controlado por quem monta o link. Sem validação, um
    `?next=https://site-falso/` transformaria o endereço do NutriPlan numa
    rampa: a pessoa clica num link do domínio real, autentica de verdade, e
    termina num site de terceiros logo depois do login — que é o momento em que
    ela está mais disposta a digitar credencial de novo.

    `url_has_allowed_host_and_scheme` é o utilitário do próprio Django, e ele
    cobre os casos que uma checagem escrita à mão erra: `//outro-site.com` (sem
    esquema, que o navegador trata como absoluto) e esquemas como `javascript:`.
    """
    destino = request.GET.get("next") or ""
    if destino and url_has_allowed_host_and_scheme(
        url=destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino
    return reverse("admin:index")


def entrada_do_admin(request):
    """Manda para o login do app, ou recusa quem já está dentro e não é staff."""
    destino = _destino_seguro(request)

    if request.user.is_authenticated:
        if request.user.is_active and request.user.is_staff:
            return HttpResponseRedirect(destino)
        # Quem já está autenticado e não é staff NÃO volta para o login.
        #
        # Mandar de volta seria criar um laço: o login veria a sessão válida,
        # devolveria para `next=/admin/`, o Admin recusaria de novo, e a pessoa
        # ficaria presa entre duas telas sem nenhuma explicar o que houve.
        raise PermissionDenied(
            "Esta conta não tem acesso administrativo ao NutriPlan."
        )

    return redirect_to_login(destino, reverse("accounts:login"))
