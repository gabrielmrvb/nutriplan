---
name: nutriplan-missao
description: O protocolo de execução autônoma do NutriPlan — como conduzir uma missão do objetivo humano até produção sem parar a cada etapa. Use ao receber uma campanha, missão, fase, bloco ou lote de trabalho ("implemente X", "faça a Fase 2", "continue de onde parou", "corrija Y e publique"); ao retomar uma sessão interrompida; ao decidir se vale decompor em subagentes; e para saber exatamente quando PODE avançar sozinho e quando DEVE parar por bloqueio humano. Traz o ciclo (planning → decomposição → subagentes → integração → testes → browser QA → sabotagem → suíte → deploy → smoke), os contratos de subagente, a regra de propriedade de arquivos, o vocabulário de evidência e os gates reais deste repositório. NÃO use para pergunta pontual, leitura de código ou dúvida de uma linha — protocolo em tarefa pequena é cerimônia.
---

# O protocolo de missão do NutriPlan

Uma missão termina quando o **comportamento exigido está provado** — não quando
o código ficou pronto.

Este arquivo é o **como**. O **o quê** do produto está no `CLAUDE.md`, e as
decisões de domínio em `nutriplan-product`, `nutriplan-architecture` e
`nutriplan-ux`.

### A relação com `nutriplan-qa`, dita por inteiro

`nutriplan-qa` descreve um papel de VALIDAÇÃO: alguém entrega, ela julga. Nesse
papel ela é explícita — não escreve teste sem autorização (`:376`), não
conserta o bug que encontra (`:239`), e **não faz deploy** (`:191`, `:394`).

Uma MISSÃO é outra coisa: a pessoa entregou o objetivo inteiro, incluindo
publicar. Dentro de uma missão, escrever teste, corrigir o defeito e publicar
**fazem parte do contrato recebido** — e é por isso que este protocolo autoriza
os três.

Fora de missão, quando alguém pede "revise isto", `nutriplan-qa` continua
valendo inteira. As duas não se contradizem porque não governam a mesma
situação; o que seria erro é usar uma no lugar da outra.

O **vocabulário de evidência é o dela**, sem exceção. Ver a seção 6.

## Quando este protocolo vale

Vale para trabalho com fases: uma campanha, um bloco, uma fase, um lote que
termina em publicação.

**Não vale** para pergunta pontual, leitura de código, ajuste de uma linha.
Rodar planning e decomposição numa tarefa de dois minutos é cerimônia, e
cerimônia gasta a atenção que a próxima missão de verdade vai precisar.

---

## 1. Planning, antes de editar

Antes do primeiro `Edit`, estabeleça:

- o objetivo, dito em uma frase que dá para verificar;
- o que o código REAL faz hoje — lido, não lembrado;
- dependências e riscos;
- o que é reversível e o que não é;
- critérios de sucesso;
- o que é **fato** e o que é **hipótese**.

E então decomponha. Cada unidade recebe um rótulo:

| rótulo | significa |
|---|---|
| **SEQUENCIAL** | depende do anterior; não paralelize |
| **PARALELIZÁVEL** | fronteira própria, sem colisão |
| **BLOQUEADA** | espera outra unidade terminar |
| **HUMANA** | só a pessoa pode destravar |

Planning não é paralisia. Quando o caminho estiver suficientemente provado,
**execute**.

### A pergunta que evita a missão inventada

Antes de decompor: **isto já foi feito?** Confira o `BACKLOG.md` — ele
marca o que está feito, bloqueado e pendente — e o histórico do git.
Refazer auditoria já provada é o desperdício mais
caro deste repositório — aconteceu, e custou um commit inteiro de duplicação.

---

## 2. Subagentes

Use quando houver **ganho real** de paralelismo ou especialização. Não crie
subagente para dizer que usou.

Sinal de que vale: duas unidades PARALELIZÁVEIS com arquivos disjuntos, ou uma
varredura ampla cujo resultado interessa mais que o caminho.

Sinal de que **não** vale: a unidade cabe em três ferramentas; a fronteira é um
arquivo só; o custo de escrever o contrato é maior que o trabalho.

### O contrato que todo subagente recebe

Sem estes sete itens, o retorno não é confiável:

1. **objetivo** — verificável, não "melhore X";
2. **contexto mínimo** — só o que ele precisa saber;
3. **área permitida** — pastas ou arquivos;
4. **arquivos proibidos** — nomeados;
5. **pode editar, ou é somente leitura**;
6. **testes esperados** e a definição de pronto;
7. **formato de retorno**.

