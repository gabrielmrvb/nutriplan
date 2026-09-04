# A Corrida como app nativo — a fronteira, e por que ela fica onde fica

Este documento responde uma pergunta só: **como um cliente mobile nativo coexiste
com o NutriPlan Django server-rendered sem destruí-lo?**

A resposta curta é que ele **não embrulha o site**. A longa está abaixo, e o
motivo é medido, não estético.

Nada aqui está provado em aparelho. Onde a fonte é documentação, ela está
citada; onde é medição, está dito que foi medida.

---

## 1. Por que "embrulhar o site" não é uma opção — e a medida que fecha isso

A tentação óbvia é um WebView apontando para `nutriplan-xxfn.onrender.com` com
um plugin de GPS por cima. Isso morre num detalhe documentado pelos próprios
plugins de background geolocation:

> "After 5 minutes in the background Android will throttle HTTP requests
> initiated from the WebView."

O requisito inegociável é correr **10+ minutos com a tela bloqueada**. Um
cliente que envia ponto por `fetch()` de dentro do WebView **para de enviar na
metade do teste** — e pior, para em silêncio: o JavaScript não recebe erro
distinguível de "rede ruim".

Some-se o que a Apple faz do outro lado: o sistema suspende o app, **enfileira**
as atualizações de localização e as entrega quando o app volta a rodar, e pode
**encerrar o app a qualquer momento** para liberar memória.

As duas coisas juntas dizem a mesma frase: **o registro da corrida não pode
depender do WebView estar vivo e com rede.** Ele tem de acontecer do lado
nativo, em armazenamento nativo, e subir em lote.

Isso não é preferência de arquitetura. É o teto das duas plataformas.

---

## 2. A fronteira

### Django é dono de

| responsabilidade | onde já mora hoje |
|---|---|
| autenticação de cliente que não é navegador | `accounts.TokenDeApp`, `api/auth.py` |
| limite de tentativas de entrada | `accounts/entrada.py` |
| persistência da atividade | `workouts.Corrida`, `workouts.TracoDaCorrida` |
| **o motor autoritativo** | `workouts/corrida.py` |
| regras de plausibilidade (teto de distância e duração) | `workouts/corrida_views.py`, reusadas em `api/views.py` |
| idempotência e conflito | `UniqueConstraint(user, op_id)` + o 409 de `api/views.py` |
| ownership | filtro por `request.dono`, 404 e não 403 |

### O cliente nativo é dono de

| responsabilidade | por quê não pode ser do servidor |
|---|---|
| aquisição de GPS | é sensor, e só o SO entrega |
| execução com a tela bloqueada | foreground service / background modes |
| estado da corrida em andamento | a corrida acontece sem rede |
| armazenamento durante a atividade | o app pode ser morto no meio |
| tela da corrida | precisa responder sem ida ao servidor |
| mapa e compartilhamento | share sheet é API do SO |

### O que NÃO muda

O produto web continua exatamente como está. `SalvarCorridaView`,
`static/js/corrida.js`, os templates e o service worker seguem servindo a PWA
publicada. **A API é acrescentada ao lado, não no lugar.** Nenhuma tela web
precisa virar SPA para o mobile existir, e nenhuma rota web muda de contrato.

Corrida gravada pela PWA continua válida — ela simplesmente não tem traçado, e
`tem_traco` no detalhe da API diz isso sem que o cliente precise adivinhar.

---

## 3. Fonte da verdade das métricas

**O servidor é autoritativo. Sempre, quando há pontos.**

Já é o comportamento implementado: em `api/views.py`, quando o corpo traz
`pontos`, o `distancia_m` que o cliente mandou é **ignorado** e o número gravado
sai de `workouts/corrida.py`. O comentário no código diz por quê — "é o que tira
a distância do lado que a pessoa controla".

