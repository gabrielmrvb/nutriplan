"""Cadastro, autenticação e o wizard de onboarding em quatro passos."""
from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.auth import login, logout
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from . import limites
from .adapters import MAXIMO_DE_TENTATIVAS, SESSAO_TENTATIVAS, SESSAO_VINCULO
from .forms import (
    BodyDataForm,
    ConectarGoogleForm,
    EmailAuthenticationForm,
    ExclusaoDeContaForm,
    GoalForm,
    PALAVRA_DE_EXCLUSAO,
    PesagemForm,
    RestrictionsForm,
    SignupForm,
    SplitPreferenceForm,
    TrainingForm,
)
from workouts.services import preferencia_muda_a_divisao

from .models import (
    ONBOARDING_DONE,
    ONBOARDING_LAST_STEP,
    Profile,
    User,
    WeightEntry,
)
from config.acoes import AcaoDeTela

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


#: Onde os dias de treino são respondidos — o passo que decide o caminho.
#:
#: É o único passo que precisa de nome próprio: o 4 não é referenciado por
#: número em lugar nenhum, porque quem decide se ele existe é `passos_de`.
PASSO_TREINOS = 3

#: Os dois caminhos possíveis. O 5 é sempre o último, e é isso que mantém
#: `ONBOARDING_DONE` e `onboarding_complete` valendo sem alteração nenhuma.
CAMINHO_COMPLETO = (1, 2, 3, 4, 5)
CAMINHO_CURTO = (1, 2, 3, 5)


def passos_de(user, profile, treinos_respondidos=None) -> tuple:
    """Os passos que ESTA pessoa realmente percorre.

    Quem treina até três dias recebe a mesma divisão pelas três preferências
    — `preferencia_muda_a_divisao` lê isso da tabela de `workouts.services`,
    em vez de repetir aqui um número que envelheceria escondido. Para essa
    pessoa o passo 4 não é uma escolha, é uma tela que não muda nada.

    Antes de o passo 3 ser respondido não dá para saber, e aí o caminho
    completo é a resposta honesta: a barra pode encurtar depois, e encurtar é
    uma boa notícia. O contrário — prometer quatro e cobrar cinco — não é.
    """
    if treinos_respondidos is None:
        treinos_respondidos = (
            profile is not None and profile.onboarding_step > PASSO_TREINOS
        )
    if not treinos_respondidos:
        return CAMINHO_COMPLETO
    dias = user.training_days.count()
    return CAMINHO_COMPLETO if preferencia_muda_a_divisao(dias) else CAMINHO_CURTO


def passo_alvo(profile, passos) -> int:
    """Para onde mandar quem chega fora de hora — ou com progresso obsoleto.

    O caso que exige isto: alguém parou no passo 4 quando treinava cinco dias,
    voltou, reduziu para dois, e agora o 4 sumiu do caminho dela. O progresso
    salvo diz "4", e 4 não existe mais. Sem este mapeamento, a entrada
    redirecionaria para 4, a guarda devolveria para a entrada, e o app entraria
    em laço.
    """
    salvo = profile.onboarding_step if profile else 1
    for passo in passos:
        if passo >= salvo:
            return passo
    return passos[-1]


#: Título e subtítulo de cada passo, usados na barra de progresso e no cabeçalho.
STEP_META = {
    1: ("Seus dados", "Precisamos disso para calcular seu gasto energético."),
    2: ("Seu objetivo", "Define se você come acima ou abaixo do seu gasto."),
    # "Sua rotina" e não "Seus treinos": desde a V2.1 a tela também pergunta a
    # janela de sono, e as três respostas são relógios do mesmo dia.
    3: ("Sua rotina", "Quando você treina e quando o seu dia começa e termina."),
    # A divisão vem DEPOIS dos dias, e não antes: a resposta só faz sentido
    # sabendo a frequência. Perguntar "quantos grupos por dia" para quem ainda
    # não disse quantos dias treina é pedir uma escolha que o app vai ter que
    # corrigir por baixo.
    4: (
        "Sua divisão de treino",
        "Escolha quantos músculos você prefere focar em cada sessão.",
    ),
    5: ("Sua comida", "O estilo do cardápio e o que você não pode comer."),
    # A janela de sono saiu daqui na V2.1 — o subtítulo já descrevia só comida,
    # e agora a tela também.
}


