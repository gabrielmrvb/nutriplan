"""Os números do painel de gestão, e o que cada um NÃO diz.

Regra que decide tudo aqui: só entra número que o dado sustenta. Este produto
não tem analytics — não existe evento de sessão, não existe log de abertura de
tela. O que existe é o que a pessoa GRAVOU: refeição marcada, água registrada,
série anotada, suplemento marcado.

Duas armadilhas de nomenclatura, evitadas de propósito:

"Ativos em 7 dias" NÃO é retenção D7. Retenção é de coorte — pega quem entrou
no dia zero e mede quem voltou no dia sete. O que este painel mede é "quem
gravou alguma coisa na última semana", que é outra pergunta e responde a outra
decisão. Chamar de retenção faria alguém comparar com benchmark de retenção.

Peso NÃO conta como engajamento. O passo 1 do onboarding EXIGE o peso: contá-lo
como ação voluntária transformaria "terminou o cadastro" em "está engajada", e
o funil mediria a si mesmo.

E `HydrationLog` só conta com `ml > 0`: a linha nasce por `get_or_create`
quando a tela do dia abre, então existir não é ter bebido água.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from accounts.models import CAMPO_DO_PILAR, ONBOARDING_DONE, Profile
from plans.models import HydrationLog, MealLog, NutritionPlan
from supplements.models import SupplementLog
from workouts.models import ExerciseLog, TrainingPlan

User = get_user_model()

#: Uma janela, um nome. Sete dias é o que cabe numa semana de hábito; trinta é
#: o horizonte em que dá para ver tendência sem esperar um trimestre.
JANELA_CURTA = 7
JANELA_LONGA = 30


def _acoes_voluntarias(desde=None):
    """As quatro coisas que a pessoa grava porque quis.

    Cada uma é um `Exists` — subconsulta anotada, não uma consulta por conta.
    Sem isso, um painel com 52 contas custaria 208 consultas, e o custo cresce
    com o produto.
    """
    filtros = {}
    if desde is not None:
        filtros["date__gte"] = desde
    return {
        "refeicao": Exists(MealLog.objects.filter(user=OuterRef("pk"), **filtros)),
        "agua": Exists(
            HydrationLog.objects.filter(user=OuterRef("pk"), ml__gt=0, **filtros)
        ),
        "serie": Exists(ExerciseLog.objects.filter(user=OuterRef("pk"), **filtros)),
        "suplemento": Exists(
            SupplementLog.objects.filter(user=OuterRef("pk"), **filtros)
        ),
    }


#: A condição "fez ALGUMA das quatro". Separada porque é usada duas vezes, com
#: janelas diferentes, e repetir a expressão convidaria as duas a divergirem.
FEZ_ALGUMA = (
    Q(refeicao=True) | Q(agua=True) | Q(serie=True) | Q(suplemento=True)
)


def numeros_do_painel():
    """Tudo que o painel mostra, em consultas de custo fixo.

    Custo fixo é a propriedade que importa aqui, e não o número: nenhuma
    delas cresce com a quantidade de contas. O número já esteve escrito
    ("cinco") e envelheceu na primeira chave nova.
    """
    hoje = timezone.localdate()
    curta = hoje - timedelta(days=JANELA_CURTA)
    longa = hoje - timedelta(days=JANELA_LONGA)

    contas = User.objects.aggregate(
        total=Count("id"),
        staff=Count("id", filter=Q(is_staff=True)),
        novas_na_semana=Count("id", filter=Q(date_joined__date__gte=curta)),
        novas_no_mes=Count("id", filter=Q(date_joined__date__gte=longa)),
    )

    por_classificacao = dict(
        User.objects.values_list("classificacao").annotate(quantas=Count("id"))
    )

    funil = User.objects.annotate(
        plano=Exists(NutritionPlan.objects.filter(user=OuterRef("pk"))),
        ficha=Exists(TrainingPlan.objects.filter(user=OuterRef("pk"))),
        **_acoes_voluntarias(),
    ).aggregate(
        com_plano=Count("id", filter=Q(plano=True)),
        com_ficha=Count("id", filter=Q(ficha=True)),
        com_acao=Count("id", filter=FEZ_ALGUMA),
    )

    recentes = User.objects.annotate(**_acoes_voluntarias(desde=curta)).aggregate(
        ativas=Count("id", filter=FEZ_ALGUMA)
    )

    terminaram = Profile.objects.filter(
        onboarding_step__gte=ONBOARDING_DONE
    ).count()

    # POR QUE AS PESSOAS ESTÃO ENTRANDO NO NUTRIPLAN — o que elas DECLARARAM.
    #
    # Duas perguntas, e elas somam de formas diferentes:
    #
    #   interesse ...... uma pessoa marca quantas quiser. Os baldes SE
    #                    SOBREPÕEM, e a soma passa do total de propósito. O
    #                    painel já teve o defeito de somar um recorte junto com
    #                    baldes exclusivos e chegar a 44 num total de 41; a
    #                    tela separa os dois visualmente por isso.
    #   prioridade ..... uma por pessoa. Esta soma fecha, e é ela que responde
    #                    a pergunta do título.
    #
    # Uma consulta cada, sem join. Foi o que decidiu a modelagem por booleanos:
    # com um `ManyToMany`, contar interesse exigiria join e os baldes deixariam
    # de ser comparáveis com `declararam`.
    #
    # `declararam` é o denominador honesto das duas: quem nunca respondeu não
    # é "zero interesse em tudo", é ausência de resposta. Dividir pelo total de
    # contas afirmaria que o legado declarou desinteresse, e ele não declarou
    # nada.
    interesses = Profile.objects.aggregate(
        declararam=Count("id", filter=~Q(prioridade="")),
        **{
            pilar: Count("id", filter=Q(**{campo: True}))
            for pilar, campo in CAMPO_DO_PILAR.items()
        },
    )

    por_prioridade = dict(
        Profile.objects.exclude(prioridade="")
        .values_list("prioridade")
        .annotate(quantas=Count("id"))
    )

    return {
        "contas": contas,
        "por_classificacao": por_classificacao,
        "onboarding_completo": terminaram,
        "funil": funil,
        "ativas_na_semana": recentes["ativas"],
        "declararam_areas": interesses.pop("declararam"),
        "por_interesse": interesses,
        "por_prioridade": por_prioridade,
        "janela_curta": JANELA_CURTA,
        "janela_longa": JANELA_LONGA,
    }
