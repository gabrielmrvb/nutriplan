# Corrida: o que dá para prometer numa PWA, e o que não dá

Análise técnica antes de escrever código. A pergunta que decide o escopo não é
"como implementar", é **o que o navegador entrega quando o telefone está no
bolso** — porque é assim que se corre.

## O limite que define o produto

Uma PWA não tem rastreamento em segundo plano. Não é limitação de esforço, é
ausência de API:

- **`watchPosition` só entrega posição com a página viva.** Quando a aba sai de
  vista o navegador suspende temporizadores; no Safari do iPhone, uma PWA
  minimizada ou com a tela bloqueada tem o JavaScript congelado.
- **Não existe Background Geolocation na web.** O que os apps nativos usam
  (`CLLocationManager` com `allowsBackgroundLocationUpdates`, ou o
  `FusedLocationProvider` num serviço de primeiro plano) não tem equivalente.
- **Background Sync não resolve.** Ele reenvia dado já coletado; não coleta.
  E não existe no Safari do iPhone — está no `CLAUDE.md` do projeto.

O projeto já esbarrou nisso: o Wake Lock do treino, em
`templates/workouts/routine.html`, **solta a trava quando a aba sai de vista**,
com o comentário explicando que o navegador solta sozinho. A corrida herda o
mesmo teto.

### A consequência honesta

Com a tela apagada ou o app em segundo plano, a corrida **perde trechos ou
para**. Qualquer tela que diga "pode guardar o telefone" estará mentindo.

Três respostas possíveis, e a escolha é de produto:

1. **Assumir o limite.** Wake Lock ligado, a tela fica acesa, e a interface diz
   isso na primeira vez: "deixe o app aberto; a tela fica acesa e o telefone
   gasta mais bateria". Honesto, funciona hoje, e é o único caminho que não
   depende de nada novo.
2. **Detectar as lacunas e admiti-las.** Registrar quando a página ficou oculta
   e marcar a corrida como "com trecho não registrado", em vez de desenhar uma
   linha reta entre dois pontos distantes — que inventaria distância.
3. **App nativo ou wrapper.** Fora do escopo desta fila e muda o produto.

**A 1 e a 2 se somam e são o MVP.** A 3 fica registrada como decisão futura.

## O que é independente dessa decisão

Dá para construir e provar sem resolver o item acima:

- **Distância** — haversine entre pontos consecutivos, com descarte por
  qualidade. Função pura, testável com coordenadas conhecidas.
- **Filtro de ruído** — GPS urbano oscila parado. Descartar ponto com
  `accuracy` acima de um limite, e trecho cuja velocidade implícita seja
  impossível (teleporte de 200 m entre duas leituras de 1 s).
- **Pace** — minutos por quilômetro, com a vírgula decimal e `tabular-nums` do
  projeto. Pace instantâneo oscila muito; média móvel é a leitura útil.
- **Splits por quilômetro** — o ponto exato de cada quilômetro cai entre duas
  leituras; interpolar ou atribuir ao ponto seguinte muda o número.
- **Pausa e retomada** — tempo parado não conta no tempo de corrida, e a
  distância entre a pausa e a retomada não conta como percurso.
- **Fila offline** — corrida acontece sem sinal. O app já tem `SyncedOperation`
  e uma fila em IndexedDB com `op_id`; salvar corrida precisa entrar nela com a
  mesma idempotência, senão o reenvio duplica a corrida.

## Privacidade — decisões antes de qualquer linha

Coordenada é dado sensível de um jeito diferente do resto do app: peso diz
quanto a pessoa pesa; rota diz **onde ela mora** e a que horas sai de casa.

- **Nunca em log.** Nem em log de erro, nem em mensagem de exceção, nem no
  Sentry se um dia existir. Ponto fixo.
- **Compartilhamento é o risco maior.** Uma imagem de rota que começa e termina
  na porta de casa publica o endereço. Se houver compartilhamento, o padrão
  precisa ser cortar as pontas — e o corte é decisão de produto, não default
  técnico.
- **Exclusão.** Toda FK para `User` neste projeto é CASCADE justamente para que
  apagar a conta apague o dado pessoal. Corrida e pontos seguem a regra.
- **Retenção do traçado.** Guardar cada leitura de 1 s de uma corrida de uma
  hora são 3.600 linhas. Vale decidir se o traçado guarda tudo ou uma versão
  simplificada — e isso é decisão de produto (fidelidade do mapa) com efeito
  em armazenamento.

## O que precisa ser medido no aparelho, e eu não consigo sozinha

Não é falta de tempo: é que o comportamento depende do sistema operacional, do
navegador e do estado de energia do telefone. Cada item abaixo é uma medição de
alguns minutos com o aparelho na mão:

1. Com a PWA aberta e a tela acesa por Wake Lock, `watchPosition` continua
   entregando durante quanto tempo?
2. Ao bloquear a tela, quantos segundos até parar de receber posição?
3. Ao voltar, ele retoma sozinho ou precisa de novo `watchPosition`?
4. Trocar de app por 30 s e voltar: quantas leituras se perdem?
5. Qual `accuracy` típica na rua onde a pessoa corre — 5 m ou 30 m? Isso decide
   o limite do filtro, e chutar o limite é chutar a distância.

## Recordes

