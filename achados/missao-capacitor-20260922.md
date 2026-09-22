# NutriPlan nativo (Capacitor) — o que foi feito, provado, e o que só você destrava (22/09/2026)

Sessão `nativo` (3146901b). Missão: envolver o PWA de produção numa casca
nativa (Capacitor) e deixar iOS e Android prontos para a loja, **sem
reescrever a interface**. Método: reproduzir e medir com o
`agent-browser`/emulador antes de tocar em código, teste escrito ANTES
(vermelho → verde), sabotagem nas guardas que importam, e publicação pela
fila (`branch → PR → suíte rápida → merge → staging → lote`).

Vocabulário: **[EXECUTADA]** feito no aparelho/navegador · **[OBSERVADA]**
lido na tela/HTML · **[LIDA NO CÓDIGO]** causa conferida no arquivo ·
**[LIMITAÇÃO]** o que a plataforma (ou a conta) não deixa.

---

## Onde cada coisa está

| PR | o que | estado |
|---|---|---|
| #113 | **Fase 0**: o 403 de CSRF de um formulário com `op_id` enviado pela tela | EM PRODUÇÃO (`a8db820`) |
| #115 | **Fase 1**: a casca (`nativo/`), ícones, splash, CI das duas plataformas | EM PRODUÇÃO (`a427665`) |
| #116 | Lado web da casca: sem convite de instalar, sem Google por WebView, shell offline honesto | EM PRODUÇÃO (`a427665`) |
| #117 | A prova do Android no CI (rede que cai e volta, socket do app vivo) | em `main` (`cad7ccd`) |
| #118 | **Fase 2**: push pelo FCM, Apple Saúde / Health Connect, login pelo SDK | na fila |
| #119 | **Fase 3**: política de saúde, textos e formulários de loja, capturas | este |

O app **não** foi enviado a loja nenhuma: o envio depende da sua conta (ver
"O que só você pode fazer").

---

## Fase 0 — os bugs "desiste", antes de qualquer coisa

