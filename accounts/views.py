"""Cadastro, autenticação e o wizard de onboarding em três etapas."""
import logging

from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.auth import login, logout
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView, LoginView
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import formats, timezone
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from . import limites
from .adapters import MAXIMO_DE_TENTATIVAS, SESSAO_TENTATIVAS, SESSAO_VINCULO
from . import entrada
from .forms import (
    DIA_CURTO,
    BodyDataForm,
    ConectarGoogleForm,
    EmailAuthenticationForm,
    ExclusaoDeContaForm,
    GoalForm,
    PALAVRA_DE_EXCLUSAO,
    PesagemForm,
    InteressesForm,
    RestrictionsForm,
    SignupForm,
    SplitPreferenceForm,
    TrainingForm,
)
from workouts.services import (
    NoTrainingDays, acertar_rotina, divisao_explicada, preferencia_muda_a_divisao,
)

from .models import (
    ONBOARDING_DONE,
    ONBOARDING_LAST_STEP,
    Profile,
    User,
    Weekday,
    WeightEntry,
)
from .templatetags import navegacao
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


#: Onde os dias de treino são respondidos — a etapa que decide a ficha.
#:
#: É a única etapa com nome próprio: é nela que os dias, a experiência e a
#: divisão nascem, e é ela que remonta a ficha quando é editada.
logger = logging.getLogger(__name__)

PASSO_TREINOS = 2

#: As TRÊS etapas, sempre as três (15/09/2026, decisão C-ONB). O wizard
#: antigo tinha seis passos e um caminho condicional — o passo da divisão só
#: existia quando os dias de treino pediam (quatro; três desde 10/09/2026). A divisão continua condicional,
#: mas DENTRO da etapa 2, por revelação progressiva: o servidor a exige quando
#: os dias postados pedem (`preferencia_muda_a_divisao`), e o JavaScript só a
#: mostra antes. Um caminho fixo é o que faz "Etapa 2 de 3" ser sempre
#: verdade.
ETAPAS = (1, 2, 3)


def passos_de(user, profile, treinos_respondidos=None) -> tuple:
    """As etapas que ESTA pessoa percorre — hoje, sempre as três.

    A assinatura fica (quem chama passa `treinos_respondidos`) porque o
    caminho já foi condicional e pode voltar a ser; o que não volta é o
    número de etapas mudar por pessoa.
    """
    return ETAPAS


def passo_alvo(profile, passos) -> int:
    """Para onde mandar quem chega fora de hora — ou com progresso obsoleto.

    O progresso salvo diz a próxima etapa; se ela não está no caminho (não
    acontece com três etapas fixas, mas a guarda fica por ser barata e por já
    ter evitado um laço de redirecionamento uma vez), vale a primeira etapa
    a partir dela.
    """
    salvo = profile.onboarding_step if profile else 1
    for passo in passos:
        if passo >= salvo:
            return passo
    return passos[-1]