"Recorde" precisa de definição antes de virar número: melhor pace de 1 km é
diferente de melhor pace médio de uma corrida de 1 km, e os dois são diferentes
de "melhor 1 km dentro de uma corrida longa". Sem escolher, a tela mostra três
coisas com o mesmo nome.

## O que NÃO entra

- Promessa de rastreamento com tela bloqueada.
- Mapa com serviço externo de tiles sem decidir o que vaza para o terceiro: um
  pedido de tile carrega a região da rota no `Referer` e no próprio endereço.
- Métrica fisiológica inventada — VO2máx estimado, "carga de treino",
  calorias de corrida por fórmula genérica. O app não tem frequência cardíaca.

## Importação de arquivo (decisão 4 da avaliação de UX, 20/09/2026)

A avaliação pediu: manter o registro à mão como caminho, **investigar
importação (arquivo GPX/TCX primeiro, depois Strava API) e implementar a de
arquivo**. Não investir em GPS ao vivo.

### O que foi implementado: GPX e TCX de arquivo

`workouts/importar_corrida.py` (puro) lê o `<trkpt>` do GPX e o `<Trackpoint>`
do TCX, devolve as leituras `{"lat","lon","t"}` que `workouts.corrida.percurso`
já consome, e a distância sai do MESMO motor que trata o GPS ao vivo — uma
leitura ruim é recusada aqui igual à da rua. `ImportarCorridaView`
(`/treino/corridas/importar/`) aplica os mesmos tetos do GPS e grava com
`origem="arquivo"`. Decisões tomadas, com a razão:

- **Parsing no servidor, e não no navegador.** O GPS ao vivo calcula no
  navegador de propósito (as leituras são o dado mais sensível). Mas o arquivo
  a pessoa ESCOLHEU subir; parsear XML no servidor é o caminho natural do
  upload, e não muda a superfície de privacidade — o arquivo já chega ao
  servidor.
- **`t` do arquivo, `duracao_s` = tempo decorrido (último − primeiro ponto).**
  Distinguir "tempo em movimento" de pausa é heurística específica de cada
  aparelho; inventar a nossa divergiria em silêncio do que o Strava/Garmin já
  mostrou à pessoa. Importado usa o tempo que o arquivo registra, e a régua de
  velocidade impossível continua valendo por cima.
- **O traçado NÃO é guardado.** Só distância, tempo, início/fim e parciais.
  Guardar as coordenadas do arquivo é a coleta que `Corrida` recusou por anos
  ("onde a pessoa mora"); dar mapa à corrida importada é outra fatia, com o
  corte das pontas da rota junto — não antes dele.
- **Idempotência pelo CONTEÚDO.** `op_id = "arq-" + sha256(arquivo)[:60]`:
  reimportar o mesmo arquivo cai no `UniqueConstraint(user, op_id)` e não
  duplica. Por pessoa, então duas pessoas podem importar o mesmo percurso.
- **Importada não se edita**, como o GPS: o percurso do arquivo contradiria
  números trocados à mão. `origem="arquivo"` (`workouts.0030`).
- **Segurança do XML sem dependência nova.** Não há `defusedxml` aqui. GPX/TCX
  nunca declaram DTD, então qualquer arquivo com `<!DOCTYPE`/`<!ENTITY` é
  recusado antes do parser — mata XXE e billion-laughs de uma vez. Teto de
  5 MB antes de ler.

### O que NÃO foi implementado: Strava API — e por quê

Investigada, não construída, e a razão é de credencial e de dono, não técnica:

- A Strava API é **OAuth 2.0**: o app precisa estar **registrado** no painel de
  desenvolvedor da Strava, o que gera um `client_id` e um `client_secret` —
  uma **credencial que não existe neste ambiente** (cai na condição de parada
  "precisa de credencial que não existe"). Registrar exige uma conta de
  desenvolvedor Strava, ou seja, **conta em serviço novo** — o que esta missão
  não faz.
- O fluxo seria: botão "Conectar Strava" → redirect para o `authorize` da
  Strava com escopo `activity:read` → callback grava o `refresh_token` da
  pessoa → `GET /api/v3/athlete/activities` lista as corridas → para cada uma,
  `GET /activities/{id}` traz distância, `moving_time`, `elapsed_time` e as
  splits. Os `streams` (latlng) dariam o traçado — que, pela decisão acima,
  continuaríamos NÃO guardando.
- **Limites do plano gratuito da Strava** (à data): ~100 req/15 min e
  1.000 req/dia por app, e as condições de uso da marca ("Powered by Strava",
  proibição de comparar atletas fora da plataforma, etc.). Nada disso
  impede — mas tudo isso é decisão do dono, junto com a credencial.
- **Custo/benefício:** a importação de arquivo já cobre Strava (exporta GPX),
  Garmin, Coros, Apple Saúde e Polar sem OAuth, sem credencial e sem depender
  da política de um terceiro. A API só acrescenta a comodidade de não baixar o
  arquivo — a um custo de credencial, conta nova e manutenção de OAuth.

**Recomendação:** manter a importação de arquivo como o caminho, e só abrir a
Strava API se o dono registrar o app (credencial) e aceitar os termos —
decisão dele, não da sessão.

### GPS ao vivo em segundo plano: continua fora

Sem mudança. A PWA não tem geolocalização com a tela bloqueada (ausência de
API, não de esforço), e a decisão da avaliação foi explícita: não investir
nisso. As medições de aparelho da seção anterior seguem pendentes.
