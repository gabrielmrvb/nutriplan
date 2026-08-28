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
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.urls import get_script_prefix, set_script_prefix

#: O login do usuário de demonstração. Não é e-mail de ninguém: o domínio
#: `.invalid` é reservado por RFC justamente para nunca resolver.
DEMO_EMAIL = "carlos.demo@nutriplan.invalid"

#: A SEGUNDA persona, e ela existe por um motivo que o Carlos nao consegue
#: cobrir: o primeiro uso.
#:
#: O Carlos tem plano, ficha, doze semanas de peso e o onboarding concluido —
#: e e exatamente por isso que ele nao serve para mostrar o onboarding. Quem
#: ja terminou o wizard nao consegue ve-lo como quem chega: `is_editing` liga,
#: os textos mudam de "vamos calcular" para "salvar", e o fluxo que a pessoa
#: veria seria o de EDICAO, nao o de estreia.
#:
#: A Ana fica parada no onboarding para sempre. Nao ha POST no demo, entao ela
#: nunca avanca — o estado dela e estavel por construcao.
DEMO_ONBOARDING_EMAIL = "ana.demo@nutriplan.invalid"

PREFIXO = "/demo"

#: O prefixo das rotas do wizard, no app real. Quem pede uma delas dentro do
#: demo esta pedindo a experiencia de estreia, e por isso ve a Ana.
ONBOARDING = "/conta/onboarding/"

#: O painel do dia mora na RAIZ da aplicação (`/`), e a raiz do demo é a capa.
#: Sem este apelido os dois disputariam `/demo/` e o link do painel viraria um
#: laço de volta para a capa.
#:
#: Um apelido, e só um: cada rota inventada aqui é uma rota que existe no demo
#: e não existe no app, e é assim que um demo começa a divergir do produto.
#: `/comecar/` e a porta da estreia. Ela aponta para o PASSO 1 e nao para
#: `/conta/onboarding/`, que redirecionaria para o passo pendente — e o
#: pendente da Ana e o ultimo. Quem chega para avaliar o primeiro uso quer
#: comecar do comeco.
#:
#: As duas grafias porque `APPEND_SLASH` age depois deste middleware: sem a
#: chave sem barra, `/demo/comecar` cairia no resolvedor antes de virar
#: `/demo/comecar/`.
APELIDOS = {
    "/hoje/": "/",
    "/comecar/": ONBOARDING + "1/",
    "/comecar": ONBOARDING + "1/",
}

#: Métodos que só leem. Todo o resto é recusado antes de chegar na view.
SEGUROS = frozenset(("GET", "HEAD", "OPTIONS"))


def usuario_demo():
    """O usuário fictício, ou `None` se o seed ainda não rodou."""
    return get_user_model().objects.filter(email=DEMO_EMAIL).first()


def usuario_onboarding():
    """A persona parada no wizard, ou `None` se o seed ainda não rodou."""
    return get_user_model().objects.filter(email=DEMO_ONBOARDING_EMAIL).first()


def _quem_ve(resto: str):
    """Qual das duas personas responde por este caminho.

    A escolha é pelo CAMINHO e não por sessão, porque o demo não tem sessão:
    cada pedido decide sozinho. É também o que garante o isolamento nos dois
    sentidos — a Ana nunca aparece fora do wizard, e o Carlos nunca entra
    nele, onde ele mostraria a tela de edição em vez da de estreia.
    """
    if resto.startswith(ONBOARDING):
        return usuario_onboarding()
    return usuario_demo()


