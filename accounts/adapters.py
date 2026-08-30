"""A política de vínculo entre a conta NutriPlan e a identidade Google.

O PRINCÍPIO

Existe UMA conta NutriPlan, que pode ter mais de um método de autenticação.
Google não é "outro tipo de conta": é outra chave da mesma porta.

O QUE ESTE ARQUIVO DECIDE

Quando o Google devolve uma identidade válida, quatro coisas podem ser
verdade, e só três delas terminam em login imediato:

  1. Não existe usuário com aquele e-mail.
     → o allauth cria a conta e vincula. Senha inutilizável.

  2. Já existe `SocialAccount` com aquele `uid`.
     → é o caso recorrente. O allauth entra sozinho.

  3. Existe usuário com o mesmo e-mail, sem Google vinculado, e a senha local
     dele é INUTILIZÁVEL.
     → vincula sozinho. Não há senha para contornar: aquela conta só pode ter
       nascido de um fluxo social ou do admin.

  4. Existe usuário com o mesmo e-mail, sem Google vinculado, e a senha local
     é UTILIZÁVEL.
     → NÃO vincula. Pede a senha do NutriPlan uma vez, e só então conecta.

POR QUE O CASO 4 EXISTE

O NutriPlan não tem recuperação de senha — não há rota, view nem template.
Isso significa que **controlar o e-mail não é, hoje, um fator de autenticação
neste app**: quem tem a caixa de entrada da pessoa não consegue entrar.

Vincular automaticamente criaria uma porta que não existia. Quem comprometesse
o Gmail passaria a ver peso, dieta, treino e histórico. Não é "o mesmo risco do
reset de senha" — é risco novo, porque o reset não existe.

O atrito é de uma vez só: depois de conectado, a pessoa cai no caso 2 para
sempre.

O QUE ESTE ARQUIVO NÃO DECIDE

Para onde ir depois do login. Isso é `accounts:onboarding`, e a decisão de qual
passo mostrar mora em `OnboardingEntryView` — que já resolve perfil ausente,
onboarding incompleto e onboarding completo. Reproduzir essa regra aqui seriam
duas cópias, e a segunda envelhece na primeira vez que o wizard mudar.
"""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_email
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from .models import User

#: Onde o caso 4 guarda a tentativa até a senha ser conferida.
#:
#: Guarda o `SocialLogin` SERIALIZADO pelo próprio allauth, em sessão do
#: servidor. Nada disso passa por URL, campo escondido ou JavaScript — e a
#: serialização é a mesma que a biblioteca usa no fluxo de cadastro dela, em
#: vez de um formato inventado aqui.
SESSAO_VINCULO = "nutriplan_vinculo_google_pendente"

#: Quantas tentativas de senha a confirmação de vínculo aceita.
SESSAO_TENTATIVAS = "nutriplan_vinculo_google_tentativas"
MAXIMO_DE_TENTATIVAS = 5

#: O QUE ESTE LIMITE É, E O QUE ELE NÃO É.
#:
#: Ele é POR PENDÊNCIA. Esgotadas as cinco, a tentativa é descartada e para
#: tentar de novo é preciso refazer o handshake com o Google inteiro.
#:
#: E ele NÃO é proteção completa contra força bruta: quem chega aqui controla a
#: caixa de entrada, então pode refazer o handshake e ganhar mais cinco. O que
#: o limite compra é CUSTO por tentativa — cinco chutes por ida ao Google, em
#: vez de infinitos num formulário parado.
#:
#: Comparado com o que já existe, ainda assim melhora: `AppLoginView` não tem
#: limite NENHUM e não exige handshake nenhum. Esta tela é a superfície de
#: força bruta menos exposta das duas, não a mais.
#:
#: A correção de verdade é rate limiting de VERDADE, e ela não cabe aqui. O
#: allauth traz um (`ACCOUNT_RATE_LIMITS`), mas ele se apoia em
#: `django.core.cache` e a própria implementação avisa que é não atômica — e
#: este projeto não configura `CACHES`, então cairia no `LocMemCache`: contador
#: por processo, perdido a cada restart, multiplicado pelo número de workers do
#: gunicorn. Pareceria um limite e vazaria por um fator que ninguém mede.
#:
#: Fica registrado como risco conhecido, e a recomendação é uma missão própria
#: de rate limiting cobrindo LOGIN e LINKING juntos, com backend de cache
#: compartilhado — não um remendo neste endpoint.


def email_verificado(sociallogin) -> str:
    """O e-mail que o provedor garante, ou vazio.

    Só conta e-mail que veio do fluxo OIDC validado E que o provedor marcou
    como verificado. E-mail não verificado é texto que o provedor não garante:
    aceitar um permitiria a qualquer conta Google reivindicar qualquer endereço.
    """
    for endereco in sociallogin.email_addresses:
        if endereco.verified and endereco.email:
            return endereco.email.lower().strip()
    return ""


def usuario_com_email(email: str):
    """O usuário daquele e-mail, comparando sem diferenciar maiúsculas.

    `User.email` é `unique=True`, e a unicidade do Postgres É sensível a
    maiúsculas — "Nome@gmail.com" e "nome@gmail.com" cabem os dois na tabela.
    O formulário de cadastro já se defende com `iexact`; aqui a defesa precisa
    ser a mesma, senão o login social cria a segunda conta que o cadastro
    recusaria.
    """
    if not email:
        return None
    return User.objects.filter(email__iexact=email).first()


