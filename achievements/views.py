"""A tela de conquistas e o fechamento do aviso.

A tela mora em `/conquistas/` e a porta dela é o Perfil — não uma aba nova. A
barra de baixo acabou de cair de cinco itens para quatro com a saída de
Suplementos, e cada item ficou mais largo; devolver o quinto para uma tela que
se visita de vez em quando desfaria essa melhora em troca de pouco.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from accounts.views import OnboardingRequiredMixin

from . import services
from .models import UserAchievement
from .regras import CATALOGO, Familia
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

        # ESTA TELA NÃO GRAVA MAIS (26/09/2026, item 0 da missão "quem entra
        # não desiste").
        #
        # Ela chamava `avaliar` no GET — o catálogo inteiro, com escrita —
        # e o Progresso chamava `resumo`, que desbloqueava a regra a 100 %.
        # Duas leituras dos mesmos dados podiam devolver números diferentes,
        # e uma requisição que a pessoa não pediu (um prefetch, um "abrir em
        # nova aba") mudava o banco. Nenhum GET CRIA conquista — o que
        # sobra num GET é o `UPDATE seen_at` do anúncio, em
        # `context_processors.conquistas_pendentes` (decisão de 20/09/2026).
        #
        # O que a avaliação daqui resolvia — RETROATIVIDADE, quem já tinha
        # histórico quando as conquistas nasceram — continua resolvido, por
        # outro caminho: toda conquista nasce no POST QUE CRIA O FATO, e são
        # esses POSTs que a missão passou a cobrir (série, carga, refeição,
        # água e corrida). O "1/1 com a conquista trancada" que a avaliação
        # daqui existia para evitar não volta, porque a barra só chega a
        # 100 % depois de um desses POSTs — e ele desbloqueia na hora.
        #
        # `services.anunciar` continua sendo chamado onde a conquista NASCE,
        # e o aviso aparece na primeira tela depois dela.

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
                # As DUAS espécies da família RECORDE contam aqui — não só
                # `novo-recorde`. Filtrar pela família no catálogo (e não por
                # uma lista de slugs escrita à mão) é o que mantém a régua
                # certa sozinha se uma terceira espécie nascer: quem só tinha
                # `melhor-serie` via "0 recordes" com uma conquista de
                # recorde listada logo abaixo dizendo o oposto (achado F5 da
                # revisão final de 16/09/2026).
                "recordes": sum(
                    len(por_slug.get(regra.slug, []))
                    for regra in CATALOGO
                    if regra.familia == Familia.RECORDE
                ),
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
        # As telas em que o aviso passou a NASCER em 16/09/2026 (B5/B35): a
        # primeira série do dia e o Progresso. "Continuar" no meio do treino
        # jogava a pessoa na Home.
        "execucao": "workouts:now",
        "progresso": "plans:history",
    }

    def _destino(self, pedido) -> str:
        """O NOME da lista — ou o CAMINHO exato de um destino da lista.

        O parcial `_conquista.html` escreve `request.path` em `proximo`, e a
        lista só conhecia nomes: todo caminho caía no padrão, a Home. A lista
        continua fechada — um caminho só vale se for o `reverse()` de um
        destino dela; "https://…", "//…" e qualquer outra rota caem na Home.
        """
        if pedido in self.DESTINOS:
            return self.DESTINOS[pedido]
        for nome in self.DESTINOS.values():
            if pedido == reverse(nome):
                return nome
        return "plans:today"

    def post(self, request, *args, **kwargs):
        try:
            ids = [int(v) for v in request.POST.getlist("id")[:20]]
        except (TypeError, ValueError):
            ids = []
        services.marcar_vistas(request.user, ids)
        services.esquecer(request)

        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse({"ok": True})
        return redirect(self._destino(request.POST.get("proximo", "")))
