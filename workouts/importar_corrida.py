# -*- coding: utf-8 -*-
"""Lê uma corrida de um arquivo GPX ou TCX (decisão 4 da avaliação, 20/09/2026).

Funções PURAS: recebem o conteúdo do arquivo e devolvem leituras no formato que
`workouts.corrida.percurso` já consome — `{"lat", "lon", "t"}`, com `t` em
segundos a partir da primeira leitura. O mesmo motor que trata o GPS ao vivo
trata o arquivo, então a distância sai de UMA conta só: uma leitura ruim é
recusada aqui do mesmo jeito que seria na rua.

SEGURANÇA DO XML. O arquivo é de fora, e `xml.etree` da biblioteca padrão
expande entidade interna (billion-laughs) e, dependendo da versão, resolve
entidade externa (XXE — ler arquivo do servidor). Não há `defusedxml` neste
ambiente. A defesa é estrutural e não custa dependência: GPX e TCX NUNCA
declaram DTD, então qualquer arquivo com `<!DOCTYPE` ou `<!ENTITY` é recusado
antes de o parser tocar nele. Sem DTD não há entidade, e sem entidade não há
nem XXE nem billion-laughs.

O QUE NÃO É GUARDADO. Só as estatísticas (distância, duração, início/fim,
parciais). O TRAÇADO (as coordenadas) não vira `TracoDaCorrida` na importação:
o arquivo que a pessoa subiu já tem onde ela mora, e guardar isso é a coleta
que `Corrida` recusou por anos. Corrida de arquivo entra como número, como a
que sincroniza só os totais. Dar mapa à corrida importada é trabalho de outra
fatia, com o corte das pontas da rota junto — não antes dele.
"""
import hashlib
from datetime import timedelta, timezone as dt_timezone
from xml.etree import ElementTree as ET

from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware

from . import corrida


class ArquivoDeCorridaInvalido(ValueError):
    """O arquivo não é uma corrida que dá para importar. A mensagem é para a tela."""


def _localname(tag):
    """`{http://…}trkpt` → `trkpt`. O namespace varia entre versões de GPX/TCX,
    e prender a leitura a um namespace específico quebraria com o export do
    aparelho seguinte."""
    return tag.rsplit("}", 1)[-1]


def _instante(texto):
    """ISO 8601 → datetime aware, ou `None` se não der para ler.

    GPX/TCX gravam em UTC com `Z`. Data sem fuso é tratada como UTC — é o que
    o formato assume, e inventar o fuso local do servidor deslocaria a hora."""
    if not texto:
        return None
    dt = parse_datetime(texto.strip())
    if dt is None:
        return None
    return make_aware(dt, dt_timezone.utc) if is_naive(dt) else dt


def _pontos_gpx(raiz):
    for trkpt in raiz.iter():
        if _localname(trkpt.tag) != "trkpt":
            continue
        lat, lon = trkpt.get("lat"), trkpt.get("lon")
        if lat is None or lon is None:
            continue
        instante = None
        for filho in trkpt:
            if _localname(filho.tag) == "time":
                instante = _instante(filho.text)
                break
        yield float(lat), float(lon), instante


def _pontos_tcx(raiz):
    for tp in raiz.iter():
        if _localname(tp.tag) != "Trackpoint":
            continue
        lat = lon = instante = None
        for elem in tp.iter():
            nome = _localname(elem.tag)
            if nome == "LatitudeDegrees":
                lat = elem.text
            elif nome == "LongitudeDegrees":
                lon = elem.text
            elif nome == "Time":
                instante = _instante(elem.text)
        if lat is None or lon is None:
            continue
        yield float(lat), float(lon), instante


def leituras_de_arquivo(conteudo, nome=""):
    """`(leituras, comecou_em)` a partir do texto do arquivo.

    `leituras` = `[{"lat", "lon", "t"}, ...]` (t em segundos do início);
    `comecou_em` é o instante da primeira leitura com horário. Levanta
    `ArquivoDeCorridaInvalido` com uma frase para a tela em qualquer recusa."""
    if conteudo is None:
        raise ArquivoDeCorridaInvalido("Arquivo vazio.")
    alto = conteudo.upper()
    if "<!DOCTYPE" in alto or "<!ENTITY" in alto:
        # Ver a docstring do módulo: GPX/TCX não têm DTD; isto é ataque ou
        # arquivo estranho, e das duas formas não importa.
        raise ArquivoDeCorridaInvalido("Arquivo com formato não aceito.")

    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError:
        raise ArquivoDeCorridaInvalido("Não conseguimos ler o arquivo — ele parece corrompido ou não é GPX/TCX.")

    tipo = _localname(raiz.tag)
    if tipo == "gpx":
        brutos = list(_pontos_gpx(raiz))
    elif tipo == "TrainingCenterDatabase":
        brutos = list(_pontos_tcx(raiz))
    else:
        raise ArquivoDeCorridaInvalido("O NutriPlan lê arquivos GPX e TCX (Garmin, Strava, Apple Saúde e afins).")

    if not brutos:
        raise ArquivoDeCorridaInvalido("Não encontramos nenhum ponto de percurso no arquivo.")

    com_tempo = [(lat, lon, dt) for lat, lon, dt in brutos if dt is not None]
    if not com_tempo:
        raise ArquivoDeCorridaInvalido("O arquivo não traz o horário dos pontos, e sem ele não dá para montar a corrida.")
    if len(com_tempo) < 2:
        raise ArquivoDeCorridaInvalido("O arquivo tem só um ponto com horário — não dá para medir distância nem tempo.")

    comecou = com_tempo[0][2]
    leituras = [
        {"lat": lat, "lon": lon, "t": (dt - comecou).total_seconds()}
        for lat, lon, dt in com_tempo
    ]
    return leituras, comecou


def corrida_de_arquivo(conteudo, nome=""):
    """Estatísticas prontas para virar `Corrida`, do parser ao motor de percurso.

    `{"distancia_m", "duracao_s", "comecou_em", "terminou_em", "parciais",
    "op_id"}`. `op_id` é a impressão do CONTEÚDO: reimportar o mesmo arquivo
    devolve o mesmo identificador, e o `UniqueConstraint(user, op_id)` recusa a
    segunda cópia. A validação de negócio (distância mínima, velocidade
    impossível) fica com a view, que tem a mensagem certa para cada recusa."""
    leituras, comecou = leituras_de_arquivo(conteudo, nome)
    resultado = corrida.percurso(leituras)
    pontos = resultado["pontos"]
    elapsed = leituras[-1]["t"]
    op_id = "arq-" + hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:60]
    return {
        "distancia_m": round(resultado["distancia_m"]),
        "duracao_s": round(elapsed),
        "comecou_em": comecou,
        "terminou_em": comecou + timedelta(seconds=elapsed),
        "parciais": corrida.parciais(pontos),
        "op_id": op_id,
    }
