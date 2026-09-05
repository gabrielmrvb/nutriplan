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
    Pilar.DIETA: ("plans:today", "today"),
    Pilar.TREINO: ("workouts:routine", "workout"),
    Pilar.CORRIDA: ("workouts:corridas", "running"),
    Pilar.HIDRATACAO: ("plans:hydration", "hydration"),
    Pilar.PROGRESSO: ("plans:history", "history"),
}


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
        endereco = _endereco(rota)
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


def _endereco(rota):
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
