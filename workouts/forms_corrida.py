# -*- coding: utf-8 -*-
"""O registro manual de corrida: distância com vírgula, tempo como no relógio."""
import re
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from .corrida_views import DISTANCIA_MAXIMA_M, DISTANCIA_MINIMA_M, DURACAO_MAXIMA_S, VELOCIDADE_MAXIMA_MS
from .models import Corrida

_TEMPO = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$")


class CorridaManualForm(forms.Form):
    distancia_km = forms.CharField(label="Distância", widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "5,2", "sufixo": "km"}))
    tempo = forms.CharField(label="Tempo", help_text="mm:ss ou h:mm:ss", widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "28:10"}))
    #: `format="%Y-%m-%d"` e não o padrão localizado — o mesmo ajuste de
    #: `accounts/forms.py::BodyDataForm` para `birth_date`. Sem ele o widget
    #: emitia a data em pt-BR (`17/09/2026`), o `<input type="date">` só
    #: entende ISO, o navegador descartava em silêncio e o campo reabria
    #: vazio.
    data = forms.DateField(label="Dia", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    sensacao = forms.ChoiceField(label="Como foi?", choices=[("", "prefiro não dizer")] + list(Corrida.Sensacao.choices), required=False, widget=forms.RadioSelect)

    def clean_distancia_km(self):
        bruto = self.cleaned_data["distancia_km"].strip().replace(".", ",")
        try:
            km = Decimal(bruto.replace(",", "."))
        except InvalidOperation:
            raise forms.ValidationError("Use números, como 5,2.")
        metros = int(km * 1000)
        if metros < DISTANCIA_MINIMA_M:
            raise forms.ValidationError("Corrida de menos de %d m não entra." % DISTANCIA_MINIMA_M)
        if metros > DISTANCIA_MAXIMA_M:
            raise forms.ValidationError("Mais de %d km num dia só não." % (DISTANCIA_MAXIMA_M // 1000))
        return metros

    def clean_tempo(self):
        m = _TEMPO.match(self.cleaned_data["tempo"].strip())
        if not m:
            raise forms.ValidationError("Escreva como no relógio: 28:10 ou 1:58:30.")
        h, mi, s = (int(x) if x else 0 for x in m.groups())
        segundos = h * 3600 + mi * 60 + s
        if segundos <= 0:
            raise forms.ValidationError("O tempo precisa ser maior que zero.")
        if segundos > DURACAO_MAXIMA_S:
            raise forms.ValidationError("Mais de 12 horas não é uma corrida.")
        return segundos

    def clean_data(self):
        dia = self.cleaned_data["data"]
        if dia > timezone.localdate():
            raise forms.ValidationError("A corrida ainda não aconteceu.")
        return dia

    def clean(self):
        dados = super().clean()
        metros, segundos = dados.get("distancia_km"), dados.get("tempo")
        if metros and segundos and metros / segundos > VELOCIDADE_MAXIMA_MS:
            self.add_error("tempo", "Mais rápido que o recorde dos 100 m — confira distância e tempo.")
        return dados

    def preencher(self, corrida):
        """Aplica os campos limpos numa `Corrida` (nova ou existente); não salva."""
        inicio = timezone.make_aware(datetime.combine(self.cleaned_data["data"], time(12, 0)))
        corrida.comecou_em = inicio
        corrida.duracao_s = self.cleaned_data["tempo"]
        corrida.terminou_em = inicio + timedelta(seconds=corrida.duracao_s)
        corrida.distancia_m = self.cleaned_data["distancia_km"]
        corrida.sensacao = self.cleaned_data.get("sensacao") or ""
        corrida.origem = Corrida.Origem.MANUAL
        return corrida
