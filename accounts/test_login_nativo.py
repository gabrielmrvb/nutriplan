"""O login NATIVO da casca (Fase 2 da missão Capacitor, 22/09/2026).

Dentro do app instalado o Google recusa o OAuth por WebView, então a casca
usa o SDK nativo (Google no Android e no iOS, Apple no iOS) e manda ao
servidor só o `id_token` assinado. `LoginNativoView` verifica a assinatura
com o MESMO `provider.verify_token` do allauth que o One Tap usa (emissor,
audiência = client id, validade) e entrega o resto a `complete_social_login`
— a mesma política do adapter: conta nova nasce, `uid` conhecido entra,
e-mail com senha utilizável PEDE A SENHA (caso 4). Nenhuma regra de vínculo
é reescrita aqui; a view só troca o transporte.

O token de verdade não existe em teste: `verify_token` é substituído por um
que devolve o `SocialLogin` que o allauth devolveria — o contrato da view é
o que acontece ANTES (recusas) e DEPOIS (o que ela faz com o login).
"""
from unittest import mock

from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from config.test_casca_web import UA_ANDROID, UA_IOS


def _verify_token_falso(uid="uid-do-google", email="nova@exemplo.com"):
    """O que `provider.verify_token` devolveria para um token BOM: um
    `SocialLogin` com a conta social, o usuário ainda não salvo e o e-mail
    marcado como verificado pelo provedor — montado pelo PRÓPRIO provider
    (`sociallogin_from_response` é o caminho real; só a assinatura do JWT
    fica de fora, porque não há Google nem Apple no teste)."""
    from allauth.account.models import EmailAddress

    def verify_token(self, request, token):
        conta = SocialAccount(provider=self.id, uid=uid, extra_data={"email": email})
        user = User(email=email, first_name="Dani")
        return SocialLogin(user=user, account=conta, provider=self,
                           email_addresses=[EmailAddress(email=email, verified=True, primary=True)])

    return verify_token


@override_settings(GOOGLE_LOGIN_ENABLED=True, APPLE_LOGIN_ENABLED=True)
class LoginNativoTests(TestCase):
    URL = reverse("accounts:login_nativo")

    def _post(self, dados, ua=UA_ANDROID):
        return self.client.post(self.URL, dados, HTTP_USER_AGENT=ua)

    def test_provedor_desconhecido_e_400(self):
        resposta = self._post({"provedor": "facebook", "id_token": "x"})
        self.assertEqual(resposta.status_code, 400)

    def test_sem_token_e_400(self):
        resposta = self._post({"provedor": "google"})
        self.assertEqual(resposta.status_code, 400)

    def test_token_invalido_e_recusado_sem_dizer_por_que(self):
        from allauth.core.exceptions import ImmediateHttpResponse  # noqa: F401
        from allauth.socialaccount.adapter import get_adapter

        with mock.patch("allauth.socialaccount.providers.google.provider.GoogleProvider.verify_token",
                        side_effect=get_adapter().validation_error("invalid_token")):
            resposta = self._post({"provedor": "google", "id_token": "assinado-por-ninguem"})
        self.assertEqual(resposta.status_code, 403)
        self.assertNotIn("invalid_token", resposta.content.decode())

    def test_token_bom_de_conta_nova_cria_a_conta_e_entra(self):
        with mock.patch("allauth.socialaccount.providers.google.provider.GoogleProvider.verify_token",
                        new=_verify_token_falso()):
            resposta = self._post({"provedor": "google", "id_token": "ok"})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(User.objects.filter(email="nova@exemplo.com").exists())
        self.assertTrue(SocialAccount.objects.filter(provider="google", uid="uid-do-google").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_conta_com_senha_pede_a_senha_como_no_google_da_web(self):
        """Caso 4 do adapter: o transporte nativo NÃO abre a porta que o
        fluxo da web mantém fechada."""
        User.objects.create_user(email="nova@exemplo.com", password="senha-bem-forte-123")
        with mock.patch("allauth.socialaccount.providers.google.provider.GoogleProvider.verify_token",
                        new=_verify_token_falso()):
            resposta = self._post({"provedor": "google", "id_token": "ok"})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:conectar_google"), resposta["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_apple_so_com_a_conta_apple_configurada(self):
        with self.settings(APPLE_LOGIN_ENABLED=False):
            resposta = self._post({"provedor": "apple", "id_token": "x"}, ua=UA_IOS)
        self.assertEqual(resposta.status_code, 400)

    def test_apple_com_token_bom_entra(self):
        with mock.patch("allauth.socialaccount.providers.apple.provider.AppleProvider.verify_token",
                        new=_verify_token_falso(uid="000123.apple", email="maca@privaterelay.appleid.com")):
            resposta = self._post({"provedor": "apple", "id_token": "ok"}, ua=UA_IOS)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(SocialAccount.objects.filter(provider="apple", uid="000123.apple").exists())

    def test_o_csrf_da_pagina_e_exigido(self):
        cliente = Client(enforce_csrf_checks=True)
        resposta = cliente.post(self.URL, {"provedor": "google", "id_token": "x"}, HTTP_USER_AGENT=UA_ANDROID)
        self.assertEqual(resposta.status_code, 403)


@override_settings(GOOGLE_LOGIN_ENABLED=True, APPLE_LOGIN_ENABLED=True)
class OsBotoesNativosTests(TestCase):
    def test_na_casca_os_botoes_sao_nativos_e_o_apple_so_no_iphone(self):
        android = self.client.get(reverse("accounts:login"), HTTP_USER_AGENT=UA_ANDROID).content.decode()
        ios = self.client.get(reverse("accounts:login"), HTTP_USER_AGENT=UA_IOS).content.decode()
        self.assertIn('data-login-nativo="google"', android)
        self.assertNotIn('data-login-nativo="apple"', android)
        self.assertIn('data-login-nativo="google"', ios)
        self.assertIn('data-login-nativo="apple"', ios)
        self.assertNotIn("google-entrada", ios, "o OAuth da web não aparece na casca")

    def test_no_navegador_nada_disso_existe(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertNotIn("data-login-nativo", html)
