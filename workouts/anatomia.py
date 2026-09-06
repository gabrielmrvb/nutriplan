# -*- coding: utf-8 -*-
"""Onde cada grupo muscular aparece no mapa do corpo.

Este módulo existe para responder DUAS perguntas, e as duas com dado:

1. **em que vista um grupo é visível?** — o dorsal só existe de costas, o
   peito só de frente, o trapézio nos dois. É o que permite abrir o mapa já na
   vista que informa, em vez de deixar a pessoa descobrir sozinha que precisa
   virar o boneco. (Esta frase já usou o trapézio como exemplo de "só de
   costas", contradizendo a tabela quinze linhas abaixo. A correção foi feita
   no comentário do SVG e não aqui — que é justamente o arquivo que alguém lê
   antes de mexer na tabela.)
2. **algum grupo ficou sem desenho?** — um `MuscleGroup` novo sem região no
   SVG apagaria a informação em silêncio, e `test_mapa_muscular.py` reprova
   quando isso acontece.

NÃO É UMA SEGUNDA TAXONOMIA. As chaves são os valores de `MuscleGroup`, e um
grupo que não estiver lá é erro de cobertura, não um músculo novo.

E não é uma segunda cópia do desenho: as regiões de verdade vivem no SVG, em
`templates/partials/mapa_muscular.html`, marcadas com `data-grupo`. O que mora
aqui é só EM QUE VISTA cada grupo aparece — o mínimo que o Python precisa
saber para escolher a vista inicial. Um teste compara os dois lados, para que
desenhar uma região nova e esquecer esta tabela (ou o contrário) fique
vermelho.
"""
from .models import MuscleGroup

FRENTE = "frente"
COSTAS = "costas"

#: grupo -> as vistas em que ele tem região desenhada.
#:
#: A ordem dentro da tupla é a de PREFERÊNCIA: para um grupo que aparece nas
#: duas, a primeira é a vista em que ele se lê melhor. O ombro é o caso — ele
#: tem massa dos dois lados, e o deltoide anterior é o que a maioria dos
#: exercícios de ombro trabalha.
VISTAS_POR_GRUPO = {
    MuscleGroup.CHEST: (FRENTE,),
    MuscleGroup.BACK: (COSTAS,),
    MuscleGroup.QUADS: (FRENTE,),
    MuscleGroup.HAMSTRINGS: (COSTAS,),
    MuscleGroup.CALVES: (COSTAS,),
    MuscleGroup.SHOULDERS: (FRENTE, COSTAS),
    MuscleGroup.BICEPS: (FRENTE,),
    MuscleGroup.TRICEPS: (COSTAS,),
    MuscleGroup.CORE: (FRENTE,),
    MuscleGroup.TRAPS: (COSTAS, FRENTE),
    MuscleGroup.FOREARMS: (FRENTE, COSTAS),
}


def vistas_do_grupo(grupo) -> tuple:
    """As vistas de um grupo, ou vazio se ele não tem desenho.

    Vazio é resposta legítima e não exceção: um grupo novo entra no banco antes
    de alguém desenhar a região dele, e a tela tem de continuar de pé — o texto
    "Principal / Também trabalha" já diz tudo que importa. O que não pode é
    isso passar despercebido, e é o teste de cobertura que impede.
    """
    return VISTAS_POR_GRUPO.get(grupo, ())


def vista_preferida(exercise) -> str:
    """A vista que mostra mais do que ESTE exercício trabalha.

    A regra é curta de propósito, e a ordem dela é a ordem da importância:

    1. **o principal manda.** Puxada abre de costas, supino abre de frente. É o
       músculo que recebe o maior estímulo, e é o que a pessoa veio ver;
    2. **empate se resolve pelos auxiliares.** Um principal que aparece nas
       duas vistas — ombro, antebraço, trapézio — deixa a decisão para onde
       está o resto do trabalho;
    3. **e o desempate final é a frente**, porque é a vista que a maioria dos
       exercícios usa e a que as pessoas reconhecem primeiro.

    Nada aqui olha o NOME do exercício. Um `if exercise == "supino"` é
    exatamente o que esta função existe para não precisar existir.
    """
    do_principal = vistas_do_grupo(exercise.muscle_group)
    if len(do_principal) == 1:
        return do_principal[0]

    # Principal em duas vistas (ou em nenhuma): quem decide são os auxiliares.
    placar = {FRENTE: 0, COSTAS: 0}
    for auxiliar in exercise.secondary_muscles or []:
        for vista in vistas_do_grupo(auxiliar):
            placar[vista] += 1

    if placar[COSTAS] > placar[FRENTE]:
        return COSTAS
    if placar[FRENTE] > placar[COSTAS]:
        return FRENTE

    # Empate real, ou nenhum auxiliar: a preferência declarada do grupo, e a
    # frente como último recurso.
    return do_principal[0] if do_principal else FRENTE


def destaques(exercise) -> dict:
    """grupo -> "principal" ou "auxiliar", pronto para o template.

    Um dicionário e não duas listas: o SVG pergunta "qual é o nível DESTE
    grupo?" para cada região que desenha, e duas listas obrigariam a tela a
    fazer duas buscas por região.
    """
    niveis = {exercise.muscle_group: "principal"}
    for auxiliar in exercise.secondary_muscles or []:
        # O principal nunca é rebaixado: `clean()` já proíbe repetir, e o
        # `setdefault` é a segunda camada para dado que entrou por outro
        # caminho — o seed e o `shell` não chamam `clean()`.
        niveis.setdefault(auxiliar, "auxiliar")
    return niveis
