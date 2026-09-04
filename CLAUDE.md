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

**Água soma NO BANCO, não em Python.** `registro.ml = registro.ml + ml` seguido
de `save()` é leitura-modificação-escrita: dois toques rápidos leem o mesmo
valor e o segundo sobrescreve o primeiro. Tocar +250, +500 e +750 em sequência
dava 1000 em vez de 1500. Nenhum debounce no JavaScript conserta — o servidor
precisa estar certo com pedidos concorrentes, e a fila offline reenvia
exatamente assim, em rajada, quando a rede volta. Hoje é
`Least(F("ml") + ml, Value(10000))`, e há teste com threads reais.

**Idempotência é requisito da fila offline.** Água SOMA e suplemento ALTERNA —
as duas precisam de `op_id`. Marcação de refeição e carga de série usam
`update_or_create` e já são seguras; se alguém trocá-las por contador, a fila
quebra em silêncio.

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