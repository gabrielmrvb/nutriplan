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

        ganhas = list(UserAchievement.objects.filter(user=user))
        por_slug = {}
        for conquista in ganhas:
            por_slug.setdefault(conquista.slug, []).append(conquista)

        dados = services.reunir(user)

        conquistadas, a_caminho = [], []
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

            # Só entra na lista de "a caminho" o que dá para medir sem inventar.
            if regra.alvo and regra.progresso:
                atual = regra.progresso(dados)
                a_caminho.append(
                    {
                        "regra": regra,
                        "atual": atual,
                        "alvo": regra.alvo,
                        "pct": min(100, round(atual * 100 / regra.alvo)),
                    }
                )

        # A mais perto primeiro: é a que a pessoa consegue fechar hoje.
        a_caminho.sort(key=lambda item: -item["pct"])

        contexto.update(
            {
                "nav": "profile",
                "conquistadas": conquistadas,
                "a_caminho": a_caminho[:4],
                "total": len(ganhas),
                "ofensiva": dados.ofensiva,
                "dias_treinados": dados.dias_treinados,
                "recordes": len(por_slug.get("novo-recorde", [])),
            }
        )
        return contexto


class MarcarVistasView(LoginRequiredMixin, View):
    """Fecha o aviso de conquista. Só POST — isso muda estado.

    Recebe os ids que a página mostrou, e não "todas": entre renderizar o aviso
    e a pessoa tocar em "Continuar" outra conquista pode nascer, e marcá-la como
    vista aqui a faria nunca aparecer.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            ids = [int(v) for v in request.POST.getlist("id")[:20]]
        except (TypeError, ValueError):
            ids = []
        services.marcar_vistas(request.user, ids)
        services.esquecer(request)

        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse({"ok": True})
        return redirect(request.POST.get("proximo") or "plans:today")
