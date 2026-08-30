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

from accounts.models import MealStyle
from catalog.models import MealCategory, MealTemplate, TagKind

from .models import MealOption, MealSlot
from .rodizio import POR_DIA

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

#: Quantas opções cada horário guarda no repertório PERSISTENTE.
#:
#: Quatro, e a tela mostra duas por dia — quem escolhe quais é
#: `plans/rodizio.py`. Antes eram duas, e as duas eram sempre as mesmas: o
#: cardápio da segunda era o cardápio do domingo, e a queixa de "pouca
#: variedade" nasceu daí.
#:
#: Não é o número de opções na tela. Esse continua sendo dois, e continua
#: saindo de `OptionLabel`, porque continua sendo decisão de produto: escolher
#: entre duas é escolher; escolher entre quatro é comparar.
#:
#: Quatro e não seis por causa do catálogo. Receita não se repete dentro do
#: horário (`unique_template_per_slot`) e o gerador ainda evita repetir entre
#: horários, então o dia inteiro consome quatro vezes o número de horários em
#: receitas distintas. Com cinco horários são vinte, e é o que o catálogo
#: sustenta com folga depois de aplicar restrição alimentar.
OPTIONS_PER_SLOT = 4

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

#: O que o cardápio econômico cobra de quem não é econômico.
#:
#: Peso e não filtro, e isto é a mesma decisão que já governa `prep_minutes`
#: nesta seção: uma restrição ELIMINA a receita, e receita eliminada deixa o
#: horário vazio quando o catálogo é pequeno. Um horário vazio é pior que um
#: horário caro — a pessoa fica sem saber o que comer, que é exatamente o que
#: o app existe para resolver.
#:
#: 0,45 por ingrediente caro é maior que a penalidade de "não é comida de
#: rotina" (0,35): na prática a receita com atum só ganha de uma econômica
#: que erre a caloria em quase metade. Ela perde, e continua existindo.
PREMIUM_INGREDIENT_PENALTY = Decimal("0.45")

#: Café da manhã e lanche com mais de dez minutos, para quem pediu rapidez.
#:
#: Os dois horários são os que competem com pressa real: um antes de sair de
#: casa, o outro no intervalo. Almoço e jantar ficam de fora porque ali a
#: pessoa já parou para comer, e vinte minutos de fogão são normais.
QUICK_PREP_MINUTES = 10
QUICK_PREP_PENALTY = Decimal("0.40")
QUICK_SLOTS = (MealCategory.BREAKFAST, MealCategory.SNACK)


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


def style_penalty(template, category: str, meal_style: str) -> Decimal:
    """O que o estilo de cardápio cobra desta receita neste horário.

    Zero para quem pediu variedade — o cardápio elaborado é o que o app já
    fazia, e o estilo não deve inventar custo onde ninguém pediu.
    """
    if meal_style != MealStyle.QUICK:
        return Decimal("0")

    penalidade = Decimal("0")

    # Um ingrediente caro basta para a receita cair; dois não a derrubam duas
    # vezes. O que pesa é a receita SER cara, e não quanto.
    if any(item.food.is_premium for item in template.items.all()):
        penalidade += PREMIUM_INGREDIENT_PENALTY

    if category in QUICK_SLOTS and template.prep_minutes > QUICK_PREP_MINUTES:
        penalidade += QUICK_PREP_PENALTY

    return penalidade


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


def score(macros: dict, slot, template, meal_style: str = None) -> Decimal:
    """Nota final de uma candidata: erro nutricional mais custo de execução."""
    return (
        deviation(macros, slot)
        + practicality_penalty(template)
        + style_penalty(template, slot.category, meal_style)
    )


