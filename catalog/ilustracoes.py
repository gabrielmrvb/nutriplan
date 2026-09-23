# -*- coding: utf-8 -*-
"""A que FAMÍLIA de prato cada receita pertence — e por que não é uma foto.

A auditoria de 23/09/2026 disse o que faltava no card de refeição: "sem
imagem, o card continua parecendo texto". Uma foto por receita seria o ideal
e não é o que este ambiente consegue entregar com honestidade: 54 imagens
exigem curadoria (é a mesma pessoa? é o mesmo prato? a licença permite?) e
este ambiente não VÊ foto para conferir — foi exatamente por isso que a
expansão de exercícios de 10/09 voltou atrás (`CLAUDE.md`, "EXERCÍCIO ATIVO
TEM DEMONSTRAÇÃO").

A resposta é a que a própria auditoria abriu como aceitável: uma ILUSTRAÇÃO
POR FAMÍLIA. Onze desenhos próprios, em SVG, no sprite
`templates/partials/ilustracoes_de_receita.html` — sem licença de terceiro,
sem download, determinísticos, e com o peso contado por teste. Um cuscuz
parece um cuscuz, um prato feito parece um prato feito, e o card deixa de
ser uma lista de palavras.

A família é DADO do catálogo (`MealTemplate.ilustracao`), não uma conta feita
na hora de desenhar: quem cadastra uma receita nova decide a que família ela
pertence, e a decisão fica gravada. O que esta função faz é o PADRÃO para
quem não decidiu — o seed a chama quando `meal_templates.json` não traz a
chave `ilustracao`, do mesmo jeito que ele já assume `prep_minutes: 10`.

A regra é o NOME, e não os ingredientes, porque é o nome que descreve a
FORMA do prato: "Arroz com ovo mexido e farofa" e "Omelete de queijo com
arroz" têm quase os mesmos itens e chegam à mesa de jeitos diferentes.
"""

#: (trecho no nome em minúscula, família). A ORDEM IMPORTA: o primeiro que
#: casa vence, e é por isso que "tapioca" vem antes de "banana" — "Tapioca
#: com banana e amendoim" é uma tapioca, não uma fruta.
REGRAS = (
    ("cuscuz", "cuscuz"),
    ("mingau", "mingau"),
    ("vitamina", "vitamina"),
    ("tapioca", "tapioca"),
    ("iogurte", "iogurte"),
    ("macarrão", "macarrao"),
    ("omelete", "ovos"),
    ("ovos mexidos", "ovos"),
    ("sanduíche", "pao"),
    ("pão", "pao"),
    ("salada de", "salada"),
    # As frutas e o queijo de lanche: prato nenhum, comida na mão.
    ("banana com", "fruta"),
    ("mamão com", "fruta"),
    ("amendoim com", "fruta"),
    ("queijo minas com", "fruta"),
)

#: Quando nenhuma regra casa. "Prato" é o desenho mais genérico do conjunto —
#: um prato repartido — e é o que 18 das 54 receitas de fato são (arroz,
#: feijão e a proteína). Errar para cá devolve um desenho verdadeiro para
#: comida de prato e genérico para o resto; errar para um desenho específico
#: seria a tela afirmando uma forma que o prato não tem.
PADRAO = "prato"

#: As onze famílias, na ordem em que o sprite as desenha. É esta lista que o
#: campo do modelo usa como `choices` e que o teste do sprite cobra.
FAMILIAS = (
    ("cuscuz", "Cuscuz"),
    ("mingau", "Mingau"),
    ("ovos", "Ovos"),
    ("pao", "Pão e sanduíche"),
    ("tapioca", "Tapioca"),
    ("vitamina", "Vitamina"),
    ("prato", "Prato feito"),
    ("macarrao", "Macarrão"),
    ("iogurte", "Iogurte"),
    ("fruta", "Fruta"),
    ("salada", "Salada"),
)


def familia_de(nome: str) -> str:
    """A família de uma receita, pelo nome. Nunca devolve vazio."""
    minusculo = nome.lower()
    for trecho, familia in REGRAS:
        if trecho in minusculo:
            return familia
    return PADRAO
