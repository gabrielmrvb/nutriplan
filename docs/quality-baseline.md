# Linha de base de qualidade — 26/09/2026

**Este documento MEDE. Ele não conserta nada, e nenhuma refatoração foi feita nem
decidida a partir dele** — foi o pedido explícito do dono ao encomendá-lo. Ele existe
para que a decisão de mexer (ou de não mexer) seja tomada com número na mão, e para
que daqui a um mês dê para saber se a dívida cresceu ou encolheu.

- **Commit medido:** `b4258fe` (ponta de `origin/main` na data).
- **Universo:** só arquivo VERSIONADO (`git ls-files`). `.venv`, `__pycache__`,
  `artifacts/` e `node_modules` ficam de fora — contá-los mediria a máquina, não o
  projeto.
- **Ferramenta:** contagem de linhas própria, `grep` e **ruff 0.16.9** (seção 4).

---

## 1. Arquivos acima de 350 linhas

A régua de 350 é a do pedido. Ela não é do projeto — o `CLAUDE.md` nunca fixou
tamanho de arquivo —, então o que segue é dívida MEDIDA contra uma régua externa, e
não violação de uma regra interna.

### Python de produção — 330 arquivos, 47.929 linhas, **30 acima de 350**

| linhas | arquivo | observação |
|---|---|---|
| 4.303 | `workouts/services.py` | o motor do treino: prescrição, opções, aparo, relógio, substituição |
| 2.065 | `plans/views.py` | ver seção 2 |
| 1.850 | `workouts/views.py` | ver seção 2 |
| 1.720 | `accounts/views.py` | ver seção 2 |
| 1.681 | `workouts/models.py` | |
| 1.211 | `accounts/models.py` | |
| 1.098 | `accounts/forms.py` | |
| 764 | `plans/evolucao.py` | |
| 756 | `workouts/opcoes.py` | |
| 692 | `demo/management/commands/seed_demo.py` | fixture do demo |
| 661 | `config/settings.py` | |
| 657 | `scripts/github.py` | ferramenta de fluxo, não roda em produção |
| 600 | `plans/tracking.py` | |
| 600 | `plans/models.py` | |

(os 16 restantes ficam entre 350 e 600)

### Python de teste — 271 arquivos, 83.444 linhas, **59 acima de 350**

| linhas | arquivo |
|---|---|
| 7.142 | `accounts/tests.py` |
| 5.729 | `workouts/tests.py` |
| 5.062 | `plans/tests.py` |
| 2.590 | `config/tests.py` |
| 1.528 | `push/tests.py` |
| 1.108 | `demo/tests.py` |

**O fato mais informativo desta medição:** teste é **63 %** do Python versionado
(83.444 de 131.373 linhas). A régua de 350 aplicada a arquivo de teste mede outra
coisa que a aplicada a arquivo de produção — um `tests.py` grande é um app com muita
regra provada, e quebrá-lo tem custo próprio (os testes deste projeto se ancoram uns
nos outros por nome de classe). Dividir teste e produção aqui é para ninguém somar
os dois e concluir a coisa errada.

### JavaScript — 10 arquivos, 5.450 linhas, **4 acima de 350**

| linhas | arquivo |
|---|---|
| 2.254 | `static/js/pwa.js` |
| 724 | `templates/pwa/sw.js` |
| 688 | `static/js/fila.js` |
| 590 | `static/js/corrida.js` |
| 346 | `static/js/card.js` (abaixo da régua) |

Nota para quem for mexer: `fila.js` e `sw.js` **têm funções propositalmente
idênticas** (`emOrdemDeToque`, `corpoDoItem`), e há teste comparando as duas.
Deduplicar os dois arquivos quebraria a decisão, não a dívida — os dois lados abrem o
mesmo IndexedDB e precisam concordar sem depender um do outro.

---

## 2. Views que acessam o ORM direto

Contagem de `.objects.` por arquivo `views.py` versionado: **9 dos 11 arquivos**.

| ocorrências | arquivo |
|---|---|
| 25 | `plans/views.py` |
| 19 | `accounts/views.py` |
| 15 | `workouts/views.py` |
| 11 | `workouts/corrida_views.py` |
| 6 | `gestao/views.py` |
| 4 | `push/views.py` |
| 3 | `ajuda/views.py` |
| 1 | `analytics/views.py` |

