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
