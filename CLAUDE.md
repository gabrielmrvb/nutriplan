# NutriPlan — como este projeto funciona

PWA de dieta e treino em Django 5.2 + PostgreSQL. Uma pessoa, um plano, sem
conta compartilhada. Em produção: https://nutriplan-xxfn.onrender.com

## Trabalho em missão

Campanha, fase, bloco ou lote que termina em publicação: leia a skill
**`nutriplan-missao`** antes de editar. Ela traz o ciclo (planning →
decomposição → subagentes → integração → testes → browser QA → sabotagem →
suíte → deploy → smoke), quando avançar sozinho, e as condições exatas de
parada humana.

As outras quatro continuam valendo para o que decidem: `nutriplan-product`
(vale construir?), `nutriplan-architecture` (onde a regra mora?),
`nutriplan-ux` (como a tela funciona?) e `nutriplan-qa` (como provar?).

Pergunta pontual e ajuste de uma linha **não** precisam de protocolo.

## Rodar

```bash
.venv/Scripts/python.exe manage.py test          # suíte completa (~20 min)
bash scripts/instalar_hooks.sh                   # liga as travas de git
```

O PostgreSQL é portátil (`C:\Users\biel-\pgsql`, cluster em
`C:\Users\biel-\pgdata\nutriplan`) e **não sobe sozinho depois de reiniciar** —
`pg_ctl start` antes de qualquer coisa.

## Apps

| app | o que guarda |
|---|---|
| `accounts` | usuário, perfil, peso, dias de treino, `SyncedOperation` |
| `catalog` | alimentos e receitas (TACO/IBGE/USDA) |
| `plans` | motor nutricional, cardápio, hidratação, ofensiva, voz |
| `workouts` | ficha, cargas, assistente de ajuste, exportação de saúde |
| `supplements` | catálogo e checklist |
| `push` | service worker, manifesto, notificações |

## Decisões que já foram tomadas — não refaça sem motivo

**Sem framework de CSS.** Um arquivo, `static/css/app.css`, lido de ponta a
ponta, com seções numeradas. Tokens no topo. Nada de Tailwind, nada de build
step.

**`:has()` é proibido** para CSS estrutural. Já derrubou a navegação uma vez: o
navegador descarta a regra inteira quando não suporta, e o convite de instalação
cobriu a barra de abas. Use classe escrita pelo servidor.

**Alvo de toque: 44px de altura E de largura.** A régua mede as duas — 26px de
largura com 44 de altura já passou despercebido uma vez. Texto de interface
nunca abaixo de 11px.

**Número é `tabular-nums` e vírgula decimal.** O app é pt-BR: "62,50", não
"62.50". Passe por `floatformat` ou `number_format`.

**Nada rola na horizontal.** Todo container de texto leva `min-width: 0`.

**A ficha da semana desenha vários dias; o histórico só sabe de um.**
`load_history` devolve um balde `"hoje"` que é de HOJE. A tela da ficha aplicava
esse balde a TODAS as sessões, e um exercício anotado hoje aparecia como
concluído dentro do card de sexta, com as cargas preenchidas nas séries de lá.
`ExerciseLog` sempre teve a data certa — era a LEITURA que perdia o dia. Ao
mexer nessa tela, lembre: `"anterior"` vale para todos os dias (é o que se
consulta ao abrir outra ficha), `"hoje"` vale só para a sessão de hoje.

**Plano é retrato, não referência.** `NutritionPlan` e `TrainingPlan` guardam os
números do dia em que foram criados. Mudou a entrada, nasce plano novo — os
antigos ficam. Nunca edite os números de um plano ativo: `plan_is_current()`
compara com o que o motor calcula hoje e descarta o que não bate.

**Ficha ajustada não é remontada.** `TrainingPlan.customized_at` desliga o
gerador. Sem isso, mudar o horário de terça apaga a troca de ontem.

**A ofensiva mede aderência AO PLANO, e o denominador vem do plano.** Não do
que a pessoa marcou — essa era a regra antiga, e ela invertia o incentivo do
app: três refeições feitas mais duas marcadas como "comi outra coisa" davam
60% e quebravam a sequência, enquanto três feitas e duas SEM MARCAR NADA davam
100% e a mantinham. Registrar honestamente custava caro; omitir saía de graça.
A propriedade que governa isso agora tem teste próprio em `plans/test_streaks.py`:
**omitir nunca pode produzir resultado melhor que registrar**. Ela vale por
construção, porque qualquer denominador independente da marcação a satisfaz.

