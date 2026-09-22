# O que só você (dono da conta) pode fazer — passo a passo

Escrito em 22/09/2026 (missão Capacitor). Cada item aqui **exige a sua
conta, o seu cartão ou um clique irreversível seu**. Tudo o que não exige
já está feito e provado — ver `achados/missao-capacitor-20260922.md`.

Faça na ordem: **1 e 2 destravam o Android inteiro; 3 a 6, o iOS.** O item
7 é o único que precisa dos dois.

---

## 1. Google Play Console — US$ 25, uma vez

1. Entre em `https://play.google.com/console` com a sua conta Google e
   pague a taxa única de **US$ 25**.
2. Escolha **conta pessoal** (a de empresa pede D-U-N-S). Conta pessoal
   criada de 2023 em diante precisa de **verificação de identidade** (foto
   de documento) e, antes de publicar, de **12 testadores por 14 dias** —
   comece isso cedo, é o que mais atrasa.
3. Crie o app: nome `NutriPlan`, idioma padrão **português (Brasil)**,
   tipo **aplicativo**, **gratuito**.
4. Me avise quando estiver criado: eu preencho a ficha da loja com
   `docs/loja/listagem.md`, subo as capturas e preencho o **Data Safety**
   com `docs/loja/privacidade-das-lojas.md`.

## 2. Assinatura do Android (keystore)

O Play exige o **Play App Signing**: o Google guarda a chave de assinatura
final e você sobe um `.aab` assinado com uma chave de upload.

- **Caminho fácil (recomendado)**: no Console, em *Configuração › Assinatura
  do app*, escolha "o Google gera a chave". Aí basta me dar o `.aab` sem
  assinatura de upload? **Não** — ainda é preciso uma chave de upload. Rode
  **uma vez**, nesta máquina:

  ```bash
  keytool -genkeypair -v -keystore ~/.nutriplan-secrets/upload.keystore \
    -alias upload -keyalg RSA -keysize 4096 -validity 10000
  ```

  Ele pede uma senha (escolha, anote no seu gerenciador; **não me diga**).
  O arquivo fica **fora do repositório** (o `.gitignore` já barra
  `*.keystore`), e é ele que assina todo envio daqui para a frente. Perder
  esse arquivo + senha significa não conseguir mais atualizar o app pela
  mesma listagem.

## 3. Apple Developer Program — US$ 99/ano

1. `https://developer.apple.com/programs/enroll/` com o seu Apple ID
   (ative a verificação em duas etapas antes).
2. Escolha **Individual** (a de organização pede D-U-N-S e leva semanas).
3. Pague os **US$ 99/ano**. A aprovação leva de horas a dois dias.

## 4. Identificadores na conta Apple (depois do item 3)

No `developer.apple.com/account`, em *Certificates, Identifiers & Profiles*:

1. **Identifiers › App IDs › +** → App → Bundle ID **explícito**:
   `com.nutriplan.app` (é o que o projeto já usa; mudar depois é criar
   outro app na loja). Marque as capacidades **HealthKit**, **Push
   Notifications** e **Sign In with Apple**.
2. **Keys › +** → marque **Apple Push Notifications service (APNs)** →
   baixe o `.p8` (**só dá para baixar uma vez**) e anote o *Key ID* e o seu
   *Team ID*.
3. **Keys › +** → marque **Sign in with Apple** → baixe o segundo `.p8`,
   anote o Key ID; e em *Identifiers › Services IDs* só é preciso criar um
   se um dia houver login com Apple na WEB (hoje não há).

## 5. Firebase — grátis, mas é a sua conta Google

`https://console.firebase.google.com` → **Adicionar projeto** (`NutriPlan`;
pode desligar o Google Analytics).

1. **Adicionar app Android**: pacote `com.nutriplan.app` → baixe
   `google-services.json`.
2. **Adicionar app iOS**: bundle `com.nutriplan.app` → baixe
   `GoogleService-Info.plist`.
