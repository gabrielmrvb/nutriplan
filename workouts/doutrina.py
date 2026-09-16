"""O leitor do `docs/briefs/treino/TREINO.md` — a doutrina de treino.

O DOCUMENTO É A FONTE; este módulo só lê. Cada número que o motor usa para
dimensionar uma sessão — exercícios por grupo, séries por exercício, séries
diretas por sessão, teto semanal por frequência, descanso, duração — sai
das tabelas do TREINO.md, lidas UMA vez do disco. `workouts/test_treino_md.py`
cobra que o que está escrito é o que o gerador entrega, como
`config/test_design_system.py` cobra o `DESIGN.md`.

Nada de Django aqui: `accounts.models` importa este módulo para publicar o
teto por nível, e um import de modelo daqui para lá fecharia o círculo.
"""
import re
from functools import lru_cache
from pathlib import Path

DOCUMENTO = Path(__file__).resolve().parent.parent / "docs" / "briefs" / "treino" / "TREINO.md"

NIVEIS = ("iniciante", "intermediario", "avancado")
#: Quem não respondeu treina como intermediário — o número que o app já
#: praticava antes da pergunta existir (`accounts.models.Experiencia`).
NIVEL_PADRAO = "intermediario"

#: Os tipos de dia, com as chaves EXATAS das tabelas do documento.
UM_GRUPO = "um_grupo"
DOIS_GRUPOS = "dois_grupos"
TRES_GRUPOS = "tres_grupos"
INFERIOR = "inferior"
SUPERIOR = "superior"
FULL = "full"
TIPOS_DE_DIA = (UM_GRUPO, DOIS_GRUPOS, TRES_GRUPOS, INFERIOR, SUPERIOR, FULL)

#: Os grupos GRANDES: um dia com um deles anunciado é "um grupo"; com um
#: grande e um pequeno é "dois grupos". Bíceps e tríceps juntos ("Braços")
#: contam como dois grupos — dois pequenos que enchem uma sessão.
GRANDES = frozenset({"chest", "back", "quads", "hamstrings", "shoulders"})

_FAIXA = re.compile(r"^\s*(\d+)\s*(?:[–\-]\s*(\d+))?\s*$")


def _faixa(texto):
    m = _FAIXA.match(texto)
    if not m:
        raise ValueError("célula sem número no TREINO.md: %r" % texto)
    minimo = int(m.group(1))
    maximo = int(m.group(2)) if m.group(2) else minimo
    return (minimo, maximo)


def _tabelas(texto):
    """Toda tabela markdown do documento, indexada pela tupla do cabeçalho."""
    tabelas = {}
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        if linha.startswith("|") and i + 1 < len(linhas) and re.match(r"^\|[\s\-:|]+\|$", linhas[i + 1].strip()):
            cabecalho = tuple(c.strip() for c in linha.strip("|").split("|"))
            corpo = []
            i += 2
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                celulas = [c.strip() for c in linhas[i].strip().strip("|").split("|")]
                corpo.append(dict(zip(cabecalho, celulas)))
                i += 1
            tabelas[cabecalho] = corpo
            continue
        i += 1
    return tabelas


