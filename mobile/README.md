# O cliente Android do NutriPlan

Existe por um motivo só: **GPS com a tela bloqueada**, que a PWA não tem como
fazer. Tudo o mais que este app faz, o site já fazia melhor.

Se você está procurando por que ele não é um WebView apontando para o site,
a resposta está em [`../docs/corrida-mobile-arquitetura.md`](../docs/corrida-mobile-arquitetura.md)
e é medida: o Android estrangula requisições HTTP saídas do WebView depois de
5 minutos em segundo plano, e o requisito é correr 10+ minutos.

## O que ele NÃO é

- **não embrulha o Django.** `capacitor.config.json` não tem `server.url`, e
  isso é a decisão inteira: as telas são locais, em `www/`, e falam com
  `/api/v1/` por HTTPS;
- **não substitui a PWA.** O site continua igual. Este app não é o produto —
  é a Corrida do produto, na única forma em que ela funciona de verdade;
- **não pede `ACCESS_BACKGROUND_LOCATION`.** Ver a seção de permissões.

## Como está organizado

| arquivo | responsabilidade |
|---|---|
| `www/geo.js` | **a fronteira de geolocalização.** Só ele conhece o plugin |
| `www/corrida.js` | estado da corrida, persistência nativa, recuperação de crash |
| `www/api.js` | a conversa com o Django e a regra da fila (2xx/409/5xx) |
| `www/app.js` | fiação da tela |

A regra que sustenta as quatro: **nenhum arquivo além de `geo.js` importa o
plugin de GPS.** A escolha do plugin ainda pode mudar — a alternativa madura
custa US$ 399 — e trocar precisa ser reescrever um arquivo, não o app.

## Permissões, e a que falta de propósito

O app **não pede `ACCESS_BACKGROUND_LOCATION`**, e isso é arquitetura, não
esquecimento. A documentação do Android trata como localização de *primeiro
plano* tudo que acontece enquanto um foreground service está de pé, e cita a
tela apagada literalmente:

> "Your app retains access when it's placed in the background, such as when the
> user presses the Home button on their device or turns their device's display
> off."

Como a corrida só começa com o app aberto e sobe um serviço do tipo `location`,
a permissão de background nunca é necessária — e não pedi-la evita o
*Permissions Declaration Form* do Google Play.

Também foram **removidos** do merge do plugin, por não termos geofencing:
`RECEIVE_BOOT_COMPLETED` e os dois receivers de geofence. E `allowBackup` é
`false`: o app guarda token de acesso e coordenadas, e backup automático
mandaria os dois para a nuvem do fabricante.

## Construir

Requisitos: **Node 22+**, **JDK 17+** e **Android SDK** com plataforma API 24 ou
maior. Nesta máquina eles são portáteis, em `C:\Users\biel-\android-dev`.

```bash
npm ci
npx cap sync android
cd android && ./gradlew.bat assembleDebug
```

O APK sai em `android/app/build/outputs/apk/debug/app-debug.apk`.

### A armadilha do wrapper do Gradle

O primeiro build aqui falhou com `SocketTimeoutException` baixando o Gradle. A
rede estava boa — 224 MB em 5 segundos por `curl`. O culpado é o
`networkTimeout=10000` do wrapper, curto demais para a distribuição `-all` com
redirect.

Se acontecer com você, baixe a distribuição à mão e aponte o wrapper para o
arquivo local — **mas não commite essa mudança**, porque o caminho é da sua
máquina e quebraria o build de todo mundo.

## O que este app ainda NÃO faz

Dito aqui para ninguém procurar: não há mapa, não há compartilhamento, não há
histórico e não há pausa. A Fase 1 existe para provar **uma** coisa — que o
percurso sobrevive à tela bloqueada — e cada tela a mais seria superfície para
auditar antes de saber se a fundação funciona.

O diagnóstico na tela existe para essa prova: modo de GPS, modo de
armazenamento, contagem de pontos e **maior intervalo entre leituras**. É o
último que transforma "acho que continuou" em evidência — se o GPS parar com a
tela bloqueada, aparece um buraco de minutos entre dois pontos.