| métrica | autoritativo | ao vivo (provisório) |
|---|---|---|
| distância | servidor, haversine sobre pontos aceitos | cliente |
| pace médio | servidor, derivado | cliente |
| duração em movimento | cliente informa, servidor valida contra o teto | — |
| filtro de precisão | servidor, `PRECISAO_MAXIMA_M` | cliente pode espelhar |
| corte de teleporte | servidor, `VELOCIDADE_MAXIMA_MS` | cliente pode espelhar |
| parciais | servidor | cliente |
| percurso | servidor guarda os aceitos | cliente desenha os brutos |

### A regra que evita dois motores divergentes

O cliente **pode** calcular durante a corrida — sem isso a tela não tem o que
mostrar enquanto não há rede. O que ele não pode é *publicar* esse número como
final.

Contrato de nomenclatura: o que o cliente calcula ao vivo é **provisório**, e a
tela pode dizê-lo. O que volta do `POST /api/v1/corridas/` é **final**, e
substitui o provisório na hora em que chega. Quando os dois divergirem, o do
servidor vence e nenhum aviso é necessário — divergir é esperado, porque o
servidor descarta leituras que o cliente mostrou.

Se algum dia o cliente precisar do número exato offline, a saída **não** é
reimplementar o motor em JavaScript ou Kotlin: é portar `corrida.py` uma vez,
com os mesmos casos de teste, e tratar qualquer divergência como defeito. Hoje
isso não é necessário e por isso não foi feito.

---

## 4. O modelo de dados de GPS

Guardado hoje, em `TracoDaCorrida`:

| campo | por quê |
|---|---|
| `lat`, `lon` | sem isso não há mapa nem compartilhamento |
| `t` | ordem e parcial dependem do tempo |
| `accuracy` | é o que explica um trecho descartado |
| `acumulado_m` | evita repetir haversine para redesenhar parciais |
| `descartadas` (contagem) | explica um mapa com buraco — sem ele, rua sem sinal parece defeito de desenho |

**Não guardado, e cada ausência é uma decisão:**

- **leituras recusadas pelo motor** — são justamente as de precisão ruim e as de
  teleporte. Guardá-las é mais coordenada para desenhar um mapa pior;
- **altitude** — o GPS de celular erra mais na vertical que na horizontal, e não
  há tela que use ganho de elevação. Entra quando a tela existir;
- **speed do sensor** — derivável de dois pontos, e uma segunda cópia do mesmo
  fato é uma cópia para ficar errada;
- **rumo, satélites, provider** — nenhum tem consumidor.

O preço já está declarado no model: mudar `PRECISAO_MAXIMA_M` **não** recalcula
corrida antiga, porque a leitura que o filtro novo aceitaria não existe mais.
Recalcular parcial em outra distância continua possível.

---

## 5. A máquina de estados, e onde ela mora

A corrida em andamento é **estado do cliente**. O servidor só conhece corrida
terminada — e isso é o desenho, não uma lacuna.

```
              (não existe)
                   │  o usuário toca "iniciar"
                   ▼
              ATIVA ──────────► PAUSADA ──┐
                   │  ▲                   │
                   │  └───────────────────┘
                   │  o usuário encerra
                   ▼
            ENCERRADA_LOCAL   ← sobrevive a app morto: está no disco
                   │  há rede
                   ▼
            SINCRONIZANDO
                 │     │
        2xx      │     │  409
                 ▼     ▼
          SINCRONIZADA  CONFLITO (terminal, reporta)
```

`5xx` e falha de rede **não** são estado: voltam para `ENCERRADA_LOCAL` e tentam
depois. Só isso já dá a recuperação de crash — se o app morrer em `ATIVA`, o que
está no disco é uma corrida `ATIVA` com pontos, e a retomada oferece encerrá-la.

**Estados impossíveis que o desenho torna difíceis de representar:**

- não existe "sincronizada mas sem `op_id`": o `op_id` nasce **antes** do
  primeiro ponto, no aparelho;
