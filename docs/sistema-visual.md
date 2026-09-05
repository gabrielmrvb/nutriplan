# O sistema visual do NutriPlan

Este documento existe para uma coisa: **uma tela nova nasce consistente sem
ninguém precisar lembrar de nada.** Se você está prestes a escrever
`font-size: .83rem`, pare e leia a seção 2.

Tudo aqui foi medido em 05/09/2026 contra `static/css/app.css`, com os
comentários removidos antes de contar — este projeto comenta muito, e o
comentário cita o nome da coisa que a medição procura.

---

## 1. O estado dos quatro eixos

O sistema não é uniforme, e fingir que é seria o começo do problema:

| eixo | tokens | travado por teste? | valores crus |
|---|---|---|---|
| **quina** | 5 | sim — `config/tests.py:614` | **0** |
| **cor** | 48 | sim — órfão e não-declarado | 8 |
| **espaço** | 7 + `--gap`/`--pad` | catraca | 242 |
| **texto** | 8 | catraca | 145 |

A lição que organiza tudo: **onde existe eixo E teste, a violação é zero.** O
raio não tem nem um valor cru em 6.300 linhas, e não é porque alguém teve mais
disciplina ao escrever quina — é porque `test_no_corner_is_written_in_a_raw_value`
recusa. Texto e espaço passaram anos sem eixo e acumularam centenas.

**Não crie um eixo novo sem criar a trava junto.** Um eixo sem teste vira
sugestão, e sugestão perde para pressa.

---

## 2. Texto

```
--texto-xs    .7rem     11,2px   rótulo, legenda, unidade
--texto-sm    .8rem     12,8px   texto de apoio (o mais usado)
--texto-md    .9rem     14,4px   corpo secundário
--texto-base  1rem      16px     corpo
--texto-lg    1.15rem   18,4px   subtítulo
--texto-xl    1.4rem    22,4px   título de seção
--texto-2xl   1.75rem   28px     título de tela
--texto-3xl   2.15rem   34,4px   número de destaque
```

**`--texto-xs` é o piso e não desce.** Texto de interface neste app nunca fica
abaixo de 11px, e há teste exigindo isso do degrau — baixá-lo rebaixaria a
legibilidade do produto inteiro de uma vez.

### Por que estes oito, e não outros

Não foram escolhidos por gosto. Cada um é um valor que o arquivo já usava
muito: `.8rem` aparecia 26 vezes, `.7rem` 16, `1rem` 10, `.9rem` 9.

Antes deles havia **41 valores distintos** em 214 declarações, sendo 20 deles
espremidos entre `.7rem` e `1rem` — incluindo `.74`, `.75` e `.76`, que são
11,8px, 12,0px e 12,2px. A diferença entre eles é invisível, e é essa
invisibilidade que prova que eram acidente: ninguém escolhe conscientemente
uma diferença que não dá para ver.

---

## 3. Espaço

```
--espaco-1  .25rem   4px
--espaco-2  .35rem   5,6px
--espaco-3  .5rem    8px     (o mais usado: 45 vezes)
--espaco-4  .7rem    11,2px
--espaco-5  .9rem    14,4px
--espaco-6  1rem     16px
--espaco-7  1.5rem   24px
```

**Não há `--espaco-8`.** Ele existiu por cinco minutos, porque `2rem` completava
a simetria da escala — e a medição disse que `2rem` não é usado como
espaçamento neste arquivo, zero ocorrências. Simetria não é evidência.

### `--gap` e `--pad` continuam existindo, e não são duplicata

```
--gap: 1rem      o vão padrão de uma pilha
--pad: 1.25rem   o respiro interno de um cartão
```

Eles dizem **para que serve**, não **quanto mede**. `--espaco-6` e `--gap` valem
o mesmo hoje, e ainda assim não são a mesma coisa: quem muda o ritmo de uma
pilha mexe em `--gap` e não quer mexer em todo espaço de 16px do app.

Regra prática: **se o espaço tem papel, use o token de papel; se é só medida,
use o degrau.**

---

## 4. A catraca — como trabalhar com ela

`config/test_design_system.py` guarda dois números: quantos valores crus de
texto e de espaço existem hoje (145 e 242). Ela falha em três situações:

- **a dívida subiu** — você escreveu valor cru. Use um degrau;
- **a dívida caiu e o teto ficou** — você migrou e esqueceu de baixar o número.
  Isso é falha de propósito: teto folgado deixaria entrar tanto valor cru quanto
  você acabou de tirar;
- **um degrau sumiu** da escala ou deixou de ser usado.

Por que catraca e não proibição, como o raio: quando os tokens nasceram já
havia 214 declarações de texto e 458 de espaço escritas à mão. Proibir de uma
vez exigiria reescrever milhares de linhas num commit só — a troca gigantesca
que quebra trinta telas de uma vez.

**Migrar é sempre bem-vindo e sempre barato:** troque um valor cru pelo degrau
mais próximo, rode, e baixe o teto.

---

## 5. O que já é componente, e o que ainda não é

### Tem fonte única

| partial | usos |
|---|---|
| `partials/field.html` | 18 — label, ajuda, widget, erro, olho de senha |
| `partials/marca.html` | 10 |
| `partials/choice_cards.html` | 4 |
| `partials/links_legais.html` | 3 |

`field.html` é o melhor exemplo do que este documento defende: ele já resolve
label + erro + ajuda num lugar só. **Mas só é usado em telas de `accounts/`.**
Oito lugares fora dele montam campo à mão — e nenhum desses oito renderiza erro
de campo.

### Repetido e ainda sem fonte única (medido)