**Dois lados abrem o mesmo IndexedDB, e eles têm que concordar.**
`static/js/fila.js` e `templates/pwa/sw.js` abrem `nutriplan-fila`. O service
worker abria sem `onupgradeneeded`; quando ele chegava primeiro — num evento
`sync` —, o navegador criava o banco COM ZERO STORES, e daí em diante toda
gravação offline morria com `NotFoundError`, para sempre, porque a versão nunca
subia. Hoje os dois criam a store e declaram a MESMA versão; `push/tests.py`
compara os dois arquivos. Subir a versão é o que migra quem já tem o banco
quebrado — `deleteDatabase()` "resolveria" o console e jogaria fora a água que
alguém registrou no metrô.

**A fila offline drena na ORDEM DOS TOQUES, e ela não vem de graça.** A chave da
store é `op_id`, que é um `crypto.randomUUID()`, e o `getAll()` do IndexedDB
devolve por ordem de CHAVE — medido em navegador, 51,7% de inversão com duas
operações e 85,7% com três. Como somar, zerar e desfazer não comutam, isso muda
o resultado: `+500 → +500 → desfazer` termina em 500 e, drenado ao contrário, em
1.000. A ordem hoje vem de `seq`, um contador calculado como `maior + 1` DENTRO
da transação de escrita — 60 gravações concorrentes, zero empates, sem lock.
**Não use o `em: Date.now()` para isso**: 199 de 200 chamadas seguidas caem no
mesmo milissegundo, e com empate o `sort` estável devolve a ordem do UUID.
`emOrdemDeToque` e `corpoDoItem` existem IDÊNTICAS nos dois arquivos, e um teste
compara as duas.

**A drenagem PARA no primeiro item que ficou na fila.** Seguir em frente com o
anterior preservado desordena de um jeito que ordenar não conserta e que
sobrevive à drenagem. `fila.js` para seco porque `meus()` já filtrou um dono; o
`sw.js` trava POR DONO, porque drena fila de várias contas e um item estrangeiro
recusado com 503 não pode travar quem está logado — é por isso que
`push/test_replay.py` proíbe `break;` lá.

**A captura guarda PARES, não um objeto, e inclui o botão que enviou.**
`new FormData(form)` não traz o `<button>` do submit: o "Pulei" da refeição
mandava só o token e sumia em silêncio. E objeto colapsa chave repetida: "Comi
outra coisa" ia de três alimentos para um — o vazio, porque o último vence.

**Idempotência tem de cair junto com o efeito.** Este projeto não liga
`ATOMIC_REQUESTS`, então `ja_aplicada` commitava o `op_id` antes da escrita. Uma
falha no meio queimava o identificador sem aplicar nada, e o reenvio era
respondido com "já aplicada" — a fila apagava o item e o registro sumia.
`LogHydrationView.post` é transacional por isso.

**Água soma NO BANCO, não em Python.** `registro.ml = registro.ml + ml` seguido
de `save()` é leitura-modificação-escrita: dois toques rápidos leem o mesmo
valor e o segundo sobrescreve o primeiro. Tocar +250, +500 e +750 em sequência
dava 1000 em vez de 1500. Nenhum debounce no JavaScript conserta — o servidor
precisa estar certo com pedidos concorrentes, e a fila offline reenvia
exatamente assim, em rajada, quando a rede volta. Hoje é
`Least(F("ml") + ml, Value(10000))`, e há teste com threads reais.

**O total do dia e a composição dele são duas tabelas, e uma só é a fonte.**
`HydrationLog` guarda o total — é dele que leem a ofensiva, o histórico e a
tela Hoje. `GoleDeAgua` guarda a COMPOSIÇÃO, e só daqui para frente: não houve
backfill porque inventar de quantos goles os totais antigos foram feitos seria
fabricar dado. A consequência aparece na tela e está escrita nela: no dia da
virada a lista mostra uma linha "sem horário" com a diferença, para a soma
fechar com o painel. As duas escritas andam juntas dentro de `transaction`, nos
três caminhos — somar, desfazer e zerar. **Zerar apaga os goles do dia também**;
quando não apagava, a tela mostrava "Registrado 0 ml" com a lista cheia embaixo,
e "desfazer" continuava oferecido sem mover número nenhum.

**A água sobe no AGORA por ESTADO, não por relógio.** Ela era prioridade 4 —
aparecia depois de todas as refeições e do treino, ou seja, quando o dia já
tinha acabado. Hoje um ramo intermediário mede quanto a pessoa está atrás do
esperado PARA A HORA, e a janela do esperado é a do próprio plano: da primeira
refeição à última. Não há horário escrito à mão, e isso é a decisão — quem come
às 5h30 e às 19h tem outra janela, e um "7h às 22h" fixo estaria errado para
essa pessoa todos os dias. Beber **desliga o cartão na hora** — e só na hora: o
esperado cresce com o relógio mais depressa do que 500 ml movem o real, então
quem continua atrás o vê de novo umas duas horas depois. Medido numa janela de
7h às 20h com meta de 3 L, bebendo 500 toda vez que ele pede: **cinco aparições
no dia**. A primeira versão desta seção afirmava que ceder DESLIGAVA a regra, e
a simulação desmentiu — cadência de duas horas não é o mesmo que aparecer uma
vez. E ela não passa na frente de treino em andamento nem de refeição vencida:
aquilo tem hora marcada; sede não.

