# Corrida V1 — a corrida não se perde

Spec escrita ANTES do código, para o resultado poder ser comparado com ela
depois.

## O que já existe, e não vai ser reescrito

Auditado em 04/09/2026. A Corrida não é esqueleto:

- **motor** (`workouts/corrida.py`): haversine, filtro de precisão (30 m),
  filtro de teleporte (12,5 m/s), piso de ruído (1,5 m), pace e parciais por km
  — cada limite com o motivo escrito ao lado;
- **model** (`workouts.Corrida`): `op_id` com constraint de unicidade por
  pessoa, `teve_lacuna`, parciais em JSON, e a decisão registrada de **não
  guardar o traçado** — coordenada diz onde a pessoa mora, e não há mapa que a
  use;
- **views**: histórico e salvamento, com o salvamento idempotente por `op_id` e
  validação no servidor;
- **tela**: começar, pausar, retomar, encerrar, com Wake Lock, `role="status"`
  para o leitor de tela, e detecção de lacuna quando a aba sai de vista;
- **47 testes**, e um roteiro de validação física em
  [`docs/prova-corrida-aparelho.md`](prova-corrida-aparelho.md);
- **análise técnica prévia** em [`docs/running-analise.md`](running-analise.md),
  que já decidiu o teto: PWA não tem geolocalização em segundo plano, e
  qualquer tela que diga "pode guardar o telefone" mente.

## O buraco

`static/js/corrida.js` não tem uma linha de `localStorage`, `indexedDB` ou fila
offline. A corrida inteira vive numa variável de JavaScript.

Duas consequências, e as duas perdem a corrida da pessoa:

1. **Recarregar a página, fechar a aba ou o navegador matar a página no meio da
   corrida apaga tudo.** Não há retomada.
2. **Se o `fetch` do salvamento falhar** — que é o caso comum, porque quem
   corre está na rua —, a tela diz "Não consegui salvar agora. Tente de novo
   com sinal.", os botões voltam ao início e **não existe "de novo"**. A
   corrida some.

E há um defeito latente que só apareceria quando alguém tentasse consertar o
item 2: o `op_id` é gerado **dentro de `salvar()`**. Um reenvio geraria chave
nova, e a constraint de unicidade — que existe justamente para impedir
duplicata — não seria acionada. A idempotência que o servidor oferece está,
hoje, inutilizada pelo cliente.

## O escopo da V1

**Uma frase:** uma corrida que aconteceu não pode desaparecer porque a página
recarregou ou o sinal caiu.

### 1. `op_id` estável, gerado no INÍCIO

Nasce junto com a corrida, não no salvamento. É a chave que faz reenvio ser
seguro, e ela precisa sobreviver a tudo o que a corrida sobreviver.

### 2. A corrida é gravada no aparelho enquanto acontece

Estado mínimo em `localStorage`, atualizado a cada leitura aceita: `op_id`,
início, distância, tempo em movimento, parciais, `teve_lacuna`, e se está
pausada.

Não é o traçado. **Nenhuma coordenada é gravada** — a decisão do model vale
igual no cliente, e gravar leitura de GPS no aparelho para "reprocessar depois"
seria contrabandear de volta o dado que o projeto recusou guardar.

### 3. Ao abrir a tela, uma corrida interrompida é oferecida de volta

Se houver estado guardado:

- **não terminada** → a tela oferece retomar ou encerrar e salvar o que já
  existe. Não retoma sozinha: a pessoa pode ter parado de correr há duas horas,
  e continuar contando o tempo inventaria duração;
- **terminada e não enviada** → tenta enviar de novo, e diz que está tentando.

### 4. Falha de rede não é fim de linha

Salvamento que falha guarda a corrida como pendente. Uma nova tentativa
acontece quando o evento `online` dispara e quando a tela é aberta. O `op_id`
estável garante que tentar duas vezes não cria duas corridas — o servidor já
devolve 200 com a corrida existente.

A mensagem muda junto: "Sem conexão. A corrida está guardada e vai subir quando
o sinal voltar" é diferente de "não consegui salvar", e a diferença é a pessoa
saber se perdeu ou não o que correu.

### 5. O estado guardado some quando deixa de fazer sentido

Depois de o servidor confirmar, o registro local é apagado. Um resto de corrida
antiga no `localStorage` reapareceria como oferta de retomada semanas depois.

## O que fica de fora da V1, e por quê

- **Mapa e traçado.** Exigem a decisão de cortar as pontas da rota antes de
  qualquer imagem ser compartilhável, e isso é produto, não persistência.
- **Quinta aba.** O contrato manda a Corrida continuar acessível por Treino →
  Corrida, e nada nesta fase muda isso.
- **Background Sync.** Não existe no Safari do iPhone, que é o alvo. O evento
  `online` é o mecanismo, e o Background Sync — se um dia — é bônus.
- **Cancelar com descarte confirmado.** A tela hoje não tem cancelar; encerrar
  com menos de um metro já não salva. Acrescentar um botão destrutivo numa tela
  usada correndo é decisão de UX que não cabe junto de uma mudança de
  persistência.
- **Integração nova com Progresso ou conquistas.** Já existe o que existe.

## Como isto vai ser provado

| o quê | como |
|---|---|
| cálculo, filtros, parciais | testes que já existem, mais os novos de persistência |
| `op_id` estável | teste que roda a corrida duas vezes e exige a mesma chave |
| retomada após reload | Agent Browser, com geolocalização simulada |
| falha de rede e reenvio | Agent Browser, derrubando a rede e voltando |
| não duplicar | teste do servidor, dois envios com o mesmo `op_id` |
| nenhuma coordenada gravada | teste que varre o `localStorage` depois de correr |
| GPS de verdade | **só aparelho físico** — `docs/prova-corrida-aparelho.md` |

Simulação de geolocalização **não** é prova de GPS físico, e o relatório final
vai separar as duas.
