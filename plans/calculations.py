"""Cálculo da meta calórica e da divisão de macros.

Este módulo é **puro**: recebe números, devolve números, não toca no banco e
não conhece Django. Ler perfil, congelar snapshot e salvar plano é trabalho do
`services.py`. A separação é o que permite testar a matemática com uma tabela
de casos, sem criar usuário nenhum.

O caminho do cálculo é sempre o mesmo:

    TMB  ->  x fator de atividade (rotina + treino)  =  TDEE
    TDEE ->  ajuste do objetivo, com travas           =  meta calórica
    meta ->  proteína por kg, gordura por % das calorias, carboidrato no resto
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from accounts.models import ACTIVITY_FACTORS, FULL_TRAINING_WEEK, Goal, Sex

#: Identificador gravado em NutritionPlan.formula. Se um dia entrar uma segunda
#: fórmula (Katch-McArdle, por exemplo), os planos antigos continuam sabendo
#: por qual conta eles passaram.
FORMULA_MIFFLIN = "mifflin_st_jeor"

#: Teto da meta para quem quer emagrecer ou manter, quando o peso é normal.
#: Acima disso a conta quase sempre veio de fator de atividade otimista, e o
#: efeito prático é uma "dieta" que ninguém perde peso seguindo. Não é limite
#: fisiológico — é trava contra hiperescala da própria fórmula.
SAFE_MAX_KCAL = 2800

#: Peso a partir do qual passar de 2.800 kcal é esperado, não suspeito: gente
#: grande gasta mais mesmo, e cortar a meta aí produziria um déficit enorme.
EXTREME_WEIGHT_KG = Decimal("120")

#: Faixa do déficit de quem está emagrecendo, em kcal por dia. O percentual
#: decide onde dentro da faixa a pessoa cai; a faixa impede os dois extremos —
#: déficit pequeno demais para dar resultado e déficit grande demais para ser
#: sustentado sem perder massa magra.
MIN_DEFICIT_KCAL = Decimal("300")
MAX_DEFICIT_KCAL = Decimal("500")

#: Ajuste sobre o TDEE por objetivo. Percentual, não valor fixo: 500 kcal a
#: menos é ~15% para quem gasta 3.200 e ~28% para quem gasta 1.800 — o mesmo
#: número em kcal produz déficits muito diferentes.
#:
#: RECOMP (emagrecer e ganhar massa ao mesmo tempo) fica entre os dois com um
#: déficit de 5%: grande o bastante para a gordura cair ao longo dos meses,
#: pequeno o bastante para o treino continuar rendendo e o músculo ter energia
#: para ser construído. É o objetivo mais lento na balança de propósito — os
#: dois resultados acontecem juntos, e nenhum deles no ritmo de quem persegue
#: um só.
GOAL_ADJUSTMENT = {
    Goal.CUT: Decimal("-0.20"),
    Goal.BULK: Decimal("0.10"),
    Goal.RECOMP: Decimal("-0.05"),
    Goal.MAINTAIN: Decimal("0.00"),
}

#: Explicação que acompanha a meta quando o objetivo pede um aviso. Só a
#: recomposição tem uma: ela é a única em que a balança quase não se mexe, e
#: sem essa frase a pessoa conclui em três semanas que a dieta não funcionou.
GOAL_NOTE = {
    Goal.RECOMP: (
        "Você escolheu perder gordura e ganhar músculo ao mesmo tempo, então a meta "
        "ficou pouco abaixo do seu gasto e com mais proteína. A balança vai se mexer "
        "devagar — acompanhe o espelho, a roupa e a carga do treino."
    ),
}

#: Piso de segurança da meta. Nunca prescrevemos abaixo da TMB — comer menos do
#: que o corpo gasta em repouso não é dieta, é restrição que derruba aderência
#: e massa magra. O mínimo absoluto é a recomendação clássica de piso para
#: dietas sem acompanhamento clínico.
ABSOLUTE_MIN_KCAL = {Sex.MALE: 1500, Sex.FEMALE: 1200}

#: Proteína por kg de peso atual, por objetivo. O padrão de 1,8 g/kg atende
#: emagrecer, ganhar massa e manter — é o patamar em que a literatura para de
#: mostrar ganho adicional para quem treina com regularidade.
#:
#: RECOMP é a exceção, e a razão é a única situação em que os dois processos
#: disputam: sem energia sobrando, a proteína deixa de ser só matéria-prima e
#: passa a ser o sinal que decide se o corpo mantém ou consome o músculo.
#: 2,0 g/kg é o piso das recomendações para déficit com treino de força.
PROTEIN_G_PER_KG = Decimal("1.8")
PROTEIN_G_PER_KG_BY_GOAL = {Goal.RECOMP: Decimal("2.0")}
FAT_KCAL_SHARE = Decimal("0.25")
#: Piso de gordura: abaixo disso a produção hormonal e a absorção de vitaminas
#: lipossolúveis sofrem. É o limite até onde a gordura pode ceder espaço.
MIN_FAT_G_PER_KG = Decimal("0.6")
#: Piso de carboidrato: abaixo disso não dá para treinar bem nem montar
#: refeições comuns com o catálogo de alimentos.
MIN_CARB_G = 50

KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_CARB = 4
KCAL_PER_G_FAT = 9


@dataclass(frozen=True)
class PlanInputs:
    """Tudo que o cálculo precisa saber sobre a pessoa, num objeto só.

    É de propósito um dataclass burro em vez do Profile: o cálculo roda igual
    para dados vindos do banco, de um teste ou de uma simulação de "e se eu
    pesasse 5 kg a menos".
    """

    sex: str
    weight_kg: Decimal
    height_cm: int
    age_years: int
    activity_level: str
    goal: str
    #: Duração de cada sessão de treino da semana, em minutos. A frequência é
    #: o len() disso — não existe campo separado que possa dessincronizar.
    session_minutes: tuple = ()

    @property
    def training_days_per_week(self) -> int:
        return len(self.session_minutes)


@dataclass(frozen=True)
class PlanResult:
    """Saída do cálculo, pronta para virar um NutritionPlan."""

    bmr_kcal: int
    #: O multiplicador que foi usado — a tela mostra para a conta ser conferível.
    activity_factor: Decimal
    tdee_kcal: int
    target_kcal: int
    protein_g: int
    carb_g: int
    fat_g: int
    formula: str
    notes: str


def _round(value) -> int:
    """Arredonda meio para cima.

    O round() embutido usa banker's rounding (round(2.5) == 2), que faz a conta
    não bater quando alguém confere no papel.
    """
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def bmr_mifflin_st_jeor(*, sex, weight_kg, height_cm, age_years) -> Decimal:
    """Taxa metabólica basal — o que o corpo gasta em repouso absoluto.

    Mifflin-St Jeor (1990) é a fórmula preditiva mais precisa entre as que
    dependem só de peso, altura, idade e sexo. Katch-McArdle acerta mais em
    quem é muito magro ou muito gordo, mas exige percentual de gordura
    corporal — dado que o onboarding não pede porque quase ninguém sabe o seu.
    """
    weight_kg = Decimal(weight_kg)
    base = (
        Decimal(10) * weight_kg
        + Decimal("6.25") * Decimal(height_cm)
        - Decimal(5) * Decimal(age_years)
    )
    return base + (Decimal(5) if sex == Sex.MALE else Decimal(-161))


def activity_factor(activity_level, training_days_per_week=0) -> Decimal:
    """O multiplicador da pessoa dentro da faixa do nível dela.

    Cada nível é uma faixa (1,25-1,35 / 1,40-1,45 / 1,50-1,60) porque duas
    pessoas com a mesma rotina podem treinar uma vez ou cinco vezes por semana,
    e é essa diferença que a faixa acomoda. Quem não treina fica no piso; quem
    treina cinco vezes ou mais chega ao teto; no meio, a posição é proporcional.

    O que este desenho evita é o erro que a versão anterior cometia: somar o
    gasto do treino por fora, com a fórmula do MET, que trata uma hora de
    musculação como uma hora de esforço contínuo. Metade de um treino de força
    é descanso entre séries — contar tudo inflava a meta de quem mais precisava
    dela apertada.
    """
    minimo, maximo = ACTIVITY_FACTORS[activity_level]
    sessoes = min(max(int(training_days_per_week), 0), FULL_TRAINING_WEEK)
    proporcao = Decimal(sessoes) / Decimal(FULL_TRAINING_WEEK)
    return minimo + (maximo - minimo) * proporcao


def tdee(bmr, activity_level, training_days_per_week=0) -> Decimal:
    """Gasto total do dia: a TMB multiplicada pelo fator de atividade.

    Um multiplicador só, cobrindo rotina e treino. É menos sofisticado que
    somar MET por minuto de academia — e mais honesto, porque a precisão
    daquela soma era aparente: ela dependia de a pessoa saber quantos minutos
    realmente treina, e tratava série e descanso como o mesmo esforço.
    """
    return Decimal(bmr) * activity_factor(activity_level, training_days_per_week)


def goal_adjustment(tdee_value, goal) -> Decimal:
    """Quantas kcal somar ou tirar do gasto, por objetivo.

    Emagrecer usa percentual **preso numa faixa de 300 a 500 kcal**. O
    percentual sozinho tratava mal os dois extremos: 20% de um gasto de 1.800
    são 360 kcal (ok), mas 20% de 3.200 são 640 — déficit que quase ninguém
    sustenta sem perder massa magra e sem desistir. A faixa mantém o critério
    proporcional onde ele funciona e corta os exageros nas pontas.

    Os outros objetivos seguem percentuais: ganhar massa não tem o mesmo risco
    (o excesso vira gordura, não é questão de segurança) e a recomposição
    depende de um déficit pequeno de propósito — prendê-la a um mínimo de 300
    kcal destruiria justamente o que a define.
    """
    ajuste = Decimal(tdee_value) * GOAL_ADJUSTMENT[goal]
    if goal != Goal.CUT:
        return ajuste

    deficit = min(max(abs(ajuste), MIN_DEFICIT_KCAL), MAX_DEFICIT_KCAL)
    return -deficit


def target_kcal(tdee_value, goal, bmr, sex, weight_kg=None) -> tuple:
    """Aplica o ajuste do objetivo respeitando pisos e teto de segurança.

    Devolve (meta, avisos). Os avisos só vêm preenchidos quando uma trava
    entrou em ação — a tela precisa poder explicar por que a meta não é
    exatamente o gasto menos o déficit.

    São três travas, nesta ordem:

    1. **Piso**: nunca abaixo da TMB nem do mínimo absoluto por sexo.
    2. **Teto de 2.800 kcal** para quem quer emagrecer ou manter. Meta acima
       disso quase sempre vem de fator de atividade otimista, e o resultado
       prático é uma dieta que não emagrece ninguém.
    3. **Exceção do peso extremo**: acima de 120 kg o teto não se aplica, mas
       a meta sai explicada. Cortar a conta de alguém que gasta muito mesmo
       produziria um déficit gigante disfarçado de segurança.

    **Quando o teto morde, o déficit pode passar dos 500 kcal da faixa.** É
    proposital, e a ordem das travas é que decide: alguém com gasto estimado de
    3.300 kcal e peso normal tem a meta limitada a 2.800, o que dá um déficit
    de 500 e pouco. Não é perigoso — para quem realmente gasta tudo isso, 528
    kcal são 16% do gasto — e, se o gasto estiver inflado (que é justamente a
    suspeita que faz o teto existir), o déficit real é menor que o mostrado. A
    nota na tela explica para a pessoa não achar que a conta ficou torta.
    """
    avisos = []
    raw = Decimal(tdee_value) + goal_adjustment(tdee_value, goal)

    floor = max(Decimal(bmr), Decimal(ABSOLUTE_MIN_KCAL[sex]))
    if raw < floor:
        raw = floor
        avisos.append(
            "O déficit cheio ficaria abaixo do seu gasto em repouso, então a meta foi "
            "elevada até esse piso. O emagrecimento fica mais lento, e mais seguro."
        )

    if goal in (Goal.CUT, Goal.MAINTAIN) and raw > SAFE_MAX_KCAL:
        pesado = weight_kg is not None and Decimal(weight_kg) > EXTREME_WEIGHT_KG
        if pesado:
            avisos.append(
                f"Sua meta passou de {SAFE_MAX_KCAL} kcal porque o seu peso realmente "
                "sustenta um gasto alto. Se o peso cair e a meta não acompanhar, "
                "registre a pesagem para o cálculo se ajustar."
            )
        else:
            raw = Decimal(SAFE_MAX_KCAL)
            avisos.append(
                f"A conta chegou acima de {SAFE_MAX_KCAL} kcal, o que costuma significar "
                "nível de atividade otimista demais. A meta foi limitada a esse teto — se "
                "o peso não se mexer em duas ou três semanas, revise o nível de atividade "
                "antes de cortar mais comida."
            )

    return _round(raw), " ".join(avisos)


def protein_per_kg(goal) -> Decimal:
    """Quantos gramas de proteína por kg o objetivo pede."""
    return PROTEIN_G_PER_KG_BY_GOAL.get(goal, PROTEIN_G_PER_KG)


def macros(target, weight_kg, goal) -> tuple:
    """Divide a meta calórica em proteína, gordura e carboidrato.

    A ordem importa e não é arbitrária:

    1. **Proteína primeiro**, 1,8 g/kg (2,0 na recomposição) — é o macro com
       alvo absoluto, o que preserva massa magra no déficit e o que dá
       saciedade. Não é sobra de nada.
    2. **Gordura por percentual** (25% das calorias), com piso de 0,6 g/kg para
       não comprometer a parte hormonal.
    3. **Carboidrato fica com o que sobrou** — é o macro flexível, o combustível
       do treino, e o que a pessoa mais ajusta no dia a dia.

    O objetivo entra aqui, e não só no total de calorias, porque duas metas de
    2.000 kcal podem pedir dietas diferentes: quem quer recompor precisa da
    mesma energia distribuída com mais proteína.

    Devolve (proteína_g, carboidrato_g, gordura_g, aviso).
    """
    weight_kg = Decimal(weight_kg)
    notes = []

    protein_g = _round(weight_kg * protein_per_kg(goal))
    fat_floor_g = _round(weight_kg * MIN_FAT_G_PER_KG)
    fat_g = max(_round(Decimal(target) * FAT_KCAL_SHARE / KCAL_PER_G_FAT), fat_floor_g)

    def remaining_carb(fat_grams):
        left = Decimal(target) - protein_g * KCAL_PER_G_PROTEIN - fat_grams * KCAL_PER_G_FAT
        return _round(left / KCAL_PER_G_CARB)

    carb_g = remaining_carb(fat_g)
    if carb_g < MIN_CARB_G and fat_g > fat_floor_g:
        # Meta apertada: a gordura cede até o piso para liberar carboidrato.
        fat_g = fat_floor_g
        carb_g = remaining_carb(fat_g)
        notes.append(
            "Sua meta ficou justa para o seu peso, então a gordura foi ao mínimo "
            "saudável para sobrar carboidrato para treinar."
        )
    if carb_g < MIN_CARB_G:
        # Só acontece com peso alto e meta baixa ao mesmo tempo.
        carb_g = max(carb_g, 0)
        notes.append(
            "Com esse peso e essa meta os macros ficam no limite do que dá para "
            "montar comendo comida de verdade. Vale conferir com um nutricionista."
        )
    return protein_g, carb_g, fat_g, " ".join(notes)


def calculate(inputs: PlanInputs) -> PlanResult:
    """Roda o cálculo inteiro e devolve o resultado pronto para persistir."""
    bmr = bmr_mifflin_st_jeor(
        sex=inputs.sex,
        weight_kg=inputs.weight_kg,
        height_cm=inputs.height_cm,
        age_years=inputs.age_years,
    )
    total = tdee(bmr, inputs.activity_level, inputs.training_days_per_week)
    target, floor_note = target_kcal(
        total, inputs.goal, bmr, inputs.sex, weight_kg=inputs.weight_kg
    )
    protein_g, carb_g, fat_g, macro_note = macros(target, inputs.weight_kg, inputs.goal)

    return PlanResult(
        bmr_kcal=_round(bmr),
        activity_factor=activity_factor(inputs.activity_level, inputs.training_days_per_week),
        tdee_kcal=_round(total),
        target_kcal=target,
        protein_g=protein_g,
        carb_g=carb_g,
        fat_g=fat_g,
        formula=FORMULA_MIFFLIN,
        notes=" ".join(
            n for n in (GOAL_NOTE.get(inputs.goal, ""), floor_note, macro_note) if n
        ).strip(),
    )
