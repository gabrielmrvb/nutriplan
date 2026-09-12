"""Grátis e Pro: UM lugar decide o que cada plano alcança.

A missão mestre (§37) pede a arquitetura do freemium — Grátis com base
funcional suficiente e Pro a R$ 19,90/mês — SEM fingir cobrança: não existe
pagamento neste repositório, e este módulo não inventa um. O que ele faz é
menor e é o que precisa existir antes de qualquer cobrança:

  - `Recurso` nomeia o que pode ser Pro. É uma lista fechada, e é por isso que
    é um `TextChoices` e não string solta: `tem_acesso(user, "exportacao")`
    com um nome errado levanta, em vez de devolver `False` para sempre.
  - `RECURSOS_PRO` é o que o plano Grátis NÃO alcança. Hoje está VAZIO de
    propósito: nenhuma função que funciona para todo mundo passa a ser
    cobrada por este commit — "não bloquear funções básicas essenciais de
    forma predatória" (§37). Mover um recurso para cá é decisão de produto,
    tem de vir com a data, e é uma linha.
  - `tem_acesso` é a ÚNICA pergunta. Template lê `recursos.<nome>` do context
    processor; view usa `ExigeRecurso`. Nada de `if perfil.plano == "pro"`
    espalhado — `accounts/test_gates.py` varre o repositório e reprova quem
    decidir por conta própria.

O plano mora em `Profile.plano`, e só o admin (ou um comando) o escreve:
até a cobrança existir, é o dono quem promove alguém a Pro, à mão. Quando o
pagamento entrar, ele escreve o mesmo campo — e nada nas telas muda.
"""
from django.core.exceptions import PermissionDenied
from django.db import models


class Plano(models.TextChoices):
    GRATIS = "gratis", "Grátis"
    PRO = "pro", "Pro"


class Recurso(models.TextChoices):
    """O que PODE ser Pro. Estar aqui não torna Pro — ver `RECURSOS_PRO`."""

    RECALCULO_AVANCADO = "recalculo_avancado", "Recálculo avançado"
    RECEITAS_EXTRAS = "receitas_extras", "Receitas extras"
    TREINO_AVANCADO = "treino_avancado", "Treino avançado"
    ANALISES = "analises", "Análises"
    HISTORICO_COMPLETO = "historico_completo", "Histórico completo"
    METAS_AVANCADAS = "metas_avancadas", "Metas avançadas"
    EXPORTACAO = "exportacao", "Exportação"
    CORRIDA_AVANCADA = "corrida_avancada", "Corrida avançada"


#: O que o Grátis NÃO alcança. Vazio em 12/09/2026: a arquitetura entra
#: antes da primeira cobrança, e cobrar o que hoje é de todo mundo seria
#: tirar, não vender. Quando um recurso entrar aqui, o `tem_acesso` dele
#: passa a ser `False` para quem é Grátis — em toda tela e toda rota, de uma
#: vez, porque só existe um lugar que responde.
RECURSOS_PRO: frozenset = frozenset()

#: Preço de referência, em centavos, para a tela que um dia oferecer o Pro.
#: Aqui e não no template: é o único número do freemium, e dois lugares é
#: como um deles envelhece.
PRECO_PRO_CENTAVOS = 1990


def plano_de(user) -> str:
    """O plano da pessoa; Grátis para quem não tem perfil ou não está logado."""
    perfil = getattr(user, "profile", None) if user is not None else None
    return getattr(perfil, "plano", None) or Plano.GRATIS


def tem_acesso(user, recurso) -> bool:
    """A única pergunta do freemium.

    `recurso` tem de ser um `Recurso`: string desconhecida é bug de quem
    chamou e levanta, porque devolver `False` deixaria uma tela bloqueada
    para sempre por um erro de digitação.
    """
    recurso = Recurso(recurso)
    if recurso not in RECURSOS_PRO:
        return True
    return plano_de(user) == Plano.PRO


def recursos_de(user) -> dict:
    """`{nome: bool}` para o template — `{% if recursos.exportacao %}`."""
    return {r.value: tem_acesso(user, r) for r in Recurso}


class ExigeRecurso:
    """Mixin de view: quem não alcança o recurso recebe 403, com mensagem.

    403 e não 302 para uma oferta: a rota de um recurso Pro pedida por POST
    direto por quem é Grátis não pode EXECUTAR e responder "veja o Pro" — é o
    caso de §76 ("como usuário Free pode acessar Pro por POST/URL?"). A tela
    de oferta, quando existir, mora no template que esconde o botão; a view
    só sabe recusar.
    """

    recurso = None

    def dispatch(self, request, *args, **kwargs):
        if self.recurso is None:
            raise ValueError("%s declara ExigeRecurso sem `recurso`" % type(self).__name__)
        if not tem_acesso(request.user, self.recurso):
            raise PermissionDenied(
                "%s faz parte do NutriPlan Pro." % Recurso(self.recurso).label
            )
        return super().dispatch(request, *args, **kwargs)
