# Onde o banco mora, e como trazê-lo de volta

Documento operacional. Serve para duas situações: a rotina de guardar uma
cópia, e o dia em que o banco de produção não existe mais.

Ele é curto de propósito. Procedimento longo não é lido no dia em que precisa
ser lido.

## Onde o banco está

**Neon**, desde 01/09/2026. Antes disso era o PostgreSQL do próprio Render.

Como isso foi verificado, e não presumido: o dump de 01/09 às 16:09 declara
`Dumped from database version: 16.9`, e o banco do Render rodava 18.4 — um
cliente 16.9 se recusa a despejar um servidor 18.4, então aquele dump não pode
ter vindo do Render.

A `DATABASE_URL` vive **só no painel do Render**, com `sync: false` no
`render.yaml`. Isso não é detalhe: o serviço é "Blueprint managed", e um
`fromDatabase` ali seria uma ORDEM para o Render devolver a URL ao banco antigo
na próxima sincronização — sem erro, sem log, sem ninguém pedir.
`BancoDoBlueprintTests` existe para isso.

O banco antigo do Render **continua declarado** no `render.yaml`, e também de
propósito: ele é o rollback. Apagar a declaração faria o Render removê-lo na
sincronização seguinte. Ele expira sozinho por volta de **23/09/2026**.

> **Não verificado por mim:** se o plano gratuito do Neon tem prazo próprio de
> expiração. O painel do Render foi lido em 31/08/2026 e diz 23/09 para o banco
> DELE. Sobre o Neon, o que está registrado no projeto é que o plano gratuito
> dá **um** slot de snapshot manual e PITR de 6 horas. Confirmar a política de
> retenção da conta é uma olhada no painel do Neon, e é sua.

## Como guardar uma cópia

Duas rotas. As duas terminam num arquivo `.gpg` que só abre com a senha.

### Rota A — na sua máquina (menor superfície de ataque)

O segredo nunca sai daqui. O preço é depender de a máquina estar ligada.

```bash
cd ~/nutriplan-infra
export PATH="$HOME/pgsql/bin:$PATH"
DATABASE_URL='<a URL do painel do Render>' \
  BACKUP_PASSPHRASE='<senha longa, guardada no gerenciador de senhas>' \
  bash -c 'scripts/backup.sh ~/backups-nutriplan && \
           scripts/guardar.sh ~/backups-nutriplan/nutriplan-*.dump'
```

O `backup.sh` **recusa** gravar dentro de um repositório git — este repositório
é público, e um dump é dado de saúde. Se precisar mesmo (checkout descartável
de CI), `PERMITIR_NO_REPO=1`.

### Rota B — GitHub Actions

`.github/workflows/backup.yml`, botão "Run workflow". Ele despeja, criptografa,
**prova que o cifrado decifra** e sobe como artefato com retenção de 14 dias.

Exige dois segredos no repositório:

| segredo | o que é |
|---|---|
| `DATABASE_URL` | a string de conexão do banco de produção |
| `BACKUP_PASSPHRASE` | senha longa e aleatória, guardada **fora** do GitHub |

O custo em risco está escrito no cabeçalho do próprio arquivo: a partir daí a
`DATABASE_URL` existe num lugar a mais. O fluxo não tem gatilho de
`pull_request`, o token é somente leitura e o dump em claro nunca toca o
checkout — mas o risco não some, ele diminui.

O agendamento diário está **comentado**. Ligá-lo é uma decisão sua.

## Frequência, retenção e onde a cópia fica

| | Rota A (máquina) | Rota B (GitHub) |
|---|---|---|
| quando | quando você rodar | manual; diário se descomentar o `schedule` |
| onde | `~/backups-nutriplan` | artefato do Actions |
| retenção | você decide | 14 dias |
| criptografia | AES-256 pelo `guardar.sh` | a mesma, o mesmo script |
| integridade | `SHA256SUMS` ao lado | `SHA256SUMS` sobe junto |

**Nenhuma das duas basta sozinha.** A da máquina morre com o disco; a do GitHub
some em 14 dias. Uma cópia mensal levada para um terceiro lugar — pendrive,
outro provedor — é o que cobre o caso de perder as duas.

## Como restaurar

Um comando. O script aceita o `.gpg` direto e nunca escreve fora de um banco
descartável.

```bash
cd ~/nutriplan-infra
export PATH="$HOME/pgsql/bin:$PATH"
BACKUP_PASSPHRASE='<a senha>' \
  scripts/restaurar.sh ~/backups-nutriplan/nutriplan-AAAAMMDD-HHMMSS.dump.gpg
```