- não existe "duas corridas ativas": o registro ativo é único no armazenamento
  local, por construção;
- não existe "sincronizada e depois modificada": o servidor recusa conteúdo
  divergente com 409, e o primeiro envio vence.

---

## 6. Offline-first, e por que o envio é no fim

O enunciado do produto é explícito: começar online, perder sinal, correr 40
minutos, terminar offline, sincronizar depois.

Logo: **a corrida inteira vive local, e sobe numa operação só.** Não há envio
incremental durante a atividade, e isso é decisão com três razões:

1. envio incremental exige rede durante a corrida — exatamente o que não se pode
   supor;
2. no Android, o WebView é estrangulado depois de 5 minutos em background;
3. uma corrida de duas horas a 1 Hz são ~7.200 pontos, e isso **cabe em 1 MB** —
   o limite que `api/auth.py` já impõe. O caso normal não precisa de fatiamento.

O que fica em aberto, declarado: corrida acima de ~1 MB de pontos seria recusada
com 413. Isso é ~3 h a 1 Hz. Quando existir usuário que corra isso, a saída é
reduzir a taxa de amostragem no cliente antes de fatiar o upload — menos pontos
descrevem a mesma rota, e fatiar introduz estado parcial no servidor, que é
justamente o que a seção 5 evita.

### Idempotência

Já implementada e testada: `UniqueConstraint(user, op_id)`, reenvio idêntico
devolve 200 com a mesma corrida, reenvio divergente devolve **409 terminal**.
A regra da fila é `2xx` apaga, `409` apaga e reporta, `5xx` mantém.

O `op_id` é por **pessoa**, não global: dois aparelhos sorteando o mesmo
identificador geram duas corridas, e é o correto — são duas pessoas.

---

## 7. GPS em background: o caminho de cada plataforma

### Android — e a decisão que evita o formulário do Google Play

A documentação do Android classifica **foreground service** como localização de
*primeiro plano*, e cita a tela apagada literalmente:

> "Your app is running a foreground service. [...] Your app retains access when
> it's placed in the background, such as when the user presses the Home button
> on their device or **turns their device's display off**."

Consequência: uma corrida iniciada com o app visível, que sobe um foreground
service do tipo `location`, **continua recebendo posição com a tela bloqueada
sem pedir `ACCESS_BACKGROUND_LOCATION`**.

Isso remove um bloqueio inteiro. Pedir `ACCESS_BACKGROUND_LOCATION` obrigaria a
preencher o *Permissions Declaration Form* do Play, cujo critério de revisão
pergunta exatamente "o app poderia entregar a mesma experiência sem acessar
localização em background?" — e no nosso caso a resposta é sim.

Exigências que ficam: `FOREGROUND_SERVICE_LOCATION` e
`foregroundServiceType="location"` (API 34+), `ACCESS_FINE_LOCATION` em runtime,
`POST_NOTIFICATIONS` (API 33+) para a notificação persistente.

### iOS

Capacidade *Background Modes → Location updates* (`UIBackgroundModes` com
`location`), `allowsBackgroundLocationUpdates = true`, e as duas *purpose
strings*. A doc da Apple avisa que ligar a flag **sem** a chave no `Info.plist`
é erro fatal que encerra o app.

O indicador azul aparece e não é removível. Isso é conteúdo de UX, não defeito.

E o ponto arquitetural: o sistema **enfileira** atualizações enquanto o app está
suspenso e as entrega em lote depois, e pode encerrar o app a qualquer momento.
Um cliente que suponha entrega contínua e em ordem perde dado por desenho.

---

## 8. A fronteira do plugin — nosso contrato, não o deles

A lógica de domínio **não** entra no plugin. O app fala com uma interface nossa:

```
iniciar(opcoes) -> sessao
sessao.onPonto(cb)     # {lat, lon, t, accuracy}
sessao.pausar() / retomar()
sessao.encerrar() -> [pontos]
```

