# -*- coding: utf-8 -*-
"""O menor contrato que prova a Fase 1.

Seis rotas: pegar token, devolver token, quem sou eu, e três de corrida. Não
cobre o NutriPlan inteiro de propósito — a Fase 1 existe para provar que um
cliente de fora consegue conversar com o backend, e não para migrar o produto.

Django puro, sem DRF e sem Ninja. O projeto tem sete dependências por escolha
declarada, `SalvarCorridaView` já era um endpoint JSON idempotente funcionando
em produção, e a autenticação que este contrato precisa não é a que o DRF
entrega de graça — o token dele é texto puro e não vence. Seis rotas não pagam
um framework e um paradigma novos.
"""
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts import entrada
from accounts.models import TokenDeApp
from workouts import corrida as motor
from workouts.corrida_views import DISTANCIA_MAXIMA_M, DURACAO_MAXIMA_S
from workouts.models import Corrida, TracoDaCorrida

from .auth import corpo_json, erro, exige_token, responder, usuario_do_pedido

# `csrf_exempt` em toda a API é correto e não é atalho: nenhuma destas rotas
# olha cookie. O raciocínio inteiro está em `api/auth.py`, e há teste exigindo
# que sessão de navegador NÃO autentique aqui.


def _perfil(pessoa):
    """O mínimo que um cliente precisa para desenhar a tela.

    Enumerar o que SAI, e não o que fica de fora: campo novo no model não
    vaza sozinho para a API no dia em que alguém o acrescentar.
    """
    perfil = getattr(pessoa, "profile", None)
    return {
        "id": pessoa.pk,
        "email": pessoa.email,
        "nome": pessoa.first_name or "",
        "sexo": getattr(perfil, "sex", None),
        "altura_cm": getattr(perfil, "height_cm", None),
    }


# ----------------------------------------------------------------- token ----


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def token(request):
    """POST troca e-mail e senha por um token. DELETE revoga o token usado."""
    if request.method == "DELETE":
        dono = usuario_do_pedido(request)
        if dono is None:
            return erro("é preciso um token válido", 401)
        cabecalho = request.headers.get("Authorization", "")
        cru = cabecalho[len("Bearer "):].strip()
        TokenDeApp.objects.filter(
            user=dono, digest=TokenDeApp._digest(cru), revogado_em__isnull=True
        ).update(revogado_em=timezone.now())
        return responder({}, status=204)

    dados, problema = corpo_json(request)
    if problema:
        return problema

    email = (dados.get("email") or "").strip()
    ip = entrada.ip_do_pedido(request)

    # A recusa é SEMPRE igual: e-mail que não existe, senha errada e origem
    # limitada respondem a mesma coisa. Duas mensagens diferentes
    # transformariam o endpoint num oráculo — de cadastro na primeira, e de
    # "achei o teto" na segunda.
    if not entrada.pode_tentar(email=email, ip=ip):
        return erro("e-mail ou senha incorretos", 401)

    pessoa = authenticate(request, username=email, password=dados.get("senha") or "")
    if pessoa is None or not pessoa.is_active:
        entrada.registrar_falha(email=email, ip=ip)
        return erro("e-mail ou senha incorretos", 401)

    entrada.limpar_apos_sucesso(email=email, ip=ip)
    registro, cru = TokenDeApp.emitir(pessoa)
    return responder(
        {
            "token": cru,
            "expira_em": registro.expira_em.isoformat(),
            "usuario": _perfil(pessoa),
        }
    )


@csrf_exempt
@require_http_methods(["GET"])
@exige_token
def eu(request):
    """Quem é o dono do token."""
    return responder(_perfil(request.dono))


# --------------------------------------------------------------- corridas ----


def _validar(dados):
    """O que o servidor recusa, e por quê. Devolve a mensagem ou `None`.

    As regras de plausibilidade são as MESMAS de `SalvarCorridaView` — teto de
    distância, teto de duração, datas coerentes. Duas cópias divergiriam na
    primeira correção, e por isso os limites são importados de lá em vez de
    reescritos.
    """
    for campo in ("op_id", "comecou_em", "terminou_em", "duracao_s"):
        if dados.get(campo) in (None, ""):
            return f"falta {campo}"

    tem_pontos = isinstance(dados.get("pontos"), list) and dados["pontos"]
    if not tem_pontos and dados.get("distancia_m") in (None, ""):
        return "falta distancia_m (ou pontos, para o servidor calcular)"

    try:
        duracao = int(dados["duracao_s"])
        if not tem_pontos:
            distancia = int(dados["distancia_m"])
    except (TypeError, ValueError):
        return "distância e duração precisam ser números"

    if duracao < 0:
        return "duração não pode ser negativa"
    if duracao > DURACAO_MAXIMA_S:
        return "duração acima do que o app registra"

    # Com pontos, `distancia_m` do cliente é DECORAÇÃO: o servidor recalcula e
    # ignora. Validar um número que será jogado fora confundiria o contrato —
    # o teto passa a valer sobre o que de fato é gravado, em `_plausivel`.
    if not tem_pontos:
        if distancia < 0:
            return "distância não pode ser negativa"
        if distancia > DISTANCIA_MAXIMA_M:
            return "distância acima do que o app registra"

    comecou = parse_datetime(dados["comecou_em"])
    terminou = parse_datetime(dados["terminou_em"])
    if comecou is None or terminou is None:
        return "datas inválidas"
    if terminou < comecou:
        return "a corrida terminou antes de começar"
    return None


