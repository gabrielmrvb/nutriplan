"""As duas páginas de texto legal, e o que separa rascunho de documento.

Uma Política de Privacidade que não diz quem responde pelos dados não é uma
política — é um texto sobre privacidade. E publicá-la como se fosse o documento
final do beta seria pedir consentimento apoiado numa informação que falta.

Por isso `LEGAL_PUBLICADO` existe. Enquanto o responsável e o contato não forem
preenchidos por ambiente, as páginas continuam acessíveis por URL direta — dá
para revisar o texto, e a suíte continua cobrindo o conteúdo —, mas elas dizem
na primeira linha que são rascunho, e o cadastro e o login não as linkam.

Nada aqui inventa CNPJ, endereço ou razão social. A ausência é declarada.

A VERSÃO e a data que as duas páginas mostram em "Última atualização" não
são mais escritas à mão no template: as duas vêm de
`accounts.consentimento.VERSAO_DOS_LEGAIS`, a mesma constante que decide
quando o app pede consentimento de novo. Escrevê-la duas vezes — aqui e no
template — é o defeito que este módulo existe para não deixar acontecer: a
data do texto e a data do consentimento divergindo sem ninguém perceber.
"""
from datetime import date

from django.conf import settings
from django.views.generic import TemplateView

from accounts.consentimento import VERSAO_DOS_LEGAIS

_MESES_POR_EXTENSO = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def data_dos_legais_por_extenso():
    """"2026-09-21" -> "21 de setembro de 2026", sem depender de locale."""
    dia = date.fromisoformat(VERSAO_DOS_LEGAIS)
    return "%d de %s de %d" % (dia.day, _MESES_POR_EXTENSO[dia.month], dia.year)


class PaginaLegal(TemplateView):
    """Base das duas páginas. Injeta o estado de publicação."""

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "legal_publicado": settings.LEGAL_PUBLICADO,
                "legal_responsavel": settings.LEGAL_RESPONSAVEL,
                "legal_contato": settings.LEGAL_CONTATO,
                "versao_dos_legais": VERSAO_DOS_LEGAIS,
                "data_dos_legais": data_dos_legais_por_extenso(),
            }
        )
        return contexto


class Privacidade(PaginaLegal):
    template_name = "legal/privacidade.html"


class Termos(PaginaLegal):
    template_name = "legal/termos.html"
