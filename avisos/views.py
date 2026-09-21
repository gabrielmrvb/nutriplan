# -*- coding: utf-8 -*-
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView

from .forms import PreferenciaForm
from .models import Preferencia

#: O que cada `?tipo=` do link desliga. `tudo` é o padrão — o cabeçalho
#: `List-Unsubscribe` do provedor não escolhe tipo.
TIPOS = {
    "inatividade": ("email_inatividade",),
    "resumo": ("email_resumo_semanal",),
    "tudo": ("email_inatividade", "email_resumo_semanal"),
}
ROTULOS = {
    "email_inatividade": "o aviso de 5 dias sem treino",
    "email_resumo_semanal": "o resumo da semana",
}


class PreferenciasView(LoginRequiredMixin, FormView):
    """`/avisos/` — o que a pessoa recebe, e quando."""

    template_name = "avisos/preferencias.html"
    form_class = PreferenciaForm

    def get_form(self, form_class=None):
        if self.request.method == "POST":
            return PreferenciaForm(self.request.POST)
        return PreferenciaForm.de(Preferencia.de(self.request.user))

    def form_valid(self, form):
        form.aplicar(Preferencia.de(self.request.user))
        messages.success(self.request, "Avisos atualizados.")
        return redirect(reverse("avisos:preferencias"))


@method_decorator(csrf_exempt, name="dispatch")
class DescadastroView(View):
    """`/avisos/sair/<chave>/?tipo=` — o link do rodapé de todo e-mail.

    Sem login (o cliente de e-mail não tem a sessão) e sem CSRF (o POST de um
    clique vem do provedor, RFC 8058). A chave de 128 bits é o que autoriza;
    a ação é idempotente e só DESLIGA — ligar de volta é na tela, logada.
    """

    def get(self, request, chave):
        return self._aplicar(request, chave, request.GET.get("tipo", "tudo"))

    def post(self, request, chave):
        return self._aplicar(request, chave, request.POST.get("tipo") or request.GET.get("tipo", "tudo"))

    def _aplicar(self, request, chave, tipo):
        pref = get_object_or_404(Preferencia, chave=chave)
        campos = TIPOS.get(tipo, TIPOS["tudo"])
        for campo in campos:
            setattr(pref, campo, False)
        pref.save(update_fields=[*campos, "atualizado_em"])
        return render(request, "avisos/descadastro.html", {
            "desligados": [ROTULOS[c] for c in campos],
            "sem_tabbar": True, "sem_convite": True,
        })
