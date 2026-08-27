"""O modo demo: o app inteiro, sem login, sobre dados fictícios.

A ideia central é não ter um app paralelo. Uma segunda cópia das telas nasce
igual e diverge na primeira semana — o demo passa a mostrar uma versão do
NutriPlan que não existe mais, que é pior do que não ter demo.

Então o que este middleware faz é montar a MESMA aplicação sob `/demo/`:

  1. tira o prefixo de `path_info`, e o resolvedor de URL do Django encontra
     a rota real (`/demo/treino/` resolve `workouts:routine`);
  2. chama `set_script_prefix("/demo/")`, e aí todo `reverse()` da renderização
     devolve endereço com o prefixo de volta — a barra de abas, os formulários
     e os links do template real apontam para dentro do demo sozinhos, sem uma
     linha de template duplicada;
  3. troca `request.user` pelo usuário fictício.

O passo 2 é o que faz a coisa toda funcionar. Sem ele, a navegação de dentro
do demo mandaria a pessoa para `/treino/`, que exige login — exatamente o beco
sem saída que o demo existe para não ter.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.urls import set_script_prefix

#: O login do usuário de demonstração. Não é e-mail de ninguém: o domínio
#: `.invalid` é reservado por RFC justamente para nunca resolver.
DEMO_EMAIL = "carlos.demo@nutriplan.invalid"

PREFIXO = "/demo"

#: O painel do dia mora na RAIZ da aplicação (`/`), e a raiz do demo é a capa.
#: Sem este apelido os dois disputariam `/demo/` e o link do painel viraria um
#: laço de volta para a capa.
#:
#: Um apelido, e só um: cada rota inventada aqui é uma rota que existe no demo
#: e não existe no app, e é assim que um demo começa a divergir do produto.
APELIDOS = {"/hoje/": "/"}

#: Métodos que só leem. Todo o resto é recusado antes de chegar na view.
SEGUROS = frozenset(("GET", "HEAD", "OPTIONS"))


def usuario_demo():
    """O usuário fictício, ou `None` se o seed ainda não rodou."""
    return get_user_model().objects.filter(email=DEMO_EMAIL).first()


class DemoMiddleware:
    """Monta o app sob `/demo/` autenticado como o usuário fictício."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        caminho = request.path_info
        if caminho != PREFIXO and not caminho.startswith(PREFIXO + "/"):
            return self.get_response(request)

        resto = caminho[len(PREFIXO):] or "/"

        # As rotas do próprio demo — a capa e a página "sobre" — são as únicas
        # que não existem na aplicação real, e passam direto.
        if resto in ("/", "/sobre/"):
            request.demo = True
            return self.get_response(request)

        resto = APELIDOS.get(resto, resto)

        usuario = usuario_demo()
        if usuario is None:
            return render(request, "demo/indisponivel.html", status=503)

        if request.method not in SEGUROS:
            # Nada que escreve chega na view. É a única garantia que não
            # depende de eu ter lembrado de proteger cada uma delas — e o
            # requisito é que o demo NUNCA altere dado nenhum.
            return render(request, "demo/acao_desativada.html", status=200)

        request.demo = True
        request.user = usuario
        # O `_cached_user` do middleware de autenticação vem antes deste e já
        # deixou o anônimo em cache; sem limpar, `request.user` volta a ser
        # anônimo na primeira vez que alguém tocar no atributo lá dentro.
        request._cached_user = usuario

        prefixo_original = None
        try:
            from django.urls import get_script_prefix

            prefixo_original = get_script_prefix()
            set_script_prefix(PREFIXO + "/")
            request.path_info = resto
            request.path = PREFIXO + resto
            return self.get_response(request)
        finally:
            if prefixo_original is not None:
                set_script_prefix(prefixo_original)
