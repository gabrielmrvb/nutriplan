"""Limite de pedidos de recuperação de senha.

O QUE ESTA PROTEÇÃO FAZ, E O QUE NÃO FAZ
========================================

Ela existe porque o endpoint `/conta/senha/` passa a mandar e-mail de verdade,
por um provedor com cota diária. Sem limite, um laço numa aba do navegador
consome a cota do dia e derruba a recuperação de senha para todo mundo — e
enche a caixa de entrada de quem foi escolhido como alvo.

São QUATRO limites, e cada um cobre o que os outros não cobrem:

  por E-MAIL      protege a caixa de entrada de uma pessoa específica. É o mais
                  forte porque o e-mail não é forjável: para pedir de novo para
                  a mesma vítima, é preciso usar a mesma chave.

  por ORIGEM      corta o caso preguiçoso — o mesmo navegador repetindo. NÃO
                  resiste a quem forja `X-Forwarded-For` nem a quem troca de
                  IP. Ver `ip_do_pedido`, que explica por que nesta
                  infraestrutura não dá para fazer melhor.

  GLOBAL/HORA     corta a rajada.

  GLOBAL/24h      o teto que de fato protege a cota do provedor. É o único que
                  não depende de identificar ninguém, e por isso é o que segura
                  quem escapou dos outros três.

A resposta ao usuário é SEMPRE a mesma, limitado ou não: a tela de "verifique
seu e-mail". Devolver 429, ou qualquer texto diferente, transformaria o limite
num oráculo — bastaria observar quando a resposta muda para descobrir quantos
pedidos aquele e-mail já teve, e portanto que ele existe.

O contador está no PostgreSQL e não no cache. Ver `PedidoDeRecuperacao`.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.utils import timezone

from .models import PedidoDeRecuperacao

#: A janela dos três limites.
JANELA_MINUTOS = 60

#: Quantos pedidos para o MESMO e-mail cabem na janela.
#:
#: Três porque o uso humano real é: pede, não chega, pede de novo, olha o spam,
#: pede mais uma. O quarto pedido em uma hora não é gente com pressa.
LIMITE_POR_EMAIL = 3

#: Quantos pedidos da MESMA origem cabem na janela. Mais folgado que o de
#: e-mail porque uma casa, um escritório ou uma operadora móvel compartilham
#: saída — e limitar demais aqui puniria vizinho.
LIMITE_POR_IP = 10

#: Teto de pedidos do app inteiro na janela de UMA HORA.
#:
#: Corta a rajada: cinquenta por hora impede que um laço numa aba consuma a
#: cota em minutos.
LIMITE_GLOBAL = 50

#: A janela longa, e o teto que realmente protege a cota do provedor.
JANELA_DIARIA_MINUTOS = 60 * 24

#: Teto de pedidos do app inteiro em 24 HORAS.
#:
#: O horário sozinho não bastava, e a conta é simples: 50/h sustentado por seis
#: horas dá 300 — a cota diária inteira do plano gratuito, consumida só com
#: recuperação de senha, antes do fim da tarde.
#:
#: Duzentos, e não 300, porque a cota é do PROVEDOR e não deste endpoint: as
#: mensagens que o app mandar por qualquer outro motivo precisam caber no
#: mesmo dia. Sobram 100 de margem — um terço — para o resto.
#:
#: Duzentos pedidos de redefinição em um dia também não é uso humano de um app
#: em beta com um punhado de contas; se um dia for, o número sobe junto com o
#: plano.
LIMITE_GLOBAL_DIARIO = 200

CHAVE_GLOBAL = "__global__"


def _hmac(valor: str) -> str:
    """HMAC do valor com a SECRET_KEY.

    Guardar o e-mail em texto transformaria a tabela de limites numa lista de
    quem usa o NutriPlan — exatamente o que a tela de recuperação existe para
    não revelar. HMAC e não hash simples: sem a chave, nem uma tabela arco-íris
    de e-mails comuns ajuda.

    EFEITO COLATERAL DE ROTACIONAR A CHAVE, e ele é deliberado: trocada a
    SECRET_KEY, as linhas antigas passam a ter um HMAC que não bate mais com
    nada, e o contador começa do zero. As janelas são de 60 minutos e 24 horas,
    então isso se cura sozinho em um dia — e o preço de não ter esse efeito
    seria guardar o e-mail de forma reversível, que é caro demais para pagar
    por um contador. `SECRET_KEY_FALLBACKS` não ajuda aqui: ele vale para
    VERIFICAR assinatura já emitida, e este HMAC é recalculado a cada consulta.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), valor.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def normalizar_email(email: str) -> str:
    """Minúsculas e sem espaços em volta.

    Sem isso, `Fulano@X.com` e `fulano@x.com` seriam contadores diferentes e o
    limite por e-mail cairia trocando a caixa das letras — que é a primeira
    coisa que alguém tenta.
    """
    return (email or "").strip().lower()


