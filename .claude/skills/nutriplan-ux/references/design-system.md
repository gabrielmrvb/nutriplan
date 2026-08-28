# O design system do NutriPlan como ele é hoje

Levantado do código, não da documentação. Serve para uma coisa: impedir que a
análise de UX proponha componente que já existe, ou reabra decisão já medida.

Se algo aqui divergir do código, **o código ganha** — e a divergência entra na
análise como achado.

Complementa, não repete: o `CLAUDE.md` traz as decisões de projeto, o
`references/produto.md` da skill `nutriplan-product` traz o inventário de
funcionalidades. Aqui está a camada de interface.

---

## 1. Onde tudo mora

Um arquivo: **`static/css/app.css`**, ~4.570 linhas, **35 seções numeradas**, lido
de ponta a ponta. Sem framework, sem build step, sem Node.

A ordem das seções é a ordem em que a tela é montada: tokens → reset → shell →
tipografia → cartões → componentes de tela. Uma mudança de UX quase sempre cai
dentro de uma seção existente; precisar de seção nova é sinal de que o padrão
não foi encontrado.

JavaScript: `static/js/pwa.js` (service worker, convite de instalação) e
`static/js/fila.js` (fila offline). O resto do comportamento é inline nos
templates.

---

## 2. Tokens

Cor (escuro é o padrão; há bloco `prefers-color-scheme: light`):

```
--bg #0d0f12   --surface #15181e   --surface-2 #1a1d24   --surface-3 #232733
--border #2a2e39            --border-strong #3a4050
--text #ffffff  --text-dim #cbd2dc  --text-mute #9ca3af
--brand #10b981  --brand-strong #34d399  --brand-soft #103028  --on-brand #04140e
--accent #6cc7ff  --warm #f59e0b  --danger #ff8a80
--carb #e0b25f   --fat #8fa8d8
--dia-a … --dia-e   uma cor por dia de treino (A verde, B azul, C âmbar, D violeta, E coral)
```

Forma e profundidade:

```
--radius-xl 26px   --radius-lg 20px   --radius 15px   --radius-sm 11px   --pill 999px
--edge      fio de luz na quina de cima
--inlay     contorno por dentro, para bloco afundado sem borda
--halo      halo de ESTADO (aba atual, refeição feita, botão sob o dedo)
--glow      halo de FOCO
--shadow-rest / --shadow-lift / --shadow-deep
--glass + --glass-blur   vidro das barras flutuantes
--grad-brand             gradiente da marca
```

Movimento, espaço e tipo:

```
--ease cubic-bezier(.2,.8,.3,1)   --dur .2s
--gap 1rem   --pad 1.25rem   --max 30rem   --tabbar-h 4.5rem
--font (system-ui)   --font-mono
```

**Nenhuma cor ou raio escrito à mão.** `DesignSystemTests` trava isso: cor de
acento, raio de quina e tratamento de texto são globais por definição.

Escala tipográfica: `h1` 1.65rem/750 · `h2` 1.08rem/680 · `h3` .95rem/650 ·
`.lead` .93rem · `.muted` .875rem · `.hint` .8rem. Piso de 11px para texto de
interface. `.num` aplica `tabular-nums`.

---

## 3. Componentes que existem

Antes de propor um novo, procure aqui.

**Shell** — `.app-bar` (topo, vidro), `.tabbar` (5 abas, vidro, fixa embaixo),
`.container` (largura máxima 30rem).

**Superfície** — `.card`, `.card__head`. Widgets de destaque usam `--radius-xl`.

**Ação** — `.btn` com `--primary`, `--ghost`, `--quiet`, `--perigo`, `--sm`,
`--block`; `.btn-link` (link com alvo de 44px por padding negativo).

**Etiqueta** — `.pill` (`--brand`, `--mute`, `--warm`), `.chip` (`--brand`),
`.chip-row`.

**Formulário** — `.field-input`, `.field__label`, `.field__help`,
`.field__errors`, `.choice-list`, `.choice-card` (cartões de escolha do
onboarding), `.segmented` (controle segmentado), `.campo-senha` (senha com olho).

