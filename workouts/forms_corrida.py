# -*- coding: utf-8 -*-
"""O registro manual de corrida: distância com vírgula, tempo como no relógio."""
import re
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from .corrida_views import DISTANCIA_MAXIMA_M, DISTANCIA_MINIMA_M, DURACAO_MAXIMA_S, VELOCIDADE_MAXIMA_MS
from .models import Corrida

#: Minutos e segundos presos a [0-5]?\d / [0-5]\d — sem isso "5:99" e
#: "1:60:00" casavam (o relógio nunca marca 99 segundos) e só a conta de
#: `clean_tempo` os pegava por acaso, se caísse acima do teto de duração.
_TEMPO = re.compile(r"^(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)$")


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

    def __init__(self, *args, **kwargs):
        """C1 (avaliação de mercado, 17/09/2026): este é um `forms.Form` cru —
        não veio de `CamposDoNutriPlanMixin` (`accounts/forms.py`), que é
        quem normalmente escreve `field-input` nos widgets. `partials/field.html`
        documenta o contrato ("os demais campos usam o widget padrão, que já
        vem com a classe .field-input aplicada PELO FORM"): sem o
        `setdefault`, os três campos de texto nasciam sem a moldura de 52px
        do resto do app — abaixo dos 44px de altura E largura que a régua de
        toque exige nas duas dimensões.

        NÃO reaproveita o mixin direto porque ele veste TODO campo, inclusive
        `sensacao` (`RadioSelect`): `.field-input` carrega `min-height:
        3.25rem`, que clampa por cima do `height: 1.2rem` que `.choice-list
        input` dá ao próprio rádio — o círculo de marcação incharia para o
        tamanho de um campo de texto. Só os três campos de texto/data levam
        a classe.
        """
        super().__init__(*args, **kwargs)
        for nome in ("distancia_km", "tempo", "data"):
            self.fields[nome].widget.attrs.setdefault("class", "field-input")

    def clean_distancia_km(self):
        bruto = self.cleaned_data["distancia_km"].strip().replace(".", ",")
        try:
            km = Decimal(bruto.replace(",", "."))
        except InvalidOperation:
            raise forms.ValidationError("Use números, como 5,2.")
        # I2 (avaliação de mercado, 17/09/2026): `Decimal("nan")` e
        # `Decimal("inf")` são conversões VÁLIDAS — não levantam
        # `InvalidOperation` — e só explodiam na conta seguinte:
        # `int(Decimal("nan") * 1000)` levanta `decimal.InvalidOperation` (nan)
        # ou `OverflowError` (inf/-inf), sem handler por perto. 500 para quem
        # colou "nan" ou usou um teclado numérico de aparelho estranho, em vez
        # do erro de validação comum que os outros campos tortos recebem.
        if not km.is_finite():
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
