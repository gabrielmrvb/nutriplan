"""O mapa das cinco áreas — a porta de primeiro nível que duas delas não têm.

POR QUE ELE EXISTE

A barra de baixo tem QUATRO itens e vai continuar tendo: medido a 320px, cinco
colunas deixam 51,8px úteis por item e "Hidratação" precisa de 60. Ela responde
FREQUÊNCIA — o que se toca todo dia. O mapa responde ESTRUTURA — de que o app é
feito.

E a estrutura estava mentindo em dois lugares: a tela de água acendia a aba
"Dieta" e a de corridas acendia "Treino", que é exatamente o que a docstring de
`accounts.models.Pilar` diz que o produto NÃO é. Hidratação não é subfunção de
Dieta; Corrida não é subfunção de Treino.

POR QUE ELE NÃO REORDENA

A área principal ganha um SELO, e não o primeiro lugar. Um mapa que muda de
ordem por pessoa é um mapa pior: ele existe para mostrar de que o app é feito,
e isso não muda de pessoa para pessoa. A personalização de ORDEM é da tela
Hoje, onde a pergunta é outra — "o que eu faço agora?" — e lá a prioridade é
mais um sinal, nunca a regra.
"""
from django import template

from accounts.models import Pilar

register = template.Library()

#: pilar -> (nome da rota, valor de `nav`)
#:
#: `nav` é o que `base.html` compara para acender o destino da vez. Os dois
#: valores novos — `running` e `hydration` — não acendem aba nenhuma da barra
#: de baixo, e isso é melhor que acender a errada.
#:
#: Um dicionário completo e não um `.get()` com padrão: pilar sem destino tem
#: de estourar aqui, na primeira renderização, e não sumir do mapa em silêncio.
DESTINO_DO_PILAR = {
    Pilar.DIETA: ("plans:alimentacao", "food"),
    Pilar.TREINO: ("workouts:routine", "workout"),
    Pilar.CORRIDA: ("workouts:corridas", "running"),
    Pilar.HIDRATACAO: ("plans:hydration", "hydration"),
    Pilar.PROGRESSO: ("plans:history", "history"),
}


#: AS CINCO ABAS DA NAVEGAÇÃO PRINCIPAL (22/09/2026), e o único lugar em que
#: elas são escritas.
#:
#: Eram QUATRO, e a primeira era o defeito central que o redesenho veio
#: corrigir: ela se chamava "Alimentação", tinha ícone de garfo e faca e
#: apontava para `/`, uma tela chamada "Hoje" que era a tela de dieta. Não
#: existia tela de Alimentação; existia a dieta fazendo as vezes de inicial.
#:
#: Agora são cinco, e a conta de largura foi REFEITA a 320px (a medição
#: antiga — "cinco colunas deixam 51,8px e Hidratação precisa de 60" — valia
#: para a barra de um rótulo por linha; o rótulo agora pode quebrar em duas
#: linhas, que é o que faz "Alimentação" caber).
#:
#: `navs` são os valores de `nav` que ACENDEM a aba. Hidratação acende Hoje
#: (o cartão de água mora lá); Corrida e Perfil acendem Mais (é de lá que se
#: chega a eles no celular). Acender a aba de onde se chegou é melhor que não
#: acender nada — e muito melhor que acender a errada, que era o defeito de
#: antes de `Pilar` existir.
ABAS = (
    {
        "chave": "hoje", "rotulo": "Hoje", "rota": "plans:today", "icone": "icone-sol",
        "navs": ("today", "hydration"),
    },
    {
        "chave": "alimentacao", "rotulo": "Alimentação", "rota": "plans:alimentacao", "icone": "icone-talher",
        "navs": ("food",),
    },
    {
        "chave": "treino", "rotulo": "Treino", "rota": "workouts:routine", "icone": "icone-halter",
        "navs": ("workout",),
    },
    {
        "chave": "progresso", "rotulo": "Progresso", "rota": "plans:history", "icone": "icone-barras",
        "navs": ("history",),
    },
    {
        "chave": "mais", "rotulo": "Mais", "rota": "areas", "icone": "icone-grade",
        "navs": ("areas", "profile", "running"),
    },
)


@register.inclusion_tag("partials/abas.html", takes_context=True)
def abas(context, onde="tabbar"):
    """As cinco abas, para as DUAS barras — a de baixo no celular e a de cima
    no desktop.

    Uma tag e não dois blocos de HTML: as duas barras precisam concordar
    sempre (acima de 60rem a de baixo some e quem navega é a de cima), e
    quando eram dois blocos copiados o contrato "renomear as duas juntas"
    era um comentário pedindo por favor. Agora é a mesma lista.
    """
    atual = context.get("nav")
    itens = []
    for aba in ABAS:
        endereco = endereco_da_area(aba["rota"])
        itens.append({**aba, "endereco": endereco, "ativa": atual in aba["navs"]})
    return {"abas": itens, "onde": onde}