def choose_options(
    slot, restriction_slugs, used_templates, meal_style=None, limite=None, ja=None
) -> list:
    """As melhores receitas para um horário, já escaladas.

    Devolve o REPERTÓRIO do horário — `OPTIONS_PER_SLOT` opções persistentes,
    ordenadas da melhor pontuação para a pior. Quais duas delas aparecem em
    cada dia é outra pergunta, e quem responde é `plans/rodizio.py`.

    As quatro saem da mesma pontuação que escolhia as duas: alvo calórico do
    slot, desvio de macro com peso dobrado na proteína, restrições alimentares,
    estilo de cardápio e praticidade. A terceira e a quarta são as terceira e
    quarta melhores — não são preenchimento para fechar número.

    `used_templates` carrega o que já foi usado nos horários anteriores: sem
    isso, o almoço e o jantar saem com as mesmas receitas, porque ambos olham
    para a mesma categoria e o mesmo alvo. Receita repetida só volta a ser
    aceita quando não há candidata inédita suficiente — melhor repetir do que
    deixar o horário vazio.
    """
    limite = OPTIONS_PER_SLOT if limite is None else limite
    ja = ja or []
    faltam = limite - len(ja)
    if faltam <= 0:
        return []
    proibidos = {opcao.template_id for opcao in ja}

    scored = []
    for template in candidates_for(slot.category, restriction_slugs):
        if template.pk in proibidos:
            continue
        scale = scale_for(template, slot.target_kcal)
        macros = template.compute_macros(scale)
        scored.append(
            (score(macros, slot, template, meal_style), template.pk, template, scale, macros)
        )
    scored.sort(key=lambda row: (row[0], row[1]))

    fresh = [row for row in scored if row[2].pk not in used_templates]
    chosen = fresh[:faltam]
    if len(chosen) + len(ja) < POR_DIA:
        # Repetir receita de outro horário é o ÚLTIMO recurso, e agora ele para
        # em `POR_DIA` em vez de encher até `OPTIONS_PER_SLOT`.
        #
        # O motivo original continua de pé: melhor repetir do que deixar o
        # horário sem o que mostrar. Só que ele valia quando o repertório era
        # dois e faltar um deixava a tela pela metade. Com repertório de quatro,
        # completar até quatro com repetição não salva tela nenhuma — as duas
        # primeiras já bastam — e cria um problema novo: no catálogo vegano, que
        # é o mais apertado, o dia inteiro passava a ter a mesma receita
        # aparecendo em horários diferentes, às vezes no MESMO dia depois do
        # rodízio projetar as duas.
        #
        # Repertório menor e honesto vence repertório cheio de cópia: quem tem
        # restrição apertada prefere três receitas diferentes a quatro com duas
        # iguais.
        repeats = [row for row in scored if row[2].pk in used_templates]
        chosen += repeats[: POR_DIA - len(chosen) - len(ja)]

    options = []
    for position, (_, _, template, scale, macros) in enumerate(chosen, start=len(ja)):
        used_templates.add(template.pk)
        options.append(
            MealOption(
                slot=slot,
                template=template,
                rank=position,
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

    # DUAS RODADAS, e a ordem é o ponto.
    #
    # Numa rodada só, o primeiro horário de uma categoria leva o repertório
    # inteiro e o segundo come as sobras. No catálogo vegano, que tem cinco
    # receitas principais, o almoço ficava com quatro e o jantar com uma — e
    # então precisava repetir uma do almoço para conseguir mostrar duas opções.
    # O cardápio V1 não tinha esse problema porque pedia dois por horário e
    # dois mais dois cabem em cinco; foi o repertório de quatro que criou a
    # disputa.
    #
    # Rodada 1 garante a TODO horário o que a tela precisa. Rodada 2 distribui
    # o que sobrou, na mesma ordem. Catálogo farto não nota diferença: as duas
    # rodadas somadas dão os mesmos quatro de antes, e na mesma ordem de
    # pontuação, porque a rodada 2 continua de onde a 1 parou.
    escolhidas = {}
    for limite in (POR_DIA, OPTIONS_PER_SLOT):
        for slot in slots:
            novas = choose_options(
                slot,
                restriction_slugs,
                used_templates,
                profile.meal_style,
                limite=limite,
                ja=escolhidas.get(slot.pk, []),
            )
            escolhidas.setdefault(slot.pk, []).extend(novas)

    for slot in slots:
        options = escolhidas.get(slot.pk, [])
        MealOption.objects.bulk_create(options)
        best_protein += max((option.protein_g for option in options), default=Decimal("0"))
        # O aviso compara com o que a TELA precisa, e não com o tamanho do
        # repertório. Ele sempre significou "este horário não consegue mostrar
        # o que promete"; quando o repertório era de dois e a tela mostrava
        # dois, as duas contas davam no mesmo. Agora o repertório é quatro e a
        # tela continua mostrando dois: reclamar de um horário com três
        # receitas seria avisar sobre um cardápio que funciona perfeitamente,
        # e um aviso que aparece sem consequência é um aviso que a pessoa
        # aprende a ignorar.
        if len(options) < POR_DIA:
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