#: ESTE ARQUIVO É CÓDIGO. `accounts.models.TETO_POR_EXPERIENCIA` lê a tabela
#: B na importação do módulo, então um `TREINO.md` movido ou com célula sem
#: número derruba o Django inteiro no boot — de propósito: a ficha de todo
#: mundo sai destes números, e um app que sobe com a doutrina quebrada
#: montaria treino errado em silêncio. O `check --deploy` do `build.sh`
#: importa os modelos e reprova ANTES de o deploy subir; o pre-push roda
#: `test_treino_md`, que lê o documento com um segundo parser.
@lru_cache(maxsize=1)
def carregar():
    """As três tabelas do documento, uma vez por processo."""
    texto = DOCUMENTO.read_text(encoding="utf-8")
    tabelas = _tabelas(texto)
    por_sessao = {}
    for linha in tabelas[("nivel", "tipo_de_dia", "exercicios_grande", "exercicios_pequeno",
                          "series_por_exercicio", "series_diretas", "duracao_min")]:
        por_sessao[(linha["nivel"], linha["tipo_de_dia"])] = {
            "exercicios": (_faixa(linha["exercicios_grande"])[0], _faixa(linha["exercicios_pequeno"])[0]),
            "series_por_exercicio": _faixa(linha["series_por_exercicio"]),
            "series_diretas": _faixa(linha["series_diretas"]),
            "duracao": _faixa(linha["duracao_min"]),
        }
    por_semana = {}
    for linha in tabelas[("nivel", "ocorrencias", "series_diretas_semana", "teto_efetivo")]:
        por_semana[(linha["nivel"], int(linha["ocorrencias"]))] = {
            "diretas": _faixa(linha["series_diretas_semana"]),
            "teto": _faixa(linha["teto_efetivo"])[0],
        }
    descansos = {linha["tipo"]: _faixa(linha["descanso_s"])[0] for linha in tabelas[("tipo", "descanso_s")]}
    # A tolerância da MÉDIA do ciclo (decisão do dono, 17/09/2026): alvo e
    # margem para o grupo grande a 2× no perfil do teste dourado.
    medias = {
        linha["medida"]: (_faixa(linha["alvo"])[0], _faixa(linha["tolerancia"])[0])
        for linha in tabelas[("medida", "alvo", "tolerancia")]
    }
    # O mapa (split, letra) -> tipo de dia vem da tabela "Tipos de dia": a
    # coluna `modelos` lista `abc2 A–C`, `abcde A`, `abcde B`... "Pernas e
    # ombros" é dois grupos (quadríceps e posterior dividem a cota do
    # grande) e "Pernas completo" é três — contagem não deduz isso.
    modelos = {}
    for linha in tabelas[("chave", "o que é", "modelos")]:
        tipo = linha["chave"].strip("`")
        for trecho in re.findall(r"`([a-z0-9]+) ([A-E])(?:[–\-]([A-E]))?`", linha["modelos"]):
            split, inicio, fim = trecho
            for letra in "ABCDE"[ord(inicio) - 65: ord(fim or inicio) - 65 + 1]:
                modelos[(split, letra)] = tipo
    faltam = [(n, t) for n in NIVEIS for t in TIPOS_DE_DIA if (n, t) not in por_sessao]
    if faltam:
        raise ValueError("TREINO.md sem linha para %s" % faltam)
    return {"sessao": por_sessao, "semana": por_semana, "descanso": descansos, "modelos": modelos, "media": medias}


def nivel_ou_padrao(nivel) -> str:
    return nivel if nivel in NIVEIS else NIVEL_PADRAO


def tipo_de_dia(split, label):
    """O tipo de dia de um modelo, pelo mapa do documento — ou `None` para o
    que o contrato não cobre (`abcd D`, o dia de complementares)."""
    return carregar()["modelos"].get((split, label))


def exercicios_por_grupo(nivel, tipo) -> tuple:
    """`(grande, pequeno)`: exercícios do grupo maior e de cada um dos demais."""
    return carregar()["sessao"][(nivel_ou_padrao(nivel), tipo)]["exercicios"]


def series_por_exercicio(nivel) -> tuple:
    return carregar()["sessao"][(nivel_ou_padrao(nivel), DOIS_GRUPOS)]["series_por_exercicio"]


def faixa_de_series(nivel, tipo) -> tuple:
    """`(piso, teto)` de séries DIRETAS numa sessão deste tipo, neste nível."""
    return carregar()["sessao"][(nivel_ou_padrao(nivel), tipo)]["series_diretas"]


def duracao_esperada(nivel, tipo) -> tuple:
    return carregar()["sessao"][(nivel_ou_padrao(nivel), tipo)]["duracao"]


def _ocorrencias(ocorrencias) -> int:
    return max(1, min(3, int(ocorrencias or 1)))


def faixa_semanal_direta(nivel, ocorrencias) -> tuple:
    """Séries DIRETAS por grupo na semana, para um grupo que cai `ocorrencias` vezes."""
    return carregar()["semana"][(nivel_ou_padrao(nivel), _ocorrencias(ocorrencias))]["diretas"]


def teto_semanal(nivel, ocorrencias) -> int:
    """O teto de séries EFETIVAS (direta 1, secundária 0,5) que o motor
    apara, para um grupo que cai `ocorrencias` vezes na semana."""
    return carregar()["semana"][(nivel_ou_padrao(nivel), _ocorrencias(ocorrencias))]["teto"]


def tolerancia_da_media() -> tuple:
    """(alvo, tolerância) da média de 3 semanas do grupo grande a 2× —
    24 ± 2, o teto da média é 26 (TREINO.md, "Tolerância da média")."""
    return carregar()["media"]["media_3_semanas_grande_2x"]


def descanso(composto) -> int:
    return carregar()["descanso"]["composto" if composto else "isolador"]
