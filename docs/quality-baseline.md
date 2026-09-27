# Linha de base de qualidade — 26/09/2026

**Este documento MEDE. Ele não conserta nada, e nenhuma refatoração foi feita nem
decidida a partir dele** — foi o pedido explícito do dono ao encomendá-lo. Ele existe
para que a decisão de mexer (ou de não mexer) seja tomada com número na mão, e para
que daqui a um mês dê para saber se a dívida cresceu ou encolheu.

- **Commit medido:** `b4258fe` (ponta de `origin/main` na data).
- **Universo:** só arquivo VERSIONADO (`git ls-files`). `.venv`, `__pycache__`,
  `artifacts/` e `node_modules` ficam de fora — contá-los mediria a máquina, não o
  projeto.
- **Ferramenta:** contagem de linhas própria e `grep`. **Sem ruff** — ele não está
  instalado neste repositório, e instalá-lo é decisão pendente do dono (D2 do plano
  `docs/superpowers/plans/2026-09-26-vibe-coding-toolkit.md`). Quando entrar, a
  contagem dele vira uma seção nova aqui.

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

## Como usar este documento

- Ele é **fotografia**, não catraca. Nenhum teste lê estes números hoje.
- Se um dia virarem catraca, o padrão do projeto é o de
  `config/test_design_system.py`: um teto que **não pode crescer**, com a medição
  escrita ao lado e a data.
- Remedir é rodar a mesma contagem sobre `git ls-files` e comparar commit a commit.
