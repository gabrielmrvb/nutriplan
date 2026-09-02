"""Quem entra no painel de gestão.

`is_staff` NÃO é a chave. Staff responde "esta pessoa entra no Django Admin",
que é uma pergunta sobre manutenção de dado. O painel de gestão responde
outra — "como o produto está indo" — e as duas não precisam andar juntas: dá
para querer alguém acompanhando números sem dar acesso à tabela de usuários, e
dá para querer o contrário.

Permissão própria, então. E o `has_perm` é a única checagem: um `and
is_staff` amarraria a autorização a um flag que existe por outro motivo, e no
dia em que alguém quisesse separar as duas coisas descobriria que não dá.
"""
from django.contrib.auth.mixins import AccessMixin
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache


class PainelDeGestaoMixin(AccessMixin):
    """Anônimo vai para o login; autenticado sem permissão leva 403.

    A diferença importa: mandar quem já está logado para a tela de login
    produz um laço — ela entra, volta para cá, é recusada de novo, e nada na
    tela explica que o problema é permissão e não sessão.
    """

    permissao = "accounts.ver_painel_de_gestao"

    #: `no-store` explícito, como o Django Admin já faz.
    #:
    #: Medido em produção: `/admin/accounts/user/` respondia
    #: `no-cache, no-store, must-revalidate, private`, e `/gestao/` não
    #: respondia diretiva nenhuma. As duas mostram dado de OUTRAS pessoas e
    #: nenhuma precisa funcionar sem rede.
    #:
    #: `Vary: Cookie` já impedia um cache compartilhado de servir a página de
    #: uma conta para outra — mas depender de cache heurístico para decidir
    #: sobre a lista de e-mails de todo mundo é mais fraco do que dizer.
    #:
    #: Isto NÃO se aplica às telas do app: lá o cache é o que faz a dieta
    #: abrir no metrô, o dado é da própria pessoa, e a privacidade entre
    #: contas é resolvida pela limpeza no logout.
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_perm(self.permissao):
            self.raise_exception = True
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)