def ip_do_pedido(request) -> str:
    """De onde veio, com o contrato REAL do Render — e com o que ele não dá.

    O comportamento do Render foi conferido na documentação e no fórum deles,
    não suposto, porque as duas escolhas ingênuas erram para lados opostos:

    *   pegar o PRIMEIRO item de `X-Forwarded-For` é o erro clássico de
        segurança — o cliente escreve o próprio cabeçalho e escolhe o IP;

    *   pegar o ÚLTIMO, atrás do Render, devolve o IP do PROXY DELE. Todos os
        usuários do app cairiam no mesmo balde e dez pedidos de dez pessoas
        diferentes bloqueariam a décima primeira. Foi o que esta função fazia
        antes desta correção.

    O Render põe o IP do cliente como PRIMEIRO item e apenas ANEXA o seu à
    lista — sem remover o que o cliente tenha mandado. Então o primeiro item é
    a melhor identificação disponível E é falsificável, as duas coisas ao mesmo
    tempo. Não há terceira opção nesta infraestrutura.

    A consequência está assumida no desenho: o limite por origem vale contra
    repetição preguiçosa e NÃO vale contra quem forja o cabeçalho. Quem forja
    escapa dele e vai bater em `LIMITE_GLOBAL` e `LIMITE_GLOBAL_DIARIO`, que
    não dependem de identificar ninguém — é por isso que o teto global é o que
    protege a cota, e não o limite por IP.

    Fora do proxy confiável, `REMOTE_ADDR` é o único valor que não veio do
    cliente. `USA_PROXY_CONFIAVEL` tem padrão FALSO: numa configuração
    desconhecida, ler o cabeçalho seria confiar em quem não se conhece.
    """
    if getattr(settings, "USA_PROXY_CONFIAVEL", False):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if encaminhado:
            primeiro = encaminhado.split(",")[0].strip()
            if primeiro:
                return primeiro
    return request.META.get("REMOTE_ADDR", "") or "desconhecido"


def _contar(tipo: str, chave: str, desde) -> int:
    return PedidoDeRecuperacao.objects.filter(
        tipo=tipo, chave=chave, criado_em__gte=desde
    ).count()


def pode_pedir(*, email: str, ip: str) -> bool:
    """Diz se este pedido ainda cabe nos três limites.

    Só CONSULTA. Quem registra é `registrar`, chamado depois de o envio ser
    de fato disparado — assim um pedido recusado por limite não gasta cota do
    contador e não empurra a janela para frente sozinho.
    """
    desde = timezone.now() - timezone.timedelta(minutes=JANELA_MINUTOS)
    chave_email = _hmac(normalizar_email(email))
    chave_ip = _hmac(ip)

    desde_dia = timezone.now() - timezone.timedelta(minutes=JANELA_DIARIA_MINUTOS)
    if _contar("global", CHAVE_GLOBAL, desde_dia) >= LIMITE_GLOBAL_DIARIO:
        return False
    if _contar("global", CHAVE_GLOBAL, desde) >= LIMITE_GLOBAL:
        return False
    if _contar("email", chave_email, desde) >= LIMITE_POR_EMAIL:
        return False
    if _contar("ip", chave_ip, desde) >= LIMITE_POR_IP:
        return False
    return True


def registrar(*, email: str, ip: str) -> None:
    """Anota o pedido nos três contadores."""
    PedidoDeRecuperacao.objects.bulk_create(
        [
            PedidoDeRecuperacao(tipo="email", chave=_hmac(normalizar_email(email))),
            PedidoDeRecuperacao(tipo="ip", chave=_hmac(ip)),
            PedidoDeRecuperacao(tipo="global", chave=CHAVE_GLOBAL),
        ]
    )


#: Quanto tempo uma linha fica depois de sair da maior janela.
#:
#: A maior janela é a de 24h, então nada além de 48h pode influenciar limite
#: nenhum — o dobro é a margem para relógio, fuso e a linha que nasce no
#: instante da limpeza.
RETENCAO_MINUTOS = JANELA_DIARIA_MINUTOS * 2


def limpar_antigos() -> int:
    """Apaga o que já não participa de nenhuma janela.

    Roda na própria escrita porque o projeto não tem agendador, e uma tabela
    que só cresce vira problema silencioso de disco num banco gratuito.

    O custo é baixo por construção, e não por sorte: o DELETE filtra por
    `criado_em`, que é indexado, e no caso normal não casa com nada — o
    planejador varre o índice, não encontra linha e volta. E ele só é chamado
    depois de um envio de fato acontecer, que é o caminho raro; pedido barrado
    pelo limite não dispara limpeza.

    O que NÃO se faz aqui é apagar por contagem ou varrer a tabela inteira: as
    duas coisas transformam uma operação rara e barata numa cara.
    """
    limite = timezone.now() - timezone.timedelta(minutes=RETENCAO_MINUTOS)
    apagados, _ = PedidoDeRecuperacao.objects.filter(criado_em__lt=limite).delete()
    return apagados