Por trás dela fica o plugin escolhido. Trocar de plugin passa a ser reescrever
um adaptador, e não o app.

Isso importa porque a escolha do plugin **ainda não está fechada** e envolve
dinheiro:

| plugin | licença | custo | estado |
|---|---|---|---|
| `@capacitor/geolocation` (oficial) | MIT | grátis | **não serve** — a doc diz: "This Capacitor plugin does not support background geolocation directly" |
| `@capgo/background-geolocation` | MPL-2.0 | **grátis** | ativo, `@capacitor/core >=8` |
| `@capacitor-community/background-geolocation` | MIT | grátis | `peerDependencies ^3.1.1`, sem push há ~1 ano |
| `@transistorsoft/...` | proprietária | **US$ 399+** para release; debug grátis | o mais completo |
| Capawesome | proprietária | **US$ 99/mês ou 1980 one-time**; sem caminho grátis | — |

Com a abstração no lugar, dá para começar pelo gratuito e trocar sem reescrever
o produto. **Nenhuma compra foi feita, e nenhuma é necessária para provar o
requisito**: o Transistorsoft é funcional em build de debug sem licença.

---

## 9. Mapa e compartilhamento — critério, não escolha ainda

Não há provedor escolhido, e escolher agora seria escolher sem o dado que
importa. Os critérios ficam registrados:

- **custo e licença** — mapa cobrado por carregamento é custo por corrida
  aberta, o que cresce com o uso do produto;
- **offline** — o resumo precisa desenhar sem rede;
- **lock-in** — o traçado é nosso e fica em `TracoDaCorrida`; o mapa desenha
  por cima. Trocar de provedor não pode exigir migrar dado.

Para o compartilhamento, a arquitetura já permite o que interessa: o resumo é
derivável de `Corrida` + `TracoDaCorrida`, e o share sheet nativo recebe uma
imagem. **Instagram não é requisito** — é um destino a mais do mesmo share
sheet.

E a decisão de privacidade que vem junto, registrada desde antes: **cortar as
pontas da rota**. Uma imagem que começa e termina na porta de casa publica o
endereço. O corte opera só sobre `TracoDaCorrida`, sem tocar em `Corrida` — que
é exatamente o motivo de serem duas tabelas.

---

## 10. Privacidade

- o traçado é o dado mais sensível do app, e mora numa tabela que pode ser
  apagada sozinha;
- `CASCADE` a partir da corrida, que é `CASCADE` a partir do usuário: excluir a
  conta apaga o percurso. Há teste;
- a **lista** nunca devolve coordenada; só o detalhe, e só para o dono;
- ninguém alcança o traçado alheio — 404 e não 403, porque 403 confirmaria que a
  corrida existe;
- coordenada nunca entra em log. `config/observabilidade.py` já redige segredo e
  dado de saúde, e o traçado não passa por parâmetro de URL.

O que **não** está feito e não é fingido: política de retenção, corte das pontas
da rota, e ocultar região próxima de casa. A arquitetura deixa os três
possíveis; nenhum está implementado.

---

## 11. O que bloqueia, e o que não bloqueia

**Bloqueia (humano):** Mac com Xcode para iOS · aparelho físico para o teste de
tela bloqueada · Apple Developer (US$ 99/ano) · Play Console (US$ 25) · 12
testadores por 14 dias para produção no Play · licença de release se o plugin
escolhido for pago.

**Não bloqueia:** tudo do lado servidor — modelo, API, motor, idempotência,
conflito, ownership, testes. É onde esta campanha trabalhou.

Neste ambiente não há `node`, `npm`, `java`, `gradle`, `adb` nem `xcodebuild`:
o projeto Capacitor **não pode ser criado aqui**. Isso é limitação de ambiente,
não decisão de arquitetura, e está dito para não ser descoberto depois.
