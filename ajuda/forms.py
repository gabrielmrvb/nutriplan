# -*- coding: utf-8 -*-
from django import forms


class ReportarForm(forms.Form):
    """Rota, versão e aparelho chegam preenchidos; a pessoa escreve o que
    aconteceu. `site` é o pote de mel — não aparece na tela e tem de vir vazio."""

    rota = forms.CharField(label="Onde aconteceu", max_length=200, required=False,
                           widget=forms.TextInput(attrs={"class": "field-input"}))
    versao = forms.CharField(label="Versão do app", max_length=40, required=False,
                             widget=forms.TextInput(attrs={"class": "field-input", "readonly": "readonly"}))
    dispositivo = forms.CharField(label="Aparelho e navegador", max_length=200, required=False,
                                  widget=forms.TextInput(attrs={"class": "field-input"}))
    descricao = forms.CharField(
        label="O que aconteceu", min_length=10, max_length=2000,
        widget=forms.Textarea(attrs={"class": "field-input", "rows": 6,
                                     "placeholder": "O que você fez, o que esperava e o que apareceu."}),
        help_text="Sem senha, sem dado de saúde: só o que precisamos para reproduzir.",
    )
    email = forms.EmailField(label="Seu e-mail (para a resposta)", required=False,
                             widget=forms.EmailInput(attrs={"class": "field-input", "autocomplete": "email"}))
    site = forms.CharField(required=False, widget=forms.HiddenInput(attrs={"autocomplete": "off", "tabindex": "-1"}))
