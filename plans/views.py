"""Telas do plano: a meta, o cardápio do dia e o acompanhamento.

A rota `today` concentra o uso diário — meta, refeições e marcação — porque é
a única tela que a pessoa abre várias vezes por dia. O histórico fica numa
rota separada, que é consulta ocasional.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.urls import reverse
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import F, Value
from django.db.models.functions import Least
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import ACTIVITY_FACTORS, SyncedOperation
from accounts.views import OnboardingRequiredMixin, recusa_pendente
from catalog.models import Food

from workouts import progresso

from . import rodizio, services, shopping, streaks, tracking, weight_trend
from . import agora as agora_mod
from workouts import services as treino_services
from .calculations import (
    KCAL_PER_G_CARB,
    KCAL_PER_G_FAT,
    KCAL_PER_G_PROTEIN,
    activity_factor,
)
from .models import HydrationLog, MealOption, MealSlot, MealStatus, OptionLabel
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


class TodayView(PlanRequiredMixin, TemplateView):
    template_name = "plans/today.html"

    def get(self, request, *args, **kwargs):
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

        slots = list(
            self.plan.slots.prefetch_related("options__template__items__food")
        )
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

        summary = tracking.day_summary(self.request.user, self.plan, today)
        menu = menu_totals(slots)

        recusa = recusa_pendente(self.request, "hoje")
        meta_agua = weight_trend.hidratacao_ml(self.plan.weight_kg)
        registro = HydrationLog.objects.filter(
            user=self.request.user, date=today
        ).first()
        bebido = registro.ml if registro else 0

        # O estado do treino de hoje é CONSUMIDO do Treino V3, não recalculado.
        #
        # `estado_do_treino` deriva tudo de `ExerciseLog` e não escreve nada —
        # e não chama `sync_active_routine`: montar rotina é trabalho da aba de
        # treino, e fazer isso aqui daria à tela de comida o poder de criar
        # ficha como efeito colateral de uma visita.
        estado_treino = treino_services.estado_do_treino(self.request.user, dia=today)

        # `localtime()` e não `datetime.now()`: o servidor roda em UTC e o
        # horário das refeições é o do fuso da pessoa. Sem isso o "agora" erra
        # por três horas, e a tela mostraria o almoço como ação às nove da
        # manhã.
        acao = agora_mod.proxima_acao(
            slots=slots,
            treino=estado_treino,
            meta_agua=meta_agua,
            bebido=bebido,
            agora=timezone.localtime(),
        )
        # A lista concorda com o topo porque LÊ a decisão dele, em vez de
        # refazer a conta.
        agora_mod.marcar_refeicoes(slots, acao, timezone.localtime())
        context.update(
            {
                "plan": self.plan,
                "profile": self.request.user.profile,
                "macros": macro_rows(self.plan, summary),
                "breakdown": breakdown(self.plan),
                "balance": energy_balance(self.plan),
                "menu": menu,
                # Diferença entre o cardápio montado e a meta. A tela mostra
                # "bate com a meta" quando é irrelevante, e o número quando não é.
                "menu_gap": menu["kcal"] - self.plan.target_kcal,
                "menu_on_target": abs(menu["kcal"] - self.plan.target_kcal) <= MENU_TOLERANCE_KCAL,
                "acao": acao,
                "treino_hoje": estado_treino,
                "hidratacao_ml": meta_agua,
                "hidratacao_bebida": bebido,
                "hidratacao_pct": (
                    min(100, int(bebido * 100 / meta_agua)) if meta_agua else 0
                ),
                "agua_completa": bool(meta_agua) and bebido >= meta_agua,
                "ofensiva": streaks.calcular(
                    self.request.user, hoje=today, meta_agua_ml=meta_agua
                ),
                # O convite para se pesar. A regra é do domínio e não da view:
                # a view pergunta, `weight_trend` responde. Consulta dirigida à
                # semana — `analisar()` carregaria o histórico inteiro para
                # responder isto, e esta é a tela mais aberta do app.
                "convite_pesagem": weight_trend.convidar_a_pesar(
                    self.request.user, hoje=today
                ),
                # `None` quando não há erro pendente DESTA tela; string
                # (às vezes vazia) quando há. `houve_recusa` carrega essa
                # diferença para o template, que não consegue distinguir
                # "sem erro" de "erro com campo em branco" olhando só o texto.
                "houve_recusa": recusa is not None,
                "peso_recusado": recusa or "",
                "proteina_perdida": proteina_perdida(slots),
                # O catálogo do `<datalist>` e as linhas em branco do painel
                # "comi outra coisa". `range` no contexto porque o template do
                # Django não sabe contar, e um `{% for %}` sobre uma lista de
                # três nadas é mais honesto que três blocos copiados.
                "alimentos": Food.objects.filter(is_active=True).order_by("name"),
                "itens_fora": range(tracking.MAX_ITENS_FORA),
                "nav": "today",
                "training_days": self.request.user.training_days.all(),
                "slots": slots,
                "today": today,
                "summary": summary,
            }
        )
        return context


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
    return reverse("plans:today") + ancora


class MarkMealView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Marca uma refeição do dia. A AÇÃO é só POST — isso muda estado.

    O GET devolve a tela do dia, e não um 405 em branco: ver
    `config/acoes.py`.

    A ação chega como `status` e, quando é "comi", vem junto o id da opção
    escolhida. O slot é buscado dentro do plano ATIVO do próprio usuário: sem
    esse filtro, um id de outra pessoa marcaria refeição na conta errada.
    """

    def post(self, request, slot_id, *args, **kwargs):
        slot = get_object_or_404(
            MealSlot, pk=slot_id, plan__user=request.user, plan__is_active=True
        )
        status = request.POST.get("status")
        if status not in MealStatus.values:
            return redirect("plans:today")

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
            macros = tracking.macros_de_itens(_itens_descritos(request.POST))

        tracking.log_meal(request.user, slot, status, option, notes=notes, macros=macros)
        return redirect(_hoje_em("#slot-%d" % slot.pk))


