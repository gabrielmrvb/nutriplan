"""A aba de suplementos e a marcação de um toque."""
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import SyncedOperation
from accounts.views import OnboardingRequiredMixin

from .models import Supplement, SupplementLog


def tomados_hoje(user, dia=None) -> set:
    dia = dia or timezone.localdate()
    return set(
        SupplementLog.objects.filter(user=user, date=dia).values_list(
            "supplement_id", flat=True
        )
    )


def checklist(user, dia=None) -> list:
    """Os suplementos do dia com o estado de cada um, para as pílulas rápidas."""
    dia = dia or timezone.localdate()
    marcados = tomados_hoje(user, dia)
    peso = getattr(getattr(user, "profile", None), "current_weight", None)

    return [
        {
            "supplement": item,
            "tomado": item.pk in marcados,
            "dose": item.dose_display(peso),
        }
        for item in Supplement.objects.filter(is_active=True)
    ]


class SupplementListView(OnboardingRequiredMixin, TemplateView):
    template_name = "supplements/list.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        perfil = getattr(self.request.user, "profile", None)
        peso = getattr(perfil, "current_weight", None)

        contexto.update(
            {
                "nav": "supplements",
                "peso": peso,
                "itens": checklist(self.request.user),
            }
        )
        return contexto


class ToggleSupplementView(OnboardingRequiredMixin, View):
    """Um toque marca, outro desmarca.

    Alternar em vez de só marcar porque o erro mais comum do checklist é tocar
    no botão errado — e sem desfazer, o único caminho de volta seria o admin.
    """

    def post(self, request, supplement_id, *args, **kwargs):
        suplemento = get_object_or_404(
            Supplement, pk=supplement_id, is_active=True
        )
        # Marcar ALTERNA, então reenviar desfaz. Sem a trava, a fila offline
        # desmarcaria o que a pessoa marcou — e ela veria o contrário do que fez.
        destino = request.POST.get("next") or reverse("plans:today")
        if SyncedOperation.ja_aplicada(request.user, request.POST.get("op_id")):
            return redirect(destino)

        hoje = timezone.localdate()

        registro = SupplementLog.objects.filter(
            user=request.user, supplement=suplemento, date=hoje
        ).first()
        if registro:
            registro.delete()
        else:
            SupplementLog.objects.create(
                user=request.user, supplement=suplemento, date=hoje
            )

        return redirect(destino)