| padrão | repetições |
|---|---|
| `<div class="card__head"><h2>…</h2>[<a>Editar</a>]</div>` | **37** em 13 arquivos |
| `btn btn--primary btn--block` | **27** |
| bloco "número + rótulo" | **24 blocos, em 8 famílias de nome diferentes** |
| `empty-state` | 13, em duas marcações |
| `page-head` | 11, em 4 variações |

O caso mais caro é o terceiro: `tile__value`/`fim__valor`/`equation__value`/
`drawer__numero-valor`/`corrida-numero__valor`/`conquistas__numero`/
`semana__valor`/`balance__value` são **oito nomes para a mesma ideia** — um
número grande com um rótulo embaixo. Só `tile` é reaproveitado entre dois
arquivos; as outras sete são exclusivas de um arquivo cada.

### Duplicação de primitiva no CSS

- `.chip` e `.pill` — duas pílulas, mesma receita, 7 usos somados;
- `.tile` e `.day-chip` — mesma superfície rebaixada, raios diferentes sem razão;
- `.modal::backdrop` e `.drawer::backdrop` — o mesmo preto translúcido escrito
  de dois jeitos (`rgba(0,0,0,.72)` e `rgba(4,8,7,.72)`).

---

## 6. Overlays: cinco mecanismos para o mesmo papel

| peça | mecanismo |
|---|---|
| drawer do exercício | `<dialog class="drawer">` + backdrop nativo |
| convite de instalação | `<div role="dialog" hidden>` — **não prende foco** |
| faixa da fila offline | `<div role="status" hidden>` |
| cronômetro de descanso | barra fixa + classe `--fim` |
| cartão de conquista | modelado no convite, não em modal |

Três deles são decisão declarada em comentário (barra fixa é melhor que modal
para o cronômetro, e o cartão de conquista não deve roubar foco). O que **não**
está resolvido é o convite de instalação ter `role="dialog"` sem prender foco —
um leitor de tela anuncia diálogo e o teclado sai dele.

Isto está registrado, **não corrigido nesta unidade**, e é candidato à próxima.

---

## 7. Ganchos de JavaScript — leia antes de renomear qualquer classe

Este projeto não usa `getElementById` em lugar nenhum: **todos os ganchos são
`data-*` ou nome de classe**. Renomear uma classe achando que é só estilo
quebra comportamento em silêncio, sem erro no console.

Os mais perigosos, porque estão no `<body>` e o service worker também os lê:

| gancho | lido por |
|---|---|
| `data-usuario` | `corrida.js:44`, `fila.js:92`, `pwa/sw.js:44,55,107` |
| `data-autenticado` | `pwa.js:289`, `pwa/sw.js:45,107` |
| `data-conta-excluida` | `fila.js:385` |
| `tem-convite` (classe) | `pwa.js:182,195` |

E dois acoplamentos **estruturais**, que quebram sem ninguém renomear nada:

- `pwa.js:333` faz `botao.parentElement.querySelector("input")` — o olho de
  senha PRECISA ser irmão do `<input>` dentro de `span.campo-senha`;
- `accounts/onboarding/step.html:177` usa o seletor `.card form` — o formulário
  precisa estar dentro de um `.card`.

A lista completa (mais de 80 ganchos, incluindo os `<script>` inline de
`routine.html` e `agora.html`) está no inventário do commit desta campanha.
**Antes de mexer em `workouts/routine.html`, leia-a**: aquele arquivo sozinho
tem ~40 ganchos lidos por script inline.

---

## 8. Tema: escuro é o padrão, e isso já está resolvido

Não confunda com "falta dark mode". É o contrário:

```css
:root { /* escuro */ }
@media (prefers-color-scheme: light) { :root { /* claro */ } }
```

O app nasce escuro porque é aberto na academia, e o claro é a exceção. Os dois
temas já existem e ambos passam contraste medido. **Não há decisão de dark mode
pendente** — há, no máximo, a decisão futura de oferecer um seletor manual em
vez de seguir só o sistema.

O cliente Android (`mobile/www/app.css`) é a exceção conhecida: ele tem sete
tokens próprios e é claro. Isso é dívida declarada, não descuido — ver a seção 9.

---

## 9. Dívida conhecida

- **145 tamanhos e 242 espaços crus** — a catraca segura o teto e desce quando
  alguém migra;
- **o cliente Android não usa este sistema.** `mobile/www/app.css` tem tokens
  próprios (`--tinta`, `--fundo`, `--marca`) e tema claro. São dois produtos
  visualmente diferentes hoje. Unificar é trabalho real e ainda não foi feito;
- **8 famílias de nome para "número + rótulo"**;
- **`.chip`/`.pill`, `.tile`/`.day-chip`** duplicados;
- **o convite de instalação diz `role="dialog"` e não prende foco**;
- **`.install` tem `box-shadow` declarado duas vezes** (`app.css`), e a primeira
  nunca pinta. É o único bloco do arquivo com propriedade repetida.

---

## 10. Ao criar uma tela nova

1. use `--texto-*` e `--espaco-*`; se nenhum degrau serve, o degrau que falta
   nasce com justificativa medida, não com um valor solto;
2. `{% include "partials/field.html" %}` para campo de formulário — ele já traz
   erro e ajuda, que oito lugares do app esqueceram;
3. `page-head` para o cabeçalho, `card` para superfície, `empty-state` para o
   nada;
4. número é `tabular-nums` e vírgula decimal;
5. todo container de texto leva `min-width: 0` — nada rola na horizontal;
6. alvo de toque 44px de **altura e largura**;
7. `:has()` é proibido para estrutura. Use classe escrita pelo servidor ou
   combinador de irmão, como `.segmented input:checked ~ .segmented__fundo`.
