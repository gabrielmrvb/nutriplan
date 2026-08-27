"""Formulários de cadastro e dos quatro passos do onboarding.

Cada passo é um form independente que persiste direto no banco. Não usamos
SessionWizardView do django-formtools de propósito: num PWA a pessoa fecha o
app no meio do fluxo o tempo todo, e dado que vive só na sessão desaparece.
Gravando passo a passo, ela retoma exatamente de onde parou.
"""
from datetime import time
from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from catalog.models import DietaryTag, TagKind

from .models import (
    ActivityLevel,
    Goal,
    MealStyle,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    User,
    Weekday,
    WeightEntry,
)


class SignupForm(UserCreationForm):
    """Cadastro mínimo: só o necessário para criar a conta.

    Tudo que é sobre o corpo e a rotina fica para o wizard. Pedir 12 campos na
    tela de cadastro é a forma mais eficiente de perder o usuário na porta.
    """

    first_name = forms.CharField(label="Como podemos te chamar?", max_length=150)
    email = forms.EmailField(label="E-mail")

    class Meta:
        model = User
        fields = ("first_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Senha"
        self.fields["password2"].label = "Confirme a senha"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")
        self.fields["email"].widget.attrs.update(
            {"autocomplete": "email", "inputmode": "email", "placeholder": "voce@email.com"}
        )
        self.fields["first_name"].widget.attrs.update({"autocomplete": "given-name"})

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com esse e-mail.")
        return email


class EmailAuthenticationForm(AuthenticationForm):
    """Login por e-mail — só troca rótulo e widget; a autenticação é a do Django."""

    username = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(
            attrs={"autofocus": True, "autocomplete": "email", "class": "field-input"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "current-password"}
        )


class OnboardingStepForm(forms.ModelForm):
    """Base dos passos: aplica a classe de estilo em todos os widgets."""

    css_class = "field-input"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple,
                                         forms.RadioSelect)):
                continue
            field.widget.attrs.setdefault("class", self.css_class)


class BodyDataForm(OnboardingStepForm):
    """Passo 1 — sexo, nascimento, altura e peso atual."""

    weight_kg = forms.DecimalField(
        label="Peso atual (kg)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("20")), MaxValueValidator(Decimal("400"))],
        widget=forms.NumberInput(
            attrs={"step": "0.1", "inputmode": "decimal", "placeholder": "75,5"}
        ),
    )

    class Meta:
        model = Profile
        fields = ("sex", "birth_date", "height_cm")
        widgets = {
            "sex": forms.RadioSelect,
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "height_cm": forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "178"}),
        }
        labels = {"sex": "Sexo biológico", "birth_date": "Data de nascimento"}
        help_texts = {
            "sex": "Usado só no cálculo da taxa metabólica — as fórmulas diferem.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sex"].choices = Sex.choices  # remove a opção vazia do RadioSelect
        if self.instance.pk:
            current = self.instance.current_weight
            if current is not None:
                self.fields["weight_kg"].initial = current

    def clean_birth_date(self):
        birth_date = self.cleaned_data["birth_date"]
        today = timezone.localdate()
        age = today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
        if birth_date > today:
            raise forms.ValidationError("A data de nascimento não pode estar no futuro.")
        if age < 14:
            raise forms.ValidationError(
                "O app calcula dietas com fórmulas validadas para adultos. "
                "Menores de 14 anos precisam de acompanhamento profissional."
            )
        if age > 100:
            raise forms.ValidationError("Confira a data de nascimento.")
        return birth_date

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            # Um registro de peso por dia: reabrir o passo 1 no mesmo dia
            # atualiza a medição em vez de criar uma duplicada.
            WeightEntry.objects.update_or_create(
                user=profile.user,
                date=timezone.localdate(),
                defaults={"weight_kg": self.cleaned_data["weight_kg"]},
            )
        return profile


class GoalForm(OnboardingStepForm):
    """Passo 2 — objetivo e nível de atividade fora do treino."""

    class Meta:
        model = Profile
        fields = ("goal", "activity_level")
        widgets = {"goal": forms.RadioSelect, "activity_level": forms.RadioSelect}
        labels = {
            "goal": "Qual é o seu objetivo?",
            # Uma linha: a versão anterior ocupava duas a 390px, e a
            # informação entre parênteses cabe em três palavras.
            "activity_level": "Sua rotina fora dos treinos",
        }
        # Sem `help_texts`: o parágrafo que morava aqui explicava a
        # recomposição em quatro linhas, e o cartão dela já diz "Os dois
        # juntos, mais devagar" no lugar onde a pessoa está olhando. Texto de
        # ajuda que repete o cartão custa 77px e empurra o botão para fora da
        # primeira tela.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["goal"].choices = Goal.choices
        self.fields["activity_level"].choices = ActivityLevel.choices