Sem ORM direto: os outros 2.

**Ressalva de leitura, e ela é importante.** Este número NÃO é, sozinho, uma medida
de lógica no lugar errado. Várias dessas ocorrências são leitura de UMA linha que a
tela precisa, e o projeto otimizou deliberadamente a Home de 44 para 17 consultas
passando resultado já lido de um subsistema para o outro **por parâmetro**, o que
coloca a leitura perto da view de propósito. Separar "consulta que é orquestração de
tela" de "regra de negócio que vazou" exige ler caso a caso — e isso não foi feito
aqui, porque o pedido era medir.

---

## 3. Lógica de negócio fora de `services/`

**5 apps têm módulo de serviço:** `achievements`, `avisos`, `plans`, `push`,
`workouts`.

**Sem módulo de serviço:** `accounts`, `catalog`, `gestao`, `ajuda`, `analytics`,
`demo`, `config`.

Dos sem serviço, o que merece olhar quando alguém decidir olhar:

- **`accounts`** — 1.720 linhas de view e 1.098 de formulário, com o onboarding em
  três etapas compostas cuja ordem de `save()` é regra (objetivo → divisão → rotina,
  porque `TrainingForm.save()` relê o perfil). É o candidato mais forte a ter regra
  fora de serviço.
- **`analytics`** — tem `consultas.py`, que já é um módulo de leitura separado com
  outro nome.
- **`catalog`, `demo`, `gestao`, `ajuda`** — pouco código e pouca regra; a ausência
  de `services.py` aqui provavelmente é correta.

De novo: **não classifiquei nenhuma dessas linhas como "regra vazada"**. Fazer isso
exige ler cada uma, e é trabalho de outra missão.

---

## 4. ruff — o piso, e o que ele mede

**ruff 0.16.9**, config em `ruff.toml`: `select = ["E", "F", "W"]`,
`ignore = ["E501"]`, `line-length = 100`, migrações excluídas (código gerado
pelo Django).

**Total: 104 achados.** O piso vive em `ruff-baseline.txt` e a regra do dono é
que **a contagem não sobe** — o `pre-commit` e o job `ruff (relatório)` do CI
comparam contra ele. Nenhum dos dois barra merge: o check obrigatório continua
sendo a "suíte rápida".

| nº | regra | o que é |
|---|---|---|
| 58 | `E741` | nome de variável ambíguo (`l`, `I`, `O`) |
| 20 | `E702` | duas instruções na mesma linha, com `;` |
| 18 | `E701` | duas instruções na mesma linha, com `:` |
| 8 | `E731` | `lambda` atribuído a nome |

### Como saiu de 1.656 para 114 (27/09/2026)

Duas mudanças, e nenhuma delas tocou lógica.

**`E501` saiu do `select`** — 1.439 dos 1.656, 87% do total, e quase todos em
COMENTÁRIO. Esta base documenta decisão em prosa dentro do código: é a razão de
o `CLAUDE.md` ter 1.900 linhas e de cada docstring explicar o porquê. Cobrar 100
caracteres disso é pedir para reescrever a documentação, não o código — e uma
catraca que ninguém pretende zerar deixa de ser catraca. `line-length = 100`
ficou: continua sendo a referência escrita, sem a regra reprovar.

**Os 97 `F401` saíram com `ruff check --fix`** — correção SEGURA, sem
`--unsafe-fixes`. 65 arquivos tocados, e
a auditoria do diff antes de rodar a suíte:

- **toda linha acrescentada é `import` ou `from ... import`** — são blocos
  multilinha que o ruff reescreveu ao remover um nome do meio;
- das removidas, **5 não começam com `import`** (`OptionLabel,`, `WeightEntry,`,
  `SEGUNDOS_ENTRE_EXERCICIOS,`, `SEGUNDOS_POR_SERIE,`, `Measure,`) e as cinco são
  linha de continuação dentro de um import multilinha;
- **nenhum `__init__.py`, `signals.py`, `apps.py` ou `conftest.py`** estava na
  lista — é ali que import "não usado" costuma ser re-exportação ou efeito
  colateral de carga;
