"""Telas do plano: a meta, o cardápio do dia e o acompanhamento.

A rota `today` concentra o uso diário — meta, refeições e marcação — porque é
a única tela que a pessoa abre várias vezes por dia. O histórico fica numa
rota separada, que é consulta ocasional.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import ACTIVITY_FACTORS, SyncedOperation
from accounts.views import OnboardingRequiredMixin, recusa_pendente
from catalog.models import Food

from . import services, shopping, streaks, tracking, weight_trend
from . import agora as agora_mod
from workouts import services as treino_services
from .calculations import (
    KCAL_PER_G_CARB,
    KCAL_PER_G_FAT,
    KCAL_PER_G_PROTEIN,
    activity_factor,
)
from .models import HydrationLog, MealOption, MealSlot, MealStatus, OptionLabel


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
        macros.append(
            {
                "name": name,
                "grams": grams,
                "kcal": grams * kcal_per_g,
                "pct": round(grams * kcal_per_g * 100 / total),
                "slug": slug,
                "eaten": eaten,
                "eaten_pct": min(round(eaten * 100 / (grams or 1)), 100),
                "left": max(grams - eaten, 0),
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
    """
    totals = {"kcal": 0, "protein_g": 0, "carb_g": 0, "fat_g": 0}
    for slot in slots:
        option = next(iter(slot.options.all()), None)
        if option is None:
            continue
        totals["kcal"] += int(option.kcal)
        totals["protein_g"] += int(option.protein_g)
        totals["carb_g"] += int(option.carb_g)
        totals["fat_g"] += int(option.fat_g)
    return totals


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
            messages.info(request, "Faltou completar seu cadastro para calcularmos a dieta.")
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


class MarkMealView(OnboardingRequiredMixin, View):
    """Marca uma refeição do dia. Só POST — isso muda estado.

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
            # `select_related` porque o snapshot do log lê `template.name`:
            # sem ele, marcar uma refeição custaria uma consulta a mais só
            # para buscar o nome que já vem no mesmo caminho.
            option = get_object_or_404(
                MealOption.objects.select_related("template"),
                pk=request.POST.get("option"),
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
        return redirect("plans:today")


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


class ClearMealView(OnboardingRequiredMixin, View):
    """Desfaz a marcação de uma refeição do dia."""

    def post(self, request, slot_id, *args, **kwargs):
        slot = get_object_or_404(
            MealSlot, pk=slot_id, plan__user=request.user, plan__is_active=True
        )
        slot.logs.filter(user=request.user, date=timezone.localdate()).delete()
        return redirect("plans:today")


class HistoryView(OnboardingRequiredMixin, TemplateView):
    template_name = "plans/history.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = tracking.history(self.request.user)
        plan = services.get_active_plan(self.request.user)
        for row in rows:
            # A barra compara o dia com a meta que vale hoje. O plano é um
            # snapshot, então o ideal seria a meta da época — fica para quando
            # existir mais de um plano por semana na prática.
            row["pct"] = min(int(row["kcal"] * 100 / (plan.target_kcal or 1)), 100)
        # A lista é materializada aqui porque o peso de hoje sai dela: as
        # pesagens vêm ordenadas por data decrescente, então se existe uma de
        # hoje ela é a primeira. Uma consulta a mais só para reencontrar a
        # linha que já está na mão seria consulta paga duas vezes.
        recusa = recusa_pendente(self.request, "metricas")
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
                "nav": "history",
            }
        )
        return context


class RecalibrateView(OnboardingRequiredMixin, View):
    """Aplica — ou recusa — o ajuste sugerido quando a média empaca.

    O corte fica guardado no perfil e não no plano: plano é snapshot e é
    refeito a cada mudança de peso, então gravar o ajuste nele o faria sumir
    na primeira pesagem. No perfil, ele acompanha a pessoa.

    "Prefiro me mexer mais" não é um botão decorativo: aumentar o gasto é uma
    resposta legítima e às vezes melhor que comer menos. O app registra a
    escolha para não repetir a pergunta na semana seguinte.
    """

    def post(self, request, *args, **kwargs):
        profile = request.user.profile
        acao = request.POST.get("acao")

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


class RecalculatePlanView(OnboardingRequiredMixin, View):
    """Recálculo manual, só por POST.

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


class LogHydrationView(OnboardingRequiredMixin, View):
    """Soma água ao dia. Só POST — isso muda estado.

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
            return redirect("plans:today")

        hoje = timezone.localdate()
        registro, _ = HydrationLog.objects.get_or_create(user=request.user, date=hoje)

        if ml == 0:
            # Zerar é o desfazer: tocou errado, começa o dia de novo.
            registro.ml = 0
        else:
            # Teto de 10 litros no DIA: acima disso é toque preso, não
            # hidratação, e um número absurdo estragaria a barra e a ofensiva.
            registro.ml = min(registro.ml + ml, 10000)

        registro.save(update_fields=["ml", "updated_at"])
        return redirect("plans:today")