### Propriedade de arquivo — a regra que evita colisão

**Dois subagentes nunca editam a mesma superfície ao mesmo tempo.**

Antes de paralelizar, atribua dono. `config/settings.py`, `config/urls.py`,
`accounts/models.py` e `CLAUDE.md` são atravessados por quase tudo: trabalho
que os toca é **serializado**, sempre.

Somente-leitura pode ser paralelo à vontade — pesquisa, auditoria e revisão não
colidem com ninguém.

### Papéis que costumam render aqui

Arquitetura/pesquisa (leitura) · implementação de unidade isolada · segurança e
abuso · adversarial (procura teste fraco e sabota) · compatibilidade web ·
browser QA · revisor. Use só os necessários.

Para revisão de risco relevante, o revisor **não** deve ser quem implementou.

### O orquestrador não delega a responsabilidade

> **"O subagente disse que passou" não é evidência.**

Quem orquestra confere o diff, roda o teste e olha o comportamento. Um retorno
aceito sem verificação é um retorno não verificado com aparência de pronto.

---

## 3. Gates reais deste repositório

Não invente gate novo: estes existem e funcionam.

**Antes de qualquer suíte, confirme que o banco de teste está livre** — é a
regra do B9, e ela já barrou uma execução concorrente de verdade:

```bash
psql -U postgres -d postgres -tAc \
  "select count(*) from pg_stat_activity where datname like 'test_nutriplan%'"
```

Zero conexões, pode rodar. Diferente de zero, há **dois casos** e eles pedem
coisas opostas:

- **suíte de verdade em andamento** — espere. Cheque CPU e saída para saber.
- **sobra de execução interrompida** — esperar nunca termina. Derrube só as
  conexões DESTE banco; o real fica intocado:

```bash
psql -U postgres -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE datname LIKE 'test_nutriplan%'"
```

`RunnerUnico` recusa por você — mas só quando **consegue enxergar**: banco fora
do ar, backend que não é Postgres ou permissão negada devolvem "não sei", e não
saber não impede ninguém de rodar (`config/runner.py:51`).

`NUTRIPLAN_IGNORAR_RUNNER_UNICO=1` é **último recurso, e aceita o resultado
embaralhado que a checagem existe para evitar**. Não é atalho para pressa.

A cadeia. O B11 versiona a FORMA dela em `docs/premium-polish-b1-b11.md`, e o
que está escrito lá é mais curto: a palavra única `gate` onde aqui vão três
comandos, `sabotage relevante se houver regra nova` em vez de sabotagem sempre,
e nem `fetch` nem `/saude/`. A cadeia abaixo é a operacional — mais estrita de
propósito. O B11 nomeia a maior parte dos passos e colapsa três deles na
palavra `gate`; o que ele não diz é QUE comandos são esses, nem onde cada um
roda. É o que a lista abaixo resolve:

```
testes dirigidos → sabotagem → browser QA → suíte completa
→ manage.py check → makemigrations --check → git diff --check
→ commit → fetch → push → hook → deploy → /saude/ → smoke
```

Onde cada um mora de verdade. Seguir o ponteiro errado é o que faz alguém
"corrigir" esta cadeia para a versão curta e perder os três comandos:

- **teste dirigido é seu, e à mão.** O `pre-commit` roda um conjunto FIXO de
  seis classes de estilo e alvo de toque (`scripts/hooks/pre-commit:30`), que
  não olha para o que você mexeu. Ele não é o primeiro passo da cadeia, e
  tomá-lo por isso é perder o gate que mais importa;
- `makemigrations --check` esse sim roda sozinho, no mesmo hook
  (`scripts/hooks/pre-commit:27`) — migração faltando quebra o deploy, não o
  teste;
- a suíte completa é do `pre-push` (`scripts/hooks/pre-push:19`);
- `manage.py check` é seu, antes do commit. Com `--deploy --fail-level ERROR`
  ele roda DE NOVO no build do Render (`scripts/build.sh:37`), depois do
  collectstatic — lá é portão, e o que reprova não sobe;
- `git diff --check` é da seção 10 deste arquivo, e é manual;
- `/saude/` como prova de deploy é do `CLAUDE.md` (`:172`), e o porquê está na
  seção 7;
- `fetch` antes do push não está versionado em lugar nenhum. É prática, e fica
  dito que é.

A suíte completa levava ~3 min com 692 testes; **medida em 04/09/2026, são
1.968 testes em ~20 min**. Rode em segundo plano e faça o que for
paralelizável enquanto ela corre.

