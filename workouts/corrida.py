"""A matemática da corrida: distância, pace e parciais.

Funções puras, sem banco e sem navegador. É deliberado: o que decide se uma
corrida está certa é o tratamento das leituras de GPS, e isso precisa ser
testável com coordenadas conhecidas em vez de com um telefone na rua.

O que este módulo NÃO faz, e o motivo está em `docs/running-analise.md`: ele
não promete leitura contínua. Uma PWA não tem geolocalização em segundo plano —
não é limitação de esforço, é ausência de API. Com a tela bloqueada as leituras
param, e o que este módulo garante é que a lacuna vire LACUNA e não uma linha
reta inventada entre dois pontos distantes.
"""
from math import asin, cos, radians, sin, sqrt

#: Raio médio da Terra em metros. Haversine sobre esfera erra menos de 0,5% em
#: distâncias de corrida — muito abaixo do erro do próprio GPS de celular.
RAIO_DA_TERRA_M = 6_371_000

#: Leitura com incerteza acima disto não entra na conta. Trinta metros é
#: prédio alto e túnel: aceitar essas leituras faz a distância crescer parada.
#:
#: O limite é um PALPITE informado até alguém medir a `accuracy` típica na rua
#: em que a pessoa corre — está na lista de medições da análise. Chutar o
#: limite é chutar a distância, e por isso ele é parâmetro e não constante
#: enterrada no meio da função.
PRECISAO_MAXIMA_M = 30.0

#: 12,5 m/s são 45 km/h. O limite existe para pegar TELEPORTE — o telefone
#: reencontrando o sinal e pulando centenas de metros —, e não para arbitrar
#: quem corre rápido.
#:
#: A primeira versão usava 8 m/s, "ritmo de recorde de maratona". Errado por
#: dois motivos: um velocista passa de 10 m/s num tiro curto, e uma leitura a
#: cada segundo pega justamente o pico. O filtro cortaria o trecho mais rápido
#: da corrida de quem faz tiro — exatamente o que a pessoa quer ver.
#:
#: Acima de 45 km/h não é erro de calibragem, é outra coisa: leitura ruim, ou a
#: pessoa num carro. A segunda é pergunta de produto ("esqueci de encerrar a
#: corrida"), e não se resolve num filtro de distância.
VELOCIDADE_MAXIMA_MS = 12.5

#: Abaixo de 1,5 m em um segundo, o deslocamento não se distingue do ruído do
#: GPS parado. Somar isso é como um velocímetro que anda com o carro na garagem.
DESLOCAMENTO_MINIMO_M = 1.5


def distancia_m(a, b) -> float:
    """Metros entre dois pontos `(lat, lon)`, por haversine."""
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * RAIO_DA_TERRA_M * asin(sqrt(h))


def _aceitavel(anterior, atual, precisao_maxima) -> bool:
    """O trecho entre duas leituras entra na distância?

    Três recusas, e cada uma tem uma causa real na rua:

    incerteza alta   -> prédio, túnel, garagem: a posição "anda" sem ninguém
                        andar, e somar isso infla a corrida de quem parou no
                        sinal.
    velocidade absurda -> o telefone reencontrou o sinal e "teleportou". A
                        linha reta entre os dois pontos é uma distância que
                        ninguém percorreu.
    deslocamento mínimo -> ruído de GPS parado. Sem este piso, dez minutos
                        esperando alguém viram trezentos metros.
    """
    if atual.get("accuracy") is not None and atual["accuracy"] > precisao_maxima:
        return False

    segundos = atual["t"] - anterior["t"]
    if segundos <= 0:
        return False

    metros = distancia_m((anterior["lat"], anterior["lon"]), (atual["lat"], atual["lon"]))
    if metros < DESLOCAMENTO_MINIMO_M:
        return False
    if metros / segundos > VELOCIDADE_MAXIMA_MS:
        return False
    return True


def percurso(leituras, precisao_maxima=PRECISAO_MAXIMA_M) -> dict:
    """Distância total e os trechos aceitos, a partir das leituras cruas.

    Cada leitura é `{"lat", "lon", "t"}` com `t` em segundos, e `accuracy`
    opcional em metros.

    Leitura recusada não vira buraco na sequência: ela é DESCARTADA e a próxima
    é comparada com a última leitura boa. Descartar o ponto e continuar de onde
    parou é o que impede uma leitura ruim no meio de um trecho reto de partir a
    corrida em dois.
    """
    aceitos = []
    total = 0.0
    anterior = None

    for leitura in leituras:
        if anterior is None:
            if (
                leitura.get("accuracy") is not None
                and leitura["accuracy"] > precisao_maxima
            ):
                # A primeira leitura também passa pelo filtro: começar a
                # corrida com a posição errada desloca o traçado inteiro.
                continue
            anterior = leitura
            aceitos.append({**leitura, "acumulado_m": 0.0})
            continue

        if not _aceitavel(anterior, leitura, precisao_maxima):
            continue

        total += distancia_m(
            (anterior["lat"], anterior["lon"]), (leitura["lat"], leitura["lon"])
        )
        aceitos.append({**leitura, "acumulado_m": total})
        anterior = leitura

    return {
        "distancia_m": total,
        "pontos": aceitos,
        "descartadas": len(leituras) - len(aceitos),
    }


def pace_por_km(distancia_m_total, segundos) -> float | None:
    """Segundos por quilômetro. `None` quando não há distância para dividir.

    Devolve segundos e não "5:30" de propósito: formatar é trabalho da tela, e
    um número que já nasce string não soma, não compara e não vira média.
    """
    if distancia_m_total <= 0 or segundos <= 0:
        return None
    return segundos * 1000 / distancia_m_total


def parciais(pontos, cada_m=1000) -> list:
    """O tempo de cada quilômetro cheio.

    O quilômetro exato cai ENTRE duas leituras, e a escolha muda o número. Aqui
    o instante é interpolado linearmente entre as duas: atribuir ao ponto
    seguinte empurraria cada parcial para frente, e o erro se acumula — numa
    corrida de dez quilômetros, dez vezes.

    Só quilômetro CHEIO vira parcial. O trecho final incompleto não entra:
    "800 m em 4min" ao lado de parciais de 1 km convida a comparar pace de
    coisas de tamanho diferente.
    """
    if len(pontos) < 2:
        return []

    marcas = []
    alvo = cada_m
    for anterior, atual in zip(pontos, pontos[1:]):
        while atual["acumulado_m"] >= alvo:
            faixa = atual["acumulado_m"] - anterior["acumulado_m"]
            if faixa <= 0:
                break
            fracao = (alvo - anterior["acumulado_m"]) / faixa
            instante = anterior["t"] + fracao * (atual["t"] - anterior["t"])
            marcas.append(instante)
            alvo += cada_m

    inicio = pontos[0]["t"]
    saida = []
    anterior_t = inicio
    for numero, instante in enumerate(marcas, start=1):
        # Só `segundos`. Numa parcial de 1 km o tempo JÁ É o pace por
        # quilômetro, e publicar os dois campos com o mesmo valor sugere um
        # cálculo que não existe — no dia em que `cada_m` mudasse, um dos dois
        # ficaria errado sem ninguém notar. Quem quiser pace de outra distância
        # chama `pace_por_km`.
        saida.append({"km": numero, "segundos": instante - anterior_t})
        anterior_t = instante
    return saida
