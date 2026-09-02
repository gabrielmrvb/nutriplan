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