def _plausivel(distancia_m):
    """O teto vale sobre o número GRAVADO, venha ele do cliente ou do motor.

    Um traçado forjado com pontos plausíveis mas milhares de quilômetros de
    percurso passaria pelo filtro de teleporte ponto a ponto e ainda assim
    registraria uma maratona que ninguém correu.
    """
    if distancia_m < 0:
        return "distância não pode ser negativa"
    if distancia_m > DISTANCIA_MAXIMA_M:
        return "distância acima do que o app registra"
    return None


def _calcular(pontos):
    """Distância e parciais a partir das leituras cruas. `None` se não der.

    É aqui que `workouts/corrida.py` deixa de ser código morto: ele já tinha
    haversine, corte de precisão, corte de teleporte e corte de ruído, com
    teste — e nenhum caminho vivo o chamava.

    OS PONTOS ACEITOS SÃO DEVOLVIDOS junto com os números, e quem decide
    guardá-los é `corridas()` — em `TracoDaCorrida`, não em `Corrida`. Esta
    função continua pura: ela calcula e não escreve.

    Aceitos, e não as leituras cruas: as recusadas são as de precisão ruim e as
    de teleporte, e guardá-las seria guardar mais dado sensível para desenhar
    um mapa pior. O teto de volume é o limite de 1 MB do corpo, em
    `api/auth.py` — ~7.200 pontos, duas horas a uma leitura por segundo.
    """
    limpos = []
    for p in pontos:
        try:
            limpo = {"lat": float(p["lat"]), "lon": float(p["lon"]), "t": float(p["t"])}
        except (KeyError, TypeError, ValueError):
            return None
        if not (-90 <= limpo["lat"] <= 90) or not (-180 <= limpo["lon"] <= 180):
            return None
        if p.get("accuracy") is not None:
            try:
                limpo["accuracy"] = float(p["accuracy"])
            except (TypeError, ValueError):
                return None
        limpos.append(limpo)

    resultado = motor.percurso(limpos)
    return {
        "distancia_m": int(round(resultado["distancia_m"])),
        "parciais": motor.parciais(resultado["pontos"]),
        "descartadas": resultado["descartadas"],
        "pontos": resultado["pontos"],
    }


def _divergencias(corrida, dados, distancia, parciais):
    """Os campos em que o reenvio discorda do que está gravado.

    Comparação por VALOR, e sobre o registro que já existe — não sobre uma
    impressão digital guardada numa coluna. Todo campo que importa já está no
    banco; um fingerprint seria uma coluna para rederivar o que se tem.

    `parciais` são listas de dicionários, e `==` em Python compara por valor:
    a mesma parcial escrita com as chaves em outra ordem NÃO é divergência.
    Comparar o JSON cru acusaria conflito onde não há um.
    """
    esperado = {
        "comecou_em": parse_datetime(dados["comecou_em"]),
        "terminou_em": parse_datetime(dados["terminou_em"]),
        "distancia_m": distancia,
        "duracao_s": int(dados["duracao_s"]),
        "teve_lacuna": bool(dados.get("teve_lacuna")),
        "parciais": parciais,
    }
    return sorted(
        campo for campo, valor in esperado.items() if getattr(corrida, campo) != valor
    )


def _corrida_em_json(corrida, com_traco=False):
    """Os números da corrida. O traçado só quando pedido, e nunca na lista.

    `com_traco` é falso por padrão de propósito: a lista do histórico devolve
    todas as corridas do dono, e anexar o percurso de cada uma arrastaria
    milhares de pontos para uma tela que desenha distância e tempo. É a mesma
    razão pela qual `TracoDaCorrida` é tabela separada — anexar aqui desfaria
    o desenho de lá.
    """
    corpo = {
        "op_id": corrida.op_id,
        "comecou_em": corrida.comecou_em.isoformat(),
        "terminou_em": corrida.terminou_em.isoformat(),
        "distancia_m": corrida.distancia_m,
        "duracao_s": corrida.duracao_s,
        "pace_s_km": corrida.pace_s_km,
        "teve_lacuna": corrida.teve_lacuna,
        "parciais": corrida.parciais,
    }
    if com_traco:
        traco = getattr(corrida, "traco", None)
        # Corrida sem traçado é o caso NORMAL, não erro: a PWA publicada
        # sincroniza só os números, e o `OneToOne` pode não existir. `pontos`
        # vem como lista vazia para o cliente não precisar distinguir os dois
        # casos ao desenhar — mas `tem_traco` diz qual dos dois é.
        corpo["tem_traco"] = traco is not None
        corpo["pontos"] = traco.pontos if traco else []
        corpo["leituras_descartadas"] = traco.descartadas if traco else 0
    return corpo


