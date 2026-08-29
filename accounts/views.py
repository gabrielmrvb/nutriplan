"""Cadastro, autenticação e o wizard de onboarding em quatro passos."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from .forms import (
    BodyDataForm,
    EmailAuthenticationForm,
    GoalForm,
    PesagemForm,
    SplitPreferenceForm,
    RestrictionsForm,
    SignupForm,
    TrainingForm,
)
from .models import ONBOARDING_LAST_STEP, Profile, WeightEntry

#: Onde o peso recusado espera até a próxima tela.
#:
#: A pessoa digitou, o servidor recusou, e o redirecionamento leva o corpo do
#: POST junto — sem guardar em algum lugar, ela volta para um campo vazio sem
#: saber o que estava errado. Vai pela sessão e não pela URL porque peso é
#: dado de saúde e não tem por que ficar no histórico do navegador.
#:
#: No módulo e não dentro da view: quem escreve é `accounts`, quem lê são as
#: duas telas de `plans`, e a chave escrita à mão nos três lugares seria uma
#: renomeação silenciosa esperando para acontecer.
#:
#: Guarda `[superfície, valor]` e não só o valor. Sem a superfície, o painel
#: consumia um erro que tinha nascido em Métricas: bastava a pessoa abrir a
#: aba Dieta antes de voltar, e o que ela tinha digitado sumia sem nada na
#: tela explicando. Cada tela leva de volta o próprio erro.
SESSAO_PESO_RECUSADO = "peso_recusado"


def recusa_pendente(request, superficie):
    """O peso recusado que pertence a ESTA tela, ou `None` se não há nenhum.

    Consome quando é desta tela e deixa quieto quando é da outra: abrir a aba
    do meio do caminho não pode gastar o erro que a pessoa ainda vai ver.

    `None` e `""` querem dizer coisas diferentes, e a distinção é o motivo de
    a função devolver `None` em vez de string vazia. `""` é uma tentativa
    recusada cujo valor era vazio — a pessoa tocou Salvar com o campo em
    branco —, e essa tentativa precisa reabrir a sanfona com a mensagem à
    vista. Quem decidisse por conteúdo de texto fecharia a sanfona justamente
    no caso em que ela não digitou nada.
    """
    guardado = request.session.get(SESSAO_PESO_RECUSADO)

    if not isinstance(guardado, list) or len(guardado) != 2:
        # Nada guardado, ou o formato antigo de uma sessão aberta antes desta
        # mudança. Descarta em vez de ignorar: sem superfície para comparar,
        # a chave nunca casaria com ninguém e ficaria presa na sessão.
        request.session.pop(SESSAO_PESO_RECUSADO, None)
        return None

    if guardado[0] != superficie:
        return None

    del request.session[SESSAO_PESO_RECUSADO]
    return guardado[1]


#: Título e subtítulo de cada passo, usados na barra de progresso e no cabeçalho.
STEP_META = {
    1: ("Seus dados", "Precisamos disso para calcular seu gasto energético."),
    2: ("Seu objetivo", "Define se você come acima ou abaixo do seu gasto."),
    3: ("Seus treinos", "Definem os horários das refeições e entram na conta."),
    # A divisão vem DEPOIS dos dias, e não antes: a resposta só faz sentido
    # sabendo a frequência. Perguntar "quantos grupos por dia" para quem ainda
    # não disse quantos dias treina é pedir uma escolha que o app vai ter que
    # corrigir por baixo.
    4: (
        "Sua divisão de treino",
        "Escolha quantos músculos você prefere focar em cada sessão.",
    ),
    5: ("Sua comida", "O estilo do cardápio e o que você não pode comer."),
}


class TelaDeEntradaMixin:
    """Marca as telas de entrar e cadastrar.

    A barra de cima usa isto para ficar só com o wordmark: ela oferecia
    "Entrar" e "Criar conta", e a tela de entrar já É entrar — com o link para
    criar conta no rodapé do cartão. Dois caminhos para o mesmo lugar, um a
    três centímetros do outro.
    """

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["tela_de_entrada"] = True
        return contexto


class SignupView(TelaDeEntradaMixin, CreateView):
    """Cria a conta e já autentica — pedir login logo após cadastrar é atrito puro."""

    form_class = SignupForm
    template_name = "accounts/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("accounts:onboarding_step", step=1)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

    def get_success_url(self):
        return reverse("accounts:onboarding_step", kwargs={"step": 1})


class AppLoginView(TelaDeEntradaMixin, LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class OnboardingStepMixin(LoginRequiredMixin):
    """Regras comuns aos quatro passos: guarda de navegação e contexto do wizard.

    A guarda impede pular passos digitando a URL — o passo N só abre se o
    progresso salvo já chegou nele. Isso não é sobre segurança, é sobre não
    deixar o banco com um perfil pela metade que o cálculo de dieta não sabe ler.
    """

    step: int = 1
    template_name = "accounts/onboarding/step.html"

    def get_profile(self):
        return Profile.objects.filter(user=self.request.user).first()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        profile = self.get_profile()
        if self.step > 1:
            if profile is None:
                return redirect("accounts:onboarding_step", step=1)
            if profile.onboarding_step < self.step:
                return redirect("accounts:onboarding_step", step=profile.onboarding_step)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        title, subtitle = STEP_META[self.step]
        profile = self.get_profile()
        context.update(
            {
                "step": self.step,
                "total_steps": ONBOARDING_LAST_STEP,
                "step_range": range(1, ONBOARDING_LAST_STEP + 1),
                "step_title": title,
                "step_subtitle": subtitle,
                "progress_pct": int(self.step / ONBOARDING_LAST_STEP * 100),
                "previous_url": (
                    reverse("accounts:onboarding_step", kwargs={"step": self.step - 1})
                    if self.step > 1
                    else None
                ),
                "is_editing": bool(profile and profile.onboarding_complete),
                "is_last_step": self.step == ONBOARDING_LAST_STEP,
                # A navegação inferior some no wizard. Os cinco destinos dela
                # passam por `OnboardingRequiredMixin` e devolvem quem ainda
                # não terminou — e quem já terminou e voltou para editar está
                # num fluxo com "Voltar" e "Salvar", que são as saídas certas.
                "sem_tabbar": True,
            }
        )
        return context

    def finish_step(self, profile):
        """Avança o progresso e decide para onde ir."""
        was_complete = profile.onboarding_complete
        profile.advance_onboarding(self.step)
        if was_complete:
            return redirect("accounts:profile")
        if self.step == ONBOARDING_LAST_STEP:
            return redirect("plans:today")
        return redirect("accounts:onboarding_step", step=self.step + 1)


class ProfileStepView(OnboardingStepMixin, UpdateView):
    """Passos que editam o Profile diretamente (1, 2 e 4)."""

    def get_object(self, queryset=None):
        profile = self.get_profile()
        if profile is None:
            # Passo 1 é o único que pode criar: os campos obrigatórios do
            # Profile são justamente os dele.
            profile = Profile(user=self.request.user)
        return profile

    def form_valid(self, form):
        self.object = form.save()
        return self.finish_step(self.object)


class BodyDataStepView(ProfileStepView):
    step = 1
    form_class = BodyDataForm


class GoalStepView(ProfileStepView):
    step = 2
    form_class = GoalForm


class TrainingStepView(OnboardingStepMixin, FormView):
    step = 3
    form_class = TrainingForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        return self.finish_step(self.get_profile())


class SplitPreferenceStepView(ProfileStepView):
    step = 4
    form_class = SplitPreferenceForm


class RestrictionsStepView(ProfileStepView):
    step = 5
    form_class = RestrictionsForm


STEP_VIEWS = {
    1: BodyDataStepView,
    2: GoalStepView,
    3: TrainingStepView,
    4: SplitPreferenceStepView,
    5: RestrictionsStepView,
}


def onboarding_step(request, step):
    """Despacha /onboarding/<n>/ para a view do passo.

    Uma rota só em vez de quatro mantém a navegação (voltar, avançar, retomar)
    resolvida por um reverse() com número, sem espalhar nomes de rota pelo código.
    """
    view = STEP_VIEWS.get(step)
    if view is None:
        return redirect("accounts:onboarding_step", step=1)
    return view.as_view()(request)


class OnboardingEntryView(LoginRequiredMixin, TemplateView):
    """Redireciona para o passo pendente — o atalho 'continuar de onde parei'."""

    def get(self, request, *args, **kwargs):
        profile = Profile.objects.filter(user=request.user).first()
        if profile is None:
            return redirect("accounts:onboarding_step", step=1)
        if profile.onboarding_complete:
            return redirect("plans:today")
        return redirect("accounts:onboarding_step", step=profile.onboarding_step)


class ProfileSummaryView(LoginRequiredMixin, TemplateView):
    """Resumo do perfil com atalho para reeditar qualquer passo."""

    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = Profile.objects.filter(user=self.request.user).first()
        context.update(
            {
                "profile": profile,
                "training_days": self.request.user.training_days.all(),
                "weight_entries": self.request.user.weight_entries.all()[:10],
                # O plano ATIVO, para o perfil mostrar as metas em vigor ao
                # lado do botao que as recalcula. Sem ele o botao pedia fe: a
                # pessoa recalculava sem saber de que numero estava saindo.
                "plano": self.request.user.plans.filter(is_active=True).first(),
                "step_meta": STEP_META,
                "nav": "profile",
            }
        )
        return context


class OnboardingRequiredMixin(LoginRequiredMixin):
    """Usado pelas telas do app: sem onboarding completo, não há plano possível."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            profile = Profile.objects.filter(user=request.user).first()
            if profile is None or not profile.onboarding_complete:
                return redirect("accounts:onboarding")
        return super().dispatch(request, *args, **kwargs)


