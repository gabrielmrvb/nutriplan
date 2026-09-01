"""As duas páginas de texto legal, e o que separa rascunho de documento.

Uma Política de Privacidade que não diz quem responde pelos dados não é uma
política — é um texto sobre privacidade. E publicá-la como se fosse o documento
final do beta seria pedir consentimento apoiado numa informação que falta.

Por isso `LEGAL_PUBLICADO` existe. Enquanto o responsável e o contato não forem
preenchidos por ambiente, as páginas continuam acessíveis por URL direta — dá
para revisar o texto, e a suíte continua cobrindo o conteúdo —, mas elas dizem
na primeira linha que são rascunho, e o cadastro e o login não as linkam.

Nada aqui inventa CNPJ, endereço ou razão social. A ausência é declarada.
"""
from django.conf import settings
from django.views.generic import TemplateView


class PaginaLegal(TemplateView):
    """Base das duas páginas. Injeta o estado de publicação."""

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "legal_publicado": settings.LEGAL_PUBLICADO,
                "legal_responsavel": settings.LEGAL_RESPONSAVEL,
                "legal_contato": settings.LEGAL_CONTATO,
            }
        )
        return contexto


class Privacidade(PaginaLegal):
    template_name = "legal/privacidade.html"


class Termos(PaginaLegal):
    template_name = "legal/termos.html"