- cada um dos cinco nomes foi procurado no resto do repositório: quem os importa
  os importa do módulo de ORIGEM (`.models`), nunca do arquivo que perdeu a
  linha. Nenhuma cadeia de re-exportação quebrada.

Resultado: **zero mudança de comportamento**, e a suíte rápida
(`--exclude-tag lento`) confirma.

### Os dez achados reais (27/09/2026, tarde) — 114 para 104

Cada um foi lido e classificado antes de mexer, com a pergunta do dono: **a
correção muda comportamento?**

| regra | onde | o que era | veredito |
|---|---|---|---|
| `F601` | `accounts/test_duracao_portao.py`, 2× | `"experiencia": "intermediario"` repetido no mesmo dict, com o **mesmo valor** | não muda — a chave sobrescrita escrevia o que já estava lá. Duplicata removida. Resto de uma edição que acrescentou `musculacao`/`experiencia`/`equipamento` numa linha que já tinha a chave embaixo. |
| `F811` | `plans/views.py` | `from django.views import View` e `from django.views.generic import TemplateView, View` | não muda — é o mesmo objeto. Ficou a linha de `generic`. |
| `F811` | `demo/tests.py` | `User` importado de `accounts.models` e redefinido por `get_user_model()` | não muda — `AUTH_USER_MODEL` é esse mesmo `User`. Ficou `get_user_model()`. |
| `F841` | `accounts/test_consentimento.py`, 2× | `user = self.pessoa()` com `user` nunca lido | não muda — a CHAMADA cria e loga a pessoa, e continua; só o nome saiu. Das sete ocorrências da linha no arquivo, as outras cinco usam `user` e ficaram. |
| `F841` | `workouts/test_lista_de_hoje.py` | `sessao = self._uma_sessao()` | não muda — mesma coisa: a chamada monta a sessão e continua. |
| `F841` | `workouts/test_perfis_de_qa.py` | `exp` no desempacotamento de `perfil`, nunca lido | não muda — saiu da tupla. O `exp` de `nascer()` é outro escopo e ficou. |
| `F841` | `demo/tests.py` | `ontem = hoje - timedelta(days=1)`, nunca lido | não muda — conta morta: o laço subtrai da data de CADA registro, não de hoje. |
| `F841` | `accounts/test_tres_etapas.py` | recorte `objetivo` montado e nunca usado; a asserção lia `html` | **MUDA** — ver abaixo. |

**O único que mudava comportamento era um teste mais fraco do que o nome.**
`test_o_campo_obrigatorio_erra_no_proprio_campo_e_preserva_o_resto` recortava o
bloco do objetivo e depois afirmava o erro contra a PÁGINA inteira — "o erro
aparece em algum lugar", bem menos do que "no próprio campo". Reaproveitar o
recorte como estava também reprovava, com o app correto: ele terminava no
primeiro `</ul>`, que é o fim da lista de opções, e o erro sai DEPOIS dela
(`choice_cards.html:122`, fora do `role="group"`).

O que liga erro e campo é o `aria-describedby` do grupo, e o teste agora prende
as duas pontas: o grupo do objetivo aponta para `id_goal_error`, e a mensagem
mora dentro do elemento com esse id. **Sabotado nos dois sentidos**, no template
que o campo de fato usa: tirar o `_error` do `aria-describedby` → vermelho;
trocar o `id` do bloco de erro → vermelho; restaurado → verde. (A primeira
sabotagem foi feita em `field.html` e passou verde — o `goal` é cartão de escolha
e não passa por ele. Fica o registro: sabotagem no arquivo errado prova nada.)

### O que sobra, e a ordem

**104, todos de estilo**, e o ruff não corrige nenhum com segurança
(`No fixes available`; os 8 atrás de `--unsafe-fixes` não foram usados):
`E741` (58), `E702` (20), `E701` (18), `E731` (8). `E741` é o maior, e vale olhar
caso a caso — um `l` de `linha` num laço curto não é o mesmo problema que um `I`
solto.

## Como usar este documento

- Ele é **fotografia**, não catraca. Nenhum teste lê estes números hoje.
- Se um dia virarem catraca, o padrão do projeto é o de
  `config/test_design_system.py`: um teto que **não pode crescer**, com a medição
  escrita ao lado e a data.
- Remedir é rodar a mesma contagem sobre `git ls-files` e comparar commit a commit.
