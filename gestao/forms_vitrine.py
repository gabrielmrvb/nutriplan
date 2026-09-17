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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O `.field-input` que os formulários de verdade aplicam (`accounts.forms`):
        # sem ele a vitrine fotografava o `<input>` nu do navegador — 177 × 22 px,
        # visto na captura de 17/09/2026 — e não o campo do sistema.
        for campo in self.fields.values():
            if not isinstance(campo.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                campo.widget.attrs.setdefault("class", "field-input")


def formulario_limpo():
    return FormularioDaVitrine(initial={"nome": "Joana", "objetivo": Goal.CUT, "lado": "kg"})


def formulario_com_erro():
    return FormularioDaVitrine(data={"nome": "", "email": "sem-arroba", "objetivo": "", "lado": "kg"})
