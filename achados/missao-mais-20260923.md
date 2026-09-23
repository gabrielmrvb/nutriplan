# Missão Mais — a tela `/areas/` deixa de ser "o que sobrou" (23/09/2026)

Branch `design/mais`, base `origin/main` (`6f570f0`). Sessão do Claude (Cowork),
num ambiente próprio — Postgres 16 local, suíte e navegador (Playwright,
Chromium) rodados aqui; **push, PR, fila e deploy não foram feitos** porque
esta sessão não tem as credenciais nem a máquina do dono (ver "O que preciso
de você").

Fecha os itens 11–15 do prompt de Progresso/Mais que a missão anterior
(PR #137) deixou intactos e declarou no relatório.

## O que a pessoa via, e o que vê agora

Antes (produção `e6194b7`, conta de 3 dias, 390 e 1280 px, dois temas —
capturas `antes-*.png` em `achados/capturas-mais-20260923/`): título
"ÁREAS SEM ABA"; seis cartões do mesmo tipo com pesos desiguais — Corrida e
Hidratação com número, Conquistas com número, Lista de compras só com uma
frase, o Perfil como "2.372 kcal por dia · manter o peso" atravessando a
grade, e Ajuda como um cartão largo quase vazio.

Agora (capturas `mais-*.png`, mesmos tamanhos e temas):

1. **Identidade no topo** — inicial num círculo da marca, nome (ou e-mail,
   quando o cadastro não tem nome), "emagrecer · 2.055 kcal por dia", e a
   linha inteira é a porta do Perfil ("Editar perfil ›"; a 390 px só a seta,
   para o nome ter a largura). Sem plano ativo a linha diz só o objetivo.
2. **"Suas áreas"** no lugar de "Áreas sem aba". Os cartões de Corrida e
   Hidratação continuam cartões (têm número vivo) e ganham a ação no rodapé
   ("Ver corrida ›", "Ver hidratação ›").
3. **Ferramentas como lista de linhas** — ícone, rótulo, detalhe, seta —
   dentro de um cartão: Conquistas ("1 conquista · última: Primeiro treino"),
   Lista de compras, Ajuda. Nenhum cartão sem número.
4. **Conta como lista** — Perfil e "Sair da conta" (formulário POST, como o do
   topo; no celular a barra de cima não tem Sair, e esta é a linha dele).
5. **Desktop em duas colunas** (≥ 60 rem): áreas à esquerda, listas à
   direita. Celular: uma coluna, linhas de 56 px.

Custo da tela: **as mesmas 8 consultas** (`OCustoDaTelaDeAreasEstaMedidoTests`
intacto) — a identidade sai de `request.user` e do fato do plano que o Perfil
já calculava. Lista de compras e Lembretes ficaram sem contagem de propósito:
cada número ali seria uma consulta nova.

## Medido no navegador (Playwright, Chromium, `scratchpad/qa/prova_mais.py`)

| vista | axe (wcag2a+aa) | altura | rolagem horizontal | alvo < 44 px | texto < 11 px |
|---|---:|---:|---|---:|---:|
| 390 / escuro | 0 | 844 → **1.016** | não | 0 | 0 |
| 390 / claro | 0 | 844 → 1.016 | não | 0 | 0 |
| 1280 / escuro | 0 | 900 → 900 | não | 0 | 0 |
| 1280 / claro | 0 | 900 → 900 | não | 0 | 0 |

A altura a 390 px cresceu 172 px: a tela ganhou a identidade e a linha de
Sair, que não existiam. Cada linha custa 56 px e responde uma pergunta.

## Testes

- `accounts/test_areas.py`: quatro testes reescritos para a forma nova
  (identidade abre a tela e diz a meta; inicial e nome vêm do usuário e caem
  no e-mail; ferramentas e conta são listas e não cartões; o rótulo fala com
  a pessoa) e dois ajustados (conquistas responde no apoio; sem plano a
  identidade diz o objetivo). `entradas()` passou a ler `.identidade`.
- `achievements/test_integracao_progresso.py` e `ajuda/tests.py`: as
  asserções que liam `modulo__nome` passaram a ler a linha (`mapa__nome`).
- Suíte dirigida verde (accounts.test_areas, config.tests, design_system,
  movimento, nomenclatura, ajuda, achievements): 220 testes.
- **Sabotagem 5/5 vermelha**: rótulo de volta a "Áreas sem aba" ·
  `.identidade` renomeada · Sair sem `action` · `.identidade` fora da lista
  de toque · inicial fixa em "?". Cada uma derrubou o teste que a guarda.
- **Suíte completa: 4.391 testes, 3 falhas — as três em login com Google**
  (`DestinoNoLoginSocialTests` ×2 e `AsContasConectadasUsamAcaraDoProdutoTests`),
  e as três falham IGUAL na `main` intocada neste ambiente (`git stash` e
  rodar de novo): é o `.env` daqui sem as chaves do Google, não esta branch.
  O CI, com os segredos, é quem responde por elas.
- `manage.py check`, `makemigrations --check`, `git diff --check`: limpos.

## Decisões que tomei sozinha

- **Lista onde não há número, cartão onde há.** A doutrina de 12/09 tirou a
  lista de Áreas porque "parecia Configurações" — e valia para as ÁREAS. Para
  ferramentas e conta a lista é a forma certa (é o "Mais" de qualquer app), e
  o dono viu os cartões vazios em produção. Está no comentário do template.
- **Ícones inline por linha** (troféu, carrinho, ajuda, pessoa, sair) em vez
  de mexer no sprite de 13 símbolos: o sprite é fechado e nenhum símbolo dele
  dizia "conquista" ou "sair". Mesmo padrão dos cartões da Home.
- **"Sair da conta" em vermelho (`--danger`)** — é a única ação destrutiva da
  tela e a cor a separa das navegações.
- **Sem cantos parciais** nas linhas: a régua `test_nothing_is_a_pill`
  proíbe raio fora dos slots; as linhas ficam com o raio inteiro e o cartão
  dá a moldura.
- **Nada novo no design system**: só tokens, nenhum valor cru de texto ou
  espaço (as catracas ficaram nos mesmos 109 e 230).
- Corrida e Hidratação continuam listadas aqui, como a decisão de 22/09 já
  dizia: quem não declarou a área não tem outro caminho até ela.

## O que preciso de você

Esta sessão não tem a sua máquina nem as suas credenciais — as quatro
condições não foram tocadas, mas a cadeia depois do commit passa por elas:

1. **Push da branch e PR.** A branch `design/mais` está commitada aqui e vai
   como `design-mais.bundle` + `design-mais.patch`. Na sua máquina:
   `git fetch <caminho>/design-mais.bundle design/mais:design/mais` (ou
   `git am design-mais.patch`), depois `scripts/github.py pr design/mais
   "Mais: identidade, áreas e listas"` e `enfileirar`.
2. **Ou ligue esta sessão ao seu computador** (Claude desktop → "Link to
   this computer"): com o repositório, o venv e o `github.py` alcançáveis, eu
   faço o push, a PR, a fila e o QA em produção daqui, sem passo seu.