@csrf_exempt
@require_http_methods(["GET", "POST"])
@exige_token
def corridas(request):
    """GET lista as do dono. POST cria ou reconhece uma já sincronizada."""
    if request.method == "GET":
        return responder(
            {
                "corridas": [
                    _corrida_em_json(c)
                    for c in Corrida.objects.filter(user=request.dono)
                ]
            }
        )

    dados, problema = corpo_json(request)
    if problema:
        return problema

    mensagem = _validar(dados)
    if mensagem:
        return erro(mensagem, 400)

    distancia = int(dados.get("distancia_m") or 0)
    parciais = dados.get("parciais") or []
    calculado = None

    if isinstance(dados.get("pontos"), list) and dados["pontos"]:
        calculado = _calcular(dados["pontos"])
        if calculado is None:
            return erro("ponto de GPS malformado", 400)
        # Com pontos, o número do cliente é IGNORADO. É o que tira a distância
        # do lado que a pessoa controla.
        distancia = calculado["distancia_m"]
        parciais = calculado["parciais"]

    impossivel = _plausivel(distancia)
    if impossivel:
        return erro(impossivel, 400)

    try:
        with transaction.atomic():
            corrida = Corrida.objects.create(
                user=request.dono,
                op_id=str(dados["op_id"])[:64],
                comecou_em=parse_datetime(dados["comecou_em"]),
                terminou_em=parse_datetime(dados["terminou_em"]),
                distancia_m=distancia,
                duracao_s=int(dados["duracao_s"]),
                teve_lacuna=bool(dados.get("teve_lacuna")),
                parciais=parciais,
            )
            if calculado is not None:
                # Na MESMA transação, e não depois: corrida gravada com o
                # traçado faltando mentiria sobre o percurso na tela de mapa,
                # e o `create` do traço pode falhar sozinho (banco cheio,
                # conexão caindo). Ou entram os dois, ou não entra nenhum.
                TracoDaCorrida.objects.create(
                    corrida=corrida,
                    pontos=calculado["pontos"],
                    descartadas=calculado["descartadas"],
                )
            criada = True
    except IntegrityError:
        # Reenvio. A resposta perdida é indistinguível do envio perdido, então
        # o cliente reenvia — e reenviar não pode criar uma segunda corrida.
        corrida = Corrida.objects.get(user=request.dono, op_id=str(dados["op_id"])[:64])
        criada = False

        divergiram = _divergencias(corrida, dados, distancia, parciais)
        if divergiram:
            # Reenvio IDÊNTICO é o caso normal e responde 200. Este aqui é
            # outro: ou o cliente tem bug, ou o armazenamento local corrompeu,
            # ou dois estados diferentes ganharam o mesmo identificador.
            #
            # Aceitar em silêncio faria o app acreditar que sincronizou um
            # número que o servidor jogou fora. 409 é TERMINAL — reenviar não
            # muda nada —, e a regra da fila passa a ser: 2xx apaga, 409 apaga
            # e reporta, 5xx e falha de rede mantêm.
            #
            # O primeiro envio vence. O segundo é suspeito por construção, e
            # sobrescrever perderia o dado que chegou quando havia menos
            # motivo para desconfiar.
            return responder(
                {
                    "erro": "op_id já usado com outro conteúdo",
                    "divergiram": divergiram,
                    "guardado": _corrida_em_json(corrida),
                },
                status=409,
            )

    corpo = _corrida_em_json(corrida)
    if calculado is not None:
        corpo["leituras_descartadas"] = calculado["descartadas"]
        corpo["distancia_do_cliente_m"] = int(dados.get("distancia_m") or 0)
    return responder(corpo, status=201 if criada else 200)


@csrf_exempt
@require_http_methods(["GET"])
@exige_token
def corrida(request, op_id):
    """Uma corrida do dono, pelo `op_id` que o próprio aparelho gerou.

    Por `op_id` e não por `pk`: identificador sequencial convida a varrer o
    vizinho. E o filtro por dono vem antes de qualquer coisa — 404 e não 403,
    porque 403 confirmaria que a corrida existe.
    """
    achada = (
        Corrida.objects.filter(user=request.dono, op_id=op_id)
        # `select_related` porque o traçado SEMPRE sai aqui: sem ele seriam
        # duas idas ao banco para uma tela só. Na LISTA não há
        # `select_related` nenhum, e isso também é intencional.
        .select_related("traco")
        .first()
    )
    if achada is None:
        return erro("corrida não encontrada", 404)
    return responder(_corrida_em_json(achada, com_traco=True))