**E espere ela terminar antes de dar `git push`.** O `pre-push` roda
`manage.py test` INTEIRO de novo (`scripts/hooks/pre-push:19`): empurrar com a
suíte de fundo ainda viva é exatamente a colisão que o B9 existe para impedir,
e ela já derrubou o hook uma vez com `database "test_nutriplan" is being
accessed by other users`.

**O código de saída importa.** `manage.py test | tail` devolve o status do
`tail`, não da suíte — já enganou aqui. Capture o exit code direto.

---

## 4. Browser QA

Quando a mudança tem comportamento observável na tela, browser QA é parte do
gate — não enfeite.

**"A página abriu" não é QA.** Percorra o fluxo como quem usa: clique, envie o
formulário, erre a senha, fique sem dado, encha de dado, abra o modal, feche
com o teclado. Para tela alterada, o B8 é incondicional e está em
`docs/premium-polish-b1-b11.md`: 375, 430, tablet e desktop, mais rolagem
horizontal, alvo de 44px, contraste, tamanho mínimo, e os estados vazio, cheio,
loading e erro. As skills de domínio usam ~390px como referência de mobile; a
lista de quatro larguras é do B8, e as duas convivem.

Três armadilhas que já custaram caro aqui, e vão custar de novo:

- **medição em cold start.** O Render devolve a página de espera dele. Confira
  o `<title>` antes de aceitar qualquer medida remota.
- **`.focus()` por JS não dispara `:focus-visible`.** Para medir foco, pressione
  Tab de verdade.
- **`color(srgb r g b / a)` traz componentes em 0–1, não 0–255.** Todo cálculo
  de contraste precisa de controle positivo: preto sobre branco tem de dar 21.

Browser QA prova experiência. **Não substitui teste**, que prova contrato.

---

## 5. Sabotagem

Para toda guarda que importa:

> Se eu quebrar isto de propósito, algum teste fica vermelho?

O laço: baseline verde → quebra controlada → o teste tem de ficar **vermelho**
→ restaura → verde de novo. **Sabotagem nunca entra no commit.**

Sabotagem que passa verde não é guarda que funcionou: é **teste errado**. Já
aconteceu dez vezes nesta base, e a causa é quase sempre a mesma —

> a asserção casa com outro lugar da página. `href="/conta/entrar/"` casa com
> o "Entrar" do cabeçalho, e não com o botão do cartão.

O `CLAUDE.md` já dá a saída: ancore na **classe** (`class="card resumo"`) ou no
**texto visível** — e, quando a asserção for sobre a estrutura de um arquivo,
**tire os comentários antes**, com um helper como o `sem_comentarios()` de
`push/test_cache_privado.py`. Este projeto comenta muito, e o comentário cita o
nome da coisa que a asserção procura.

Duas outras que já enganaram:

- **`self.client.post(url, {...})` prova a VIEW, não a TELA.** Com o nome do
  campo trocado no template, o teste segue verde e o formulário está quebrado.
  Envie o formulário **renderizado**, com `enforce_csrf_checks=True`.
- **Sabotagem inofensiva.** Acrescentar `post` a um mixin não muda nada quando
  a view já define o próprio. Confira que a quebra realmente quebra.

---

## 6. Vocabulário de evidência

**Use o de `nutriplan-qa`, e não invente outro.** Ele já é fechado em cinco
categorias, e a própria skill proíbe acrescentar:

`[EXECUTADA]` · `[OBSERVADA]` · `[LIDA NO CÓDIGO]` · `[LIDA NA DOCUMENTAÇÃO]` ·
`[HIPOTÉTICA]`

Um segundo vocabulário ao lado seria duas maneiras de dizer a mesma coisa, e a
segunda nasceria para divergir.

Para classificar um ACHADO — que é outra pergunta — use `BUG` · `UX REAL` ·
`OBSERVAÇÃO` · `FALSO POSITIVO`, e `LIMITAÇÃO` para o que a plataforma não
permite. Os cinco são convenção **deste protocolo**: medido em 04/09/2026, só
`OBSERVAÇÃO` tem precedente escrito como rótulo no repositório
(`BACKLOG.md:934`). O `BACKLOG.md` descarta "falso positivo" várias vezes, mas
em prosa e em minúscula — o que não é a mesma coisa, e foi exatamente o que
uma medição com `grep -i` confundiu aqui.

Separe sempre **PROVADO EM PRODUÇÃO** de **PROVADO LOCAL/QA**. Simulação não é
aparelho na rua, e teste local não é produção.

