from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import path, reverse_lazy

from . import exportacao, views
from .forms import DefinirSenhaForm, RecuperarSenhaForm, TrocarSenhaForm

app_name = "accounts"

urlpatterns = [
    path("cadastro/", views.SignupView.as_view(), name="signup"),
    path("entrar/", views.AppLoginView.as_view(), name="login"),
    # O caso 4 da política de vínculo: e-mail do Google bate com uma conta que
    # já tem senha, e a senha é pedida uma vez antes de conectar.
    path("conectar-google/", views.ConectarGoogleView.as_view(), name="conectar_google"),
    path("sair/", LogoutView.as_view(), name="logout"),
    # ----------------------------------------------------------------- senha
    #
    # As views são as do Django, e isso é escolha: token assinado, expiração,
    # invalidação no uso e hash da senha na assinatura são criptografia, e
    # criptografia caseira é como se perde conta de gente.
    #
    # O que é nosso são os TEMPLATES. O projeto mantém uma interface de
    # autenticação só (ver o comentário em `config/urls.py` sobre deixar
    # `allauth.account.urls` de fora), então as telas de senha usam a mesma
    # identidade de `login.html` em vez de trazer a segunda cópia da
    # biblioteca.
    path(
        "senha/",
        views.PedirSenhaView.as_view(
            template_name="accounts/senha_pedir.html",
            form_class=RecuperarSenhaForm,
            email_template_name="accounts/email_senha.txt",
            # O `.txt` continua sendo o corpo principal e o `.html` vai como
            # alternativa: cliente que nao renderiza HTML — e leitor de tela —
            # recebe o texto, com o mesmo link.
            html_email_template_name="accounts/email_senha.html",
            subject_template_name="accounts/email_senha_assunto.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "senha/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/senha_enviado.html"
        ),
        name="password_reset_done",
    ),
    # `uidb64` e `token` são o par que o Django assina. A view troca o token da
    # URL por um na sessão antes de mostrar o formulário — por isso o endereço
    # com o token não fica no histórico do navegador junto com a senha nova.
    path(
        "senha/nova/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/senha_nova.html",
            form_class=DefinirSenhaForm,
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "senha/pronta/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/senha_pronta.html"
        ),
        name="password_reset_complete",
    ),
    # Trocar senha estando logado. `PasswordChangeView` chama
    # `update_session_auth_hash` sozinha: a senha muda e a sessão continua de
    # pé, em vez de derrubar a pessoa para a tela de login logo depois de ela
    # fazer a coisa certa.
    path(
        "senha/trocar/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/senha_trocar.html",
            form_class=TrocarSenhaForm,
            success_url=reverse_lazy("accounts:password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "senha/trocada/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/senha_trocada.html"
        ),
        name="password_change_done",
    ),
    path("excluir/", views.ExcluirContaView.as_view(), name="excluir_conta"),
    # Portabilidade (LGPD, Art. 18, V). Mora aqui e não numa rota pública
    # porque o que ela devolve é a conta de quem está logado — e o caminho
    # inteiro do dado da pessoa começa em `accounts`.
    path(
        "exportar/",
        exportacao.ExportarDadosView.as_view(),
        name="exportar_dados",
    ),
    path("onboarding/", views.OnboardingEntryView.as_view(), name="onboarding"),
    path("onboarding/<int:step>/", views.onboarding_step, name="onboarding_step"),
    path("perfil/", views.ProfileSummaryView.as_view(), name="profile"),
    # O peso mora em accounts e continua com um escritor só. Uma rota em
    # `plans` deixaria WeightEntry sendo gravado de dois apps, com duas
    # validações para manter em sincronia.
    path("peso/", views.WeightLogView.as_view(), name="log_weight"),
]