Ele confere o sha256, decifra num temporário que some no fim, verifica se o
cliente consegue LER o arquivo, restaura num banco chamado `nutriplan_drill`,
imprime schema e contagens (**sem ler nenhuma linha de dado**), varre toda
chave estrangeira procurando órfã, e apaga o banco de teste.

Se ele disser que o cliente não lê o arquivo: quatro dos backups desta máquina
foram escritos por um `pg_dump` 18 e exigem um `pg_restore` 18. A mensagem diz
o caminho — nesta máquina, `~/pg18/pgsql/bin`.

## Se produção desaparecer

Nesta ordem.

1. **Não mexa em nada ainda.** Confirme que sumiu: `/saude/vivo/` responde sem
   banco, e `/saude/` responde com. Se o primeiro está de pé e o segundo caiu,
   o problema é o banco.
2. **Descubra a cópia mais nova.** `ls -la ~/backups-nutriplan` e os artefatos
   do último `Backup do banco` no Actions. Pegue a mais recente das duas.
3. **Prove que ela presta ANTES de criar qualquer coisa.** Rode o
   `restaurar.sh` acima, contra o Postgres local. Se ele falhar, tente a cópia
   anterior — descobrir isso agora é muito melhor que no meio da recriação.
4. **Crie o banco novo.** No Neon ou onde for. Anote quanto dado se perdeu:
   é a distância entre o carimbo do dump e agora.
5. **Restaure nele.** `FORCA=1` é obrigatório para alvo não-local, e existe
   exatamente para você ter que digitar que sabe o que está fazendo:

   ```bash
   FORCA=1 BACKUP_PASSPHRASE='<a senha>' \
     scripts/restaurar.sh <o arquivo> '<URL do banco NOVO e vazio>'
   ```

6. **Troque a `DATABASE_URL` no painel do Render.** Só no painel — nunca no
   `render.yaml`, pelo motivo explicado lá em cima.
7. **Rode as migrations e confira:** `python manage.py migrate` e depois
   `/saude/`, que devolve as contagens do catálogo.
8. **Registre no BACKLOG** o que aconteceu e quanto se perdeu.

## O que é perigoso

- **Restaurar por cima de produção.** O `restaurar.sh` APAGA o banco de destino
  antes de restaurar. Ele se recusa a apontar para host não-local sem `FORCA=1`,
  e essa recusa existe para ser respeitada.
- **Pôr `fromDatabase` de volta no `render.yaml`.** Devolve a produção ao banco
  antigo em silêncio.
- **Apagar o bloco `databases:` do `render.yaml`.** Remove o rollback.
- **Rodar `backup.sh` dentro do repositório.** Ele recusa; não contorne com
  `PERMITIR_NO_REPO=1` fora de CI.
- **Passar a URL do banco como argumento para `pg_dump`/`psql` na mão.** Os
  scripts tiram a senha da URL e a entregam por `PGPASSWORD` justamente porque
  argumento aparece em `ps`. Um comando digitado direto no terminal não tem
  essa proteção.
- **Guardar a `BACKUP_PASSPHRASE` junto do backup.** Sem ela o arquivo não é
  nada; com ela ao lado, a criptografia também não é.
- **Confiar num backup que ninguém restaurou.** É a regra que originou estes
  scripts, e ela vale para o `.gpg` também.

## O que ainda não está resolvido

- O fluxo do GitHub **nunca rodou** — `total_count: 0` na API em 04/09/2026.
  Enquanto isso for verdade, não existe cópia fora desta máquina.
- Os backups em `~/nutriplan-backups` e `~/backups-nutriplan` estão **em claro**.
  Cifrá-los com `guardar.sh` é um comando por arquivo.
- Duas pastas com nomes quase iguais (`backups-nutriplan` e `nutriplan-backups`)
  convidam ao engano no pior momento. Vale unificar.

## Mover o banco para o Neon São Paulo — procedimento, NÃO executado

Escrito em 21/09/2026 a pedido do dono, depois da pesquisa legal (LGPD:
hospedar dado de saúde nos EUA é transferência internacional sem decisão de
adequação — só a União Europeia tem uma, Res. CD/ANPD 32/2026 — e sem
cláusula-padrão brasileira aprovada). Guardar o dado em repouso no Brasil
reduz o que cruza a fronteira; **não elimina**, porque o serviço web
continua em Oregon e processa tudo.

**O que foi conferido na fonte (21/09/2026):**