class WeightLogView(OnboardingRequiredMixin, View):
    """Grava o peso de hoje. Só POST — isso muda estado.

    Escreve `WeightEntry` e nada mais. Não toca o `Profile`, não gera plano,
    não chama o `meal_planner`. A cadeia que atualiza a meta já existe e é
    preguiçosa: peso novo muda `Profile.current_weight`, que muda
    `build_inputs`, que faz `plan_is_current` falhar, e `sync_active_plan`
    cria o plano novo na próxima entrada de tela. Gerar plano aqui duplicaria
    esse mecanismo e o faria rodar sobre um número que a pessoa pode corrigir
    no minuto seguinte.

    `update_or_create` por (usuário, dia) porque registrar de novo hoje é
    CORRIGIR, não empilhar — a unicidade no banco é quem garante isso.

    A rota fica fora da fila offline de propósito: sem rede, o POST falha e a
    tela não some. A fila reenvia na ordem da chave, que é um identificador
    sorteado, e uma escrita em que vence o último a chegar sairia sorteada
    junto.
    """

    #: Para onde voltar. Uma lista fechada, e não a URL que veio no corpo:
    #: destino escolhido pelo cliente é redirecionamento aberto.
    DESTINOS = {"hoje": "plans:today", "metricas": "plans:history"}

    #: Para onde vai quem chegou sem origem reconhecível.
    ORIGEM_PADRAO = "metricas"

    def post(self, request, *args, **kwargs):
        # A origem é normalizada ANTES de qualquer coisa, e o mesmo valor
        # normalizado decide o destino e carimba o erro. Guardar a origem crua
        # deixaria um erro carimbado com algo que nenhuma tela reconhece, e a
        # chave ficaria presa na sessão para sempre.
        origem = request.POST.get("origem")
        if origem not in self.DESTINOS:
            origem = self.ORIGEM_PADRAO
        destino = self.DESTINOS[origem]

        form = PesagemForm(request.POST)

        if not form.is_valid():
            # Apagar o que a pessoa digitou por causa de uma vírgula é
            # punição: ela volta para um campo vazio sem saber o que errou.
            messages.error(request, form.primeiro_erro)
            request.session[SESSAO_PESO_RECUSADO] = [
                origem,
                (request.POST.get("weight_kg") or "")[:16],
            ]
            return redirect(destino)

        WeightEntry.objects.update_or_create(
            user=request.user,
            date=timezone.localdate(),
            defaults={"weight_kg": form.cleaned_data["weight_kg"]},
        )
        request.session.pop(SESSAO_PESO_RECUSADO, None)
        return redirect(destino)