class TrainingForm(forms.Form):
    """Passo 3 — dias de treino.

    Não é ModelForm porque um único envio cria/remove VÁRIOS TrainingDay.
    Pedimos um horário só para todos os dias: cobre a rotina da maioria e
    reduz o passo de 21 campos para 3. Quem treina em horários diferentes
    ajusta depois na tela de perfil.
    """

    weekdays = forms.TypedMultipleChoiceField(
        label="Em quais dias você treina?",
        choices=Weekday.choices,
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Se não treina ainda, pode deixar em branco e ajustar depois.",
    )
    start_time = forms.TimeField(
        label="Horário do treino",
        initial=time(19, 0),
        widget=forms.TimeInput(attrs={"type": "time", "class": "field-input"}),
    )
    duration_min = forms.IntegerField(
        label="Duração média (minutos)",
        initial=60,
        min_value=15,
        max_value=300,
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "class": "field-input"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        existing = list(user.training_days.all()) if user else []
        if existing and not self.is_bound:
            self.fields["weekdays"].initial = [d.weekday for d in existing]
            self.fields["start_time"].initial = existing[0].start_time
            self.fields["duration_min"].initial = existing[0].duration_min

    def save(self):
        weekdays = set(self.cleaned_data["weekdays"])
        start_time = self.cleaned_data["start_time"]
        duration = self.cleaned_data["duration_min"]

        self.user.training_days.exclude(weekday__in=weekdays).delete()
        for weekday in weekdays:
            TrainingDay.objects.update_or_create(
                user=self.user,
                weekday=weekday,
                defaults={"start_time": start_time, "duration_min": duration},
            )
        return self.user.training_days.all()


class SplitPreferenceForm(OnboardingStepForm):
    """Passo 4 — quantos grupos musculares por sessão.

    Vem DEPOIS dos dias de treino de propósito: a resposta só faz sentido
    sabendo a frequência, e a tela do passo seguinte pode dizer o que a
    escolha vai virar. Quem treina duas vezes escolhendo "poucos grupos por
    dia" não recebe uma divisão de três — recebe superior e inferior, porque
    a terceira letra nunca chegaria na semana dele.
    """

    class Meta:
        model = Profile
        fields = ("split_preference",)
        widgets = {"split_preference": forms.RadioSelect}
        labels = {"split_preference": "Quantos grupos musculares por dia?"}
        help_texts = {
            "split_preference": (
                "Contam os grupos principais. Trapézio, antebraço, panturrilha "
                "e abdômen entram junto sem virar um dia à parte. Se a divisão "
                "não couber nos seus dias, o app usa a mais próxima que fecha "
                "na semana."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["split_preference"].choices = SplitPreference.choices


class RestrictionsForm(OnboardingStepForm):
    """Passo 5 — estilo de cardápio, restrições e janela do dia."""

    class Meta:
        model = Profile
        fields = ("meal_style", "dietary_tags", "wake_time", "sleep_time")
        widgets = {
            "meal_style": forms.RadioSelect,
            "dietary_tags": forms.CheckboxSelectMultiple,
            "wake_time": forms.TimeInput(attrs={"type": "time"}),
            "sleep_time": forms.TimeInput(attrs={"type": "time"}),
        }
        labels = {
            "meal_style": "Que tipo de cardápio você quer?",
            "dietary_tags": "Alguma restrição alimentar?",
            "wake_time": "Que horas você costuma acordar?",
            "sleep_time": "Que horas você costuma dormir?",
        }
        help_texts = {
            # A diferença entre este campo e o de baixo é a diferença entre
            # preferência e restrição, e vale escrever na tela: um pesa, o
            # outro elimina.
            "meal_style": (
                "Isto é preferência, não restrição: se um horário só fechar "
                "com uma receita mais cara, ela ainda aparece — melhor uma "
                "opção fora do seu estilo do que horário nenhum."
            ),
            "dietary_tags": "Só serão sugeridas refeições que atendam a tudo que você marcar.",
            "wake_time": "Os horários das refeições são distribuídos dentro dessa janela.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dietary_tags"].queryset = DietaryTag.objects.filter(
            kind=TagKind.RESTRICTION
        )
        self.fields["dietary_tags"].required = False
        self.fields["meal_style"].choices = MealStyle.choices

    def clean(self):
        cleaned = super().clean()
        wake, sleep = cleaned.get("wake_time"), cleaned.get("sleep_time")
        if wake and sleep:
            # Só barramos janelas absurdas. Dormir depois da meia-noite é normal
            # e faz sleep < wake — isso é válido, não erro.
            same_day = wake < sleep
            awake_hours = (
                (sleep.hour * 60 + sleep.minute) - (wake.hour * 60 + wake.minute)
                if same_day
                else 1440 - (wake.hour * 60 + wake.minute) + (sleep.hour * 60 + sleep.minute)
            ) / 60
            if awake_hours < 6:
                raise forms.ValidationError(
                    "A janela entre acordar e dormir ficou muito curta para "
                    "distribuir as refeições. Confira os horários."
                )
        return cleaned
