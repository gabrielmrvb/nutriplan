"""Os formulários do painel.

Cada campo aqui é uma decisão que o profissional toma sobre a saúde de outra
pessoa, então a validação é dupla: o `Form` recusa o que está fora da faixa
antes de chegar ao banco, e `prescription.py` recusa de novo antes de gravar.
Um formulário é conveniência de tela; a trava é a camada de serviço.
"""
from decimal import Decimal

from django import forms

from accounts.models import ActivityLevel, Goal
from workouts.models import Exercise

from . import prescription
from .models import LinkRole, ProfessionalProfile


class EstiloDeCampo:
    """Aplica `field-input` em todo widget, como os formulários do onboarding.

    A alternativa era escrever a classe à mão em cada `<select>` do template, e
    foi exatamente o que aconteceu: o seletor do convite saiu com 18px de
    altura porque ninguém lembrou. Aqui a regra é do formulário, não da tela.
    """

    css_class = "field-input"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(
                field.widget,
                (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect),
            ):
                continue
            field.widget.attrs.setdefault("class", self.css_class)


class ProfessionalSignupForm(EstiloDeCampo, forms.ModelForm):
    class Meta:
        model = ProfessionalProfile
        fields = ("display_name", "default_role", "council_id")
        labels = {
            "display_name": "Como seus alunos te chamam",
            "default_role": "Você atua como",
            "council_id": "Registro no conselho (opcional)",
        }
        help_texts = {
            "council_id": "CREF para educação física, CRN para nutrição.",
        }


class ConviteForm(EstiloDeCampo, forms.Form):
    """Gera um código de convite com um escopo já decidido.

    O escopo é escolhido na geração, e não no aceite, de propósito: quem sabe
    se vai mexer no treino ou na dieta é o profissional, e pedir isso ao aluno
    seria pedir que ele autorize algo que não sabe descrever.
    """

    role = forms.ChoiceField(
        label="Este convite autoriza",
        choices=LinkRole.choices,
    )


class MetasForm(EstiloDeCampo, forms.Form):
    """A recalibragem que o nutricionista prescreve.

    A taxa metabólica basal não está aqui, e a ausência é a decisão: ela é a
    saída de uma fórmula sobre sexo, altura, idade e peso. Um campo para
    editá-la seria um campo para mentir ao resto do motor — que usa a TMB como
    piso de segurança da meta calórica.
    """

    activity_level = forms.ChoiceField(
        label="Nível de atividade", choices=ActivityLevel.choices
    )
    goal = forms.ChoiceField(label="Objetivo", choices=Goal.choices)
    target_weight_kg = forms.DecimalField(
        label="Peso-alvo (kg)",
        required=False,
        min_value=Decimal("35"),
        max_value=Decimal("300"),
        decimal_places=2,
        help_text="Aparece como linha de meta no gráfico de acompanhamento.",
    )
    kcal_adjustment = forms.IntegerField(
        label="Ajuste calórico (kcal)",
        min_value=prescription.AJUSTE_MIN,
        max_value=prescription.AJUSTE_MAX,
        help_text="Somado à meta depois das travas de segurança. Negativo aperta.",
    )
    protein_g_per_kg = forms.DecimalField(
        label="Proteína (g/kg)",
        required=False,
        min_value=prescription.PROTEINA_MIN,
        max_value=prescription.PROTEINA_MAX,
        decimal_places=1,
        help_text="Em branco usa a regra do app: 1,8 g/kg (2,0 na recomposição).",
    )
    fat_kcal_share = forms.DecimalField(
        label="Gordura (% das calorias)",
        required=False,
        min_value=prescription.GORDURA_MIN * 100,
        max_value=prescription.GORDURA_MAX * 100,
        decimal_places=0,
        help_text="Em branco usa 25%. O piso de 0,7 g/kg do app continua valendo.",
    )

    def clean_fat_kcal_share(self):
        """A tela fala em por cento, o motor pensa em fração."""
        valor = self.cleaned_data.get("fat_kcal_share")
        return None if valor is None else Decimal(valor) / 100


class PrescricaoForm(EstiloDeCampo, forms.Form):
    """Séries, repetições e descanso de um exercício."""

    sets = forms.IntegerField(label="Séries", min_value=1, max_value=10)
    rep_min = forms.IntegerField(label="Rep. mín.", min_value=1, max_value=50)
    rep_max = forms.IntegerField(label="Rep. máx.", min_value=1, max_value=50)
    rest_seconds = forms.IntegerField(label="Descanso (s)", min_value=20, max_value=300)

    def clean(self):
        dados = super().clean()
        minimo, maximo = dados.get("rep_min"), dados.get("rep_max")
        if minimo and maximo and minimo > maximo:
            raise forms.ValidationError(
                "A repetição mínima não pode ser maior que a máxima."
            )
        return dados


class TrocaExercicioForm(EstiloDeCampo, forms.Form):
    exercise = forms.ModelChoiceField(
        label="Trocar por",
        queryset=Exercise.objects.filter(is_active=True).order_by("name"),
        empty_label="Escolha um exercício",
    )
