"""Formulários de cadastro e dos quatro passos do onboarding.

Cada passo é um form independente que persiste direto no banco. Não usamos
SessionWizardView do django-formtools de propósito: num PWA a pessoa fecha o
app no meio do fluxo o tempo todo, e dado que vive só na sessão desaparece.
Gravando passo a passo, ela retoma exatamente de onde parou.
"""
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
    MINUTOS_POR_DURACAO,
    ActivityLevel,
    DuracaoTreino,
    Equipamento,
    Experiencia,
    Musculacao,
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
    #: O ACEITE dos Termos e da Política, no cadastro (decisão do dono,
    #: 21/09/2026). É uma caixa própria, desmarcada — "cláusula destacada das
    #: demais" (LGPD art. 8º, § 1º) —, e não substitui as duas caixas de
    #: consentimento (dados de saúde, transferência internacional), que
    #: moram na etapa 1, onde o dado de saúde é pedido. Quem entra pelo
    #: Google não passa por aqui e aceita os Termos na etapa 1.
    termos = forms.BooleanField(
        required=True,
        label="Li e aceito os Termos de Uso e a Política de Privacidade.",
        error_messages={"required": "Para criar a conta, aceite os Termos de Uso e a Política de Privacidade."},
    )

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
            attrs={
                "autofocus": True,
                "autocomplete": "email",
                "class": "field-input",
                # O TECLADO DO CELULAR: sem isto o iPhone capitaliza a primeira
                # letra e "corrige" o domínio, e um e-mail com maiúscula
                # inicial falha no login para quem não viu o que digitou.
                "autocapitalize": "none",
                "autocorrect": "off",
                "spellcheck": "false",
                "inputmode": "email",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs.update(
            {
                "class": "field-input",
                "autocomplete": "current-password",
                # O botão do teclado diz o que faz: "ir", e não "retorno".
                "enterkeyhint": "go",
            }
        )


class OnboardingStepForm(forms.ModelForm):
    """Base dos passos: aplica a classe de estilo em todos os widgets.

    E abre a PRIMEIRA passagem sem resposta marcada. O `Profile` nasce com
    `goal`, `activity_level`, `split_preference` e `meal_style` preenchidos
    de fábrica — os padrões existem para a migração não reescrever o plano
    de quem nunca viu a pergunta —, e o `ModelForm` os punha na tela como
    se fossem escolha: o passo 2 abria com "Manter o peso" e "Pouco ativo"
    marcados, o 4 com "3 grupos por dia" ao lado de um "2 grupos" que dizia
    "Mais popular", o 5 com "Variada" ao lado de "Rápida — Recomendado".
    Quem toca "Continuar" sem ler declara o que não escolheu; é a regra que
    `experiencia` e o horário do treino já seguem, dita aqui para o cartão.

    Cada passo diz em `escolhas_abertas` quais campos abrem em branco e em
    `sem_resposta_previa()` quando ainda não há resposta. Quem já respondeu
    volta e encontra a resposta dele — o formulário de EDIÇÃO não muda.
    """

    css_class = "field-input"
    #: Campos de escolha que abrem sem marcação na primeira passagem.
    escolhas_abertas: tuple = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple,
                                         forms.RadioSelect)):
                continue
            field.widget.attrs.setdefault("class", self.css_class)
        if self.escolhas_abertas and self.sem_resposta_previa():
            for campo in self.escolhas_abertas:
                self.initial[campo] = None

    def sem_resposta_previa(self) -> bool:
        """A pessoa ainda não respondeu ESTE passo? Cada passo sabe dizer."""
        return False


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


#: A idade mínima para criar o perfil (decisão do dono, 21/09/2026).
IDADE_MINIMA = 18