**O campo que diz para onde voltar é uma lista fechada.** `LogHydrationView`
aceita POST de qualquer sessão autenticada, e `?next=` livre seria
redirecionamento aberto. O pedido manda o NOME da tela, `DESTINOS` resolve, e o
que não estiver lá cai no destino padrão.

**Idempotência é requisito da fila offline.** Água SOMA e suplemento ALTERNA —
as duas precisam de `op_id`. Marcação de refeição usa `update_or_create` e já é
segura; se alguém a trocar por contador, a fila quebra em silêncio.

**A carga de treino NÃO entra na fila offline, e a frase acima já a incluiu.**
Ela dizia que `record_load` era segura por `update_or_create` — verdade do
SERVIÇO, falsa da VIEW, que envolve o serviço num laço mais um
`DELETE ... set_number__gt=N`. O formulário manda `series_feitas`, contador
derivado que a ficha só atualiza no sucesso; offline ele fica defasado por um,
sempre. Medido em `workouts/test_carga_fora_da_fila.py`: três séries a 40 kg
mais uma quarta a 50 com o contador antigo terminam em três séries a 50 — a
quarta some e o peso das anteriores é reescrito; com o contador em zero, o dia
daquele exercício é apagado. A rota saiu de `ROTAS` nos DOIS lados, item de
carga já gravado é DESCARTADO na drenagem, e a FICHA DA SEMANA avisa que a série
não foi salva em vez de fingir. A tela "Agora" não avisa — ela é POST de
formulário puro, sem JavaScript, e sem rede navega para a tela de offline; isso é
pré-existente e está no BACKLOG. É mitigação temporária: `CAMPANHA — CARGA
OFFLINE V2`.

**A SECRET_KEY não é gerada pela plataforma.** `generateValue: true` do Render
entrega 256 bits em base64 — 44 caracteres —, e o Django exige 50. Isso deixou
`security.W009` aceso em produção desde o primeiro deploy sem travar nada,
porque W é *warning* e o build reprova só em ERROR. Hoje é `accounts.E005`, e
derruba. A chave é definida à mão no painel; `DJANGO_SECRET_KEY_FALLBACKS`
existe só para a janela de troca, e sai da lista assim que as sessões antigas
expiram.

**Monitor externo bate em `/saude/vivo/`, nunca em `/saude/`.** As duas rotas
existem por causa desta diferença: `/saude/` é o readiness — consulta o
catálogo, e é o healthcheck do deploy. `/saude/vivo/` responde com ZERO
consultas. O banco no Neon hiberna após 5 minutos parado, e o plano gratuito dá
100 CU-horas por mês; a 0,25 CU sem hibernar dá 182, e a cota estoura por volta
do dia 16. Um monitor de 5 em 5 minutos em `/saude/` manteria o banco acordado
para sempre — o serviço que existe para melhorar a disponibilidade derrubaria o
banco no meio do mês. Em `/saude/vivo/` ele acorda o serviço web (que é o que
resolve o cold start de 50 s) e deixa o banco dormir.

**Log não guarda segredo nem dado de saúde.** `config/observabilidade.py` redige
token de redefinição (que anda **na URL**, e o logger de request grava caminho),
parâmetro de OAuth, chave de SMTP e URL de banco. `django.db.backends` fica em
WARNING até em DEBUG: consulta com parâmetro carrega e-mail e peso. Toda linha
leva o identificador do pedido, que também volta no cabeçalho `X-Request-ID` —
sem ele, "deu erro" e "fulano reclamou" nunca se encontram.
## Testes

Nome descreve o comportamento, não o método. Docstring diz **por que** aquilo
importa — de preferência com o caso real que motivou o teste.

Armadilha recorrente neste repositório: **o seletor do JavaScript e o marcador
do HTML são a mesma string.** `assertNotIn("data-x", html)` passa por acidente
porque `data-x` também está dentro do `<script>`. Ancore na classe
(`class="card resumo"`) ou no texto visível.

Contraste é medido, não julgado: `config.tests` recalcula a razão WCAG a partir
dos tokens, inclusive contra os fundos tingidos (`--brand-soft` e companhia).

## Limites reais deste ambiente

- **Node/npm/npx não estão instalados.** Nada de `npx`, Lighthouse, Playwright.
- **PWA não escreve no Apple Saúde nem no Health Connect** — não existe API web.
  `workouts/health_export.py` gera TCX para importar.
- **Background Sync não existe no Safari do iPhone.** O evento `online` é o
  mecanismo principal; o sync em segundo plano é bônus.
