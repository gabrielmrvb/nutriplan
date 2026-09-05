"""As três telas do painel de gestão.

O que ele NÃO é: uma segunda cara para o Django Admin. O Admin responde "o que
tem nesta linha da tabela"; o painel responde "como o produto está indo". Se
uma tela daqui só mostra registros um a um, ela está no lugar errado.

O que ele não tem, e é escolha: sem entrar na conta de ninguém, sem exportar
lista, sem token, sem histórico de peso ou de refeição pessoa por pessoa. Um
painel de negócio precisa de AGREGADO — e cada uma dessas coisas seria uma
janela para a vida de alguém que a pergunta de negócio não pede.
"""
from django.core.paginator import Paginator
from django.db.models import Exists, Max, OuterRef, Q
from django.views.generic import TemplateView

from accounts.models import ClassificacaoDeConta, Pilar, Profile
from plans.models import MealLog, NutritionPlan
from workouts.models import ExerciseLog, TrainingPlan

from .acesso import PainelDeGestaoMixin
from .metricas import JANELA_CURTA, User, numeros_do_painel


class PainelView(PainelDeGestaoMixin, TemplateView):
    template_name = "gestao/painel.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        numeros = numeros_do_painel()
        contexto.update(numeros)
        # A contagem por classificação vai montada, e não como dicionário para
        # o template procurar: o Django não tem filtro de acesso por chave, e
        # inventar um seria escrever lógica de dado dentro do HTML.
        contexto["classificacao"] = [
            (rotulo, numeros["por_classificacao"].get(valor, 0))
            for valor, rotulo in ClassificacaoDeConta.choices
        ]
        # As áreas declaradas, montadas aqui pela mesma razão da classificação
        # acima. Duas listas e não uma: interesse SE SOBREPÕE (a soma passa do
        # denominador de propósito) e prioridade é exclusiva (a soma fecha).
        # Juntá-las numa tabela só convidaria a somar a coluna, que foi o
        # defeito que o painel já teve com "Com acesso administrativo".
        contexto["interesses"] = [
            (rotulo, numeros["por_interesse"].get(valor, 0))
            for valor, rotulo in Pilar.choices
        ]
        contexto["prioridades"] = [
            (rotulo, numeros["por_prioridade"].get(valor, 0))
            for valor, rotulo in Pilar.choices
        ]
        contexto["aba"] = "painel"
        contexto["sem_tabbar"] = True
        return contexto


class PessoasView(PainelDeGestaoMixin, TemplateView):
    """A lista, para responder "quem são" — não para editar ninguém.

    Paginada desde a primeira versão. Uma lista sem paginação funciona com 52
    contas e derruba a tela com 5 mil, e a hora de descobrir isso não é quando
    já houver 5 mil.
    """

    template_name = "gestao/pessoas.html"
    POR_PAGINA = 50

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        classe = self.request.GET.get("classificacao") or ""

        contas = (
            User.objects.select_related("profile")
            .annotate(
                tem_plano=Exists(NutritionPlan.objects.filter(user=OuterRef("pk"))),
                tem_ficha=Exists(TrainingPlan.objects.filter(user=OuterRef("pk"))),
                ultima_refeicao=Max("meal_logs__date"),
                ultima_serie=Max("exercise_logs__date"),
            )
            .order_by("-date_joined")
        )
        if classe:
            contas = contas.filter(classificacao=classe)

        paginas = Paginator(contas, self.POR_PAGINA)
        contexto["pagina"] = paginas.get_page(self.request.GET.get("pagina"))
        contexto["classificacoes"] = ClassificacaoDeConta.choices
        contexto["classificacao_atual"] = classe
        contexto["aba"] = "pessoas"
        contexto["sem_tabbar"] = True
        return contexto


class AtividadeView(PainelDeGestaoMixin, TemplateView):
    """Quantas pessoas gravaram alguma coisa, dia a dia.

    PESSOAS por dia, e não LINHAS por dia. A distinção decide o que o número
    significa: quem marca cinco refeições produz cinco linhas, e contar linhas
    faria um dia de uma pessoa aplicada parecer um dia movimentado. `distinct`
    responde a pergunta que interessa — quantas pessoas apareceram.

    Uma consulta por tipo de ação, e nenhuma por dia: o agrupamento é do banco.

    A tabela tem TODOS os dias da janela, inclusive os zerados. Antes ela só
    tinha os dias que o banco devolveu — um dia em que ninguém abriu o app
    simplesmente não existia na tela, e quem lesse a coluna de datas precisava
    notar sozinho que 11/08 não estava entre 12/08 e 10/08. Num painel de
    operação, dia morto é justamente o que se quer enxergar: é a mesma decisão
    que a tela de Métricas já tinha tomado para as semanas ("buraco na série é
    informação"), e não faz sentido o painel de gestão dizer o contrário.

    Preencher é de graça: o agrupamento continua no banco, o número de
    consultas não muda, e o laço é sobre 30 datas.
    """

    template_name = "gestao/atividade.html"
    DIAS = 30

    def get_context_data(self, **kwargs):
        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        from plans.models import HydrationLog
        from supplements.models import SupplementLog

        contexto = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        # `DIAS - 1` porque hoje conta. Com `- self.DIAS` a janela pegava 31
        # dias e o texto da tela dizia 30: a tabela entregava uma linha a mais
        # do que a frase prometia.
        desde = hoje - timedelta(days=self.DIAS - 1)

        fontes = (
            ("refeições", MealLog.objects.filter(date__gte=desde)),
            ("água", HydrationLog.objects.filter(date__gte=desde, ml__gt=0)),
            ("séries", ExerciseLog.objects.filter(date__gte=desde)),
            ("suplementos", SupplementLog.objects.filter(date__gte=desde)),
        )

        por_dia = {}
        for nome, consulta in fontes:
            linhas = (
                consulta.values("date")
                .annotate(pessoas=Count("user", distinct=True))
                .order_by("date")
            )
            for linha in linhas:
                dia = por_dia.setdefault(linha["date"], {})
                dia[nome] = linha["pessoas"]

        contexto["nomes"] = [nome for nome, _ in fontes]
        # A janela inteira, do mais recente para o mais antigo, e não só os
        # dias que o banco devolveu.
        contexto["dias"] = [
            (
                hoje - timedelta(days=atras),
                [
                    por_dia.get(hoje - timedelta(days=atras), {}).get(nome, 0)
                    for nome, _ in fontes
                ],
            )
            for atras in range(self.DIAS)
        ]
        # A pergunta é "existe algum registro na janela?", e não "a lista tem
        # linhas": desde que a janela passou a vir inteira, ela SEMPRE tem 30
        # linhas, e `{% if dias %}` seria verdadeiro num banco recém-criado.
        # Sem esta distinção, o estado vazio virava código morto e a tela
        # respondia com trinta linhas de zero. É a mesma distinção que a tela
        # de Métricas faz com `tem_agua` e `tem_treino`, pelo mesmo motivo.
        contexto["tem_atividade"] = bool(por_dia)
        contexto["janela"] = self.DIAS
        contexto["aba"] = "atividade"
        contexto["sem_tabbar"] = True
        return contexto
