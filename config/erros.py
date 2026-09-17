# -*- coding: utf-8 -*-
"""Os handlers de erro do projeto — só para acrescentar `pagina_de_erro=True`.

`django.views.defaults.page_not_found` e `permission_denied` já encontram
`404.html`/`403.html` sozinhos, SEM handler nenhum registrado aqui: é o
comportamento padrão do Django quando os templates do projeto existem. O que
faltava não era a tela — era um jeito de `base.html` SABER que é uma tela de
erro.

A tentativa óbvia era `request.resolver_match`: ele é `None` desde
`HttpRequest.__init__` e só ganha valor quando `resolve()` acha uma rota —
mas isso só cobre a URL QUE NÃO RESOLVE. Um `Http404` levantado DENTRO de uma
view (`get_object_or_404` em `/treino/exercicio/999999/`, por exemplo) roda
DEPOIS da resolução: `resolver_match` já está preenchido quando o handler
entra em ação, e `base.html` continuava desenhando o aviso de conquista por
cima do cartão "Esta página não existe" — sem ninguém para fechá-lo (achado
da revisão final de 16/09/2026, item F3).

Reimplementados linha a linha a partir do contrato de
`django.views.defaults.page_not_found`/`permission_denied` — e não só
decorados por cima — porque a única mudança real é UMA chave de contexto a
mais. Preservar `exception` e `request_path` (a página de 404 os usa) e o
`ERROR_PAGE_TEMPLATE` de escape (inatingível aqui, já que `404.html`/
`403.html` sempre existem no projeto, mas mantido para não divergir do
contrato documentado caso um dia um deles suma) evita reinventar o que já
funciona só para acrescentar um booleano.
"""
from urllib.parse import quote

from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.template import Context, Engine, TemplateDoesNotExist, loader
from django.views.decorators.csrf import requires_csrf_token
from django.views.defaults import (
    ERROR_403_TEMPLATE_NAME,
    ERROR_404_TEMPLATE_NAME,
    ERROR_PAGE_TEMPLATE,
)


@requires_csrf_token
def handler404(request, exception, template_name=ERROR_404_TEMPLATE_NAME):
    """O 404 do projeto: mesmo contrato do `page_not_found` padrão do
    Django, com `pagina_de_erro=True` a mais no contexto (ver docstring do
    módulo — é o que apaga o aviso de conquista desta tela)."""
    exception_repr = exception.__class__.__name__
    try:
        mensagem = exception.args[0]
    except (AttributeError, IndexError):
        pass
    else:
        if isinstance(mensagem, str):
            exception_repr = mensagem
    context = {
        "request_path": quote(request.path),
        "exception": exception_repr,
        "pagina_de_erro": True,
    }
    try:
        template = loader.get_template(template_name)
        corpo = template.render(context, request)
    except TemplateDoesNotExist:
        if template_name != ERROR_404_TEMPLATE_NAME:
            raise
        template = Engine().from_string(
            ERROR_PAGE_TEMPLATE
            % {
                "title": "Not Found",
                "details": "The requested resource was not found on this server.",
            },
        )
        corpo = template.render(Context(context))
    return HttpResponseNotFound(corpo)


@requires_csrf_token
def handler403(request, exception, template_name=ERROR_403_TEMPLATE_NAME):
    """O 403 do projeto: mesmo contrato do `permission_denied` padrão do
    Django, com `pagina_de_erro=True` a mais no contexto."""
    try:
        template = loader.get_template(template_name)
    except TemplateDoesNotExist:
        if template_name != ERROR_403_TEMPLATE_NAME:
            raise
        return HttpResponseForbidden(
            ERROR_PAGE_TEMPLATE % {"title": "403 Forbidden", "details": ""},
        )
    return HttpResponseForbidden(
        template.render(
            request=request,
            context={"exception": str(exception), "pagina_de_erro": True},
        )
    )