- O Neon tem a região **AWS South America (São Paulo), `aws-sa-east-1`**
  (https://neon.com/docs/introduction/regions), "generally available" desde
  o changelog de 28/02/2025, "to keep your data within Brazil"
  (https://neon.com/docs/changelog/2025-02-28).
- A região é escolhida **na criação do projeto** e **não pode ser trocada**:
  "You cannot change the region for an existing project. If you need your
  data in a different region, you create a new Neon project in that region
  and migrate your database there" (mesma página de regiões).
- O plano **Free** dá 100 projetos, 0,5 GB e 100 CU-h por projeto, com
  suspensão após 5 min (https://neon.com/docs/introduction/plans), e a
  documentação **não restringe região por plano** — nenhuma linha de
  "regiões" na tabela de planos, nenhuma ressalva na página de regiões.
  **Não vi o menu do console**: a confirmação definitiva é abrir "New
  project" na conta do dono e ver São Paulo na lista — um clique seu.
- A produção está hoje em **`us-west-2` (Oregon)**, lido do host da
  `DATABASE_URL` no Render (só a região; nada mais foi impresso) — a mesma
  região do serviço web.

**Por que NÃO executar antes de medir — a conta que decide:** o serviço web
fica em Oregon (o Render não tem região no Brasil:
https://render.com/docs/regions). Hoje web e banco estão no mesmo data
center, e cada consulta paga menos de 1 ms de rede. Oregon–São Paulo são
~10.500 km de grande círculo; a luz na fibra anda ~200 km/ms, então o piso
FÍSICO da ida e volta é ~105 ms, e rotas reais ficam em 170–200 ms
(não medido daqui — é o primeiro passo abaixo). A Home faz até **41
consultas** (`CLAUDE.md`, "O pre-push testa o commit que sobe"), em série:
41 × 105 ms = **4,3 s só de rede no piso físico**, ~7 s no valor típico —
contra ~40 ms hoje. Mover só o banco troca uma exposição jurídica parcial
por um app 100× mais lento em toda tela. A migração só faz sentido junto
com o serviço web (outro provedor com região no Brasil, fora deste
documento) ou com um teto de consultas por tela muito menor.

**O procedimento, se a medição disser que cabe** (12 MB; `scripts/migrar.sh`
faz dump, restore e conferência tabela a tabela num comando):

1. **Medir a latência** que o web pagaria: de um shell no Render (ou de um
   job no `nutriplan-staging`), `psql -d "<URL de um projeto Neon em SP>"
   -c '\timing' -c 'select 1'` dez vezes; anote o mediano. Acima de ~20 ms
   por consulta, pare aqui e registre no BACKLOG.
2. **Backup antes de tudo**: `scripts/backup.sh` + `guardar.sh`, e o drill de
   `restaurar.sh` no Postgres local — a regra deste documento.
3. **Criar o projeto novo** no console do Neon: região São Paulo, Postgres 16
   (a mesma versão da produção — `pg_dump` 18 funciona nos dois), plano
   Free, um banco com o mesmo nome. Pegar a connection string **direta**
   (sem `-pooler`): "Avoid using `pg_dump` over a pooled connection string"
   (https://neon.com/docs/import/migrate-from-neon).
4. **Ensaiar no staging primeiro**: apontar a `DATABASE_URL` do
   `nutriplan-staging` (branch `staging` do projeto atual) para um banco de
   ensaio em SP, subir, medir a Home com `nav.py` e o E2E
   (`scripts/qa/e2e_staging.py`). Sem essa medida, não há decisão.
5. **Janela de manutenção** (poucos minutos; avisar no app ANTES — a LGPD,
   art. 8º § 6º, manda informar com destaque a mudança do que o art. 9º
   descreve, e a Política promete aviso de troca de operador):
   `ORIGEM_URL='<Oregon>' DESTINO_URL='<São Paulo>'
   scripts/migrar.sh` — as URLs entram por ambiente, nunca por argumento; o
   script conta linhas de verdade nos dois lados e para se divergir.
6. **Trocar a `DATABASE_URL`** de produção no painel do Render (ou
   `scripts/render_api.py env`), nunca no `render.yaml`; reiniciar o
   serviço; `/saude/` tem de devolver o mesmo `commit` e as contagens do
   catálogo.
7. **Atualizar a Política de Privacidade** ("Onde seus dados ficam": Neon em
   São Paulo, Render em Oregon) e o registro das operações.
8. **Manter o projeto de Oregon por 7 dias** como rollback (a mesma razão
   de o banco do Render ter ficado declarado), depois apagar — e conferir
   que o UptimeRobot e o `podar_operacoes` continuam batendo no lugar certo.

O que este procedimento não cobre: mover o serviço web (Render não tem
Brasil), a região do `nutriplan-staging` (fica onde estiver o projeto que
ele usa), e o custo de CU-h — um projeto novo tem cota própria, mas o
staging, se for para o mesmo projeto, compartilha.