#: Título e subtítulo de cada etapa, usados no cabeçalho.
STEP_META = {
    1: ("Sobre você", "Quatro dados que entram no cálculo do seu gasto energético."),
    2: (
        "Seu objetivo e rotina",
        "O objetivo decide se você come acima ou abaixo do gasto; a rotina "
        "monta a ficha e distribui as refeições no seu dia.",
    ),
    # O SUBTÍTULO NOMEIA A CONSEQUÊNCIA da prioridade (correção de
    # 08/09/2026): ela muda os ramos do cartão AGORA, onde a seção da área
    # entra na Home e o limiar do aviso de hidratação — e nada some.
    3: (
        "Sua personalização",
        "O estilo do cardápio, o que você não come e o que o app organiza "
        "primeiro. Todas as áreas continuam acessíveis.",
    ),
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


class SairView(LogoutView):
    """Sair leva o cache do navegador junto.

    O QUE ESTE CABEÇALHO RESOLVE, e o que ele NÃO resolve.

    Ao sair, `pwa.js` já apaga o cache de PÁGINAS do service worker — é o que
    impede a próxima pessoa de abrir o app e encontrar a dieta da anterior. O
    que ficava de fora era o cache do próprio navegador e a pilha de histórico
    da aba: o botão Voltar não passa pelo service worker.

    MEDIDO no Chromium deste ambiente: depois do logout, Voltar re-requisitou
    `/conta/perfil/`, levou 302 e caiu no login — nenhum dado reapareceu. Ou
    seja, o vazamento NÃO foi reproduzido aqui. Este cabeçalho é defesa em
    profundidade para os navegadores em que a restauração acontece, e o
    `pageshow` de `pwa.js` cobre o Safari, que ignora `Clear-Site-Data`.

    `"cache"` e não `"*"`: `"storage"` apagaria o Cache Storage e o IndexedDB
    — ou seja, o app offline e a fila de operações pendentes. Sair da conta
    não pode destruir água que alguém registrou no metrô e ainda não subiu.
    """

    def dispatch(self, request, *args, **kwargs):
        resposta = super().dispatch(request, *args, **kwargs)
        resposta["Clear-Site-Data"] = '"cache"'
        return resposta


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

    def post(self, request, *args, **kwargs):
        """Origem no teto: nem chega a conferir a senha.

        A checagem vem ANTES de `authenticate` de propósito. Depois seria só
        cosmética — o servidor já teria feito o trabalho que o limite existe
        para não fazer.

        A resposta é a MESMA de senha errada: mesma tela, mesma mensagem. Quem
        está limitado não recebe aviso de que está, porque um aviso diria ao
        atacante que ele achou o teto. Ver `accounts/entrada.py`.
        """
        email = (request.POST.get("username") or "").strip()
        if not entrada.pode_tentar(email=email, ip=entrada.ip_do_pedido(request)):
            formulario = self.get_form()
            formulario.is_valid()
            formulario.add_error(None, formulario.error_messages["invalid_login"] % {
                "username": formulario.username_field.verbose_name
            })
            return self.render_to_response(self.get_context_data(form=formulario))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """Entrou: as falhas deste par (origem, e-mail) somem.

        Quem errou duas vezes, acertou e voltou a errar não começa do
        quase-limite.
        """
        entrada.limpar_apos_sucesso(
            email=(self.request.POST.get("username") or "").strip(),
            ip=entrada.ip_do_pedido(self.request),
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        """Errou: conta a falha, e responde igual a sempre."""
        entrada.registrar_falha(
            email=(self.request.POST.get("username") or "").strip(),
            ip=entrada.ip_do_pedido(self.request),
        )
        return super().form_invalid(form)

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
    """Regras comuns às três etapas: guarda de navegação e contexto do wizard.

    A guarda impede pular etapa digitando a URL — a etapa N só abre se o
    progresso salvo já chegou nela. Isso não é sobre segurança, é sobre não
    deixar o banco com um perfil pela metade que o cálculo de dieta não sabe ler.
    """

    step: int = 1
    template_name = "accounts/onboarding/step.html"

    #: De onde a pessoa veio, quando entrou aqui para EDITAR um dado.
    #:
    #: Lista fechada, e não a URL que vier no endereço — é a mesma regra de
    #: `LogWeightView`: destino escolhido pelo cliente é redirecionamento
    #: aberto. Aqui a lista tem um item porque só existe uma tela do app, fora
    #: o Perfil, que manda alguém para uma etapa: `/treino/`, pelo cartão de
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

        No wizard, "Voltar" é a etapa anterior — quem está cadastrando anda
        para trás dentro do caminho. Na EDIÇÃO não: quem entrou de uma tela do
        app para trocar um dado quer voltar para ela.
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
                "posicao": posicao,
                "total_steps": len(passos),
                "step_title": title,
                "step_subtitle": subtitle,
                # A trilha anda por etapa: 1/3, 2/3, 3/3. Sem porcentagem na
                # tela — "16%" era o número de seis passos vazando.
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
                # Só na edição: no wizard, "Voltar" continua sendo a etapa
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

    def acertar_ficha(self):
        """Monta, remonta ou desliga a ficha depois de salvar os dias.

        O que pode dar errado aqui é o CATÁLOGO (`NoTrainingDays`: divisão
        sem modelo, catálogo não semeado), e isso não é motivo para o cadastro
        de quem veio pela comida terminar em 500. Fica registrado com o
        identificador do pedido; a aba de Treino levanta o mesmo erro ao
        abrir, que é onde ele sempre apareceu.
        """
        # `TrainingForm.__init__` já leu `user.profile` neste pedido, e o
        # Django guarda a reversa do OneToOne no próprio `user`. A divisão e
        # o objetivo foram gravados por OUTRA instância (`self.profile`), e
        # `acertar_rotina(user)` leria a preferência VELHA pelo cache — "só a
        # divisão mudou" virava "nada mudou", e a ficha não remontava. O
        # cache sai antes de o motor ler.
        reversa = Profile._meta.get_field("user").remote_field
        if reversa.is_cached(self.request.user):
            reversa.delete_cached_value(self.request.user)
        try:
            acertar_rotina(self.request.user)
        except NoTrainingDays as erro:
            # Sem traceback: a mensagem já diz a causa, e o traceback sujava
            # a saída de todo teste de onboarding que roda sem catálogo.
            logger.warning("ficha não montada ao salvar os dias: %s", erro)

    def montar_cardapio(self):
        """O plano alimentar nasce em "Criar meu plano", e não na primeira Home.

        `sync_active_plan` é idempotente — devolve o plano vigente quando os
        dados não mudaram —, então concluir duas vezes não duplica nada. O
        que pode faltar é peso (`IncompleteProfile`): não acontece por este
        caminho, porque a etapa 1 grava a pesagem, e se acontecer a Home já
        sabe mandar de volta ao onboarding.
        """
        from plans import services as plans_services

        try:
            plans_services.sync_active_plan(self.request.user)
        except plans_services.IncompleteProfile as erro:
            logger.warning("cardápio não montado ao concluir: %s", erro)

    def finish_step(self, profile):
        """Avança o progresso e decide para onde ir."""
        was_complete = profile.onboarding_complete
        passos = passos_de(self.request.user, profile)
        indice = passos.index(self.step) if self.step in passos else len(passos) - 1
        proximo = passos[indice + 1] if indice + 1 < len(passos) else ONBOARDING_DONE

        profile.advance_onboarding(self.step, proximo=proximo)
        if was_complete:
            if self.step == PASSO_TREINOS:
                # Os dias ou a divisão mudaram, e a ficha muda com eles AGORA
                # — não na próxima visita ao Treino. A Home lê o plano ativo
                # sem montar nada, e é para a Home que "Salvar" pode voltar.
                # Zero dias desliga o plano (P1-02): a ofensiva e o resumo do
                # dia param de cobrar um treino que a pessoa tirou da semana.
                self.acertar_ficha()
            # Só na EDIÇÃO. No onboarding, o feedback de ter salvo é a etapa
            # seguinte aparecer — dizer "pronto" três vezes seguidas durante
            # o cadastro seria a mensagem virando ruído.
            messages.success(self.request, "Alterações salvas.")
            # De volta para a tela de onde a pessoa veio, e não sempre para o
            # Perfil: ela saiu do treino para trocar os dias de treino, e é a
            # ficha — que acabou de ser remontada com eles — que ela quer ver.
            return redirect(self.voltar_para())
        if proximo >= ONBOARDING_DONE:
            # "Criar meu plano" cria os dois planos AQUI: a ficha (P1-01) e o
            # cardápio. A tela de montagem diz "calculando… ajustando…
            # estruturando…" enquanto isto roda, e com os dois montados aqui
            # ela deixa de ser promessa. Quem terminou sem dia nenhum não
            # ganha ficha; o cardápio não depende de treino.
            self.acertar_ficha()
            self.montar_cardapio()
            messages.success(
                self.request, "Seu plano está pronto: cardápio e ficha montados."
            )
            destino = reverse("plans:today")
            if self.request.headers.get("X-Requested-With") == "XMLHttpRequest":
                # A tela de montagem envia por `fetch`. Se a resposta fosse o
                # redirect, o `fetch` SEGUIRIA para a Home e consumiria a
                # mensagem acima ali — e a navegação de verdade, logo depois,
                # abriria a Home sem ela. O destino vai no corpo; quem navega
                # é o navegador, e a mensagem chega inteira.
                return JsonResponse({"destino": destino})
            return redirect(destino)
        return redirect("accounts:onboarding_step", step=proximo)


class SobreVoceView(OnboardingStepMixin, UpdateView):
    """Etapa 1 — sexo, nascimento, altura e peso. A única que pode CRIAR o perfil."""

    step = 1
    form_class = BodyDataForm

    def get_object(self, queryset=None):
        profile = self.get_profile()
        if profile is None:
            # Os campos obrigatórios do Profile são justamente os desta etapa.
            profile = Profile(user=self.request.user)
        return profile

    def form_valid(self, form):
        self.object = form.save()
        return self.finish_step(self.object)


class EtapaCompostaView(OnboardingStepMixin, TemplateView):
    """Uma etapa feita de mais de um formulário existente.

    Os formulários dos seis passos antigos continuam sendo a fonte de
    validação, de `save()` e de "escolhas abrem em branco": compor é o que
    permite três etapas sem reescrever regra nenhuma. Cada subclasse diz
    quais formulários entram (`nomes_dos_forms`) e como cada um nasce
    (`instanciar`). Todos validam antes de qualquer um salvar, e a gravação é
    uma transação: ou a etapa inteira entra, ou nada.
    """

    #: Os nomes dos formulários, na ordem em que a tela os desenha.
    nomes_dos_forms: tuple = ()

    def instanciar(self, nome, dados):
        raise NotImplementedError

    def get_forms(self, dados=None):
        # UMA instância do perfil para todos os formulários da etapa. Cada
        # `ModelForm.save()` grava o objeto INTEIRO: com uma instância por
        # formulário, o último a salvar devolvia ao banco os campos velhos
        # dos outros (o objetivo voltava a "cut" depois de a divisão salvar).
        self.profile = self.get_profile()
        return {nome: self.instanciar(nome, dados) for nome in self.nomes_dos_forms}

    def forms_exigidos(self, forms):
        """Quais formulários precisam validar neste envio. Subclasse decide."""
        return list(forms)

    def get_context_data(self, **kwargs):
        forms = kwargs.pop("forms", None) or self.get_forms()
        context = super().get_context_data(**kwargs)
        context["forms"] = forms
        # `form` é o primeiro, para o template e os testes que leem
        # `context["form"]` continuarem valendo.
        context["form"] = forms[self.nomes_dos_forms[0]]
        return context

    def salvar(self, forms):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        forms = self.get_forms(request.POST)
        exigidos = self.forms_exigidos(forms)
        validos = [forms[nome].is_valid() for nome in exigidos]
        if not all(validos):
            return self.render_to_response(self.get_context_data(forms=forms))
        with transaction.atomic():
            self.salvar({nome: forms[nome] for nome in exigidos})
        return self.finish_step(self.get_profile())


class ObjetivoERotinaView(EtapaCompostaView):
    """Etapa 2 — objetivo, atividade, experiência, dias, janela do dia e divisão.

    A DIVISÃO É PROGRESSIVA: só é exigida quando os dias postados pedem
    (`preferencia_muda_a_divisao`, a mesma régua do passo 4 antigo). O
    JavaScript mostra o bloco antes de a pessoa enviar; sem JavaScript o
    servidor recusa o envio com quatro dias e sem divisão, e reabre a tela
    com o bloco visível e o erro no campo. `split_preference_confirmada` só
    vira verdadeiro quando a divisão foi de fato respondida — é o que separa
    "escolheu" de "nunca viu a pergunta".
    """

    step = 2
    nomes_dos_forms = ("objetivo", "rotina", "divisao")

    def instanciar(self, nome, dados):
        if nome == "objetivo":
            return GoalForm(dados, instance=self.profile)
        if nome == "rotina":
            return TrainingForm(dados, user=self.request.user)
        return SplitPreferenceForm(dados, instance=self.profile)

    def dias_pedidos(self, forms):
        """Quantos dias este envio (ou o banco, num GET) declara."""
        rotina = forms["rotina"]
        if rotina.is_bound:
            return len(set(rotina.data.getlist("weekdays")))
        return self.request.user.training_days.count()

    def mostrar_divisao(self, forms):
        return preferencia_muda_a_divisao(self.dias_pedidos(forms))

    def forms_exigidos(self, forms):
        exigidos = ["objetivo", "rotina"]
        if self.mostrar_divisao(forms):
            exigidos.append("divisao")
        return exigidos

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["mostrar_divisao"] = self.mostrar_divisao(context["forms"])
        # `preferencia_muda_a_divisao` lê a tabela do motor: o JavaScript
        # precisa do mesmo número para revelar o bloco na hora certa.
        context["dias_para_divisao"] = MINIMO_DE_DIAS_PARA_DIVISAO
        return context

    def salvar(self, forms):
        # Os `ModelForm` (objetivo, divisão) salvam o perfil inteiro e vêm
        # PRIMEIRO; `TrainingForm.save` vem por último porque grava o perfil
        # com `update_fields` restrito a partir de `user.profile` — uma
        # instância própria — e um save inteiro depois dele devolveria a
        # experiência e a janela do dia antigas ao banco.
        forms["objetivo"].save()
        if "divisao" in forms:
            divisao = forms["divisao"].save()
            # Salvar a divisão é o que transforma o padrão do campo numa
            # escolha (era o `form_valid` do passo 4).
            Profile.objects.filter(pk=divisao.pk).update(split_preference_confirmada=True)
        forms["rotina"].save()


class PersonalizacaoView(EtapaCompostaView):
    """Etapa 3 — estilo do cardápio, restrições, áreas e prioridade; e o resumo."""

    step = 3
    nomes_dos_forms = ("comida", "areas")

    def instanciar(self, nome, dados):
        if nome == "comida":
            return RestrictionsForm(dados, instance=self.profile)
        return InteressesForm(dados, instance=self.profile)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Só no cadastro: o resumo é a conferência antes de "Criar meu plano".
        # Quem veio do Perfil trocar o cardápio não tem esse botão, e um
        # `<dl>` de altura e dias que não se editam ali seria ruído.
        if not context.get("is_editing"):
            context["resumo"] = resumo_das_escolhas(self.request.user, self.get_profile())
        return context

    def salvar(self, forms):
        forms["comida"].save()
        forms["areas"].save()


#: A partir de quantos dias a divisão passa a mudar a ficha — o mesmo número
#: que `preferencia_muda_a_divisao` lê da tabela do motor. Calculado uma vez,
#: para o template dizer ao JavaScript "revele com N dias".
MINIMO_DE_DIAS_PARA_DIVISAO = next(
    (dias for dias in range(1, 8) if preferencia_muda_a_divisao(dias)), 8
)


def resumo_das_escolhas(user, profile) -> list:
    """As escolhas das etapas 1 e 2, em pares (rótulo, valor), para a etapa 3.

    Só leitura: é a pessoa conferindo antes de "Criar meu plano". Dias sem
    treino é uma resposta, e aparece como tal.
    """
    if profile is None:
        return []
    peso = profile.current_weight
    dias = sorted(user.training_days.values_list("weekday", flat=True))
    nomes = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
    itens = [
        ("Altura e peso", "%d cm · %s kg" % (profile.height_cm, formats.number_format(peso, decimal_pos=1)) if peso is not None else "%d cm" % profile.height_cm),
        ("Objetivo", profile.get_goal_display()),
        ("Atividade", profile.get_activity_level_display()),
        ("Dias de treino", ", ".join(nomes[d] for d in dias) if dias else "Nenhum por enquanto"),
    ]
    if profile.experiencia:
        itens.append(("Experiência", profile.get_experiencia_display()))
    itens.append(("Equipamento", profile.get_equipamento_display()))
    if profile.split_preference_confirmada:
        itens.append(("Divisão", profile.get_split_preference_display()))
    return itens


STEP_VIEWS = {
    1: SobreVoceView,
    2: ObjetivoERotinaView,
    3: PersonalizacaoView,
}


def onboarding_step(request, step):
    """Despacha /conta/onboarding/<n>/ para a view da etapa.

    Uma rota só em vez de três mantém a navegação (voltar, avançar, retomar)
    resolvida por um reverse() com número. Etapa que não existe é 404 — e
    não "cai na 1": `/conta/onboarding/4/` foi rota por meses, e um link
    velho que "funciona" abrindo outra tela nunca é consertado.
    """
    view = STEP_VIEWS.get(step)
    if view is None:
        raise Http404("etapa não existe")
    return view.as_view()(request)


class OnboardingEntryView(LoginRequiredMixin, TemplateView):
    """Redireciona para a etapa pendente — o atalho 'continuar de onde parei'."""

    #: Onde o peso é coletado. A etapa 1 salva `WeightEntry` junto com altura,
    #: sexo e nascimento — ver `BodyDataForm.save`.
    PASSO_DO_PESO = 1

    def get(self, request, *args, **kwargs):
        profile = Profile.objects.filter(user=request.user).first()
        if profile is None:
            return redirect("accounts:onboarding_step", step=1)
        if profile.onboarding_complete:
            # "Completo" aqui é CONTADOR DE ETAPAS. O motor tem outra régua:
            # `build_inputs` também recusa quando não há peso registrado, e a
            # tela Hoje devolve para cá quando isso acontece.
            #
            # Sem esta checagem as duas réguas discordam e a pessoa fica presa
            # num LOOP: `/` manda para o onboarding porque falta peso, o
            # onboarding manda para `/` porque o contador chegou ao fim, e o
            # navegador vai e volta até desistir. Reproduzido com uma conta
            # real do banco local — último passo, nenhuma pesagem.
            #
            # A regra: quem decide se dá para entrar no app é o MOTOR. Aqui só
            # se traduz a recusa dele para a etapa que resolve.
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
        passos = passos_de(request.user, profile)
        return redirect("accounts:onboarding_step", step=passo_alvo(profile, passos))


class ProfileSummaryView(LoginRequiredMixin, TemplateView):
    """Resumo do perfil com atalho para reeditar qualquer passo."""

    template_name = "accounts/profile.html"

    def _plano_em_vigor(self, profile):
        """O plano gravado, e se ele ainda vale — sem escrever nada.

        A PRIMEIRA VERSÃO CHAMAVA `sync_active_plan` E ESTAVA ERRADA por dois
        motivos que a suíte mediu: ela subiu a tela de 15 para 19 consultas,
        porque um plano vencido faz o cardápio inteiro ser regerado; e ela
        CRIAVA plano num GET de tela de leitura, o que apagou o estado "ainda
        não tem plano" que `ProfileActionsTests` cobre de propósito.

        O defeito de verdade é outro e é mais barato de consertar: a tela
        chamava o número gravado de "suas metas de hoje" mesmo quando ele já
        não era. Medido no navegador — depois de registrar 78,4 kg no lugar de
        80, o Perfil dizia 2.520 e o motor já respondia 2.497.

        Então aqui não se sincroniza: compara-se. `plan_is_current` já existe,
        não escreve, e é a MESMA função que as telas do app usam para decidir
        se refazem o plano — uma fonte só para a pergunta "este plano ainda
        vale?". Quem responde "não" ganha um aviso na tela, ao lado do botão
        que recalcula.
        """
        plano = self.request.user.plans.filter(is_active=True).first()
        if plano is None or profile is None or not profile.onboarding_complete:
            return plano, False

        from plans.services import IncompleteProfile, build_inputs, plan_is_current

        try:
            atual = plan_is_current(plano, build_inputs(self.request.user))
        except IncompleteProfile:
            # Falta dado para calcular: não dá para afirmar que venceu.
            return plano, False
        return plano, not atual

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = Profile.objects.filter(user=self.request.user).first()
        plano, plano_vencido = self._plano_em_vigor(profile)
        # UMA leitura dos dias de treino, para quatro consumidores: o cartão
        # (existe algum?), a linha "Seg · Qua · Sex", o cartão da divisão e a
        # explicação dela. Eram `count()` + `all()` + `order_by()` — três
        # consultas para a mesma lista de até sete linhas.
        dias_de_treino_lista = list(self.request.user.training_days.order_by("weekday"))
        dias_de_treino = len(dias_de_treino_lista)
        context.update(
            {
                "profile": profile,
                "training_days": dias_de_treino_lista,
                # "Seg · Qua · Sex": o mesmo vocabulário curto do resumo da
                # etapa 3, lido de `DIA_CURTO` (o do formulário). O nome inteiro
                # partia em "Quinta-/feira" a 390 px (avaliação de 16/09, B33).
                "dias_de_treino_curtos": " · ".join(
                    DIA_CURTO[Weekday(d.weekday)] for d in dias_de_treino_lista
                ),
                "weight_entries": self.request.user.weight_entries.all()[:10],
                # O plano ATIVO, para o perfil mostrar as metas em vigor ao
                # lado do botao que as recalcula. Sem ele o botao pedia fe: a
                # pessoa recalculava sem saber de que numero estava saindo.
                #
                # SINCRONIZADO, e não lido cru. Esta linha era
                # `plans.filter(is_active=True).first()`, e mostrava o plano
                # ANTIGO: as telas do app chamam `sync_active_plan` no GET
                # (`PlanRequiredMixin`), o Perfil não chamava, e as duas
                # discordavam. Medido — depois de registrar 78,4 kg no lugar de
                # 80, o Perfil dizia 2.520 kcal enquanto o motor já respondia
                # 2.497. Quem abrisse o Perfil antes de Hoje via a meta velha
                # bem ao lado do botão de recalcular.
                #
                # Só para quem já terminou o cadastro: `sync_active_plan`
                # precisa do perfil inteiro, e esta tela é `LoginRequiredMixin`
                # — alguém no meio do onboarding chega aqui.
                "plano": plano,
                "plano_vencido": plano_vencido,
                "step_meta": STEP_META,
                # Mesma regra do wizard, para o perfil não oferecer um
                # "Editar" que leva a uma tela que a guarda vai recusar.
                "divisao_importa": preferencia_muda_a_divisao(dias_de_treino),
                # A MESMA EXPLICAÇÃO QUE A TELA DE TREINO MOSTRA.
                #
                # `divisao_explicada` nasceu porque o Perfil dizia "1 grupo por
                # dia" enquanto a ficha entregava AB — e a ressalva foi parar
                # só na tela de Treino. O Perfil continuava sendo o lugar onde
                # a frase mentia, que é o lugar onde ela precisava aparecer.
                # É a mesma chamada e o mesmo dicionário: duas telas contando a
                # mesma coisa, e não duas versões dela.
                #
                # `dias` vem por argumento e não é contado de novo: a linha
                # acima já pagou por essa consulta, e o orçamento de consultas
                # desta tela é medido.
                "divisao": divisao_explicada(self.request.user, dias=dias_de_treino),
                "nav": "profile",
            }
        )
        return context


class OnboardingRequiredMixin(LoginRequiredMixin):
    """Usado pelas telas do app: sem onboarding completo, não há plano possível."""

    #: O perfil que o `dispatch` já buscou, para a view não buscar de novo.
    #:
    #: Guardar é ADITIVO: nenhuma tela que não leia este atributo muda de
    #: comportamento nem de número de consultas. A alternativa era preencher o
    #: cache do descritor (`request.user.profile = profile`), que ficaria mais
    #: barato para todo mundo — e mudaria a contagem de telas que hoje têm teto
    #: medido em `plans/test_stress.py`. Melhorar a conta alheia no meio de uma
    #: campanha de navegação é otimização sem medição, e ela fica para quem
    #: medir.
    perfil_do_dispatch = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            profile = Profile.objects.filter(user=request.user).first()
            if profile is None or not profile.onboarding_complete:
                return redirect("accounts:onboarding")
            self.perfil_do_dispatch = profile
        return super().dispatch(request, *args, **kwargs)



class AreasView(OnboardingRequiredMixin, TemplateView):
    """Áreas — o quarto destino da barra, e o que não cabe nela.

    UX-01. Antes desta tela a navegação tinha DOIS sistemas: a barra de baixo
    com quatro itens e um `<details>` chamado "Áreas" no canto superior
    direito. O dono, usando o app, descreveu o efeito: "uma barra principal
    mais um segundo menu paralelo", sem hierarquia entre os dois.

    A REGRA QUE DEFINE O CONTEÚDO: Áreas não repete o que a barra já alcança
    direto. Alimentação, Treino e Progresso ficam de fora — quem quer chegar
    neles toca na barra, que está a um dedo daqui. O que sobra são os dois
    pilares sem porta de primeiro nível (Corrida e Hidratação), as ferramentas
    que nunca tiveram porta fixa, e a conta.

    O que esta tela NÃO é: um mapa dos cinco pilares. Aquele mapa mostrava a
    estrutura inteira porque vivia fora da barra e não competia com ela; aqui
    ele seria a duplicação que UX-01 veio remover. A nota no topo diz onde
    estão os outros três, em uma linha, sem link — porque o link é a barra.
    """

    template_name = "accounts/areas.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["nav"] = "areas"
        # O perfil vem do `dispatch`, que já o buscou para decidir se esta
        # tela abre. Buscá-lo de novo aqui é a segunda consulta na mesma
        # tabela no mesmo pedido — e é o que `OCustoDaTelaDeAreasEstaMedido`
        # pega.
        contexto["areas"] = navegacao.areas_fora_da_barra(
            self.request, self.request.user, "areas",
            perfil=self.perfil_do_dispatch,
        )
        # `is_staff` e não a permissão de gestão: quem não é staff nem vê a
        # seção, e quem é staff sem a permissão recebe o 403 da própria tela.
        # Esconder por permissão exigiria consultar o grupo em toda renderização
        # desta tela para poupar um clique de uma pessoa.
        contexto["mostra_gestao"] = self.request.user.is_staff
        # O fato entra DENTRO da área, e não num dicionário paralelo: template
        # do Django não indexa dicionário por variável, e resolver isso com
        # filtro novo seria inventar infraestrutura para uma linha de HTML.
        fatos = self._fatos_das_areas()
        for area in contexto["areas"]:
            area["fato"] = fatos.get(area["valor"])
            area["progresso"] = fatos.get(area["valor"] + ":pct")
            area["convite"] = fatos.get(area["valor"] + ":convite")
        contexto["ferramentas"] = self._fatos_das_ferramentas()
        return contexto

    def _fatos_das_ferramentas(self):
        """O que cada ferramenta responde ANTES do toque — a custo fixo.

        Conquistas: quantas e a mais recente, numa consulta. `proxima` fica de
        fora de propósito: ela passa por `achievements.reunir()`, que o
        Progresso paga com orçamento de 26 consultas; Áreas é hub de um
        relance e a régua dela é `OCustoDaTelaDeAreasEstaMedidoTests`.

        Perfil: objetivo e meta de calorias do plano ativo, numa consulta. É a
        porta da conta, e a primeira coisa que a pessoa confere nela é "para
        quanto estou comendo".
        """
        from achievements.models import UserAchievement
        from plans.models import NutritionPlan

        fatos = {}
        # UMA consulta: quantas e a mais recente saem da mesma lista. São
        # dezenas de linhas no pior caso; duas consultas (count + first)
        # custariam mais que trazer a lista.
        ganhas = list(
            UserAchievement.objects.filter(user=self.request.user).order_by("-pk")
        )
        if ganhas:
            quantas = len(ganhas)
            fatos["conquistas"] = {
                "valor": f"{quantas}",
                "rotulo": ("conquista" if quantas == 1 else "conquistas")
                + f" · última: {ganhas[0].titulo}",
            }
        perfil = self.perfil_do_dispatch
        plano = NutritionPlan.objects.filter(
            user=self.request.user, is_active=True
        ).only("target_kcal").first()
        if perfil is not None:
            objetivo = perfil.get_goal_display().lower()
            if plano is not None:
                fatos["perfil"] = {
                    "valor": f"{plano.target_kcal:,}".replace(",", "."),
                    "rotulo": f"kcal por dia · {objetivo}",
                }
            else:
                # Sem plano ainda (a pessoa nunca abriu Hoje), o objetivo
                # sozinho já responde "para que este perfil existe".
                fatos["perfil"] = {"valor": objetivo.capitalize(), "rotulo": "é o objetivo"}
        return fatos

    def _fatos_das_areas(self):
        """Um fato REAL por área, para a tela parar de parecer Configurações.

        Uma lista de nome + descrição + seta é um menu: ela pede um toque
        para responder qualquer coisa. O que transforma menu em hub é a
        pergunta já respondida na linha — "quanto bebi hoje?" não deveria
        custar uma navegação.

        Três regras, e as três são de honestidade:

        1. Só entra fato que existe. Sem dado, a linha fica como estava — um
           zero inventado ("0 corridas") é pior que silêncio, porque afirma
           que a pessoa não corre quando o app apenas não sabe.
        2. O custo é FIXO, não por linha. A meta de água sai do peso do perfil
           que o `dispatch` já carregou (zero consulta) e as duas consultas
           daqui não crescem com o número de áreas — que é a propriedade que
           `OCustoDaTelaDeAreasEstaMedidoTests` protege.
        3. A meta vem de `weight_trend.hidratacao_ml`, chamada e não copiada.
           Uma segunda fórmula aqui divergiria da tela de água no primeiro
           ajuste, e a mesma pessoa veria duas metas no mesmo app.
        """
        from plans import weight_trend
        from plans.models import HydrationLog
        from workouts.models import Corrida

        fatos = {}
        # O peso sai de `request.user`, e não de `perfil.current_weight`.
        # A propriedade faz `self.user.weight_entries.first()`, e o `self.user`
        # dela re-busca o usuário que este pedido já tem em memória: medido,
        # eram DUAS consultas para responder uma pergunta.
        entrada = self.request.user.weight_entries.first()
        peso = entrada.weight_kg if entrada else None
        if peso:
            meta = weight_trend.hidratacao_ml(peso)
            registro = HydrationLog.objects.filter(
                user=self.request.user, date=timezone.localdate()
            ).first()
            bebido = registro.ml if registro else 0
            if meta:
                # Valor e rotulo separados porque a tela agora e uma GRADE: o
                # numero e o protagonista do modulo e o rotulo orbita embaixo
                # dele. Uma frase unica ("1600 de 2500 ml hoje") obrigaria o
                # template a fatiar texto para achar o numero.
                fatos["hidratacao"] = {
                    "valor": f"{bebido:,}".replace(",", "."),
                    "rotulo": f"de {meta:,} ml hoje".replace(",", "."),
                }
                # A BARRA é o que faz o número caber num relance (§6
                # "progresso"): 1.250 de 3.500 pede conta; um terço da barra
                # cheia não pede.
                fatos["hidratacao:pct"] = min(100, round(100 * bebido / meta))

        # A última corrida diz mais que a contagem — "5,2 km" responde "como
        # foi" e a contagem só "quantas". Uma consulta a mais, de custo fixo.
        # UMA consulta para as duas perguntas — "quantas" e "qual foi a
        # última" —: a lista de distâncias em ordem. Corrida é evento raro
        # (dezenas por pessoa por ano), e `count()` + `first()` seriam duas.
        distancias = list(
            Corrida.objects.filter(user=self.request.user)
            .order_by("-terminou_em")
            .values_list("distancia_m", flat=True)
        )
        if distancias:
            corridas = len(distancias)
            km = f"{distancias[0] / 1000:.1f}".replace(".", ",")
            fatos["corrida"] = {
                "valor": f"{km} km",
                "rotulo": ("última corrida · 1 registrada" if corridas == 1
                           else f"última corrida · {corridas} registradas"),
            }
        else:
            # SEM HISTÓRICO, O VAZIO CONVIDA (§39): dizer o que a área faz e
            # qual é o primeiro passo, em vez de descrever a ferramenta.
            fatos["corrida:convite"] = "Grave a primeira com o GPS do celular."
        return fatos


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
        # COM O NÚMERO (UX UXA-06): a faixa da Home some depois de salvar —
        # o convite de pesagem deixa de valer — e "Peso registrado." sem o
        # valor deixava a pessoa sem ver o dígito que acabou de digitar.
        messages.success(
            request,
            "Peso registrado: %s kg." % formats.number_format(
                form.cleaned_data["weight_kg"], decimal_pos=2
            ),
        )
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
    from workouts.models import ExerciseLog, TrainingPlan

    linhas = [
        ("Planos alimentares", NutritionPlan.objects.filter(user=user).count()),
        ("Refeições registradas", MealLog.objects.filter(user=user).count()),
        ("Registros de água", HydrationLog.objects.filter(user=user).count()),
        ("Pesagens", WeightEntry.objects.filter(user=user).count()),
        ("Fichas de treino", TrainingPlan.objects.filter(user=user).count()),
        ("Séries registradas", ExerciseLog.objects.filter(user=user).count()),
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