def pendencia(sociallogin, usuario) -> dict:
    """A identidade que espera pela senha — e SÓ a identidade.

    A primeira versão guardava `sociallogin.serialize()`, que é o mecanismo
    oficial do allauth para o fluxo de cadastro dele. Lido o código instalado,
    ele carrega junto o que não pode ficar em sessão:

        if self.token:
            ret["token"] = serialize_instance(self.token)

    e `SocialToken` tem `token` (o access token) e `token_secret` (o refresh
    token) como campos de texto. Provado em runtime com marcadores falsos: os
    dois apareciam na serialização, junto do `extra_data` da conta e do hash de
    senha do objeto de usuário.

    Nada disso é necessário para concluir um vínculo. O que o vínculo precisa é
    de quatro coisas, e todas elas nascem do callback JÁ VALIDADO pelo allauth
    — nenhuma vem do navegador:

        provider  qual provedor
        uid       o `sub` do Google, identidade permanente da conta lá
        email     o e-mail verificado, normalizado
        user_pk   a conta daqui, resolvida no servidor pelo e-mail

    O `email` fica junto do `user_pk` de propósito: na hora de conectar, os
    dois são conferidos um contra o outro. Se a conta tiver trocado de e-mail
    entre a ida ao Google e a volta, a pendência é descartada em vez de
    conectar ao alvo errado.
    """
    return {
        "provider": sociallogin.account.provider,
        "uid": sociallogin.account.uid,
        "email": email_verificado(sociallogin),
        "user_pk": usuario.pk,
    }


def recusa(request):
    """Uma mensagem só, sem detalhe técnico e sem dizer o que existe.

    "E-mail não verificado" e "conta desativada" contam coisas diferentes sobre
    quem está do outro lado, e as duas contam demais: a primeira ensina o que
    ajustar para tentar de novo, a segunda confirma que aquele e-mail tem conta
    aqui.
    """
    messages.error(request, "Não foi possível entrar com o Google. Tente novamente.")
    return redirect("accounts:login")


class NutriPlanSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Aplica a política acima antes de o allauth concluir o login."""

    def pre_social_login(self, request, sociallogin):
        """Chamado depois de o Google autenticar e antes de o login acontecer.

        É o ponto onde dá para desviar o fluxo levantando
        `ImmediateHttpResponse` — e é por isso que a política mora aqui e não
        num sinal: sinal não intervém, e a ordem entre vários é indefinida.
        """
        # CASO 2 — já existe vínculo com este `uid`. O allauth segue e o
        # `is_active` é conferido no login, por `respond_user_inactive`.
        if sociallogin.is_existing:
            return

        email = email_verificado(sociallogin)
        if not email:
            raise ImmediateHttpResponse(recusa(request))

        existente = usuario_com_email(email)

        # CASO 1 — ninguém com este e-mail. O allauth cria e vincula.
        if existente is None:
            return

        # Conta desativada não entra, e o Google não reativa nada. Vem antes
        # dos casos 3 e 4 de propósito: vincular a uma conta desativada seria
        # preparar a porta para quando ela voltasse.
        if not existente.is_active:
            raise ImmediateHttpResponse(recusa(request))

        # CASO 3 — sem senha utilizável: não há o que confirmar.
        if not existente.has_usable_password():
            sociallogin.connect(request, existente)
            return

        # CASO 4 — a conta tem senha. Guarda a IDENTIDADE e pede a senha.
        request.session[SESSAO_VINCULO] = pendencia(sociallogin, existente)
        raise ImmediateHttpResponse(redirect("accounts:conectar_google"))

    def populate_user(self, request, sociallogin, data):
        """O nome vem do Google; o e-mail vem normalizado.

        Normalizar aqui e não só no formulário é o que fecha o buraco de
        maiúsculas na criação: este caminho não passa por `SignupForm`.
        """
        user = super().populate_user(request, sociallogin, data)
        email = user_email(user)
        if email:
            user_email(user, email.lower().strip())
        return user


class NutriPlanAccountAdapter(DefaultAccountAdapter):
    """Só existe para uma coisa: recusar conta desativada sem quebrar a página.

    O `respond_user_inactive` da biblioteca faz `reverse("account_inactive")`, e
    essa rota mora em `allauth.account.urls` — que este projeto NÃO monta, de
    propósito, para não ter uma segunda interface de login. O resultado era um
    `NoReverseMatch` que ninguém captura: `complete_login` só trata
    `SignupClosedException` e `ImmediateHttpResponse`, e a view de callback só
    trata erros de OAuth. A pessoa recebia 500.

    E o caminho é real: `is_active` é campo editável no admin. Qualquer conta
    que já tenha conectado o Google e depois for desativada cairia aqui no
    próximo "Continuar com Google".

    O caso 2 da política — vínculo já existente — depende deste método: é ele
    que o `perform_login` chama, e é onde `is_active` é conferido para quem
    entra pelo `SocialAccount` em vez de pelo e-mail.
    """

    def respond_user_inactive(self, request, user):
        return recusa(request)