#: O que a barra de baixo já alcança direto. UX-01: Áreas NÃO repete isso.
#:
#: A regra veio do dono, usando o app: "se uma funcionalidade já possui acesso
#: direto pela navegação principal, ela não precisa aparecer novamente dentro
#: de Áreas". Um menu que repete a barra é o segundo menu paralelo que UX-01
#: existe para acabar.
#:
#: A lista é de PILARES e não de rotas porque é por pilar que o mapa é montado.
PILARES_NA_BARRA = (Pilar.DIETA, Pilar.TREINO, Pilar.PROGRESSO)


def areas_fora_da_barra(request, usuario, nav, perfil=None):
    """Os pilares que a barra de baixo NÃO alcança direto: Corrida e Hidratação.

    Eram justamente os dois sem porta de primeiro nível — o motivo de o mapa
    ter nascido. Com Áreas fixa na barra, eles passam a estar a um toque de um
    destino permanente, em vez de atrás de um `<details>` no canto de cima que
    a pessoa precisava descobrir.
    """
    from accounts.templatetags.escolhas import DETALHES

    # `perfil` explícito quando quem chama já o tem: a tela de Áreas passa o
    # que o `dispatch` buscou, e sem isso a mesma tabela é lida duas vezes no
    # mesmo pedido.
    if perfil is None and usuario is not None:
        perfil = getattr(usuario, "profile", None)
    principal = getattr(perfil, "prioridade", "") or ""
    aqui = getattr(request, "path", "")

    fora = []
    for pilar in Pilar:
        if pilar in PILARES_NA_BARRA:
            continue
        rota, chave = DESTINO_DO_PILAR[pilar]
        _icone, titulo, apoio = DETALHES[pilar.value][:3]
        endereco = endereco_da_area(rota)
        fora.append(
            {
                "valor": pilar.value,
                "endereco": endereco,
                "titulo": titulo,
                "apoio": apoio,
                "aqui": bool(endereco) and endereco == aqui,
                "na_secao": chave == nav,
                "principal": pilar.value == principal,
            }
        )
    return fora


@register.inclusion_tag("partials/mapa_de_areas.html", takes_context=True)
def mapa_de_areas(context):
    """As cinco áreas, na ordem canônica de `Pilar` — a mesma do onboarding.

    Uma `inclusion_tag` e não um context processor: o mapa é renderizado numa
    tela só, `base.html`, e um processor cobraria a montagem de toda resposta
    do projeto, inclusive das que não têm barra nenhuma.
    """
    from django.urls import reverse

    from accounts.templatetags.escolhas import DETALHES

    # Segunda camada da mesma guarda do `base.html`: o selo de área
    # principal é IDENTIDADE, e o shell de offline é pré-cacheado e servido a
    # quem pegar o aparelho depois. `base.html` já não chama esta tag lá; se
    # alguém tirar aquele `{% if %}`, o selo continua sem sair.
    usuario = None if context.get("shell_offline") else context.get("user")
    perfil = getattr(usuario, "profile", None) if usuario else None
    principal = getattr(perfil, "prioridade", "") or ""
    atual = context.get("nav")

    pedido = context.get("request")
    aqui = getattr(pedido, "path", "")

    areas = []
    for pilar in Pilar:
        rota, chave = DESTINO_DO_PILAR[pilar]
        icone, titulo, apoio = DETALHES[pilar.value][:3]
        endereco = endereco_da_area(rota)
        areas.append(
            {
                "valor": pilar.value,
                "endereco": endereco,
                "icone": icone,
                "titulo": titulo,
                "apoio": apoio,
                # DUAS coisas diferentes, e juntá-las fazia o mapa mentir.
                #
                # `aqui` é a página EXATA. `na_secao` é "você está dentro desta
                # área" — a lista de compras declara `nav = "today"`, e com uma
                # marca só o mapa anunciava `aria-current="page"` em
                # "Alimentação" apontando para `/`, que não é a página aberta.
                "aqui": bool(endereco) and endereco == aqui,
                "na_secao": chave == atual,
                "principal": pilar.value == principal,
            }
        )
    return {"areas": areas, "request": pedido}


def endereco_da_area(rota):
    """O endereço da área, já com o prefixo do demo quando houver.

    `reverse()` sozinho não basta, e o motivo está escrito em `demo/views.py`:
    `plans:today` mora na RAIZ da aplicação, então sob `set_script_prefix`
    ele reverte para `/demo/` — que não é a tela Hoje, é a capa do demo. O
    mapa mandava quem estava avaliando o produto para a página de marketing,
    e ainda marcava "você está aqui" ao fazê-lo.

    A tradução sai de `demo.middleware.APELIDOS`, invertido, e não de um
    terceiro literal escrito à mão: já existem dois (`base.html` e
    `demo/views.py`), e o terceiro é o que envelhece sozinho.
    """
    from django.urls import reverse

    from demo import middleware as demo

    endereco = reverse(rota)
    raiz_do_demo = demo.PREFIXO + "/"
    if endereco == raiz_do_demo:
        de_volta = {destino: apelido for apelido, destino in demo.APELIDOS.items()}
        return demo.PREFIXO + de_volta["/"]
    return endereco