Quando não der para observar de fora qual versão está viva — um commit que só
toca teste ou documentação não cria superfície —, **diga isso** em vez de
contornar.

---

## 7. Deploy e produção

`git push` dispara o Render. Não declare deploy porque o tempo passou:
**prove com sinal observável**. Uma rota que muda de 404 para 401, um título
que muda, um cabeçalho novo.

E escolha a sonda certa: **`/saude/` é a prova**, porque ela consulta o catálogo
e só devolve 200 se a migração rodou. `/saude/vivo/` não faz consulta nenhuma —
prova que o serviço web acordou, e nada além disso. Trocar uma pela outra
declara deploy verde com o banco atrasado, e foi o erro de prática desta sessão
inteira até alguém conferir.

Distinga **cold start** de erro: o plano gratuito dorme, e a primeira
requisição pode levar os ~50 s que o `CLAUDE.md` registra, ou dar timeout.
Repita antes de acusar.

Smoke com **controle positivo**. Uma varredura que não consegue enxergar um
erro que você sabe existir não está medindo — já devolveu "zero 5xx" porque um
`\r` de CRLF invalidava toda URL e o curl respondia `000`.

Em produção: só GET e navegação não destrutiva. **Não use a conta pessoal do
dono como ferramenta de QA**, e não tente senhas nela. Sem conta QA autorizada,
limite a prova ao que se observa sem autenticar — e declare o resto como
bloqueio humano.

---

## 8. Continuidade automática

Terminou uma etapa, os critérios estão satisfeitos, os gates verdes e a próxima
etapa está definida pelo plano? **Avance.**

Não pergunte "posso continuar?", "quer que eu faça a próxima fase?", "devo
corrigir?".

**Não pare por:** teste demorando · deploy demorando · precisar pesquisar ou ler
documentação · bug encontrado · primeira correção falhar · falso positivo ·
precisar criar teste ou sabotagem · subagente achar problema · fim normal de
subfase.

Achou defeito no escopo? O laço é:

```
REPRODUZA → CLASSIFIQUE → CORRIJA → TESTE → BROWSER QA → SABOTE → REVALIDE
```

### Pare somente por bloqueio humano real

Credencial que só a pessoa tem · 2FA · CAPTCHA · pagamento · aceite legal ·
conta em serviço externo · operação destrutiva relevante · risco de perda de
dado real · decisão de produto com alternativas materialmente diferentes ·
decisão arquitetural fora do contrato — e o portão de `nutriplan-architecture`
é mais largo que "irreversível": **escolha de fundo que precisa ser feita antes
de existir código** para aí, com as opções e os custos · teste físico que exige
o aparelho · autorização para usar dado ou conta real · conflito de requisitos
que o contrato não resolve · infraestrutura externa fora do ar sem alternativa
segura.

Encontrou algo inesperado que não está nessa lista? **Investigue primeiro.**

---

## 9. Checkpoints e retomada

Mantenha o progresso visível no relatório, fase a fase, com o que já está
provado. Serve para quem lê e serve para você, se a sessão cair.

Ao retomar, **não recomece do zero**:

1. leia o plano e o último checkpoint;
2. `git status`, `HEAD`, local vs remoto;
3. processos e tarefas em segundo plano — leia a saída deles;
4. determine onde parou;
5. continue dali.

Tarefa que parece travada: cheque CPU e saída **antes** de matar. CPU subindo
junto com o relógio é trabalho em andamento; CPU parada há horas sem produzir
um byte, não. Compare o consumo com o tempo de vida do processo em vez de olhar
um número isolado.

---

## 10. Commits

Antes de cada um: `git status`, `git diff`, `git diff --check`.

Confirme que entrou **só** o da missão — nada de sabotagem, arquivo
temporário, segredo, pasta de outro projeto ou conserto oportunista.

Commit coerente: nem um por ajuste cosmético, nem um gigante misturando
assuntos. Quando as partes não se sustentam separadas, um commit só — e o
motivo escrito na mensagem.

**Hook que recusa é gate, não obstáculo.** Investigue a causa. `--no-verify`
para fazer a missão passar é proibido; o `pre-commit` recusa pasta nova de
primeiro nível de propósito, e a correção é declará-la em `CONHECIDAS`, não
contornar.

---

## 11. Qualidade acima de movimento

Se a investigação provar que não há defeito, **não invente correção**. Se uma
fase não exige alteração, registre a evidência e avance.

**"Zero linhas alteradas" é resultado válido** — e às vezes é o certo.