class DemoMiddleware:
    """Monta o app sob `/demo/` autenticado como o usuário fictício."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        caminho = request.path_info
        if caminho != PREFIXO and not caminho.startswith(PREFIXO + "/"):
            return self.get_response(request)

        # O caminho pedido, ANTES do apelido. A distinção importa: o apelido
        # `/hoje/` aponta para `/`, e `/` é a capa — resolver o apelido antes
        # de escolher a tela faria `/demo/hoje/` servir a capa em vez do painel
        # do dia. Foi o que aconteceu, e ficou em produção: as duas respondiam
        # 200 com o mesmo HTML, e o teste só olhava o código de resposta.
        pedido = caminho[len(PREFIXO):] or "/"
        resto = APELIDOS.get(pedido, pedido)

        usuario = _quem_ve(resto)
        if usuario is None:
            return render(request, "demo/indisponivel.html", status=503)

        if request.method not in SEGUROS:
            # Nada que escreve chega na view. É a única garantia que não
            # depende de eu ter lembrado de proteger cada uma delas — e o
            # requisito é que o demo NUNCA altere dado nenhum.
            return render(request, "demo/acao_desativada.html", status=200)

        request.demo = True
        request.user = usuario
        # Só o Carlos tem dia para manter vivo. A Ana não tem plano — a função
        # sairia na primeira guarda de qualquer jeito, e chamá-la aqui só
        # gastaria uma consulta por tela do wizard.
        if usuario.email == DEMO_EMAIL:
            _manter_o_dia_vivo(usuario)
        # O `_cached_user` do middleware de autenticação vem antes deste e já
        # deixou o anônimo em cache; sem limpar, `request.user` volta a ser
        # anônimo na primeira vez que alguém tocar no atributo lá dentro.
        request._cached_user = usuario

        prefixo_original = get_script_prefix()
        try:
            set_script_prefix(PREFIXO + "/")
            request.path_info = resto
            request.path = PREFIXO + resto

            # A capa e a página "sobre" são as únicas telas que o demo tem e o
            # app não. Elas são chamadas DIRETO, sem passar pelo resolvedor de
            # URL: com o prefixo ligado, `/` resolveria o painel do dia.
            #
            # E elas precisam do prefixo ligado — foi o defeito da primeira
            # versão, que as deixava passar por fora. Sem ele a capa
            # renderizava com visitante anônimo, e a barra de cima oferecia
            # "Entrar" e "Criar conta": duas saídas do demo direto para a tela
            # de login, que é o beco sem saída que o demo existe para não ter.
            propria = PROPRIAS.get(pedido)
            if propria is not None:
                resposta = propria(request)
                # `TemplateResponse` é preguiçoso: quem o renderiza é o
                # manipulador do Django, DEPOIS de toda a cadeia de middleware
                # — ou seja, depois do `finally` abaixo devolver o prefixo ao
                # que era. O template sairia com `/treino/` no lugar de
                # `/demo/treino/`, e a navegacão da capa voltaria a apontar
                # para fora do demo.
                #
                # As telas que passam pelo resolvedor não têm esse problema: o
                # `_get_response` do Django renderiza a resposta ainda dentro
                # do `get_response(request)`, com o prefixo ligado.
                if hasattr(resposta, "render") and callable(resposta.render):
                    resposta = resposta.render()
                return resposta

            return self.get_response(request)
        finally:
            set_script_prefix(prefixo_original)


def _capa(request):
    from .views import DemoHomeView

    return DemoHomeView.as_view()(request)


def _sobre(request):
    from .views import DemoSobreView

    return DemoSobreView.as_view()(request)


#: As duas telas que existem no demo e não no app.
#:
#: O `import` fica adiado dentro de cada função porque `demo.views` importa
#: deste módulo — no topo, os dois se importariam em círculo.
PROPRIAS = {"/": _capa, "/sobre/": _sobre}


def _manter_o_dia_vivo(usuario):
    """Recria o dia do Carlos quando a data vira.

    O seed escreve "hoje" no dia em que roda, e o Render só roda o seed em
    deploy. Um dia depois, "hoje" é ontem: o painel abre com o anel em zero,
    nenhuma refeição marcada e nenhuma água — e quem chegasse ao demo veria um
    app que parece nunca ter sido usado.

    Isto é uma ESCRITA num pedido de leitura, que é justamente o que o
    middleware recusa logo acima. A diferença que a torna aceitável é o
    alcance: ela toca só o usuário fictício, só o dia de hoje, e só quando não
    há nada. Nenhum caminho aqui alcança dado de pessoa real — a consulta é
    fechada em `usuario`, que é sempre o Carlos.

    A alternativa seria um agendamento diário, e o plano gratuito do Render não
    tem nem cron nem shell.
    """
    from django.utils import timezone

    from plans.models import MealLog

    hoje = timezone.localdate()
    if MealLog.objects.filter(user=usuario, date=hoje).exists():
        return

    plano = usuario.plans.filter(is_active=True).first()
    if plano is None:
        return

    from django.core.management import call_command

    # `--somente-o-dia` refaz as refeições, a água e as CARGAS de hoje. O seed
    # inteiro remontaria plano e ficha a cada virada de data, e remontar plano
    # é caro.
    call_command("seed_demo", somente_o_dia=True, verbosity=0)
