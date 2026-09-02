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


class PainelDeGestaoMixin(AccessMixin):
    """Anônimo vai para o login; autenticado sem permissão leva 403.

    A diferença importa: mandar quem já está logado para a tela de login
    produz um laço — ela entra, volta para cá, é recusada de novo, e nada na
    tela explica que o problema é permissão e não sessão.
    """

    permissao = "accounts.ver_painel_de_gestao"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_perm(self.permissao):
            self.raise_exception = True
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)
