"""Geração do plano de refeições: horários, alvos por refeição e as opções.

O trabalho acontece em três fases bem separadas, e cada uma é testável sozinha:

1. **Horários** — as cinco refeições são espalhadas na janela entre acordar e
   dormir, e uma delas é puxada para depois do treino.
2. **Alvos** — a meta do dia é dividida entre as refeições por percentual, com
   sobra de arredondamento redistribuída para a soma bater exatamente.
3. **Opções** — para cada refeição, as receitas do catálogo que atendem às
   restrições são escaladas até o alvo e as duas com menor desvio ganham.

O que a etapa 3 decidiu continua valendo aqui: existe uma meta só, igual todo
dia, então o plano de refeições também é um só — não há versão de dia de treino
e versão de descanso.
"""
from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from catalog.models import MealCategory, MealTemplate, TagKind

from .models import MealOption, MealSlot, OptionLabel

MINUTES_IN_DAY = 24 * 60

#: A primeira refeição não é na hora exata de acordar, e a última não é na hora
#: de dormir — ninguém come com o despertador na mão nem deitando.
FIRST_MEAL_AFTER_WAKE = 30
LAST_MEAL_BEFORE_SLEEP = 90
#: Distância mínima entre duas refeições, usada quando a âncora do pós-treino
#: empurra os horários vizinhos.
MIN_GAP_MINUTES = 45
#: Quanto tempo depois do FIM do treino cai a refeição pós-treino.
POST_WORKOUT_DELAY = 45

#: Quantas opções tentamos oferecer por horário — exatamente duas, Opção A e
#: Opção B. O número não é escrito à mão: ele é a quantidade de rótulos em
#: `OptionLabel`, que é onde a regra mora. Assim não existe estado possível em
#: que o gerador queira uma terceira opção sem ter rótulo para ela, nem rótulo
#: sobrando que o gerador nunca usa.
OPTIONS_PER_SLOT = len(OptionLabel.values)

#: Limites do fator de escala de uma receita. Fora disso a porção deixa de ser
#: comida de verdade: 0,4x vira meia colher de arroz, 2,5x vira travessa.
MIN_SCALE = Decimal("0.50")
MAX_SCALE = Decimal("2.50")

#: Pesos do desvio. A proteína pesa o dobro porque é o macro com alvo absoluto
#: — sem esse peso o algoritmo bate a caloria com massa pura e ignora a meta
#: de proteína do dia.
KCAL_WEIGHT = Decimal("1")
PROTEIN_WEIGHT = Decimal("2")

#: Passar da proteína custa bem menos que ficar abaixo dela. A meta de proteína
#: é um piso funcional, não um teto: 80 g num almoço de 55 g não faz mal a
#: ninguém, enquanto 30 g deixa o dia devendo. Sem essa assimetria o algoritmo
#: fugia de frango e carne — que estouram o alvo — e enchia o almoço de tofu e
#: carne de soja para quem nunca pediu isso.
PROTEIN_OVERSHOOT_FACTOR = Decimal("0.35")

#: Penalidade de quem não é comida de rotina (`MealTemplate.everyday` falso).
#: O valor é da ordem de um erro de 35% na caloria: grande o bastante para a
#: receita elaborada só aparecer quando nenhuma simples serve, e pequeno o
#: bastante para não deixar o alvo nutricional em segundo plano.
NOT_EVERYDAY_PENALTY = Decimal("0.35")

#: Quanto da meta de proteína o cardápio precisa alcançar para o plano ser
#: honesto. Abaixo disso avisamos: não adianta prescrever 120 g de proteína se
#: as receitas que sobram depois das restrições só chegam a 87 g — a pessoa
#: seguiria o cardápio à risca e ficaria devendo sem saber por quê.
PROTEIN_COVERAGE_FLOOR = Decimal("0.85")

#: Acima disso o preparo começa a pesar, um pouco por minuto. Vinte minutos é
#: o teto do que se faz numa noite de semana sem planejar nada.
EASY_PREP_MINUTES = 20
PREP_PENALTY_PER_MINUTE = Decimal("0.01")
#: Teto da penalidade de preparo, para uma receita de forno não ser
#: eliminada por tempo quando ela é a única que atende às restrições.
MAX_PREP_PENALTY = Decimal("0.30")


@dataclass(frozen=True)
class SlotBlueprint:
    """O molde de uma refeição do dia, antes de virar linha no banco."""

    name: str
    category: str
    share: Decimal


