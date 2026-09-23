"""Telas do plano: a meta, o cardápio do dia e o acompanhamento.

A rota `today` concentra o uso diário — meta, refeições e marcação — porque é
a única tela que a pessoa abre várias vezes por dia. O histórico fica numa
rota separada, que é consulta ocasional.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.urls import reverse
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.core.cache import cache
from django.db.models import Exists, F, OuterRef, Value, prefetch_related_objects
from django.db.models.functions import Greatest, Least
from django.utils import timezone

from .porcoes import PORCAO_ESCRITA, PORCOES, passos_do_preparo, porcao_valida
from .weight_trend import TETO_DIARIO_ML
from django.views import View
from django.views.generic import TemplateView, View

from accounts.models import (
    ACTIVITY_FACTORS,
    CAMPO_DO_PILAR,
    Goal,
    Pilar,
    SyncedOperation,
    WeightEntry,
)
from accounts.views import OnboardingRequiredMixin, recusa_pendente
from achievements import services as conquistas
from catalog.models import Food

from workouts import progresso
from workouts.models import Corrida

from . import calculations, rodizio, services, shopping, streaks, tracking, weight_trend
from . import agora as agora_mod
from analytics import servidor as analytics
from workouts import services as treino_services
from .calculations import (
    KCAL_PER_G_CARB,
    KCAL_PER_G_FAT,
    KCAL_PER_G_PROTEIN,
    activity_factor,
)
from .models import (
    GoleDeAgua,
    HydrationLog,
    MealLog,
    MealOption,
    MealSlot,
    MealStatus,
    OptionLabel,
    ItemAvulsoDaLista,
    ItemDaListaMarcado,
)
# A política de arredondamento mora em `tracking` e é importada, não repetida:
# duas cópias da mesma regra é como as duas nasceram diferentes.
from .tracking import ZERO, arredondar
from config.acoes import AcaoDeTela


def proteina_perdida(slots) -> dict:
    """O que as refeições puladas custaram em proteína, hoje.

    Só proteína, e isso é escolha. Carboidrato pulado a pessoa recupera no
    almoço sem pensar; proteína pulada não volta — é o macro com alvo
    absoluto, o que preserva massa magra no déficit, e o único em que ficar 30
    g abaixo importa de verdade.

    Mostrar o número no lugar de um aviso genérico é o ponto: "você pulou uma
    refeição" não muda comportamento nenhum; "faltam 41 g de proteína, o
    equivalente a 130 g de frango" diz o que fazer no jantar.
    """
    puladas = [s for s in slots if getattr(s, "log", None) and s.log.status == MealStatus.SKIPPED]
    if not puladas:
        return {}

    gramas = sum(s.target_protein_g for s in puladas)
    return {
        "refeicoes": len(puladas),
        "nomes": [s.name for s in puladas],
        "gramas": gramas,
        # Uma tradução para comida: 100 g de peito de frango têm ~31 g de
        # proteína. Grama de macro é abstrato; "130 g de frango" é jantar.
        "equivalente_frango_g": int(round(gramas / Decimal("0.31"), -1)),
    }


def _proteina_no_rumo(plan, summary):
    """"no_rumo", "atras" ou None — a proteína acompanha as calorias do dia?

    A auditoria pediu que o topo respondesse depois de registrar ("1 de 5 ·
    faltam 2.372 kcal · proteína no rumo"). A frase só pode existir se houver
    uma régua, e a régua aqui é COMPARATIVA: quem já comeu 40% da caloria do
    dia deveria ter comido perto de 40% da proteína.

    Ela devolve `None` sem nada registrado — não há o que comparar — e sem
    meta de proteína, que é o caso do plano antigo sem macro. A tolerância de
    10 pontos existe porque um café da manhã de pão e café fica naturalmente
    atrás em proteína sem que o dia esteja perdido; abaixo disso a frase
    viraria alarme em toda manhã.
    """
    alvo_p = getattr(plan, "protein_g", 0) or 0
    alvo_kcal = summary.get("target_kcal") or 0
    if not summary.get("marked") or not alvo_p or not alvo_kcal:
        return None
    fracao_p = Decimal(summary.get("protein_g", 0) or 0) / Decimal(alvo_p)
    fracao_kcal = Decimal(summary.get("consumed_kcal", 0) or 0) / Decimal(alvo_kcal)
    return "no_rumo" if fracao_p >= fracao_kcal - Decimal("0.1") else "atras"


def macro_rows(plan, summary=None):
    """Os três macros prontos para a tela.

    Quando o resumo do dia vem junto, cada macro sai com o quanto já foi comido
    e a barra de progresso correspondente — é a leitura que a pessoa faz várias
    vezes por dia ("falta proteína?"), e ela não deveria exigir subtração
    mental na tela.
    """
    total = plan.target_kcal or 1
    rows = [
        ("Proteína", plan.protein_g, KCAL_PER_G_PROTEIN, "protein", "protein_g"),
        ("Carboidrato", plan.carb_g, KCAL_PER_G_CARB, "carb", "carb_g"),
        ("Gordura", plan.fat_g, KCAL_PER_G_FAT, "fat", "fat_g"),
    ]
    macros = []
    for name, grams, kcal_per_g, slug, key in rows:
        eaten = (summary or {}).get(key, 0)
        left = max(grams - eaten, 0)
        acima = max(eaten - grams, 0)
        macros.append(
            {
                "name": name,
                "grams": grams,
                # `kcal` e `pct` descrevem a META, e `pct` é a participação
                # daquele macro no orçamento calórico do dia. Isso está certo,
                # e é o que a barra empilhada precisa: os três somam 100%.
                #
                # O defeito não estava aqui — estava na FRASE embaixo dela, que
                # dizia "faltam X g · Y kcal · Z% da meta" reunindo três
                # semânticas incompatíveis. Com 39 de 146 g de proteína saía
                # "faltam 107 g · 584 kcal · 21% da meta": 584 é a meta inteira
                # vezes quatro, e 21% é quanto a proteína pesa no dia. Só o
                # primeiro número respondia "quanto falta".
                "kcal": grams * kcal_per_g,
                "pct": round(grams * kcal_per_g * 100 / total),
                "slug": slug,
                "eaten": eaten,
                # Limitado a 100 porque é a largura da barra de progresso.
                # O texto ao lado mostra `eaten / grams` sem limite, então
                # ultrapassar a meta continua visível.
                "eaten_pct": min(round(eaten * 100 / (grams or 1)), 100),
                "left": left,
                # O par de `left`. Fica AQUI e não no template porque o fator
                # muda por macro — 4 kcal/g para proteína e carboidrato, 9 para
                # gordura — e um `×4` escrito no HTML mentiria na linha da
                # gordura no dia em que alguém reaproveitasse o trecho.
                "left_kcal": left * kcal_per_g,
                "batido": eaten >= grams and grams > 0,
                "acima": acima,
            }
        )
    return macros


#: Convenção clássica: 1 kg de gordura corporal ≈ 7.700 kcal. É estimativa, não
#: lei — serve para transformar "-500 kcal por dia" em "meio quilo por semana",
#: que é a única forma de a pessoa saber se o ritmo dela faz sentido.
KCAL_PER_KG = 7700

#: Diferença entre o cardápio e a meta que a tela trata como "bateu". Quarenta
#: kcal é menos que uma colher de arroz — abaixo disso a precisão é ilusória,
#: porque a própria tabela nutricional do alimento tem erro maior que esse.
MENU_TOLERANCE_KCAL = 40

ENERGY_BALANCE_LABEL = {
    "deficit": "Déficit diário recomendado",
    "surplus": "Superávit diário recomendado",
    "balance": "Sem déficit nem superávit",
    # O quarto caso: a meta subiu porque bateu no piso de segurança, e o sinal
    # da conta ficou positivo mesmo com objetivo de emagrecer. Chamar isso de
    # "superávit recomendado" seria a tela recomendar o contrário do que a
    # pessoa pediu.
    "piso": "Meta no mínimo seguro",
}


def energy_balance(plan) -> dict:
    """A diferença entre o que a pessoa gasta e o que ela vai comer.

    É o número que explica a dieta inteira em uma linha: emagrecer é comer
    abaixo do gasto, ganhar massa é comer acima. A tela mostra ele com o sinal
    na frente (-513 kcal) porque déficit e superávit são a mesma conta em
    sentidos opostos, e esconder o sinal obrigaria a pessoa a descobrir de
    cabeça de que lado ela está.

    O ritmo semanal em quilos vem junto: sem ele, "-500 kcal por dia" é um
    número abstrato; com ele, a pessoa consegue julgar se o plano é rápido
    demais ou lento demais para ela.
    """
    delta = plan.target_kcal - plan.tdee_kcal
    kind = "deficit" if delta < 0 else "surplus" if delta > 0 else "balance"

    # O PISO DE SEGURANÇA VENCE O SINAL DA CONTA.
    #
    # `target_kcal` eleva a meta quando o déficit cheio ficaria abaixo da taxa
    # basal ou do mínimo clínico. Em gente pequena isso passa do gasto: mulher
    # de 45 kg, 150 cm e 60 anos, sedentária, tem gasto 1.158 e meta 1.200 —
    # +42 kcal. Esta função lia só o sinal e devolvia "Superávit diário
    # recomendado" para quem escolheu Emagrecer, treze linhas acima da nota do
    # plano dizendo "o emagrecimento fica mais lento, e mais seguro". A mesma
    # tela afirmava as duas coisas.
    #
    # A PERGUNTA CERTA É "HOUVE PISO?", e quem sabe responder é o motor. A
    # primeira correção nomeava o objetivo na condição e cobria um de três:
    # Recomposição e Manutenção continuavam com o defeito, porque as duas
    # também batem no piso nesse perfil. Nomear objetivo aqui é o que fez o
    # defeito nascer, e é o que faria o próximo objetivo novo nascer com ele.
    # Achado em revisão adversarial desta própria correção.
    if delta >= 0 and calculations.piso_elevou(plan.tdee_kcal, plan.goal, plan.target_kcal):
        kind = "piso"

    return {
        "kind": kind,
        "label": ENERGY_BALANCE_LABEL[kind],
        "delta_kcal": delta,
        "abs_kcal": abs(delta),
        "pct": round(abs(delta) * 100 / (plan.tdee_kcal or 1)),
        "weekly_kcal": delta * 7,
        "weekly_kg": round(abs(delta) * 7 / KCAL_PER_KG, 2),
        "tdee_kcal": plan.tdee_kcal,
        "target_kcal": plan.target_kcal,
    }


def menu_totals(slots) -> dict:
    """Soma do cardápio seguindo a Opção A de cada refeição.

    Serve de prova na tela de que o cardápio realmente fecha na meta: os alvos
    por horário somam a meta por construção, mas a receita escalada pode parar
    um pouco antes quando a porção chegaria ao limite do que é comida de
    verdade. Mostrar a soma real, e não só a pretendida, é o que deixa isso
    visível em vez de escondido.

    "Opção A" é a primeira opção PROJETADA para hoje, e não a primeira do
    repertório: é a que a pessoa está vendo na tela, e o total precisa somar o
    cardápio que ela tem diante dos olhos. Lê `slot.opcoes_do_dia`, que
    `rodizio.projetar` já pendurou — recalcular aqui daria uma segunda resposta
    para a mesma pergunta.
    """
    # Soma em `Decimal` e arredonda UMA vez, no fim. A versão anterior fazia
    # `int(option.kcal)` por refeição: cinco truncamentos antes da soma, até 5
    # kcal perdidas, e o rodapé do cardápio não batia com os cards logo acima
    # dele — que exibem o mesmo número via `floatformat`, que arredonda.
    totals = {"kcal": ZERO, "protein_g": ZERO, "carb_g": ZERO, "fat_g": ZERO}
    for slot in slots:
        # `slot.opcoes_do_dia` sem `getattr` com padrão, e isto é deliberado:
        # quem esquecer de chamar `rodizio.projetar` antes leva um
        # AttributeError na cara. A primeira versão usava padrão vazio e o
        # resultado foi um cardápio somando ZERO kcal em silêncio — a tela
        # diria que o dia inteiro tem 0 de 2 400, e nada acusaria.
        option = next(iter(slot.opcoes_do_dia), None)
        if option is None:
            continue
        totals["kcal"] += option.kcal
        totals["protein_g"] += option.protein_g
        totals["carb_g"] += option.carb_g
        totals["fat_g"] += option.fat_g
    return {chave: arredondar(valor) for chave, valor in totals.items()}


def breakdown(plan):
    """Passo a passo do cálculo, montado só com dados congelados no plano.

    O fator é recalculado a partir das entradas do plano em vez de guardado num
    campo: dois números que dizem a mesma coisa acabam discordando um dia, e
    aqui o plano já guarda tudo que a conta precisa (nível e frequência).
    """
    factor = activity_factor(plan.activity_level, plan.training_days_per_week)
    minimo, maximo = ACTIVITY_FACTORS[plan.activity_level]
    ajuste = plan.target_kcal - plan.tdee_kcal
    return {
        "bmr_kcal": plan.bmr_kcal,
        "activity_factor": factor.quantize(Decimal("0.01")),
        "factor_min": minimo,
        "factor_max": maximo,
        "training_days": plan.training_days_per_week,
        "tdee_kcal": plan.tdee_kcal,
        "adjustment_pct": round(abs(ajuste) * 100 / (plan.tdee_kcal or 1)),
        "adjustment_kcal": ajuste,
    }


class PlanRequiredMixin(OnboardingRequiredMixin):
    """Coloca o plano ativo (recalculando se necessário) em self.plan.

    A sincronização acontece na entrada da tela, e não no fim do onboarding,
    porque assim ela cobre qualquer origem de mudança — wizard, admin, um
    registro de peso novo — sem espalhar chamadas de recálculo pelo código.
    """

    def get_plan(self, request):
        plan, changed = services.sync_active_plan(request.user)
        if changed and request.user.plans.count() > 1:
            messages.info(
                request, "Seus dados mudaram, então recalculamos sua meta."
            )
        return plan


#: Quantas pesagens a Home lê de uma vez: o peso de hoje para o cálculo e as
#: datas da semana para o convite — uma por dia, sete dias.
PESAGENS_LIDAS = 7

#: Por quanto tempo o `<datalist>` de alimentos vive em cache, por processo.
#: O catálogo muda no deploy (`seed_catalog`, que reinicia o processo) ou
#: por edição no admin; quinze minutos é o preço de um alimento novo demorar
#: a aparecer na sugestão de "comi outra coisa" — contra uma consulta ao
#: catálogo inteiro a cada abertura da Home.
CACHE_DO_CATALOGO_S = 15 * 60


def agua_e_desfazer(user, inicio, hoje) -> tuple:
    """A água por dia desde `inicio` E se há gole de hoje para desfazer, numa
    consulta: a pergunta do "desfazer" entra como `Exists` na linha de hoje
    (`HydrationLog` é uma por dia). Existe gole para desfazer NÃO é o mesmo
    que `bebido > 0`: um dia anterior à tabela de goles tem total e não tem
    composição, e mostrar "desfazer" ali ofereceria uma ação que só pode
    falhar."""
    linhas = (
        HydrationLog.objects.filter(user=user, date__gte=inicio)
        .annotate(tem_gole=Exists(GoleDeAgua.objects.filter(user=OuterRef("user"), dia=OuterRef("date"))))
        .values_list("date", "ml", "tem_gole")
    )
    por_dia, desfazer = {}, False
    for data, ml, tem_gole in linhas:
        por_dia[data] = ml or 0
        if data == hoje:
            desfazer = bool(tem_gole)
    return por_dia, desfazer


def alimentos_do_catalogo() -> list:
    """Os nomes do catálogo para o `<datalist>` de "comi outra coisa"."""
    nomes = cache.get("plans.alimentos_do_catalogo")
    if nomes is None:
        nomes = list(Food.objects.filter(is_active=True).order_by("name").values_list("name", flat=True))
        cache.set("plans.alimentos_do_catalogo", nomes, CACHE_DO_CATALOGO_S)
    return nomes


def relogio():
    """A hora local que a tela Hoje usa para decidir o cartão AGORA e os selos.

    Existe para ser CONGELADA em teste. A Home é a única tela cujo conteúdo
    muda com o relógio de parede — refeição vencida, treino de hoje, água
    atrás do esperado —, e dois testes passavam de dia e reprovavam de noite:
    depois da última refeição não há "refeição futura", e depois do jantar a
    refeição vencida passa na frente do treino das 19h. O `pre-push` de
    14/09/2026 às 20h44 pegou os dois. Um teste que lê a hora da máquina não
    está medindo a tela; está medindo a hora.
    """
    return timezone.localtime()


class LandingView(TemplateView):
    """A porta de entrada para quem ainda não tem conta (decisão 2, 20/09/2026).

    Uma frase do que o produto é, três provas do app e três saídas: a
    demonstração pública (o produto de verdade, sempre atual — a prova que
    nunca envelhece), criar conta, e — discreto — entrar. O login saiu da raiz:
    chega-se a ele por um link daqui, não por um redirect na cara de quem só
    queria saber o que o app faz.

    Sem barra de abas nem convite de instalação: quem não entrou não tem para
    onde navegar, e a barra prometeria destinos que exigem login. É a mesma
    razão de `tela_de_entrada` no login.
    """

    template_name = "plans/landing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sem_tabbar"] = True
        context["sem_convite"] = True
        context["tela_de_entrada"] = True
        return context


class RaizView(View):
    """A raiz decide pelo visitante: anônimo vê a landing, quem tem sessão vê o app.

    Fica com o nome `plans:today` — a raiz canônica — para que todo
    `reverse("plans:today")` continue apontando para `/`, o pós-login continue
    caindo no painel do dia e o mapa/onboarding não mudem de endereço. O ramo
    autenticado delega para `TodayView`, que mantém as próprias guardas
    (onboarding e plano).

    O DEMO NÃO CAI NA LANDING: sob o prefixo `/demo/` o middleware troca
    `request.user` pela persona (autenticada), então `/demo/hoje/` cai no ramo
    do app; e `/demo/` (a capa) é servida direto pelo middleware, sem passar
    por aqui. Há teste para os dois.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return TodayView.as_view()(request, *args, **kwargs)
        return LandingView.as_view()(request, *args, **kwargs)


#: A ordem canônica dos cartões do painel do dia — a mesma de `Pilar`.
CARTOES_DO_PAINEL = ("dieta", "treino", "hidratacao", "corrida", "progresso")

#: Os dois que só entram para quem DECLAROU a área. Alimentação, Treino e
#: Hidratação são o dia de qualquer pessoa — todo mundo come, treina (ou
#: descansa, que é o plano) e bebe água. Corrida e Progresso não: quem não
#: corre não tem "última corrida", e quem não acompanha peso não tem pesagem.
#: Um cartão vazio nessas duas seria a grade cobrando espaço para dizer
#: "nada aqui" — e a auditoria de 22/09/2026 chama isso de cartão com buraco.
CARTOES_DECLARADOS = ("corrida", "progresso")


def cartoes_do_painel(prioridade, *, declarados=()) -> list:
    """Os cartões do painel: qual, em que ordem, e qual ocupa a linha inteira
    no celular.

    A promoção da área principal deixou de mover seções de meia tela e virou
    ORDEM dentro da grade (22/09/2026). O contrato de produto é o mesmo de
    antes e continua tendo teste: interesse ORGANIZA e nunca restringe —
    nenhuma área some por não ter sido escolhida, e quem não declarou nada vê
    a ordem canônica.

    `largo` é layout decidido no servidor, e não no CSS, porque depende de
    CONTAR os cartões: a grade do celular tem duas colunas, e com um número
    ÍMPAR deles o último ficaria sozinho ao lado de meia célula vazia — o
    buraco que a auditoria de 22/09/2026 aponta em outras telas. É o único
    caso: a grade do celular é 2×2 para quem corre e 2+1 para quem não corre.
    No desktop são tantas colunas quantos cartões e ninguém é largo — a regra
    do CSS desliga o caso acima de 60rem.

    A Hidratação já precisou da linha inteira em toda largura: os três passos
    de 44px não cabiam na célula. Hoje cabem, porque os botões são uma linha
    que quebra quando três não cabem (medido em 22/09/2026: 65px por botão a
    390px, 50px a 320px, sempre acima da régua de 44).

    `declarados` são os pilares em que a pessoa marcou interesse. Ele decide
    SÓ os dois opcionais (`CARTOES_DECLARADOS`) — interesse organiza e não
    restringe, então não declarar Alimentação não tira o cartão do cardápio.
    """
    chaves = [
        c for c in CARTOES_DO_PAINEL
        if c not in CARTOES_DECLARADOS or c in declarados
    ]
    if prioridade in chaves:
        chaves.remove(prioridade)
        chaves.insert(0, prioridade)
    sozinho = chaves[-1] if len(chaves) % 2 else None
    return [{"chave": c, "largo": c == sozinho} for c in chaves]


class TodayView(PlanRequiredMixin, TemplateView):
    """A tela HOJE: o orquestrador do dia (o painel de quatro cartões).

    Ela e a `AlimentacaoView` computam o MESMO contexto, e isso é decisão: as
    duas telas respondem sobre o mesmo dia, e o dia é lido uma vez por
    pedido. O que separa as duas é o template e dois extras que só a
    Alimentação usa (o catálogo do `<datalist>` e a proteína perdida), ambos
    atrás de `mostra_cardapio` — a Home não paga consulta por eles.
    """

    template_name = "plans/today.html"
    nav = "today"
    #: A Alimentação liga isto. Ver `get_context_data`.
    mostra_cardapio = False

    def get_plan(self, request):
        """O plano E o cardápio, lidos uma vez (`services.plano_do_dia`)."""
        peso = self.pesagens[0].weight_kg if self.pesagens else None
        plan, self.slots, changed = services.plano_do_dia(request.user, peso_kg=peso)
        if changed and request.user.plans.count() > 1:
            messages.info(request, "Seus dados mudaram, então recalculamos sua meta.")
        return plan

    def get(self, request, *args, **kwargs):
        # Os dias de treino, UMA vez: `build_inputs` (a duração de cada
        # sessão) e "Dados do cálculo" no template leem a mesma lista, e
        # sem o pré-carregamento cada um abria a sua consulta.
        prefetch_related_objects([request.user], "training_days")
        # As últimas pesagens, UMA vez: o peso mais recente entra no cálculo
        # (`build_inputs`) e as datas da semana no convite de pesar. Sete
        # bastam para as duas perguntas — uma pesagem por dia, sete dias.
        self.pesagens = list(request.user.weight_entries.order_by("-date", "-pk")[:PESAGENS_LIDAS])
        try:
            self.plan = self.get_plan(request)
        except services.IncompleteProfile:
            # Sem mensagem aqui: quem sabe POR QUE a pessoa esta voltando para
            # o wizard e a entrada do onboarding, que e quem escolhe o passo.
            # Com as duas falando, a tela abria com dois avisos quase iguais
            # empilhados — e no bug do loop, com trinta.
            return redirect("accounts:onboarding")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        logs = tracking.logs_by_slot(self.request.user, today)
        slots = self.slots  # lidos junto com o plano, em `get_plan`
        for slot in slots:
            # O log vira atributo do slot para o template não precisar de um
            # filtro de dicionário — a linguagem de template não indexa por
            # variável, e criar um filtro só para isso é peso morto.
            slot.log = logs.get(slot.pk)

        # A projeção do dia, uma vez, para todos os consumidores desta tela.
        # `today` é `timezone.localdate()`, calculado no topo do método: a data
        # local do projeto, e não a data do servidor em UTC. Quem entra às 21h
        # de Brasília já estaria no dia seguinte em UTC, e o cardápio trocaria
        # três horas antes da meia-noite dele.
        rodizio.projetar(slots, self.request.user.pk, today)

        # `weight_kg` sai do plano ATIVO, já em mãos aqui — não do perfil: é o
        # peso congelado que gerou a meta de hoje, e passá-lo poupa a tela de
        # uma consulta extra ao perfil dentro de `day_summary`.
        # UMA LEITURA POR TABELA (21/09/2026; `plans/test_orcamento_da_home`):
        # água, corridas e o histórico de treino são lidos aqui, uma vez, no
        # período que a ofensiva olha, e o cartão de água, o resumo do dia e
        # a ofensiva recebem a mesma leitura. Antes cada um abria a sua.
        inicio_da_ofensiva = streaks.inicio_do_historico(today)
        agua_por_dia, pode_desfazer_agua = agua_e_desfazer(self.request.user, inicio_da_ofensiva, today)
        corridas = list(
            Corrida.objects.filter(
                user=self.request.user, comecou_em__date__gte=inicio_da_ofensiva
            ).values_list("comecou_em", "distancia_m")
        )
        corridas_de_hoje_m = [
            distancia for comecou, distancia in corridas
            if timezone.localtime(comecou).date() == today
        ]
        summary = tracking.day_summary(
            self.request.user, self.plan, today, peso_kg=self.plan.weight_kg,
            logs=logs, slots=slots, corridas_m=corridas_de_hoje_m,
        )
        menu = menu_totals(slots)

        recusa = recusa_pendente(self.request, "hoje")
        meta_agua = weight_trend.hidratacao_ml(self.plan.weight_kg)
        bebido = agua_por_dia.get(today, 0)  # a leitura de água de cima

        # Existe gole para desfazer? A pergunta é `exists()` e não a contagem:
        # a tela só precisa saber se o botão aparece.
        #
        # Isto NÃO é o mesmo que `bebido > 0`. Um dia anterior à tabela de goles
        # tem total e não tem composição — mostrar "desfazer" ali ofereceria uma
        # ação que só pode falhar.

        # O estado do treino de hoje é CONSUMIDO do Treino V3, não recalculado.
        #
        # `estado_do_treino` deriva tudo de `ExerciseLog` e não escreve nada —
        # e não chama `sync_active_routine`: montar rotina é trabalho da aba de
        # treino, e fazer isso aqui daria à tela de comida o poder de criar
        # ficha como efeito colateral de uma visita.
        estado_treino = treino_services.estado_do_treino(self.request.user, dia=today)
        # "Seu treino pode ficar mais completo — regenerar?": só quando o
        # catálogo mudou embaixo de uma ficha válida e a pessoa ainda não
        # dispensou (17/09/2026). Com a ficha nascida deste catálogo custa
        # ZERO consultas (a impressão digital está no plano, que o estado
        # já carregou); com ficha de antes ou de outro catálogo, a
        # conferência exata da prescrição — medido em `plans.test_stress`.
        aviso_regenerar = (
            estado_treino.tem_ficha
            and treino_services.aviso_de_regenerar(self.request.user, plan=estado_treino.plan)
        )

        # `localtime()` e não `datetime.now()`: o servidor roda em UTC e o
        # horário das refeições é o do fuso da pessoa. Sem isso o "agora" erra
        # por três horas, e a tela mostraria o almoço como ação às nove da
        # manhã.
        # O convite de pesagem sai daqui, e não de dentro do dicionário de
        # contexto, porque agora DUAS coisas o leem: o cartão do topo e a faixa
        # de pesagem. Duas chamadas dariam duas respostas na virada do dia, e a
        # tela mostraria um cartão pedindo o peso ao lado de uma faixa fechada.
        convite_pesagem = weight_trend.convidar_a_pesar(
            self.request.user, hoje=today, pesagens=self.pesagens
        )

        # A prioridade declarada é MAIS UM SINAL, e entra como argumento em vez
        # de ser lida lá dentro: `proxima_acao` é uma função pura, e é isso que
        # deixa `plans/test_agua_no_agora.py` provar a regra sem banco.
        # `request.user.profile` — em cache desde o `dispatch` —, e não
        # `self.plan.user.profile`: `plan.user` é OUTRA instância do usuário,
        # e cada acesso custava duas consultas (o usuário e o perfil de novo).
        perfil = self.request.user.profile
        prioridade = getattr(perfil, "prioridade", "")
        # AS ÁREAS QUE A PESSOA DECLAROU. São os mesmos campos do onboarding —
        # nada é inferido de histórico: quem nunca marcou Corrida não recebe o
        # cartão de corrida, e nenhuma corrida registrada o faz aparecer
        # sozinho. É a doutrina de "uso não é intenção declarada", do outro
        # lado da tela.
        declarados = {
            pilar for pilar, campo in CAMPO_DO_PILAR.items()
            if getattr(perfil, campo, False)
        }

        # O conteúdo dos dois cartões OPCIONAIS, e só deles. Treino já está em
        # `estado_treino` e o convite de pesagem já foi calculado acima — os
        # dois custam zero aqui. Corrida e Progresso custam UMA consulta cada,
        # e só para quem declarou aquela área: a Home é a tela mais aberta do
        # app, e carregar as duas para todo mundo seria cobrar de quem nunca
        # respondeu a pergunta.
        #
        # Em 22/09/2026 a condição deixou de ser "elegeu como área principal"
        # e passou a ser "declarou interesse": o cartão é do painel, e o
        # painel mostra as áreas da pessoa — a principal é a primeira delas,
        # não a única.
        ultima_corrida = None
        ultimo_peso = None
        if Pilar.CORRIDA in declarados:
            ultima_corrida = (
                Corrida.objects.filter(user=self.request.user)
                .order_by("-comecou_em")
                .first()
            )
        if Pilar.PROGRESSO in declarados:
            ultimo_peso = self.pesagens[0] if self.pesagens else None

        # UMA leitura do relógio para o topo e para a lista: os dois têm de
        # concordar, e é este instante que os testes congelam (ver `relogio`).
        agora = relogio()
        acao = agora_mod.proxima_acao(
            slots=slots,
            treino=estado_treino,
            meta_agua=meta_agua,
            bebido=bebido,
            agora=agora,
            prioridade=prioridade,
            # Declarar interesse em hidratação sem elegê-la principal não pode
            # PIORAR a hidratação — era o que acontecia, e uma revisão
            # adversarial pegou: quem marcava a área caía no ramo genérico
            # (35 pp) e recebia o aviso mais tarde que quem não declarou nada.
            interesse_em_agua=getattr(
                perfil, CAMPO_DO_PILAR[Pilar.HIDRATACAO], False
            ),
            convite_pesagem=convite_pesagem,
            # No dia do cadastro, refeição de antes da conta existir não
            # cobra (achado #7 das personas). Zero consultas: o usuário já
            # está carregado.
            desde=timezone.localtime(self.request.user.date_joined),
        )
        # A lista concorda com o topo porque LÊ a decisão dele, em vez de
        # refazer a conta.
        agora_mod.marcar_refeicoes(slots, acao, agora, desde=timezone.localtime(self.request.user.date_joined))
        context.update(
            {
                "plan": self.plan,
                "profile": self.request.user.profile,
                "macros": macro_rows(self.plan, summary),
                "breakdown": breakdown(self.plan),
                "balance": energy_balance(self.plan),
                # O SALDO DO PLANO SÓ APARECE DEPOIS DO PRIMEIRO REGISTRO DO DIA.
                #
                # `energy_balance` responde sobre o PLANO — meta menos gasto —,
                # e é um número que não depende de registro nenhum. Mas ele é
                # desenhado dentro de `today-hero__facts`, entre "faltam 2.055
                # kcal" e "0/5 refeições", que são as duas sobre HOJE. Num dia
                # em branco, "Sem déficit nem superávit" lido nessa companhia
                # afirma que o dia fechou empatado — e o app não sabe disso,
                # porque ninguém comeu ainda.
                #
                # A porta é `marked`, e não `consumed_kcal`: quem marcou "Pulei"
                # nas cinco refeições consumiu zero E registrou o dia inteiro.
                # Mandar essa pessoa registrar seria pedir o que ela já fez.
                # Registro ausente e consumo zero são estados diferentes.
                "saldo_do_dia_ja_conta": summary["marked"] > 0,
                # O TOPO CONTA O DIA, E NÃO O ZERO (23/09/2026).
                #
                # Antes da primeira refeição o painel dizia "0 de 2.839",
                # "0/5 refeições" e "P 0 · C 0 · G 0": meia tela de zero, com
                # a única frase útil ("registre para acompanhar") explicando
                # por que não havia nada. A auditoria chamou isso de "o topo
                # conta o zero".
                #
                # `modo` é a resposta em uma palavra: com nada registrado o
                # anel mostra a META e o plano do dia — que é a informação que
                # existe naquele instante —, e a partir da primeira marcação
                # ele passa a mostrar o consumido. Não é um estado vazio com
                # texto de consolo: é outra pergunta, respondida.
                "topo": {
                    "modo": "dia" if summary["marked"] else "plano",
                    # A proteína está acompanhando o dia? A régua é honesta e
                    # comparativa: a fração de proteína já comida contra a
                    # fração de CALORIA já comida. Dizer "no rumo" por um
                    # limiar absoluto (70% às 15h) seria inventar um horário
                    # que o plano de cada pessoa não tem.
                    "proteina": _proteina_no_rumo(self.plan, summary),
                },
                # O TETO DO TREINO, de todo mundo. `duration_min` continua
                # gravado porque este app precisa dele para não marcar refeição
                # no meio do treino, mas ele deixou de ser a resposta da pessoa.
                # `teto_completo_de`, e não `teto_de_minutos`: desde 15/09/2026
                # quem é "sem limite rígido" também tem teto — a sessão
                # completa é de até 65 —, e a Home não dizia nada para essa
                # pessoa. Imprimir os 90 gravados seria inventar promessa; o
                # 65 é o que o motor obedece.
                "teto_do_treino": treino_services.teto_completo_de(self.request.user),
                "menu": menu,
                # Diferença entre o cardápio montado e a meta. A tela mostra
                # "bate com a meta" quando é irrelevante, e o número quando não é.
                "menu_gap": menu["kcal"] - self.plan.target_kcal,
                "menu_on_target": abs(menu["kcal"] - self.plan.target_kcal) <= MENU_TOLERANCE_KCAL,
                "acao": acao,
                "treino_hoje": estado_treino,
                "aviso_regenerar": aviso_regenerar,
                "hidratacao_ml": meta_agua,
                "pode_desfazer_agua": pode_desfazer_agua,
                "hidratacao_bebida": bebido,
                "hidratacao_pct": (
                    min(100, int(bebido * 100 / meta_agua)) if meta_agua else 0
                ),
                "agua_completa": bool(meta_agua) and bebido >= meta_agua,
                "ofensiva": streaks.calcular(
                    self.request.user, hoje=today, meta_agua_ml=meta_agua,
                    ja_lido=streaks.JaLido(
                        previstos={linha.weekday for linha in estado_treino.linhas}
                        if estado_treino.tem_ficha else set(),
                        corridas=[comecou for comecou, _ in corridas],
                        agua_por_dia=agua_por_dia,
                        tem_plano=True,
                    ),
                ),
                # O convite para se pesar. A regra é do domínio e não da view:
                # a view pergunta, `weight_trend` responde. Consulta dirigida à
                # semana — `analisar()` carregaria o histórico inteiro para
                # responder isto, e esta é a tela mais aberta do app.
                "convite_pesagem": convite_pesagem,
                # A prioridade chega ao template para decidir ONDE a seção do
                # pilar aparece — nunca SE ela aparece. Nenhum pilar esconde
                # seção de ninguém.
                "prioridade": prioridade,
                # A área que ganha o alto da tela. É a MESMA string, com outro
                # nome, e a separação é de propósito: `prioridade` é o que a
                # pessoa declarou, `area_promovida` é o que esta tela faz com
                # isso. Sem declaração as duas são vazias e a Home é a de
                # sempre — quem não respondeu não recebe personalização
                # nenhuma, e nada aqui infere intenção de histórico.
                "area_promovida": prioridade,
                # Os fatos da área promovida, consultados SÓ quando ela é a
                # promovida. Quem não declarou não paga consulta nenhuma.
                "ultima_corrida": ultima_corrida,
                "corrida_km": (ultima_corrida.distancia_m / 1000) if ultima_corrida else 0,
                "ultimo_peso": ultimo_peso,
                # `None` quando não há erro pendente DESTA tela; string
                # (às vezes vazia) quando há. `houve_recusa` carrega essa
                # diferença para o template, que não consegue distinguir
                # "sem erro" de "erro com campo em branco" olhando só o texto.
                "houve_recusa": recusa is not None,
                "peso_recusado": recusa.valor if recusa else "",
                "peso_erro": recusa.mensagem if recusa else "",
                # SÓ a Alimentação mostra o cardápio, e só ela paga por
                # estes dois: o catálogo do `<datalist>` é uma consulta, e a
                # proteína perdida uma varredura dos slots.
                "proteina_perdida": proteina_perdida(slots) if self.mostra_cardapio else None,
                # O catálogo do `<datalist>` e as linhas em branco do painel
                # "comi outra coisa". `range` no contexto porque o template do
                # Django não sabe contar, e um `{% for %}` sobre uma lista de
                # três nadas é mais honesto que três blocos copiados.
                "alimentos": alimentos_do_catalogo() if self.mostra_cardapio else (),
                "itens_fora": range(tracking.MAX_ITENS_FORA),
                "nav": self.nav,
                # O PAINEL DO DIA: quais cartões, e em que ordem.
                #
                # Lista no servidor, e não `{% if %}` espalhados pelo
                # template: a ordem é decisão de produto (a área principal
                # primeiro; o resto na ordem canônica de `Pilar`) e precisa de
                # um lugar só, que o teste consiga ler sem varrer HTML.
                #
                # Corrida e Progresso só entram para quem declarou a área;
                # Alimentação, Treino e Hidratação são o dia de qualquer um.
                "painel": cartoes_do_painel(prioridade, declarados=declarados),
                # O selo "sua área" do cartão de água, que é um `{% include %}`
                # e não enxerga `area_promovida` do contexto pai.
                "agua_principal": prioridade == Pilar.HIDRATACAO,
                # O próximo treino, para o cartão dizer "amanhã, B" em vez de
                # só "Descanso". Zero consulta: as linhas do plano já vieram
                # em `estado_do_treino`.
                "proximo_treino": (
                    treino_services.proximo_treino(
                        estado_treino.linhas, estado_treino.plan, today, estado_treino.linhas
                    )
                    if estado_treino.tem_ficha and not estado_treino.tem_treino
                    else None
                ),
                "training_days": self.request.user.training_days.all(),
                "slots": slots,
                "today": today,
                "summary": summary,
            }
        )
        return context


class AlimentacaoView(TodayView):
    """A tela ALIMENTAÇÃO: o cardápio do dia e de onde vem a meta.

    É a tela que o app chamava de "Hoje" até 22/09/2026, com o mesmo conteúdo
    e o mesmo contexto. O que mudou é que ela tem endereço e nome próprios: a
    barra dizia "Alimentação" e levava para uma tela chamada "Hoje" que era a
    tela de dieta com um widget de água pendurado no fim.
    """

    template_name = "plans/alimentacao.html"
    nav = "food"
    mostra_cardapio = True

    #: Quantos itens da lista de compras cabem na prévia da direita.
    #:
    #: Três, e não "os primeiros que couberem": a prévia não é a lista, é o
    #: lembrete de que ela existe. Quem vai ao mercado abre a lista inteira;
    #: quem está olhando o cardápio só precisa saber que a semana já está
    #: contada. Mais do que isso e a coluna de consulta vira uma segunda tela.
    ITENS_NA_PREVIA = 3

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        # O PAINEL DA DIREITA, no desktop, JÁ NASCE COM UMA RECEITA.
        #
        # A coluna media 336px de largura por 1.500px de altura vazia embaixo
        # de três cartões recolhidos — medido a 1280px em 23/09/2026. O que
        # ela passa a mostrar é a receita da refeição da VEZ: a pergunta que
        # a pessoa tem na tela de cardápio, respondida sem tocar em nada.
        #
        # Zero consulta nova para a opção: ela é uma das que a tela já
        # carregou (com `template__items__food__portions` no prefetch), e o
        # registro do dia é o `slot.log` que a tela já leu. `outras` custa
        # UMA, dentro de `contexto_da_receita`.
        contexto["receita_do_painel"] = self._receita_do_painel(contexto.get("slots"))

        contexto["compras"] = self._previa_das_compras()
        return contexto

    #: A ordem em que o painel escolhe a refeição, e ela é a MESMA do cartão
    #: AGORA: a da vez, depois a vencida, depois qualquer uma.
    #:
    #: Medido a 1280px em 23/09/2026: sem a preferência por `agora`, às 10h o
    #: painel mostrava o café das 7h (vencido) enquanto o card aberto ao lado
    #: era o lanche das 10h37 — a coluna de consulta respondendo sobre outra
    #: refeição que não a que está na tela.
    ORDEM_DO_PAINEL = ("agora", "pendente", "")

    def _receita_do_painel(self, slots):
        """A receita que a coluna da direita abre, ou `None` sem cardápio.

        O último degrau é "qualquer uma com opção" — dia inteiro resolvido
        continua tendo a pergunta "como eu faço isso?", e devolver a coluna
        vazia ali seria voltar ao defeito que o painel veio corrigir.
        """
        for estado in self.ORDEM_DO_PAINEL:
            for slot in slots or ():
                opcoes = getattr(slot, "opcoes_do_dia", None) or []
                if not opcoes:
                    continue
                if estado and getattr(slot, "estado", "") != estado:
                    continue
                return contexto_da_receita(opcoes[0], log=getattr(slot, "log", None))
        return None

    def _previa_das_compras(self) -> dict:
        """Três itens e o total, em CACHE de processo — zero consulta na
        visita seguinte.

        A conta é a mesma da tela da lista (`shopping_list`), porque uma
        segunda conta aqui compraria uma semana diferente da que a lista
        mostra. E ela é cara: percorre os sete dias projetando o cardápio de
        cada um, seis consultas medidas. Pagar isso em toda abertura do
        cardápio, para mostrar três nomes, seria 6 das 24 consultas da tela
        gastas num lembrete.

        A chave leva o PLANO e a SEMANA, que são as duas coisas que mudam a
        resposta: plano novo tem pk novo (plano é retrato, nunca editado), e
        a virada da semana troca a janela. Os 15 minutos são o mesmo teto do
        `<datalist>` de alimentos, pela mesma razão — o pior caso é uma
        prévia com quinze minutos de idade ao lado de um link que abre a
        lista exata.

        O cache é por PROCESSO (LocMem, dois workers): cada um paga a
        primeira visita. O que ele não pode é vazar entre pessoas — e não
        vaza, porque `plan.pk` é de uma conta só.
        """
        semana = shopping.dias_da_semana()[0]
        chave = "plans.previa_de_compras:%s:%s" % (self.plan.pk, semana.isoformat())
        previa = cache.get(chave)
        if previa is None:
            corredores = shopping.shopping_list(self.plan, label=OptionLabel.A)
            itens = [item for corredor in corredores for item in corredor["items"]]
            previa = {
                # Só o que a prévia desenha: nome e a forma de compra. Guardar
                # o `Food` inteiro poria um objeto do ORM no cache, que é como
                # se guarda uma linha velha sem perceber.
                "primeiros": [
                    {"nome": item["food"].name, "display": item["display"]}
                    for item in itens[: self.ITENS_NA_PREVIA]
                ],
                "total": len(itens),
                "restantes": max(len(itens) - self.ITENS_NA_PREVIA, 0),
            }
            cache.set(chave, previa, CACHE_DO_CATALOGO_S)
        return previa


#: A tela Hoje tem 4 a 5 dobras, e toda escrita dela era um POST/redirect que
#: devolvia a pessoa ao TOPO. Medido no navegador, em 375x812: o cartão de água
#: começa em y=2491, e cada "+250" custava rolar 2500px, tocar e ser jogado de
#: volta ao começo. Para fechar três litros de 250 em 250 são doze idas.
#:
#: A âncora resolve sem mexer na ordem da tela nem no desenho: o navegador
#: reabre a página no cartão que a pessoa acabou de usar. As duas já existiam —
#: `#hidratacao` no cartão de água e `#slot-<pk>` em cada refeição, esta última
#: já usada pelo cartão AGORA para levar até a refeição da vez.
#:
#: NÃO vale para os ramos de erro: a mensagem é renderizada no topo, e ancorar
#: rolaria a tela para longe do texto que explica o que deu errado. Nem para o
#: recálculo, que refaz o dia inteiro e tem mensagem própria.
def _hoje_em(ancora: str) -> str:
    """A tela do cardápio, na âncora da refeição que acabou de ser marcada.

    Ela apontava para `plans:today`, que era a tela do cardápio. Com a
    separação de 22/09/2026 o cardápio mora em `plans:alimentacao`, e é para
    lá que o POST de refeição tem de voltar — voltar para a Hoje faria a
    pessoa perder de vista a lista que ela está preenchendo.
    """
    return reverse("plans:alimentacao") + ancora


def contexto_da_receita(opcao, porcao=None, log=None):
    """Tudo o que `plans/_receita.html` desenha, para uma opção e uma porção.

    Existe como função e não como método da view porque ela serve a DOIS
    lugares: a tela da receita e o painel da direita do cardápio, que no
    desktop já nasce com a receita da refeição da vez. Duas montagens do
    mesmo contexto divergiriam na primeira coisa que a receita ganhasse.

    Nenhuma consulta escondida: `ingredient_list` usa `.all()` para aproveitar
    o `prefetch_related` de quem chamou, e `outras` é UMA consulta — as outras
    receitas do repertório daquele horário, que é o que "trocar por outra
    receita" oferece.
    """
    porcao = porcao_valida(porcao)
    return {
        "opcao": opcao,
        "slot": opcao.slot,
        "log": log,
        "porcao": porcao,
        "porcoes": [
            {"valor": v, "escrita": PORCAO_ESCRITA[v], "atual": v == porcao}
            for v in PORCOES
        ],
        "kcal": opcao.kcal * porcao,
        "protein_g": opcao.protein_g * porcao,
        "carb_g": opcao.carb_g * porcao,
        "fat_g": opcao.fat_g * porcao,
        "itens": opcao.ingredient_list(porcao),
        "passos": passos_do_preparo(opcao.template.instructions),
        "outras": [
            o
            for o in opcao.slot.options.select_related("template").order_by("rank")
            if o.pk != opcao.pk
        ],
    }


class ReceitaView(OnboardingRequiredMixin, TemplateView):
    """A receita de uma opção: ingredientes, preparo, macros e porção.

    É uma TELA, com URL própria, e não um bloco que só existe dentro de um
    `<dialog>`. A ordem do projeto é "tela antes de `<details>` antes de
    `<dialog>`", e aqui ela tem uma razão concreta além da doutrina: o modo de
    preparo saiu do card na reforma de 23/09/2026, e um modo de preparo que só
    existe dentro de um script é um modo de preparo que some quando o script
    falha. `pwa.js` INTERCEPTA o link e abre o mesmo HTML numa folha; sem
    JavaScript, o link navega e a receita aparece inteira.

    Uma view, um template, uma resposta: a folha busca ESTA página e recorta
    a seção `#receita` dela, que é o que `pwa.js` já faz com "Outras formas"
    na ficha do treino. Devolver um fragmento por cabeçalho seria um segundo
    caminho de renderização para o mesmo conteúdo — e o segundo caminho é o
    que diverge na primeira receita nova.

    A PORÇÃO chega por `?porcao=` e a conta é do SERVIDOR. Fazê-la no
    navegador daria o número na hora e faria a tela e o registro discordarem
    no instante em que a rede caísse — e é o mesmo número que vai para o
    histórico quando a pessoa toca "Comi esta".
    """

    template_name = "plans/receita.html"
    nav = "food"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # O filtro por plano ATIVO do próprio usuário é o que fecha o IDOR:
        # sem ele, um `pk` de outra conta devolveria a receita dela — e com
        # ela o horário e o alvo calórico daquela pessoa.
        opcao = get_object_or_404(
            MealOption.objects.select_related("template", "slot")
            .prefetch_related("template__items__food__portions"),
            pk=self.kwargs["option_id"],
            slot_id=self.kwargs["slot_id"],
            slot__plan__user=self.request.user,
            slot__plan__is_active=True,
        )
        # O registro de HOJE daquele horário: a tela que oferece "Comi esta"
        # para uma refeição já registrada oferece uma ação que só pode dar
        # errado. Uma consulta, e ela responde a pergunta que a pessoa faria.
        log = MealLog.objects.filter(
            user=self.request.user, slot=opcao.slot, date=timezone.localdate()
        ).first()
        contexto["receita"] = contexto_da_receita(
            opcao, self.request.GET.get("porcao"), log=log
        )
        return contexto


class MarkMealView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Marca uma refeição do dia. A AÇÃO é só POST — isso muda estado.

    O GET devolve a tela do dia, e não um 405 em branco: ver
    `config/acoes.py`.

    A ação chega como `status` e, quando é "comi", vem junto o id da opção
    escolhida. O slot é buscado dentro do plano ATIVO do próprio usuário: sem
    esse filtro, um id de outra pessoa marcaria refeição na conta errada.
    """

    #: A tela desta ação é a do CARDÁPIO, e não a Hoje: desde 22/09/2026 são
    #: duas telas, e é da Alimentação que este botão é tocado. O padrão do
    #: mixin ("errar para a porta de entrada") continua certo para quem não
    #: declara nada — aqui não é errar, é saber.
    tela_da_acao = "plans:alimentacao"

    def post(self, request, slot_id, *args, **kwargs):
        slot = get_object_or_404(
            MealSlot, pk=slot_id, plan__user=request.user, plan__is_active=True
        )
        status = request.POST.get("status")
        if status not in MealStatus.values:
            # De volta ao cardápio, que é de onde o botão veio — a mesma tela
            # de `tela_da_acao`. Apontava para a Hoje, que até 22/09/2026 era
            # a mesma página.
            return redirect(self.tela_da_acao)

        option = None
        if status == MealStatus.DONE:
            # O id é convertido ANTES de virar filtro. `pk=""` ou `pk="abc"`
            # não caem em `get_object_or_404` como "não encontrei": o próprio
            # ORM levanta `ValueError` ao preparar a consulta, e o que chega na
            # cara de quem só queria marcar o almoço é um 500.
            #
            # Encontrado ao escrever o teste de segurança do cardápio V2, e é a
            # mesma família do `exercise_id` malformado que derrubava a
            # conclusão de série no Treino V3.
            try:
                option_id = int(request.POST.get("option") or "")
            except (TypeError, ValueError):
                raise Http404("opção inválida")
            # `select_related` porque o snapshot do log lê `template.name`:
            # sem ele, marcar uma refeição custaria uma consulta a mais só
            # para buscar o nome que já vem no mesmo caminho.
            #
            # O filtro por `slot` é o que fecha o IDOR, e o slot já veio
            # filtrado pelo plano ativo do próprio usuário. Repare que NÃO se
            # valida contra a projeção do dia: a fila offline reenvia a opção
            # que estava na tela quando a pessoa marcou, e depois da virada do
            # dia essa opção pode não ser mais uma das duas de hoje.
            option = get_object_or_404(
                MealOption.objects.select_related("template"),
                pk=option_id,
                slot=slot,
            )

        notes = (request.POST.get("notes") or "").strip()

        # "Comi outra coisa" sem dizer o quê não é registro, é um buraco com
        # carimbo: some da lista de pendências e não conta nada no histórico.
        # O `required` do HTML já barra no navegador; aqui é a mesma regra do
        # lado que ninguém desliga.
        if status == MealStatus.OFF_PLAN and not notes:
            return redirect(reverse("plans:today") + f"#refeicao-{slot.pk}")

        macros = None
        if status == MealStatus.OFF_PLAN:
            desconhecidos = []
            macros = tracking.macros_de_itens(
                _itens_descritos(request.POST, desconhecidos)
            )
            if desconhecidos:
                # A refeição entra do mesmo jeito; o que a pessoa fica sabendo
                # é que aquela linha não contou nas calorias.
                messages.warning(
                    request,
                    "Não encontramos %s no catálogo — a refeição foi registrada sem %s."
                    % (
                        ", ".join('"%s"' % n for n in desconhecidos),
                        "isso" if len(desconhecidos) == 1 else "esses itens",
                    ),
                )

        # A porção vem do formulário da receita ("comi meia"), e o servidor a
        # valida contra a lista fechada: ela MULTIPLICA o kcal que entra no
        # histórico, e um `porcao=99` forjado escreveria um dia de 280 mil
        # calorias. Fora da receita o campo não é emitido, e a falta dele vale 1.
        tracking.log_meal(
            request.user,
            slot,
            status,
            option,
            notes=notes,
            macros=macros,
            porcao=request.POST.get("porcao"),
        )
        if status == MealStatus.DONE:
            analytics.evento(request, "dieta.refeicao_registrada",
                             {"opcao": option.template.name if option else ""})
        elif status == MealStatus.SKIPPED:
            analytics.evento(request, "dieta.pulou")
        elif status == MealStatus.OFF_PLAN:
            analytics.evento(request, "dieta.comeu_outra_coisa")
        return redirect(_hoje_em("#slot-%d" % slot.pk))


#: Teto de gramas por alimento numa refeição fora do plano.
#:
#: Três quilos é absurdo de propósito: o número existe para barrar dedo
#: escorregando no teclado ("1000" virando "10000"), e não para julgar quanto
#: alguém comeu. Vale para a SOMA das linhas daquele alimento.
LIMITE_GRAMAS = Decimal("3000")


def _itens_descritos(dados, desconhecidos=None) -> list:
    """Os pares `(Food, gramas)` que a pessoa descreveu, ignorando o resto.

    Casa por NOME e não por id porque a entrada é um `<input list="...">`: o
    datalist sugere, e a pessoa pode digitar qualquer coisa por cima. Nome que
    não bate com o catálogo é descartado — o registro ainda vale pela
    descrição, e recusar a refeição inteira por causa de uma linha mal
    digitada é o caminho mais curto para ela parar de registrar. Descartado,
    mas NÃO em silêncio: quem passar `desconhecidos` (uma lista) recebe os
    nomes que não casaram, e a tela avisa (UX UXA-04 — "input ignorado sem
    aviso").

    Um `<select>` com os 61 alimentos daria o id de graça e custaria 61 opções
    por linha, vezes três linhas, vezes cinco horários: 900 nós de DOM na tela
    mais visitada do app, para uma ação que quase nunca acontece.
    """
    nomes = dados.getlist("alimento")[: tracking.MAX_ITENS_FORA]
    gramas = dados.getlist("gramas")[: tracking.MAX_ITENS_FORA]

    pedidos = {}
    originais = {}
    for nome, quantidade in zip(nomes, gramas):
        nome = (nome or "").strip()
        if not nome:
            continue
        try:
            valor = Decimal(str(quantidade).replace(",", "."))
        except (InvalidOperation, TypeError):
            continue
        # `Decimal("NaN")` NÃO levanta ao ser construído — ele constrói um NaN,
        # e a comparação abaixo é que estourava `InvalidOperation`, com o
        # erro 500 chegando na cara de quem só queria registrar o almoço.
        # `is_finite()` cobre NaN e infinito de uma vez.
        if not valor.is_finite():
            continue
        # Zero grama de alguma coisa é a linha que a pessoa começou e
        # abandonou, e peso negativo não existe. Três quilos é o teto: acima
        # disso é dedo escorregando no teclado, não refeição.
        if valor <= 0 or valor > LIMITE_GRAMAS:
            continue
        # SOMA em vez de sobrescrever. Arroz no almoço e arroz de novo à noite
        # é a mesma linha do catálogo duas vezes, e a versão anterior guardava
        # só a última: "150 g" e depois "100 g" viravam 100, não 250.
        #
        # E o teto vale para a SOMA, não para a linha: com ele só por linha,
        # duas de 2 kg passavam e viravam 4 kg de arroz num prato — o teto
        # existe para barrar dedo escorregando no teclado, e escorregar duas
        # vezes é o caso mais provável, não o menos.
        chave = nome.casefold()
        somado = pedidos.get(chave, Decimal("0")) + valor
        if somado > LIMITE_GRAMAS:
            continue
        pedidos[chave] = somado
        originais.setdefault(chave, nome)

    if not pedidos:
        return []

    # Uma consulta, e o casamento sem diferenciar maiúscula acontece em
    # Python: são 61 alimentos ativos, e um `iexact` por linha seriam três
    # idas ao banco para comparar com uma lista que cabe na memória.
    por_nome = {
        food.name.casefold(): food for food in Food.objects.filter(is_active=True)
    }
    if desconhecidos is not None:
        # Como a pessoa escreveu, e não a chave normalizada: o aviso cita o
        # que ela digitou.
        desconhecidos.extend(originais[nome] for nome in pedidos if nome not in por_nome)
    return [
        (por_nome[nome], quantidade)
        for nome, quantidade in pedidos.items()
        if nome in por_nome
    ]


class ClearMealView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Desfaz a marcação de uma refeição do dia."""

    #: A tela desta ação é a do CARDÁPIO, e não a Hoje: desde 22/09/2026 são
    #: duas telas, e é da Alimentação que este botão é tocado. O padrão do
    #: mixin ("errar para a porta de entrada") continua certo para quem não
    #: declara nada — aqui não é errar, é saber.
    tela_da_acao = "plans:alimentacao"

    def post(self, request, slot_id, *args, **kwargs):
        slot = get_object_or_404(
            MealSlot, pk=slot_id, plan__user=request.user, plan__is_active=True
        )
        slot.logs.filter(user=request.user, date=timezone.localdate()).delete()
        return redirect(_hoje_em("#slot-%d" % slot.pk))


class HistoryView(OnboardingRequiredMixin, TemplateView):
    template_name = "plans/history.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = tracking.history(self.request.user)
        plan = services.get_active_plan(self.request.user)
        # A meta DA ÉPOCA, e não a de hoje. `NutritionPlan` é retrato e os
        # antigos ficam, então a informação sempre esteve no banco: comparar
        # todo dia com a meta atual fazia a segunda-feira parecer excesso para
        # quem cortou calorias na terça.
        metas = tracking.metas_por_dia(self.request.user, [r["date"] for r in rows])
        atual = plan.target_kcal if plan else 0
        for row in rows:
            meta = metas.get(row["date"]) or atual or 1
            row["meta"] = meta
            row["pct"] = min(int(row["kcal"] * 100 / meta), 100)
        # A lista é materializada aqui porque o peso de hoje sai dela: as
        # pesagens vêm ordenadas por data decrescente, então se existe uma de
        # hoje ela é a primeira. Uma consulta a mais só para reencontrar a
        # linha que já está na mão seria consulta paga duas vezes.
        recusa = recusa_pendente(self.request, "metricas")
        tendencia = weight_trend.analisar(self.request.user)
        semanas_de_agua = tracking.agua_por_semana(self.request.user)
        semanas_de_treino = progresso.dias_treinados(self.request.user)
        semanas_de_corrida = progresso.km_corridos(self.request.user)
        entries = list(self.request.user.weight_entries.all()[:10])
        hoje = timezone.localdate()
        de_hoje = entries[0] if entries and entries[0].date == hoje else None

        # CONQUISTAS ENTRAM AQUI, e a razão é de produto: a pergunta "como
        # estou evoluindo" é desta tela, e conquista é resposta dela. A página
        # isolada continua existindo para quem quiser ver tudo.
        #
        # `resumo` é a MESMA função que a tela de conquistas usa — a regra do
        # que entra em "próxima" é delicada ("só o que dá para medir sem
        # inventar", que é o que impede a parede de medalhas cinzentas), e duas
        # cópias dela divergiriam na primeira mudança.
        total_conquistas, recente, proxima = conquistas.resumo(
            self.request.user, request=self.request
        )

        context.update(
            {
                "conquistas_total": total_conquistas,
                "conquistas_recente": recente,
                "conquistas_proxima": proxima,
                "plan": plan,
                "rows": rows,
                "totals": tracking.adherence(rows),
                "days": tracking.HISTORY_DAYS,
                "weight_entries": entries,
                "tendencia": tendencia,
                # A CURVA é derivada da MESMA lista de semanas que a tabela
                # imprime — não é uma segunda fonte, é a mesma leitura em outra
                # forma. Uma tabela responde "quanto eu pesava em 31/08?"; a
                # curva responde "para onde isso está indo?", que é a pergunta
                # de quem abre a tela de Progresso.
                "curva_peso": _curva_de_peso(tendencia.semanas),
                # Preenche o campo com o peso já registrado hoje: salvar de
                # novo é corrigir, e corrigir começa do valor que está lá.
                "peso_de_hoje": de_hoje.weight_kg if de_hoje else None,
                "houve_recusa": recusa is not None,
                "peso_recusado": recusa.valor if recusa else "",
                "peso_erro": recusa.mensagem if recusa else "",
                # O treino nesta tela. Cada série sempre esteve no banco, e a
                # tela chamada "Métricas" não mostrava nenhuma: quem treinava
                # há dois meses não via nada do próprio treino aqui.
                "semanas_de_treino": semanas_de_treino,
                # Mesma distinção da água, e aqui eu tinha errado: a lista tem
                # SEMPRE oito semanas, inclusive as zeradas — buraco na série é
                # informação. `{% if lista %}` é verdadeiro mesmo sem nenhum
                # treino, e o estado vazio nunca apareceria.
                "tem_treino": any(s["dias"] for s in semanas_de_treino),
                "dias_combinados": self.request.user.training_days.count(),
                # A corrida é pilar: o cartão só aparece para quem correu
                # (uma consulta agregada; achado #9 das personas, 22/09/2026).
                "semanas_de_corrida": semanas_de_corrida,
                "tem_corrida": any(s["corridas"] for s in semanas_de_corrida),
                "semana_de_corrida": semanas_de_corrida[-1],
                "cargas": progresso.progressao_de_carga(self.request.user),
                # Iniciante há meio ano e duas dúzias de treinos: convite a
                # atualizar o nível (uma consulta; zero para os outros níveis).
                "convite_de_nivel": progresso.convidar_a_atualizar_experiencia(self.request.user),
                "agua_semanas": semanas_de_agua,
                # A pergunta é "existe algum registro?", e não "a lista tem
                # itens": a lista SEMPRE tem oito semanas, inclusive as
                # zeradas — buraco na série é informação. Sem esta distinção o
                # cartão nunca mostraria o estado vazio.
                "tem_agua": any(s["dias"] for s in semanas_de_agua),
                "nav": "history",
            }
        )
        return context


class RecalibrateView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Aplica — ou recusa — o ajuste sugerido quando a média empaca.

    O corte fica guardado no perfil e não no plano: plano é snapshot e é
    refeito a cada mudança de peso, então gravar o ajuste nele o faria sumir
    na primeira pesagem. No perfil, ele acompanha a pessoa.

    "Prefiro me mexer mais" não é um botão decorativo: aumentar o gasto é uma
    resposta legítima e às vezes melhor que comer menos. O app registra a
    escolha para não repetir a pergunta na semana seguinte.

    E, desde agora, ele de fato não repete. `recalibrated_at` era gravado aqui
    pelas duas ações e não era lido por ninguém: a tela recalculava
    `sugerir_recalibragem` só do peso, e o peso não se mexe em dois minutos.
    Medido no navegador: dois toques em "Cortar 150 kcal" no mesmo minuto
    levaram o ajuste para −300 kcal com o cartão ainda na tela, oferecendo o
    terceiro.

    A tela deixou de oferecer, e esta guarda fecha a outra porta: uma aba
    aberta antes da resposta continua com o formulário válido, e sem ela o
    corte seria aplicado de novo por quem só voltou numa aba velha.

    "aumentar" existe pelo mesmo motivo que "cortar", do outro lado do
    objetivo: quem quer GANHAR massa e empacou destrava somando calorias, não
    cortando — `weight_trend.analisar` só oferece este botão para quem tem
    `goal == BULK`, mas a view não reencena essa checagem: `acao` é só um dos
    três nomes que ela sabe aplicar ("cortar", "aumentar", "dispensar"); um
    valor que não é nenhum dos três não vira "dispensar" por acidente — não
    grava nada e só devolve para a tela.
    """

    #: A tela desta ação é a do CARDÁPIO, e não a Hoje: desde 22/09/2026 são
    #: duas telas, e é da Alimentação que este botão é tocado. O padrão do
    #: mixin ("errar para a porta de entrada") continua certo para quem não
    #: declara nada — aqui não é errar, é saber.
    tela_da_acao = "plans:alimentacao"

    def post(self, request, *args, **kwargs):
        profile = request.user.profile
        acao = request.POST.get("acao")

        if weight_trend.respondeu_ha_pouco(request.user):
            messages.info(
                request,
                "Você já respondeu a esse aviso. Vamos esperar duas semanas "
                "para ver o efeito antes de mexer na meta de novo.",
            )
            return redirect(reverse("plans:history"))

        if acao == "cortar":
            profile.kcal_adjustment -= weight_trend.AJUSTE_KCAL
            profile.recalibrated_at = timezone.now()
            profile.save(update_fields=["kcal_adjustment", "recalibrated_at"])
            services.sync_active_plan(request.user)
            messages.success(
                request,
                f"Cortamos {weight_trend.AJUSTE_KCAL} kcal da sua meta. "
                "Dê duas semanas antes de julgar o resultado.",
            )
        elif acao == "aumentar":
            profile.kcal_adjustment += weight_trend.AJUSTE_KCAL
            profile.recalibrated_at = timezone.now()
            profile.save(update_fields=["kcal_adjustment", "recalibrated_at"])
            services.sync_active_plan(request.user)
            messages.success(
                request,
                f"Somamos {weight_trend.AJUSTE_KCAL} kcal à sua meta. "
                "Dê duas semanas antes de julgar o resultado.",
            )
        elif acao == "dispensar":
            profile.recalibrated_at = timezone.now()
            profile.save(update_fields=["recalibrated_at"])
            if profile.goal == Goal.BULK:
                # Gastar mais é conselho de CORTE. Quem quer GANHAR massa e
                # empacou destrava comendo o que a meta já pede — proteína e
                # as refeições do dia — não andando mais.
                texto = (
                    "Combinado. Vale conferir se a meta de proteína e as "
                    "refeições do dia estão sendo batidas — perguntamos de "
                    "novo daqui a algumas semanas."
                )
            else:
                texto = (
                    "Combinado. Tente somar uns 20 minutos de caminhada por dia — "
                    "perguntamos de novo daqui a algumas semanas."
                )
            messages.info(request, texto)
        # `acao` desconhecida (nem "cortar", "aumentar" nem "dispensar") não
        # grava nada: um POST inventado não pode aplicar a recusa por engano.

        return redirect(reverse("plans:history"))


class RecalculatePlanView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Recálculo manual: a AÇÃO é só por POST.

    O recálculo automático já cobre mudança de dado; este botão existe para o
    caso de a pessoa querer forçar um plano novo (voltou de férias, mudou de
    fase) e para deixar explícito que recalcular é uma ação, não um efeito
    colateral de abrir uma tela.
    """

    #: A tela desta ação é a do CARDÁPIO, e não a Hoje: desde 22/09/2026 são
    #: duas telas, e é da Alimentação que este botão é tocado. O padrão do
    #: mixin ("errar para a porta de entrada") continua certo para quem não
    #: declara nada — aqui não é errar, é saber.
    tela_da_acao = "plans:alimentacao"

    def post(self, request, *args, **kwargs):
        try:
            services.create_plan(request.user)
        except services.IncompleteProfile:
            return redirect("accounts:onboarding")
        messages.success(request, "Meta recalculada com os seus dados de hoje.")
        return redirect("plans:alimentacao")


class MarcarItemDaListaView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Risca (ou desrisca) um item da lista de compras.

    ESTADO ABSOLUTO, NUNCA ALTERNÂNCIA. O corpo diz `marcado=1` ou `marcado=0`,
    e não "inverta" — porque este POST pode chegar duas vezes. A fila offline
    reenvia quando a resposta se perde no meio, e um "alterne" reproduzido
    desfaz o que a pessoa fez. É o mesmo defeito que a água pagou para
    aprender, e aqui ele é evitado pela FORMA do pedido: aplicar duas vezes o
    mesmo estado absoluto dá o mesmo resultado.

    Por isso esta rota dispensa `op_id`: ela é idempotente por construção, e um
    identificador seria maquinário para uma corrida que não existe.

    A semana vem do corpo e é conferida contra a lista de hoje: sem isso, um
    pedido atrasado marcaria o item na semana errada — e a marcação da semana
    passada voltaria riscada na próxima compra.
    """

    tela_da_acao = "plans:shopping"

    def post(self, request, *args, **kwargs):
        destino = redirect("plans:shopping")

        # O item avulso tem a própria coluna de estado — o mesmo contrato
        # absoluto, chaveado pelo `pk` dele em vez de (alimento, opção, dia).
        # Só do dono: um `pk` alheio não acha linha e não muda nada.
        avulso = (request.POST.get("avulso_id") or "").strip()
        if avulso:
            try:
                avulso_id = int(avulso)
            except ValueError:
                raise Http404("item inválido")
            ItemAvulsoDaLista.objects.filter(user=request.user, pk=avulso_id).update(
                marcado=(request.POST.get("marcado") or "") in ("1", "true", "on")
            )
            return destino

        try:
            food_id = int(request.POST.get("food_id") or "")
        except (TypeError, ValueError):
            raise Http404("alimento inválido")
        food = get_object_or_404(Food, pk=food_id)

        opcao = (request.POST.get("opcao") or OptionLabel.A).strip()
        if opcao not in OptionLabel.values:
            opcao = OptionLabel.A

        # A semana é a da lista que a pessoa está vendo. Um valor ilegível cai
        # na semana de hoje, que é a única que a tela desenha.
        semana = shopping.dias_da_semana()[0]
        bruto = (request.POST.get("semana") or "").strip()
        if bruto:
            try:
                semana = datetime.strptime(bruto, "%Y-%m-%d").date()
            except ValueError:
                pass

        if (request.POST.get("marcado") or "") in ("1", "true", "on"):
            ItemDaListaMarcado.objects.get_or_create(
                user=request.user, food=food, opcao=opcao, semana=semana
            )
        else:
            # Desriscar apaga o risco de QUALQUER dia da janela: o arroz
            # riscado no sábado e desriscado na quarta não pode reaparecer
            # riscado na quinta porque a linha de sábado ficou.
            ItemDaListaMarcado.objects.filter(
                user=request.user, food=food, opcao=opcao,
                semana__range=shopping.janela_de_marcacao(semana),
            ).delete()
        return destino


class AdicionarItemDaListaView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Acrescenta um item que o cardápio não pede (§36).

    `get_or_create` pela chave (pessoa, dia, nome): o toque duplo no botão e
    o reenvio do formulário produzem UM item. O nome é normalizado no espaço
    em branco e nada mais — "Café" e "café" são dois itens, e a pessoa vê os
    dois e remove um; corrigir por ela seria adivinhar.
    """

    tela_da_acao = "plans:shopping"

    def post(self, request, *args, **kwargs):
        nome = " ".join((request.POST.get("nome") or "").split())[:60]
        if not nome:
            return _de_volta_a_lista(request)
        item, _ = ItemAvulsoDaLista.objects.get_or_create(
            user=request.user, semana=timezone.localdate(), nome=nome
        )
        # A tela DIZ que entrou e POUSA no item, não no topo do cartão: a 320
        # o item novo — o último da lista — ficava fora da tela, e nada
        # dizia que algo tinha acontecido (UX P1-10).
        messages.success(request, "%s entrou na lista." % item.nome)
        return _de_volta_a_lista(request, ancora="item-%d" % item.pk)


class RemoverItemDaListaView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Remove um item avulso. Só os avulsos: o que vem do cardápio não sai
    daqui — riscar já diz "tenho em casa", e tirar da lista o que o plano
    consome faria a lista mentir sobre a semana."""

    tela_da_acao = "plans:shopping"

    def post(self, request, *args, **kwargs):
        try:
            item_id = int(request.POST.get("item_id") or "")
        except ValueError:
            raise Http404("item inválido")
        ItemAvulsoDaLista.objects.filter(user=request.user, pk=item_id).delete()
        return _de_volta_a_lista(request)


def _de_volta_a_lista(request, ancora="seus-itens"):
    """Para a lista da MESMA opção, na seção dos itens da pessoa — ou no item.

    A opção vem do corpo e passa pela lista fechada, como na tela: um valor
    inventado cai na A em vez de virar querystring livre. A âncora é do
    servidor, nunca do pedido."""
    opcao = (request.POST.get("opcao") or OptionLabel.A).strip()
    if opcao not in OptionLabel.values:
        opcao = OptionLabel.A
    return redirect(reverse("plans:shopping") + "?opcao=%s#%s" % (opcao, ancora))


class ShoppingListView(PlanRequiredMixin, TemplateView):
    """A lista de compras da semana, por corredor de supermercado."""

    template_name = "plans/shopping.html"

    def get(self, request, *args, **kwargs):
        # Os dias de treino, UMA vez: `build_inputs` (a duração de cada
        # sessão) e "Dados do cálculo" no template leem a mesma lista, e
        # sem o pré-carregamento cada um abria a sua consulta.
        prefetch_related_objects([request.user], "training_days")
        # As últimas pesagens, UMA vez: o peso mais recente entra no cálculo
        # (`build_inputs`) e as datas da semana no convite de pesar. Sete
        # bastam para as duas perguntas — uma pesagem por dia, sete dias.
        self.pesagens = list(request.user.weight_entries.order_by("-date", "-pk")[:PESAGENS_LIDAS])
        try:
            self.plan = self.get_plan(request)
        except services.IncompleteProfile:
            messages.info(request, "Faltou completar seu cadastro para montar a lista.")
            return redirect("accounts:onboarding")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # A opção vem da URL para a pessoa poder ver a lista da B sem precisar
        # trocar nada no plano — é comparação de compras, não mudança de dieta.
        label = self.request.GET.get("opcao", OptionLabel.A)
        if label not in OptionLabel.values:
            label = OptionLabel.A

        aisles = shopping.shopping_list(self.plan, label=label)

        # AS MARCAÇÕES VÊM DO BANCO, e são lidas pelo cruzamento com a lista
        # de agora. Alimento que saiu do cardápio não é desenhado, então uma
        # marcação órfã fica sem efeito em vez de reaparecer em lista que não a
        # contém — é assim que a troca de plano se invalida sozinha, sem
        # migração destrutiva.
        # A gravação é chaveada pelo DIA do toque; a leitura cobre a janela
        # inteira (`janela_de_marcacao`): o risco de sábado vale na quarta.
        semana = shopping.dias_da_semana()[0]
        janela = shopping.janela_de_marcacao(semana)
        marcados = set(
            ItemDaListaMarcado.objects.filter(
                user=self.request.user, opcao=label, semana__range=janela
            ).values_list("food_id", flat=True)
        )
        for corredor in aisles:
            for item in corredor["items"]:
                item["marcado"] = item["food"].id in marcados

        context.update(
            {
                "semana_da_lista": semana,
                # Os itens da pessoa, da mesma janela, em qualquer opção.
                "avulsos": list(
                    ItemAvulsoDaLista.objects.filter(
                        user=self.request.user, semana__range=janela
                    )
                ),
                # A lista é uma subtela da ALIMENTAÇÃO — é o cardápio da
                # semana virado compra —, e desde 22/09/2026 existe uma aba
                # com esse nome para acender. Antes ela acendia a aba que se
                # chamava "Alimentação" e levava para a Hoje; hoje acende a
                # aba certa, e a porta continua sendo a mesma: o link no topo
                # do cardápio e o módulo em "Mais".
                "nav": "food",
                "plan": self.plan,
                "aisles": aisles,
                "label": label,
                "labels": OptionLabel.choices,
                "days": shopping.DAYS,
                "total_items": sum(aisle["count"] for aisle in aisles),
            }
        )
        return context


class LogHydrationView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Soma água ao dia. A AÇÃO é só POST — isso muda estado.

    O GET devolve a tela do dia, e não um 405 em branco: ver
    `config/acoes.py`.

    Soma em vez de definir o total porque é assim que a pessoa mede: ela acabou
    de beber um copo, não sabe (nem quer calcular) quanto isso faz no
    acumulado. O botão diz "+500 ml" e some com a conta.
    """

    #: Os volumes dos botões: copo, garrafinha, garrafa.
    PASSOS = (250, 500, 750)

    #: A faixa da quantidade digitada, que só a tela de hidratação produz.
    #:
    #: A regra anterior aceitava SÓ os três passos, e o comentário dizia por
    #: quê: "aceitar qualquer múltiplo de dez seria aceitar um valor que
    #: nenhuma tela produz". Isso deixou de ser verdade — agora existe um campo
    #: para digitar, e a razão de recusar caiu junto com ela.
    #:
    #: Os limites não são decoração. Abaixo de 50 ml não é um gole, é um toque
    #: errado; acima de 2 L num registro só é quase sempre dedo escorregando
    #: ("500" virando "5000"), e o teto diário de 10 L não pega esse caso
    #: porque ele cabe folgado embaixo. Múltiplo de 10 porque ninguém mede
    #: 237 ml — e porque um passo faz o teclado numérico do celular errar menos.
    LIVRE_MINIMO = 50
    LIVRE_MAXIMO = 2000
    LIVRE_MULTIPLO = 10

    #: Para onde voltar depois de somar. É uma LISTA FECHADA, e não a URL que
    #: veio no pedido: `?next=` livre é redirecionamento aberto, e esta view
    #: aceita POST de qualquer origem autenticada. O nome da tela é o bastante.
    DESTINOS = {"hidratacao": "plans:hydration", "topo": "plans:today"}

    def _aceita(self, ml) -> bool:
        if ml in self.PASSOS:
            return True
        return (
            self.LIVRE_MINIMO <= ml <= self.LIVRE_MAXIMO
            and ml % self.LIVRE_MULTIPLO == 0
        )

    def _volta(self, request, *, erro=False):
        """A âncora, ou a tela própria quando foi dela que veio o toque.

        Erro continua indo para o TOPO da tela de hoje: a `.flash` é
        renderizada lá, e ancorar rolaria para longe do texto que explica o que
        deu errado. Na tela de hidratação não há esse problema — ela é curta, e
        a mensagem cabe na primeira dobra.
        """
        destino = self.DESTINOS.get(request.POST.get("de"))
        if destino:
            return redirect(destino)

        # Sem `de`, a âncora — e ela é da tela HOJE, não da Alimentação: em
        # 22/09/2026 o cartão de água virou uma célula do painel do dia, e a
        # tela do cardápio deixou de ter `#hidratacao`. Apontar para lá seria
        # uma âncora que não existe, que o navegador ignora em silêncio (é o
        # defeito que `plans/test_b2_hoje.py` existe para pegar).
        return redirect("plans:today" if erro else reverse("plans:today") + "#hidratacao")

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """TUDO numa transação, e a razão é a trava de idempotência.

        `ja_aplicada` faz `get_or_create` e este projeto não liga
        `ATOMIC_REQUESTS` — então, sem este decorador, o `op_id` COMMITA
        sozinho, antes de o efeito acontecer. Se a escrita seguinte estourasse,
        o identificador ficava queimado e o efeito não: a fila preservava o
        item pelo 5xx, reenviava, a trava respondia "já aplicada", a barreira
        de replay traduzia o redirect em 200 e a fila APAGAVA o item.

        A pessoa registrava água, o servidor falhava, e o registro sumia sem
        que nada dissesse que falhou. Reproduzido em
        `OpIdQueimadoPorFalhaNaoPodePerderAOperacaoTests`.

        Com a transação em volta, o identificador e o efeito caem juntos ou não
        caem: falhar volta ao estado anterior, e o reenvio encontra a operação
        ainda não aplicada. A proteção contra dois reenvios SIMULTÂNEOS
        continua sendo o índice único de `SyncedOperation`, que não depende
        disto.
        """
        # A trava vem ANTES de escolher o ramo, e não depois.
        #
        # Ela ficava lá embaixo, depois do `desfazer` já ter voltado — e o
        # `CLAUDE.md` é explícito sobre quem precisa dela: "Água SOMA e
        # suplemento ALTERNA — as duas precisam de op_id". Desfazer SUBTRAI,
        # que é a mesma família: se o servidor aplica e a resposta se perde, a
        # fila reenvia e um SEGUNDO gole vai embora. `static/js/fila.js`
        # enfileira `/agua/` inteiro, e o formulário de desfazer posta ali.
        #
        # `ja_aplicada` registra e responde numa chamada só — conferir e depois
        # gravar abriria a janela em que dois reenvios simultâneos passam os
        # dois. Sem `op_id` ela devolve `False`, que é o caminho da tela normal.
        if SyncedOperation.ja_aplicada(request.user, request.POST.get("op_id")):
            return self._volta(request)

        if request.POST.get("acao") == "desfazer":
            return self._desfazer(request)

        # Valor ausente ou ilegível é RECUSADO, e não tratado como zero.
        #
        # A versão anterior caía em `ml = 0` — e zero, nesta view, quer dizer
        # ZERAR O DIA. Enquanto os únicos emissores eram os três botões e o
        # "zerar" (que manda `value="0"` de propósito), isso era inalcançável.
        # A tela de hidratação criou o emissor que faltava: um `<input
        # type="number">` vazio envia `ml=`, `int("")` estoura, e tocar "Somar"
        # com o campo em branco apagaria o dia INTEIRO — total e goles, agora
        # que zerar também limpa a composição.
        #
        # Encontrado lendo o próprio caminho novo, antes de alguém apagar um
        # dia de verdade. O `required` no template avisa primeiro; quem decide
        # é o servidor, porque a fila offline reenvia o corpo cru.
        bruto = request.POST.get("ml")
        try:
            ml = int(bruto)
        except (TypeError, ValueError):
            messages.error(request, "Quantidade de água inválida.")
            return self._volta(request, erro=True)

        # A validação vem ANTES de criar a linha. Ao contrário, um valor
        # inválido deixava uma linha de 0 ml no banco — inofensiva na conta e
        # suja o bastante para confundir quem for depurar o dia depois.
        #
        # De volta aos três botões: a faixa larga existia para a entrada por
        # voz, que foi removida. Sem ela, aceitar qualquer múltiplo de dez seria
        # aceitar um valor que nenhuma tela produz.
        if ml != 0 and not self._aceita(ml):
            messages.error(request, "Quantidade de água inválida.")
            return self._volta(request, erro=True)

        hoje = timezone.localdate()
        registro, _ = HydrationLog.objects.get_or_create(user=request.user, date=hoje)

        if ml == 0:
            # Zerar é recomeçar o dia, e o dia é o total E a composição.
            #
            # A versão anterior mexia só em `HydrationLog`, e os goles daquele
            # dia ficavam órfãos. Encontrado no navegador: a tela de
            # hidratação mostrava "Registrado 0 ml" com a lista de goles cheia
            # logo abaixo. Pior que a contradição na tela, "desfazer"
            # continuava sendo oferecido e não movia número nenhum — o total já
            # estava no chão, e `Greatest(..., 0)` o segurava lá.
            #
            # As duas escritas vão juntas pelo mesmo motivo que o registro:
            # meio zerar deixaria o dia num estado que nenhuma tela sabe
            # desenhar.
            with transaction.atomic():
                HydrationLog.objects.filter(pk=registro.pk).update(
                    ml=0, updated_at=timezone.now()
                )
                GoleDeAgua.objects.filter(user=request.user, dia=hoje).delete()
        else:
            # A SOMA ACONTECE NO BANCO, e não em Python. A versão anterior era
            #
            #     registro.ml = min(registro.ml + ml, 10000)
            #     registro.save(...)
            #
            # ou seja: lê, soma na memória do processo, escreve de volta. Com
            # dois toques rápidos, os dois requests leem o MESMO valor antigo e
            # o segundo sobrescreve o primeiro. Tocar +250, +500 e +750 em
            # sequência rápida dava 1000 em vez de 1500 — uma perdia.
            #
            # Isso é `lost update`, e o defeito não é de velocidade de clique:
            # é de duas transações concorrentes lendo antes de a outra gravar.
            # Nenhum debounce no JavaScript conserta, porque o servidor precisa
            # estar certo mesmo com pedidos simultâneos — e a fila offline
            # reenvia exatamente assim, em rajada, quando a rede volta.
            #
            # Com `F("ml") + ml` o Postgres soma sobre o valor corrente da
            # linha, dentro da própria instrução. Não há janela entre ler e
            # escrever, então a ordem de chegada deixa de importar: três
            # incrementos dão a soma dos três, sempre.
            #
            # `Least` mantém o teto do dia sem voltar para Python, e o teto
            # vem de `weight_trend` — o mesmo módulo que calcula a meta. Eram
            # dois números independentes, e por isso divergiam: acima de 293 kg
            # a meta pedia mais do que este `update` deixava entrar.
            # `updated_at` vai explícito porque `auto_now` só age em `save()`,
            # e `update()` não passa por ele.
            # O gole e o total sobem JUNTOS ou não sobem. Sem a transação, um
            # erro entre as duas escritas deixaria o total somado e o gole
            # ausente — e aí "desfazer o último" tiraria o gole ANTERIOR, que é
            # pior que não ter desfazer nenhum.
            with transaction.atomic():
                HydrationLog.objects.filter(pk=registro.pk).update(
                    ml=Least(F("ml") + ml, Value(TETO_DIARIO_ML)),
                    updated_at=timezone.now(),
                )
                GoleDeAgua.objects.create(user=request.user, dia=hoje, ml=ml)
            # FORA da transação: uma falha do analytics não pode poluir o commit
            # da água nem derrubá-lo. Só o SOMAR chega aqui — zerar e desfazer
            # são outros ramos.
            analytics.evento(request, "agua.registrada")

        return self._volta(request)

    def _desfazer(self, request):
        """Tira o ÚLTIMO gole do dia, e só ele.

        O desfazer antigo era zerar o dia inteiro: quem tocasse errado depois de
        dois litros escolhia entre um número errado e perder tudo. `zerar`
        continua existindo — é outra intenção, "recomeçar o dia" —, e este aqui
        é o conserto de um toque.

        Dia anterior à tabela de goles não tem o que desfazer, e a tela diz
        isso em vez de fingir que desfez.
        """
        hoje = timezone.localdate()

        with transaction.atomic():
            # `select_for_update` no GOLE, não no total: dois toques em
            # "desfazer" ao mesmo tempo não podem remover o mesmo gole duas
            # vezes e descontar duas. O total continua sendo somado por `F()`,
            # sem leitura prévia.
            gole = (
                GoleDeAgua.objects.select_for_update(skip_locked=True)
                .filter(user=request.user, dia=hoje)
                .order_by("-registrado_em", "-pk")
                .first()
            )

            if gole is None:
                # TOPO, e não a âncora — é a convenção que o B2 fixou: "os
                # ramos de ERRO continuam no topo, onde a mensagem é
                # renderizada". A `.flash` mora no começo da página; mandar o
                # erro para a âncora da água deixaria a pessoa a 2.300px da
                # explicação, olhando um botão que não fez nada.
                #
                # O sucesso vai para a âncora de propósito: lá o próprio número
                # mudando é a confirmação, e voltar ao topo custaria a posição.
                messages.error(request, "Não há registro de hoje para desfazer.")
                return self._volta(request, erro=True)

            # `Greatest(..., 0)` porque o total tem teto de 10 L: no teto, um
            # gole de 750 pode ter somado menos que 750, e devolver o pedido
            # cheio levaria a linha para baixo de zero. A imprecisão acima de
            # dez litros por dia está declarada em `GoleDeAgua`.
            HydrationLog.objects.filter(user=request.user, date=hoje).update(
                ml=Greatest(F("ml") - gole.ml, Value(0)),
                updated_at=timezone.now(),
            )
            gole.delete()

        # SEM aviso de confirmação, e isso é regra deste projeto e não
        # descuido: `ConfirmacaoDeEscritaTests` recusa aviso de êxito nas ações
        # de alta frequência desta tela, porque "um aviso em cada uma vira uma
        # tela que fala o tempo todo".
        #
        # E a regra é lida no CÓDIGO-FONTE, não no comportamento — escrever o
        # nome da chamada aqui, mesmo dentro de um comentário que a explica,
        # deixa o teste vermelho. Aconteceu na primeira tentativa desta
        # correção. É a armadilha que o CLAUDE.md descreve: o comentário cita o
        # nome da coisa que a asserção procura.
        #
        # O desfazer pertence a essa família — é a correção de uma ação
        # frequente —, e o número caindo de 750 para 500 já é a confirmação.
        # A mensagem que eu havia escrito era, além de proibida, invisível: o
        # redirect volta para a âncora e a `.flash` mora 2.300px acima.
        #
        # O ERRO continua falando, e por isso vai para o topo: ali não há
        # número mudando, e sem a frase a pessoa vê um botão não fazer nada.
        return self._volta(request)


class HydrationView(PlanRequiredMixin, TemplateView):
    """A tela da água: o dia, o que foi bebido nele, e a semana.

    Por que ela existe, já que o cartão do Hoje continua inteiro: o cartão
    responde "quanto falta?" e some com o resto. Ele não tem espaço para a
    lista do que foi registrado hoje, nem para os sete dias, nem para uma
    quantidade que não seja um dos três botões — e enfiar isso tudo lá dentro
    engordaria a tela mais longa do app, que já tem 4.128px em 375 de largura.

    Por que ela NÃO é uma aba: hidratação é frequente, mas é frequente em
    toques de dois segundos, e esses continuam no Hoje, onde a pessoa já está.
    Uma aba cobraria uma viagem de ida e volta por copo. Esta tela é para as
    outras perguntas — "eu bebi quando?", "como foi a semana?" —, que são de
    consulta, e consulta tem lugar próprio. É a mesma decisão da lista de
    compras: subtela da dieta, com a aba Dieta acesa.

    Ela é somente leitura. Quem escreve continua sendo `LogHydrationView`, uma
    só, e os formulários daqui apontam para lá — dois caminhos de escrita para
    a mesma coisa é como a soma em Python e a soma no banco chegaram a
    coexistir.
    """

    template_name = "plans/hydration.html"

    def get(self, request, *args, **kwargs):
        # O mesmo contrato das outras telas de plano: `PlanRequiredMixin`
        # oferece `get_plan`, e cada tela decide o que dizer quando o cadastro
        # está incompleto. Aqui a frase é sobre a meta, que é o que falta.
        try:
            self.plan = self.get_plan(request)
        except services.IncompleteProfile:
            messages.info(request, "Faltou completar seu cadastro para calcular a meta.")
            return redirect("accounts:onboarding")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.localdate()

        # A fórmula da meta é a de `weight_trend`, chamada e não copiada: uma
        # segunda cópia aqui divergiria da do Hoje no primeiro ajuste, e a
        # mesma pessoa veria duas metas diferentes em duas telas do mesmo app.
        meta_ml = weight_trend.hidratacao_ml(self.plan.weight_kg)
        registro = HydrationLog.objects.filter(user=self.request.user, date=hoje).first()
        bebido = registro.ml if registro else 0
        goles = list(GoleDeAgua.objects.filter(user=self.request.user, dia=hoje))

        context.update(
            {
                # A tela de água é da HIDRATAÇÃO, e hidratação não é subfunção
                # de dieta — está escrito na docstring de `Pilar`. Com `today`
                # aqui, a aba "Dieta" acendia, e a barra dizia o contrário do
                # produto. Nenhuma aba acende agora; quem diz onde a pessoa
                # está é o mapa da barra de cima.
                "nav": "hydration",
                "meta_ml": meta_ml,
                "bebido": bebido,
                "faltam": max(meta_ml - bebido, 0),
                "pct": min(int(bebido * 100 / meta_ml), 100) if meta_ml else 0,
                "completa": bool(meta_ml) and bebido >= meta_ml,
                "goles": goles,
                # A diferença entre o total e a soma dos goles.
                #
                # Ela não é erro: é o dia da virada. Quem já usava o app tem
                # total sem composição, e no primeiro dia em que registra um
                # gole novo a lista passa a mostrar 1.000 embaixo de um painel
                # escrito 1.500. Sem esta linha, a conta simplesmente não fecha
                # na tela — e uma lista que não soma o próprio total é o tipo
                # de coisa que faz alguém parar de confiar no número.
                #
                # `max(..., 0)` porque o teto de 10 L pode ter cortado a soma:
                # o gole guarda o que foi PEDIDO, e o total guarda o que coube.
                "sem_horario": max(bebido - sum(g.ml for g in goles), 0),
                "semana": tracking.agua_dos_ultimos_dias(self.request.user, meta_ml),
                "passos": LogHydrationView.PASSOS,
                "livre_minimo": LogHydrationView.LIVRE_MINIMO,
                "livre_maximo": LogHydrationView.LIVRE_MAXIMO,
                "livre_multiplo": LogHydrationView.LIVRE_MULTIPLO,
            }
        )
        return context


def _curva_de_peso(semanas, largura=300, altura=64):
    """Pontos de uma polilinha SVG a partir das médias semanais.

    Apresentação, não cálculo: nenhum número novo nasce aqui. A função pega as
    médias que a tabela já mostra e as projeta num retângulo, para o mesmo
    dado poder ser LIDO como direção em vez de lista.

    Três decisões que a curva exige e a tabela não:

    - a escala é a do próprio período, não zero-based. Peso humano varia
      poucos por cento; ancorar em zero produziria uma reta horizontal que
      esconde exatamente a variação que a tela existe para mostrar.
    - com uma faixa muito estreita (todo mundo no mesmo peso), um piso de
      0,4 kg impede que ruído de balança vire montanha.
    - menos de dois pontos não é curva. Devolve None, e o template mostra a
      tabela sozinha — desenhar uma linha de um ponto seria afirmar tendência
      onde não há.
    """
    # SEM `reversed`: `semanas_de` devolve `sorted(por_semana.items())`, ou
    # seja, do mais ANTIGO para o mais novo — que é a ordem que uma curva
    # precisa. Quem inverte é o template da tabela, para listar o recente
    # primeiro. Inverter aqui também desenhava o tempo de trás para frente,
    # e uma perda de peso subia no gráfico.
    # `Semana` é dataclass, não dicionário — `s["media"]` estourou aqui na
    # primeira versão. `getattr` mantém a função utilizável se um dia a lista
    # vier de outra fonte, sem obrigar quem chama a converter.
    medias = [getattr(s, "media", None) for s in semanas]
    pontos = [float(m) for m in medias if m is not None]
    if len(pontos) < 2:
        return None

    # As datas andam junto com as médias — mesma lista, mesmo filtro: um
    # `zip` sobre `semanas` cru desalinharia a primeira data de um ponto que
    # a média `None` tirou da curva.
    datas = [
        getattr(s, "inicio", None)
        for s, m in zip(semanas, medias)
        if m is not None
    ]

    menor, maior = min(pontos), max(pontos)
    faixa = max(maior - menor, 0.4)
    passo = largura / (len(pontos) - 1)
    coords = []
    marcas = []
    for i, valor in enumerate(pontos):
        x = i * passo
        # y invertido: em SVG a origem é em cima, e peso maior tem de subir.
        y = altura - ((valor - menor) / faixa) * altura
        coords.append(f"{x:.1f},{y:.1f}")
        # STRING, e não float: o app é pt-BR com `USE_L10N`, e `{{ marca.x }}`
        # de um float sai "42,9" — vírgula decimal, que é o certo em texto e
        # inválido em atributo de SVG. Medido: os oito pontos empilhados na
        # origem, porque o navegador descarta o `cx` que não entende. É o
        # mesmo motivo de `pontos` já ser uma string montada aqui.
        marcas.append({"x": f"{x:.1f}", "y": f"{y:.1f}"})
    return {
        "pontos": " ".join(coords),
        # Um ponto por semana, para a curva dizer QUANTAS medições ela tem.
        # Sem eles, três semanas e trinta desenham a mesma linha.
        "marcas": marcas,
        "largura": largura,
        "altura": altura,
        "primeiro": pontos[0],
        "ultimo": pontos[-1],
        "delta": round(pontos[-1] - pontos[0], 1),
        # O EIXO (22/09/2026). A escala é a do próprio período — e é
        # exatamente por isso que ela precisa ser dita: sem os dois números, a
        # mesma linha serve para 200 g e para 4 kg de variação, e a auditoria
        # leu a curva como "linha reta". `piso` e `teto` são o que está
        # desenhado na base e no topo da caixa, não o menor e o maior peso:
        # com faixa menor que o piso de 0,4 kg os dois deixam de coincidir.
        "piso": round(menor, 1),
        "teto": round(menor + faixa, 1),
        # E o PERÍODO, pelo mesmo motivo: uma curva sem datas não diz se
        # aquilo levou um mês ou um ano.
        "de": datas[0],
        "ate": datas[-1],
    }
