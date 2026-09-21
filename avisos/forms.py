# -*- coding: utf-8 -*-
from datetime import time

from django import forms

from .models import Preferencia

EMAILS = [
    ("inatividade", "Quando eu passar 5 dias sem registrar treino"),
    ("resumo", "Resumo da semana, na segunda-feira"),
]
PUSHES = [
    ("refeicoes", "Lembrete de refeição, 20 min antes do horário"),
]


class PreferenciaForm(forms.Form):
    """As três perguntas da tela: quais e-mails, quais pushes, a que horas.

    Caixas de seleção múltipla (o parcial `field.html` as desenha como cartões
    de toque), e o horário como `<input type=time>` — o mesmo widget que o
    onboarding usa para acordar/dormir.
    """

    emails = forms.MultipleChoiceField(
        label="E-mails", choices=EMAILS, required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="O e-mail de boas-vindas sai uma vez, no cadastro; o de senha só quando você pede.",
    )
    pushes = forms.MultipleChoiceField(
        label="Avisos no aparelho", choices=PUSHES, required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Precisa do aparelho inscrito em Perfil › Lembretes.",
    )
    hora_email = forms.TimeField(
        label="Hora dos e-mails", initial=time(8, 0),
        widget=forms.TimeInput(attrs={"type": "time", "class": "field-input"}),
        help_text="Os e-mails do dia saem a partir desta hora (até meia hora depois).",
    )

    @classmethod
    def de(cls, pref: Preferencia):
        return cls(initial={
            "emails": [c for c, ligado in (("inatividade", pref.email_inatividade), ("resumo", pref.email_resumo_semanal)) if ligado],
            "pushes": ["refeicoes"] if pref.push_refeicoes else [],
            "hora_email": pref.hora_email,
        })

    def aplicar(self, pref: Preferencia):
        emails = set(self.cleaned_data["emails"])
        pushes = set(self.cleaned_data["pushes"])
        pref.email_inatividade = "inatividade" in emails
        pref.email_resumo_semanal = "resumo" in emails
        pref.push_refeicoes = "refeicoes" in pushes
        pref.hora_email = self.cleaned_data["hora_email"]
        pref.save()
