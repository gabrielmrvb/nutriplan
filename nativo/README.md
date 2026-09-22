# NutriPlan nativo — a casca (Capacitor)

iOS e Android carregam o PWA de produção num WebView. **Não há cópia do
app aqui**: a sessão, o service worker, a fila offline e todas as telas são
as de `https://nutriplan-xxfn.onrender.com`. O que a casca acrescenta é o
que a web não alcança — push pelo APNs/FCM, HealthKit/Health Connect,
Sign in with Apple, e a vitrine das lojas.

## Como funciona

- `capacitor.config.ts` — `server.url` é produção (`NUTRIPLAN_URL` troca
  para o staging ou um servidor local, para QA e para o CI). `allowNavigation`
  é só o host do app: qualquer outro link abre no navegador do sistema.
  `errorPath` é `www/erro.html`, a única tela local — quando nem a rede nem
  o cache do worker respondem.
- O WebView manda `NutriPlanNativo/1.0` no User-Agent (`appendUserAgent`):
  o servidor sabe que está falando com a casca (esconde o convite de
  instalar o PWA, troca o login com Google pelo nativo).
- **iOS**: o service worker só existe no WKWebView para domínio *app-bound*
  — `WKAppBoundDomains` no `Info.plist` lista produção e staging, e
  `limitsNavigationsToAppBoundDomains` está ligado. Sem os dois, o app abre
  mas o modo offline do NutriPlan não vale no iPhone.
- **Android**: o service worker funciona como no Chrome. Provado no
  emulador (API 35): a landing carrega, `sw.js` aparece como alvo do
  DevTools, e em modo avião a casca mostra o shell offline do PWA servido
  pelo worker.

## Rodar

```bash
npm ci
../.venv/Scripts/python.exe scripts/gerar_assets.py   # as fontes dos ícones/splash, da arte aprovada
npm run assets                                        # todos os tamanhos, nas duas plataformas
npx cap sync
npm run android:debug                                 # android/app/build/outputs/apk/debug/app-debug.apk
```

Android nesta máquina: SDK portátil em `C:\Users\biel-\android-dev\sdk`
(`android/local.properties` com `sdk.dir=C:/Users/biel-/android-dev/sdk`,
barras normais — a barra invertida é escape em `.properties`), JDK 21 do
Temurin. Emulador: `emulator -avd nutriplan35 -no-window -gpu
swiftshader_indirect -memory 1280` (a máquina tem 8 GB; mais que isso o
QEMU morre em `failed to allocate`), sempre por `scripts/fundo.py rodar`.

iOS só constrói em macOS: o fluxo `nativo.yml` do Actions faz o
`xcodebuild` no simulador e tira as capturas.

`config/test_nativo.py` prende o contrato: host de produção, marca de
User-Agent nas duas plataformas, app-bound no iOS, página de erro sem
recurso externo, e os tamanhos de ícone/splash que as lojas pedem.

## O que só o dono destrava

Conta Apple Developer (bundle `com.nutriplan.app`, certificados, perfis,
APNs), Google Play Console (assinatura, listagem), projeto Firebase (FCM)
— a lista numerada está no relatório da missão em
`achados/missao-capacitor-20260922.md`.