#: Teto de gramas por alimento numa refeição fora do plano.
#:
#: Três quilos é absurdo de propósito: o número existe para barrar dedo
#: escorregando no teclado ("1000" virando "10000"), e não para julgar quanto
#: alguém comeu. Vale para a SOMA das linhas daquele alimento.
LIMITE_GRAMAS = Decimal("3000")


def _itens_descritos(dados) -> list:
    """Os pares `(Food, gramas)` que a pessoa descreveu, ignorando o resto.

    Casa por NOME e não por id porque a entrada é um `<input list="...">`: o
    datalist sugere, e a pessoa pode digitar qualquer coisa por cima. Nome que
    não bate com o catálogo é descartado em silêncio — o registro ainda vale
    pela descrição, e recusar a refeição inteira por causa de uma linha mal
    digitada é o caminho mais curto para ela parar de registrar.

    Um `<select>` com os 61 alimentos daria o id de graça e custaria 61 opções
    por linha, vezes três linhas, vezes cinco horários: 900 nós de DOM na tela
    mais visitada do app, para uma ação que quase nunca acontece.
    """
    nomes = dados.getlist("alimento")[: tracking.MAX_ITENS_FORA]
    gramas = dados.getlist("gramas")[: tracking.MAX_ITENS_FORA]

    pedidos = {}
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

    if not pedidos:
        return []

    # Uma consulta, e o casamento sem diferenciar maiúscula acontece em
    # Python: são 61 alimentos ativos, e um `iexact` por linha seriam três
    # idas ao banco para comparar com uma lista que cabe na memória.
    por_nome = {
        food.name.casefold(): food for food in Food.objects.filter(is_active=True)
    }
    return [
        (por_nome[nome], quantidade)
        for nome, quantidade in pedidos.items()
        if nome in por_nome
    ]


