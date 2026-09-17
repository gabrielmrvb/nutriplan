"""O formulário da vitrine: um campo de cada tipo que `partials/field.html`
e `partials/choice_cards.html` sabem desenhar. Não grava nada."""
from django import forms

from accounts.models import Goal

DIAS = [("0", "Segunda"), ("1", "Terça"), ("2", "Quarta"), ("3", "Quinta"), ("4", "Sexta")]


class FormularioDaVitrine(forms.Form):
    nome = forms.CharField(label="Nome", help_text="Como aparece no cabeçalho.")
    email = forms.EmailField(label="E-mail")
    peso = forms.DecimalField(label="Peso (kg)", initial="82,4", disabled=True, help_text="Campo desabilitado.")
    objetivo = forms.ChoiceField(label="Objetivo", choices=Goal.choices, widget=forms.RadioSelect)
    dias = forms.MultipleChoiceField(label="Dias de treino", choices=DIAS, widget=forms.CheckboxSelectMultiple, required=False)
    lado = forms.ChoiceField(label="Unidade", choices=[("kg", "kg"), ("lb", "lb")], widget=forms.RadioSelect)


def formulario_limpo():
    return FormularioDaVitrine(initial={"nome": "Joana", "objetivo": Goal.CUT, "lado": "kg"})


def formulario_com_erro():
    return FormularioDaVitrine(data={"nome": "", "email": "sem-arroba", "objetivo": "", "lado": "kg"})