Os três itens que você listou (equipamento, queda de sessão com perda do
digitado, erro de validação sem destaque) **já estavam corrigidos** pela
missão UX de 22/09 (PRs #108 e #111) e em produção. Refazer seria
duplicação; o que fiz foi **provar depois** e consertar o que a prova
achou.

Prova [EXECUTADA] no staging, com conta descartável criada pelo cadastro
público e apagada pela tela no fim (`qa-e2e-fase0…@nutriplan.invalid`, 11
de 11 passos):

| item | o que a prova mediu |
|---|---|
| equipamento | "Só o peso do corpo" escolhido na etapa 2 com DOIS dias → etapa 3 resume "Só o peso do corpo" → Perfil idem. Persiste. |
| CONTINUAR com 2 dias | existe, 198×53 px, fora de `[hidden]`, alcançável por `elementFromPoint` |
| erro de validação | corrida vazia → `aria-invalid` no campo, foco nele, visível na janela, "Este campo é obrigatório." embaixo |
| envio que cai | token de CSRF velho → "Este envio não pôde ser confirmado" → "Voltar ao formulário" → **5,2** e **00:31:10** de volta, com a nota "Devolvemos o que você tinha digitado aqui" |

**O que a prova achou, e virou o PR #113**: um formulário com `op_id`
(água, série, refeição, corrida) recusado pelo CSRF e enviado **pela tela**
devolvia a tela inteira em `{"code": "replay_offline_csrf_expirado", …}` —
JSON cru, sem botão de voltar, digitado perdido. `falha_de_csrf` decidia "é
replay" só por `op_id` no corpo, e o caminho ONLINE carimba o mesmo `op_id`.
O que distingue a DRENAGEM da fila é ser `fetch`: navegação de formulário
chega com `Sec-Fetch-Dest: document`. `accounts.replay.veio_da_tela` lê
isso; a fila continua recebendo a resposta que não a faz apagar o item
(5 testes com controle).

## Fase 1 — a casca

`nativo/` (Capacitor 8.5.2). O WebView carrega
`https://nutriplan-xxfn.onrender.com` — **nenhuma cópia do app**: a sessão,
o service worker, a fila offline e todas as telas são as do PWA.
`www/erro.html` é a única tela local (quando nem a rede nem o cache do
worker respondem; o ícone vai inline porque um `<img src>` externo ficou
quebrado no emulador).

- `allowNavigation` só o host do app; qualquer outro link abre no navegador
  do sistema. `appendUserAgent: NutriPlanNativo/1.0` nas duas plataformas.
- **iOS**: `WKAppBoundDomains` + `limitsNavigationsToAppBoundDomains` — sem
  os dois o WKWebView **não tem service worker** e o modo offline some no
  iPhone. `pt-BR`, retrato no iPhone, `ITSAppUsesNonExemptEncryption = NO`.
- Ícones e splash em todos os tamanhos (`@capacitor/assets`): 74 no Android
  (adaptive icon, claro e escuro), 7 no iOS (1024 sem alfa). As fontes saem
  de `nativo/scripts/gerar_assets.py`, que recorta o símbolo da arte
  aprovada com as medidas do `gerar_identidade.ps1`.

**O service worker funciona na casca — provado, não assumido**
[EXECUTADA]:

| aparelho | online | sem rede |
|---|---|---|
| Android (emulador Pixel 7, API 35, WHPX) | título "NutriPlan — alimentação e treino num app só"; `navigator.serviceWorker.controller` **verdadeiro** dentro da casca | modo avião → a tela é o **shell offline do PWA servido pelo worker** (`[data-shell-offline]`), não a `erro.html` |
| iOS (simulador, runner macOS do Actions) | a landing carrega no WKWebView | a mesma tela offline do PWA (capturas 04 e 05, do run do PR #115) |

**Honestidade sobre a prova do iOS**: ela é VISUAL — o WKWebView não expõe
DevTools no simulador, então não há como ler `serviceWorker.controller` de
fora como no Android. E num run posterior (o do PR #119) a captura do
offline saiu com a **tela inicial do iPhone**: o `simctl launch` responde na
hora, o app podia morrer em seguida, e o passo passava assim mesmo. Isso foi
corrigido — `prova_ios.sh` agora confere pelo `launchctl list` que o app
está de pé antes de cada captura, e reprova nomeando o que viu. As capturas
04 e 05 deste relatório são as do run em que o app ESTAVA na frente.

`nativo/scripts/prova_android.sh` é essa sequência (lê o WebView pelo
DevTools remoto — texto, não só captura), e `.github/workflows/nativo.yml`
a roda num emulador do Actions e faz `xcodebuild` + simulador no macOS —
**iOS só constrói lá**: esta máquina é Windows.

**Lado web** (#116): dentro da casca o convite "Instale o NutriPlan" não
existe (já está instalado) e o botão de OAuth do Google some (o Google
recusa WebView). E o shell offline deixou de confiar só no
`navigator.onLine`: no WebView em modo avião ele responde `true`, e a tela
dizia "o servidor está acordando — você está conectado". Agora duas
rejeições imediatas seguidas (1,5 s) viram "Você está sem conexão"
(reproduzido no Chrome por CDP: "acordando" → "sem conexão" em 2,7 s).

## Fase 2 — push, saúde e login

Tudo gated por `config.nativo.e_app_nativo`; o navegador não muda.

**Push.** `DispositivoNativo` guarda o token do FCM (chave = token, uma
linha por instalação); o servidor manda pelo FCM HTTP v1 com a conta de
serviço do projeto Firebase. No iOS o Firebase encaminha ao APNs. Os
lembretes são os mesmos: `due_slots` passou a contar quem só tem aparelho
nativo e `notify_user` manda para os dois mundos. Token morto é desativado;
falha de rede não é token morto. **Sem a conta de serviço nada sai e nada
quebra** — é o estado até o projeto Firebase existir.

**Saúde.** `capacitor-health` (MIT, **só leitura**) lê peso e treinos de
corrida; o servidor recebe o que a pessoa mandou importar e aplica a régua
que já existia: a corrida do aparelho passa pelo mesmo `_conferir_negocio`
da corrida de arquivo, entra com `Origem.APARELHO` (que não se edita) e
`op_id = aparelho:<id>` (que não duplica); a pesagem é uma por dia e
**nunca sobrescreve** a que a pessoa digitou. O manifesto declara TRÊS
permissões de saúde e **remove as outras nove** que o plugin traz.

**Login.** O SDK do aparelho devolve o `id_token`; `LoginNativoView` o
verifica com o MESMO `provider.verify_token` do allauth que o One Tap usa e
entrega a `complete_social_login` — a política do adapter fica inteira,
inclusive o caso 4 (e-mail com senha utilizável PEDE a senha). **Sign in
with Apple** entra no iPhone, como a App Store exige quando há Google.

Provado dentro do app [EXECUTADA] (emulador + servidor local, pelo DevTools
do WebView):

```
tela de entrar   → "Continuar com Google" nativo; OAuth da web ausente; data-app-nativo="android"
Lembretes        → cartão presente; permissão do FCM "granted"; POST /push/nativo/registrar/ → 201
                   (getToken falha com o Firebase de EXEMPLO — a conta do dono é o que falta)
Health Connect   → cartão presente; isHealthAvailable() {"available":true}
                   POST corridas → {"importadas":1}; POST peso → {"gravadas":1}
                   segunda importação → {"repetidas":1} e {"ja_tinha":1}  (idempotente)
```

## Fase 3 — preparo de loja

- **Capturas**: `nativo/scripts/capturas_de_loja.py` tira 30 imagens das
  telas REAIS (conta do demo, logada, servidor local — **sem** a faixa
  "Ambiente de demonstração" das rotas `/demo/`), nos **tamanhos exatos**
  de cada loja: iPhone 6.9" 1290×2796, iPhone 6.5" 1242×2688, iPad 13"
  2048×2732, telefone Android 1080×1920, tablets 7" e 10". Conferido: 30 de
  30 no pixel certo.
- **Textos**: `docs/loja/listagem.md` — nome, subtítulo, descrição curta e
  longa, novidades, palavras-chave, categoria, classificação etária, URLs e
  a nota para a revisão da Apple. Tudo na régua de linguagem do app:
  **estimativa** e **cardápio de exemplo**, nunca "plano alimentar", e o
  "não substitui nutricionista nem médico" está lá.
- **Política de privacidade**: seção nova **"Dados de saúde do seu aparelho
  (Apple Saúde e Health Connect)"**, com âncora `#saude-do-aparelho` — é
  ela que a folha de permissões do Health Connect abre. Diz o que é lido
  (peso e treinos de corrida, 30 dias), para quê, e as três negativas que a
  Apple e o Google cobram: **não escreve**, **não lê em segundo plano**,
  **não compartilha com ninguém**.
- **Formulários**: `docs/loja/privacidade-das-lojas.md` traz o App Privacy
  (Apple) e o Data Safety (Google) preenchidos linha a linha, com a coluna
  "onde no código" — e `config/test_docs_da_loja.py` prende a
  correspondência: as permissões justificadas são exatamente as declaradas
  no manifesto, e o que o app não lê (GPS, crash) está marcado como não
  coletado.

## O que NÃO foi feito, e por quê

- **Enviar às lojas.** Depende da sua conta e do seu cartão; a submissão é
  irreversível e ficou para você (lista abaixo).
- **Build de RELEASE assinado.** Precisa de keystore (Android) e de
  certificado/perfil da sua conta Apple. O que existe hoje é o debug,
  construído e rodado no emulador/simulador.
- **Push de ponta a ponta com notificação na tela.** Precisa do projeto
  Firebase (`getToken` recusa com o projeto de exemplo) e, no iPhone, da
  chave APNs. Todo o resto — registro, envio, desativação de token morto —
  está testado com a API falsa e provado no emulador até onde vai sem conta.
- **O CONTEÚDO da tela do iOS por leitura automática.** O WKWebView não
  expõe DevTools no simulador; o que o CI garante é que o app sobe, fica de
  pé e é fotografado nos três estados. O julgamento do que aparece continua
  sendo de quem olha a captura. **[LIMITAÇÃO]**
- **HealthKit em aparelho de verdade.** O simulador do iOS não tem dados de
  saúde e o entitlement exige perfil de provisionamento. No Android a
  leitura foi provada com o Health Connect do emulador respondendo
  `available`; os dados importados na prova foram enviados pelo mesmo
  caminho que o plugin usa. **[LIMITAÇÃO]**
- **Escrever no Apple Saúde / Health Connect.** Escolhi **só leitura**: o
  app não tem o que escrever que o aparelho já não saiba (peso vem de
  balança, corrida vem de relógio), e cada permissão de escrita é mais uma
  linha na folha de consentimento e no formulário da loja. A string de uso
  do iOS diz isso.
- **Gráfico de destaque do Play (1024×500)** e vídeo de prévia: arte, não
  código. Fica para você ou para uma missão de design.
- **A pasta `mobile/` antiga** (Capacitor standalone, saiu em 20/09) não
  voltou: a casca de agora é `server.url` sobre o PWA, como você pediu.

## Segurança e infra — o que vale saber

- O login nativo **não abre porta nova**: o `id_token` é verificado pelo
  allauth (assinatura, emissor, audiência) e a política de vínculo é a
  mesma do fluxo web, inclusive o caso em que a conta tem senha (pede a
  senha). O CSRF da página continua valendo.
- As rotas novas de `fetch` (`/push/nativo/…`, `/conta/peso/aparelho/`,
  `/treino/corridas/aparelho/`, `/conta/entrar/nativo/`) exigem sessão e
  CSRF, e estão declaradas em `config/test_acoes_com_tela.py` com o motivo
  de não terem tela.
- **Nenhum segredo entrou no repositório**: `google-services.json` e
  `GoogleService-Info.plist` estão no `.gitignore` e o que se versiona são
  EXEMPLOS de um projeto fictício (`nativo/exemplo/`), colocados por
  `nativo/scripts/firebase_config.sh`. A conta de serviço do FCM é variável
  do painel (`FIREBASE_SERVICE_ACCOUNT_JSON`), nunca arquivo.
- `minSdk` subiu de 24 para **26** (Android 8, 2017): exigência do
  `connect-client` do Health Connect.
- O build de **debug** ganhou `usesCleartextTraffic` para falar com o
  servidor de desenvolvimento; o **release não tem**.
