# Revisão multi-agente — NutriPlan

Adaptado de `docs/prompts/03-multi-agent-code-review.md` do Vibe Coding Toolkit
(`soumatheusgomes/vibe-coding-toolkit`). O que veio de lá: três revisores
independentes, o formato do achado com CENÁRIO DE FALHA obrigatório, e a síntese em
deduplicar → filtrar → ordenar. O que foi trocado: os revisores genéricos ("segurança
OWASP", "type-safety", "framework") viraram os TRÊS que este projeto tem, cada um com
as réguas REAIS do `CLAUDE.md` — régua genérica devolve achado genérico.

**Como usar:** despache os três em paralelo, SOMENTE LEITURA, sobre o mesmo diff.
Depois faça a síntese você mesmo. O revisor nunca é quem implementou.

---

## Regras que valem para os três

- **Somente leitura.** Não editar, não criar, não apagar. Não rodar `manage.py test`
  (a suíte recusa concorrência e pode haver outra rodando).
- **Achado sem cenário de falha concreto é descartado pelo próprio revisor.** Não
  encha a lista. "Poderia ser mais legível" não é achado.
- **Classificação é a do `nutriplan-qa`**, e não se inventa outra:
  `BUG` · `UX REAL` · `OBSERVAÇÃO` · `FALSO POSITIVO` · `LIMITAÇÃO`.
- **Evidência é a do `nutriplan-qa`**, uma por achado, sem rótulo novo:
  `[EXECUTADA]` · `[OBSERVADA]` · `[LIDA NO CÓDIGO]` · `[LIDA NA DOCUMENTAÇÃO]` ·
  `[HIPOTÉTICA]`.
- **Formato do achado:**
  `arquivo:linha — classificação — [evidência] — a afirmação em uma frase — o cenário concreto de falha`
- Se uma categoria não tiver achado, **diga isso**. Achado inventado custa mais caro
  que achado não encontrado.

---

## Revisor 1 — Django e segurança

Procure, nesta ordem de suspeita:

- **Consulta que cresce com o dado (N+1).** Os orçamentos são medidos e estão no
  `CLAUDE.md`: Home 17, Alimentação 18/19, painel do treino 25, leitura 11, ficha 17.
  Consulta nova dentro de laço, ou orçamento estourado sem a medição escrita ao lado.
- **Idempotência da fila offline.** Toda escrita que a fila reenvia precisa de
  `op_id`, e o `op_id` tem de cair junto com o efeito (transação) — commitar o
  identificador antes da escrita responde "já aplicada" a um reenvio que nunca
  aplicou. Água SOMA no banco (`F()` + `Least`), nunca lê-modifica-escreve.
- **CSP e nonce.** Todo `<script>` inline de `templates/` carrega
  `nonce="{{ csp_nonce }}"`; nenhum atributo `onclick=`/`onsubmit=`/`onchange=`
  sobrevive. Sob CSP, atributo de evento não dá erro visível — o botão só não faz nada.
- **Cache de tela logada.** Resposta `text/html` autenticada leva
  `private, no-cache, must-revalidate`; **nunca `no-store`** (o service worker recusa
  guardar, e o Chrome desliga o bfcache do "Voltar ao formulário").
- **Segredo.** Nada de valor no repositório, no log ou no relatório; o cofre é
  `~/.nutriplan-secrets`. O log redige token de redefinição (que anda na URL),
  parâmetro de OAuth, chave de SMTP e URL de banco.
- **LGPD e consentimento.** Dado de saúde (peso, altura) exige a caixa do art. 11, I
  ANTES de gravar; transferência internacional é caixa própria (art. 33, VIII). A
  prova é `Consentimento`, porque o ônus é do controlador.
- **Constraint no banco, não só em Python.** "Pertence a" é `CheckConstraint`: duas
  transações simultâneas atravessam juntas uma checagem em Python.
- **Redirecionamento aberto.** `?next=` é lista fechada por NOME de tela.

---

## Revisor 2 — UI e PWA

- **Alvo de toque 44 px de altura E de largura.** A régua mede as duas — 26 px de
  largura com 44 de altura já passou despercebido uma vez.
- **Texto de interface nunca abaixo de 11 px** — e cuidado com texto dentro de SVG,
  que ESCALA com o `viewBox`: a régua de tipo mede o token, não o tamanho na tela.
- **Nada rola na horizontal.** Todo container de texto leva `min-width: 0`.
  `documentElement.scrollWidth` é cego neste app (`overflow-x: hidden` na raiz) —
  meça por `body.scrollWidth` e pela maior borda direita, com controle positivo.
- **Número é `tabular-nums` e vírgula decimal** (pt-BR: "62,50").
- **Tokens, não valor cru.** Sem framework de CSS, um arquivo só, seções numeradas;
  a catraca de valor cru não pode crescer. Quina é `--quina-*`; nada clicável é
  pílula; botão sempre declara a variante.
- **Movimento.** Durações saem dos tokens `--mov-*` (o teto de duração escrita à mão
  é ZERO); toda animação tem par em `prefers-reduced-motion`; `view-transition-name`
  é ÚNICO por documento — duplicado, o navegador pula a transição inteira sem erro.
- **`[hidden]` perde para `display: flex`** se não fosse o `!important` global —
  confira antes de dar `display` a um bloco que o JavaScript esconde.
- **Os dois lados do IndexedDB concordam** (`fila.js` e `sw.js`: mesma versão, mesma
  store, `emOrdemDeToque` e `corpoDoItem` idênticos).
- **Ordem de leitura e de foco é a do DOM** (WCAG 1.3.2 e 2.4.3) — `order` do
  flexbox move a pintura e deixa o foco para trás.
- **Estado vazio é convite**, não constatação.

---

## Revisor 3 — Testes

- **Teste que passa pelo motivo errado.** Para CADA asserção: existe outro trecho da
  página ou do arquivo que satisfaz essa string? O seletor do JavaScript e o marcador
  do HTML são a mesma string — `assertNotIn("data-x", html)` passa por acidente
  porque `data-x` está dentro do `<script>`. Ancore em classe ou em texto visível, e
  **tire os comentários antes** quando a asserção for sobre a estrutura de um arquivo:
  este projeto comenta muito, e o comentário cita o nome da coisa que a asserção procura.
- **Laço que passaria vazio.** `for x in re.findall(...)` sem `assertGreater(len(...))`
  antes é um teste que vira verde no dia em que a regex parar de casar.
- **Tautologia.** A asserção compara uma fonte com ela mesma? Um número escrito à mão
  no teste que deveria vir do arquivo sob teste?
- **Controle positivo.** Toda medição precisa de um caso que ela SABE detectar. Uma
  varredura que não enxerga um erro conhecido não está medindo.
- **Sabotagem.** Para toda guarda que importa: quebre de propósito e exija VERMELHO.
  Sabotagem que passa verde não é guarda que funcionou — é teste errado.
- **A view não é a tela.** `self.client.post(url, {...})` prova a VIEW; com o nome do
  campo trocado no template o teste segue verde e o formulário está quebrado. Envie o
  formulário RENDERIZADO, com `enforce_csrf_checks=True`.
- **Doutrina do relógio.** Teste nunca lê `date.today()`, `datetime.now()` nem
  `time.time()`; a suíte congela quarta 16/09/2026 às 12:00. Expectativa não nasce de
  "agora ± N horas" e nem de `if` sobre a hora.
- **Docstring diz POR QUE aquilo importa** — de preferência com o caso real que
  motivou o teste. Docstring que envelheceu junto com o código é defeito grave aqui.

---

## Síntese (você, depois dos três)

1. **Deduplicar** — o mesmo achado de dois revisores vira uma entrada, com a descrição
   mais afiada, anotando quem apontou.
2. **Filtrar** — fora o que não tem cenário de falha, o que o código já trata, e o que
   não corresponde ao diff de verdade. Confira cada um contra o `git diff`.
3. **Ordenar**, do mais grave ao menos. A ordem é só ordenação — a CLASSIFICAÇÃO
   continua sendo a do `nutriplan-qa`, e não se troca uma pela outra:
   - trava o merge: `BUG` de segurança ou de perda de dado;
   - depois: `BUG` de comportamento;
   - depois: `UX REAL`;
   - depois: `OBSERVAÇÃO` e `LIMITAÇÃO`;
   - `FALSO POSITIVO` fica na lista, dito como tal — ele é o registro de que alguém
     já olhou e refutou.
4. Relatório com arquivo:linha, a afirmação, o cenário de falha, a classificação, a
   evidência e quem apontou. Termine com **o que foi verificado e estava correto** —
   é o que diz ao leitor o que a revisão cobriu.