class ClearMealView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Desfaz a marcação de uma refeição do dia."""

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
        semanas_de_agua = tracking.agua_por_semana(self.request.user)
        semanas_de_treino = progresso.dias_treinados(self.request.user)
        entries = list(self.request.user.weight_entries.all()[:10])
        hoje = timezone.localdate()
        de_hoje = entries[0] if entries and entries[0].date == hoje else None

        context.update(
            {
                "plan": plan,
                "rows": rows,
                "totals": tracking.adherence(rows),
                "days": tracking.HISTORY_DAYS,
                "weight_entries": entries,
                "tendencia": weight_trend.analisar(self.request.user),
                # Preenche o campo com o peso já registrado hoje: salvar de
                # novo é corrigir, e corrigir começa do valor que está lá.
                "peso_de_hoje": de_hoje.weight_kg if de_hoje else None,
                "houve_recusa": recusa is not None,
                "peso_recusado": recusa or "",
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
                "cargas": progresso.progressao_de_carga(self.request.user),
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
    """

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
        else:
            profile.recalibrated_at = timezone.now()
            profile.save(update_fields=["recalibrated_at"])
            messages.info(
                request,
                "Combinado. Tente somar uns 20 minutos de caminhada por dia — "
                "perguntamos de novo daqui a algumas semanas.",
            )

        return redirect(reverse("plans:history"))


class RecalculatePlanView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Recálculo manual: a AÇÃO é só por POST.

    O recálculo automático já cobre mudança de dado; este botão existe para o
    caso de a pessoa querer forçar um plano novo (voltou de férias, mudou de
    fase) e para deixar explícito que recalcular é uma ação, não um efeito
    colateral de abrir uma tela.
    """

    def post(self, request, *args, **kwargs):
        try:
            services.create_plan(request.user)
        except services.IncompleteProfile:
            return redirect("accounts:onboarding")
        messages.success(request, "Meta recalculada com os seus dados de hoje.")
        return redirect("plans:today")


class ShoppingListView(PlanRequiredMixin, TemplateView):
    """A lista de compras da semana, por corredor de supermercado."""

    template_name = "plans/shopping.html"

    def get(self, request, *args, **kwargs):
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
        context.update(
            {
                # A lista é uma subtela da dieta: manter a aba Dieta acesa é
                # melhor que deixar a barra inteira apagada, que dá sensação de
                # ter saído do app.
                "nav": "today",
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

    def post(self, request, *args, **kwargs):
        try:
            ml = int(request.POST.get("ml", 0))
        except (TypeError, ValueError):
            ml = 0

        # A validação vem ANTES de criar a linha. Ao contrário, um valor
        # inválido deixava uma linha de 0 ml no banco — inofensiva na conta e
        # suja o bastante para confundir quem for depurar o dia depois.
        #
        # De volta aos três botões: a faixa larga existia para a entrada por
        # voz, que foi removida. Sem ela, aceitar qualquer múltiplo de dez seria
        # aceitar um valor que nenhuma tela produz.
        if ml != 0 and ml not in self.PASSOS:
            messages.error(request, "Quantidade de água inválida.")
            return redirect("plans:today")

        # Água SOMA, então reenviar aplica de novo. A trava transforma o
        # reenvio da fila offline numa consulta.
        if SyncedOperation.ja_aplicada(request.user, request.POST.get("op_id")):
            return redirect(_hoje_em("#hidratacao"))

        hoje = timezone.localdate()
        registro, _ = HydrationLog.objects.get_or_create(user=request.user, date=hoje)

        if ml == 0:
            # Zerar é o desfazer: tocou errado, começa o dia de novo.
            HydrationLog.objects.filter(pk=registro.pk).update(
                ml=0, updated_at=timezone.now()
            )
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
            # `Least` mantém o teto de 10 litros no dia sem voltar para Python.
            # `updated_at` vai explícito porque `auto_now` só age em `save()`,
            # e `update()` não passa por ele.
            HydrationLog.objects.filter(pk=registro.pk).update(
                ml=Least(F("ml") + ml, Value(10000)),
                updated_at=timezone.now(),
            )

        return redirect(_hoje_em("#hidratacao"))