**Dado** — `.data-list`, `.progress` + `.progress__fill`, `.macro-bar`,
`.hero-macros`, `.equation`, `.tile`, `.history-row`, `.ring` (anel de
progresso do dia).

**Dieta** — `.today-hero`, `.meal` + `.option` (sanfona de opção),
`.fora` ("comi outra coisa"), `.shopping`, `.agua`, `.ofensiva`.

**Treino** — `.exercise` (sanfona por exercício), `.registro` (registro de carga:
um por **exercício**, não por série — medidas na seção 7), `.ficha` (sanfona da
semana), `.session`, `.rest-timer` (barra flutuante de descanso), `.drawer`
(execução do exercício), `.semana`.

**Estado e retorno** — `.flash` (mensagem do servidor), `.callout`,
`.empty-state`, `.hint`, `.esqueleto` (carregando), `.fila` (faixa de pendências
offline).

**Outros** — `.install` (convite de instalação), `.supl`, `.metas`,
`.demo-area`, `.montagem` (montagem do plano).

---

## 4. Padrões de comportamento

**Sanfona é `<details>`/`<summary>`.** Três usos: ficha da semana, exercício,
opção de refeição. Traz de graça teclado, leitor de tela, Ctrl+F do navegador, e
funciona antes de o JavaScript carregar. Componente novo que abre e fecha deve
seguir isto, não reimplementar com `div` e classe.

**Feedback é mudança de estado no próprio elemento.** Não há toast no app, e é
decisão. A série marcada muda de aparência, a barra cresce, a etiqueta troca de
cor. `.flash` cobre a mensagem vinda do servidor.

**O que muda sem recarregar usa `role="status"` + `aria-live="polite"`.** Três
lugares hoje: fila offline, cronômetro de descanso, montagem do plano.

**Tudo que se toca responde ao toque.** `TouchFeedbackTests` existe porque uma
auditoria achou onze clicáveis sem retorno — inclusive as sanfonas, que são os
elementos mais tocados. O padrão é `transform: scale(.98)` no `:active`, sempre
com saída em `prefers-reduced-motion` (20 blocos no arquivo).

**Escrita offline vai para a fila.** Água, suplemento, marcação de refeição e
carga. Ação nova que escreve precisa decidir se entra nesse contrato.

---

## 5. Decisões de UX travadas em teste

Não são gosto. Cada uma tem cicatriz, e mexer nelas quebra a suíte.

| Trava | O que protege |
|---|---|
| `TouchTargetTests` | 44px de altura **e** largura. Mede as duas — 26px de largura com 44 de altura já passou. Lista explícita inclui `.registro__carga`, `.registro__salvar`, `.registro__timer`, `.rest-timer__more`, `.rest-timer__close`, `.shopping__check`, `.btn-link`. |
| `ContrastTests` | Razão WCAG recalculada dos tokens, inclusive contra fundos tingidos (`--brand-soft` e companhia). |
| `PillContrastTests` | Texto de pílula medido sobre a própria tinta a 12%, não sobre a superfície nua — a tinta clareia o fundo e come o contraste. |
| `DayColourContrastTests` | As cinco cores de dia de treino, legíveis e distinguíveis. |
| `DesignSystemTests` | Paleta e layout globais; nada de cor ou raio à mão. |
| `MotionTests` | As animações que carregam informação (barra que cresce, botão que afunda) e a saída para movimento reduzido. |
| `TouchFeedbackTests` | Todo clicável responde ao dedo, e responde igual. |
| `HasSelectorTests` | `:has()` não decide layout. |
| `GymReadyTests` | Um destaque só por tela; fio de acento só em cartão de destaque; cor de token. |
| `GymHardwareTests` | Recursos do aparelho usados na tela de treino. |
| `LoadStepperTests` | Degraus de **2,5 kg** — é o que a anilha pesa e como ela entra aos pares. |
| `RestBadgeTests` | Descanso escrito como relógio ("1:20"), não "1min20". |
| `ExerciseHeaderLayoutTests` | O cabeçalho do exercício, medido. Nasceu de três defeitos com a mesma forma: a regra de CSS continuou descrevendo um elemento que o HTML deixou de ser — o rótulo de 24 caracteres dentro de um círculo de 44px quebrou em sete linhas e inflou o cabeçalho de 98px para 364px por cartão. |
| `ImpeccableStyleTests` | O catálogo de anti-padrões de UI gerada por IA. |
| `VisualRefinementTests` | Quina em token, halo de estado único, transição em `--dur`/`--ease`, saída de movimento para todo estado de toque. |

