# -*- coding: utf-8 -*-
"""Tentar senha em série para de sair de graça — no web e na API.

O QUE ESTAVA ABERTO
===================

Medido antes de escrever qualquer coisa: `AppLoginView` não tinha gancho de
falha, `POST /api/v1/token/` também não, e não havia axes nem defender. Os
limites de `accounts/limites.py` protegem a RECUPERAÇÃO DE SENHA — a cota de
e-mail de um provedor —, não autenticação.

A POLÍTICA, E O QUE ELA RECUSA DE PROPÓSITO
===========================================

Três limites, e a ausência de um quarto é a decisão mais importante:

  ORIGEM + E-MAIL   corta a adivinhação dirigida vinda de um lugar.

  ORIGEM            corta a varredura — quem espalha as tentativas por muitas
                    contas para escapar do limite acima.

  GLOBAL            a válvula de emergência. Não depende de identificar
                    ninguém, e é o que segura quem forja o cabeçalho de origem.

  por E-MAIL        NÃO EXISTE, e é de propósito. Um limite assim seria uma
                    arma: bastaria saber o endereço de alguém para deixar essa
                    pessoa de fora da própria conta. Aqui as tentativas de um
                    atacante prendem a ORIGEM dele; a dona entra do aparelho
                    dela mesmo enquanto o ataque acontece.

A RESPOSTA DE QUEM ESTÁ LIMITADO É IGUAL À DE SENHA ERRADA
==========================================================

Não é 429. É o precedente que este projeto já fixou na recuperação de senha:
"devolver 429, ou qualquer texto diferente, transformaria o limite num
oráculo". Um status próprio diria ao atacante que ele achou o teto — e diria,
por tabela, que vale a pena continuar de outro lugar.

O custo assumido: um cliente honesto não aprende a recuar sozinho. Para um app
com dezenas de contas, é troca barata; se um dia houver muitos clientes
automáticos, a conta muda.

SUCESSO LIMPA O CONTADOR
========================

Quem errou duas vezes, acertou e voltou a errar não começa do quase-limite.
Sem isso, trocar de senha e digitar errado ao longo do dia acabaria barrando
alguém que não fez nada.

DE ONDE VEM A ORIGEM
====================

De `limites.ip_do_pedido`, e não de uma segunda leitura de cabeçalho. Ele já
carrega o contrato real do Render — o cliente é o PRIMEIRO item de
`X-Forwarded-For`, o Render apenas anexa o dele, e por isso o primeiro é a
melhor identificação disponível E é falsificável ao mesmo tempo. Fora de proxy
confiável vale `REMOTE_ADDR`, que é o único valor que não veio do cliente.

Duas implementações de "de onde veio" divergiriam na primeira correção, e a
que ficasse para trás seria a que protege a senha.
"""
from django.utils import timezone

# `_hmac` é privado do módulo vizinho e é importado de propósito: duplicar a
# derivação de chave criaria duas keyings para o mesmo segredo, e a segunda
# nasceria sem o cuidado que a primeira tem.
from .limites import _hmac, ip_do_pedido, normalizar_email  # noqa: F401
from .models import TentativaDeEntrada

#: Cinco erros do mesmo lugar para a mesma conta. Quem digita errado três vezes
#: seguidas ainda entra na quarta; quem está adivinhando, não.
LIMITE_POR_ORIGEM_E_EMAIL = 5

#: Vinte falhas do mesmo lugar, somando todas as contas. Corta a varredura sem
#: atrapalhar uma casa com várias pessoas usando o app atrás do mesmo IP.
LIMITE_POR_ORIGEM = 20

#: O teto que não depende de identificar ninguém. Alto o bastante para não ser
#: alcançado por uso real, e é o que resta contra quem forja a origem.
LIMITE_GLOBAL = 300

#: Quinze minutos. Bloqueio permanente é negação de serviço com outro nome.
JANELA_MINUTOS = 15

#: A tabela só cresce se ninguém apagar. Uma hora cobre a janela com folga.
RETENCAO_MINUTOS = 60

CHAVE_GLOBAL = "global"


def _desde():
    return timezone.now() - timezone.timedelta(minutes=JANELA_MINUTOS)


def _chave_do_par(email, ip):
    return _hmac(normalizar_email(email) + "|" + ip)


def _contar(tipo, chave):
    return TentativaDeEntrada.objects.filter(
        tipo=tipo, chave=chave, criado_em__gte=_desde()
    ).count()


def falhas_de(*, email, ip):
    """Quantas falhas este par (origem, e-mail) tem na janela. Para teste."""
    return _contar("origem+email", _chave_do_par(email, ip))


def pode_tentar(*, email, ip):
    """Só CONSULTA.

    Uma tentativa barrada não registra falha: se registrasse, o próprio limite
    empurraria a janela para frente e o bloqueio nunca terminaria — que é como
    um limite vira negação de serviço permanente sem ninguém decidir isso.
    """
    if _contar("global", CHAVE_GLOBAL) >= LIMITE_GLOBAL:
        return False
    if _contar("origem", _hmac(ip)) >= LIMITE_POR_ORIGEM:
        return False
    return _contar("origem+email", _chave_do_par(email, ip)) < LIMITE_POR_ORIGEM_E_EMAIL


def registrar_falha(*, email, ip):
    """Uma falha vira três linhas — uma por limite.

    Três linhas em vez de uma consulta agregada porque cada limite tem janela e
    teto próprios, e porque somar por tipo é o que permite investigar depois
    qual deles pegou o abuso.
    """
    TentativaDeEntrada.objects.bulk_create(
        [
            TentativaDeEntrada(tipo="origem+email", chave=_chave_do_par(email, ip)),
            TentativaDeEntrada(tipo="origem", chave=_hmac(ip)),
            TentativaDeEntrada(tipo="global", chave=CHAVE_GLOBAL),
        ]
    )
    _limpar_antigos()


def limpar_apos_sucesso(*, email, ip):
    """Apaga as falhas do PAR, e só dele.

    Não apaga as de origem nem a global: quem acertou uma senha não desfaz a
    varredura que estava fazendo nas outras contas. Apagar as três seria dar ao
    atacante uma tecla para zerar o contador — basta ele ter uma conta própria.
    """
    TentativaDeEntrada.objects.filter(
        tipo="origem+email", chave=_chave_do_par(email, ip)
    ).delete()


def _limpar_antigos():
    """Na própria escrita, porque o projeto não tem agendador.

    O DELETE filtra por `criado_em`, que está no índice composto, e no caso
    normal não casa com nada — o planejador varre o índice, não encontra linha
    e volta. Mesma decisão de `limites.limpar_antigos`, e pelo mesmo motivo:
    uma tabela que só cresce vira problema silencioso de disco num banco
    gratuito.
    """
    limite = timezone.now() - timezone.timedelta(minutes=RETENCAO_MINUTOS)
    TentativaDeEntrada.objects.filter(criado_em__lt=limite).delete()