3. *Configurações do projeto › Cloud Messaging › Apple app configuration*:
   suba o **`.p8` do APNs** do item 4.2 com o Key ID e o Team ID.
4. *Configurações do projeto › Contas de serviço* → **Gerar nova chave
   privada** → baixa um JSON. **Esse JSON é o segredo do servidor.**

Depois me entregue os três arquivos (pode ser por caminho local; eu não os
commito):

| arquivo | onde vai |
|---|---|
| `google-services.json` | `nativo/android/app/` (ignorado pelo git) |
| `GoogleService-Info.plist` | `nativo/ios/App/App/` (ignorado pelo git) |
| chave da conta de serviço (JSON) | variável `FIREBASE_SERVICE_ACCOUNT_JSON` no painel do Render (produção e staging) |

Enquanto esses três não existirem, o push nativo simplesmente não registra
token — o app funciona, e nada quebra.

## 6. Google Cloud — client IDs do login nativo (grátis)

O login com Google já funciona na web; o app precisa de mais dois client
IDs no **mesmo** projeto do Google Cloud que hoje atende
`GOOGLE_CLIENT_ID`:

1. `https://console.cloud.google.com/apis/credentials` → *Criar
   credenciais › ID do cliente OAuth*:
   - **Android**: pacote `com.nutriplan.app` + o **SHA-1** da chave de
     upload. Pegue assim:
     ```bash
     keytool -list -v -keystore ~/.nutriplan-secrets/upload.keystore -alias upload
     ```
   - **iOS**: bundle `com.nutriplan.app` → o client id que sair vai para a
     variável `GOOGLE_IOS_CLIENT_ID` no Render.
2. O `webClientId` que o app usa continua sendo o `GOOGLE_CLIENT_ID` de
   hoje (o do tipo *Web application*) — não troque.
3. Para o **Sign in with Apple**, defina no Render:
   `APPLE_CLIENT_ID=com.nutriplan.app` (o bundle é a audiência do token) e,
   se um dia houver fluxo web, `APPLE_TEAM_ID`, `APPLE_KEY_ID` e
   `APPLE_PRIVATE_KEY`.

## 7. Certificados, perfis e o envio (o clique final)

Com os itens 3 e 4 prontos, o build assinado do iOS sai do **Xcode em um
Mac** (ou do Xcode Cloud): esta máquina é Windows, e o `xcodebuild` do CI
constrói **sem assinatura**, só para o simulador. Você vai precisar de um
Mac (ou de um runner macOS com os seus certificados) para:

1. abrir `nativo/ios/App/App.xcodeproj`, escolher o seu Team em *Signing &
   Capabilities* (o Xcode cria o certificado e o perfil sozinho), e
   arquivar (*Product › Archive*);
2. subir para a App Store Connect (*Distribute App*);
3. preencher a ficha (eu deixo o texto pronto em `docs/loja/listagem.md`) e
   o **App Privacy** (`docs/loja/privacidade-das-lojas.md`);
4. criar uma **conta de demonstração** pelo cadastro público do app, com
   dados fictícios, e colocá-la em *Informações de login* — a Apple testa
   o fluxo real. **Nunca a sua conta pessoal.**
5. **Submit for Review** — o clique irreversível, que é seu.

No Android o mesmo, sem Mac: eu gero o `.aab` assinado com a chave de
upload do item 2 (`npm run android:release`), você sobe no Console, revisa
a ficha e clica em **Enviar para revisão**.

---

## Resumo do custo

| item | quanto | quando |
|---|---|---|
| Google Play Console | US$ 25 | uma vez |
| Apple Developer Program | US$ 99 | por ano |
| Firebase (FCM) | grátis | — |
| Google Cloud (client IDs) | grátis | — |
| Mac para arquivar o iOS | o que você já tiver, ou Xcode Cloud / um Mac emprestado | por envio |

Nada disso foi contratado: gasto é decisão sua, e a missão parou onde o
cartão começa.
