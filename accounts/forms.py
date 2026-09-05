"""Formulários de cadastro e dos quatro passos do onboarding.

Cada passo é um form independente que persiste direto no banco. Não usamos
SessionWizardView do django-formtools de propósito: num PWA a pessoa fecha o
app no meio do fluxo o tempo todo, e dado que vive só na sessão desaparece.
Gravando passo a passo, ela retoma exatamente de onde parou.
"""
from datetime import time
from decimal import Decimal

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from django.utils.safestring import mark_safe

from catalog.models import DietaryTag, TagKind

from .models import (
    CAMPO_DO_PILAR,
    ActivityLevel,
    Goal,
    MealStyle,
    Pilar,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    User,
    Weekday,
    WeightEntry,
)


#: Os validadores que `REGRAS_DE_SENHA` descreve, na ordem em que aparecem.
#: O teste compara com `settings.AUTH_PASSWORD_VALIDATORS`.
REGRAS_ESPERADAS = (
    "UserAttributeSimilarityValidator",
    "MinimumLengthValidator",
    "CommonPasswordValidator",
    "NumericPasswordValidator",
)

REGRAS_DE_SENHA = mark_safe(
    "<p class=\"senha__titulo\">Sua senha precisa:</p>"
    "<ul class=\"senha__regras\">"
    "<li>ter pelo menos 8 caracteres</li>"
    "<li>não ser só números</li>"
    "<li>não ser uma senha comum</li>"
    "<li>não parecer com seu nome ou e-mail</li>"
    "</ul>"
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

        # O cursor tem que cair na PRIMEIRA pergunta da tela.
        #
        # `UserCreationForm.__init__` marca `autofocus` no `USERNAME_FIELD`, que
        # aqui é o e-mail — e o e-mail é o SEGUNDO campo. Medido no navegador,
        # em produção: o atributo estava em `email` enquanto a ordem visual e de
        # tabulação começa em "Como podemos te chamar?". Quem chega e começa a
        # digitar o nome escreve dentro do campo de e-mail.
        #
        # Não é o teclado que decide a ordem, é a tela: o foco segue a pergunta
        # que a pessoa acabou de ler.
        self.fields["email"].widget.attrs.pop("autofocus", None)
        self.fields["first_name"].widget.attrs["autofocus"] = True

        self.fields["password1"].label = "Senha"
        self.fields["password2"].label = "Confirme a senha"
        # A ajuda da senha, encurtada. A VALIDAÇÃO não muda: quem recusa senha
        # continua sendo `AUTH_PASSWORD_VALIDATORS`, intacto — isto aqui é
        # texto de tela.
        #
        # O padrão do Django repete "Sua senha" quatro vezes, uma por regra, e
        # o resultado são 272 caracteres de parágrafo onde a pessoa precisa de
        # uma lista para conferir. O sujeito sai para o título e sobram os
        # quatro requisitos, cada um em três a cinco palavras.
        #
        # `REGRAS_ESPERADAS` existe porque este texto é escrito à mão: se
        # alguém acrescentar ou trocar um validador, a lista fica mentindo. Há
        # teste comparando as duas coisas, e ele quebra antes do usuário ver.
        self.fields["password1"].help_text = REGRAS_DE_SENHA
        self.fields["password2"].help_text = ""
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
    """Login por e-mail — só troca rótulo, widget e recado; a autenticação é a do Django."""

    #: A frase padrão do Django dizia uma coisa que NESTE app é falsa.
    #:
    #: "Note que ambos os campos diferenciam maiúsculas e minúsculas" manda a
    #: pessoa procurar um erro de capitalização no e-mail — e medido no
    #: navegador, contra a stack real, o e-mail entra em CAIXA ALTA sem
    #: problema: `AUTHENTICATION_BACKENDS` tem o backend do allauth depois do
    #: `ModelBackend`, e ele acha a conta sem diferenciar caixa. Só a senha
    #: diferencia.
    #:
    #: Mandar alguém conferir a caixa do e-mail quando o defeito está na senha
    #: é pior que não explicar nada: gasta a tentativa seguinte no lugar errado.
    #:
    #: O texto padrão ainda vinha com espaço duplo ("um e-mail  e senha"),
    #: porque o `verbose_name` interpolado já termina em espaço.
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": (
            "E-mail ou senha incorretos. A senha diferencia maiúsculas de "
            "minúsculas; o e-mail, não."
        ),
    }

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


