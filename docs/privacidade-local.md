# O que o NutriPlan guarda no aparelho

Auditoria de toda persistência do lado do cliente. A pergunta de cada linha é a
mesma: **se outra pessoa pegar este telefone depois do logout, o que ela
alcança?**

## Inventário

| store | o que guarda | privado | escrita pendente | sobrevive ao logout | decisão |
|---|---|---|---|---|---|
| `CACHE` (shell) | página offline, CSS e JS de `/static/` | não | não | sim | fica — é código, não dado |
| `CACHE_PAGINAS` | HTML de cada página navegada | **sim** | não | **não mais** | limpo no logout e em página anônima |
| IndexedDB `fila` | POSTs feitos sem rede: rota + campos do formulário | **sim** | **sim** | sim | separado por dono, nunca apagado |
| `localStorage` | uma chave: "dispensei o convite de instalação" | não | não | sim | fica — é preferência de tela |
| `sessionStorage` | não é usado | — | — | — | — |
| cookies | `sessionid` e `csrftoken` | — | não | `sessionid` não | gerenciados pelo Django |

## Cache de páginas

`/admin/` e `/gestao/` **nunca** entram. Mostram dado de outras pessoas e não
precisam de offline — a guarda está no `sw.js`, antes de qualquer estratégia,
e confere a origem.

As telas do app **entram**, e isso é o produto: a dieta de hoje abre no metrô.
O risco delas não é o cache existir, é ele sobreviver à sessão. Duas camadas:

1. **o clique em "Sair"** dispara a limpeza antes de o POST terminar. Se a rede
   cair no meio do logout, a sessão pode acabar no servidor sem a página
   seguinte chegar — e aí a camada 2 nunca rodaria;
2. **qualquer página renderizada sem sessão** limpa também. Cobre sessão
   expirada sozinha, logout em outra aba, cookie apagado.

O nome do cache é descoberto pelo sufixo `-paginas`, e não repetido no
JavaScript: duplicar a versão faria a limpeza apagar nada, em silêncio.

### O que nenhuma das duas cobre

Se o aparelho ficar **offline logo depois de a sessão expirar no servidor**,
nenhuma página anônima chega e o service worker não tem como saber que a
sessão morreu. As páginas guardadas continuam abrindo até a próxima navegação
online. Não há como resolver isso do lado do cliente sem inventar uma garantia
que a plataforma não dá.

## A fila offline

É o único store com **escrita pendente**: água, marcação de refeição e carga de
série que a pessoa registrou sem rede e que ainda não subiram.

O IndexedDB pertence ao navegador, não à sessão — a fila atravessa o logout
inteira. E ela drena sozinha no primeiro carregamento de página, com
`credentials: "same-origin"`, ou seja, na sessão de quem estiver logado agora.
Sem dono, o cliente SELECIONA a água que A marcou e a ENVIA com a sessão de B.

O que foi medido, e o que não foi. O envio está provado: o cliente publicado
monta e dispara o pedido de A dentro da sessão de B. A GRAVAÇÃO não está —
medido com a stack real e `enforce_csrf_checks`, o item carrega o
`csrfmiddlewaretoken` de quando foi enfileirado, `login()` chama `rotate_token`,
e o CSRF recusa antes da view. Não existe evidência de que uma operação de A
tenha chegado a virar linha na conta de B.

Corrigir o caminho do cliente continua valendo: uma proteção que só funciona
porque outra camada é atravessada primeiro não é desenho, é sorte. Mas a
afirmação honesta é "caminho de replay cross-account no cliente, sem efeito
provado", e não "vazamento consumado".

**A fila é separada por dono, e não esvaziada.** Apagar no logout resolveria o
vazamento e criaria outro problema: A perderia o que marcou sem rede. O que é
de A continua guardado, esperando A voltar.

O dono vem do `data-usuario` do `<body>` — a chave primária da própria conta,
que identifica a pessoa para o próprio JavaScript dela. Não autoriza nada: quem
autoriza continua sendo o cookie de sessão, do lado do servidor.

### Quarentena

Item enfileirado antes desta separação existir **não tem dono confiável**. Ele
não é enviado por ninguém e não é apagado:

- não enviar, porque não há como saber de quem é — e adivinhar é o vazamento
  que a separação existe para fechar;
- não apagar, porque pode ser água ou refeição que alguém marcou de verdade,
  sem rede.

