import type { CapacitorConfig } from "@capacitor/cli";

/*
 * A casca nativa do NutriPlan.
 *
 * Ela NÃO embrulha uma cópia do app: o WebView carrega o PWA de produção
 * (`server.url`), com a mesma sessão, o mesmo service worker e a mesma fila
 * offline que o navegador usa. O que a casca acrescenta é o que a web não
 * alcança — push pelo APNs/FCM, HealthKit/Health Connect, Sign in with
 * Apple e a vitrine das lojas. `www/` só tem a página de erro de rede
 * (`server.errorPath`): quando nem a rede nem o cache do worker respondem.
 *
 * `NUTRIPLAN_URL` troca o destino para o staging ou para um servidor local
 * (o E2E do CI aponta para o staging); sem ela, produção.
 */
const url = process.env.NUTRIPLAN_URL || "https://nutriplan-xxfn.onrender.com";
const host = new URL(url).hostname;

const config: CapacitorConfig = {
  appId: "com.nutriplan.app",
  appName: "NutriPlan",
  webDir: "www",
  server: {
    url,
    // O host do app é a origem do WebView; qualquer outro link (o vídeo do
    // exercício, gov.br, a loja) abre no navegador do sistema.
    allowNavigation: [host],
    errorPath: "erro.html",
    androidScheme: "https",
    iosScheme: "https",
  },
  android: {
    // O servidor lê o User-Agent para saber que está falando com a casca
    // (`config/nativo.py`): esconde o convite "Instalar" do PWA, troca o
    // login com Google pelo nativo. `Capacitor.isNativePlatform()` no JS
    // diz o mesmo, mas só depois de a página carregar.
    appendUserAgent: "NutriPlanNativo/1.0",
    allowMixedContent: false,
    backgroundColor: "#0b140f",
    // O `<a download>` e a exportação de dados são `attachment`: o WebView
    // do Android entrega ao gerenciador de downloads em vez de abrir a página.
    webContentsDebuggingEnabled: false,
  },
  ios: {
    appendUserAgent: "NutriPlanNativo/1.0",
    contentInset: "automatic",
    backgroundColor: "#0b140f",
    // Service worker no WKWebView SÓ existe para domínio "app-bound"
    // (`WKAppBoundDomains` no Info.plist lista o host) e com esta chave.
    // Sem os dois, o PWA abre mas o modo offline do NutriPlan não vale no
    // iPhone — e é ele que guarda a água registrada no metrô.
    limitsNavigationsToAppBoundDomains: true,
    preferredContentMode: "mobile",
  },
  plugins: {
    FirebaseMessaging: {
      // No iOS a notificação em primeiro plano aparece como banner com som
      // (o padrão do plugin é só badge).
      presentationOptions: ["alert", "badge", "sound"],
    },
    SplashScreen: {
      launchShowDuration: 0,
      launchAutoHide: true,
      backgroundColor: "#0b140f",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    StatusBar: {
      style: "DARK",
      backgroundColor: "#0b140f",
      overlaysWebView: false,
    },
  },
};

export default config;