class PesoField(forms.DecimalField):
    """Um peso digitado por gente que escreve "82,5".

    O campo chega como texto porque `type="number"` recusa vírgula, e o app é
    pt-BR. A troca acontece antes da conversão: `Decimal("82,5")` levanta
    `InvalidOperation`, então esperar o `to_python` do Django decidir seria
    recusar exatamente o formato que a tela pede.

    Mesma tradução que a carga da ficha faz em `workouts/views.py`.
    """

    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace(",", ".").strip()
        return super().to_python(value)


class BodyDataForm(OnboardingStepForm):
    """Passo 1 — sexo, nascimento, altura e peso atual."""

    #: O peso do passo 1 — e o único campo decimal do onboarding.
    #:
    #: Era `DecimalField` com `NumberInput`, e isso significa `type="number"`:
    #: o NAVEGADOR descarta "72,4" antes de enviar, o campo chega vazio e o
    #: formulário recusa dizendo que faltou preencher. Quem digita vírgula —
    #: ou seja, o Brasil — não conseguia passar do primeiro passo sem adivinhar
    #: que precisava de ponto.
    #:
    #: A defesa é dupla, e nenhuma metade basta sozinha: `PesoField` troca a
    #: vírgula por ponto no servidor, e `TextInput` deixa a vírgula chegar até
    #: lá. É a mesma dupla que a pesagem e a carga da ficha já usavam.
    weight_kg = PesoField(
        label="Peso atual",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("20")), MaxValueValidator(Decimal("400"))],
        error_messages={
            "invalid": "Peso inválido — use números, como 82,5.",
            "min_value": "Peso fora da faixa que o app calcula — use de 20 a 400 kg.",
            "max_value": "Peso fora da faixa que o app calcula — use de 20 a 400 kg.",
            "required": "Digite o peso, como 82,5.",
        },
        widget=forms.TextInput(
            attrs={
                "inputmode": "decimal",
                "maxlength": "6",
                "placeholder": "75,5",
                "sufixo": "kg",
            }
        ),
    )

    class Meta:
        model = Profile
        fields = ("sex", "birth_date", "height_cm")
        widgets = {
            "sex": forms.RadioSelect,
            # `format="%Y-%m-%d"`, e não o padrão localizado.
            #
            # Sem ele o widget emitia `value="20/05/1990"` — correto para
            # pt-BR e ilegível para `<input type="date">`, que só entende
            # ISO. O navegador descartava em silêncio e o campo aparecia
            # VAZIO ao reabrir o passo 1 pelo perfil: quem só queria corrigir
            # o peso levava "Este campo é obrigatório" até redigitar a data.
            #
            # É a mesma família do peso com vírgula: valor válido no servidor,
            # formato que o input HTML não sabe ler. Só que aqui a tradução é
            # na SAÍDA, e o campo já aceitava ISO na entrada — `input_formats`
            # traz `%Y-%m-%d`, que é o que o navegador envia ao escolher a data.
            #
            # Declarativo no widget, e não JavaScript: quem precisa formatar é
            # quem desenha o campo.
            "birth_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "height_cm": forms.NumberInput(
                attrs={"inputmode": "numeric", "placeholder": "178", "sufixo": "cm"}
            ),
        }
        labels = {
            "sex": "Sexo biológico",
            "birth_date": "Data de nascimento",
            "height_cm": "Altura",
        }
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


