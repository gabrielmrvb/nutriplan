# -*- coding: utf-8 -*-
"""O que um buscador vê do NutriPlan — e SÓ o que deve ver.

Sete rotas são públicas de verdade: a landing, a capa e o "sobre" do demo, a
política e os termos, criar conta e entrar. Todo o resto é instância — a
tela do app exige sessão, a tela interna do demo mostra o Carlos, o shell
offline é o que o service worker serve sem rede. Indexar instância é o erro
que este módulo fecha: antes dele, `/demo/treino/` podia entrar no índice
como se fosse "o treino do NutriPlan", com a ficha de uma pessoa fictícia.

Duas peças:

* `ROTAS_PUBLICAS` é a lista fechada, e é ela que `sitemap.xml` publica e
  que `config/test_seo.py` cobra ser indexável (descrição própria,
  `canonical`, Open Graph) e abrir com 200 sem login. Rota nova pública
  entra AQUI e declara o bloco `seo` no template; a que não entrar fica
  `noindex` por padrão, no `base.html` — esquecer é ficar fora do índice,
  nunca o contrário;
* `robots.txt` diz onde o rastreador não perde tempo e onde está o sitemap.
  Ele NÃO lista o admin: a rota vai deixar de ser óbvia (segurança,
  21/09/2026), e um `Disallow` a anunciaria para quem procura.

Sem `django.contrib.sitemaps` de propósito: são sete URLs estáticas, e a
biblioteca traria `sites` e uma configuração a mais para gerar o mesmo XML.
"""
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import escape

#: A frase genérica do `base.html`, que vale para o que não é público.
DESCRICAO_PADRAO = "Sua dieta calculada, o cardápio do dia e o treino da semana."

#: As rotas que um buscador pode indexar — o sitemap inteiro.
ROTAS_PUBLICAS = (
    "/",
    "/demo/",
    "/demo/sobre/",
    "/privacidade/",
    "/termos/",
    "/conta/cadastro/",
    "/conta/entrar/",
)

#: Onde o rastreador não tem o que fazer: painel de gestão, sondas, tarefas
#: e o shell offline. Tela do app não precisa estar aqui — exige sessão.
NAO_RASTREAR = ("/gestao/", "/saude/", "/tarefas/", "/offline/")


def _raiz(request):
    return "%s://%s" % (request.scheme, request.get_host())


def robots(request):
    linhas = ["User-agent: *"]
    linhas += ["Disallow: %s" % caminho for caminho in NAO_RASTREAR]
    linhas.append("Sitemap: %s%s" % (_raiz(request), reverse("sitemap")))
    return HttpResponse("\n".join(linhas) + "\n", content_type="text/plain; charset=utf-8")


def sitemap(request):
    raiz = _raiz(request)
    urls = "".join("<url><loc>%s</loc></url>" % escape(raiz + rota) for rota in ROTAS_PUBLICAS)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % urls
    )
    return HttpResponse(xml, content_type="application/xml; charset=utf-8")