class TelaDeEntradaMixin:
    """Marca as telas de entrar e cadastrar.

    A barra de cima usa isto para ficar só com o wordmark: ela oferecia
    "Entrar" e "Criar conta", e a tela de entrar já É entrar — com o link para
    criar conta no rodapé do cartão. Dois caminhos para o mesmo lugar, um a
    três centímetros do outro.
    """

    #: O botão do Google leva o destino de retorno? Cada tela decide.
    #:
    #: A decisão mora AQUI e não no parcial, que é compartilhado por entrar e
    #: cadastrar: uma regra escrita lá dentro faria um template decidir política
    #: de duas telas com contextos diferentes, e a divergência apareceria na
    #: primeira vez que uma delas mudasse.
    leva_destino_no_google = False

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["tela_de_entrada"] = True
        contexto["destino_do_google"] = (
            self.request.GET.get("next", "") if self.leva_destino_no_google else ""
        )
        return contexto


class SignupView(TelaDeEntradaMixin, CreateView):
    """Cria a conta e já autentica — pedir login logo após cadastrar é atrito puro."""

    #: Cadastro NÃO leva o destino para o Google.
    #:
    #: Quem chega em `/conta/cadastro/?next=/admin/` e cria uma conta acabou de
    #: virar usuário comum — e mandá-la direto para uma tela de acesso negado é
    #: um primeiro minuto de uso terrível. Seguro, e péssimo.
    #:
    #: Não é "descartar todo next no cadastro": é não deixar um destino que a
    #: conta recém-criada não pode alcançar atravessar a criação dela. O fluxo
    #: normal — onboarding — continua valendo.
    leva_destino_no_google = False

    form_class = SignupForm
    template_name = "accounts/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("accounts:onboarding_step", step=1)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        # O backend vai explícito desde que o login com Google entrou.
        #
        # Com mais de um backend em `AUTHENTICATION_BACKENDS`, o `login()` do
        # Django não tem como adivinhar qual autenticou — ele levanta
        # `ValueError` em vez de escolher. Quem cria conta aqui foi validado
        # pelo formulário, e é o `ModelBackend` que a atende.
        login(
            self.request,
            self.object,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        return response

    def get_success_url(self):
        return reverse("accounts:onboarding_step", kwargs={"step": 1})


class AppLoginView(TelaDeEntradaMixin, LoginView):
    #: Entrar leva o destino, inclusive para o Google.
    #:
    #: O formulário de senha já levava, de graça: ele não tem `action`, então o
    #: POST vai para a URL atual COM a query string, e `LoginView` lê `next` do
    #: GET. O do Google não levava nada, e `/admin/` terminava em `/hoje/`.
    #:
    #: Quem valida o destino é o allauth — `get_next_redirect_url` descarta o
    #: que não passa em `is_safe_url`. Repetir a validação aqui seria uma
    #: segunda regra para manter alinhada com a primeira.
    leva_destino_no_google = True

    authentication_form = EmailAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        """Entrega, UMA vez, o aviso de que uma conta acabou de ser excluída.

        Esta é a tela para onde a exclusão redireciona, e o `pop` é o que faz
        o aviso valer só naquele render: deixá-lo na sessão faria a fila local
        ser apagada de novo a cada visita ao login, inclusive por outra pessoa
        que fosse entrar no mesmo aparelho.

        O que vai para a tela é a chave primária, e não o e-mail: ela é o
        mesmo identificador que a fila local usa como dono, e identifica uma
        linha que acabou de deixar de existir. E-mail identificaria a pessoa
        fora do app.
        """
        contexto = super().get_context_data(**kwargs)
        contexto["conta_excluida"] = self.request.session.pop(
            ExcluirContaView.CHAVE_DA_EXCLUSAO, ""
        )
        return contexto


class ConectarGoogleView(TelaDeEntradaMixin, FormView):
    """O caso 4: confirmar a senha do NutriPlan para conectar o Google.

    Chega aqui quem autenticou no Google com um e-mail que já tem conta local
    COM senha. O adapter (`accounts/adapters.py`) guardou a tentativa na sessão
    e desviou para cá em vez de entrar — o porquê está lá.

    A tentativa pendente guarda SÓ a identidade — provedor, `uid`, e-mail
    verificado e o `pk` da conta alvo —, em sessão do servidor.

    A primeira versão guardava `sociallogin.serialize()`, que é o mecanismo
    oficial do allauth. Ele carrega o access token e o refresh token junto
    (`if self.token: ret["token"] = ...`), o que viola a regra de não guardar
    credencial em sessão. Trocado por um dicionário mínimo depois de a
    violação ser provada em runtime com marcadores falsos.

    Nada aqui vem do navegador: os quatro campos nascem do callback já validado
    pelo allauth, e o alvo é reconferido a cada requisição.
    """

    template_name = "accounts/conectar_google.html"
    form_class = ConectarGoogleForm

    def dispatch(self, request, *args, **kwargs):
        self.pendencia = self._pendente(request)
        if self.pendencia is None:
            # Sem tentativa pendente não há o que conectar: alguém abriu a URL
            # direto, ou a sessão expirou. Volta para a porta.
            return redirect("accounts:login")

        self.usuario = self._alvo(self.pendencia)
        if self.usuario is None or not self.usuario.is_active:
            return self._desistir(request)
        return super().dispatch(request, *args, **kwargs)

    def _pendente(self, request):
        """A identidade guardada, conferida no formato antes de servir.

        Ela é um dicionário simples escrito pelo adapter a partir do callback
        já validado — não o `SocialLogin` serializado, que carregava o access
        token e o refresh token para dentro da sessão.
        """
        dados = request.session.get(SESSAO_VINCULO)
        if not isinstance(dados, dict):
            request.session.pop(SESSAO_VINCULO, None)
            return None
        if not all(dados.get(campo) for campo in ("provider", "uid", "email", "user_pk")):
            # Sessão de uma versão anterior, ou adulterada. Descarta.
            request.session.pop(SESSAO_VINCULO, None)
            return None
        return dados

    def _alvo(self, pendencia):
        """A conta a conectar, com o e-mail conferido contra o que foi guardado.

        Duas conferências e não uma: o `pk` diz QUAL conta, e o e-mail diz que
        ela continua sendo a mesma que o Google confirmou. Se a conta tiver
        trocado de e-mail entre a ida ao Google e a volta, o vínculo é abortado
        em vez de cair na conta errada.
        """
        usuario = User.objects.filter(pk=pendencia["user_pk"]).first()
        if usuario is None:
            return None
        if usuario.email.lower().strip() != pendencia["email"]:
            return None
        return usuario

    def _desistir(self, request):
        request.session.pop(SESSAO_VINCULO, None)
        request.session.pop(SESSAO_TENTATIVAS, None)
        messages.error(request, "Não foi possível entrar com o Google. Tente novamente.")
        return redirect("accounts:login")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.usuario
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # Só o e-mail, que a pessoa acabou de usar no Google e portanto já
        # conhece. Nada sobre o que a conta tem dentro.
        contexto["email"] = self.usuario.email
        return contexto

    def form_valid(self, form):
        """Senha certa: conecta e entra.

        O vínculo é reconstruído a partir da identidade guardada — provedor e
        `uid` —, e não de um `SocialLogin` ressuscitado da sessão. A conta
        social nasce com `get_or_create` sobre `(provider, uid)`, que é a
        unicidade que o próprio modelo do allauth declara: duas requisições
        simultâneas produzem um vínculo só, e a segunda encontra o da primeira
        em vez de estourar.

        O estado pendente sai da sessão ANTES de gravar, para um duplo envio
        não chegar duas vezes aqui.

        `extra_data` fica vazio de propósito. Ele é informativo — nome, foto —,
        não participa da autenticação, e o próprio allauth o preenche no
        próximo login com os dados frescos do provedor. Guardar menos é o que a
        missão pede.
        """
        self.request.session.pop(SESSAO_VINCULO, None)
        self.request.session.pop(SESSAO_TENTATIVAS, None)

        with transaction.atomic():
            SocialAccount.objects.get_or_create(
                provider=self.pendencia["provider"],
                uid=self.pendencia["uid"],
                defaults={"user": self.usuario},
            )

        login(
            self.request,
            self.usuario,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        return redirect("accounts:onboarding")

    def form_invalid(self, form):
        """Senha errada: não vincula, não troca de usuário, e conta a tentativa.

        A tentativa pendente FICA na sessão nas primeiras vezes — descartá-la
        no primeiro erro obrigaria a refazer o Google inteiro por causa de um
        dedo trocado.

        Mas ela não fica para sempre. Quem chega a esta tela já completou um
        login Google de verdade, o que quer dizer que controla a caixa de
        entrada — e é justamente essa a ameaça que o caso 4 existe para conter.
        Sem limite, a última defesa da conta viraria um formulário de força
        bruta sem atrito nenhum. Esgotadas as tentativas, a pendência é
        descartada e é preciso refazer o Google.
        """
        tentativas = self.request.session.get(SESSAO_TENTATIVAS, 0) + 1
        if tentativas >= MAXIMO_DE_TENTATIVAS:
            self.request.session.pop(SESSAO_TENTATIVAS, None)
            return self._desistir(self.request)

        self.request.session[SESSAO_TENTATIVAS] = tentativas
        return super().form_invalid(form)


class OnboardingStepMixin(LoginRequiredMixin):
    """Regras comuns aos quatro passos: guarda de navegação e contexto do wizard.

    A guarda impede pular passos digitando a URL — o passo N só abre se o
    progresso salvo já chegou nele. Isso não é sobre segurança, é sobre não
    deixar o banco com um perfil pela metade que o cálculo de dieta não sabe ler.
    """

    step: int = 1
    template_name = "accounts/onboarding/step.html"

    #: De onde a pessoa veio, quando entrou aqui para EDITAR um dado.
    #:
    #: Lista fechada, e não a URL que vier no endereço — é a mesma regra de
    #: `LogWeightView`: destino escolhido pelo cliente é redirecionamento
    #: aberto. Aqui a lista tem um item porque só existe uma tela do app, fora
    #: o Perfil, que manda alguém para um passo: `/treino/`, pelo cartão de
    #: dias de treino e pelo convite de quem ainda não cadastrou nenhum.
    ORIGENS = {"treino": "workouts:routine"}

    #: Quem chega sem origem reconhecível volta para o Perfil, que é de onde
    #: vêm todos os outros links de edição.
    ORIGEM_PADRAO = "accounts:profile"

    def get_profile(self):
        return Profile.objects.filter(user=self.request.user).first()

    def origem(self):
        """A rota de volta, já resolvida. Sempre um nome da lista fechada."""
        pedida = self.request.GET.get("origem")
        return self.ORIGENS.get(pedida, self.ORIGEM_PADRAO)

    def voltar_para(self):
        """Para onde "Voltar" aponta, e é o mesmo lugar que "Salvar".

        No wizard, "Voltar" é o passo anterior — quem está cadastrando anda
        para trás dentro do caminho. Na EDIÇÃO não: quem entrou de uma tela do
        app para trocar um dado quer voltar para ela, e o botão apontava para o
        passo 2 do cadastro. Medido no navegador: de `/treino/`, "Dias de
        treino" levava ao passo 3 sem barra de abas, "Voltar" ia para o passo 2
        e "Salvar" ia para o Perfil — nenhum dos dois voltava para o treino, e
        só o botão do NAVEGADOR fazia isso.
        """
        return reverse(self.origem())

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        profile = self.get_profile()
        passos = passos_de(request.user, profile)

        if self.step > 1:
            if profile is None:
                return redirect("accounts:onboarding_step", step=1)
            if profile.onboarding_step < self.step:
                return redirect(
                    "accounts:onboarding_step", step=passo_alvo(profile, passos)
                )

        # O passo existe, mas não para esta pessoa: quem treina até três dias
        # não responde divisão. Vale inclusive para quem já terminou e volta
        # pelo perfil — uma tela que não muda o plano não é edição, é ruído.
        if self.step not in passos:
            return redirect("accounts:onboarding_step", step=passo_alvo(profile, passos))

        self.passos = passos
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        title, subtitle = STEP_META[self.step]
        profile = self.get_profile()
        passos = getattr(self, "passos", None) or passos_de(self.request.user, profile)
        posicao = passos.index(self.step) + 1
        context.update(
            {
                "step": self.step,
                # POSIÇÃO no caminho, não o número do passo. Para quem pula a
                # divisão, o passo 5 é o quarto de quatro — mostrar "Passo 5/4"
                # seria a barra denunciando a própria gambiarra.
                "posicao": posicao,
                "total_steps": len(passos),
                "step_title": title,
                "step_subtitle": subtitle,
                "progress_pct": int(posicao / len(passos) * 100),
                "previous_url": (
                    reverse(
                        "accounts:onboarding_step",
                        kwargs={"step": passos[posicao - 2]},
                    )
                    if posicao > 1
                    else None
                ),
                "is_editing": bool(profile and profile.onboarding_complete),
                # Só na edição: no wizard, "Voltar" continua sendo o passo
                # anterior.
                "voltar_para": (
                    self.voltar_para()
                    if profile and profile.onboarding_complete
                    else None
                ),
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
        """Avança o progresso e decide para onde ir.

        O caminho é recalculado DEPOIS de salvar, não antes: é o passo 3 que
        define se o 4 existe, e ele acabou de ser respondido. Recalcular antes
        leria os dias de treino de ontem.
        """
        was_complete = profile.onboarding_complete
        # `treinos_respondidos` explícito: ao CONCLUIR o passo 3 o progresso
        # salvo ainda diz "3", e a inferência normal leria isso como "ainda não
        # respondeu" — mandando para o passo 4 justamente quem acabou de dizer
        # que treina pouco. Quem está terminando o passo dos treinos sabe que
        # eles foram respondidos; os dias já estão no banco.
        respondeu = self.step >= PASSO_TREINOS or profile.onboarding_step > PASSO_TREINOS
        passos = passos_de(self.request.user, profile, treinos_respondidos=respondeu)
        indice = passos.index(self.step) if self.step in passos else len(passos) - 1
        proximo = passos[indice + 1] if indice + 1 < len(passos) else ONBOARDING_DONE

        profile.advance_onboarding(self.step, proximo=proximo)
        if was_complete:
            # A pergunta de divisão passou a importar agora?
            #
            # Quem treinava três dias nunca viu o passo 4 —
            # `preferencia_muda_a_divisao` devolve False ali — e o perfil ficou
            # com o TRES que o campo traz de fábrica. No dia em que essa pessoa
            # marca um quarto dia a resposta passa a mudar a ficha, e o app
            # estava usando uma escolha que ela nunca fez.
            #
            # `split_preference_confirmada` é o que separa os dois casos, e a
            # edição do passo 3 é o momento exato de perguntar: os dias novos
            # acabaram de ser salvos e a divisão vai ser decidida em seguida.
            if (
                self.step == PASSO_TREINOS
                and 4 in passos
                and not profile.split_preference_confirmada
            ):
                # A origem viaja junto: quem veio do treino responder a
                # divisão continua voltando para o treino no fim, e não cai no
                # Perfil por ter passado por um passo a mais.
                destino = reverse(
                    "accounts:onboarding_step", kwargs={"step": 4}
                )
                pedida = self.request.GET.get("origem")
                if pedida in self.ORIGENS:
                    destino += f"?origem={pedida}"
                return redirect(destino)
            # Só na EDIÇÃO. No onboarding, o feedback de ter salvo é o passo
            # seguinte aparecer — dizer "pronto" cinco vezes seguidas durante
            # o cadastro seria a mensagem virando ruído.
            messages.success(self.request, "Alterações salvas.")
            # De volta para a tela de onde a pessoa veio, e não sempre para o
            # Perfil: ela saiu do treino para trocar os dias de treino, e é a
            # ficha — que acabou de ser remontada com eles — que ela quer ver.
            return redirect(self.voltar_para())
        if proximo >= ONBOARDING_DONE:
            return redirect("plans:today")
        return redirect("accounts:onboarding_step", step=proximo)


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

    def form_valid(self, form):
        """Salvar aqui é o que transforma o padrão do campo numa escolha.

        `split_preference` sozinho não distingue "marquei três grupos por dia"
        de "nunca vi esta tela" — nasce com TRES nos dois casos. Passar por
        aqui é o único fato que o banco tem sobre a intenção da pessoa, e é
        isso que a marca registra.
        """
        resposta = super().form_valid(form)
        Profile.objects.filter(pk=self.object.pk).update(
            split_preference_confirmada=True
        )
        return resposta


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

    #: Onde o peso e coletado. O passo 1 salva `WeightEntry` junto com altura,
    #: sexo e nascimento — ver `DadosBasicosForm.save`.
    PASSO_DO_PESO = 1

    def get(self, request, *args, **kwargs):
        profile = Profile.objects.filter(user=request.user).first()
        if profile is None:
            return redirect("accounts:onboarding_step", step=1)
        if profile.onboarding_complete:
            # "Completo" aqui é CONTADOR DE PASSOS. O motor tem outra régua:
            # `build_inputs` também recusa quando não há peso registrado, e a
            # tela Hoje devolve para cá quando isso acontece.
            #
            # Sem esta checagem as duas réguas discordam e a pessoa fica presa
            # num LOOP: `/` manda para o onboarding porque falta peso, o
            # onboarding manda para `/` porque o contador chegou ao fim, e o
            # navegador vai e volta até desistir. Reproduzido com uma conta
            # real do banco local — passo 6, nenhuma pesagem.
            #
            # A regra: quem decide se dá para entrar no app é o MOTOR. Aqui só
            # se traduz a recusa dele para o passo que resolve.
            if profile.current_weight is None:
                messages.info(
                    request, "Faltou registrar seu peso para calcularmos a dieta."
                )
                return redirect(
                    "accounts:onboarding_step", step=self.PASSO_DO_PESO
                )
            return redirect("plans:today")

        # Quem está no meio do wizard NÃO recebe aviso: esta tela também é o
        # "continuar de onde parei" que a pessoa aciona de propósito, e avisar
        # ali cobraria por algo que ela está justamente fazendo.
        # `passo_alvo` e não `onboarding_step` cru: quem parou no 4 e depois
        # reduziu os dias de treino tem um progresso salvo que aponta para um
        # passo que não existe mais no caminho dela.
        passos = passos_de(request.user, profile)
        return redirect("accounts:onboarding_step", step=passo_alvo(profile, passos))


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
                # Mesma regra do wizard, para o perfil não oferecer um
                # "Editar" que leva a uma tela que a guarda vai recusar.
                "divisao_importa": preferencia_muda_a_divisao(
                    self.request.user.training_days.count()
                ),
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


class WeightLogView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Grava o peso de hoje. A AÇÃO é só POST — isso muda estado.

    O GET devolve a tela do dia, e não um 405 em branco: ver
    `config/acoes.py`.

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
        # A tela não prova sozinha que gravou. O campo volta preenchido com o
        # peso de hoje — que é exatamente o número que a pessoa acabou de
        # digitar —, então antes e depois do envio ela vê a mesma coisa. Nas
        # outras ações do app o próprio elemento muda de estado e a mensagem
        # seria ruído; aqui não há elemento que mude.
        messages.success(request, "Peso registrado.")
        return redirect(destino)





class ExcluirContaView(LoginRequiredMixin, FormView):
    """"Excluir minha conta" — a única ação do app que não tem volta.

    Duas etapas de propósito. `GET` mostra o que será apagado e exige um toque
    para chegar ao formulário; `POST` só apaga depois de a pessoa provar posse
    (senha) ou intenção (a palavra EXCLUIR), conforme o tipo de conta. Ver
    `ExclusaoDeContaForm`.

    A conta apagada é SEMPRE `request.user`. Não existe id no formulário nem na
    URL, então não existe superfície para apagar a conta de outra pessoa — a
    proteção não é uma checagem que alguém pode esquecer de escrever, é a
    ausência do parâmetro.

    O `logout` vem ANTES do `delete`: a sessão guarda o id do usuário e o hash
    da senha, e deixá-la de pé apontando para uma linha que não existe mais é
    como o Django começa a levantar exceção no próximo request.
    """

    template_name = "accounts/excluir_conta.html"
    form_class = ExclusaoDeContaForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                # O que a pessoa perde, contado no banco e não no chute. Uma
                # tela que diz "seus dados" sem número não deixa ninguém medir
                # o que está prestes a fazer.
                "resumo": resumo_do_que_sera_apagado(self.request.user),
                "tem_senha": self.request.user.has_usable_password(),
                "palavra": PALAVRA_DE_EXCLUSAO,
                "sem_tabbar": True,
            }
        )
        return context

    #: Chave que avisa o navegador que a exclusão FOI CONCLUÍDA.
    #:
    #: O aparelho guarda operações feitas sem rede numa fila local, separada
    #: por dono. Sair da conta preserva essa fila — a pessoa volta e ela
    #: sincroniza. Excluir a conta é o oposto: não há volta, e a conta que
    #: receberia aquelas operações deixou de existir.
    #:
    #: O sinal sai daqui e não do clique em "Excluir" porque tentativa não é
    #: conclusão: com o POST recusado por senha errada, apagar a fila teria
    #: perdido o que a pessoa marcou sem rede, com a conta ainda de pé.
    #:
    #: E não sai de "ficou anônimo", porque ficar anônimo também é logout
    #: normal, sessão vencida e cookie perdido — nos três a fila TEM que
    #: sobreviver.
    CHAVE_DA_EXCLUSAO = "conta_excluida"

    def form_valid(self, form):
        """A exclusão do BANCO acontece sozinha; o resto vem depois do commit.

        `form_valid` NÃO é mais atômico inteiro, e a fronteira é o ponto todo.
        `transaction.atomic` protege o banco — sessão não participa dela. Com
        as duas coisas dentro do mesmo bloco e `ATOMIC_REQUESTS` desligado, uma
        falha no `delete()` desfazia o banco e deixava a sessão nova, vazia,
        gravada pelo middleware DEPOIS: conta viva, pessoa deslogada.

        Agora só o `delete()` está dentro do bloco. Tudo o que vem abaixo do
        `with` só executa se o COMMIT tiver passado — se o commit falhar, o
        `__exit__` levanta e nada abaixo acontece. O contrato fica:

        falhou em qualquer ponto → a conta continua, a sessão continua, a fila
        local continua, e nenhum sinal definitivo é emitido;

        commitou → a conta não existe, a sessão encerra, e o sinal sai.

        O `logout` vir DEPOIS do `delete` inverte a ordem antiga. O motivo dela
        — não deixar sessão apontando para uma linha que sumiu — continua
        atendido: as duas linhas são consecutivas e nenhuma resposta sai entre
        elas.
        """
        usuario = self.request.user
        email = usuario.email
        # Capturado ANTES do `delete()`, que zera o `pk` do objeto em memória.
        # Em texto porque é assim que o navegador vai comparar: `dataset` só
        # devolve string, e comparar 43 com "43" com `===` dá falso.
        apagada = str(usuario.pk)

        with transaction.atomic():
            usuario.delete()

        # Daqui para baixo, a exclusão é fato consumado no banco.
        logout(self.request)
        # A sessão aqui já é a NOVA, criada pelo `logout`. É ela que atravessa
        # o redirect e chega na tela de login.
        self.request.session[self.CHAVE_DA_EXCLUSAO] = apagada
        messages.success(
            self.request,
            "Conta de %s apagada. Sentiremos sua falta." % email,
        )
        return redirect("accounts:login")


def resumo_do_que_sera_apagado(user) -> list:
    """Quantos registros de cada tipo somem junto com a conta.

    Lido do banco no momento da pergunta. Todas as relações diretas com
    `User` são `CASCADE` — conferido no `_meta` —, então o `delete()` do
    usuário leva tudo; esta função só EXIBE o que a cascata já garante, e não
    apaga nada por conta própria.

    Se alguém acrescentar um modelo novo apontando para `User`, ele entra na
    cascata sozinho e some daqui — por isso há teste comparando esta lista com
    o que o `_meta` do modelo declara.
    """
    from plans.models import HydrationLog, MealLog, NutritionPlan
    from supplements.models import SupplementLog
    from workouts.models import ExerciseLog, TrainingPlan

    linhas = [
        ("Planos alimentares", NutritionPlan.objects.filter(user=user).count()),
        ("Refeições registradas", MealLog.objects.filter(user=user).count()),
        ("Registros de água", HydrationLog.objects.filter(user=user).count()),
        ("Pesagens", WeightEntry.objects.filter(user=user).count()),
        ("Fichas de treino", TrainingPlan.objects.filter(user=user).count()),
        ("Séries registradas", ExerciseLog.objects.filter(user=user).count()),
        ("Suplementos marcados", SupplementLog.objects.filter(user=user).count()),
    ]
    return [(nome, total) for nome, total in linhas if total]


class PedirSenhaView(auth_views.PasswordResetView):
    """A tela de "esqueci minha senha", com limite de abuso.

    Tudo o que é criptográfico continua sendo do Django: esta subclasse só
    decide se o envio acontece. Ver `accounts/limites.py` para o contrato dos
    três limites e para o que eles NÃO protegem.

    A resposta é a MESMA em todos os caminhos — e-mail existente, inexistente
    ou limitado. É a mesma regra que faz a tela não revelar quem tem conta: se
    o limite devolvesse 429, ou qualquer texto diferente, bastaria observar
    quando a resposta muda para descobrir quantos pedidos aquele endereço já
    recebeu, e portanto que ele existe.
    """

    def form_valid(self, form):
        email = form.cleaned_data.get("email", "")
        ip = limites.ip_do_pedido(self.request)

        if not limites.pode_pedir(email=email, ip=ip):
            # Pula o envio e cai direto na tela de confirmação. Nada distingue
            # este caminho do caminho normal do lado de fora.
            return HttpResponseRedirect(self.get_success_url())

        resposta = super().form_valid(form)
        limites.registrar(email=email, ip=ip)
        limites.limpar_antigos()
        return resposta