#: Estrutura fixa do dia. Os percentuais somam 1,00.
DAY_BLUEPRINT = (
    SlotBlueprint("Café da manhã", MealCategory.BREAKFAST, Decimal("0.25")),
    SlotBlueprint("Lanche da manhã", MealCategory.SNACK, Decimal("0.10")),
    SlotBlueprint("Almoço", MealCategory.MAIN, Decimal("0.30")),
    SlotBlueprint("Lanche da tarde", MealCategory.SNACK, Decimal("0.10")),
    SlotBlueprint("Jantar", MealCategory.MAIN, Decimal("0.25")),
)


# --------------------------------------------------------------------------
# Fase 1 — horários
# --------------------------------------------------------------------------

def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _offset_from(wake: time, moment: time) -> int:
    """Minutos entre acordar e um horário qualquer.

    O `% MINUTES_IN_DAY` é o que faz quem dorme depois da meia-noite funcionar:
    dormir às 00:30 tendo acordado às 07:00 são 17h30 de janela, não -6h30.
    """
    return (_minutes(moment) - _minutes(wake)) % MINUTES_IN_DAY


def _time_at(wake: time, offset: int) -> time:
    total = (_minutes(wake) + offset) % MINUTES_IN_DAY
    return time(total // 60, total % 60)


def base_offsets(window: int, count: int) -> list:
    """Espalha `count` refeições uniformemente dentro da janela do dia."""
    first = FIRST_MEAL_AFTER_WAKE
    last = max(window - LAST_MEAL_BEFORE_SLEEP, first + count - 1)
    step = Decimal(last - first) / Decimal(count - 1)
    return [int(first + step * index) for index in range(count)]


def _anchor_post_workout(offsets: list, target_offset: int) -> tuple:
    """Puxa a refeição mais próxima para o horário do pós-treino.

    Escolher a mais próxima em vez de fixar uma refeição específica é o que faz
    a regra servir tanto para quem treina 6h da manhã (o café vira o pós-treino)
    quanto para quem treina 19h (o jantar vira). Depois de mover, os vizinhos
    cedem espaço para manter o intervalo mínimo — sem isso o plano sugere comer
    duas vezes em quinze minutos.
    """
    anchor = min(range(len(offsets)), key=lambda i: abs(offsets[i] - target_offset))
    offsets = list(offsets)
    offsets[anchor] = target_offset

    for index in range(anchor - 1, -1, -1):
        offsets[index] = min(offsets[index], offsets[index + 1] - MIN_GAP_MINUTES)
    for index in range(anchor + 1, len(offsets)):
        offsets[index] = max(offsets[index], offsets[index - 1] + MIN_GAP_MINUTES)
    return offsets, anchor


def slot_times(wake: time, sleep: time, training_end: time = None) -> tuple:
    """Horário de cada refeição do dia.

    Devolve (horários, índice do pós-treino ou None).
    """
    window = _offset_from(wake, sleep) or MINUTES_IN_DAY
    offsets = base_offsets(window, len(DAY_BLUEPRINT))
    anchor = None

    if training_end is not None:
        end = _offset_from(wake, training_end)
        # Duas amarras: a refeição nunca é antes de o treino acabar, e nunca
        # depois da hora de dormir. Quem treina 19:00 às 20:30 e dorme 21:00
        # come às 20:45 — apertado, mas é o horário real dessa pessoa. Sem essa
        # segunda amarra a âncora era descartada e o jantar caía às 19:30, no
        # meio do treino, que é bem pior do que comer tarde.
        target = min(end + POST_WORKOUT_DELAY, max(window - 15, end))
        offsets, anchor = _anchor_post_workout(offsets, target)

    offsets = [max(0, min(offset, window)) for offset in offsets]
    return [_time_at(wake, offset) for offset in offsets], anchor


# --------------------------------------------------------------------------
# Fase 2 — alvos por refeição
# --------------------------------------------------------------------------

def distribute(total: int, shares) -> list:
    """Divide um total inteiro em partes proporcionais, sem perder nada.

    Usa o método do maior resto: arredonda tudo para baixo e distribui as
    unidades que sobraram para quem tem a maior fração descartada. Arredondar
    cada parte isoladamente faria a soma das refeições não bater com a meta do
    dia — e é exatamente esse tipo de diferença de 3 kcal que faz alguém abrir
    uma issue perguntando se o app sabe somar.
    """
    exact = [Decimal(total) * Decimal(share) for share in shares]
    floors = [int(value) for value in exact]
    remainder = total - sum(floors)
    order = sorted(range(len(exact)), key=lambda i: exact[i] - floors[i], reverse=True)
    for index in order[:remainder]:
        floors[index] += 1
    return floors


def build_slots(plan, wake: time, sleep: time, training_end: time = None) -> list:
    """Cria (sem salvar) os MealSlot do plano, já com horário e alvo."""
    times, anchor = slot_times(wake, sleep, training_end)
    shares = [blueprint.share for blueprint in DAY_BLUEPRINT]

    kcal = distribute(plan.target_kcal, shares)
    protein = distribute(plan.protein_g, shares)
    carb = distribute(plan.carb_g, shares)
    fat = distribute(plan.fat_g, shares)

    slots = []
    for index, blueprint in enumerate(DAY_BLUEPRINT):
        name = blueprint.name
        if index == anchor:
            name = f"{name} (pós-treino)"
        slots.append(
            MealSlot(
                plan=plan,
                name=name,
                category=blueprint.category,
                time=times[index],
                order=index,
                target_kcal=kcal[index],
                target_protein_g=protein[index],
                target_carb_g=carb[index],
                target_fat_g=fat[index],
            )
        )
    return slots


# --------------------------------------------------------------------------
# Fase 3 — opções de cada refeição
# --------------------------------------------------------------------------

def candidates_for(category: str, restriction_slugs) -> list:
    """Receitas ativas da categoria que atendem a TODAS as restrições.

    Um `.filter(tags__slug__in=[...])` traria quem atende a qualquer uma delas;
    o filtro encadeado é o que dá a semântica de E — vegano E sem glúten.

    O `exclude` de ingrediente inativo é o que impede o cardápio de mandar a
    pessoa comprar algo que saiu do catálogo: basta desativar o alimento no
    admin para toda receita que depende dele parar de ser sugerida, sem
    precisar caçar receita por receita.
    """
    queryset = MealTemplate.objects.filter(is_active=True, category=category)
    for slug in restriction_slugs:
        queryset = queryset.filter(tags__slug=slug)
    queryset = queryset.exclude(items__food__is_active=False)
    return list(queryset.distinct().prefetch_related("items__food"))


def scale_for(template, target_kcal: int) -> Decimal:
    """Fator que leva a receita ao alvo calórico do horário.

    A conta isola a parte escalável porque os itens fixos (1 ovo, 1 fatia de
    pão) não crescem: dobrar a receita não dobra as calorias dela. Resolver
    `alvo = fixo + escalável × fator` é exato; usar `alvo / total` erraria
    proporcionalmente ao peso dos itens fixos.
    """
    fixed = Decimal("0")
    scalable = Decimal("0")
    for item in template.items.all():
        kcal = item.food.macros_for(item.quantity_g)["kcal"]
        if item.scalable:
            scalable += kcal
        else:
            fixed += kcal
    if scalable <= 0:
        return Decimal("1.00")
    raw = (Decimal(target_kcal) - fixed) / scalable
    return max(MIN_SCALE, min(MAX_SCALE, raw)).quantize(Decimal("0.01"))


def deviation(macros: dict, slot) -> Decimal:
    """Quanto essa receita escalada erra o alvo do horário. Menor é melhor."""
    kcal_target = Decimal(max(slot.target_kcal, 1))
    protein_target = Decimal(max(slot.target_protein_g, 1))

    # Caloria erra para os dois lados igual: é ela que decide se a pessoa
    # emagrece ou engorda.
    kcal_error = abs(macros["kcal"] - Decimal(slot.target_kcal)) / kcal_target

    protein_gap = macros["protein_g"] - Decimal(slot.target_protein_g)
    if protein_gap > 0:
        protein_gap *= PROTEIN_OVERSHOOT_FACTOR
    protein_error = abs(protein_gap) / protein_target

    return KCAL_WEIGHT * kcal_error + PROTEIN_WEIGHT * protein_error


def practicality_penalty(template) -> Decimal:
    """O quanto a receita atrapalha a vida de quem vai cozinhar.

    Entra somada ao desvio nutricional, e não como filtro, de propósito: dieta
    que a pessoa não consegue executar não é dieta. Mas como é só uma parcela
    da nota, uma receita elaborada ainda vence uma simples que erre feio o
    alvo — e continua entrando quando é a única que atende às restrições.
    """
    penalty = Decimal("0") if template.everyday else NOT_EVERYDAY_PENALTY
    extra_minutes = max(template.prep_minutes - EASY_PREP_MINUTES, 0)
    return penalty + min(
        PREP_PENALTY_PER_MINUTE * Decimal(extra_minutes), MAX_PREP_PENALTY
    )


def score(macros: dict, slot, template) -> Decimal:
    """Nota final de uma candidata: erro nutricional mais custo de execução."""
    return deviation(macros, slot) + practicality_penalty(template)


def choose_options(slot, restriction_slugs, used_templates) -> list:
    """As melhores receitas para um horário, já escaladas.

    `used_templates` carrega o que já foi usado nos horários anteriores: sem
    isso, o almoço e o jantar saem com as mesmas duas receitas, porque ambos
    olham para a mesma categoria e o mesmo alvo. Receita repetida só volta a
    ser aceita quando não há candidata inédita suficiente — melhor repetir do
    que deixar o horário vazio.
    """
    scored = []
    for template in candidates_for(slot.category, restriction_slugs):
        scale = scale_for(template, slot.target_kcal)
        macros = template.compute_macros(scale)
        scored.append((score(macros, slot, template), template.pk, template, scale, macros))
    scored.sort(key=lambda row: (row[0], row[1]))

    fresh = [row for row in scored if row[2].pk not in used_templates]
    chosen = fresh[:OPTIONS_PER_SLOT]
    if len(chosen) < OPTIONS_PER_SLOT:
        repeats = [row for row in scored if row[2].pk in used_templates]
        chosen += repeats[: OPTIONS_PER_SLOT - len(chosen)]

    options = []
    for position, (_, _, template, scale, macros) in enumerate(chosen):
        used_templates.add(template.pk)
        options.append(
            MealOption(
                slot=slot,
                template=template,
                label=OptionLabel.values[position],
                scale_factor=scale,
                kcal=macros["kcal"].quantize(Decimal("0.01")),
                protein_g=macros["protein_g"].quantize(Decimal("0.01")),
                carb_g=macros["carb_g"].quantize(Decimal("0.01")),
                fat_g=macros["fat_g"].quantize(Decimal("0.01")),
            )
        )
    return options


def generate(plan, profile) -> list:
    """Monta horários e opções do plano. Devolve a lista de avisos.

    Nenhum horário sem receita derruba a geração inteira: o plano sai com o que
    o catálogo permite e o aviso diz exatamente o que faltou. Com restrições
    apertadas e catálogo pequeno, um plano parcial e honesto é mais útil que
    uma tela de erro.
    """
    training_end = _training_end_for(profile.user)
    slots = build_slots(plan, profile.wake_time, profile.sleep_time, training_end)
    MealSlot.objects.bulk_create(slots)

    restriction_slugs = list(
        profile.dietary_tags.filter(kind=TagKind.RESTRICTION).values_list("slug", flat=True)
    )

    warnings = []
    used_templates = set()
    best_protein = Decimal("0")
    for slot in slots:
        options = choose_options(slot, restriction_slugs, used_templates)
        MealOption.objects.bulk_create(options)
        best_protein += max((option.protein_g for option in options), default=Decimal("0"))
        if len(options) < OPTIONS_PER_SLOT:
            warnings.append(
                f"{slot.name}: o catálogo tem só {len(options)} receita(s) que atendem "
                f"às suas restrições."
                if options
                else f"{slot.name}: nenhuma receita do catálogo atende às suas restrições."
            )

    warnings.extend(protein_coverage_warning(plan, best_protein))
    return warnings


def protein_coverage_warning(plan, best_protein) -> list:
    """Avisa quando nem o melhor cardápio possível chega perto da meta de proteína.

    Acontece com restrição apertada e comida barata: escolhendo sempre a opção
    mais proteica do horário, a soma do dia ainda fica abaixo do alvo. É um
    fato sobre o catálogo, não um erro do cálculo — e é informação que muda o
    que a pessoa faz (procurar um complemento, rever a restrição) em vez de
    deixá-la achando que segue o plano quando não segue.
    """
    target = Decimal(plan.protein_g)
    if not target or best_protein >= target * PROTEIN_COVERAGE_FLOOR:
        return []
    return [
        f"Escolhendo sempre a opção com mais proteína, o dia chega a cerca de "
        f"{best_protein:.0f} g contra a meta de {plan.protein_g} g. As receitas que "
        f"atendem às suas restrições não dão mais que isso sem sair do básico — "
        f"vale rever as restrições ou combinar um complemento com um nutricionista."
    ]


def _training_end_for(user) -> time:
    """Fim do treino, a partir do horário único informado no passo 3."""
    day = user.training_days.order_by("weekday").first()
    if day is None:
        return None
    end = (_minutes(day.start_time) + day.duration_min) % MINUTES_IN_DAY
    return time(end // 60, end % 60)
