"""A casca nativa (`nativo/`, Capacitor) — o contrato que o Django precisa
que ela cumpra, lido dos arquivos que o Capacitor de fato usa (22/09/2026).

Ela NÃO embrulha uma cópia do app: o WebView carrega o PWA de PRODUÇÃO
(`server.url`), com a mesma sessão, o mesmo service worker e a mesma fila
offline. O que a régua prende é o que faria a casca mentir ou quebrar por
fora: apontar para outro host, perder a marca de User-Agent que o servidor
lê, deixar o iOS sem `WKAppBoundDomains` (sem ele o service worker não
existe no WKWebView e o modo offline some no iPhone), ou uma página de erro
de rede que depende da rede para desenhar o próprio ícone.
"""
import json
import plistlib
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
NATIVO = RAIZ / "nativo"
PRODUCAO = "nutriplan-xxfn.onrender.com"
MARCA_DE_UA = "NutriPlanNativo/"


def _config_ts():
    return (NATIVO / "capacitor.config.ts").read_text(encoding="utf-8")


class AConfiguracaoDaCascaTests(SimpleTestCase):
    def test_a_casca_carrega_producao_e_so_navega_no_proprio_host(self):
        config = _config_ts()
        self.assertIn('"https://%s"' % PRODUCAO, config)
        self.assertIn("allowNavigation: [host]", config)
        self.assertIn('errorPath: "erro.html"', config)
        self.assertIn('appId: "com.nutriplan.app"', config)

    def test_o_servidor_reconhece_a_casca_pelo_user_agent_nas_duas_plataformas(self):
        config = _config_ts()
        self.assertEqual(config.count('appendUserAgent: "%s' % MARCA_DE_UA), 2, "Android e iOS")

    def test_o_iphone_tem_service_worker_porque_o_dominio_e_app_bound(self):
        config = _config_ts()
        self.assertIn("limitsNavigationsToAppBoundDomains: true", config)
        with open(NATIVO / "ios" / "App" / "App" / "Info.plist", "rb") as f:
            plist = plistlib.load(f)
        self.assertIn(PRODUCAO, plist["WKAppBoundDomains"])
        self.assertLessEqual(len(plist["WKAppBoundDomains"]), 10, "o WebKit aceita no máximo dez")
        self.assertEqual(plist["CFBundleDevelopmentRegion"], "pt-BR")
        self.assertIs(plist["ITSAppUsesNonExemptEncryption"], False)

    def test_a_pagina_de_erro_de_rede_nao_depende_da_rede(self):
        """Ela é a tela de quando NADA responde — nem rede, nem cache do
        worker. Um `<img src="...png">` ficaria quebrado (visto no emulador)."""
        html = (NATIVO / "www" / "erro.html").read_text(encoding="utf-8")
        self.assertIn('lang="pt-br"', html)
        self.assertIn("Sem conexão", html)
        for src in re.findall(r'src="([^"]+)"', html):
            self.assertTrue(src.startswith("data:"), "recurso externo na página de erro: %s" % src[:40])
        self.assertNotIn("<link", html)
        self.assertIn("https://%s/" % PRODUCAO, html)


class OsAssetsDasLojasTests(SimpleTestCase):
    def test_as_fontes_dos_icones_e_splash_existem_nos_tamanhos_que_as_lojas_pedem(self):
        from PIL import Image

        esperados = {
            "icon-only.png": (1024, 1024),
            "icon-foreground.png": (1024, 1024),
            "icon-background.png": (1024, 1024),
            "splash.png": (2732, 2732),
            "splash-dark.png": (2732, 2732),
        }
        for nome, tamanho in esperados.items():
            with Image.open(NATIVO / "assets" / nome) as imagem:
                self.assertEqual(imagem.size, tamanho, nome)
                if nome == "icon-only.png":
                    self.assertEqual(imagem.mode, "RGB", "o ícone da App Store não pode ter alfa")

    def test_o_android_tem_icone_adaptativo_e_o_ios_o_icone_de_1024(self):
        android = NATIVO / "android" / "app" / "src" / "main" / "res"
        self.assertTrue((android / "mipmap-anydpi-v26" / "ic_launcher.xml").exists())
        for densidade in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
            self.assertTrue((android / ("mipmap-" + densidade) / "ic_launcher_foreground.png").exists(), densidade)
        icones = json.loads((NATIVO / "ios" / "App" / "App" / "Assets.xcassets" / "AppIcon.appiconset" / "Contents.json").read_text(encoding="utf-8"))
        self.assertTrue(any(i.get("size") == "1024x1024" for i in icones["images"]))


class OProjetoNativoNaoCarregaSegredoTests(SimpleTestCase):
    def test_nenhum_arquivo_de_credencial_de_firebase_ou_chave_entra_no_git(self):
        ignore = (NATIVO / ".gitignore").read_text(encoding="utf-8")
        for nome in ("google-services.json", "GoogleService-Info.plist", "*.keystore", "*.jks", "local.properties"):
            self.assertIn(nome, ignore, nome)