**A lição do `ExerciseHeaderLayoutTests` vale como método:** quando propuser
mudar um elemento, verifique se a regra de CSS que o descreve continua
descrevendo o que ele passou a ser. A maior parte dos defeitos visuais deste app
nasceu dessa dessincronia, não de má escolha estética.

---

## 6. Breakpoints

```
max-width: 22rem   telas estreitas (anel e tipografia encolhem)
max-width: 26rem
min-width: 30rem   cartões de escolha em duas colunas
min-width: 40rem
min-width: 60rem   desktop: some a tabbar, os links sobem para a barra de cima
```

O alvo de projeto é **~390px**. O desktop é acomodação, não destino.

---

## 7. Medições de referência

Números tirados da página renderizada a **390×844**, com o aviso do demo
removido do DOM para reproduzir o que o usuário autenticado vê. São fatos com
data, não hipóteses — e por isso podem ficar velhos: **remeça antes de citar**.

Onde investigar primeiro é assunto do `SKILL.md`, na seção de heurísticas. Aqui
só entra o que foi medido.

**Medido em 28/08/2026, na produção.**

### Moldura

| | |
|---|---|
| Barra de cima (`.app-bar`) | 61px, sticky |
| Barra de abas (`.tabbar`) | 68px, fixa |
| Região visível sem rolar | y 61 → 776 (**715px úteis**) |

### Painel do dia

| Bloco | Topo (px) | Altura |
|---|---|---|
| `.ofensiva` | 78 | 99 |
| `.card.today-hero` | 209 | 267 |
| `.agua` | 508 | 158 |
| Título "Seu cardápio de hoje" | 685 | 28 |
| Primeira `.meal` | **740** | 148–355 |
| `.split__aside` (5 cartões de consulta) | 2476 | 1837 |
| Página inteira | — | **4310** (5,1 telas) |

Sem rolagem horizontal. Todos os alvos ≥44px.

### Linha de registro de série (`.registro`)

Duas faixas, e a disposição é resultado de medição registrada três vezes no
template — sete controles não cabem numa faixa só em 390px.

```
grid-template-columns: 52px 126px 52px
grid-template-areas:   "menos  carga   mais"
                       "salvar salvar  timer"
gap: 8px        largura total: 272px        altura: 148px
```

| Controle | Medida |
|---|---|
| `.registro__campo` (carga, rótulo "Carga") | 126×65 |
| `.registro__passo` (−2,5 / +2,5) | 52×44 cada |
| `.registro__salvar` — **é o contador**, texto "OK 4/4" | 186×51 |
| `.registro__timer` | 52×44 |
| "desfazer última série" (`.btn-link`) | 132×44 |

Um `.registro` por **exercício**, não por série: um toque em OK registra uma
série e o contador anda. O campo aceita vírgula (`type=text` +
`inputmode=decimal`). Abaixo, `.exercise__previous` traz o último treino com
delta ("Último treino (21/08): 82,50 kg · ▲ +2,50 kg").

### Cronômetro de descanso (`.rest-timer`)

390×71, fixa, vidro (`--glass` + blur 20px), `role="status"` +
`aria-live="polite"`. Número a 32px/780 com `tabular-nums`. `+30s` 62×44,
parar 44×44. Não cobre a tabbar. Parte sozinho ao salvar a série.

### Onboarding

5 passos, uma rota (`/conta/onboarding/<step>/`) despachando para cada. A ordem
é dados corporais → objetivo → dias de treino → divisão → comida; a divisão vem
depois dos dias porque a resposta depende da frequência.

*(O produto não coleta métrica de conclusão ou abandono. Qualquer afirmação
sobre onde as pessoas desistem seria invenção.)*