- **O serviço web gratuito do Render bloqueia saída SMTP nas portas 25, 465 e
  587.** O e-mail de produção usa a Brevo na **2525**, que negocia STARTTLS
  normalmente (TLSv1.3 confirmado no handshake). Isso custou caro para
  descobrir: o Django **captura** a falha de envio em `PasswordResetForm.save()`
  e registra `Failed to send password reset email` — a tela devolve 302 e diz
  "verifique seu e-mail" como se tivesse dado certo. Só o log denuncia, e antes
  de `config/observabilidade.py` não havia log. Se a recuperação de senha parar
  de novo, o primeiro lugar a olhar é o `TimeoutError` do socket, não o Django.
- **O banco saiu do Render e foi para o Neon em 01/09/2026.** Provado em 04/09
  pelo cabeçalho do dump daquele dia: servidor 16.9, e o Render rodava 18.4 —
  um cliente 16.9 não despeja um servidor 18.4. O banco do Render **é apagado
  por volta de 23/09/2026** (verbo do painel: *deleted*), e continua declarado
  no `render.yaml` de propósito: ele é o rollback. Se o plano gratuito do Neon
  tem prazo próprio, ninguém verificou — é uma olhada no painel dele.
  Ver **Backup e restauração** e [`docs/infra-recuperacao.md`](docs/infra-recuperacao.md).
## Deploy

`git push` dispara o Render. `scripts/build.sh` roda collectstatic →
`check --deploy` → migrate → os três seeds, com `errexit`: build que passa
prova que a migração rodou. Confira em `/saude/`.

O `check --deploy` vem **depois** do collectstatic e é um portão, não um aviso:
ele importa a URLconf, que resolve `static()` para o favicon em tempo de import,
e sem o manifesto isso estoura com um erro que não tem nada a ver com o que a
verificação veio checar. Com `--fail-level ERROR`, o que reprova ali não sobe —
hoje são e-mail de produção (`accounts.E001`–`E003`) e força da SECRET_KEY
(`accounts.E004`–`E006`).

## Backup e restauração

Procedimento completo, incluindo o que fazer se produção desaparecer, em
[`docs/infra-recuperacao.md`](docs/infra-recuperacao.md).

```bash
DATABASE_URL='...' scripts/backup.sh ~/backups-nutriplan   # tira e valida
BACKUP_PASSPHRASE='...' scripts/guardar.sh ~/backups-nutriplan/xxx.dump
BACKUP_PASSPHRASE='...' scripts/restaurar.sh ~/backups-nutriplan/xxx.dump.gpg
```

`guardar.sh` cifra em AES-256 e **decifra de volta conferindo o sha256** antes
de apagar o arquivo em claro. Sem isso um cifrado quebrado sobe verde e só se
revela inútil no dia em que alguém precisa dele.

`backup.sh` **recusa** gravar dentro de um repositório git: este repositório é
público, e o `.gitignore` registra duas vezes em que um `git add -A` trouxe
pasta inteira que não era para vir. E ele apaga o arquivo pela metade quando o
despejo falha — `pg_dump` cria o arquivo antes de terminar de escrevê-lo.

O `pg_dump` precisa ser **18 ou mais novo** — o cliente se recusa a despejar um
servidor mais novo que ele. No Windows os binários ficam em
`C:\Users\biel-\pg18\pgsql\bin`; os do 16 que vêm com outras ferramentas geram
um arquivo de zero byte.

`restaurar.sh` se recusa a apontar para qualquer host que não seja local, porque
ele começa apagando o banco de destino. Ele varre **toda** chave estrangeira
procurando órfã — não uma lista escrita à mão, que envelheceria na primeira
migration — e conta linhas sem nunca ler conteúdo: o dump tem e-mail, peso e
histórico de treino de gente real.

Um dump que ninguém restaurou é uma esperança, não um backup. Restaurar os 12 MB
deste banco leva 0,3 s: não há desculpa para pular o drill.

Para trocar de provedor de banco, `scripts/migrar.sh` faz dump, restore e
conferência tabela a tabela **num comando só** — o que importa aqui é o tempo
entre o dump e a troca da `DATABASE_URL`, porque tudo escrito na origem nessa
janela se perde. Ele conta linha de verdade, e não `n_live_tup`: num banco
recém-restaurado a estatística ainda é zero, e a comparação passaria comparando
nada com nada.

Nos três scripts a string de conexão vai em `-d`, nunca como argumento
posicional: posicional exige vir por último, e `pg_dump "$URL" -Fc` morre com
"too many command-line arguments" em cliente mais velho — no meio de uma janela
de manutenção, que é o pior momento para descobrir isso.

O destino precisa ser **PostgreSQL 17 ou mais novo**: o `pg_dump` 18 emite
`SET transaction_timeout`, parâmetro que só existe a partir do 17.