class PesagemForm(forms.Form):
    """O peso do dia, sozinho.

    Existe separado do `BodyDataForm` porque aquele grava o perfil inteiro:
    reaproveitá-lo faria toda pesagem escrever sexo, nascimento e altura, e
    faria a validação de data de nascimento decidir se a pessoa pode ou não
    se pesar hoje.

    Os limites não são reescritos aqui. Eles vêm do campo do model, que é onde
    a faixa de 20 a 400 kg já mora — repetir os números criaria dois lugares
    para mudá-los e um deles ficaria para trás. As mensagens, sim, são nossas:
    a do Django explica a regra, não o que fazer.
    """

    weight_kg = PesoField(
        label="Peso",
        max_digits=5,
        decimal_places=2,
        validators=WeightEntry._meta.get_field("weight_kg").validators,
        error_messages={
            "invalid": "Peso inválido — use números, como 82,5.",
            "min_value": "Peso fora da faixa que o app calcula — use de 20 a 400 kg.",
            "max_value": "Peso fora da faixa que o app calcula — use de 20 a 400 kg.",
            "required": "Digite o peso, como 82,5.",
        },
    )

    @property
    def primeiro_erro(self) -> str:
        """A mensagem a mostrar, já que o campo é um só."""
        return self.errors["weight_kg"][0]


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


#: A abreviação de cada dia, para o chip caber.
#:
#: São RÓTULOS, não valores: o que é enviado continua sendo o inteiro de
#: `Weekday`, e o perfil continua exibindo "Segunda-feira" pelo
#: `get_weekday_display()` do model. Encurtar aqui não encurta nada lá.
DIA_CURTO = {
    Weekday.MONDAY: "Seg",
    Weekday.TUESDAY: "Ter",
    Weekday.WEDNESDAY: "Qua",
    Weekday.THURSDAY: "Qui",
    Weekday.FRIDAY: "Sex",
    Weekday.SATURDAY: "Sáb",
    Weekday.SUNDAY: "Dom",
}


class DiasDaSemanaWidget(forms.CheckboxSelectMultiple):
    """Caixas de marcar cujo rótulo VISÍVEL é curto e o falado é inteiro.

    O chip mostra "Qua" porque sete dias precisam caber em duas linhas num
    celular. Mas "Qua" lido em voz alta é um ruído, não um dia — então cada
    caixa leva `aria-label` com o nome completo, que substitui o texto do
    rótulo para quem ouve a tela.

    Quem enxerga lê a abreviação no contexto de uma fila de sete; quem ouve
    recebe "Quarta-feira", sem contexto nenhum para reconstruir.
    """

    def create_option(self, name, value, label, *args, **kwargs):
        option = super().create_option(name, value, label, *args, **kwargs)
        completo = dict(Weekday.choices).get(getattr(value, "value", value))
        if completo:
            option["attrs"]["aria-label"] = completo
        return option