A primeira versão desta correção ADOTAVA o item sem dono para quem estivesse
logado, com a justificativa de que a janela era curta. Janela curta para vazar
dado de outra pessoa continua sendo vazar. O fallback `(item.dono || eu) === eu`
foi removido: a única condição elegível é `item.dono === usuárioAtual`.

Quantos podem existir: no máximo os itens que estivessem pendentes no aparelho
de alguém no instante do deploy. A fila só enche sem rede e drena no primeiro
`online`, então o número esperado é zero ou próximo disso. O formato é o
antigo — `{op_id, url, dados, em}`, sem `dono`.

Não há tela para eles hoje, e criar um botão "recuperar" que peça à pessoa para
adivinhar de quem eram os dados seria trocar um problema por outro. Está no
backlog como RECUPERAÇÃO/EXPIRAÇÃO DE FILA OFFLINE LEGADA.

### Excluir a conta é diferente de sair

Sair guarda a fila para a volta. Excluir não tem volta: a conta que receberia
aquelas operações deixou de existir no servidor.

O gatilho é o SERVIDOR confirmando a exclusão, e não o clique em "Excluir" —
tentativa não é conclusão, e com o POST recusado por senha errada apagar a fila
teria perdido o que a pessoa marcou sem rede, com a conta ainda de pé. Também
não é "ficou anônimo": isso também acontece em logout normal, sessão vencida e
cookie perdido, e nos três a fila tem que sobreviver.

Depois do `delete()`, a view grava a chave primária apagada na sessão nova. A
tela de login lê e REMOVE — uma vez só — e o `<body>` carrega
`data-conta-excluida`. O JavaScript remove apenas os itens daquele dono: fila
de outra conta no mesmo aparelho e itens em quarentena ficam onde estão.

### O banco antigo abre sem migração

`dono` é propriedade do objeto guardado, não do schema: object store do
IndexedDB não declara colunas fora da chave. A versão continua 2, o `keyPath`
continua `op_id`, e o `onupgradeneeded` não apaga nada. Subir a versão sem
necessidade é que reintroduziria o `VersionError` que já aconteceu neste
arquivo, quando duas abas ficaram em versões diferentes.

## Cabeçalhos HTTP

Medido em produção, com sessão real:

- `/admin/…` → `no-cache, no-store, must-revalidate, private` (o `never_cache`
  que o Django Admin já aplica)
- `/gestao/…` → o mesmo, desde a correção desta rodada. Antes não respondia
  diretiva nenhuma
- telas do app → sem diretiva, e de propósito: o cache é o que faz o offline
  funcionar, o dado é da própria pessoa, e a separação entre contas é resolvida
  pela limpeza no logout

Todas respondem `Vary: Cookie`, que já impede um cache compartilhado de
entregar a página de uma conta para outra.

## Exportações

`/conta/exportar/` e `/treino/exportar/saude.tcx` não entram em
`CACHE_PAGINAS`: o worker só guarda `mode: "navigate"` e, fora disso, apenas
`/static/`. A exportação de dados é POST, e o worker ignora tudo que não é GET
já na primeira linha do `fetch`.

## Limitações medidas, não disfarçadas

### Outras abas continuam mostrando o que já estava na tela

Não existe `BroadcastChannel` nem ouvinte de `storage` no projeto — conferido
por varredura. Sair da conta numa aba não executa JavaScript nas outras.

O que a aba antiga ainda mostra é o HTML que já estava no DOM. Ela não ganha
acesso novo: qualquer navegação ou pedido cai em 302 para o login, e o cache de
páginas já foi apagado pela aba que saiu. É pixel velho, não porta aberta.

Implementar notificação entre abas é possível e não foi feito agora: mexeria no
comportamento de todas as telas para resolver um caso que não abre acesso.
Fica registrado como risco conhecido de navegador com várias abas.

### Sinal de exclusão que não chega a ser consumido

Se a pessoa fechar o navegador entre o `delete()` e a próxima tela, o sinal
morre com a sessão e a fila daquela conta fica órfã no aparelho.

O que isso NÃO é: vazamento. A fila órfã nunca drena, porque o dono dela não é
igual ao de ninguém que entre depois; nunca aparece no contador de outra
pessoa; e nunca é atribuída a ninguém. O que ela é: dado pessoal ocupando
espaço sem prazo.

Está no backlog como LIMPEZA/EXPIRAÇÃO DE FILAS ÓRFÃS.

### A fronteira da transação

`transaction.atomic` protege o banco. Sessão não participa dela — com
`ATOMIC_REQUESTS` desligado, o middleware grava a sessão depois da view, fora
da transação.

