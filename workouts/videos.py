# -*- coding: utf-8 -*-
"""A identidade do vídeo de cada exercício, e como conferi-la.

POR QUE ESTE MÓDULO EXISTE.

Em 07/09/2026 o catálogo apareceu com 10 exercícios abrindo o vídeo de OUTRO
exercício: o supino reto mostrava tríceps na polia, a rosca martelo mostrava
supino, o stiff mostrava rosca inversa. A investigação mostrou que o defeito
NÃO estava no aplicativo — o seed casa por `name`, não há `zip`, índice nem
`videos[i]` em lugar nenhum, e o banco servia exatamente o par que tinha
chegado. O par já veio trocado da curadoria manual.

Ou seja: era um defeito de CONTEÚDO que nenhum teste podia ver, porque todos os
testes comparavam a URL cadastrada com a URL esperada — e as duas eram a mesma
URL errada. Um teste de identidade só morde se souber algo sobre o CONTEÚDO.

A âncora escolhida é o TÍTULO do vídeo. `exercises.json` passa a guardar
`video_titulo`, capturado do oEmbed público do YouTube no dia da curadoria, e
`titulo_confere` compara esse título com as palavras do movimento. Isso pega a
troca grosseira — "Supino reto" apontando para um vídeo intitulado "Rosca
Martelo em Pé" — sem depender de rede na suíte.

O QUE ISTO NÃO PROVA, e fica escrito: título não é imagem. Um vídeo intitulado
"Supino reto barra" que mostre outra coisa passa por aqui. Conferir o quadro
exige assistir, e este ambiente não assiste vídeo do YouTube — foi medido:
`readyState 0`, `buffered 0`, `networkState 2` depois de 60 s. A conferência
visual continua sendo humana; o que este módulo faz é impedir que a troca
ATRAVESSE o processo sem ninguém ver.
"""
import unicodedata

#: Palavras que identificam o MOVIMENTO de cada exercício num título de vídeo.
#:
#: A lista é generosa de propósito — sinônimo, inglês e apelido de academia —,
#: porque o objetivo é achar TROCA DE EXERCÍCIO, não julgar como o canal
#: escreveu. Basta uma bater.
#:
#: "invertido" está ao lado de "inverso" porque o vídeo do crucifixo inverso se
#: chama "Crucifixo invertido máquina", e a primeira versão desta tabela
#: reprovou um par CERTO por causa de uma letra.
MOVIMENTO_ESPERADO = {
    "Abdominal supra no solo": ["abdominal", "crunch", "supra"],
    "Afundo com halteres": ["afundo", "avanco", "lunge", "passada"],
    "Agachamento livre": ["agachamento", "squat"],
    "Barra fixa assistida": ["barra fixa", "pull up", "pull-up", "graviton",
                             "assistida"],
    "Cadeira extensora": ["extensora", "leg extension"],
    "Cadeira flexora": ["cadeira flexora", "leg curl", "flexora"],
    "Crucifixo inverso na máquina": ["crucifixo inverso", "crucifixo invertido",
                                     "reverse fly", "peck deck inverso",
                                     "voador inverso"],
    "Crucifixo na máquina (voador)": ["crucifixo", "voador", "peck-deck",
                                      "peck deck", "chest fly"],
    "Desenvolvimento com halteres": ["desenvolvimento", "shoulder press"],
    "Elevação de pernas": ["elevacao de perna", "leg raise", "abdominal infra"],
    "Elevação frontal com halteres": ["elevacao frontal", "front raise"],
    "Elevação lateral com halteres": ["elevacao lateral", "lateral raise"],
    "Elevação pélvica": ["elevacao pelvica", "hip thrust", "ponte"],
    "Encolhimento com halteres": ["encolhimento", "shrug"],
    "Flexão de braço": ["flexao de braco", "push up", "push-up", "apoio",
                        "flexao"],
    "Leg press 45°": ["leg press", "legpress"],
    "Mergulho no banco": ["mergulho", "dips", "banco"],
    "Mesa flexora": ["mesa flexora", "flexora deitado", "leg curl"],
    "Panturrilha em pé": ["panturrilha", "calf"],
    "Panturrilha sentado": ["panturrilha", "calf"],
    "Prancha abdominal": ["prancha", "plank", "isometrica"],
    "Puxada frente na polia": ["puxada", "puxador", "pulldown", "pull down"],
    "Remada alta com barra": ["remada alta", "upright row"],
    "Remada baixa na polia": ["remada baixa", "remada sentado", "seated row",
                              "cable row"],
    "Remada curvada com barra": ["remada curvada", "barbell row"],
    "Remada unilateral com halter": ["remada unilateral", "serrote",
                                     "one arm row"],
    "Rosca alternada com halteres": ["rosca alternada", "alternate curl"],
    "Rosca de punho com barra": ["rosca punho", "rosca de punho", "wrist curl",
                                 "antebraco"],
    "Rosca direta com barra": ["rosca direta", "rosca com barra",
                               "barbell curl"],
    "Rosca inversa com barra": ["rosca inversa", "reverse curl", "pronada"],
    "Rosca martelo": ["martelo", "hammer"],
    "Stiff com barra": ["stiff", "romeno", "rdl"],
    "Supino inclinado com halteres": ["supino inclinado", "incline press",
                                      "incline bench"],
    "Supino reto com barra": ["supino reto", "bench press"],
    "Tríceps na polia com corda": ["triceps", "pulley", "polia", "corda",
                                   "pushdown", "rope"],
    "Tríceps testa com barra": ["triceps testa", "testa", "skull crusher",
                                "frances"],
}


def _simples(texto):
    """Sem acento e em minúsculas — o título vem escrito de todo jeito."""
    normal = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normal
                   if unicodedata.category(c) != "Mn").lower()


def titulo_confere(exercicio, titulo):
    """O título do vídeo menciona o movimento deste exercício?

    Devolve `True` também quando o exercício não está na tabela — a tabela
    cobre o catálogo de hoje, e um exercício novo sem entrada não pode
    derrubar o build. Quem cobra a entrada é o teste que compara as duas
    listas.
    """
    palavras = MOVIMENTO_ESPERADO.get(exercicio)
    if not palavras:
        return True
    alvo = _simples(titulo)
    return any(_simples(p) in alvo for p in palavras)


def oembed(video_id, timeout=20):
    """Título e canal do vídeo, pelo oEmbed público. Devolve `None` se morreu.

    Fora da suíte de propósito: teste não fala com a rede, e um soluço do
    YouTube não pode reprovar um build. Quem usa isto é
    `manage.py conferir_videos`, rodado à mão.
    """
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    alvo = "https://www.youtube.com/watch?v=" + video_id
    url = ("https://www.youtube.com/oembed?url="
           + urllib.parse.quote(alvo, safe="") + "&format=json")
    pedido = urllib.request.Request(url, headers={"User-Agent": "NutriPlan/1.0"})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        return {"vivo": False, "motivo": "HTTP %d" % erro.code}
    except Exception as erro:                       # rede, DNS, TLS, timeout
        return {"vivo": False, "motivo": str(erro)[:80]}
    return {"vivo": True, "titulo": dados.get("title", ""),
            "canal": dados.get("author_name", "")}