class TrainingForm(forms.Form):
    """Passo 3 — a rotina do dia: dias de treino, horário e janela de sono.

    Não é ModelForm porque um único envio cria/remove VÁRIOS TrainingDay.
    Pedimos um horário só para todos os dias: cobre a rotina da maioria e
    reduz o passo de 21 campos para 3. Quem treina em horários diferentes
    ajusta depois na tela de perfil.

    O sono mora aqui desde a V2.1, e não no passo da comida. Os três campos de
    relógio deste passo respondem à MESMA pergunta — como é o seu dia — e o
    treino precisa caber dentro da janela que o sono define. Perguntar que
    horas a pessoa acorda logo depois de "alguma restrição alimentar?" obrigava
    a trocar de assunto no meio de uma tela; aqui a pergunta continua a
    anterior.
    """

    weekdays = forms.TypedMultipleChoiceField(
        label="Em quais dias você treina?",
        # Rótulo curto, valor idêntico: continua saindo o inteiro de `Weekday`.
        choices=[(dia.value, DIA_CURTO[dia]) for dia in Weekday],
        coerce=int,
        widget=DiasDaSemanaWidget,
        required=False,
        help_text="Se não treina ainda, pode deixar em branco e ajustar depois.",
    )
    start_time = forms.TimeField(
        label="Horário do treino",
        initial=time(19, 0),
        widget=forms.TimeInput(attrs={"type": "time", "class": "field-input"}),
    )
    duration_min = forms.IntegerField(
        # "Tempo disponível", e não mais "Duração média".
        #
        # O rótulo antigo descrevia a rotina da pessoa e o gerador nunca lia o
        # número: quem informava 30 minutos recebia sessão estimada em 47 a 51.
        # A interface fazia acreditar num limite que o motor ignorava — e entre
        # mudar o texto para admitir isso ou fazer o motor respeitar, a segunda
        # é a que deixa o campo valer alguma coisa.
        #
        # A unidade entra no campo, como já acontece com altura e peso no passo
        # 1. "Tempo disponível (minutos)" quebraria em duas linhas a 390px e
        # empurraria o campo para baixo do vizinho, desalinhando a dupla.
        label="Tempo disponível",
        help_text="O treino é montado para caber nesse tempo.",
        initial=60,
        min_value=15,
        max_value=300,
        widget=forms.NumberInput(
            attrs={"inputmode": "numeric", "class": "field-input", "sufixo": "min"}
        ),
    )
    # Rótulos de uma palavra, e a explicação uma vez só acima do par.
    #
    # Eram duas perguntas inteiras lado a lado, e só a da esquerda tinha texto
    # de ajuda — o que empurrava o campo dela 66px abaixo do outro, medidos a
    # 390px. Dois relógios da mesma janela desalinhados por dois parágrafos
    # diferentes é ruído que a tela não precisa.
    wake_time = forms.TimeField(
        label="Acorda",
        widget=forms.TimeInput(attrs={"type": "time", "class": "field-input"}),
    )
    sleep_time = forms.TimeField(
        label="Dorme",
        widget=forms.TimeInput(attrs={"type": "time", "class": "field-input"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        existing = list(user.training_days.all()) if user else []
        if existing and not self.is_bound:
            self.fields["weekdays"].initial = [d.weekday for d in existing]
            self.fields["start_time"].initial = existing[0].start_time
            self.fields["duration_min"].initial = existing[0].duration_min
        # O sono vive no Profile, e não em TrainingDay: o formulário só o
        # empresta. Sem este initial, voltar ao passo 3 mostraria os campos
        # vazios e um "Continuar" apagaria o que já estava salvo.
        perfil = self.perfil()
        if perfil is not None and not self.is_bound:
            self.fields["wake_time"].initial = perfil.wake_time
            self.fields["sleep_time"].initial = perfil.sleep_time

    def perfil(self):
        return getattr(self.user, "profile", None) if self.user else None

    def clean(self):
        """A janela entre acordar e dormir precisa caber um dia de refeições.

        Veio junto com os campos, do passo 5. Só barramos janelas absurdas:
        dormir depois da meia-noite é normal e faz `sleep < wake` — isso é
        válido, não erro.
        """
        cleaned = super().clean()
        wake, sleep = cleaned.get("wake_time"), cleaned.get("sleep_time")
        if wake and sleep:
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

        # `update_fields` restrito: este passo não é dono do resto do Profile,
        # e salvar o objeto inteiro sobrescreveria o que outra aba tivesse
        # gravado enquanto esta tela estava aberta.
        perfil = self.perfil()
        if perfil is not None:
            perfil.wake_time = self.cleaned_data["wake_time"]
            perfil.sleep_time = self.cleaned_data["sleep_time"]
            perfil.save(update_fields=["wake_time", "sleep_time", "updated_at"])

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
    """Passo 5 — estilo de cardápio e restrições.

    A janela de sono saiu daqui na V2.1 e foi para o passo 3, junto dos outros
    horários. Ela nunca foi uma pergunta sobre comida: era uma pergunta sobre o
    dia da pessoa que tinha ido parar na tela de comida porque é a comida que
    consome a resposta. Consumidor não é dono.
    """

    class Meta:
        model = Profile
        fields = ("meal_style", "dietary_tags")
        widgets = {
            "meal_style": forms.RadioSelect,
            "dietary_tags": forms.CheckboxSelectMultiple,
        }
        labels = {
            "meal_style": "Que tipo de cardápio você quer?",
            "dietary_tags": "Alguma restrição alimentar?",
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dietary_tags"].queryset = DietaryTag.objects.filter(
            kind=TagKind.RESTRICTION
        )
        self.fields["dietary_tags"].required = False
        self.fields["meal_style"].choices = MealStyle.choices


class ConectarGoogleForm(forms.Form):
    """A senha do NutriPlan, pedida uma vez, para conectar o Google.

    O caso 4 da política em `accounts/adapters.py`: o Google provou quem a
    pessoa é do lado dele, e falta ela provar que a conta daqui também é dela.

    Só a senha. Não pede o e-mail: ele já veio do fluxo OIDC validado, e um
    campo editável aqui deixaria o cliente escolher a qual conta se conectar —
    que é exatamente o que esta tela existe para impedir.
    """

    password = forms.CharField(
        label="Sua senha do NutriPlan",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autofocus": True,
                "autocomplete": "current-password",
                "class": "field-input",
            }
        ),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean_password(self):
        senha = self.cleaned_data["password"]
        # `check_password` do model, e não comparação de hash à mão: ele
        # conhece o algoritmo gravado, atualiza o hash quando o padrão do
        # Django muda, e tem tempo constante.
        if self.usuario is None or not self.usuario.check_password(senha):
            raise forms.ValidationError("Senha incorreta.")
        return senha


#: O que a pessoa precisa digitar para confirmar a exclusão quando não há senha
#: local para pedir.
#:
#: Maiúscula e sem acento de propósito: é a palavra que o teclado do celular
#: não completa sozinho, e digitar sete letras é a fricção que separa "toquei
#: sem querer" de "eu quis".
PALAVRA_DE_EXCLUSAO = "EXCLUIR"


class ExclusaoDeContaForm(forms.Form):
    """A confirmação final de "excluir minha conta".

    Existe em duas versões porque existem dois tipos de conta, e fingir que são
    uma só produziria um dos dois erros: pedir senha a quem nunca teve uma, ou
    aceitar um clique só de quem tem.

    *   **Conta com senha local** — pede a senha. É a prova de posse que o
        Django já sabe conferir, e é a mesma que o `ConectarGoogleView` usa
        antes de vincular.
    *   **Conta só do Google** — `has_usable_password()` é falso, e não existe
        senha para conferir. Pedir uma seria inventar credencial. O que se pede
        é a palavra `EXCLUIR`, digitada à mão, sobre uma sessão que já está
        autenticada: quem chegou aqui provou identidade no login, e o que falta
        provar é INTENÇÃO.

    Em nenhum dos dois casos a conta é escolhida pelo formulário — ela é sempre
    `request.user`. Não há campo de id, e por isso não há IDOR possível.
    """

    senha = forms.CharField(
        label="Sua senha",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "class": "field-input"}
        ),
        required=False,
    )
    confirmacao = forms.CharField(
        label="Digite %s para confirmar" % PALAVRA_DE_EXCLUSAO,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "class": "field-input",
            }
        ),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.tem_senha = bool(usuario and usuario.has_usable_password())
        # O campo que não se aplica SAI do formulário, em vez de ficar visível e
        # opcional: campo que aceita vazio ensina que dá para pular a etapa.
        if self.tem_senha:
            del self.fields["confirmacao"]
            self.fields["senha"].required = True
        else:
            del self.fields["senha"]
            self.fields["confirmacao"].required = True

    def clean_senha(self):
        senha = self.cleaned_data.get("senha") or ""
        if not self.usuario.check_password(senha):
            raise forms.ValidationError("Senha incorreta.")
        return senha

    def clean_confirmacao(self):
        texto = (self.cleaned_data.get("confirmacao") or "").strip().upper()
        if texto != PALAVRA_DE_EXCLUSAO:
            raise forms.ValidationError(
                "Digite %s exatamente para confirmar." % PALAVRA_DE_EXCLUSAO
            )
        return texto


