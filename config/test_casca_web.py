"""O que o servidor faz DIFERENTE quando quem pede é a casca nativa
(`nativo/`, Capacitor) — reconhecida pelo `NutriPlanNativo/` no User-Agent
que `capacitor.config.ts` acrescenta nas duas plataformas (22/09/2026).

Três coisas, e o controle é o navegador comum, que continua vendo tudo:

* o convite "Instale o NutriPlan" não existe dentro do app instalado;
* o botão "Continuar com Google" some: o Google recusa OAuth dentro de
  WebView (`disallowed_useragent`), e um botão que leva a um erro do Google
  é pior que nenhum — o login nativo é a Fase 2;
* o `<html>` diz a plataforma (`data-app-nativo="android|ios"`), para o CSS
  e o JS que precisarem saber.
"""
from django.test import TestCase
from django.urls import reverse

from config.nativo import e_app_nativo, plataforma_nativa

UA_ANDROID = "Mozilla/5.0 (Linux; Android 15; Pixel 7 Build/AE3A.240806.043; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.0.0 Mobile Safari/537.36 NutriPlanNativo/1.0"
UA_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 NutriPlanNativo/1.0"
UA_CHROME = "Mozilla/5.0 (Linux; Android 15; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"


class OServidorReconheceACascaTests(TestCase):
    def test_pelo_user_agent_e_diz_a_plataforma(self):
        class Pedido:
            def __init__(self, ua):
                self.META = {"HTTP_USER_AGENT": ua}

        self.assertTrue(e_app_nativo(Pedido(UA_ANDROID)))
        self.assertTrue(e_app_nativo(Pedido(UA_IOS)))
        self.assertFalse(e_app_nativo(Pedido(UA_CHROME)))
        self.assertFalse(e_app_nativo(Pedido("")))
        self.assertEqual(plataforma_nativa(Pedido(UA_ANDROID)), "android")
        self.assertEqual(plataforma_nativa(Pedido(UA_IOS)), "ios")
        self.assertEqual(plataforma_nativa(Pedido(UA_CHROME)), "")


class ACascaNaoVeOQueNaoFazSentidoNelaTests(TestCase):
    def _landing(self, ua):
        return self.client.get("/", HTTP_USER_AGENT=ua).content.decode()

    def _login(self, ua):
        return self.client.get(reverse("accounts:login"), HTTP_USER_AGENT=ua).content.decode()

    def test_o_convite_de_instalar_o_pwa_nao_existe_no_app_instalado(self):
        self.assertNotIn('class="install"', self._landing(UA_ANDROID))
        self.assertIn('class="install"', self._landing(UA_CHROME), "controle: o navegador continua com o convite")

    def test_o_html_diz_a_plataforma_nativa(self):
        self.assertIn('data-app-nativo="android"', self._landing(UA_ANDROID))
        self.assertIn('data-app-nativo="ios"', self._landing(UA_IOS))
        self.assertNotIn("data-app-nativo", self._landing(UA_CHROME))

    def test_o_google_por_webview_nao_e_oferecido(self):
        with self.settings(GOOGLE_LOGIN_ENABLED=True):
            self.assertNotIn("google-entrada", self._login(UA_IOS))
            self.assertIn("google-entrada", self._login(UA_CHROME), "controle")