class BodyDataForm(OnboardingStepForm):
    """Etapa 1 — sexo, nascimento, altura e peso atual."""

    #: O peso da etapa 1 — e o único campo decimal do onboarding.
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
                # O MESMO exemplo da mensagem de erro deste campo e do outro campo de
                # peso do app ("82,5"): a pessoa via 75,5 na caixa e 82,5 no erro.
                "placeholder": "82,5",
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
        # 18, como os Termos e a Política sempre disseram (o código aceitava
        # 14 até 21/09/2026): as fórmulas são para adultos, o motor não foi
        # calibrado para quem está crescendo, e a prescrição dietética para
        # menor é do nutricionista (Lei 8.234/1991).
        if age < IDADE_MINIMA:
            raise forms.ValidationError(
                "O NutriPlan é para maiores de 18 anos: as fórmulas são para "
                "adultos, e menor de idade precisa de acompanhamento profissional."
            )
        if age > 100:
            raise forms.ValidationError("Confira a data de nascimento.")
        return birth_date

    def save(self, commit=True):
        # ANTES do `super().save()`: o peso atual é a última pesagem gravada, e
        # é com ela que o valor enviado é comparado.
        peso_atual = self.instance.current_weight if self.instance.pk else None
        peso_enviado = self.cleaned_data["weight_kg"]
        profile = super().save(commit=commit)
        # Pesagem só quando o número MUDOU (ou é a primeira). O campo abre
        # pré-preenchido com a última pesagem, de qualquer data; gravar sempre
        # fabricava uma pesagem datada de hoje com o número de dez dias atrás
        # para quem só veio corrigir a altura — e `convidar_a_pesar` parava de
        # convidar, porque "hoje já tem pesagem" (avaliação de 16/09/2026,
        # B4). Um registro por dia continua valendo: mudar o peso duas vezes
        # no mesmo dia atualiza a medição em vez de duplicar.
        if commit and (peso_atual is None or peso_enviado != peso_atual):
            WeightEntry.objects.update_or_create(
                user=profile.user,
                date=timezone.localdate(),
                defaults={"weight_kg": peso_enviado},
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
    """Etapa 2 (o objetivo) — objetivo e nível de atividade fora do treino.

    Era o passo 2 de seis; desde 15/09/2026 abre a etapa 2 com a rotina."""

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

    escolhas_abertas = ("goal", "activity_level")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["goal"].choices = Goal.choices
        self.fields["activity_level"].choices = ActivityLevel.choices

    def sem_resposta_previa(self):
        # `onboarding_step` é o PRÓXIMO passo a fazer: quem ainda está no 2
        # (ou antes) nunca salvou objetivo nenhum — o que há no perfil é o
        # padrão de fábrica que o passo 1 gravou junto.
        return self.instance.pk is None or self.instance.onboarding_step <= 2


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
    """Etapa 2 (a rotina) — dias de treino, horário e janela de sono.

    Era o passo 3 de seis; desde 15/09/2026 compõe a etapa 2 com o objetivo
    e a divisão (`accounts.views.ObjetivoERotinaView`).

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

    musculacao = forms.ChoiceField(
        # A PERGUNTA-PORTA (22/09/2026): com "não", experiência, equipamento,
        # dias e divisão não são pedidos nem gravados. Obrigatória: é ela que
        # decide o resto da tela, e "não respondeu" aqui deixaria a pessoa
        # que só corre no mesmo lugar de antes — inventando dias de academia.
        label="Você faz musculação?",
        choices=Musculacao.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Diga se você faz musculação — o resto da tela depende disso."},
    )
    weekdays = forms.TypedMultipleChoiceField(
        label="Em quais dias você treina?",
        # Rótulo curto, valor idêntico: continua saindo o inteiro de `Weekday`.
        choices=[(dia.value, DIA_CURTO[dia]) for dia in Weekday],
        coerce=int,
        widget=DiasDaSemanaWidget,
        required=False,
        help_text="Se não treina ainda, pode deixar em branco e ajustar depois.",
    )
    experiencia = forms.ChoiceField(
        # Uma das DUAS dimensões de personalização do treino; a outra é o
        # equipamento, logo abaixo (17/09/2026).
        label="Há quanto tempo você treina?",
        help_text="Ajusta o volume semanal de cada grupo muscular.",
        choices=Experiencia.choices,
        # SEM `initial`, e pelo mesmo motivo do horário logo acima: abrir com
        # "Intermediário" já marcado faz quem passa batido declarar um nível
        # que não escolheu. Sem resposta o motor usa 20, que é o que o app já
        # praticava — a ficha não muda, e a tela não inventa a frase.
        required=False,
        widget=forms.RadioSelect,
    )
    equipamento = forms.ChoiceField(
        # COM `initial` — ao contrário da experiência: "completa" é a verdade
        # de quem já tinha ficha e o padrão de quem nasce agora (ver
        # `Equipamento`), então abrir com ele marcado não declara nada que a
        # pessoa não tenha. O motor filtra o catálogo pelo mapa do TREINO.md.
        label="O que você tem para treinar?",
        help_text="A ficha usa só o que está à mão; mudar aqui remonta a ficha.",
        choices=Equipamento.choices,
        required=False,
        widget=forms.RadioSelect,
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
        # O sono e a experiência vivem no Profile, e não em TrainingDay: o
        # formulário só os empresta. Sem este initial, voltar ao passo
        # mostraria os campos vazios e um "Continuar" apagaria o que já estava
        # salvo.
        #
        # A experiência ficava DENTRO do `if existing` acima, e isso apagava a
        # resposta de quem ainda não tinha dia marcado — "Se não treina ainda,
        # pode deixar em branco" é convite explícito da tela. Reproduzido em
        # produção em 16/09/2026 (avaliação, B2): a etapa 3 mostrava
        # "Experiência: Intermediário", reabrir a 2 mostrava o rádio vazio, e
        # salvar gravava "". Só os DIAS dependem de haver dias.
        perfil = self.perfil()
        if perfil is not None and not self.is_bound:
            self.fields["wake_time"].initial = perfil.wake_time
            self.fields["sleep_time"].initial = perfil.sleep_time
            # A faixa NÃO tem mais campo aqui — ela saiu da tela em
            # 10/09/2026 e continua vindo do perfil dentro de `save`.
            self.fields["experiencia"].initial = perfil.experiencia
            self.fields["equipamento"].initial = perfil.equipamento
            # Conta anterior à pergunta com dias gravados: o "sim" é
            # implícito, e a tela abre com ele — quem veio trocar o
            # equipamento não é obrigado a responder o que já respondeu.
            if perfil.musculacao:
                self.fields["musculacao"].initial = perfil.musculacao
            elif self.user.training_days.exists():
                self.fields["musculacao"].initial = Musculacao.SIM

    def perfil(self):
        return getattr(self.user, "profile", None) if self.user else None

    def clean(self):
        """A janela entre acordar e dormir precisa caber um dia de refeições.

        Veio junto com os campos, do passo 5. Só barramos janelas absurdas:
        dormir depois da meia-noite é normal e faz `sleep < wake` — isso é
        válido, não erro.
        """
        cleaned = super().clean()
        # "Não faço musculação" ZERA o resto do bloco, mesmo que o navegador
        # sem JavaScript tenha mandado os campos: o servidor é quem decide.
        if cleaned.get("musculacao") == Musculacao.NAO:
            cleaned["weekdays"] = []
            cleaned["experiencia"] = ""
            cleaned["equipamento"] = ""
        elif cleaned.get("musculacao") == Musculacao.SIM:
            # OBRIGATÓRIAS PARA QUEM FAZ MUSCULAÇÃO (24/09/2026).
            #
            # Os dois campos nasceram opcionais com a razão escrita acima:
            # "sem resposta o motor usa 20 — a ficha não muda, e a tela não
            # inventa a frase". A régua está certa e continua valendo: o app
            # NÃO declara nível por ninguém. O que a rodada 2 mediu é o outro
            # lado dela — quem passava batido saía do cadastro e o Perfil
            # dizia "não informada", que é o app admitindo que montou a ficha
            # com um palpite.
            #
            # A saída não é inventar a resposta: é PERGUNTAR. E só para quem
            # disse que faz musculação — a pergunta-porta decide se o bloco
            # existe na tela, e cobrar o que não foi perguntado seria um beco
            # sem saída para quem só corre.
            #
            # O erro fica NO CAMPO (`add_error`), e não no topo: é o que faz
            # o `aria-invalid` nascer e o "FOCO NO ERRO" do `pwa.js` rolar
            # até ele.
            for campo, frase in (
                ("experiencia", "Diga há quanto tempo você treina — é o que ajusta o volume da sua ficha."),
                ("equipamento", "Diga o que você tem para treinar — a ficha usa só o que está à mão."),
            ):
                if not cleaned.get(campo):
                    self.add_error(campo, frase)
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
        perfil = self.perfil()

        # A FAIXA VEM DO PERFIL, e não mais do formulário.
        #
        # A pergunta saiu da tela em 10/09/2026; o motor continua precisando do
        # teto. Quem já respondeu mantém a resposta — é `perfil.duracao_treino`
        # —, e quem nunca respondeu passa a valer "Padrão, até 60 minutos" em
        # vez de "sem limite rígido".
        #
        # O padrão MUDOU DE VALOR, e a consequência está dita aqui porque ela é
        # real: quem tinha o campo vazio treinava sem teto, e passa a ter um de
        # 60 minutos. A ficha dessa pessoa é remontada na próxima visita, como
        # acontece com qualquer mudança de entrada. Ninguém com valor explícito
        # é tocado — ver `0026_duracao_padrao_para_quem_nao_respondeu`.
        faixa = getattr(perfil, "duracao_treino", "") or DuracaoTreino.PADRAO

        # O INTEIRO CONTINUA SENDO GRAVADO, e não é resíduo.
        #
        # `plans/meal_planner.py` soma `start_time + duration_min` para não
        # marcar refeição no meio do treino. A pergunta virou faixa; o contrato
        # com o cardápio continua sendo um número, e ele passa a ser derivado.
        duration = MINUTOS_POR_DURACAO[faixa]

        # O HORÁRIO EXISTENTE É PRESERVADO, dia a dia.
        #
        # O campo saiu da tela, e `update_or_create` com `start_time=None` nos
        # defaults apagaria o horário de quem já tinha — mudando o cardápio dessa
        # pessoa em silêncio, que é exatamente o que não pode acontecer. Aqui a
        # chave `start_time` só entra nos defaults de quem ainda não existe.
        horarios = dict(
            self.user.training_days.values_list("weekday", "start_time")
        )
        self.user.training_days.exclude(weekday__in=weekdays).delete()
        for weekday in weekdays:
            TrainingDay.objects.update_or_create(
                user=self.user,
                weekday=weekday,
                defaults={
                    "start_time": horarios.get(weekday),
                    "duration_min": duration,
                },
            )

        # `update_fields` restrito: este passo não é dono do resto do Profile,
        # e salvar o objeto inteiro sobrescreveria o que outra aba tivesse
        # gravado enquanto esta tela estava aberta.
        if perfil is not None:
            perfil.wake_time = self.cleaned_data["wake_time"]
            perfil.sleep_time = self.cleaned_data["sleep_time"]
            perfil.duracao_treino = faixa
            # `or ""` e não `or INTERMEDIARIO`: enviar o passo em branco não
            # pode gravar uma declaração. E quem já respondeu não é apagado —
            # o campo abre com o valor do perfil, então o envio o traz de volta.
            perfil.experiencia = self.cleaned_data.get("experiencia") or ""
            # Em branco NÃO apaga: um envio sem o campo (cliente antigo, tela
            # que não o desenha) mantém o que a pessoa tinha.
            perfil.equipamento = self.cleaned_data.get("equipamento") or perfil.equipamento
            perfil.musculacao = self.cleaned_data.get("musculacao") or perfil.musculacao
            perfil.save(update_fields=[
                "wake_time", "sleep_time", "duracao_treino", "experiencia",
                "equipamento", "musculacao", "updated_at",
            ])

        return self.user.training_days.all()


class SplitPreferenceForm(OnboardingStepForm):
    """Etapa 2 (a divisão) — quantos grupos musculares por sessão.

    Era o passo 4 de seis. Hoje mora na MESMA tela dos dias, revelada quando
    os dias marcados pedem (`preferencia_muda_a_divisao`): a resposta só faz
    sentido sabendo a frequência, e a tela pode dizer o que a escolha vai
    virar. Quem treina duas vezes escolhendo "poucos grupos por
    dia" não recebe uma divisão de três — recebe superior e inferior, porque
    a terceira letra nunca chegaria na semana dele.
    """

    class Meta:
        model = Profile
        fields = ("split_preference",)
        widgets = {"split_preference": forms.RadioSelect}
        labels = {"split_preference": "Como dividir os treinos da semana?"}
        help_texts = {
            "split_preference": (
                "Cada opção diz o que você treina em cada dia. Na dúvida, fique "
                "com a mais popular — dá para trocar depois. Trapézio, "
                "antebraço, panturrilha e abdômen entram junto, sem virar um "
                "dia à parte; se a divisão não couber nos seus dias, o app usa "
                "a mais próxima que fecha na semana."
            ),
        }

    escolhas_abertas = ("split_preference",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["split_preference"].choices = SplitPreference.choices

    def sem_resposta_previa(self):
        # Não é o número da etapa: quem treina até dois dias não vê a pergunta
        # e chega ao fim do cadastro sem nunca ter respondido. `split_preference_confirmada`
        # é o fato que o banco tem sobre a intenção da pessoa — e é o que
        # manda quem marca o terceiro dia de volta a esta pergunta.
        return not self.instance.split_preference_confirmada


class RestrictionsForm(OnboardingStepForm):
    """Etapa 3 (a comida) — estilo de cardápio e restrições.

    Era o passo 5 de seis. A janela de sono saiu daqui na V2.1 e foi para a
    rotina (hoje etapa 2), junto dos outros
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

    escolhas_abertas = ("meal_style",)

    def sem_resposta_previa(self):
        return self.instance.pk is None or self.instance.onboarding_step <= 3

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
    """Etapa 3 (as áreas) — o que a pessoa quer cuidar, e o que ela quer cuidar
    primeiro.

    Era o passo 6 de seis; hoje fecha a etapa 3 junto da comida. Uma pergunta
    só, e não duas: partir isto em duas telas custaria uma etapa a mais para
    responder uma coisa que cabe num cartão e num rádio.

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

    #: O valor que significa "respondi, e não quero priorizar".
    #:
    #: Sem ele, não responder e escolher não priorizar eram o MESMO silêncio —
    #: e a validação cobrava uma principal de quem marcasse várias áreas, sem
    #: oferecer saída. Quem escolhe isto recebe a organização canônica, que é
    #: um resultado legítimo e não uma personalização pela metade.
    #:
    #: Ele não é gravado: `clean` o traduz para string vazia, que é como o
    #: modelo já representa "sem prioridade". Um sentinela em banco seria um
    #: segundo jeito de dizer a mesma coisa.
    SEM_PRIORIDADE = "nenhuma"

    interesses = forms.MultipleChoiceField(
        label="O que você quer acompanhar?",
        help_text="Marque quantas quiser. Dá para mudar depois.",
        choices=Pilar.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    prioridade = forms.ChoiceField(
        label="Qual vem primeiro?",
        # Sem `help_text` aqui de propósito: a consequência já está no
        # subtítulo do passo, e repeti-la em cada campo é o que faz a tela
        # ficar longa. Três explicações da mesma coisa não explicam três vezes
        # melhor.
        choices=list(Pilar.choices) + [(SEM_PRIORIDADE, "Não quero priorizar agora")],
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
            self.fields["prioridade"].initial = self._prioridade_inicial()

    def _prioridade_inicial(self):
        """A resposta gravada, traduzida de volta para o rádio.

        "Não quero priorizar agora" é gravado como `""` (ver `SEM_PRIORIDADE`),
        e `""` também é "ainda não respondeu". Abrir o rádio VAZIO para quem já
        respondeu era o defeito: salvar de novo com UMA área marcada promovia
        a área a principal em silêncio, e com duas recusava com "Escolha qual
        vem primeiro" — cobrando uma resposta já dada (avaliação de
        16/09/2026, B3).

        O que distingue os dois silêncios é a etapa já ter sido respondida:
        interesse marcado (uma área sem principal só existe por esta opção —
        `clean` promove a única marcada) ou onboarding concluído. Quem está
        na primeira passagem continua abrindo sem marcação.
        """
        if self.instance.prioridade:
            return self.instance.prioridade
        if self.instance.interesses or self.instance.onboarding_complete:
            return self.SEM_PRIORIDADE
        return ""

    def clean(self):
        dados = super().clean()
        marcados = set(dados.get("interesses") or ())
        principal = dados.get("prioridade") or ""
        # "Não quero priorizar agora" é uma RESPOSTA, e vira ausência de
        # prioridade — não erro. Sem esta linha, quem marca três áreas e escolhe
        # a opção neutra receberia a cobrança de escolher uma principal.
        escolheu_nenhuma = principal == self.SEM_PRIORIDADE
        if escolheu_nenhuma:
            # RESPOSTA COMPLETA, e ela sai por aqui.
            #
            # As três regras abaixo existem para quem QUER priorizar: marcar a
            # área da principal, promover a única marcada, e cobrar a escolha
            # de quem marcou várias. Nenhuma delas se aplica a quem disse que
            # não quer priorizar agora — e passar por elas transformaria a
            # opção neutra em erro (com várias áreas) ou em prioridade
            # acidental (com uma só).
            #
            # Interesses continuam valendo sem principal: `limiar_de_atraso`
            # lê `interesse_em_agua` por conta própria. E marcar nada também é
            # resposta: quem não quer priorizar nem acompanhar nada específico
            # recebe a organização canônica.
            dados["interesses"] = sorted(marcados)
            dados["prioridade"] = ""
            return dados

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