class CamposDoNutriPlanMixin:
    """Põe `field-input` nos widgets de um formulário que veio do Django.

    `partials/field.html` documenta o contrato: "os demais campos usam o widget
    padrão, que já vem com a classe `.field-input` aplicada PELO FORM". Os
    formulários próprios do projeto aplicam; os de `django.contrib.auth` —
    recuperação, redefinição e troca de senha — não conhecem essa convenção, e
    por isso os campos das telas de senha nasceram com 177x22 em vez dos 44px
    da régua de toque.

    Existe como mixin, e não como três subclasses copiando a mesma linha,
    porque são três formulários com o mesmo problema e a quarta cópia é a que
    alguém esquece de atualizar.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")


class RecuperarSenhaForm(CamposDoNutriPlanMixin, PasswordResetForm):
    """O e-mail do pedido de recuperação.

    Só veste o campo. Quem decide a quem enviar continua sendo o
    `get_users()` do Django, que já filtra por conta ativa e senha utilizável —
    é ele que faz a conta do Google não receber link, sem que este formulário
    precise saber que Google existe.
    """


class DefinirSenhaForm(CamposDoNutriPlanMixin, SetPasswordForm):
    """A senha nova, vinda do link do e-mail."""


class TrocarSenhaForm(CamposDoNutriPlanMixin, PasswordChangeForm):
    """A troca de senha de quem já está dentro."""


class InteressesForm(OnboardingStepForm):
    """Passo 6 — o que a pessoa quer cuidar, e o que ela quer cuidar primeiro.

    Uma tela só, e não duas. O onboarding já tem cinco passos e catorze campos;
    partir esta pergunta em duas telas custaria um sexto passo para responder
    uma coisa que cabe num cartão e num rádio.

    **A prioridade não é o primeiro checkbox tocado.** Ela é uma pergunta
    própria, com controle próprio, e é isso que impede a escolha acidental —
    quem marca quatro áreas de uma vez não vira "prioridade a primeira que o
    dedo pegou".

    E ela não pode ficar inconsistente, mesmo sem JavaScript: marcar a
    prioridade **implica** o interesse. Quem escolhe "Corrida" como principal
    sem ter marcado Corrida acima não recebe erro — recebe Corrida marcada.
    O contrário (recusar com mensagem) seria cobrar do dedo uma coerência que o
    formulário pode garantir sozinho.

    Quem marca UMA área e não escolhe principal também não recebe erro: com uma
    só, não há o que perguntar. A pergunta explícita existe para quem marcou
    várias, e é aí que ela é obrigatória.
    """

    interesses = forms.MultipleChoiceField(
        label="O que você quer cuidar no NutriPlan?",
        help_text="Escolha tudo que fizer sentido. Você pode mudar depois.",
        choices=Pilar.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    prioridade = forms.ChoiceField(
        label="Qual delas vem primeiro?",
        help_text=(
            "A principal organiza o que aparece antes. Nada fica escondido: "
            "todas as áreas continuam abertas no menu."
        ),
        choices=Pilar.choices,
        widget=forms.RadioSelect,
        required=False,
    )

    class Meta:
        model = Profile
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["interesses"].initial = [
                str(pilar) for pilar in self.instance.interesses
            ]
            self.fields["prioridade"].initial = self.instance.prioridade

    def clean(self):
        dados = super().clean()
        marcados = set(dados.get("interesses") or ())
        principal = dados.get("prioridade") or ""

        # Escolher a principal MARCA a área. Ver a docstring: o formulário
        # fecha o buraco em vez de devolvê-lo para a pessoa.
        if principal:
            marcados.add(principal)

        if not marcados:
            raise forms.ValidationError(
                "Escolha pelo menos uma área para o NutriPlan organizar."
            )

        # Uma área só dispensa a pergunta — ela É a principal.
        if not principal and len(marcados) == 1:
            principal = next(iter(marcados))

        if not principal:
            raise forms.ValidationError(
                "Você marcou mais de uma área. Escolha qual vem primeiro."
            )

        dados["interesses"] = sorted(marcados)
        dados["prioridade"] = principal
        return dados

    def save(self, commit=True):
        perfil = super().save(commit=False)
        marcados = set(self.cleaned_data["interesses"])
        for pilar, campo in CAMPO_DO_PILAR.items():
            setattr(perfil, campo, pilar in marcados)
        perfil.prioridade = self.cleaned_data["prioridade"]
        if commit:
            perfil.save(
                update_fields=list(CAMPO_DO_PILAR.values()) + ["prioridade", "updated_at"]
            )
        return perfil
