"""A tela de conquistas e o fechamento do aviso.

A tela mora em `/conquistas/` e a porta dela é o Perfil — não uma aba nova. A
barra de baixo acabou de cair de cinco itens para quatro com a saída de
Suplementos, e cada item ficou mais largo; devolver o quinto para uma tela que
se visita de vez em quando desfaria essa melhora em troca de pouco.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from accounts.views import OnboardingRequiredMixin

from . import services
from .models import UserAchievement
from .regras import CATALOGO, POR_SLUG
from config.acoes import AcaoDeTela


class ConquistasView(OnboardingRequiredMixin, TemplateView):
    """O que já foi conquistado e o que está a caminho.

    Deliberadamente pequena. A tentação num sistema de conquistas é a parede de
    medalhas cinzentas — cem coisas que a pessoa não fez, que é o oposto do que
    o NutriPlan faz com a ofensiva, cujo texto inteiro foi escrito para não
    cobrar. Aqui aparecem as conquistas ganhas e, das que faltam, só as que têm
    progresso REAL para mostrar.
    """

    template_name = "achievements/list.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        user = self.request.user

        # Avaliar AQUI, e a razão é retroatividade.
        #
        # O desbloqueio acontecia num lugar só: o POST que registra carga. Quem
        # já tinha histórico quando as conquistas nasceram nunca era avaliado —
        # e como esta tela calcula o progresso ao vivo, ela mostrava "1/1" em
        # "Próximas": progresso completo e conquista trancada, lado a lado. A
        # pessoa via que cumpriu a condição e que o app não reconheceu.
        #
        # A avaliação continua FORA dos demais requests, que era a decisão
        # original e segue valendo. Aqui ela é proporcional: é a página que
        # trata do assunto, e a pessoa entra nela de vez em quando.
        #
        # `avaliar` é idempotente — `get_or_create` mais a constraint de
        # unicidade —, então abrir a tela dez vezes não cria dez conquistas.
        services.avaliar(user)

        ganhas = list(UserAchievement.objects.filter(user=user))
        por_slug = {}
        for conquista in ganhas:
            por_slug.setdefault(conquista.slug, []).append(conquista)

        dados = services.reunir(user)

        # "A caminho" sai de `services.a_caminho`, e não de um laço aqui: o
        # bloco de Conquistas do Progresso lê a MESMA lista, e a regra do que
        # entra nela ("só o que dá para medir sem inventar") é a decisão que
        # impede a parede de medalhas cinzentas. Duas cópias dela divergiriam.
        conquistadas = []
        for regra in CATALOGO:
            ocorrencias = por_slug.get(regra.slug, [])
            if ocorrencias:
                conquistadas.append(
                    {
                        "regra": regra,
                        "quantas": len(ocorrencias),
                        "ultima": ocorrencias[0],
                        # Repetível mostra a última ocorrência; única mostra a
                        # data em que aconteceu.
                        "contexto": ocorrencias[0].contexto,
                    }
                )
                continue


        proximas = services.a_caminho(dados, set(por_slug))

        contexto.update(
            {
                "nav": "profile",
                "conquistadas": conquistadas,
                "a_caminho": proximas[:4],
                "total": len(ganhas),
                "ofensiva": dados.ofensiva,
                "dias_treinados": dados.dias_treinados,
                "recordes": len(por_slug.get("novo-recorde", [])),
            }
        )
        return contexto


class MarcarVistasView(AcaoDeTela, LoginRequiredMixin, View):
    """Fecha o aviso de conquista. A AÇÃO é só POST — isso muda estado.

    O GET devolve a tela de conquistas, e não um 405 em branco: ver
    `config/acoes.py`.

    Recebe os ids que a página mostrou, e não "todas": entre renderizar o aviso
    e a pessoa tocar em "Continuar" outra conquista pode nascer, e marcá-la como
    vista aqui a faria nunca aparecer.
    """

    tela_da_acao = "achievements:list"

    #: "get" entra porque o GET aqui NAO e acao: ele so devolve a tela.
    #:
    #: Sem ele o `AcaoDeTela` nunca roda, e quem volta de um login com
    #: `next=/conquistas/vistas/` recebe 405 com zero byte.
    http_method_names = ["get", "post"]

    #: Para onde voltar, e é uma LISTA FECHADA — o pedido manda o NOME da
    #: tela, não a URL.
    #:
    #: Aqui ficava `redirect(request.POST.get("proximo"))`, com o valor cru
    #: indo para o `redirect()`, que aceita endereço absoluto. Era o único
    #: destino de retorno do app fora da doutrina que os outros três já
    #: seguem: `LogHydrationView.DESTINOS`, `WeightLogView.DESTINOS` e
    #: `OnboardingStepMixin.ORIGENS`.
    #:
    #: Explorar exigia o token CSRF de quem está logado, então não era
    #: alcançável de fora hoje. Fechar custa uma linha e tira o redirecionamento
    #: aberto do dia em que alguém aceitar GET aqui.
    DESTINOS = {
        "conquistas": "achievements:list",
        "hoje": "plans:today",
        "treino": "workouts:routine",
    }

    def post(self, request, *args, **kwargs):
        try:
            ids = [int(v) for v in request.POST.getlist("id")[:20]]
        except (TypeError, ValueError):
            ids = []
        services.marcar_vistas(request.user, ids)
        services.esquecer(request)

        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse({"ok": True})
        return redirect(self.DESTINOS.get(request.POST.get("proximo"),
                                          "plans:today"))