Por isso só o `delete()` fica dentro do bloco. Tudo abaixo do `with` só executa
se o commit passou. Falhou em qualquer ponto: a conta continua, a sessão
continua, a fila continua, e nenhum sinal definitivo é emitido.

Isso não é observável num `TestCase`, porque ali o teste inteiro roda numa
transação e o `atomic` da view vira savepoint — o rollback desfaz também o
flush da sessão, e o banco termina igual nas duas ordens. O que o teste afirma,
então, é a CHAMADA: com o `delete` falhando, o `logout` não chega a acontecer.

## O protocolo de replay, e três coisas que a medição corrigiu

O replay da fila é reconhecido por dois sinais: o cabeçalho `X-NutriPlan-Replay`
(protocolo novo) ou `op_id` no corpo (o que o cliente publicado já manda). O
cabeçalho `X-NutriPlan-Dono` declara para QUAL sessão a operação foi criada.

O dono é PRÉ-CONDIÇÃO, nunca endereço. O destino é sempre `request.user`. Buscar
o usuário pelo dono seria deixar o cliente escolher a conta, e há um teste que
proíbe `objects.get` dentro de `accounts/replay.py` por causa disso.

Replay legado — `op_id` sem dono — **não é recusado**. O cliente publicado não
conhece o cabeçalho, e recusá-lo quebraria a fila de quem ainda não recarregou a
página. Ele continua protegido pelo que sempre o protegeu: CSRF e sessão.
Aceitar o transporte legado não é adotar a propriedade do item.

### 1. A ordem das camadas não era a que eu documentei

Eu tinha escrito que o CSRF decide antes da barreira de identidade. Errado:
`CsrfViewMiddleware` valida em `process_view`, que roda depois da fase de
request de TODOS os middlewares. A barreira fala primeiro.

Consequência prática: com dono alheio, quem recusa é a barreira
(`replay_offline_de_outra_sessao`) nos dois clientes — não o CSRF. O CSRF decide
o que a barreira deixa passar, que é o cliente publicado.

### 2. O 302 de sucesso era indistinguível do 302 para o login

As views de escrita respondem com redirect quando dão certo — é post/redirect/get.
O cliente novo manda `redirect: "manual"` para que o 302 do `login_required` não
seja seguido até uma página 200 que ele leria como sucesso. Só que aí o 302 de
SUCESSO chega como `opaqueredirect`, sem status e sem destino: o item ficava na
fila para sempre, reenviado a cada carregamento.

O servidor traduz: para o protocolo NOVO, redirect vira `200 {"code":
"replay_processado"}`. "Processado" e não "aplicado" porque a view também
redireciona quando RECUSA o conteúdo — `/agua/` só aceita 250, 500 e 750. Sair da
fila é certo nos dois casos; dizer "aplicado" quando o servidor recusou não seria.

### 3. O worker se derrubava sozinho

`const db` declarado dentro do `try` ficava preso ao bloco. `removerDaFila(db,
…)` lançava `ReferenceError`, engolido pelo `catch` do laço — nenhum item saía da
fila —, e `db.close()` lançava solto, rejeitando `drenarFila()`. Como quem chama
é `event.waitUntil`, o Background Sync lia falha e REAGENDAVA: gravava, não
removia, tentava de novo.

Nunca chegou a produção. O teste que protege isso não lê strings: localiza a
declaração, descobre onde o bloco que a contém fecha, e exige que todo uso esteja
antes disso — com os comentários removidos antes da análise, porque a primeira
versão dele achou um `db.close()` dentro do comentário que explica o bug.

### O 503 não é erro de servidor

`django.request` loga qualquer 5xx como ERROR. Sem cuidado, cada replay
preservado viraria `ERROR Service Unavailable` no log — e o 5xx de verdade
ficaria escondido no meio deles. A resposta preservável é marcada com
`_has_been_logged`, o mesmo atributo que o Django usa para não logar duas vezes,
e registrada em INFO. Sem o caminho no log: `/refeicao/<id>/marcar/` carrega o id
do slot, e log de rotina não precisa dele.

### Por que o worker não ganhou um endpoint de CSRF

Ele não tem DOM nem `document.cookie`, então não consegue renovar o token. Um
endpoint só para isso seria superfície nova para um ganho que já existe: com o
token velho o servidor responde de forma preservável, o item fica, e a próxima
abertura do app sincroniza pelo `fila.js`, que tem o token atual. O worker
adianta o que dá e não perde nada — e o Background Sync nem existe no Safari do
iPhone, que é o alvo principal deste app.
