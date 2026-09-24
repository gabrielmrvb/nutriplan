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

## Autonomia

**DECIDA E REGISTRE (regra permanente, 17/09/2026).** Uma sessão só para e
pergunta quando UMA das quatro condições vale:

1. **gasta dinheiro novo** — plano do Render, serviço pago, API cobrada;
2. **apaga ou altera dado de usuário real em produção**;
3. **muda direção visual ou de produto que ainda não está escrita** em
   `DESIGN.md` / `TREINO.md`;
4. **precisa de credencial que não existe no ambiente**.

Tudo o mais — escolha técnica, ordem de execução, defaults de infra,
tolerância de teste, rótulo de texto, nome de campo, parâmetro de motor —
decide com o melhor padrão, registra em **"Decisões que tomei sozinha"** com
uma linha de razão, e segue. Vetos vêm depois, no relatório; nunca antes.

**Padrões já decididos — não perguntar de novo:** superpowers em toda missão
· TDD + sabotagem 100 % vermelha + revisão adversarial + suíte · o gate é o
CI, fluxo branch → PR → FILA (`scripts/github.py enfileirar`: a fila
local desta máquina, porque a do GitHub só existe em organização; merge
commit; `strict` intacto)
· deploy provado por `/saude/` + smoke + QA em produção com conta descartável
pelo signup público, conta apagada pela tela, demo intacto — **a conta de QA
descartável é do AGENTE (decisão do dono, 18/09/2026): a sessão cria pelo
signup público, com e-mail claramente de QA (`qa-<sessão>-<data>@nutriplan.invalid`),
senha só para aquela conta, nunca no relatório; obrigação de APAGAR pela
tela ao terminar e provar que sumiu (login recusado). Nunca a conta pessoal
do dono. Sessão cujo ambiente proíba criar conta ou digitar senha diz isso
no relatório e prova o que der pelo `/demo/`** · `scripts/qa/
nav.py` (CDP) para navegador, inclusive sites de terceiros na sessão logada do
dono (Render, GitHub, claude.ai) · mídia de exercício ativa com curadoria e
mosaico para veto posterior · plano ativo antigo nunca remonta sozinho · o
teste dourado da ficha nunca afrouxa · spec (`DESIGN.md` / `TREINO.md`) vence
proposta externa, e a divergência vai para "recomendo rever" · segredo nunca
no repositório nem no relatório.

**Relatório:** "O que preciso de você" só lista itens que caem nas quatro
condições. Lista vazia se escreve "nada" — e a sessão vai para o próximo item
do plano mestre sem esperar.

**Coordenação entre sessões:** antes de tocar arquivo em comum, a sessão
avisa as outras pelo ledger compartilhado — `C:\Users\biel-\nutriplan-ledger.md`,
fora de qualquer worktree, uma linha por aviso (`data hora · sessão · arquivo
· o que vai fazer`), lido antes de editar e escrito antes de commitar. Conflito
de merge é resolvido por quem faz o rebase.

## Rodar

```bash
.venv/Scripts/python.exe manage.py test          # suíte completa (~20 min)
bash scripts/instalar_hooks.sh                   # liga as travas de git
```

O PostgreSQL é portátil (`C:\Users\biel-\pgsql`, cluster em
`C:\Users\biel-\pgdata\nutriplan`) e **não sobe sozinho depois de reiniciar** —
`pg_ctl start` antes de qualquer coisa.

**PODA SEMANAL DE WORKTREES E BANCOS DE TESTE (toda segunda, 21/09/2026).**
Cada sessão nasce num worktree e cada suíte interrompida deixa um
`test_nutriplan_*`; medido em 21/09, 46 worktrees registrados e 18 bancos
órfãos. A poda é `scripts/worktrees.py`, dry-run por padrão:

```bash
.venv/Scripts/python.exe scripts/worktrees.py --podar              # relatório: o que sairia, nada apagado
.venv/Scripts/python.exe scripts/worktrees.py --podar --executar   # apaga, prune, e diz antes/depois em GB
```

**Sai** o worktree cuja branch está MERGEADA em `origin/main`, ou que NÃO
EXISTE mais no origin, ou que está DESTACADO (os descartáveis do pre-push
e da fila) — sempre com a árvore LIMPA. **Fica** o checkout principal, o
worktree de onde o script roda, o trancado (`git worktree lock`), o com
mudança não commitada e todo worktree citado no ledger nas últimas 12 h
(`--ledger-horas`): sessão ativa é quem escreveu no ledger hoje. **Sai** o
banco `test_nutriplan_*` com ZERO conexões em `pg_stat_activity` (suíte
viva está conectada); o `nutriplan` de desenvolvimento não entra. E a
guarda que a primeira execução quase não teve: quase todo worktree tem
`.venv` como JUNÇÃO para o venv compartilhado do checkout principal —
`os.walk` contava 0,18 GB por worktree de 0,02 e um `rmtree` ingênuo
apagaria o venv de todo mundo. O script desliga toda junção/symlink
(`desligar_links`, só a entrada) ANTES de `git worktree remove --force`, e
`config/test_worktrees.py` prova com junção real que o alvo fica. O
relatório mede o disco livre antes e depois — o número honesto, não a soma
dos tamanhos.

## Apps

| app | o que guarda |
|---|---|
| `accounts` | usuário, perfil, peso, dias de treino, `SyncedOperation` |
| `catalog` | alimentos e receitas (TACO/IBGE/USDA) |
| `plans` | motor nutricional, cardápio, hidratação, ofensiva, voz |
| `workouts` | ficha, cargas, catálogo de exercícios, exportação de saúde |
| `push` | service worker, manifesto, notificações |

(A `api` — token, eu, corridas — e o cliente `mobile/` saíram em 20/09/2026
por decisão do dono: a Fase 1 da Corrida mobile ficou sem cliente que o
ambiente consiga construir. `TracoDaCorrida` fica: a importação de GPX/TCX
usa. O contrato antigo está no histórico do git, em `docs/api-v1.md`.)

## Decisões que já foram tomadas — não refaça sem motivo

**Sem framework de CSS.** Um arquivo, `static/css/app.css`, lido de ponta a
ponta, com seções numeradas. Tokens no topo. Nada de Tailwind, nada de build
step. **A cópia SERVIDA perde os comentários no `collectstatic`** (decisão
do dono, 20/09/2026; `config/estaticos.py`, `config/test_estaticos.py`): a
auditoria mediu 340 067 bytes na folha, 60 % de comentário, 106 KB gzip na
primeira visita — e 23 KB sem eles; a cobertura por CDP mostrou que 87 % dos
bytes de regra são usados, então o peso não era CSS morto. A fonte é o que
se edita e continua comentada; o hash no nome é o do conteúdo servido.

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

**O NutriPlan tem CINCO PILARES, e "Hoje" não é um deles.** Alimentação,
Treino, Corrida, Hidratação e Progresso estão no mesmo nível conceitual —
`accounts.models.Pilar`. Hoje é o orquestrador do dia; Perfil é utilitário. A
navegação DIZIA o contrário: a tela de água acendia a aba "Dieta" e a de
corridas acendia "Treino". Hoje `nav` tem `hydration` e `running`, e nessas
telas NENHUMA aba acende — melhor que acender a errada. Quem orienta é o mapa.

**Uma área, um nome — e o nome mora em `Pilar.label`.** O padrão oficial é
**Alimentação · Treino · Corrida · Hidratação · Progresso**. O produto já teve
TRÊS vocabulários: a barra dizia "Dieta/Treino/Progresso", o mapa e o
onboarding diziam "Alimentação/Musculação/Evolução", e a documentação chamava o
quinto de "Progresso" — com os dois primeiros visíveis AO MESMO TEMPO no
celular. `DETALHES` não escreve mais o nome: ele lê o label, e guarda só o que
o modelo não tem (ícone e frase de apoio). `config/test_nomenclatura.py` compara barra e
mapa POR DESTINO — e onboarding, Perfil e gestão por presença dentro do recorte
da seção, que é mais fraco e está dito aqui para ninguém confiar demais. A capa
do demo escreve os cinco nomes à mão em `demo/views.py` e **não tem teste**;
renomear um pilar deixa ela para trás em silêncio.

O `value` **não** acompanhou o rótulo, e a separação é a prova de que os dois
planos são independentes: `Pilar.DIETA` continua valendo `"dieta"` enquanto a
tela diz "Alimentação". O valor está em banco, no `CheckConstraint`, nas chaves
de `CAMPO_DO_PILAR` e no `name` do formulário — renomear a tela não migra dado
nenhum, e a `0025` é no-op no PostgreSQL.

E a régua protege NOME DE PRODUTO, não palavra: "dieta", "musculação" e
"evolução" continuam livres em texto educativo. Um teste que varresse a página
atrás delas transformaria padronização em censura de vocabulário — o app diz
"sua dieta calculada" na descrição e "não é prescrição" no texto da água.

**A barra de baixo responde FREQUÊNCIA; o mapa responde ESTRUTURA.** São
perguntas diferentes, e por isso não competem pelo mesmo espaço. A barra tem
QUATRO itens e a conta é medida: a 320px, cinco colunas deixam 51,8px úteis por
item e "Hidratação" precisa de 60. O mapa
(`templates/partials/mapa_de_areas.html`, um `<details>` na barra de cima) lista
os cinco pilares, marca a área da vez com `aria-current` e põe um selo na área
principal da pessoa. Ele **não** reordena por pessoa: um mapa que muda de ordem
é um mapa pior, porque existe para mostrar de que o app é feito — e isso é igual
para todo mundo.

Três ausências no mapa são decisão, e as três foram achadas por revisão
adversarial ANTES de virarem defeito em produção:

- **não tem ícone**: o sprite dos cinco desenhos (`partials/icones.html`, 4 KB)
  só é incluído no onboarding, e copiar os desenhos é o que o sprite existe para
  impedir;
- **não entra no shell de offline**: aquela tela é pré-cacheada e servida a quem
  pegar o aparelho depois, e o selo de área principal é identidade — o mesmo
  motivo de `data-usuario` sair de lá. Duas camadas: o `{% if %}` no `base.html`
  e a tag se recusando a ler o perfil;
- **não aparece no onboarding**: a barra de baixo já é desligada lá porque os
  destinos devolvem quem não terminou, e o mapa reintroduzia os mesmos — sendo
  que `workouts:corridas` tem só `LoginRequiredMixin` e era saída DE VERDADE no
  meio do cadastro. O mesmo `sem_tabbar` desliga os dois.

E o endereço sai de `{% url %}` passando por `_endereco()`, que traduz a raiz do
demo: `plans:today` mora em `path("")`, então sob `set_script_prefix("/demo/")`
ele reverte para `/demo/` — que **não** é a tela Hoje, é a capa. O mapa mandava
quem estava avaliando o produto para a página de marketing e ainda anunciava
"você está aqui" ao fazê-lo.

**A TELA "MAIS" (`/areas/`) ABRE COM A PESSOA, E A FORMA SEGUE O DADO
(23/09/2026).** Ela era seis cartões do mesmo tipo com pesos desiguais sob o
rótulo "Áreas sem aba" — que descreve a ARQUITETURA, não o que a pessoa tem:
Corrida e Hidratação com número, Ajuda um cartão largo quase vazio, e o
Perfil aparecendo como "2.372 kcal por dia". Hoje:

- **a primeira linha é a identidade** (`.identidade`): inicial num círculo,
  nome — ou o e-mail, quando o cadastro não tem nome —, objetivo e meta do
  dia, e a linha inteira é a porta do Perfil. Sem plano ativo ela diz só o
  objetivo, porque inventar a meta seria afirmar um número que não existe;
- **cartão onde há número, LISTA onde não há.** A doutrina de 12/09 tirou a
  lista das ÁREAS porque "a tela parecia Configurações", e ela continua
  valendo para as áreas: Corrida e Hidratação seguem em cartão, com a ação
  no rodapé. Ferramentas (Conquistas, Lista de compras, Ajuda) e Conta
  (Perfil, Sair) são linhas de navegação — ícone, rótulo, detalhe, seta —,
  que é a forma certa para o que não tem número e é o "Mais" de qualquer
  app. Cartão vazio era o defeito que o dono viu em produção;
- **"Sair da conta" é POST e é o único `<form>` do `<main>`** (há teste), em
  `--danger` porque é a única ação da tela que encerra alguma coisa. No
  celular a barra de cima não tem Sair, e esta é a linha dele;
- **desktop em duas colunas** (≥ 60rem): áreas à esquerda, listas à direita.
  Numa coluna só, a 1280, os dois cartões de área viravam faixas com o
  número num canto e vazio no resto;
- **mesmas 8 consultas** (`OCustoDaTelaDeAreasEstaMedidoTests`): a identidade
  sai de `request.user` e do fato do plano que o Perfil já calculava. Lista
  de compras e Lembretes ficaram SEM contagem de propósito — cada número ali
  seria uma consulta nova;
- os ícones das linhas são **inline**, e não do sprite de 13 símbolos: ele é
  fechado e nenhum símbolo dele dizia "conquista" ou "sair".

**A Home organiza pela área principal, e o AGORA continua sendo o primeiro
bloco.** A prioridade declarada move UMA seção para o alto da tela de Hoje,
logo abaixo do resumo do dia — e nunca acima do cartão AGORA. Urgência vence
preferência: refeição vencida e treino em andamento têm hora marcada, e a hora
passa; a área preferida continua verdadeira amanhã.

Hidratação é a única que tem para onde subir — as refeições já são a primeira
seção de área. Ela sobe por `{% include "plans/_agua.html" %}`, com DOIS pontos
de chamada e um `{% if %}` em cada: o markup existe uma vez e a página emite uma
vez. Copiar o bloco quebraria de dois jeitos concretos — `id="hidratacao"` é
âncora de link e viraria ambíguo, e a página passaria a ter dois formulários de
registro com os mesmos nomes. **Não é `order` do flexbox**: `.split__main` é
flex, e `order` moveria o cartão na pintura deixando a ordem de leitura e de
foco onde estavam (WCAG 1.3.2 e 2.4.3).

Treino, Corrida e Progresso não têm seção própria na Home — não porque já
estejam no topo, mas porque a tela nunca falou deles. Os três ganham
`plans/_area_promovida.html`, um cartão com um fato real do dia e a porta para a
área. Treino sai de `estado_do_treino`, que a Home já calcula; Corrida e
Progresso custam UMA consulta cada, e só para quem declarou aquela área.

**SÓ A REFEIÇÃO DA VEZ NASCE ABERTA NA HOME (decisão do dono, 20/09/2026).**
Desde 12/09 a futura ficava atrás de "Ver opções"; a VENCIDA continuava
aberta por ser "ação em aberto", e a auditoria de 20/09 mediu o preço: um
primeiro uso às 15 h dava 3 757 px com quatro refeições abertas × quatro
botões, e um fixture às 18 h, 3 530 px — a tela mais aberta do app rolando
por formulários que ninguém ia usar naquele momento. Hoje `slot.marcador
!= "agora"` vai para o mesmo `<details class="meal__futuro">`, e a vencida
diz "Não registrada · registrar" no `summary`. Medido no protótipo: 3 530 →
2 875 px com duas vencidas. `plans/test_opcoes_tocaveis.py` cobra a ordem —
fora da vez, o `<details>` abre antes da primeira ação.

**UMA REFEIÇÃO PARECE UMA REFEIÇÃO — O CARD, A RECEITA E A PORÇÃO
(23/09/2026).** A auditoria daquele dia mediu o cardápio: "horário, nome,
alvo e um link *Ver opções*; fechado, um retângulo vazio. Aberto, cada opção
é UMA LINHA seguida de um REGISTRAR A gigante". O que decide uma escolha de
comida — do que é feita, quanto rende, quanto demora, como se faz — estava no
banco e fora da tela: os ingredientes com quantidade já existiam (a lista de
compras é feita deles).

- **O ESTADO DA REFEIÇÃO VEM DO SERVIDOR NUMA PALAVRA.** `plans/agora.py`
  escreve `slot.estado` ao lado do `marcador`: `resolvida` · `agora` ·
  `pendente` · `futura`. A tela desenha quatro coisas a partir dela e não
  recalcula nada (`test_o_template_nao_recalcula_quem_e_a_vez`). **Só a
  `agora` nasce aberta** — a decisão de 20/09 sobre a Home compacta vale
  para a vencida também, e esta reforma quase a desfez: com cards de receita
  no lugar das linhas, abrir `pendente` poria dois cardápios na tela às 15h.
  Quem segurou foi `test_a_vencida_fica_em_uma_linha_com_o_convite_a_registrar`.
  Fechada, a refeição é UMA LINHA (hora · nome · alvo, ou "Não registrada ·
  registrar"): 150 → 86 px, medidos a 390.
- **A opção é um CARD DE RECEITA**, não uma linha com sanfona: ilustração,
  nome, caloria, os TRÊS macros, tempo e os ingredientes com a porção numa
  linha (`MealOption.resumo_dos_itens`, sobre o `prefetch_related` que a tela
  já fazia — zero consulta nova). A linha ABREVIA a medida ("6,5 col. de
  sopa"); a receita escreve por extenso. O rótulo A/B **saiu da interface** —
  é nome interno do rodízio; `OptionLabel` continua no banco e na lista de
  compras. O CTA é "Comi esta", e só a sugestão do dia é verde.
- **A RECEITA É UM MARKUP SÓ EM TRÊS LUGARES** (`templates/plans/_receita.html`):
  a tela `/refeicao/<slot>/receita/<opcao>/`, a folha do celular e o painel
  da direita no desktop. A folha e o painel são a seção `#receita`
  RECORTADA da página buscada — a mesma mecânica de "Outras formas" na ficha
  do treino —, e `pwa.js` escolhe entre os dois perguntando ao LAYOUT se o
  painel está visível (`offsetParent`), nunca a um breakpoint copiado no
  JavaScript. Sem JavaScript o link navega e a receita aparece inteira: modo
  de preparo é o que se lê com a mão na panela, e não pode depender de
  script. `contexto_da_receita` é a montagem única desse contexto.
- **A PORÇÃO (½ · 1 · 1½) É CONTA DO SERVIDOR, E A LISTA É FECHADA.** Cada
  valor é um ENDEREÇO (`?porcao=0.5`), então recarregar preserva a escolha.
  Ela multiplica kcal, macros e **todas** as quantidades, inclusive o item
  `scalable=False`: `scale_factor` é o MOTOR ajustando a receita ao alvo
  (1,37 ovo não existe) e `porcao` é a PESSOA dizendo que comeu meio prato —
  se o ovo não acompanhasse, o kcal da tela deixaria de ser o kcal do que foi
  comido. `porcoes.porcao_valida` recusa o que não está na lista porque este
  número multiplica caloria GRAVADA: um `porcao=99` forjado escreveria um dia
  de 280 mil kcal. Vai para o histórico em `MealLog.porcao` (migration
  `plans.0011`, `default=1`, **sem backfill**: todo registro anterior É uma
  porção inteira — isso é fato, não suposição).
- **ILUSTRAÇÃO POR FAMÍLIA, NÃO FOTO POR RECEITA.** `MealTemplate.ilustracao`
  (migration `catalog.0008`, preenchida pelo nome por `catalog/ilustracoes.py`)
  e onze desenhos próprios em `templates/partials/ilustracoes_de_receita.html`
  (7,8 kB). 54 fotos exigem curadoria e este ambiente não VÊ foto para
  conferir — é o mesmo motivo que fez a expansão de exercícios de 10/09
  voltar atrás. O mosaico de veto é a **vitrine** (`/gestao/vitrine/`), que é
  também o que satisfaz `CoberturaDaVitrineTests` para essa parcial. O
  sprite NÃO entra na `base.html`: é conteúdo de duas telas, e a Hoje não tem
  por que pagar 7,8 kB.
- **O TOPO CONTA O DIA, E NÃO O ZERO.** Sem marcação, o anel mostra a META e
  o plano ("o seu dia em 5 refeições · 148 g de proteína") e a legenda dos
  macros mostra o alvo; da primeira marcação em diante volta o par
  comido/meta. A palavra está no servidor (`topo.modo`). A frase "Registre
  suas refeições para acompanhar o saldo do dia" FICA: o que o anel mostra é
  o cardápio, e o que falta ali é o SALDO.
- **A COLUNA DA DIREITA TEM CONTEÚDO** (medido: três cartões recolhidos e
  ~1.500 px vazios a 1280). Ela abre com a receita da refeição da VEZ — a
  ordem é `agora` → `pendente` → qualquer uma com opção, a mesma do cartão
  AGORA; sem ela, às 10h o painel falava do café das 7h com o lanche aberto
  ao lado — traz a lista de compras resumida e deixa as três explicações
  recolhidas no fim. **Painel e prévia são só do desktop**: no celular seriam
  a terceira cópia do mesmo conteúdo. A prévia é CACHE DE PROCESSO por
  (plano, semana), como o `<datalist>` de alimentos: `shopping_list` projeta
  os sete dias e custa SEIS consultas para mostrar três nomes.
  `plans:alimentacao` entrou em `TETOS` com **18** (17 sem a coluna, o mesmo
  piso da Home; a única a mais é `outras`).
- **O que NÃO se faz aqui:** rolar a tela até a refeição da vez ao abrir (o
  cartão AGORA no topo já é ela, com o mesmo CTA — rolar 600 px passaria por
  cima dele e do anel); "trocar por outra receita" PERSISTENTE (é o que a
  pessoa comeu HOJE; a troca de semanas existe no Treino, onde é a interação
  principal da ficha); e `.meal--done`, que virou `.meal--resolvida` junto
  com a saída do bloco `.option*` do CSS (3.491 bytes de markup morto) — a
  comemoração verde da refeição feita estava apontando para uma classe que
  ninguém mais emitia.
- **A meta de "abaixo de 1.500 px com uma refeição aberta" NÃO foi atingida
  e a aritmética está escrita** (`achados/missao-alimentacao-20260923.md`):
  2.645–2.799 px medidos, e os itens da própria missão — duas opções sempre
  visíveis com desenho, macros e ingredientes (802 px), o anel (268) e o
  cartão AGORA com a receita (271) — somam ~1.400 px sozinhos. Chegar a 1.500
  exige desfazer um deles, e isso é decisão de produto.

**Quem não declarou nada vê a Home de antes da campanha** — sem selo, sem cartão
de área, na ordem canônica. E ela não infere área de histórico, peso, treino,
água ou frequência: há teste com uma pessoa de histórico cheio provando que ela
continua neutra.

**Declarar interesse numa área nunca pode PIORAR aquela área.** `limiar_de_atraso`
lia só a prioridade, então quem marcava [Alimentação, Hidratação] e elegia
Alimentação recebia 35pp — mais tarde que quem não declarou nada, que recebe 25.
Declarar interesse em hidratação atrasava o aviso de hidratação. Hoje quem marcou
a área sem elegê-la principal fica no valor neutro, e há teste varrendo os cinco
pilares com essa propriedade.

**Interesse ORGANIZA; ele não restringe.** Quem marcou só Corrida continua com
as outras quatro áreas abertas, e há teste varrendo as cinco rotas. Esconder o
que não foi marcado é a simplificação tentadora que transformaria a
personalização em prisão.

**A prioridade é uma pergunta PRÓPRIA, não o primeiro checkbox tocado.** Marcar
várias áreas sem escolher a principal devolve a pergunta explícita; marcar a
principal sem marcar a área acima MARCA a área, porque cobrar essa coerência do
dedo seria devolver à pessoa um erro que o formulário fecha sozinho. Uma área
só dispensa a pergunta.

**A prioridade tem de pertencer aos interesses, e quem garante é o banco.**
`prioridade_pertence_aos_interesses` é o primeiro `CheckConstraint` do
repositório. O padrão até aqui era `UniqueConstraint`, que não expressa
"pertence a" — e a doutrina de `um_primeiro_admin_por_pessoa` já dizia por que
Python não basta: duas transações simultâneas atravessam juntas uma checagem.

**Preferência ≠ urgência contextual.** O pilar entra em `plans/agora.py` como
MAIS UM SINAL: ele move o limiar da regra de hidratação dentro de uma faixa
fechada de 15 a 35 pontos, e abre um ramo para Progresso **só quando
`convidar_a_pesar` já disse que há uma pesagem faltando**. Ele nunca passa na
frente de treino em andamento nem de refeição vencida — aquilo tem hora marcada
e a hora passa; o pilar continua verdadeiro amanhã. E nenhum pilar DESLIGA a
água: o teto de 35 existe para isso.

**Uso não é intenção declarada.** A migration `0024` não infere preferência de
ninguém. Quem já usava o app fica com `prioridade == ""`, que é um estado de
verdade — "ainda não respondeu" — e não um buraco. É o mesmo raciocínio que
`split_preference_confirmada` pagou caro para aprender. O `RunPython` que
existe ali só preserva o `onboarding_step` de quem já tinha terminado, porque o
passo novo moveu `ONBOARDING_DONE` de 6 para 7.

**O onboarding tem TRÊS etapas, e `ONBOARDING_DONE` continua 7.** Eram seis
passos (`/conta/onboarding/1/` a `/6/`, "Passo 1/6 · 16%", CTA "Salvar"), e
sete perguntas passavam antes de qualquer consequência. Desde 15/09/2026 são
três rotas reais — Sobre você · Seu objetivo e rotina · Sua personalização —,
e a tela só diz "Etapa N de 3". `ONBOARDING_LAST_STEP` é 3; o 7 de DONE
ficou de propósito, porque é o valor gravado em toda conta concluída e mudá-lo
custaria uma migration de dado para trocar um número por outro. A `0032` faz o
único remapeamento que importa: quem estava no meio (2-6) cai na etapa que
contém o passo antigo.

As etapas 2 e 3 são formulários COMPOSTOS (`EtapaCompostaView`): os cinco
`ModelForm` antigos continuam existindo com a validação e o `save()` de cada
um — e é isso que faz três etapas sem reescrever regra nenhuma. Duas coisas
custaram caro ali: **os formulários compostos compartilham UMA instância de
`Profile`** (com instâncias separadas, o último `save()` sobrescrevia o
objetivo gravado pelo primeiro — a etapa 3 mostrava "Emagrecer" sumido), e a
ordem dos saves é objetivo → divisão → rotina, porque `TrainingForm.save()`
relê o perfil. A divisão é PROGRESSIVA: aparece a partir de
`MINIMO_DE_DIAS_PARA_DIVISAO` dias marcados (a régua é
`preferencia_muda_a_divisao`, a mesma do antigo passo 4), e sem JavaScript o
servidor reabre a tela com o bloco visível e o erro no campo.

**"Calcular minha estimativa" (era "Criar meu plano" até 21/09/2026) monta
os DOIS planos e devolve JSON quando é XHR.** A tela de montagem envia o
último POST por `fetch` e SEGUE o redirect — o que consumia a mensagem "Sua
estimativa está pronta" antes de a Home ser aberta pelo navegador. Com
`X-Requested-With` o servidor responde `{"destino": url}` e o JavaScript
navega; sem JavaScript continua sendo o 302 de sempre.

**A ALIMENTAÇÃO É "ESTIMATIVA" E "CARDÁPIO DE EXEMPLO", NUNCA "PLANO"; A
LANDING NÃO PROMETE "DIETA" (decisão do dono, 21/09/2026).** A pesquisa
legal (em `gabrielmrvb/nutriplan-docs`, privado) achou o que a lei diz:
prescrição dietética é atividade privativa do nutricionista (Lei
8.234/1991), a Res. CFN 600/2018 define "plano alimentar", e a página do
CFN de 30/01/2026 lê a "oferta de planos alimentares por leigos no ambiente
digital" como contravenção (art. 47 da LCP). O NutriPlan não prescreve —
aplica fórmula pública e monta cardápio de exemplo —, e o texto passou a
dizer isso com as palavras certas: o CTA da etapa 3 é "Calcular minha
estimativa", a mensagem é "Sua estimativa está pronta", a Home fala em
"estimativa nova", o Perfil em "estimativa ativa", a Ajuda em "A estimativa
e o cardápio", a gestão em "cardápio montado", o 404 em "o que você
registrou"; a landing diz "alimentação e treino" e "estimativa de calorias,
cardápio de exemplo" (título, lead, description, JSON-LD), e a
`DESCRICAO_PADRAO`/manifesto idem. E o aviso "não substitui nutricionista
nem médico" está em TRÊS lugares com a mesma frase — o formulário de criar
conta, a etapa 3 acima do botão e o fim da seção do cardápio na Home — e os
Termos citam a lei. `config/test_linguagem.py` mede o TEXTO VISÍVEL do
`<main>` (sem script, estilo, comentário e tag): nenhuma tela da
alimentação com a palavra "plano", nenhuma promessa de "dieta" na landing e
nas descrições. O que NÃO mudou, de propósito: "plano"/"ficha" para o
TREINO e "Plano" da corrida (não há conselho privativo em jogo), `Pilar.
label` ("Alimentação"), os nomes de campo e modelo (`NutritionPlan`,
`target_kcal`), e a palavra "dieta" em texto educativo ("a razão mais
comum de uma dieta não funcionar") — a régua protege promessa pública, não
vocabulário (`config/test_nomenclatura.py`, o contrapeso).

**MISSÃO UX IRREPREENSÍVEL, LOTE 1 — CADASTRO E FORMULÁRIOS (22/09/2026).**
Sete coisas, cada uma MEDIDA no navegador antes de ser tocada
(`scratchpad/ux/` da sessão 3146901b; servidor local `nutriplan_ux3`):

- **O CONTINUAR da etapa 2 sumia com 0, 1 ou 2 dias de treino** (achado
  #1 das personas — duas das três desistiam ali). Não era CSS:
  `partials/choice_cards.html` fechava o `<div role="group">` só dentro de
  `{% if field.errors %}`; sem erro o grupo ficava aberto e engolia o
  `form-actions`, que caía dentro de `div.revela[hidden]`. O `</div>`
  saiu do `if`; `accounts/test_continuar_sempre.py` prova com um parser
  que sabe que ancestral está `hidden` (`assertIn("Continuar")` passava
  com o botão morto) e cobra o balanço de `<div>` dos parciais.
- **"Você faz musculação?"** (`Profile.musculacao`, `Musculacao` sim/nao,
  em branco = não perguntado; migration `0039`) é a pergunta-porta da
  etapa 2, ANTES do bloco da academia e DEPOIS da janela do dia (que é das
  refeições). Com "não": o bloco `[data-so-musculacao]` some (pwa.js) e o
  servidor zera dias/experiência no `clean` mesmo sem JavaScript; o
  resumo da etapa 3 diz "Musculação · Não faço" e para; a aba Treino
  repete a resposta com a corrida e "Mudei de ideia" em vez de "Cadastrar
  meus dias"; o Perfil idem. Obrigatória (é ela que decide o resto), e
  conta anterior com dias gravados reabre com "sim" marcado.
  `accounts/test_musculacao.py`. Copy dos cartões ≤ 45 caracteres
  (`WizardChromeTests`), uma coluna.
- **O erro nasce junto do campo, e a tela vai até ele.** Só as ações POST →
  redirect → flash erravam "isolado": o peso (Home e Progresso). A recusa
  viaja pela sessão COM a mensagem (`PesoRecusado(valor, mensagem)`,
  `[origem, valor, mensagem]` — o formato de dois itens ainda é lido), o
  campo leva `aria-invalid` + `aria-describedby="peso_error"` e a `<ul
  class="field__errors">` embaixo; a Home desenha a faixa do peso com
  `houve_recusa` mesmo sem convite de pesar. E `pwa.js` "FOCO NO ERRO"
  rola até o primeiro `[aria-invalid="true"]` de QUALQUER página e o foca
  (abre o `<details>` em volta; respeita `autofocus`).
  `plans/test_erro_junto_do_campo.py`.
- **O primeiro toque não se perde na transição.** MEDIDO no Chrome 153:
  durante a view transition entre páginas `elementFromPoint` devolve
  `<html>` por 280–320 ms depois de o documento começar; o clique vai
  para o `<html>` e nada acontece — 0 de 5 no experimento
  (`r7_prova.py`). `pointer-events: none` na árvore de pseudo não muda
  nada (medido). `pwa.js` "TOQUE DURANTE A TRANSIÇÃO" escuta
  `pagereveal`, guarda o clique que caiu no `<html>` e o repete no
  elemento daquele ponto em `viewTransition.finished`: 4 de 5 (o quinto
  cai antes de a navegação começar). `config/test_toque_durante_transicao.py`
  prende o bloco e o `--mov-tela: .2s` — a janela morta é a duração.
- **Nada digitado se perde.** O "derruba a sessão" do dono não tem
  logout em POST nenhum (`logout()` só na tela de sair); os dois caminhos
  com essa cara são o 403 de CSRF (token velho de outra aba ou de página
  servida do cache do worker depois de re-login) e a sessão expirada com o
  formulário aberto. `templates/403_csrf.html` fala português, diz que o
  digitado ficou guardado e tem "Voltar ao formulário" (`history.back()`,
  GET); `pwa.js` "RASCUNHO DO FORMULÁRIO" grava os campos de todo `<form
  data-rascunho>` (etapas do cadastro, corrida, reportar) no
  `localStorage` — chave por pessoa e caminho, 24 h, sem senha/token/
  arquivo/escondido — e os devolve quando o formulário reabre; se
  reabriu COM erro, o que o servidor devolveu manda. O envio marca
  `enviado`; a página seguinte, se for outra, apaga. Provado:
  reload, 403 → voltar, envio certo → rascunho some (`r2_rascunho.py`).
  `config/test_rascunho_e_403.py`.
- **`alimentos_do_catalogo()` devolve NOMES**, e o `<datalist>` do "comi
  outra coisa" lia `food.name` — 62 `value=""` em produção desde o #102.
  `plans/test_outra_coisa_datalist.py`.
- **Ação recusada não é a "primeira ação de valor"**: o convite de
  instalação aparecia por cima do erro do peso. `config/acoes.py` lê a
  fila de mensagens sem consumir.
- **O equipamento do cadastro NÃO reverte** (item 1 do dono): não
  reproduzido no código nem no navegador — "só o peso do corpo" chega ao
  banco, à etapa 3, ao Perfil, e a edição remonta a ficha. O que existia
  era o CONTINUAR sumido acima. `accounts/test_equipamento_pela_tela.py`
  envia o formulário RENDERIZADO e prova a volta; sabotado, fica vermelho.

**MISSÃO UX IRREPREENSÍVEL, LOTE 2 — OS NÚMEROS DO PRIMEIRO DIA E A HOME
POR PRIORIDADE (22/09/2026).**

- **A ofensiva e o recorde não olham para antes de `user.date_joined`**
  (`streaks.primeiro_dia_da_conta`, `_limite`). Achado #4 das personas:
  "3 dias de ofensiva" no primeiro dia e "401 / 3" nas Conquistas de quem
  não tem dia de treino — os 400 dias anteriores ao cadastro fechavam
  sozinhos (descanso é o plano; sem meta não há o que cobrar). E as
  Conquistas passam a MESMA meta de água que a Home (`achievements.reunir`
  lê o plano ativo uma vez e o empresta à ofensiva): duas telas, um
  número. Consequência nos fixtures: `plans.tests.create_complete_user` e
  `workouts.tests.create_user` nascem em 2020 — os testes escrevem
  histórico em agosto; quem quer "nasceu hoje" sobrescreve.
  `plans/test_ofensiva_comeca_na_conta.py`.
- **A ofensiva em zero distingue quem já vinha usando** (`Ofensiva.
  falta_ontem`, só quando ontem já era da conta; achado #11). Ela DIZIA o
  que faltou ("Ontem faltou dieta ou água. Hoje recomeça"); desde a rodada
  2 de 24/09/2026 a frase não nomeia mais a falta, e o que sobrou de
  `falta_ontem` na tela é o VERBO — "Recomeça hoje" para quem tinha conta
  ontem, "Comece hoje" para quem chegou hoje. Ver "A OFENSIVA EM ZERO
  CONVIDA", na rodada 2.
- **Aderência: hoje só cobra o que já passou, e o consolidado é dos dias
  fechados** (item 6). `tracking.history` recorta o denominador de HOJE
  pelo relógio (`previstas_ate_agora`; o feito entra no piso, então marcar
  uma refeição futura não passa de 100 %) e marca a linha `parcial` ("1/2
  até agora"); `tracking.adherence` devolve `adherence_pct=None` sem dia
  fechado, e o Progresso mostra "1/2 · Refeições · hoje, até agora" em vez
  de "20 %". No dia do cadastro, as refeições de ANTES da hora do cadastro
  não entram — nem aqui nem no AGORA/lista (`agora.proxima_acao(desde=)`,
  `marcar_refeicoes(desde=)`; achado #7: "três refeições Pendente" na
  primeira Home de quem chegou às 18h). `plans/test_aderencia_primeiros_dias.py`.
- **"FICOU PARA TRÁS" depois da janela da refeição** (`JANELA_DO_AGORA_MIN
  = 90`): a refeição vencida mais recente continua sendo a ação (registrar
  o que aconteceu), mas às 18:20 o almoço das 14:30 não é "AGORA" (achado
  #6). `AcaoAgoraTests`.
- **O cartão da área principal traz a AÇÃO do dia, como botão** (item 4 do
  dono — "a prioridade não muda a tela"): Treino → "Começar treino" para a
  sessão de hoje (nome, exercícios, séries feitas), ou "Ver a ficha" se
  concluído; Corrida → "Registrar corrida"; Progresso → "Registrar peso"
  (`#pesar` quando a faixa está na Home, senão o Progresso — e desde
  24/09/2026 esse é o ÚNICO atalho de peso da Home: o rodapé do cartão do
  painel voltou a "Ver progresso"). Quando o AGORA
  já é o treino, o cartão vira consulta (sem repetir o botão — dois
  "COMEÇAR TREINO" na mesma dobra, medido). `OCartaoDaAreaTemAAcaoDoDiaTests`.

**MISSÃO UX IRREPREENSÍVEL, LOTE 3 — O TREINO DE QUEM COMEÇA (22/09/2026).**

- **O aviso de conquista entra NO FLUXO da execução**, logo abaixo de
  "Concluir série" (`[data-conquista-alvo]` em `agora.html`;
  `conquista.js` move a caixa para lá — `pousar()` — no carregamento e a
  cada "Concluir série" sem recarga, pelo `nutriplan:pagina-trocada`;
  `.conquista--em-fluxo` é `position: static`). Fixo e ancorado embaixo,
  ele cobria "CONCLUIR SÉRIE 2" e o descanso (achado #3 das personas, nas
  duas que treinaram; `elementFromPoint` no centro do botão devolvia
  COMPARTILHAR — e o QA desta missão reproduziu: 40 cliques no botão
  caíam no toast). Nas outras telas continua fixo, com a reserva de
  `tem-conquista`. `workouts/test_toast_nao_cobre_o_botao.py`.
- **O iniciante do peso do corpo começa no degrau 3 ou abaixo**
  (`services.ajustar_degrau_do_iniciante`, `DEGRAU_DO_INICIANTE = 3`;
  doutrina no `TREINO.md`, "O degrau do iniciante no peso do corpo"): a
  persona recebia paralelas (4), parada de mão (5) e flexão arqueiro (5).
  Só `iniciante` + `peso_corporal`; item acima do degrau é trocado pelo
  degrau mais baixo LIVRE do mesmo movimento e grupo (dentro do alcance,
  não "um abaixo"), com a dose; sem degrau livre, sai — a não ser que
  seja o último do grupo — e `preencher_ate_a_faixa` devolve as séries.
  Roda no gerador e na conferência (`_prescricao_bate`), como a
  substituição por equipamento: a ficha nova não nasce "desatualizada".
  Medido no `abc2` de 5 dias: A 3 + 3 em ~28 min, B 5 em ~35, C 8 em ~58.
  Com 2 como teto a letra A virava duas opções de dois exercícios.
  `workouts/test_degrau_do_iniciante.py`; dourado e capacidade de ambiente
  intactos.
- **O placar do peso do corpo tem herói**: `Placar.repeticoes`/`series` e
  `Placar.heroi` — kg quando houve carga; repetições quando não; séries
  quando nem repetição foi anotada. A folha e o cartão de compartilhar
  (`data-compartilhar-heroi[-rotulo]`; `kg` continua para o dado antigo)
  leem o mesmo. E o kg da tela leva ponto de milhar (`0g`; "8008" contra
  "8.008" no cartão era o achado #16). `OPlacarDoPesoDoCorpoTests`.
- **A primeira série de um exercício sem histórico abre com as reps no
  PISO da faixa** (`_sugestao_de_reps`): o campo vazio com placeholder
  "6-10" gravava série sem repetição para quem tocava "Concluir" sem
  digitar, e o placar fechava em "0 repetições feitas" (medido no QA).
- **Editar treinos pelo Perfil diz o que valeu** (achado #8):
  `acertar_ficha` devolve a frase — "a ficha foi remontada com elas", "há
  série registrada hoje, então a ficha muda amanhã" (`treino_em_andamento`
  + `rotina_invalida`), "ajustou a ficha à mão, então ela não é
  remontada" — como a troca de duração já dizia.
  `accounts/test_edicao_diz_o_que_valeu.py`.
- **A corrida nas telas que resumem** (achado #9): cartão "Corrida" no
  Progresso (`workouts.progresso.km_corridos`, oito semanas, UMA consulta
  agregada — o teto de `plans:history` foi 28 → 29 com a razão escrita) só
  para quem correu; "Corridas" na lista da exclusão da conta; a FAQ ganhou
  "Eu só corro (ou nado, ou pedalo). O app serve para mim?"; e a caixa das
  refeições vazia diz "Nenhuma refeição registrada" — "Ainda não há nada
  marcado" lia como "nada" para quem tinha 25 séries na véspera (#12).
- **Dia sem nada a cumprir não fecha** (`Dia.mensuravel`; a mesma régua em
  `_recorde`): sem rotina de treino (nenhum dia previsto na semana), sem
  cardápio e sem meta de água não há o que ter cumprido — era o resto do
  "401 / 3". O descanso ENTRE dias previstos continua sendo o plano
  (`achievements.tests.OfensivaTests` prende).

**MISSÃO UX IRREPREENSÍVEL, LOTE 4 — A VARREDURA (22/09/2026).** Quinze
telas logadas e onze anônimas, nos dois temas, a 360/390/430/768/1280,
com `axe` (agent-browser) a 390 no escuro: **zero violação, zero rolagem
horizontal, zero texto abaixo de 11 px** (`scratchpad/ux/varredura*.py`
da sessão). O que a régua de 44 px achou e foi consertado: o opt-in da
análise de uso no Perfil (197 × 17 → cartão de `choice-list`, como os
consentimentos e os avisos) e os links da caixa de aceite dos Termos (150 ×
16 → `padding` vertical com margem negativa, em tokens). O que ela acha e
fica: `<label>` de campo de texto (o alvo é o campo) e link corrido dentro
de parágrafo (exceção do WCAG 2.5.8). PWA offline PROVADO ponta a ponta no
local: worker registrado, `/treino/` e `/` servidos do cache sem rede,
"+250" vira "1 marcação esperando conexão" e drena para 250 ao voltar. E
três coisas que a varredura mudou:

- **As provas da landing pesam em WebP** (`<picture>` com PNG de reserva;
  q90 ≈ 24 KB cada contra ~90 KB): no 3G a landing levava 9,6 s para
  terminar — os três PNG eram quase tudo. `capturas_landing` gera os dois;
  `plans/test_landing_webp.py` prende o peso.
- **A divisão em português de quem começa** (achado #13): "Como dividir os
  treinos da semana?", cartões com "Peito e tríceps · Costas e bíceps ·
  Pernas e ombros" em vez de "Peito+Tríceps | Costas+Bíceps", sem "agrupa
  complementares"; e o resumo da etapa 3 diz o TÍTULO DO CARTÃO que a
  pessoa tocou (`escolhas.titulo_de`: "Pouco ativo", não "Sedentário /
  pouco ativo").
- **A sessão de quem usa não vence no meio do uso**
  (`config/sessao.py`, `RenovarSessaoMiddleware`, depois do
  `SessionMiddleware`): os 14 dias contavam do LOGIN, e quem entrava todo
  dia era deslogado do nada a cada duas semanas — a "queda de sessão" do
  item 2 com outra cara. `SESSION_SAVE_EVERY_REQUEST` gravaria em toda
  resposta; aqui a renovação é passada a METADE da vida (uma escrita por
  semana), e a data mora na própria sessão (`set_expiry(datetime)` na
  primeira passagem — sem ela `get_expiry_age()` devolve a idade cheia e a
  data real só existe na linha do banco). `config/test_sessao_renovada.py`.

**AUDITORIA DE SESSÃO, CSRF E CACHE — E A RAIZ DO "A SESSÃO CAIU E PERDI O
QUE DIGITEI" (22/09/2026).** A queixa do dono foi medida até o fim, numa
sessão LOGADA do staging (`fetch` same-origin enxerga todo cabeçalho de
resposta; é o que curl anônimo não alcança). **Não há logout em POST
nenhum** — `logout()` só na exclusão da conta —, e a sessão deixou de vencer
no meio do uso no lote 4. O que sobrava era 403 de CSRF, por dois caminhos:
a página veio do CACHE DO SERVICE WORKER (ele serve a cópia guardada quando
a rede passa de 3 s) com o token de uma sessão anterior, ou a pessoa entrou
de novo em outra aba e `login()` chamou `rotate_token()`. Nos dois o COOKIE
está certo e só o campo escondido do HTML está velho — e `fila.js` já
trocava o token pelo do MOMENTO DO ENVIO, que é por que a água marcada sem
rede nunca sofreu. Quem sofria era o formulário COMUM, o longo: a etapa 2 do
cadastro e o registro de corrida, os dois citados pelo dono. Hoje `pwa.js`
("TOKEN DE CSRF") reescreve `csrfmiddlewaretoken` com o valor do cookie no
carregamento, no `pageshow` (bfcache) e no `submit` em CAPTURA. Isso **não**
enfraquece nada: o cookie só é legível por JavaScript da própria origem, que
é de onde a defesa vem, e `config/test_csrf_do_cookie.py` prende os dois
lados — o valor cru do cookie é aceito (se `CSRF_COOKIE_MASKED` for ligado um
dia, o teste cai antes da produção) e token de outro segredo continua 403.
Provado no navegador: token trocado por `token-de-outra-sessao-ja-vencido`,
envio passa, corrida gravada.

**E O ACHADO DE SEGURANÇA DA MESMA MEDIÇÃO: tela logada respondia SEM
`Cache-Control`.** `/historico/`, `/treino/` e `/conta/perfil/` não mandavam
diretiva nenhuma, e sem diretiva o navegador guarda por heurística — peso,
altura, e-mail, objetivo e histórico de treino, o dado de saúde que a etapa 1
pede autorização para tratar. Num aparelho de casa, sair da conta e apertar
VOLTAR redesenhava a tela da pessoa anterior a partir do disco.
`config.cache_privado.CachePrivadoMiddleware` (o ÚLTIMO da lista, para a
fase de resposta rodar com o `request.user` já posto) escreve `private,
no-cache, must-revalidate` em toda resposta `text/html` de sessão
autenticada que não declare a própria diretiva — `never_cache` do login e da
gestão e o `no-store` da exportação ficam como estão. **E nada de
`no-store`**, de propósito: o service worker recusa guardar o que vem com
`no-store` (`podeGuardar`), e é o cache dele que faz a dieta abrir no metrô;
e o Chrome desliga o bfcache numa página `no-store`, que é o "Voltar ao
formulário" do 403 devolvendo o digitado. `config/test_cache_privado.py` lê
a régua do próprio worker para as duas pontas não divergirem em silêncio.

**E O TERCEIRO ACHADO DA MESMA AUDITORIA: NÃO HAVIA
`Content-Security-Policy` EM ROTA NENHUMA (22/09/2026).** Nem a landing, nem
a tela logada, nem o cadastro. CSP não conserta um XSS; ela limita o estrago
de um que exista, e num app que sabe peso, altura e histórico de treino esse
limite vale o trabalho. `config/csp.py` é a política MEDIDA do que o app
carrega — `script-src 'self' 'nonce-…'` **sem `'unsafe-inline'`**, que é o
que faz a política valer alguma coisa; `style-src` COM `'unsafe-inline'`,
porque a barra de progresso é `style="width: {{ pct }}%"` calculado pelo
servidor (a exceção já escrita na seção de Design) e estilo inline não
executa código; `img-src` com `data:`, `blob:` (o cartão do placar nasce de
um `canvas.toBlob`) e `https://cdn.jsdelivr.net` (as fotos da
free-exercise-db); `frame-src` só o `youtube-nocookie`; `form-action 'self'
https://accounts.google.com`, porque o botão do Google posta para o próprio
site e o servidor redireciona — sem a origem, o Chrome mata o login em
silêncio; `object-src 'none'`, `base-uri 'self'` e `frame-ancestors 'none'`.
O nonce é sorteado por RESPOSTA no middleware (o primeiro depois do
`SecurityMiddleware`, porque o template precisa dele) e chega aos templates
por `config.csp.contexto`.

Duas consequências que qualquer mudança futura esbarra, e por isso têm
teste de VARREDURA em `config/test_csp.py`: **todo `<script>` inline de
`templates/` carrega `nonce="{{ csp_nonce }}"`** (são 13; sem ele o script
simplesmente não roda em produção, e ninguém descobre até a tela quebrar) e
**nenhum atributo `onclick=`/`onsubmit=`/`onchange=` sobrevive** — os quatro
que existiam (403 de CSRF, Perfil, gestão e a tela offline) viraram marcador
no HTML com ouvinte delegado em `pwa.js`, e o da gestão num `<script>` com
nonce da própria página, porque `gestao/base.html` não carrega `pwa.js`.
Atributo de evento sob CSP não dá erro visível: o botão fica lá e não faz
nada.

E uma consequência que a suíte achou e que volta a morder quem escrever
o próximo teste de segurança: **o nonce muda a cada resposta, e há quatro
testes que comparam duas respostas BYTE A BYTE** para provar que a recusa
não é oráculo (bloqueado, senha errada e conta inexistente respondem a
mesma coisa). Eles ficaram vermelhos sem que nada de segurança tivesse
mudado. `accounts.tests.sem_o_que_muda_por_resposta` normaliza o token de
CSRF e o nonce — e só eles; todo o resto do HTML continua comparado byte a
byte.

**A casca nativa NÃO recebe a política**, e a razão é medida: o Capacitor
injeta a própria ponte no WebView e nenhuma política que este servidor
escreva conhece o nonce dela. Isso não abre buraco real — a marca
`NutriPlanNativo/` é do User-Agent de QUEM PEDE, e um XSS rodando no
navegador da vítima não muda o User-Agent dela; o que um atacante consegue
falsificando a marca é desligar a CSP do próprio navegador, contra si mesmo.

**OS LEGAIS ESTÃO PUBLICADOS, E O CONSENTIMENTO SÃO TRÊS CAIXAS COM PROVA
(decisão do dono, 21/09/2026).** `LEGAL_RESPONSAVEL` e `LEGAL_CONTATO`
preenchidos no Render (produção e staging) fazem `settings.LEGAL_PUBLICADO`
virar verdadeiro: o rodapé (`partials/links_legais.html`, incluído pela
`base.html` em toda tela fora do shell offline; "Ajuda" fica mesmo em
rascunho) passa a linkar `/privacidade/` e `/termos/`, e as páginas deixam
de se declarar rascunho. O consentimento é TRÊS controles separados,
desmarcados, e não um (`accounts/consentimento.py`, `partials/
caixas_de_consentimento.html`): o aceite dos Termos com os dois links (no
cadastro por e-mail; na etapa 1 para quem veio pelo Google), **dados de
saúde** (LGPD art. 11, I — o app pede peso e altura na etapa 1, então é
ALI, antes de gravar, que a pessoa autoriza) e **transferência
internacional** (art. 33, VIII — o banco é o Neon nos EUA por decisão de
não migrar; a caixa nomeia o país). Cada texto termina em "Sem isso o app
não funciona" (art. 9º, § 3º: condição do serviço, dita com destaque). A
prova é `Consentimento` (user, tipo, versão, `dado_em`; único por versão),
porque o ônus da prova é do controlador (art. 8º, § 2º), e o perfil guarda
`consentimento_versao` para a guarda custar zero consultas.
`VERSAO_DOS_LEGAIS` ("2026-09-21") é a data dos textos: subir a versão faz
TODO MUNDO consentir de novo, uma vez, em `/conta/consentimento/` — a
tela única, sem barra de abas, com "apagar sua conta" linkado (ninguém
precisa consentir para ir embora; `ExcluirContaView` não é guardada). Quem
JÁ TINHA conta passa por ela também: a migration `0038` liga
`Profile.precisa_consentir` só para conta com cadastro terminado que não é
`@nutriplan.invalid`, e `deve_consentir(perfil)` é `precisa_consentir or
(versão consentida ≠ vigente)` — o perfil de fixture/seed, sem versão e sem
marca, NÃO é barrado, de propósito: ele nunca passou pelo cadastro, e a
alternativa era fingir que consentiu ou reescrever todo fixture da suíte. A
etapa 1 em EDIÇÃO (perfil completo, vindo do Perfil) não pede caixa
nenhuma: consentir é do cadastro e da tela única, e três classes de
`accounts.tests` reprovaram quando pedia. `IDADE_MINIMA = 18` no
`clean_birth_date` (era 14): sem responsável legal e sem base para tratar
saúde de adolescente, o cadastro recusa e diz. `scripts/qa/e2e_staging.py`
marca as três caixas; `accounts/test_consentimento.py` prende o fluxo, a
migration (`TransactionTestCase`) e a política ("Com que base tratamos cada
dado", transferência sem adequação, ANPD). `LEGAL_CONTATO` é
`bielpointblank@gmail.com` — o e-mail que já é público neste arquivo, o
remetente da Brevo e o alerta do UptimeRobot — e o dono troca pelo painel
quando quiser um dedicado; `claudeglauco@gmail.com` (VAPID) não é contato
público e não entra.

**ESTRATÉGIA E PESQUISA DE NEGÓCIO MORAM EM `gabrielmrvb/nutriplan-docs`
(privado), NÃO AQUI (decisão do dono, 21/09/2026).** Este repositório é
público desde 21/09/2026 e descreve o PRODUTO e a OPERAÇÃO — arquitetura,
runbook, doutrina do treino, design system, achados de auditoria. O que
descreve o NEGÓCIO — pesquisa de mercado e de concorrentes, leitura
jurídica, decisões de preço, canal e posicionamento — vai para o repositório
privado (`pesquisa/`, um arquivo datado por levantamento). O primeiro
morador é `pesquisa/pesquisa-loja-e-legal-20260921.md`; a branch local
`docs/pesquisa-loja-e-legal` deste repositório foi apagada sem push.

**O BANCO NÃO VAI PARA SÃO PAULO: banco e app ficam nos EUA, e a
transferência internacional é declarada e consentida (decisão do dono,
21/09/2026).** A pesquisa achou a região `aws-sa-east-1` do Neon e escreveu
o procedimento (`docs/infra-recuperacao.md`), e a conta decidiu contra: o
web fica em Oregon (o Render não tem região no Brasil), a produção do Neon
está em `us-west-2` no mesmo data center, e a Home fazia até 41 consultas
em série — a 105 ms de piso físico Oregon–São Paulo seriam 4,3 s de rede por
tela para reduzir, sem eliminar, o que cruza a fronteira. O que cobre a LGPD
é a segunda caixa do cadastro (art. 33, VIII: consentimento específico e
destacado para a transferência, com o país de destino nomeado) e a seção
"Onde seus dados ficam" da Política, que já diz Oregon, Neon e Render; a
Res. 19/2024 da ANPD ainda não tem cláusula-padrão aprovada e só a UE tem
adequação (Res. 32/2026). Revisita-se se um dia o web também puder morar no
Brasil — nunca só o banco.

**Plano é retrato, não referência.** `NutritionPlan` e `TrainingPlan` guardam os
números do dia em que foram criados. Mudou a entrada, nasce plano novo — os
antigos ficam. Nunca edite os números de um plano ativo: `plan_is_current()`
compara com o que o motor calcula hoje e descarta o que não bate.

**O RETRATO DO PLANO INCLUI O QUE ESCOLHE A COMIDA (24/09/2026).**
`NutritionPlan` fotografava peso, altura, idade, sexo, atividade, objetivo e
dias de treino — tudo que calcula a META — e nada do que escolhe a RECEITA.
Consequência medida: marcar "sem peixe" no Perfil devolvia "Alterações
salvas." e o cardápio seguia oferecendo sardinha, **e continuava seguindo**
em toda visita, porque `plan_is_current` comparava só aqueles sete campos.
Hoje o retrato tem `restricoes` (os slugs ORDENADOS, separados por vírgula)
e `meal_style`, os dois em `_INPUT_FIELDS`. Ordenados porque a ordem do
`values_list` de um M2M não é estável, e uma ordem diferente seria lida como
restrição diferente — o cardápio remontaria em toda abertura da Home.
**Texto e não JSON** pela mesma razão que o resto do retrato é escalar: a
comparação é `==` contra o que `build_inputs` monta, e lista contra tupla
nunca é igual.

O VAZIO é assimétrico, e a assimetria é a decisão (`_VAZIO_E_DESCONHECIDO`):
`meal_style` vazio no retrato é "nasci antes do campo" e NÃO invalida — o
perfil sempre tem estilo, então trocar o cardápio de todo mundo num deploy
seria cobrar de quem não pediu nada; `restricoes` vazio compara normalmente,
porque quem TEM restrição no perfil e um retrato vazio é exatamente quem
está vendo sardinha. Sem backfill, pelos dois motivos.

E a etapa 3 em EDIÇÃO remonta AGORA (`EtapaCompostaView.acertar_cardapio`,
`PASSO_COMIDA`), como a etapa 2 já remontava a ficha: a mensagem vira
"Alterações salvas — o cardápio foi remontado com elas". O cache do perfil
sai antes de o motor ler, pelo mesmo motivo escrito em `acertar_ficha` —
`salvar()` grava por `self.profile` e `build_inputs` lê `user.profile`; as
restrições escapariam (o M2M consulta toda vez), o estilo não. **Preço
medido: +1 consulta na Home (17 → 18) e na Alimentação (18 → 19)**, constante
e não por linha; devolver o número exigiria denormalizar os slugs numa coluna
do perfil, que é uma segunda cópia da verdade.
`plans/test_restricao_invalida_o_cardapio.py`.

**Ficha ajustada não é remontada.** `TrainingPlan.customized_at` desliga o
gerador. Sem isso, mudar o horário de terça apaga a troca de ontem.

**Ficha que o CATÁLOGO deixou para trás também não é remontada — a Home
pergunta (17/09/2026).** O painel remontava a ficha na entrada sempre que a
prescrição do catálogo divergia da gravada; o deploy que ativou 28
exercícios trocaria a ficha de todo mundo no meio da semana, sem ninguém
pedir. Hoje `sync_active_routine` só remonta a ficha INVÁLIDA
(`rotina_invalida`: sem sessão, exercício aposentado, divisão que não
corresponde à frequência, dias/horários diferentes — e nível ou faixa de
duração diferentes dos que a ficha guarda, porque aí foi a pessoa que mexeu
na própria entrada). Prescrição diferente é `rotina_desatualizada`, e a
resposta é um aviso único e dispensável na Home, depois do AGORA: "Seu
treino pode ficar mais completo — regenerar?". Regenerar é `POST
/treino/regenerar/`; "Agora não" grava `aviso_dispensado_em` NO PLANO, não
no navegador. O plano virou retrato também das ENTRADAS (`catalogo`,
`nivel`, `duracao`): `catalogo` é a impressão digital de `exercises.json` +
`splits.json` + `TREINO.md` (`versao_do_catalogo`), e com ela igual à de
hoje a Home responde "nada mudou" com ZERO consultas — a conferência exata
(represcrever a semana, onze consultas) só roda para ficha nascida de outro
catálogo ou de antes da migration `0023`, que ficou com os três em branco.
Em branco é desconhecido, e desconhecido não invalida nada. E quando a
conferência exata diz "igual", o plano recebe a impressão digital de HOJE
(uma escrita, uma vez): sem isso todo deploy que reescreve prosa do
`TREINO.md` — a doutrina entra na impressão — cobrava as onze consultas de
toda ficha antiga em toda visita à Home, para sempre. Prescrição divergente
NÃO carimba: o aviso continua até a pessoa decidir. O demo é fixture de que
o seed é dono: `seed_demo` regenera sozinho quando a prescrição mudou.

**O CICLO DA DIVISÃO RODA CONTÍNUO, e a letra de hoje sai da POSIÇÃO, não
do dia da semana (17/09/2026).** Em 5 dias com ABC o ciclo fixo A B C A B
recomeçava toda segunda, peito e costas caíam 2× e "Pernas e ombros" 1× —
quadríceps em 7 diretas por semana, para sempre. O desequilíbrio era do
calendário. Hoje a semana seguinte continua de onde a anterior parou (C A B
C A, depois B C A B C; em 3 semanas cada letra cai 5 vezes), e a média do
ciclo está medida no `TREINO.md` — peito 25,0 no Padrão contra o alvo de
24, ACEITO pelo dono em 17/09 com tolerância de ± 2 (26 é o teto da média;
ficha real de academia faz 26–28), lida do documento pelo teste. O golden
não baixa. Como funciona: `TrainingPlan.
inicio_do_ciclo` é a posição zero (o primeiro dia de treino da semana em que
o plano nasce — a primeira semana é a de sempre, a rotação começa na
segunda); as linhas de `sessions` continuam UMA POR DIA DA SEMANA, com a
letra da primeira semana — são o retrato de dias, horários e durações que
`rotina_invalida` compara —; `services.sessao_do_dia(plan, dia)` devolve a
linha da LETRA da posição vestindo o dia da semana (`_no_dia`: horário,
duração e `weekday` do dia, `pk` da letra — a escolha e a ficha apontam
para a letra); `sessoes_da_semana` é a semana de hoje que o painel, a ficha
e a leitura desenham. A posição é do CALENDÁRIO: treino pulado conta, como
o quadro da academia. Toda letra recebe o teto e o número de opções da PIOR
semana (`ocorrencias_das_letras`: 2× para A, B e C em 5 dias). Plano de
antes da rotação (`inicio_do_ciclo` em branco) segue preso ao dia da semana,
não é remontado, e a Home pergunta. NUNCA volte a resolver "a sessão de hoje"
por `weekday=hoje.weekday()`: era isso que prendia o ciclo.

**A ofensiva mede aderência AO PLANO, e o denominador vem do plano.** Não do
que a pessoa marcou — essa era a regra antiga, e ela invertia o incentivo do
app: três refeições feitas mais duas marcadas como "comi outra coisa" davam
60% e quebravam a sequência, enquanto três feitas e duas SEM MARCAR NADA davam
100% e a mantinham. Registrar honestamente custava caro; omitir saía de graça.
A propriedade que governa isso agora tem teste próprio em `plans/test_streaks.py`:
**omitir nunca pode produzir resultado melhor que registrar**. Ela vale por
construção, porque qualquer denominador independente da marcação a satisfaz.

**O DIA FECHA COM DOIS DOS TRÊS PILARES, E O TREINO É OBRIGATÓRIO NO DIA
PREVISTO (decisão do dono, 20/09/2026).** Até então a régua era treino E
dieta (≥ 80 %) E água (≥ 90 % de 35 ml/kg) no mesmo dia, e a auditoria de
20/09 simulou uma semana de uso real — 4 refeições de 5, 1,5 L de uma meta
de 3 L, treino feito — que terminava com "0 dias — Comece hoje": a água
dominava. Hoje `Dia.completo` é `treino and (dieta or agua)`; no dia sem
treino previsto descansar continua sendo o plano (`treino=True`), então o
dia de descanso fecha com um dos dois outros. A pendência diz o que FECHA o
dia ("treino", "dieta ou água"), nunca a lista de tudo que faltou.
`manage.py simular_ofensiva` reproduz a semana auditada sob as duas regras
(0 → 5 dias) e há teste sobre a saída dele — rode antes e depois de mexer
na régua. `OmitirNaoPodeCompensarTests` passou a medir a dieta SEM água,
senão a água fecharia o dia e o teste deixaria de medir o que diz medir.

**Dois lados abrem o mesmo IndexedDB, e eles têm que concordar.**
`static/js/fila.js` e `templates/pwa/sw.js` abrem `nutriplan-fila`. O service
worker abria sem `onupgradeneeded`; quando ele chegava primeiro — num evento
`sync` —, o navegador criava o banco COM ZERO STORES, e daí em diante toda
gravação offline morria com `NotFoundError`, para sempre, porque a versão nunca
subia. Hoje os dois criam a store e declaram a MESMA versão; `push/tests.py`
compara os dois arquivos. Subir a versão é o que migra quem já tem o banco
quebrado — `deleteDatabase()` "resolveria" o console e jogaria fora a água que
alguém registrou no metrô.

**A fila offline drena na ORDEM DOS TOQUES, e ela não vem de graça.** A chave da
store é `op_id`, que é um `crypto.randomUUID()`, e o `getAll()` do IndexedDB
devolve por ordem de CHAVE — medido em navegador, 51,7% de inversão com duas
operações e 85,7% com três. Como somar, zerar e desfazer não comutam, isso muda
o resultado: `+500 → +500 → desfazer` termina em 500 e, drenado ao contrário, em
1.000. A ordem hoje vem de `seq`, um contador calculado como `maior + 1` DENTRO
da transação de escrita — 60 gravações concorrentes, zero empates, sem lock.
**Não use o `em: Date.now()` para isso**: 199 de 200 chamadas seguidas caem no
mesmo milissegundo, e com empate o `sort` estável devolve a ordem do UUID.
`emOrdemDeToque` e `corpoDoItem` existem IDÊNTICAS nos dois arquivos, e um teste
compara as duas.

**A drenagem PARA no primeiro item que ficou na fila.** Seguir em frente com o
anterior preservado desordena de um jeito que ordenar não conserta e que
sobrevive à drenagem. `fila.js` para seco porque `meus()` já filtrou um dono; o
`sw.js` trava POR DONO, porque drena fila de várias contas e um item estrangeiro
recusado com 503 não pode travar quem está logado — é por isso que
`push/test_replay.py` proíbe `break;` lá.

**A captura guarda PARES, não um objeto, e inclui o botão que enviou.**
`new FormData(form)` não traz o `<button>` do submit: o "Pulei" da refeição
mandava só o token e sumia em silêncio. E objeto colapsa chave repetida: "Comi
outra coisa" ia de três alimentos para um — o vazio, porque o último vence.

**Idempotência tem de cair junto com o efeito.** Este projeto não liga
`ATOMIC_REQUESTS`, então `ja_aplicada` commitava o `op_id` antes da escrita. Uma
falha no meio queimava o identificador sem aplicar nada, e o reenvio era
respondido com "já aplicada" — a fila apagava o item e o registro sumia.
`LogHydrationView.post` é transacional por isso.

**Água soma NO BANCO, não em Python.** `registro.ml = registro.ml + ml` seguido
de `save()` é leitura-modificação-escrita: dois toques rápidos leem o mesmo
valor e o segundo sobrescreve o primeiro. Tocar +250, +500 e +750 em sequência
dava 1000 em vez de 1500. Nenhum debounce no JavaScript conserta — o servidor
precisa estar certo com pedidos concorrentes, e a fila offline reenvia
exatamente assim, em rajada, quando a rede volta. Hoje é
`Least(F("ml") + ml, Value(10000))`, e há teste com threads reais.

**O total do dia e a composição dele são duas tabelas, e uma só é a fonte.**
`HydrationLog` guarda o total — é dele que leem a ofensiva, o histórico e a
tela Hoje. `GoleDeAgua` guarda a COMPOSIÇÃO, e só daqui para frente: não houve
backfill porque inventar de quantos goles os totais antigos foram feitos seria
fabricar dado. A consequência aparece na tela e está escrita nela: no dia da
virada a lista mostra uma linha "sem horário" com a diferença, para a soma
fechar com o painel. As duas escritas andam juntas dentro de `transaction`, nos
três caminhos — somar, desfazer e zerar. **Zerar apaga os goles do dia também**;
quando não apagava, a tela mostrava "Registrado 0 ml" com a lista cheia embaixo,
e "desfazer" continuava oferecido sem mover número nenhum.

**A água sobe no AGORA por ESTADO, não por relógio.** Ela era prioridade 4 —
aparecia depois de todas as refeições e do treino, ou seja, quando o dia já
tinha acabado. Hoje um ramo intermediário mede quanto a pessoa está atrás do
esperado PARA A HORA, e a janela do esperado é a do próprio plano: da primeira
refeição à última. Não há horário escrito à mão, e isso é a decisão — quem come
às 5h30 e às 19h tem outra janela, e um "7h às 22h" fixo estaria errado para
essa pessoa todos os dias. Beber **desliga o cartão na hora** — e só na hora: o
esperado cresce com o relógio mais depressa do que 500 ml movem o real, então
quem continua atrás o vê de novo umas duas horas depois. Medido numa janela de
7h às 20h com meta de 3 L, bebendo 500 toda vez que ele pede: **cinco aparições
no dia**. A primeira versão desta seção afirmava que ceder DESLIGAVA a regra, e
a simulação desmentiu — cadência de duas horas não é o mesmo que aparecer uma
vez. E ela não passa na frente de treino em andamento nem de refeição vencida:
aquilo tem hora marcada; sede não.

**O campo que diz para onde voltar é uma lista fechada.** `LogHydrationView`
aceita POST de qualquer sessão autenticada, e `?next=` livre seria
redirecionamento aberto. O pedido manda o NOME da tela, `DESTINOS` resolve, e o
que não estiver lá cai no destino padrão.

**Idempotência é requisito da fila offline.** Água SOMA e suplemento ALTERNA —
as duas precisam de `op_id`. Marcação de refeição usa `update_or_create` e já é
segura; se alguém a trocar por contador, a fila quebra em silêncio.

**A carga de treino entra na fila offline como EVENTO, e a rota da FICHA
continua fora.** As duas frases são a mesma decisão, e separá-las é o que
resolveu o problema.

Estado é o que não pode ser enfileirado. O formulário da ficha mandava
`series_feitas`, um contador derivado que ela só atualizava no sucesso — offline
ele ficava defasado por um, sempre, por construção e não por corrida. **Nenhum
template emite mais esse campo**: aquele formulário saiu com o cartão da ficha
em 10/09/2026, e há teste varrendo `templates/` para ele não voltar. A rota e o
descarte na drenagem continuam, porque item gravado por versão antiga do app
ainda pode chegar. E o replay
desse corpo não é escrita inofensiva: a view envolve `record_load` num laço mais
um `DELETE ... set_number__gt=N`. Medido em
`workouts/test_carga_fora_da_fila.py`: três séries a 40 kg mais uma quarta a 50
com o contador antigo terminam em TRÊS séries a 50 — a quarta some e o peso das
anteriores é reescrito; com o contador em zero, o dia daquele exercício é
apagado. Aquela rota (`/treino/exercicio/<id>/carga/`) segue fora de `ROTAS` nos
dois lados, e item já gravado por versão antiga é DESCARTADO na drenagem.

Evento é o que pode. `/treino/agora/serie/` manda "fiz mais uma série" e **não
manda número nenhum**: quem decide o `set_number` é o servidor, na hora de
aplicar, procurando o primeiro número livre — a mesma conta que
`_primeira_serie_livre` já fazia na tela online, e igualá-las é o que faz a
sequência offline terminar idêntica à online. Não é `maior + 1`: quem anotou a
série 3 e deixou a 1 em branco recebe a 1 nos dois caminhos.

**A identidade é do TOQUE offline e da PÁGINA online**, e isso é um par, não uma
inconsistência. O HTML renderiza um `op_id` por renderização, e é ele que faz
toque duplo e botão voltar corrigirem em vez de duplicar — era o papel do
`update_or_create` no `set_number`. Offline a página não recarrega entre um
toque e outro, então `fila.js` DESCARTA o `op_id` do formulário e sorteia um por
captura; sem isso os três toques sairiam com o mesmo identificador, o servidor
recusaria os dois últimos como repetição, e a pessoa terminaria o treino com uma
série de três que fez. O descarte precisa acontecer na captura porque
`corpoDoItem` mantém o PRIMEIRO `op_id` que encontra, e o do HTML vem antes.

**Desfazer também é idempotente.** Ele entra na mesma fila, e a fila reenvia
quando a resposta se perde no meio: sem `op_id`, um único toque reproduzido
apagaria DUAS séries — a que a pessoa desfez e a anterior, que ela queria
manter.

**O `IntegrityError` concorrente é retentado, e a medição é o motivo.** Duas
threads leem o mesmo "primeiro número livre" e as duas tentam gravá-lo; o
`UniqueConstraint`, que está certo em existir, derruba a segunda.
`select_for_update` não resolve — com o dia vazio não há linha para travar. Oito
`append_set` simultâneos gravavam CINCO e perdiam três; hoje o serviço aceita a
colisão e tenta de novo com o conjunto de ocupadas RELIDO, e grava oito. O teste que guarda
isso precisa de `threading.Barrier`: sem ela, cada thread paga o handshake da
própria conexão, as oito se escalonam, a corrida nunca acontece e o teste passa
**mesmo sem o retry** — foi o que a sabotagem mostrou.

**O DIA viaja com o evento, e o servidor não confia cego.** A fila drena quando
a rede volta, e isso pode ser noutro dia: quem fecha a última série às 23h50 e
só recupera sinal ao sair da academia via o treino inteiro cair no dia
seguinte — sumia do dia certo e virava sessão fantasma no outro, e
`estado_do_treino`, a ofensiva e o histórico leem por DATA, então os três
passavam a mentir juntos. A tela escreve a data no formulário e ela viaja no
corpo como qualquer campo. O servidor recusa o que não faz sentido: data
ilegível, FUTURA (relógio adiantado escreveria num dia que ainda não existe, e
aquele registro ficaria invisível para toda tela que pergunta "e hoje?") ou mais
velha que sete dias cai em hoje. Sete porque a fila drena na primeira abertura
com rede — mais que isso é aparelho esquecido, e escrever um treino de mês
passado seria pior que descartar a data.

Provado no navegador em 08/09/2026, com a rede desligada pelo CDP: três toques
sem rede não navegam, viram três itens com `op_id` distintos e sem contador no
corpo, e drenam para as séries 2, 3 e 4 com os pesos de cada toque. O `getAll()`
do IndexedDB devolveu os três fora de ordem (2, 3, 1) — é a inversão que o `seq`
existe para consertar, vista ao vivo.

**A dose do catálogo vale POR SESSÃO, e a semana é aparada depois.**
`splits.json` diz quantas séries cada exercício pede numa sessão; repetir a
letra A duas vezes na semana soma o peito duas vezes. A resposta NÃO é reduzir
a dose — quem repete a letra quer a frequência maior. `prescrever_semana` monta
a dose cheia e só então apara: `aparar_volume_semanal` remove ISOLADORES até
nenhum grupo passar do teto semanal de séries efetivas — até 16/09/2026
`TETO_SEMANAL_POR_GRUPO = 20` para todo grupo; desde 17/09 o teto é do NÍVEL
e da FREQUÊNCIA com que o grupo é treinado na semana (`TREINO.md`, tabela B;
`services.tetos_da_semana`) —, e `escolher_para_o_tempo` corta até a sessão
caber no tempo informado. A versão anterior cobrava do exercício principal e
derrubava o supino de quatro séries para duas.

**Série secundária não é série direta**, e é por isso que o teto fala em
efetivas: `volume_efetivo` conta 1,0 para o grupo trabalhado e
`PESO_SECUNDARIO = 0,5` para cada `secondary_muscles`. Um tríceps de supino não
substitui um tríceps de tríceps.

**PRINCIPAL é o composto de MAIOR DOSE de cada grupo, um por grupo por
sessão.** Duas versões anteriores foram medidas e reprovadas: "o primeiro
composto do grupo" rebaixava a remada só por vir depois da puxada; "quatro
séries = principal" tornava intocáveis os DOIS pressões de peito do mesmo dia, e
o peito fechava a semana com 27 efetivas contra o teto de 20 sem nada que o laço
pudesse ceder. E não use `secondary_muscles` como proxy de importância: ele dá
três secundários para "Flexão de braço", que é acessório, e um para
"Leg press 45°", que é principal.

**O aparo tem TRÊS TRAVAS, e as três vieram de medição.** Só sai quem treina o
grupo DIRETAMENTE — senão o laço apagava a prancha para resolver um excesso de
core que vinha de agachamento e stiff; nunca o último exercício direto de um
grupo — senão antebraço saía inteiro da semana; e cede sempre a sessão mais
cheia. Uma primeira versão esvaziou a sexta-feira até dois exercícios e onze
minutos.

**Tempo disponível é TETO, não cota a preencher.** Noventa minutos informados
não obrigam a montar noventa; o perfil de referência (homem, 27, 102 kg, 1,85 m,
segunda a sexta) recebe sessões de 39 a 66 minutos, e isso está certo. Reduzir
um principal a duas séries só é aceitável com razão calculada — nunca para
encaixar o relógio.

**A pergunta do tempo é uma FAIXA, e o topo dela é teto duro.** Era um inteiro,
"Tempo disponível", com a ajuda prometendo que o treino cabia nele — e a
promessa era falsa e estava medida: 30 informados entregavam 32, 45 entregavam
48, 60 entregavam 61. A culpa não era do corte, era da pergunta: o mesmo número
servia de ALVO e de TETO, e `_teto_em_segundos` somava até 5 minutos de folga
para uma sessão não ser rejeitada por trinta segundos. Com faixa, o piso é o
alvo e o topo é o limite — Rápido até 30, Padrão até 60, Completo até 65, e
"sem limite rígido", que é `None` e não corta nada. A folga saiu.
`Profile.duracao_treino` é o dono da resposta; `TrainingDay.duration_min`
continua gravado porque `plans/meal_planner.py` precisa dele, e deixou de ser a
pergunta.

**O RÓTULO SÓ DIZ O TETO — Rápido 30, Padrão 60, Completo 90 — e desde
17/09/2026 a sessão CHEGA lá.** "Padrão — 45 a 60" e "Completo — 60 a 90"
prometiam pisos que o gerador não garantia: medido em 16/09, com teto 60 a
sessão ia de 14 a 59 minutos, e com 90 o treino era IDÊNTICO ao de 65 em 54
combinações, porque a faixa de séries do nível (no máximo 16–20) e o
catálogo de 35 ativos limitavam a sessão antes do relógio. `Completo` valeu
65 por um dia, para o rótulo ser verdade por construção. Com os 63 ativos e a
doutrina do `TREINO.md` ele voltou a 90 (`accounts.0034`, só rótulo), e
"Sem limite rígido" continua "o mesmo que Completo", fora de todo formulário
(`DuracaoTreino.escolhas_visiveis`; segue no `choices` e no banco para quem
já tem). O seletor da ficha diz a faixa CALCULADA da rápida ("~19–24 min"), e
não "até 40". Medido em 17/09 na letra A do intermediário de cinco dias:
Padrão 25 séries em 59 minutos; Completo 27 em 62–63.

**A DOUTRINA DO TREINO MORA EM `docs/briefs/treino/TREINO.md`, e os testes
LEEM o arquivo (17/09/2026).** É o contrato do gerador por nível × tipo de
dia — `um_grupo`, `dois_grupos`, `tres_grupos`, `inferior`, `superior`,
`full` —: exercícios por grupo (grande/pequeno), séries por exercício,
séries diretas por sessão, semanal por frequência do grupo, descanso
(composto 80 s, isolador 60 s) e duração esperada, com Schoenfeld, Helms e
Israetel citados onde o número vem deles. `workouts/doutrina.py` lê as
tabelas do disco uma vez (`lru_cache`) e o mapa "Tipos de dia" diz o tipo de
cada letra de cada modelo; `workouts/test_treino_md.py` reprova o gerador
contra o documento, e `workouts/test_ficha_de_verdade.py` é o TESTE DOURADO
do dono, imutável: intermediário, 5 dias, `abc2`, Padrão → A com ≥ 6
exercícios (≥ 4 peito, ≥ 2 tríceps), 21–28 séries diretas, 55–65 min, nas
DUAS opções; Completo 60–80 min; o mesmo para 4 dias e 3 dias em ABC; os
outros níveis com os valores do `TREINO.md`. Se não passar com o catálogo,
ajusta-se o motor ou pede-se catálogo — nunca se afrouxa o teste. Antes da
missão: 4 exercícios, 13 séries, ~36 minutos.

Cinco decisões da doutrina que custaram medição, e o motivo de cada uma:

- **a faixa de séries é do TIPO DE DIA e do nível, e o preenchimento vai até
  o TOPO dela** (`preencher_ate_a_faixa`): parar no piso deixava "Peito e
  tríceps" em 22 séries e 54 minutos com o catálogo inteiro. O que segura é
  o relógio, o teto semanal e o teto por exercício do nível — e para o
  iniciante (2–3 por exercício) a mesma função DESCE até o topo antes de
  subir: o supino de quatro do catálogo vira três para ele, e "Peito,
  tríceps e ombro" com oito exercícios fecha em 18–20;
- **`tres_grupos` tem o grande em 4 e os pequenos em 2, com a MESMA faixa de
  `dois_grupos`**: o teste dourado vale para "Peito, tríceps e ombro" de 3 e
  4 dias, e três pequenos em 3 dariam dez exercícios e 31 séries antes do
  preenchimento. Os modelos de `abc` foram redesenhados para isso (peito 8,
  tríceps 4, ombro 4; costas 8, bíceps 4, antebraço+trapézio 4; quadríceps
  4, posterior 4, panturrilha 4, core 2);
- **a frequência da tabela B conta o grupo TREINADO — direto ou como
  secundário de composto** (`grupos_treinados`): contando só o anunciado, o
  ombro de "Pernas e ombros" caía uma vez (teto 23) com vinte séries
  efetivas vindas dos supinos e das remadas, e o aparo tirava um dos três
  exercícios de ombro do dia que se chama "Pernas e ombros". A tese da
  tabela — mais sessões, mais recuperação, mais volume — vale para o
  estímulo secundário do mesmo jeito;
- **a margem de secundários do teto efetivo é ABSOLUTA (8 a 2×, 9 a 3×), a
  mesma em todo nível**: o secundário vem do catálogo, não do nível; com a
  margem proporcional (25%) o iniciante a 2× perdia o terceiro peito;
- **o avançado é igual ao intermediário em Completo na sessão de dois
  grupos** (27–28 séries, 62–63 min): sete exercícios a quatro séries são 28,
  o máximo físico da linha; o que separa os níveis hoje é a tabela B (o
  avançado fecha "Costas e bíceps" em 28, o intermediário em 26). Cinco de
  peito para o avançado é dívida de CATÁLOGO, escrita no documento.

A duração da tabela A foi MEDIDA em 17/09 com Completo, todas as letras de
todos os modelos, e não estimada: onde a medição discordou da primeira
versão, a medição venceu, e a lista de ajustes está no documento.

**E a pergunta saiu da TELA em 10/09/2026, sem sair do motor.** Ela pedia uma
calibração que ninguém consegue fazer antes de ver uma ficha — "rápido, padrão,
completo ou sem limite?" é resposta que depende de já conhecer o resultado. O
motor continua processando as QUATRO faixas, e quem já respondeu continua com
o que respondeu; o que mudou é que `duracao_treino == ""` deixou de ser "ainda
não respondeu" e virou "não tem como responder". Um estado que a pessoa não
pode mais mudar precisa de um VALOR, não de um buraco: a migration `0029`
escreve "padrão" (até 60) para quem estava em branco, uma vez, deixando
rastro — em vez de um padrão em tempo de leitura, que mudaria toda consulta
futura sem ninguém ver.

**E voltou para a TELA em 16/09/2026 — na área de Treino, onde a ficha está.**
A avaliação daquele dia (D4) mostrou que "escolha da área de Treino" era
frase sem porta: a ficha oferecia só a "Versão rápida" do dia, "Dados do
cálculo" dizia "até 60 min" fixo, e o Completo de 90 — a ficha inteira —
não tinha onde ser escolhido. Hoje "Seu programa" no painel tem
Rápido · Padrão · Completo com o teto de cada um (`DuracaoDoTreinoView`,
`POST /treino/duracao/`, lista fechada em `escolhas_visiveis`); "Aplicar"
grava `Profile.duracao_treino`, deriva `TrainingDay.duration_min` como
`TrainingForm.save` já fazia, e `sync_active_routine` remonta — faixa
diferente da que a ficha guarda é `rotina_invalida`. As travas continuam e a
tela diz qual valeu: série registrada hoje, a ficha muda amanhã; ficha
ajustada à mão não é remontada. Medido no intermediário de cinco dias:
Padrão 23–26 séries/~58 min; Completo 26–28 séries/58–68 min.

**O horário do treino é OPCIONAL, e a ausência é um estado de verdade.** Ele
nunca participou da montagem da ficha — `create_routine` jamais leu
`start_time` —, e exigi-lo fazia todo mundo sair do passo 3 com o padrão de
19:00, que a tela então repetia em cada cartão como se fosse a rotina da
pessoa. Sem horário, `_training_end_for` devolve `None` e o cardápio volta a
ser distribuído pela janela de sono: o mesmo caminho de quem não cadastrou dia
de treino. O que não se faz é inventar um padrão para completar a conta.

**Em 10/09/2026 ele saiu da INTERFACE inteira** — do passo 3 e do Perfil —,
porque exibir um valor que não participa de nada e não dá para editar faz
procurar o botão que não existe. **O dado permanece no banco**: `save()` relê
os horários gravados e os devolve no `update_or_create`, senão `start_time=None`
nos defaults apagaria em silêncio o que o cardápio de quem já usa o app lê. Há
teste postando `start_time=06:30` num formulário que não tem o campo e provando
que o 19:00 gravado sobrevive.

**A experiência move o TETO SEMANAL POR GRUPO e a dose por exercício, e não
a lista.** `Profile.experiencia` valia 12, 20 ou 24 séries efetivas até
16/09/2026; desde 17/09 `TETO_POR_EXPERIENCIA` vem da tabela B do `TREINO.md`
para o grupo que cai UMA vez (15, 23, 28), e o grupo que cai duas ou três
vezes tem teto maior (`tetos_da_semana`). Vazio, que é "ainda não respondeu",
vale intermediário. Ninguém tem a ficha reescrita por uma pergunta nova, e a
tela não afirma um nível que a pessoa não declarou. Ela não mexe em QUAIS
exercícios entram: rebaixar o agachamento por ser "complexo demais para
iniciante" seria o app tirar sozinho o movimento que mais interessa a quem
está começando — o iniciante faz os mesmos movimentos com 2 a 3 séries.

E **o teto semanal é de APARO, não promessa** — vale para os três níveis e para
o 20 de sempre. `aparar_volume_semanal` só remove isolador que treina o grupo
diretamente, e nunca o último deles, então excesso que vem de secundário de
composto principal fica onde está: medido, o ombro fecha em 14,5 com o teto em
12, porque baixá-lo exigiria derrubar o supino. O que o número move de verdade
é o volume da SEMANA — 65 séries contra 88, no perfil de quatro dias. Quem
tratar o teto como garantia vai "consertar" as travas e esvaziar um treino.

**O catálogo cobre o contrato de variedade, e `abc B` foi o último buraco.**
Quatro peitos, quatro costas, três tríceps e três bíceps por semana é o que o
produto pede para o intermediário de 45 a 60 minutos. O modelo `abc B` listava
TRÊS dorsais com quatro no catálogo; `Barra fixa assistida` entrou em
10/09/2026, com a mesma dose que já abre `abcd B` e `abcde B`.
`Remada curvada com barra` continua aposentada e não volta por essa porta.

**O EQUIPAMENTO ESTÁ NO PERFIL DESDE 17/09/2026 (tarde), E O MOTOR OBEDECE
POR SUBSTITUIÇÃO — nunca por filtro.** `Profile.equipamento`
(`accounts.models.Equipamento`: completa · básica · casa com halteres · só
peso do corpo; pergunta na etapa 2 do onboarding e no Perfil), o mapa de
cada resposta para `Exercise.equipment` no `TREINO.md` ("Mapa de
equipamento", lido por `doutrina.equipamentos_de`), e
`services.substituir_por_equipamento` ANTES de `prescrever_opcoes`: o item
do modelo fora do perfil é trocado por exercício ativo do MESMO `padrao` e
grupo dentro do perfil que ainda não esteja no modelo, com a dose do item
trocado; sem substituto, sai. `TrainingPlan.equipamento` é retrato; mudar
no perfil torna a ficha inválida e remonta, como nível e faixa. **O default é
"completa" nos dois lados e NÃO é vazio**, ao contrário de `experiencia`:
toda ficha anterior à pergunta nasceu do catálogo inteiro, então "completa"
é a verdade dela, e ninguém foi remontado pela pergunta nova. "Completa"
custa zero consultas (o filtro nem roda); perfil restrito custa UMA consulta
ao catálogo por prescrição — e a conferência (`_prescricao_bate` +
`_prescricao_confere`) refaz a conta COM o perfil, inclusive na
pré-conferência de reps e descanso, senão o afundo que substituiu o
agachamento reprovava e a Home oferecia "regenerar" para sempre a quem
treina em casa.

Por que substituição e não filtro — a medição de 10/09/2026, que continua
valendo: a prescrição não SELECIONA exercícios, `prescrever_semana` copia
MODELOS curados de `splits.json`, com os nomes escritos; filtrar por
equipamento não troca de exercício — abre BURACO no modelo (em "casa +
halteres" oito modelos perdiam grupo sem substituto e `abcde-C` terminava
com ZERO exercícios). E os modelos já listam quase todas as alternativas: em
"básica" o `abc2 A` perdia os três itens de barra SEM repor, porque todas as
pressões de peito sem barra já estavam nele — a letra fechava em 6
exercícios e 50–52 min, dourado vermelho. Os **cinco de peito e tríceps sem
barra** (supino declinado com halteres, crucifixo inclinado com halteres,
flexão com pés elevados, flexão fechada, tríceps coice) entraram FORA de
todo modelo, de propósito, para serem exatamente esse substituto: a ficha
de "completa" ficou idêntica (ninguém recebeu "regenerar?") e básica E casa
com halteres fecham o dourado da letra A (7 exercícios, 25 séries, 59 min
no `abc2`). "Só peso do corpo" continua `expectedFailure` nomeado no
dourado: B tem um exercício e C dois, e a lista do que falta está no
`BACKLOG.md`. **E nesse perfil a versão rápida NÃO aparece — por regra,
não por falta (decisão de 18/09/2026, opção "manter ausente")**: "Menos
tempo hoje?" só existe onde a rápida CORTA alguma coisa (`hoje.rapida_muda`
em `preparar_dia`), e a letra A de só peso do corpo tem 3 exercícios em ~30
minutos — cabe inteira nos 40 da rápida. Gerar uma "rápida com menos
séries" ali seria o mesmo treino com outro nome, o defeito de veracidade
que o app recusa desde a faixa de duração. Provado em produção com conta
descartável (18/09, casa com halteres oferece; peso do corpo não) e
guardado em `workouts/test_rapida_por_perfil.py`, com controle positivo.

**Varridos os 31 recortes possíveis de equipamento, UM era viável em 10/09: o
conjunto completo** — ou seja, nenhuma restrição, que é o comportamento de
hoje. A causa era estrutural, três monopólios: **core** 3 de 3 em peso do
corpo, **antebraço** 2 de 2 em barra, **panturrilha** 2 de 2 em máquina. Com
os 63 ativos de 17/09/2026 sobrou o core, e **casa + halteres virou PARCIAL**:
nenhum grupo sem substituto, nenhuma sessão abaixo do piso, e três grupos
sem folga (panturrilha, posterior, trapézio).

O que destrava, medido: **casa + halteres precisava de DEZ exercícios em
10/09, e precisa de TRÊS desde 17/09** — e não de "três" no sentido de
10/09. Aquele três era a conta da COBERTURA — todo grupo com pelo menos uma
opção —, e ela engana: com exatamente três, sete dos onze grupos ficariam
com UM exercício, a semana cairia de 26-29 movimentos distintos para 13-14
com o mesmo número de séries, e o teto por experiência pararia de funcionar,
porque `aparar_volume_semanal` nunca remove o último exercício direto de um
grupo. O piso real é a FOLGA (duas opções por grupo usado): eram dez, e
quatro variantes com halteres entraram com foto conferida (stiff,
panturrilha em pé, rosca de punho, agachamento goblet) — faltam a
panturrilha sentado, a elevação pélvica e a remada alta com halteres, com
mídia curada. A tabela está no `BACKLOG.md`; a régua, em
`workouts/test_capacidade_de_ambiente.py`.

**EXERCÍCIO ATIVO TEM DEMONSTRAÇÃO, e são quatro contratos com nove guardas.**
`video_url` embutível, `clip_kind` não vazio, `tem_anatomia` verdadeiro e
presença em `media_map.json`. Isso não é burocracia: foi o que bloqueou a
expansão de Casa + Halteres em 10/09/2026. Nove variantes com halteres foram
cadastradas, mediram bem — sete grupos sem folga viraram um, variedade de 13-14
para 18-19 movimentos por semana — e voltaram atrás, porque escolher vídeo exige
assistir e este ambiente não assiste. Quatro delas entraram em 17/09/2026 pela
porta certa — foto conferida pelo dono num mosaico de veto, licença
registrada em `curadoria` no `exercises.json` —, junto com outros 24; o veto
é `manage.py desativar_exercicio <nome>` (reversível com `--reativar`), e
ele desativa no JSON e no banco. O que falta para os cinco restantes é
curadoria de MÍDIA, não decidir o que cadastrar.

**O CONTRATO DE MÍDIA VALE PARA QUEM TEM APARELHO — o peso do corpo pode ser
ativo sem vídeo (decisão 1 da avaliação de UX, 20/09/2026).** O dono decidiu
que o catálogo de peso do corpo NÃO depende de mídia: "sem vídeo fica sem
vídeo". A régua acima passou a valer só para exercício COM aparelho — todo
`equipment != bodyweight` ativo continua exigindo vídeo curado, e todo vídeo
que EXISTIR (inclusive nos de peso do corpo que já têm um) continua com o
contrato inteiro (embed, unicidade, anatomia, foto no mapa). O peso do corpo
sem vídeo entra com nome, músculos, dica e progressão; a tela cai
graciosamente no "Sem demonstração cadastrada" (`_demonstracao.html`, que já
tinha o ramo). Os guardas mudaram de `filter(is_active=True)` para
`.exclude(equipment="bodyweight")` (o vídeo é obrigatório) ou
`.exclude(video_url="")` (o vídeo presente é validado); há teste único da
conjunção em `test_capacidade_de_ambiente`.

**34 EXERCÍCIOS DE PESO DO CORPO, COM PROGRESSÃO (20/09/2026).** Cobrem os
grupos que faltavam — quadríceps, posterior, glúteo (na cadeia posterior,
`hamstrings` até 21/09/2026; desde então `glutes`, ver abaixo), panturrilha, ombro, costas,
bíceps — e adensam peito/tríceps/core, para a ficha desse perfil ter volume
COMPARÁVEL às outras (medido: ~94% do volume semanal da completa; letra A com
2 opções de 5 ex/52 min, B 8 ex/58 min, C 8 ex/58-59 min ×2). O motor preenche
por SUBSTITUIÇÃO (`padrao`+grupo), então `splits.json` não mudou. A LETRA A
continua `@expectedFailure` no dourado por um motivo FÍSICO: o modelo de
academia enche o peito com crucifixo (abertura), e não há crucifixo sem carga
— sobram as pressões, ~3 por opção, não 4. O dourado não afrouxa; a
comparabilidade é provada à parte (`test_volume_peso_do_corpo`). A PROGRESSÃO
é o campo `Exercise.progressao` (`{"movimento","nivel"}`, 1 = mais fácil): a
leitura mostra a escada do movimento (`services.escada_de`) do fácil ao
difícil, com "você está aqui"; vazio para quem usa aparelho (a progressão dele
é a carga). Os vereditos de ambiente melhoraram: peso do corpo
NAO_SUPORTADO → PARCIAL (bíceps/antebraço/trapézio sem folga é limite físico),
casa com halteres PARCIAL → SUPORTADO.

**COBERTURA NÃO É QUALIDADE**, e a régua cobra as duas. Como efeito colateral, o
catálogo virou contrato: aposentar um dos dois exercícios de panturrilha derruba
o veredito da própria academia, porque o grupo fica com opção única — e a suíte
diz qual capacidade se perdeu.

O campo de ambiente NÃO existiu no perfil até o motor poder obedecê-lo, de
propósito: guardar preferência que não vira nada é o mesmo defeito de
veracidade que `prioridade == ""` evita do outro lado. Quando o motor passou
a obedecer (17/09, tarde), `workouts/test_capacidade_de_ambiente.py` virou
ao contrário — o perfil TEM a pergunta, o formulário a FAZ, o motor LÊ
`equipment` — e os ambientes medidos passaram a ser os QUATRO PERFIS do mapa
(completa e básica SUPORTADO; casa PARCIAL; peso do corpo NAO_SUPORTADO).

**`Equipment` tem UM consumidor no motor: `substituir_por_equipamento`.** O
campo nasceu para o assistente de troca ("a máquina está ocupada"), que
entrou em `7819b30` e saiu em `d86d9c7`; `DISPUTADOS` e `disputa_equipamento`
sobreviveram à remoção como código morto por três campanhas e saíram em
10/09/2026. A substituição por PERFIL acontece antes de prescrever; a
troca por EXERCÍCIO é a de baixo.

**"OUTRAS FORMAS" É A INTERAÇÃO PRINCIPAL DA FICHA (17/09/2026, noite).** A
pessoa não escolhe mais entre opção 1 e 2; escolhe COMO fazer cada
movimento. `TrocaDeExercicio(user, original, substituto)` (migration
`workouts.0029`) é customização POR EXERCÍCIO — vale em toda letra, toda
semana e toda opção em que o original apareça — e NÃO toca em
`SessionExercise` nem em `customized_at`: a ficha continua retrato, a
rotação continua, `rotina_invalida`/`_prescricao_bate` não a enxergam. A
aplicação é EM MEMÓRIA (`services.aplicar_trocas`, uma consulta por tela,
logo depois de carregar as linhas do plano — painel, ficha, execução e
leitura passam pelo mesmo ponto): o item passa a apontar para o substituto
com a MESMA dose, então trocar não altera séries nem volume (diferença 0).
`ExerciseLog` grava no exercício FEITO; a linha do original responde pelo
substituto na prescrição de hoje por JOIN (`_linha_do_exercicio`), na
consulta que já existia — o orçamento do POST da série continua 20. As
alternativas (`alternativas_de`) são do mesmo `padrao` e grupo, dentro do
equipamento do perfil, FORA DA MESMA LISTA (sessão + opção — duplicata só
é problema no mesmo treino; a outra opção é outro dia), o equipamento mais
próximo primeiro; a ficha só anuncia "outras formas" onde a leitura lista
alguma (`contar_outras_formas`, a mesma régua — o QA achou a linha
anunciando e a leitura vazia quando as réguas divergiam). A lista mora na
LEITURA do exercício, com foto (o primeiro quadro da free-exercise-db) e
"Trocar"; a leitura do substituto diz "No lugar de X", mostra o histórico
de X e tem "Voltar ao original". `POST /treino/trocar/` é estado absoluto
(trocar de novo atualiza, `desfazer=1` apaga, sem `op_id`), volta para a
leitura com a mesma volta (`?de=`), e recusa original fora da ficha ou
substituto que não é forma do movimento no equipamento. A leitura passou a
TER formulários, e a régua "ver não é executar" virou POR DESTINO: todo
`<form>` do `<main>` aponta para a troca, nunca para a série. Custos
medidos: leitura 9 → 11 (trocas + alternativas; o perfil vem do
`dispatch` e as linhas vêm sem o exercício), ficha 15 → 17 (trocas +
contagem), Home 43 (no teto), painel 20.

**RODADA 2 DE EXPERIÊNCIA — OS SETE ATRITOS (24/09/2026).** Todos medidos
no navegador antes de tocados, e cada um com a régua que impede a volta:

- **UM CLIQUE PARA TREINAR.** O CTA do painel apontou para `workouts:now`
  até 22/09, foi movido para a FICHA ("o fluxo pulava a etapa em que a
  pessoa decide") e VOLTA agora para a execução, por decisão do dono. As
  duas leituras são verdadeiras e medem gente diferente: quem ainda não
  decidiu precisa da lista, e quem já decidiu pagava dois toques toda vez.
  "Ver ficha do Treino X · N exercícios" continua logo abaixo — o que mudou
  foi qual dos dois é o principal. O rótulo diz o estado: "Começar treino"
  sem série hoje, "Continuar treino (3 de 8)" com o treino em andamento.

  E o **cartão AGORA da Home acompanha**, no mesmo commit: ele usa o MESMO
  rótulo, e um rótulo com dois destinos é o defeito que a rodada 1 nomeou.
  Isso desfaz o requisito de 13/09/2026 ("'Começar treino' abre a FICHA,
  nunca o primeiro exercício com o vídeo tocando") — a premissa dele não
  existe mais: nenhum `autoplay` é escrito no HTML e o vídeo do exercício
  nasce no toque. `workouts/test_ux_rodada2.py`, `plans.tests.AcaoAgoraTests`.
- **O PLACAR DIZ O TREINO, NÃO OS REGISTROS.** `minutos_entre_registros`
  descreve o BANCO; `EstadoDoTreino.minutos_do_treino` é da primeira série
  ao "Encerrar treino" (`EscolhaDeTreino.encerrado_em`) — quem anota a
  última série às 19h05 e encerra às 19h40 passou 35 minutos a mais lá.
  **Sem "Encerrar" o número continua sendo o intervalo de sempre**: inventar
  um fim que ninguém marcou seria o defeito que a frase antiga evitava. E
  `exercicios_feitos`/`exercicios_do_dia` dão o tamanho que a lista "Sem
  registro hoje" não dava — 3 nomes podem ser 3 de 4 ou 3 de 12.
- **A OFENSIVA EM ZERO CONVIDA.** "Recomeça hoje: … Ontem faltou dieta ou
  água" saiu inteiro: um contador em zero só tem uma leitura, e
  acrescentar "faltou" cobra duas vezes pela mesma coisa. A frase virou a
  porta mais barata do dia — "registre uma refeição ou um copo d'água" —, e
  o TREINO fica de fora de propósito, porque tem dia marcado. O VERBO ainda
  lê `falta_ontem`, e é a única coisa que ele decide: `None` é exatamente
  "ontem não era da conta", e ali "recomeça" seria falso — quem chegou hoje
  lê **"Comece hoje"**. `falta_ontem` continua sendo calculada por inteiro
  (o número é verdadeiro e é lido em outro lugar); o que saiu foi a frase. As de risco, de 1 dia, de
  menos de 7 e de 30 não mudaram. `plans/test_ux_rodada2.py`.
- **`/hoje/` responde 301 para a Home.** Era a rota do cardápio até 22/09 e
  virou 404 para a primeira tela do app. `RedirectView` com
  `pattern_name="plans:today"` e não uma barra escrita: sob
  `set_script_prefix("/demo/")` ele reverte para dentro do demo.
  `config/test_rotas_antigas.py`.
- **NÍVEL E EQUIPAMENTO SÃO OBRIGATÓRIOS PARA QUEM FAZ MUSCULAÇÃO.** Os dois
  nasceram opcionais com a razão escrita ("a tela não inventa a frase"), e a
  régua continua valendo — o app não declara nível por ninguém. O outro lado
  dela era o Perfil dizendo **"não informada"**, que é admitir que a ficha
  foi montada com um palpite. A saída não é inventar: é PERGUNTAR, e só a
  quem a pergunta-porta já mostrou o bloco. O erro vai no CAMPO
  (`add_error`), que é o que faz o `aria-invalid` nascer e o "FOCO NO ERRO"
  do `pwa.js` rolar até ele. E o Perfil de quem já tinha conta sem resposta
  diz o que o motor USA, marcado como padrão.
  `accounts/test_onboarding_obrigatorio.py`.
- **A lista de corridas usa a largura do desktop** (`container_class largo`):
  abria em 480 px num monitor de 1280 enquanto Hoje, Progresso e Alimentação
  já usavam 1024 — o "celular no meio da tela" que o redesenho de 22/09
  tirou das outras e esqueceu nesta.
- **UM SÓ "REGISTRAR PESO" NA HOME.** MEDIDO com Progresso declarado: TRÊS
  caminhos para o mesmo campo na mesma dobra — o cartão AGORA, o rodapé do
  cartão do painel e a faixa `#pesar`. Os dois primeiros eram âncoras para o
  terceiro. O rodapé do cartão voltou a responder o que o cartão é (a porta
  da ÁREA, "Ver progresso"); ficam o cartão AGORA, que é a ação do momento,
  e a faixa, que é onde o campo mora.

**A área de Treino são TRÊS telas, e cada uma responde UMA pergunta.**

    painel   (`/treino/`)              -> "como é a minha semana"
    ficha    (`/treino/ficha/<id>/`)   -> "o que eu vou fazer hoje"
    execução (`/treino/agora/`)        -> "estou fazendo, e agora"

O painel mostra o treino de hoje e um cartão por sessão, e cada cartão é um
link. Ele NÃO lista exercício: "Começar treino" abre a EXECUÇÃO desde
24/09/2026 (era a ficha; ver "UM CLIQUE PARA TREINAR"), e "Ver ficha do
Treino X · N exercícios" fica logo abaixo. A ficha é uma
lista numerada — nome, séries × repetições, músculo e o marcador do movimento
principal —, e cada linha é uma porta para a execução. O selo "Principal" é o
PRIMEIRO composto de cada grupo anunciado da opção
(`services.marcar_quem_abre_o_grupo`, 17/09/2026), não todo composto: com
quatro pressões de peito por opção ele aparecia em cinco de sete linhas. A execução mostra UM
exercício: o vídeo dele, a carga, as repetições, o descanso, o desfazer e a
carga da última vez.

A divisão é por PERGUNTA, e não por tamanho de página — mas o tamanho conta a
mesma história. Medido no perfil de seis dias quando a ficha ganhou rota
própria: 259,1 kB para 72,2 kB, 22 formulários para 1, 141 botões para 8, 266
controles alcançáveis para 30. Medido em 10/09/2026, com as três telas: painel
28,9 kB e zero exercício listado; ficha 8,9 kB (2 exercícios) e 11,7 kB (7);
execução 20,0 kB com DOZE controles alcançáveis.

**Nada que se use DURANTE a série mora na ficha.** Nem vídeo, nem campo de
carga, nem cronômetro, nem histórico detalhado — a ficha é tela de preparação,
para quem ainda não decidiu o que vai fazer. `_exercicio.html`, `_drawer.html`
e `_cronometro.html` saíram do repositório em 10/09/2026 por isso.

A guarda antiga era a RELAÇÃO — botão que abre precisa de gaveta que abre —, e
ela nasceu de um defeito real: quando o cartão mudou para a ficha, a página
ficou com nove botões de vídeo e nenhum `<dialog>`. A relação continua sendo a
régua, satisfeita agora com ZERO dos dois: a ficha não tem botão de vídeo
porque o vídeo mora na execução, onde nasce inline e não precisa de gaveta. O
teste mede as duas pontas.

**A ficha de OUTRO dia não executa.** A execução lê e grava `ExerciseLog` de
HOJE; um link "fazer" na ficha de sexta, numa terça, prometeria registrar série
num treino que não está acontecendo. Fora do dia a linha é `<div>`, não `<a>`.

**Escolher exercício é ESTRITO.** `/treino/agora/?exercicio=<id>` com id
inexistente, ilegível, negativo, repetido, de outra sessão ou de outra conta
responde 404 — e não abre outro exercício. O fallback silencioso (`pedido or
atual`) mascarava link quebrado e podia tocar o vídeo errado, e um link
quebrado que "funciona" nunca é consertado. Sem o parâmetro, a tela continua
abrindo sozinha o próximo pendente. `services.ExercicioForaDaSessao` cobre os
quatro casos num lugar só, porque `estado_do_treino` só enxerga a sessão de
hoje do próprio usuário — e "não está aqui" é a mesma resposta para todos.

**Texto da ficha só afirma o que aconteceu.** Três frases já mentiram, e as três
mentiam por comparar com a coisa errada:

- *"A ficha foi ajustada para caber no tempo que você informou"* aparecia para
  quem respondeu "sem limite rígido". `aviso_de_tempo` media o corte contra o
  MODELO do catálogo e creditava ao relógio o que o teto de volume tinha
  tirado. A régua agora é `prescrever_semana` com `teto=None` — a mesma
  prescrição, sem o relógio —, e a diferença é, por construção, o que o tempo
  cortou;
- *"as duas passagens trazem exercícios diferentes"* valia num caso auditado e
  não como regra: em quatro dias a segunda passagem de A é SUBCONJUNTO da
  primeira, e em sete as três são IDÊNTICAS. O que é sempre verdade é o teto
  semanal, e é isso que a frase diz agora;
- *"85 séries no total"*, ao lado do cartão do treino de hoje, convidava a
  entender 85 séries num dia. É o total da SEMANA, e duas palavras resolveram.

**A letra repetida vira A1 e A2 na TELA, nunca no banco.**
`TrainingSession.label` é a identidade que liga a sessão ao modelo do catálogo;
"A1" gravado ali quebraria `templates_for`, a conferência de prescrição e o
histórico. `nomear_ocorrencias` calcula `rotulo` por OCORRÊNCIA — nunca por
posição na lista —, e leva junto a contagem, porque em sete dias a letra A
aparece três vezes e o template dizia "duas" para todo mundo.

**"2 grupos por dia" é ABC, e o quarto dia não existe.** A preferência
entregava ABCD, cujo quarto dia se chama "Complementares" e é trapézio,
antebraço, panturrilha, glúteo e core — não são dois grupos principais, são o
resto, e quem treinava cinco dias recebia A-B-C-D-A com o dia D no meio da
semana. Hoje ela pede TRÊS dias e produz `Split.ABC2`: peito e tríceps, costas
e bíceps, pernas e ombros, repetindo a partir do quarto dia (A-B-C-A,
A-B-C-A-B, A-B-C-A-B-C, A-B-C-A-B-C-A).

Os complementares não sumiram — foram para dentro de B e de C, e é
`repartir_ocorrencia` que os distribui: B1 leva o encolhimento, B2 leva a remada
alta; C1 leva a panturrilha em pé, C2 a sentada. **A objeção de que integrar os
complementares obrigaria sessões de onze exercícios está medida e é falsa**:
`abc2 B` tem onze itens e `abc2 C` tem doze, e a maior sessão da semana tem
SETE no tempo padrão e QUATRO no rápido. Doze só chega a quem escolheu
"Completo" ou "sem limite rígido", em 88 minutos contra um teto de 90 — ali a
pessoa pediu a ficha inteira.

**UMA LETRA, ATÉ DUAS OPÇÕES — e "A1/A2" deixaram de ser dias obrigatórios
(15/09/2026).** Medido em produção: intermediário, cinco dias, dois grupos
por dia recebia A1 com 4 exercícios/13 séries/~36 min e A2 com 4/13/~29 — a
mesma letra com conteúdos diferentes em dias diferentes, cada sessão curta, e
o nome dizendo "dois treinos". `repartir_ocorrencia` já repartia o modelo
entre as passagens; o que faltava era tratar as metades como VERSÕES da
mesma letra. Hoje (`workouts/opcoes.py`, `services.prescrever_opcoes`):

- o calendário só diz letras (A · B · C · A · B); a ocorrência de segunda e
  a de quinta carregam EXATAMENTE as mesmas linhas (`SessionExercise.opcao`
  1 e 2); `nomear_ocorrencias` só numera quando os conteúdos diferem de
  verdade — plano antigo ajustado à mão, que continua legível;
- as duas opções são equivalentes por construção: mesmos grupos anunciados,
  volume DIRETO por grupo com diferença ≤ 1 série, duração ≤ 5 min de
  diferença, metade dos exercícios próprios. A régua é o volume direto, e
  não o efetivo: a flexão de braço tem três secundários e desequilibraria
  ombro e core sem ser exercício de ombro;
- o teto semanal vale para o PIOR CASO — cada ocorrência da letra fazendo a
  opção mais pesada no grupo —, nunca para a soma das duas: ninguém faz os
  dois treinos no mesmo dia. `services.volume_da_semana(plan)` é a conta
  oficial; somar `session.exercises.all()` conta um treino que não existe;
- sem catálogo para duas opções distintas, a letra sai com UMA — o modelo
  inteiro, e não a metade que sobrou. É o caso do "Superior" de dois dias;
- **tantas opções quantas ocorrências (mínimo duas)**: com a letra três
  vezes na semana (7 dias em ABC), duas opções de meio modelo dariam, no
  pior caso, 1,5 modelo por semana, e o teto esvaziava as duas até sobrar um
  exercício de peito. Com três opções de um terço, repetir a preferida três
  vezes é exatamente a dose do modelo. Preço medido: a 7 dias o peito fica
  com TRÊS exercícios distintos na semana (o crucifixo compartilhado não
  cabe no teto em nenhuma das três) — o contrato 4/4/3/3 vale de 3 a 6 dias;
- a repartição por grupo COMEÇA PELA OUTRA OPÇÃO a cada grupo, e a
  concessão num exercício compartilhado é ESPELHADA nas irmãs: sem as duas
  regras, uma opção ficava com três compostos e a outra com um (doze minutos
  de diferença) e o teto tirava o crucifixo de uma opção só;
- a faixa de séries por sessão é do NÍVEL e do TIPO DE DIA (`TREINO.md`,
  tabela A: 21–28 para "Peito e tríceps" do intermediário; 14–18 para o
  iniciante), e o preenchimento vai até o topo dela — até 16/09/2026 era só
  do nível (12–15 / 15–18 / 16–20) e parava no piso;
- a pessoa escolhe qual faz (`EscolhaDeTreino`, uma por dia); a recomendada
  é a menos usada recentemente e é um selo, nunca uma obrigação; a
  primeira série grava a escolha; trocar depois da primeira série pede
  confirmação e não apaga nada (`ExerciseLog` é por exercício e data);
- Completo/Rápido é escolha da área de Treino, não do cadastro: a rápida é a
  opção escolhida passando por `escolher_para_o_tempo` a 40 min — não é uma
  terceira ficha, e a linha diz o que ficou de fora.

**TODO EXERCÍCIO TEM `padrao`, E AS OPÇÕES COBREM OS MESMOS PADRÕES
COMPOSTOS (16/09/2026).** `Padrao` são 22 valores de um nível só — ângulo e
pegada ficam no nome (reto e inclinado são a mesma `pressao_de_peito`;
lateral e frontal a mesma `elevacao`); se um dia precisar distinguir, é um
campo `variante`, não um padrão novo. `PADROES_COMPOSTOS` (oito) marca os
compostos, e `is_compound` tem de concordar com ele (há teste).
`equipment` já existia com os cinco valores e foi REUSADO, não duplicado.
O banco recusa exercício sem padrão ou sem equipamento (`CheckConstraint`),
e a `0022` preencheu os 36 pelo nome.

A régua nova de `equivalentes`: em cada grupo ANUNCIADO, as opções cobrem
os MESMOS padrões compostos; isolador pode diferir. Três supinos contra três
crucifixos passavam nas réguas de volume e de minutos — e treze das
dezesseis letras com duas opções eram assim (crucifixo numa, mergulho na
outra; stiff numa, mesa flexora na outra). Para a régua ser satisfazível,
`montar_opcoes` reparte o grupo anunciado por bloco de padrão composto
(`_partes_por_padrao`) e COMPARTILHA o padrão composto de exercício único; o
empréstimo do grupo ímpar continua no nível do grupo. Preço com o catálogo
ativo de hoje: **16 letras com duas opções viram 12** — `ab B`, `abcd C`,
`abcd D` e `abcde D` só tinham a segunda por acidente, e voltam quando o
modelo tiver uma segunda extensão de quadril, pressão vertical ou remada
alta ATIVA.

E `aparar_opcoes` cede EM LOCKSTEP, ensaiando numa cópia: a irmã acompanha
pelo volume DIRETO (a régua de equivalência), não pelo efetivo (a régua do
teto) — os dois divergem quando uma opção carrega mais secundário, e a
flexão de braço tem três; a concessão que a irmã não consegue acompanhar
NÃO acontece — o excesso fica, teto de aparo. E com duas opções o
PENÚLTIMO exercício direto de um grupo só sai quando o excesso é GRANDE:
mais de um quinto do teto POR OCORRÊNCIA da letra
(`FRACAO_DE_EXCESSO_QUE_DESTRAVA`), e com a própria letra repetida já
acima do teto no grupo. Sem isso a irmã seguia e a semana ficava com UM
tríceps distinto (abc2, seis dias: corda e testa saíam por um excesso de
uma série); com "nunca" o iniciante (teto 12) fechava a semana com o
mesmo volume do intermediário (73 contra 74) e o nível deixava de valer;
e sem "a própria letra" o ombro de "Pernas e ombros" pagava o secundário
dos pressões de "Peito e tríceps" a seis e sete dias. Consequência
escrita: o volume DIRETO pode ficar UMA série acima do teto (a 7 dias, A
três vezes, peito 21) — `excesso_e_irredutivel`, em `workouts/tests.py`, é
a régua dos testes e diz exatamente quando o excesso é legítimo. O custo
visível: "Pernas e ombros" tem OITO exercícios por opção (o único
desenvolvimento é compartilhado), 24–26 séries em 54–58 minutos, dentro
do teto de 60.

**GATE PERMANENTE, POR LETRA: nenhuma letra que produção tem com duas opções
pode perder a segunda.** `workouts/opcoes_em_producao.py` conta com o MOTOR
e o catálogo ATIVO (uma pessoa transitória por divisão, desfeita ao sair), e
`LETRAS_COM_OPCOES_EM_PRODUCAO` é o CONJUNTO de letras que produção tem com
duas — 16 pares em 16/09/2026, TODAS as 18 desde o deploy de 17/09. Por
letra, e não por contagem (17/09): `abcd C` perdendo a segunda enquanto
`full A` ganha uma dá "16 = 16" e é regressão para quem treina quatro dias. O teste em
`workouts/test_catalogo.py` fica VERMELHO enquanto o código local tirar a
segunda opção de qualquer letra do conjunto, e o pre-push roda a suíte: para
subir, ou o catálogo ativado devolve a letra, ou a decisão de reduzir é
tomada em voz alta, tirando a letra do conjunto com a razão escrita. O
conjunto só cresce depois do deploy que provou a letra nova. O relatório de
deploy mostra "antes / depois" por letra: `manage.py opcoes_por_letra` no
commit de produção e no candidato.

**O CATÁLOGO CRESCEU INATIVO ATÉ SUSTENTAR DUAS OPÇÕES CHEIAS (16/09/2026),
E FOI ATIVADO EM 17/09 COM FOTO CONFERIDA.** 28 exercícios novos (64 no
total) entraram com `active: false`, padrão, equipamento, dica,
articulações, secundários, chave CONFERIDA na free-exercise-db (The
Unlicense) e `candidatos` de mídia achados por BUSCA — não por visualização.
No dia seguinte entraram ativos (63; "Remada curvada com barra" continua
aposentada): cada foto conferida — mesma pessoa, mesmo movimento, sem marca
d'água, licença — e registrada em `curadoria` no `exercises.json`, com um
mosaico de veto para o dono. A régua dos modelos é a tabela A do
`TREINO.md`: cada opção é metade do modelo, então o modelo lista o DOBRO da
cota de exercícios por grupo anunciado (`CatalogoDimensionadoTests` cobra
isso com `_cotas` do `test_treino_md`) — peito 8, tríceps 6 em "Peito e
tríceps".

E os modelos também ganharam exercícios que JÁ ERAM ATIVOS onde faltava um
segundo do mesmo padrão composto (elevação pélvica em `ab B`, barra fixa
assistida em `full A`, stiff em `abcd D`...): com isso o gate fechava em 16
sem ativar nada. Medido em 16/09: ativar só "Desenvolvimento na máquina" dá
17 (`abcd C` volta); com os 28 ativos, 18 de 18 — e é o estado de produção
desde 17/09, com as sessões em 55–60 minutos no Padrão.

**O que o catálogo NÃO deixava fazer, medido em 15/09:** "peito e tríceps"
tinha 4 exercícios por opção porque o catálogo tinha 4 peitos e 3 tríceps —
duas opções distintas de 3+3 pediam 6 e 6 —, e com a letra duas vezes na
semana o teto de 20 séries efetivas deixava ~10 por sessão para o tríceps.
Sessões de 13–22 séries e 30–52 minutos eram o número daquele dia; desde
17/09/2026, com 8 peitos e 6 tríceps no modelo e o teto da frequência (40 a
2×), são 7 exercícios por opção, 24–26 séries e 57–60 minutos no Padrão
(`workouts/test_opcoes.py`), e o teste dourado cobra a letra A. A
equilibragem PRIMEIRO DÁ série à opção mais leve e só depois tira da mais
pesada: tirar primeiro deixava as duas com o tríceps em duas séries.

**O modelo declara os grupos que o NOME promete, e o resto é COMPLEMENTAR.**
`WorkoutTemplate.main_groups` é curadoria, não dedução: "grupo com poucos
exercícios" chamaria o ombro de complementar no `abcd C`, que se chama "Pernas e
ombros", e "grupo de isoladores" chamaria o trapézio de complementar no
`abcd D`, que existe para ele. A lista decide três coisas concretas —

- **o EXCEDENTE do complementar cede primeiro** quando falta tempo — a segunda
  panturrilha antes da terceira rosca. Sem essa distinção o corte protegia o que
  ninguém prometeu: medido, "Costas e bíceps" a 60 minutos saía com bíceps=1 e
  trapézio=1, porque bíceps era o grupo mais cheio entre os isoladores e o
  trapézio, com um exercício só, estava travado. Com a regra, o perfil de
  referência — cinco dias, 45 a 60 minutos — fecha a semana com costas=4 e
  bíceps=3. E o ÚLTIMO exercício de um grupo complementar só sai depois de a
  redução de série se esgotar — ver a ordem em cinco camadas, abaixo;
- **o título só nomeia grupo anunciado**, então tirar a panturrilha não torna o
  nome mentira;
- **a ficha separa as duas listas** — "Complementares desta sessão" —, e
  `TrainingSession.main_groups` é cópia congelada do modelo, pela mesma razão
  que `name` e `focus` são: plano é retrato.

**O título é MONTADO, então ele tem de caber na coluna — e a folga não basta.**
`TrainingSession.name` é `varchar(60)`, e o PostgreSQL RECUSA o que não cabe em
vez de truncar: um nome longo não seria feio, seria a montagem da ficha
estourando. Medido sobre todos os subconjuntos dos onze grupos, a pior
combinação possível dá 94 caracteres; a pior combinação REAL do catálogo de
hoje dá 51. Nove de folga é o tipo de margem que a próxima divisão gasta sem
ninguém perceber. `_frase_que_cabe` lê o limite do próprio campo do modelo e,
quando estoura, NOMEIA MENOS e conta o resto — "Quadríceps, peito e mais 4" —,
nunca cortando no meio de uma palavra.

**O título da sessão é escrito DEPOIS da prescrição, e diz só o que ela tem.**
`titulo_honesto` reescreve `name` quando um grupo anunciado não sobreviveu —
"Corpo inteiro" com três exercícios vira "Quadríceps, peito e costas", e
"Costas, bíceps, antebraço e trapézio" sem antebraço vira "Costas, bíceps e
trapézio". Três frases mentiram em produção por causa disso, e uma delas nem era
culpa do relógio: `aparar_volume_semanal` só protege o último exercício do grupo
na SEMANA, então ele pode tirar a rosca inversa de B1 e deixá-la em B2.

**O tempo curto tem UMA ordem de concessão, e ela codifica UMA prioridade:**

    grupos principais e variedade contratada -> movimentos compostos ->
    redução equilibrada de séries -> complementares -> aviso do que não coube

`escolher_para_o_tempo`, em cinco camadas: (1) sai o EXCEDENTE do complementar —
a segunda panturrilha, o segundo abdominal; (2) **reduz série**, do degrau mais
BAIXO para o mais alto, até o piso — três num composto, duas num isolado; (3)
sai o ÚLTIMO exercício de um grupo complementar; (4) sai o excedente do
anunciado, do grupo mais CHEIO; (5) só então um anunciado cai inteiro, e o
título acompanha. E no fim a série VOLTA enquanto couber, na ordem inversa.

**A camada 2 já esteve depois da 4, e a redução já foi sem grau. As duas coisas
eram defeito.** Removendo o excedente anunciado antes de reduzir série, o dia de
puxar perdia dois bíceps para caber o trapézio. Reduzindo por "quem tem mais
série", o primeiro a cair era o composto PRINCIPAL — o agachamento perde série
antes da rosca, porque é ele que tem quatro.

**E a devolução existe porque concessão cobrada sem razão é defeito.** A redução
acontece para caber; se depois dela um exercício sair, o espaço aberto fica
vazio e a ficha paga o preço sem o motivo. Medido: o dia de puxar a 30 minutos
terminava com 24 de 30, com tudo no piso.

**Série reduzida também é ajuste, e o aviso demorou a enxergar isso.**
`aviso_de_tempo` contava EXERCÍCIO removido, que era a única forma de ajuste
até a redução subir na ordem. Passou a existir ficha fortemente encolhida com
zero remoções — três dias com 55 minutos cabem inteiros baixando série —, e a
nota ficava muda enquanto a pessoa via números menores que os do catálogo.

A ordem resolve duas queixas que puxavam para lados opostos: "a ficha de 30
minutos virou agachamento e supino" é a camada 5 sem a reescrita do título, e "o
supino caiu para duas séries num perfil normal" é a camada 3 acontecendo onde a
camada 2 ainda tinha o que ceder. Medido: no perfil de 45 a 60 minutos o supino
mantém quatro séries em todas as divisões.

**A camada 1 já foi "sai o complementar inteiro", e isso também estava errado**
— pelo motivo oposto. Com ela, panturrilha e abdômen ficavam órfãos da SEMANA em
três, quatro e cinco dias: a letra C cai uma vez só nessas frequências, e o que
saía dela não voltava. Eu registrei isso como limitação aritmética e não era.

**O COMPLEMENTAR ÓRFÃO PROCURA VAGA NA SEMANA, e não só na letra dele.**
`realocar_complementares_orfaos` é a terceira coisa que eu tinha dado por
impossível e não era. Medido que o abdômen não cabia no dia de perna como
DÉCIMO exercício, escrevi que ele não cabia na semana — tratando a capacidade
de uma sessão como a capacidade das cinco. A diferença estava à vista: com
quatro dias, `A2` fecha em 24 minutos de 60, trinta e seis ociosos ao lado de
uma prancha descartada.

Abdômen não pertence ao dia de perna; ele só estava listado ali. O modelo diz
onde o complementar CABE melhor, não onde ele PODE estar. A função procura a
sessão de MAIOR FOLGA, reduz série de isolador e acessório para abrir espaço —
nunca do composto principal, nunca abaixo do piso, nunca acima do teto — e
desiste quando nenhuma sessão comporta.

Ela não mexe no volume da semana **por construção**: o candidato é um item que
já passou por `aparar_volume_semanal` e foi descartado pelo RELÓGIO, então
mudá-lo de sessão preserva o total. E não inventa nada — é o item do catálogo,
com o nome e a dose dele.

Medido no `abc2` a 45 minutos ou mais: **zero grupo órfão de três a sete
dias**. Com três dias a prancha entra em `A1`, com quatro e cinco em `A2`, e a
partir de seis a própria repartição resolve. Em "até 30 minutos" ainda sobra
órfão, e aí — só aí — `aviso_de_tempo` NOMEIA o músculo.

**Consequência que a ficha passou a ter: um exercício pode aparecer numa letra
que não o lista.** A ordem do modelo continua valendo para o que veio do
modelo; o realocado entra no fim, e a tela o mostra em "Complementares desta
sessão" como qualquer outro.

E "mais cheio" conta os exercícios que o grupo tem NA SESSÃO, não quantos deles
estão no degrau que cede. Contando o degrau, o quadríceps — três exercícios,
sendo dois compostos intocáveis — parecia o grupo mais magro da sessão e a ficha
"Pernas e ombros" terminava com UM ombro.

**O contrato de variedade 4/4/3/3 vale de TRÊS dias para cima, e o complementar
NÃO entra às custas dele.** Houve uma versão, em 10/09/2026, que removia dois
exercícios de bíceps do dia de puxar para caber trapézio e antebraço — a semana
fechava com bíceps=1 —, e eu cheguei a escrever um teste que media essa
concessão e a dava por boa. Estava congelando o defeito.

A saída não foi abrir mão do complementar: foi **reduzir SÉRIE em vez de remover
exercício**, e reduzir na ordem certa. Medido no dia de puxar a 60 minutos com
três dias: quatro costas, três bíceps, trapézio e antebraço cabem em 60 exatos,
com as roscas em duas séries e as costas intactas.

**Preferência de divisão que cede, cede EM VOZ ALTA.** `split_for` cruza
preferência com frequência e a frequência manda — quem pede "1 grupo por dia" e
treina quatro vezes recebe ABCD, porque uma divisão maior deixaria parte do
corpo sem treinar nenhuma vez. A regra está certa; o que estava errado era a
tela mostrar ABCD e o Perfil continuar dizendo "1 grupo por dia".
`divisao_explicada` devolve o pedido, o aplicado e o motivo, e a ressalva só
aparece quando os dois divergem.

**A ADAPTAÇÃO DA CARGA É LEITURA, e mora em `workouts/adaptacao.py` — um
módulo PURO com o estado nomeado (T2.1, 17/09/2026).** Ele não abre consulta,
não olha o relógio e não fala com a rede (`workouts/test_adaptacao.py` lê o
texto do módulo e tem controle positivo); recebe o que `load_history` já
carregou — `sessoes` (≤ 10 datas) e `ultimo_registro`, do MESMO laço, sem
consulta a mais — e devolve `Progressao(estado, valor, razao)` com `Estado`
em `SUBIR`/`MANTER` e `MUDA_CARGA = {SUBIR}` dizendo quem muda o número do
campo. É o que permite simular um ano de treino em memória para calibrar
RETOMAR e ESTAGNADO (T2.3) antes de publicar. A regra é a dupla progressão
de 13/09 com UMA correção: fechar a faixa é fechar NA MESMA carga — 60/60/55
com todas as reps no topo era SUBIR para 62,5, e virou MANTER 60, com a frase
dizendo "a série 3 foi a 55 kg". E **frase == campo**: com `Progressao` o
campo abre com `valor` em toda série (antes a terceira abria com 55 — a
mesma série da última vez — enquanto a frase falava de 60). `services.
proxima_carga` é o alias que continua servindo os testes de b14efff.

**A FAIXA DE REPETIÇÕES É ALVO, NÃO TETO — e quem tem 65 anos ou mais nunca
lê "falha" (T2.2, 17/09/2026).** `instrucao_de_esforco(item, serie,
experiencia, cauteloso=False)` diz, na ÚLTIMA série de composto com
`rep_max` até 12 (`REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO`), "1 a 2 sobrando,
mesmo passando de 10": quem chega em 10 com 1 a 2 na reserva faz 11 — o RIR
governa, o número orienta (Helms 2016). Com faixa longa (15, 20) o aviso não
entra: seria ruído. `cauteloso` é `perfil.age >= IDADE_CAUTELOSA` (65,
Fragala 2019/NSCA), lido em `services` no mesmo ponto que a experiência,
do perfil já carregado — zero consulta a mais —, e tira a falha até do
isolador ("Última série: 1 na reserva, técnica limpa."). Toda frase cabe
numa linha a 320px, e a régua foi MEDIDA, não só contada: "Pare com 1–2
sobrando, mesmo passando de 10." tem 44 caracteres — o teto do teste — e
quebrava em duas linhas a 320 e 360; a de 37 cabe. A tela não mudou:
`agora.html` já lia `atual.esforco`.

**A REFERÊNCIA DO MOVIMENTO (20/09/2026).** As duas opções de uma letra
não repetem exercício (medido no banco da semana simulada da auditoria:
zero em comum entre a segunda e a quinta da mesma letra A), então um
exercício só volta de duas em duas semanas — e "última carga", SUBIR e
recorde ficam mudos por 14 dias. Quando o exercício em foco não tem
histórico próprio, a execução diz o que a pessoa fez no mesmo `padrao`:
"Primeira vez neste. Na última pressão de peito (supino reto com barra,
21/09): 20 kg × 10" (`services.ultima_vez_do_movimento` — a mais recente,
no mesmo dia a mais pesada; UMA consulta, só nesse caso). É DICA, não
número no campo: barra e máquina não pesam igual, e a adaptação continua
sendo por exercício. `workouts/test_referencia_do_movimento.py` prende os
três casos e o custo.

**RETOMAR E ESTAGNADO FALAM; NUNCA BAIXAM NÚMERO (T2.3, 17/09/2026).** Dois
estados a mais em `workouts/adaptacao.py`, na mesma leitura pura, com
precedência fixa — hoje manda > sem anilha > sem referência completa nas 4
datas > RETOMAR > SUBIR > ESTAGNADO > MANTER:

- **RETOMAR**: 21 dias ou mais sem NENHUMA série do exercício
  (`DIAS_PARA_RETOMAR`; o intervalo conta do último registro, de qualquer
  série — parcial há 5 dias com a completa há 20 não é pausa). Mesma carga
  (`valor` = a maior da referência, nunca × 0,9), SUBIR suspenso mesmo com
  a faixa fechada, reps no piso (`REPS_NO_PISO = {SUBIR, RETOMAR}`; a
  `_sugestao_de_reps` lê esse conjunto, não `MUDA_CARGA`), e a frase pede
  para confirmar; de 28 em diante acrescenta "comece mais leve se
  precisar". 21 e não 15: Hwang 2017 dá duas semanas sem perda e Bosquet
  2013 diz "significativo a partir da terceira semana"; frear antes disso
  era freio sem evidência.
- **ESTAGNADO**: três sessões completas seguidas (≤ 27 dias entre elas) na
  mesma carga máxima, nenhuma fechou a faixa, e o total de repetições da
  última não passou o da primeira por mais de 1 (Mitter 2022: uma rep é
  ruído). "Manter e dizer": o campo abre com a mesma carga, a tela mostra o
  verbo **manter** (`Progressao.rotulo`; "estagnado" não é verbo e não
  aparece) e a frase diz "três treinos em 60 kg sem ganhar repetição".
  `ESTAGNADO_PERSISTENTE` é a trava escrita ANTES de existir RESET: o mesmo
  platô depois de um recomeço (sessão mais leve seguida da volta à mesma
  carga em ≤ 56 dias) é só frase, nunca outro RESET em cadeia.

Os quatro negativos que congelam o veto ("a adaptação é leitura") têm
teste em `workouts/test_retomar_estagnado.py`: a ficha da semana 8 é igual
à da semana 1 com sete semanas de registro no meio; a série de ontem não
muda a prescrição de hoje; treinar em dia não declarado não altera dias,
teto nem divisão; o módulo não escreve em `SessionExercise` (controle
textual, e o retrato das linhas antes e depois das telas). Medido sobre o
ano sintético de `seed_stress` (1.254 aberturas, 50 exercícios): manter
71,9 %, retomar 21,7 %, sem sugestão 4,0 %, subir 1,8 %, estagnado 0,7 % —
o retomar alto é do GERADOR, que sorteia 6 de 50 exercícios por dia e
deixa intervalos de 3+ semanas em 22 % das aberturas; o gatilho de
recalibrar era "estagnado > 30 %" e está longe. Os dias (21, 28, 27, 56) e
o "+1" são calibração [HIPOTÉTICA] do brief de 13/09, e é o
`medir_progressao` (T2.4) que vai revê-los com dado de produção.

**O INSTRUMENTO (T2.4, 17/09/2026): medir e limpar sem mudar o que a
pessoa vê.** Quatro peças, e a natureza comum é essa:

- `manage.py medir_progressao [--dias 365]` é SÓ LEITURA — duas consultas
  fixas (as linhas de prescrição ativas e os registros da janela), nunca
  uma por pessoa — e conta, por abertura de exercício, o estado que a
  adaptação daria, a distribuição de `reps − rep_max` na última série do
  dia, a fração que PAROU EXATAMENTE em `rep_max` (a faixa lida como teto),
  os "retomar" sem pausa (a pessoa treinou outros exercícios no intervalo)
  e o intervalo em semanas. `workouts/test_instrumento.py` cobra que
  nenhuma consulta começa por UPDATE/INSERT/DELETE e que o custo não
  cresce por exercício;
- `RecordLoadView` (a rota da ficha, fora da fila) avalia conquista só na
  PRIMEIRA série do dia ou no RECORDE — a guarda que `ConcluirSerieView`
  já tinha. A rota antiga pagava o catálogo inteiro em toda carga anotada;
  abaixo do recorde, no meio do treino, nenhuma regra muda de resposta;
- o Progresso CONVIDA quem se declarou iniciante (ou não respondeu) a
  atualizar o nível depois de 180 dias e 24 datas com série
  (`progresso.convidar_a_atualizar_experiencia`): o app não infere nível —
  "uso não é intenção declarada" — mas depois de meio ano a pergunta cabe,
  porque o teto por grupo do iniciante é o menor (TREINO.md, B). UMA
  consulta para qualquer nível — o nível entra no `WHERE` pela junção com
  o perfil, porque `user.profile` não está em cache nessa tela e lê-lo à
  parte custava a segunda (medido: 28 contra o teto de 26; o teto foi para
  27 com a razão escrita);
- `manage.py podar_operacoes` roda no build, por último, e apaga
  `SyncedOperation` com mais de `VALIDADE_DIAS` (30). O método `podar`
  existia desde a fila offline e ninguém o chamava. Trinta é MAIOR que os
  7 dias que a fila reenvia — a poda nunca alcança um `op_id` que um
  reenvio ainda traria, senão a água somaria duas vezes; há teste.

E a medição L08, feita no navegador com rede lenta emulada (`nav.py rede
3g`: 400 ms de latência, 400 kbps): "Concluir série" é um POST→302→GET
de 31 KB que custa 180–330 ms de `load` no Wi-Fi e ~550 ms no 3G lento
(redirect ~460 ms) — e o iframe do vídeo que a pessoa abriu MORRE com a
recarga (1 → 0): a cada série, tocar "ver vídeo" de novo. É o insumo da
fatia E "fetch sem recarga", que continua fora até alguém decidir com
esse número.

**Duração tem UMA conta, e ela é `workouts.models.segundos_da_sessao`.**
Existiam duas cópias, uma sobre linhas gravadas e outra sobre tuplas, com um
teste prendendo as duas; prender duas cópias é pior que ter uma.
`DurationMixin.estimated_minutes` e `services._segundos_da_sessao` chamam esta.
A conta é série a série porque o descanso domina, e inclui o que a versão
anterior ignorava: aquecimento geral (300 s), aproximação nos compostos (130 s),
e a troca entre exercícios como o MAIOR entre o descanso e a caminhada — quem
descansa 80 s não troca de aparelho em 45. Nada é contado depois do último
exercício: ali a pessoa vai embora. Medido: 31 séries saíram de 52 para 66
minutos, e os 66 são os verdadeiros.

**Exercício aposentado NUNCA é apagado.** `ExerciseLog.exercise` é `CASCADE`:
`delete()` no `Exercise` levaria junto todo o histórico de carga de quem já o
treinou. Aposentar é `is_active=False` mais a troca nas linhas de prescrição, e
`prescrever_semana` filtra por `is_active` como guarda estrutural. A substituição
é por IDENTIDADE — nome validado, nunca posição na lista.
`Remada curvada com barra` saiu em 09/09/2026 e `Remada baixa na polia` herdou a
dose onde ela já existia.

E o **seed também precisa saber**: `seed_workouts` roda a cada deploy e
ressuscitava o aposentado toda vez, porque `exercises.json` continuava dizendo
que ele valia. A aposentadoria mora nos dois lugares — na migration e no
`"active": false` do catálogo — e há teste rodando o seed DEPOIS da migration.

**"Treino iniciado" é evidência comportamental, não data.** A migration precisa
saber se pode trocar o exercício de um plano, e `TrainingPlan.created_at` não
responde isso: plano criado não é treino começado. A prova é `ExerciseLog` DA
SESSÃO — alguém anotou carga em algum exercício daquele dia depois que o plano
nasceu. Data atual, horário previsto, abertura da página e presença do exercício
no plano não provam nada sozinhos.

**O cartão completo saiu da ficha — e a razão pela qual ele ficou uma vez
continua valendo.** Em 09/09/2026 alguém trocou os outros dias pela linha
compacta de hoje mirando o TAMANHO da página, e aquilo apagou registro de
série, carga, repetições, descanso, progressão e histórico. Vinte e um testes
reprovaram e estavam certos: nada daquilo tinha para onde ir.

Em 10/09/2026 tem. A execução ganhou tela própria com todos os seis recursos, e
aí a ficha pôde virar lista. A diferença entre as duas mudanças não é de
opinião: uma removia o detalhe, a outra o MUDA DE ENDEREÇO, e é por isso que a
segunda passou. Quem for encolher tela neste app, a pergunta é essa —
"para onde vai o que estou tirando?".

**A lista de compras pede o que se COMPRA.** O cardápio calcula em grama de
alimento pronto, e ninguém compra arroz cozido nem meio ovo.
`plans/compra.py` tem cinco tabelas chaveadas por `Food.name` — `FATOR_CRU`
(cozido→cru), `POR_UNIDADE` (ovo, banana, pão) e `EMBALAGEM` (lata, pacote,
litro), como antes, mais `MINIMO_DE_COMPRA` (o piso que o mercado vende —
a garrafa de azeite não vem em 20 ml — arredondado sempre para CIMA) e
`FATOR_DE_ENCOLHIMENTO` (o mesmo cozido→cru de `FATOR_CRU`, só que na
direção oposta, para carne/frango/peixe/verdura refogada, que PERDE água em
vez de inchar). Toda conversão sai marcada com `~`, porque ela É
aproximada. Dúzia só quando divide exato. E `to_integral_value()` devolve
`Decimal`, que imprime `5.0E+2 g de macarrão`: a humanização passa por
`int()`.

**A marcação da lista é ESTADO ABSOLUTO, e a chave é o alimento.** O pedido diz
`marcado=1` ou `marcado=0`, nunca "alterne" — assim ele é idempotente por
construção e dispensa `op_id`, e um reenvio da fila não desfaz o que a pessoa
fez. A chave é `(pessoa, alimento, opção, semana)`: a lista é recalculada a cada
visita e não tem identidade estável; o alimento tem. Marcação de alimento que
saiu do cardápio fica órfã e sem efeito, que é como a troca de plano se invalida
sozinha sem migration destrutiva.

**O JavaScript da página mora em `pwa.js`.** `static/js/app.js` NÃO é servido —
`app_js_url` aponta para `pwa.js`. Código posto lá passa em teste de endpoint e
não roda no navegador; foi assim que a marcação da lista "funcionou" sem salvar
nada. E o ouvinte de mudança é delegado no `document`: pendurá-lo no
`[data-lista-compras]` não pega as caixas, que não são filhas dele.

**A HOME LÊ CADA TABELA UMA VEZ: 44 → 17 consultas (decisão do dono,
21/09/2026; pediu < 15, e 17 é o piso medido com esta arquitetura).** Cada
subsistema abria a sua consulta sobre o que o vizinho já tinha carregado —
o perfil quatro vezes, o plano de treino duas, as sessões duas, o cardápio
duas, os registros de refeição quatro. Agora o que a tela precisa de cada
tabela é lido UMA vez e passado adiante, por parâmetro opcional que
preserva o caminho antigo para quem chama de fora: `services.plano_do_dia`
(plano + cardápio em 4 consultas — os horários trazem o plano por JOIN,
opção→modelo e item→alimento por `select_related`, e `plan_is_current(slots=)`
confere em memória), `tracking.day_summary(logs=, slots=, corridas_m=)`,
`streaks.calcular(ja_lido=)` com `JaLido` (dias previstos, corridas, água
por dia, tem plano) e o denominador por SUBCONSULTA
(`tracking.previstas_do_plano`, a mesma conta de `previstas_por_plano`),
`workouts.services.rotina_ativa_com_linhas` (plano + sessões + itens +
trocas numa consulta, com o cache de `exercises` montado à mão — o mesmo
que o `prefetch_related` deixaria), `views.agua_e_desfazer` (a água dos 400
dias e o `Exists` do gole de hoje na mesma consulta; `HydrationLog` é uma
linha por dia), `weight_trend.convidar_a_pesar(pesagens=)` e o `<datalist>`
de alimentos em cache de 15 min por processo. `OnboardingRequiredMixin`
lê o perfil PELO DESCRITOR (`request.user.profile`), o que o deixa em
cache para a tela inteira — e isso tem uma consequência que a suíte
achou na hora: **quem GRAVA o perfil por outra instância
(`Profile.objects.filter(...).first()`) e depois chama o motor lê o cache
velho**; a escolha da duração remontava a ficha para "padrão". A regra:
tela sob o mixin usa `self.perfil_do_dispatch`/`request.user.profile` para
gravar, ou apaga o cache antes de o motor ler (o padrão que a etapa 2 do
onboarding já usava). `plans/test_orcamento_da_home.py` mede a Home no
pior estado com o nome de cada consulta e prova, para cada leitura
compartilhada, que as duas formas dão o mesmo número; `plans/test_stress`
baixou o teto de `plans:today` de 44 para 17. Descer de 17 é decisão de
produto — guardar a ofensiva calculada em vez de reler 400 dias (2
consultas), ou tirar dado da tela —, não de código.

**`achievements.resumo` não chama `avaliar` — ele desbloqueia SÓ a regra que
chegou a 100 %.** O Progresso mostra um resumo das conquistas, e avaliar as
regras ali levou a tela de 15 para 50 consultas, com crescimento por
histórico — 36 contra 54 medidas. `ConquistasView` já documentava a mesma
decisão. O teto do orçamento subiu de 15 para 26 COM a medição escrita, e a
guarda de N+1 continua estrita: teto só se mexe depois de provar que o custo
é constante. A consequência que essa decisão tinha apareceu em produção em
16/09/2026 (avaliação, B35): "Desbloqueadas 0" com a barra "Primeiro treino
1/1" cheia na mesma caixa. Hoje `resumo` grava a regra a 100 % com os dados
que já reuniu (`_gravar`, duas consultas, uma vez) e anuncia na mesma tela;
a visita seguinte custa o mesmo que a de quem não tem nada a 100 %.

**A conquista é avaliada na PRIMEIRA SÉRIE DO DIA e no recorde, e anunciada
onde nasce.** Até 16/09/2026 o POST da série só avaliava quando
`supera_recorde` dizia sim — e estreia não é recorde, então "Primeiro
treino" nunca nascia na hora (B5): dez das onze regras dependem de um dia
de treino passar a existir, e ele passa a existir na primeira série. A
segunda em diante paga UMA consulta ("é a primeira?") e nada mais
(`workouts/test_recorde_na_hora`, 20); reenvio da fila (`criada=False`) não
avalia. E `ConquistasView` anuncia o que desbloqueia — antes a medalha
aparecia na lista sem "Conquista desbloqueada" ter sido vista uma vez.

**A SENHA É ARGON2, e o PBKDF2 fica de reserva (20/09/2026).** A auditoria
mediu em produção: login certo 3,0–3,2 s de TTFB, senha errada 4,4–5,6 s
(dois backends, dois hashes), cadastro 3,7 s — o PBKDF2-SHA256 de 1 000 000
iterações, padrão do Django 5.2, custa 0,6 s nesta máquina e ≈ 3 s na CPU
do Render free. `config/hashers.py`: `argon2-cffi` em `requirements.txt` e o
Argon2 do Django na frente de `PASSWORD_HASHERS` quando `import argon2`
funciona (extensão nativa — a suíte não depende dele: sem ele, cai no
`PBKDF2SHA256Rapido`, 600 000 iterações, o piso da OWASP). Toda senha
gravada continua conferindo (mesmo `algorithm` do PBKDF2) e é regravada no
hasher preferido no próximo login — sem migration, sem pedir nada.
`manage.py medir_hash` mede cada hasher nesta máquina; `config/test_hashers.py`
prende a ordem, a conferência da senha antiga e a regravação.

**E OS PARÂMETROS DO ARGON2 SÃO DO RENDER FREE, não os do Django
(21/09/2026).** Provado em produção com os padrões (m=100 MiB, t=2, p=8):
login certo 2,0–2,6 s — ~1,7 s só de hash, contra 0,30 s de um GET da mesma
tela; o ganho de 0,8 s medido nesta máquina não se repetiu lá, porque o
CPU do free não tem os 8 fios do p=8 nem banda para 100 MiB por login.
`config.hashers.Argon2Moderado` é m=32 MiB, t=2, p=1 (decisão do dono;
a OWASP aceita a partir de m=19 MiB, t=2, p=1 — 32 é folga, não mínimo),
e é o primeiro da lista. Mesmo `algorithm` do hasher do Django: todo
`argon2$…` gravado com os padrões continua conferindo (os parâmetros
viajam no hash) e é regravado no login seguinte, porque `must_update`
compara parâmetros. Nesta máquina: 0,057 s contra 0,22 s do padrão.

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

**A LINHA É JSON, O ACESSO TEM ROTA E DURAÇÃO, E 5xx DEMAIS VIRA E-MAIL
(21/09/2026).** Fora de DEBUG cada linha de log é um objeto (`FormatoJSON`:
`t`, `nivel`, `logger`, `pedido`, `msg`, e `rota`/`metodo`/`status`/`ms`/
`usuario` quando é acesso, `exc` redigido quando há traceback) — é o que se
filtra e se conta no log do Render sem regex; `NUTRIPLAN_LOG_JSON` força num
sentido ou no outro. `nutriplan.acesso` registra UMA linha por pedido com a
ROTA (`resolver_match.route`, o padrão da URL — não o caminho, que pode
levar token), a duração e o **usuário anônimo**: `blake2b` do id com a
`SECRET_KEY` como chave, 12 hex — segue-se o que uma pessoa fez sem que o
log diga quem é, e sem a chave o hash não volta. O hash só é calculado
quando a view já resolveu `request.user`: `/saude/vivo/` continua a ZERO
consultas (teste). Estático não entra; na suíte o logger fica em WARNING
(`NUTRIPLAN_LOG_ACESSO`, desligado quando `sys.argv` diz `test`) — seriam
milhares de `GET … -> 200` no stderr de cada fatia. E `AlertaDe5xx` é um
handler no `django.request`: conta os 5xx numa janela de 5 min e, passado
`NUTRIPLAN_ALERTA_5XX` (3, **por processo** — dois workers, dois
contadores), manda UM e-mail para `NUTRIPLAN_ALERTA_EMAIL` (o e-mail
administrativo, copiado do `VAPID_ADMIN_EMAIL` nos dois serviços) com rota,
identificador e contagem, e cala por 30 min — um deploy quebrado é um
e-mail, não cem. O envio roda numa thread; sem destinatário, só uma linha
WARNING. `config/test_logs_json.py` prende as três coisas, inclusive que um
500 de verdade chega ao handler CONFIGURADO. O UptimeRobot continua sendo o
alerta de "caiu"; este é o de "está de pé e errando".

**i18n PREPARADA, SEM TRADUZIR (21/09/2026).** O app é pt-BR e continua
sendo — `LANGUAGE_CODE = "pt-br"`, `LANGUAGES` só com ele, sem
`LocaleMiddleware` (nenhuma tela negocia língua por cabeçalho). O que
mudou: `LOCALE_PATHS` aponta para `locale/`, o catálogo
`locale/pt_BR/LC_MESSAGES/django.po` existe com `msgstr ""` em toda frase (o
Django mostra o msgid, que já é o texto certo; não rode `compilemessages`),
e **template NOVO carrega `{% load i18n %}` e marca texto visível com
`{% translate %}`** — a régua é `TEMPLATES_NOVOS` em `config/test_i18n.py`,
que cresce com cada template criado a partir de hoje e cobra a frase no
catálogo — **com uma exceção, o painel de gestão** (`templates/analytics/`),
escrita no próprio arquivo em 24/09/2026 depois de ter existido calada
desde o primeiro dia: aquelas telas são a ferramenta de quem OPERA o
produto, e a segunda língua é para quem USA o app. Marcar mil frases antigas de uma vez não é o objetivo; marcar as
novas custa nada agora e evita a varredura no dia da segunda língua. A
primeira frase marcada é a faixa do staging em `base.html`.
**O BUSCADOR VÊ SETE ROTAS, E O RESTO É `noindex` POR PADRÃO (21/09/2026).**
`config/seo.py` fecha a lista (`ROTAS_PUBLICAS`: landing, capa e "sobre" do
demo, privacidade, termos, criar conta, entrar) e é dela que `/sitemap.xml`
sai; `/robots.txt` diz o que não rastrear (gestão, sondas, tarefas, offline)
e NÃO lista o admin — a rota vai deixar de ser óbvia, e um `Disallow` a
anunciaria. A meta description saiu solta do `base.html` e virou o bloco
`seo`, que inclui `partials/seo.html` UMA vez no `<head>`: sem argumento a
página é instância (tela do app, tela interna do demo, shell offline) e leva
`noindex`; a rota pública declara `publica=True`, `titulo` (igual ao bloco
`title` — há teste) e `descricao` própria (≤ 160), e ganha `canonical` e
Open Graph a partir do pedido (`scheme` + host + path, nunca domínio escrito
à mão). Rota pública nova entra na lista E declara o bloco; esquecer é
ficar fora do índice, nunca o contrário. Antes disto (medido em produção
em 21/09): a mesma description em toda página, zero `canonical`/OG, e
`/demo/treino/` indexável com a ficha do Carlos como se fosse o produto.
Desde a ajuda (21/09, tarde) são NOVE: `/ajuda/` e `/ajuda/o-que-mudou/`
entraram na lista com bloco `seo` próprio — a FAQ é o texto que diz o que
o produto faz, e é por onde alguém o ACHA; `/ajuda/reportar/` e a
confirmação continuam `noindex` (formulário não é conteúdo).

## As três perguntas de produto do analytics (24/09/2026)

O app já tinha evento bruto com taxonomia fechada, alias no login e poda de
90 dias (`docs/analytics.md`). O painel tinha as FERRAMENTAS — explorar um
evento, montar um funil qualquer, ver a coorte semanal — e faltavam as
PERGUNTAS. Três telas novas sob `/gestao/analytics/`, na mesma régua de
sempre (abaixo de 15 consultas, custo que não cresce com o volume):

- **`entrada/` — onde a pessoa desiste.** `consultas.funil_de_entrada` sobre
  `PASSOS_DE_ENTRADA` (landing → cadastro → etapas 1, 2 e 3 → 1ª refeição →
  1ª série), por coorte de dia ou de semana, com a taxa DO PASSO ANTERIOR em
  destaque — a do topo só diz que o funil é um funil. **A coorte é do
  PRIMEIRO passo da pessoa**, e não do dia do evento: quem abriu a landing na
  segunda e treinou na quarta pertence à segunda, senão a taxa de um dia
  depende do movimento do anterior. Quem entrou direto pelo cadastro não some
  do funil — entra pelo passo em que apareceu, com os de cima zerados. UMA
  consulta por passo, sete, fixas.
- **`retencao/` — a pessoa volta?** `retencao_por_coorte` põe **D1/D7/D30**
  acima da matriz semanal que já existia. "Voltou" é ter REGISTRADO alguma
  coisa (`EVENTOS_DE_REGISTRO`), não ter aberto o app; janela que ainda não
  fechou vem VAZIA e não zero — zero afirmaria que ninguém voltou de um prazo
  que não chegou.
- **`uso/` — o que a base usa de fato.** `uso_por_area`: registros **e**
  pessoas por pilar, semana a semana. Os dois juntos de propósito: 400
  registros podem ser quarenta pessoas ou uma obsessiva. Área zerada aparece
  na tabela — sumir faria ninguém reparar que a corrida não é usada.

`EVENTOS_DA_AREA` é a fonte única do que conta como uso, e
`EVENTOS_DE_REGISTRO` é ela achatada: a retenção tira dali o "voltou", e duas
definições de "usou o app" é como duas telas passam a discordar (há teste).

**Três eventos entraram.** `site.landing_vista` nasceu (disparado pela
`LandingView`, no SERVIDOR: um degrau de funil preso ao texto de uma rota
quebra em silêncio no dia em que a rota muda de nome); `treino.serie_concluida`
e `treino.concluido` estavam na taxonomia **desde o começo e nunca eram
disparados** — o funil não tinha fim e o uso por área enxergava tudo menos o
treino. A série só conta quando a linha NASCE (`criada=True`): o reenvio da
fila offline é a mesma série chegando de novo, e contá-la inflaria o número
que decide investimento.

E duas classes que existiam no template da Retenção **sem regra nenhuma no
CSS** ganharam a seção 54 (`.tabela-rolagem`, `.coorte`): a tabela só não
vazava a 390 px porque as colunas cabiam, e as telas novas, com cabeçalho de
palavra de verdade, mediram 621 px numa janela de 390. A rolagem é do BLOCO
(com `tabindex` e `role="region"`), nunca da página. O dead-class ruler não
pega isso: ele mede classes com `__`, as de ELEMENTO.

## Ajuda (21/09/2026)

**`/ajuda/` são três telas PÚBLICAS, e a FAQ só afirma o que o app faz.**
Quem não consegue entrar é quem mais precisa de ajuda, então nada ali
exige sessão (`ajuda/views.py`; a barra de baixo já não aparece para
anônimo pelo `base.html`). A FAQ (`templates/ajuda/index.html`) é
`<details class="fora">` — a sanfona da Home, com a animação do `pwa.js` —
em quatro blocos (plano e cardápio · treino · água, peso e progresso ·
conta, avisos e privacidade), e cada resposta aponta uma tela ou uma regra
que existe no código, com a fonte no `CLAUDE.md`. Três respostas dizem
NÃO de propósito e há teste prendendo as três (caloria gasta, Apple
Saúde/Health Connect, prescrição): "melhorar" a FAQ prometendo isso é o
defeito de veracidade que o app evita em todo lugar. A porta é tripla:
Áreas › Ferramentas, Perfil › Conta e sessão, e o rodapé das telas de
entrada (`partials/links_legais.html`, FORA do `{% if legal_publicado %}`
— a ajuda não depende do legal).

**"Reportar um problema" chega PREENCHIDO, e o que a pessoa escreve é só o
que aconteceu.** Rota (`?de=` ou o `Referer` do MESMO host — de outro host
é descartado), versão (`RENDER_GIT_COMMIT[:7]`, o mesmo que `/saude/`
publica; somente leitura) e aparelho (`User-Agent`) vão no formulário; o
e-mail da conta entra quando há sessão. O relato vira `EmailMessage` para
`NUTRIPLAN_SUPORTE_EMAIL` (vazio cai em `VAPID_ADMIN_EMAIL` — o mesmo
dono, uma variável a menos para esquecer no painel) com `Reply-To` da
pessoa. É público, então tem três guardas e a MESMA resposta para as três
(um bot não aprende qual o pegou): pote de mel (`site`, `HiddenInput`,
`tabindex=-1`), limite por IP (5/h) e global (60/h) na tabela de
`accounts.limites` (`PedidoDeRecuperacao`, tipos `ajd-ip`/`ajd-glob`,
HMAC do IP — o mesmo motivo de lá: cache é por worker e some no deploy).
Falha de SMTP responde 503 com mensagem e NÃO conta no limite. O teste do
envio usa o formulário RENDERIZADO com `enforce_csrf_checks` — um nome de
campo trocado no template derruba o teste, e não um `post` de dicionário.

**"O que mudou" lê o `CHANGELOG.md`, que é OUTRO documento.** O
`BACKLOG.md` é o caderno de engenharia e não serve para quem usa;
`CHANGELOG.md` tem uma seção por dia (`## AAAA-MM-DD`), um item por
mudança que a pessoa VÊ (`- **Título.** Uma frase.`), sem nome de arquivo
nem número de PR. `ajuda/mudancas.py` lê pouco de propósito — escapa tudo
e só conhece `**negrito**` e `` `código` ``; Markdown inteiro seria uma
dependência para três marcas — e relê quando o mtime muda. Há teste
cobrando a forma do arquivo real (datas decrescentes, uma seção por dia,
nenhuma vazia). Toda missão que muda o que a pessoa vê acrescenta a linha
dela ANTES do merge, na própria branch — e uma linha só entra quando a
mudança que ela descreve está na mesma branch ou já em `main` (a linha
do placar saiu deste PR por isso e entra no dele).

**O GLÚTEO É GRUPO PRÓPRIO DESDE 21/09/2026 (`MuscleGroup.GLUTES`), E
NENHUMA FICHA MUDOU POR ISSO.** A elevação pélvica, a elevação pélvica no
banco e as duas pontes de glúteo saíram de "posterior de coxa e glúteo"
(migration `workouts.0032`, POR NOME, reversível; o `seed_workouts` grava o
mesmo), o rótulo do posterior virou "Posterior de coxa", e todo
agachamento e toda extensão de quadril de quadríceps/posterior levam
`glutes` nos secundários — é de onde vem o estímulo além do único
exercício direto por letra. O glúteo é ANUNCIADO (`principais`) nas sete
letras que têm um exercício dele, ao lado do posterior: complementar
cederia primeiro no tempo curto, e a elevação pélvica sempre foi protegida
como posterior. O título continua "Pernas": `_nomes_dos_grupos` colapsa
quadríceps, posterior e glúteo quando os dois primeiros estão; sozinho com
o posterior ("Complementares" do ABCD) ele é nomeado.

O que custou medição — e é a decisão desta seção: **para as OPÇÕES, para
o RELÓGIO e para o PRINCIPAL da sessão, posterior e glúteo são UMA
família** (`workouts.models.FAMILIA_DE_OPCOES`, `familia_de_opcoes`). Stiff
e elevação pélvica são o mesmo padrão composto (extensão de quadril), e o
rodízio sempre deu um a cada versão da letra. Com os dois grupos separados
em toda parte, cada um virava o único composto do próprio grupo, era
compartilhado, e as duas opções carregavam os dois: a letra C do `abc2` em
Padrão não fechava em 60 minutos e caía para UMA opção de 6 exercícios e
20 séries (era 9/25 e 9/27); só no relógio, o "Inferior" de dois dias em
Rápido perdia a segunda opção (três principais de três séries são os 30
minutos inteiros); e sem a família na substituição por equipamento, "só o
peso do corpo" perdia dois dos três stiffs do "Inferior" (o catálogo tem
UM stiff sem carga) — a família só responde ali quando o grupo esgotou: o
stiff troca por stiff e a elevação pélvica por elevação pélvica enquanto
houver. A família NÃO vale para o teto de aparo, para os órfãos, para
"outras formas", para o volume da semana nem para a tabela do `TREINO.md`
— aí o grupo é o de verdade, e é para isso que ele existe.

Medido em 540 perfis (nível × dias × preferência × faixa × equipamento,
`scripts/qa/retrato_das_fichas.py`, antes/depois): "academia completa"
IDÊNTICA em 135 de 135; nos perfis restritos 198 de 1 269 sessões mudam
só QUAL variante de extensão de quadril substitui a de barra, com o mesmo
número de exercícios e a mesma dose; nenhuma letra perdeu opção; a tabela
de médias do `TREINO.md` ganhou a coluna glúteo (5,0 no Padrão) e nenhuma
outra se moveu. Ficha nascida antes do grupo continua com as mesmas linhas
e não é julgada desatualizada (`workouts/test_gluteo.py`) — o
`SessionExercise` aponta para o exercício pela chave, e o grupo não entra
em `_prescricao_bate`. Quem tem perfil restrito e ficha da variante
antiga vê o aviso "regenerar?" uma vez, e decide.

## Design: o que já existe, e o que não inventar de novo

**O sistema visual já existe, é enforcado por teste, e a primeira coisa a fazer
antes de criar componente é procurar o equivalente.** Auditado em 05/09/2026:
70 tokens no `:root` — oito degraus de texto, sete de espaçamento, quatro de
quina, três de sombra e seis de camada, mais as cores e as receitas. (O número
já foi escrito como 64 aqui: era a contagem de ANTES dos seis tokens de camada,
no mesmo parágrafo que os anunciava.) `config/test_design_system.py` congela a
dívida de valor cru no número atual — ela não pode crescer.

**A escala de empilhamento é vocabulário, e a ordem é regra de produto.** De
baixo para cima: `--camada-conteudo` → `--camada-barra-topo` →
`--camada-flutuante` → `--camada-navegacao` → `--camada-aviso` →
`--camada-bloqueio`. As duas barras
**não** ficam no mesmo degrau: nada pode cobrir a barra de baixo — o convite de
instalação cobriu a navegação uma vez, e `push/tests.py` guarda isso desde
então. A barra de cima pode ser coberta por um flutuante. Colapsar as duas num
degrau só inverte esse par, e foi o que a primeira versão da escala fez.

E `z-index` alto não vence contexto de empilhamento: o painel do mapa declarava
40 "acima da tabbar, que é 30" e perdia, porque é filho da barra de cima, que é
`sticky` com camada própria. Quem resolveu foi `max-height`, medido.

**Espaçamento não volta para dentro do HTML.** Havia 23 `style=` estáticos em
13 templates, com seis valores para cinco intenções — três deles fora da
escala. Cada intenção ganhou nome: `.form__nota`, `.acao-solta`,
`.chip-row--conteudo`, `.chip-row--inicio`, `.acoes-empilhadas`,
`.nota-do-botao`. Não são utilitárias genéricas (`.mt-4` e parentes): utilitária
só muda o lugar onde o número arbitrário é escrito. Duas exceções continuam
válidas e têm teste: valor calculado pelo servidor (`style="width: {{ pct }}%"`)
e template de **e-mail**, onde cliente não lê CSS externo.

**O que este app deliberadamente NÃO faz** — medido, não afirmado: zero
gradiente roxo; seis gradientes em 6.700 linhas; vidro em três cartões do topo e
no cartão de entrada, com `@supports` de contraste e a razão escrita (desfocar
cor chapada custa quadros para produzir a mesma cor chapada); 89% das sombras
usando token.

**O movimento tem UMA linguagem, e ela mora nos tokens `--mov-*` (15/09/2026).**
Toque `.1s`, estado `.18s`, expansão `.25s`, tela `.2s`, modal `.28s`,
sucesso `.5s`, passo 6 px, passo longo 12 px, degrau de lista 35 ms — e
`config/test_movimento.py` conta as durações escritas à mão em
`transition`/`animation` (o teto é ZERO; `.01ms` da saída de movimento
reduzido é a única exceção). Antes dos tokens o app tinha `.12s`, `.15s`,
`.16s`, `.22s`, `.32s`, `.5s`, `.7s` e `.9s` espalhados: uma segunda
linguagem nasce de um valor solto. Quatro decisões medidas:

- **`<details>` anima por JavaScript, abrindo E fechando** (`pwa.js`,
  "MOVIMENTO"): o navegador troca `open` de uma vez, e a refeição saltava de
  44 para 422 px. O animador mede as duas alturas, anima com `overflow:
  clip` e limpa os estilos ao terminar; `grid-template-rows: 0fr → 1fr` só
  animava a abertura e saiu da `.fora__corpo` porque a medida era tirada no
  meio da transição. Quem pedir `data-sem-animacao` fica nativo, e com
  `prefers-reduced-motion` TUDO fica nativo — o JS consulta `matchMedia`.
- **`view-transition-name` é ÚNICO por documento, e o teste lê os nomes do
  CSS.** Duplicado, o navegador PULA a transição inteira sem erro. O cartão
  AGORA da Home **não** leva nome de propósito: ele muda de slot ao ser
  marcado, e um nome faria o cartão A morfar no B. O número da série leva
  `display: inline-block`, porque elemento sem caixa derruba a transição
  da execução inteira.
- **Uma escala de toque, `.96`, e uma lista só** (seção 8 do CSS, três
  listas que `config/tests.py` confere serem a mesma). O brief pedia
  .97–.99; uma segunda escala no mesmo gesto é o que aquele teste existe
  para impedir. `.sessao-cartao` entrou na lista — e perdeu a `transition`
  própria, que sobrescrevia a da lista e afundava sem transição.
- **A memória de um toque entre páginas é `sessionStorage`, lida UMA vez.**
  O app é multi-página: o número da água conta do valor de ANTES do POST ao
  de agora, o cartão marcado celebra na página seguinte, o onboarding entra
  da direita ao avançar e da esquerda ao voltar. Nada disso afirma sucesso
  antes do servidor — a página nova É a confirmação. Enfileirado sem rede,
  a memória é apagada: um almoço marcado no metrô não pode "celebrar"
  horas depois.

**A RÉGUA SISTEMÁTICA DO MOVIMENTO REDUZIDO (21/09/2026).**
`config/test_movimento.py` prende os três caminhos que animam por JS e o
bloco universal; `config/test_movimento_reduzido.py` é a régua que
continua valendo na PRÓXIMA animação: todo seletor com `animation-delay`
fora dos blocos reduzidos tem o atraso zerado (ou `animation: none`) num
bloco reduzido — `.01ms` de duração não zera o atraso, e um cartão com
`fill: both` fica invisível esperando (achado da régua: os números do
placar, `.recompensa .fim__numeros > li`, esperavam a nervura que não ia
riscar); toda chamada a `.animate(`, `requestAnimationFrame(` ou rolagem
`smooth`, em `static/js/*.js` e nos `<script>` dos templates, tem
`reduzido()`/`prefers-reduced-motion` nas 45 linhas acima (as duas
sanfonas ganharam o gate dentro da própria função — antes só o toque era
filtrado); nenhum `<animate>` SMIL e nenhum `autoplay` escrito no HTML (o
vídeo do exercício nasce no toque). E o E2E noturno emula
`prefers-reduced-motion` e exige `getAnimations()` sem nada acima de 50 ms.

**Antes de criar componente novo, procure.** `templates/partials/` tem oito
parciais; `card`, `btn`, `chip`, `pill`, `tile`, `data-list`, `empty-state` e
`hint` já existem e têm regra própria. Uma quarta versão do mesmo botão é o
defeito que esta seção existe para impedir.

`drawer` esteve nesta lista e saiu em 10/09/2026 com o redesenho do Treino: era
o `<dialog>` de vídeo do exercício, e a execução virou tela em vez de gaveta.
Não há mais sobreposição modal no app fora do `.modal`.

**Sobreposição: `<details>` antes de `<dialog>`, e TELA antes das duas.**
O mapa de áreas é `<details>` porque um menu de cinco links não precisa de foco
preso. O vídeo do exercício foi `<dialog>` por precisar — e deixou de precisar
quando a execução virou tela própria: navegar resolve foco, histórico e botão
voltar sem código nenhum, e uma gaveta que some ao trocar de exercício era
trabalho para reimplementar o que o navegador já faz.

`<dialog>` traz `inert` e foco preso de graça, e traz o custo que o convite de
instalação pagou, com 68 controles alcançáveis por trás quando o papel estava
errado.

**Estado vazio é convite, e os deste app já foram auditados.** Dos 16, quatro
parecem só constatar — e os quatro têm o motivo escrito no template: dois têm a
saída ao lado (botão ou campo na mesma tela) e dois são ramos defensivos que
ninguém alcança. Acrescentar texto ali seria ruído.

## Design / Onda 3

Seção da campanha Mesa & Ferro (branch `design/mesa-e-ferro`, 15–16/09/2026).
Tudo aqui foi MEDIDO no `app.css` real; onde uma frase de outra seção deste
arquivo ficou velha, a verdade nova está aqui e a velha não foi editada — as
duas sessões da campanha só escrevem nesta seção para não brigar no merge.

**Ferro é escrito UMA vez, e dois gatilhos o ligam.** A paleta escura mora em
36 tokens `--ferro-*` no `:root`; `@media (prefers-color-scheme: dark)` e
`body.modo-foco` (classe que o servidor escreve na execução do treino) só
fazem `--x: var(--ferro-x)`. Antes, a mesma cor estava escrita em dois blocos
e divergia sem ninguém ver. `config/test_ferro.py` guarda a estrutura — todo
`--ferro-x` tem um `--x` de Mesa, os dois gatilhos mapeiam o mesmo conjunto
e nada além de `var(--ferro-…)` entra neles — e `config/tests.py` resolve o
`var()` antes de medir contraste. Os pilares têm cor nomeada: `--agua`,
`--brasa`, `--terra`, `--chama`, `--folha`; `--accent`/`--warm`/`--border`
saíram de vez.

**Foco é `--brand` em todo controle, e o `--glow` virou anel de 1 px.** Cinco
controles pintavam o foco com `--agua` — a cor do pilar Hidratação num
formulário de perfil —, e o campo em foco tinha um brilho difuso de 26 px. O
anel de 1 px somado à borda que já vira `--brand` dá os 2 px do DESIGN.md. O
NOME `--glow` ficou porque `workouts/tests.py` lê `var(--glow)` no foco do
campo e proíbe token órfão; a receita é que mudou. `config/tests.py` conta o
anel de marca por DEFINIÇÃO de token ({`--halo`, `--glow`, `--ferro-glow`}) e
exige zero fora delas. E o campo inválido FALA: `.field-input[aria-invalid]`
pinta a borda de `--danger`, e `partials/field.html` escreve os ids
`{{ auto_id }}_error` / `_helptext` que o `aria-describedby` do Django 5.2 já
apontava sem alvo. `config/test_foco.py`.

**O sprite entra em toda página, uma vez, pela base — e não no shell
offline.** A frase "só é incluído no onboarding" do bullet **não tem
ícone** das "Três ausências no mapa" (seção "Decisões") era verdade até
16/09/2026 — e a decisão dali continua de pé por outro motivo: `/areas/`
segue sem `<use>` porque o mapa é lista de nomes, não de desenhos. Hoje `base.html` inclui `partials/icones.html`
dentro do mesmo `{% if not shell_offline %}` do `data-usuario`; onboarding e
vitrine deixaram de incluir por conta própria. Medido: ficha +2 939 bytes
(sprite 2 946 B brutos, 849 B gzip, 13 símbolos) — abaixo do teto de +4 KB do
plano mestre; `/offline/` zero símbolos. E o `stroke-width="2"` está em CADA
`<symbol>`, não na raiz: o clone do `<use>` herda do consumidor, e com o
atributo só na raiz o cartão de escolha desenhava traço 1 (1 397 px de tinta
contra 2 789). `config/test_sprite.py` lê os 13 símbolos e fecha a lista de
traços do consumidor em {2, 2.8 (o visto do cartão marcado)}.

**Keyframe sem consumidor é linguagem morta, e a catraca está em zero.**
`serie-ok`, `serie-anel`, `esqueleto` e `descanso-acabando` foram escritos
para a execução e nunca ganharam a classe que os dispara; `varrer` fazia o
anel de progresso varrer do zero a cada abertura — movimento que não confirma
ação nenhuma. Os cinco saíram (23 → 18 keyframes), e
`config/test_movimento.py` exige que toda `@keyframes X` tenha `animation: X`
ou `animation-name` em algum lugar. Se a onda 6 os quiser, nascem com o
consumidor no mesmo commit. `font-weight: 760` (dois números) virou 750, o
peso de todo tile — pesos distintos 12 → 11.

**Todo botão diz qual botão é, e a variante é lista fechada.** {`btn--primary`,
`btn--ghost`, `btn--quiet`, `btn--perigo`, `btn--google`, `btn-link`};
`btn--block`, `btn--sm` e `btn--hoje` são tamanho e posição, não decisão.
Eram cinco botões nus (500.html, "Minhas conquistas" no Perfil, três na
gestão); hoje zero, e `config/test_design_system.py` varre `templates/`. O
`.mapa__area:active` entrou na lista única de `:active` da seção 8 em vez de
ter escala própria. E o `<a class="btn">` que leva a outra tela avisa que
está indo: `pwa.js` marca `is-carregando` + `aria-busy` no clique (mesma
receita visual do `[aria-busy]` do `<button>`), e o `pageshow` limpa ao
voltar pelo bfcache. Fica de fora quem não troca de página: `target`,
`download`, `#`, `mailto:`, `tel:`, `sms:`, `javascript:`, clique com
modificador — e **`data-arquivo`**, a marca dos dois links que exportavam o TCX (saíram em 20/09/2026; a marca fica para o próximo link de arquivo):
a resposta é `attachment` e a página não troca, mas a view pode responder 302
com mensagem quando não há treino, e `download` faria o navegador SALVAR
aquele HTML. Sem a guarda de `#`, o CTA da Home (`acao.url = "#slot-N"`)
ficaria com o anel para sempre.

**A vitrine mora em `/gestao/vitrine/`** (mesma permissão do painel de
gestão): toda parcial e componente em todo estado, nos dois regimes
(`?regime=ferro` escreve `body.modo-foco`), coberta por um teste que lê a
pasta `templates/partials/` e exige cada arquivo lá ou nos dois `base.html`.
É onde se fotografa antes de mexer em token.

**Contraste: 274 pares medidos no CSS real, zero reprovados.** Todo texto ×
todo fundo a 4,5:1 e todo gráfico × superfície a 3:1, Mesa e Ferro
(`scripts/qa/auditar_contraste.py`, mesma régua da suíte). Quatro passam
raspando, todos gráficos em Mesa: `--folha` sobre `--surface-3` (3,03),
`--brand-soft` (3,14) e `--surface-2` (3,15); `--chama` sobre `--surface-3`
(3,29). Quem mexer em `--surface-2`/`--surface-3` roda o script antes.

**O export do Claude Design ainda não chegou, e o terreno está pronto.**
`scripts/inventariar_export.py` classifica a árvore extraída (tolerante a
pasta desconhecida; `--estrito` falha nomeando cada arquivo incerto) e
`scripts/tokens_do_export.py` compara os tokens do export com o `:root` de
Mesa (CSS custom properties e JSON W3C/plano; nomes e cores normalizados).
Os dois estão testados contra árvores sintéticas com a estrutura documentada;
o primeiro uso real é a Task 12 do plano do design system.

**O que a onda 3 NÃO fez, e por quê** (plano da noite de 16/09,
`docs/superpowers/plans/2026-09-16-onda-3-noite.md`): famílias de cartão
(T3.3 — 114 cartões e três decisões de direção abertas), variantes novas de
botão (T3.4 — `--tonal`/`--texto`/`--icone`), o renome
`.choice-list--dias → .segmented--envolve`, emoji → glifo nas conquistas (3
desenhos novos e o cartão de compartilhar desenha o emoji), a fonte própria
(T3.2 — download externo e decisão do dono). Cartão dentro de cartão foi
MEDIDO e é zero em sete rotas (`config/test_cartoes.py`, catraca em 0).

**CORTE: o Ferro é a BASE e o Papel o derivado (T3.1′, 16/09/2026).** A
direção escolhida em `docs/briefs/design/DIRECAO-ESCOLHIDA.md` (veto do dono
pendente) inverteu quem é a base: os valores moram UMA vez em `--ferro-*` e
`--papel-*` no `:root`; o próprio `:root` liga o Ferro (`--bg:
var(--ferro-bg)`), `@media (prefers-color-scheme: light)` liga o Papel e
`:root.modo-foco` liga o Ferro de volta. A classe `modo-foco` vai no
`<html>`, e NÃO no `<body>`: `--glass`, `--glow` e `--halo` são receitas
de `var(--bg)`/`var(--brand)` declaradas no `:root`, e uma custom property
resolve o `var()` onde é declarada — com a classe no `<body>` a execução em
Ferro saía com a barra de abas clara e o anel de foco oliva (visto na
captura). E a execução (`ModoTreinoView`) passou a ESCREVER a classe: o
contrato dizia isso desde a Mesa & Ferro e nenhuma view cumpria — só a
vitrine, por parâmetro (`workouts/test_foco_na_execucao.py`). `config/
tests.py` lê os dois regimes por `REGIME_FERRO`/`REGIME_PAPEL` e o leitor
`_tokens` resolve o `var()` do próprio `:root`; `config/test_tema_claro.py`
virou a trava de "o Ferro é a base". Paleta da tabela do DESIGN.md com
quatro ajustes MEDIDOS: `--ferro-surface-2` #292d25 e `--surface-3`
#33382d (a direção dava 1,11 e 1,14 sobre a superfície; a régua U28 pede
1,2), `--ferro-terra` #da9169 (a argila da direção ficava a 4,44 sobre a
própria tinta em `--surface-2`) e os cinco `--dia-*` movidos 1–12 % para
passar a 4,5 sobre a própria tinta nos fundos novos. 274 pares no CSS real,
zero reprovados; raspando só `--brasa` (4,59) e `--terra` (4,72) sobre
`--surface-3` no Ferro. `--corte`/`--corte-g`/`--corte-p` e
`--mov-recompensa` NASCEM com o consumidor, nos PRs dos componentes e da
execução (`test_no_css_variable_is_declared_and_never_used` recusou os
quatro órfãos no pre-commit); `--shadow-*`/`--edge` valem `0 0 0 0 transparent` — não `none`, que não entra em lista de
`box-shadow` e derrubaria o `--halo`. Manifesto e `theme-color` seguem a
base (`PWA_THEME_COLOR` #10120e; `PWA_LIGHT_COLOR` na meta com `media`).

**Duas fontes próprias, e a display só em herói (T3.2, 16/09/2026).**
Bodoni Moda (display; `wght` 400–900, `opsz` 6–96) e Karla (texto; `wght`
400–800), os dois `.woff2` do Google Fonts para o subconjunto latin,
auto-hospedados em `static/fonts/` com a OFL ao lado: **70 580 bytes** no
total contra o gate de 260 KB (`config/test_fontes.py`), `font-display:
swap`, pré-cacheados pelo service worker, `font/woff2` registrado no
`mimetypes` para o servidor local (o Windows não o conhece). A itálica da
Bodoni ficou de fora: o mockup a usava a 13–19 px, abaixo do piso de 20 da
display — sem consumidor, sem arquivo. Medido com fontTools, as duas têm
`tnum`; a nota de `DIRECAO-ESCOLHIDA.md` ("didone não tem numeral
tabular") valia para o mockup e foi corrigida. A display aparece em DEZ
regras e só nelas — `h1` (28 px, 600; era 40/800), `.hoje__nome`,
`.agora__titulo` e `.agora__nome` (os nomes, 22,7 px), `.ring__value`,
`.curva__valor`, `.modulo__valor`, `.balance__value`, `.tile__value`,
`.pesagem__media`, `.entrada__wordmark`, `.corrida-numero__valor` — e o
teste cobra que toda regra com `var(--font-display)` tenha tamanho de
herói. Os pesos são QUATRO (400 · 500 · 600 · 700): os oito degraus
sintéticos (550/620/650/680/720/750/780/800) foram mapeados (550 → 500,
620/650 → 600, o resto → 700), e `b, strong { font-weight: 700 }` porque
`bolder` de 600 é 900 e a Karla para em 800 — o "2100 kcal" do resumo
saía sintetizado. Catraca de `font-size` cru desceu 119 → 117 (o `h1` do
desktop perdeu o `1.9rem`).

**A quina é a folha, e nada clicável é pílula (T3.3 + T3.4, 16/09/2026).**
Três tokens de QUATRO valores substituem a escala 24/16/12/8: `--corte-g:
0 40px 0 40px` (o prato — `.card.agora-card`, o painel de hoje do treino,
a ofensiva, a água, a barra de abas), `--corte: 0 20px 0 20px` (cartão de
lista, botão, campo, mídia, modal, `.meal`, a aba ativa) e `--corte-p: 0
12px 0 12px` (chip, célula, selo de opção, filho de caixa). Ordem sup-esq
· sup-dir · inf-dir · inf-esq: ponta em cima à esquerda e embaixo à
direita, como a folha do logo. A migração foi de TOKEN, não de regra —
`var(--radius-xl)` → `var(--corte-g)` etc., 82 declarações —, e o único
lugar que precisou de decisão foi o raio "de dentro" do segmented
(`calc(var(--radius-sm) - 3px)`): `calc()` não entra num token de quatro
valores, então é `--corte-p` direto. `--pill` ficou em 14 usos, todos
barra, trilha, ponto ou selo; sete clicáveis saíram dela (`.chip`, os
links da barra de cima, "Fazer" da ficha, o avanço do wizard, o fechar do
demo, as abas da gestão, o rótulo dos dias) e `config/tests.py` prende as
duas coisas — a identidade dos quatro tokens e a lista de clicáveis que
não podem ser pílula. O cartão continua sem sombra e sem borda: a
superfície é o que separa, e é por isso que o contrato o chama de FAIXA.

**A folha de recompensa, e os três momentos que se movem (T3.5 + T3.6,
16/09/2026).** A última série do treino abre o placar DENTRO da folha-lima
(`.recompensa`: `--brand` cheio, `--on-brand`, `--corte-g`): a carga total
de hoje em Bodoni — peso × repetições, série a série, `services.Placar`,
CONTAGEM sobre o `item.load` que a tela já tinha, zero consulta nova —,
"vs. a última vez" (a mesma conta sobre a última vez de cada exercício;
some sem passado), o recorde (a série mais pesada de hoje acima de
qualquer data, a régua de `achievements`), séries e minutos; "Ver o treino
completo" primário (a ficha da sessão — o mockup dizia "Ver resumo do
treino", e um verbo por destino venceu) e "Voltar para Hoje" contorno. O
movimento: `folha-sobe` em `--mov-recompensa` (.45 s) a partir do canto
inferior direito, o número conta do ZERO em `--mov-sucesso` depois de a
folha subir (`data-conta="zero"`, `pwa.js`), os números pequenos em
cascata de `--mov-cascata` (80 ms), os botões chegam parados a .95 s; com
`prefers-reduced-motion` o quadro final aparece pronto
(`workouts/test_recompensa.py`). Os outros dois momentos: `corte-abre` na
refeição recém-marcada (`.meal.is-recem` — as duas pontas viram curva por
um instante, `--corte-aberto`) e `corte-desdobra` ao CRUZAR a meta de água
(`.agua-card.is-meta`, só no toque que cruza — `pwa.js` compara o valor de
antes com o de agora contra `data-agua-meta`). O Chrome headless desta
máquina responde `prefers-reduced-motion: reduce` por padrão — `scripts/qa/
nav.py movimento normal|reduzido` emula os dois, junto com o tema, na
mesma chamada. `.choice-list--dias` virou `.segmented--envolve` e o visto
do cartão de escolha virou folha pequena. O que a onda 3 ainda NÃO fez:
emoji → glifo nas conquistas (três desenhos e o `card.js` desenha o
emoji) e a corrida em andamento em Ferro — os dois ficam para a próxima
onda, com o consumidor.

**VETO: a direção principal é a NERVURA · ANDAIME (17/09/2026).** O dono
escolheu por gosto, sobre as capturas, e a pontuação de 16/09 (CORTE 25 ×
NERVURA 23) ficou como histórico em `DIRECAO-ESCOLHIDA.md`; o `DESIGN.md`
foi reescrito a partir do `Direcao1-a`, e do `1-b` entrou só o que pontua
em identidade e em execução/recompensa, item a item (tabela naquele
arquivo). O que mudou de VALOR, sem mexer em estrutura (PR dos tokens):
a paleta — chão #0b140f, `--surface` #121e17, verde-neon #43df7a, laranja
#e8a33d para a carga; no claro, verde-floresta #106632 — com a segunda e a
terceira superfícies vindas da régua U28 (a direção só tem dois degraus)
e quatro valores do claro escurecidos 1–5 % pelo vizinho que passa
(`artifacts/paleta_nervura.py`; 274 pares, zero reprovados; pior par
`--danger`/`--surface-3` 4,65 no Ferro); as fontes — Big Shoulders
Display (display, caixa alta 800 nos títulos e nomes, 900 nos números) e
Archivo (texto), 70 364 bytes; **a Big Shoulders NÃO tem `tnum`** (dígitos
proporcionais, medido com fontTools), então a display fica para o número
SOLTO e toda coluna de números — a lista de pesagens — é Archivo tabular
(`config/test_fontes.py` prende as duas regras); a quina — ZERO
`border-radius` em 390 declarações do mockup — virou três SLOTS com o
mesmo valor (`--quina-g`/`--quina`/`--quina-p: 0`), `--pill` saiu e todo
`border-radius` do arquivo é slot, `50%` (o anel) ou `inherit`; o
movimento — `--mov-nervura: .6s` e `nervura-acende` (a régua que risca da
esquerda para a direita) no lugar de `corte-abre`/`corte-desdobra`, como
`::after` da refeição registrada e do bloco da meta batida. A régua
diagonal (`--nervura`), o traço de 2 px (`--traco`), o CTA inclinado
(`--inclinado`) e a ponta de folha (`--ponta`) nascem com o consumidor,
no PR dos componentes.

**O andaime nos componentes (NERVURA 2/3, 17/09/2026).** `--traco: 2px`
é a borda de contorno, quieto, campo e chip (e transparente no primário,
para os três botões terem a mesma altura empilhados); o primário é
INCLINADO por `clip-path: var(--inclinado)` num `::before` de fundo — o
botão em si continua retângulo, porque `clip-path` no botão cortaria o
anel de foco e a área de toque (`isolation: isolate` + `z-index:
var(--camada-fundo)` põem o fundo atrás do texto sem sair de trás do
botão); o texto do primário é a display em caixa alta a `--texto-xl`, e
o primário pequeno (`btn--sm`, 44 px) volta ao texto porque a display
nunca desce de 20 px; o halo de hover/foco FICA (decisão do dono de
16/09) — o anel traça o retângulo inteiro, inclusive onde o preenchimento
foi cortado, e é o preço de ter o toque inteiro. A nervura
(`--nervura: -14deg`) é `::after` decorativo atrás do texto (`z-index:
var(--camada-fundo)`): no prato (`.today-hero`) nasce no canto inferior
esquerdo, e no título (`.page-head h1`) nasce no canto SUPERIOR esquerdo e
sobe para o respiro acima — a primeira versão nascia na base do `h1` e
cruzava as letras, e nem "atrás" salva legibilidade de um título
riscado. A ponta de folha (`--ponta`) é o `::after` do preenchido da
barra de progresso, na cor da própria barra (`background: inherit`), com
`overflow: visible` na trilha. A aba ativa é `--brand` sem preenchimento,
com a régua de `--traco` em cima. O chip é caixa de contorno em caixa
alta .06em. `config/test_nervura.py` prende tudo isso; a regra
`.page-head h1,
.today-hero` está nessa ORDEM porque `GymReadyTests`
âncora na primeira ocorrência de `
.today-hero,` para achar a régua do
fio de pilar.

**As telas da execução e do placar (NERVURA 3/3, 17/09/2026).** Os dois
heróis da execução são display em caixa alta: o nome do exercício
(`.agora__nome`, já da 1/3) e "SÉRIE 2 DE 4" (`.series__titulo`, `--texto-xl`
800 com o número em `--texto-3xl` 900); o campo de carga (`.registro__carga`)
virou só um sublinhado de `--traco` em `--terra`, com o número em display
900 a `--texto-2xl` e centrado — o foco troca o sublinhado por `--brand`
(`box-shadow: 0 var(--traco) 0`), sem anel em volta, porque a caixa não
existe mais. A régua "a display nunca desce de 20 px" tem um caminho que o
teste das REGRAS não vê: HERANÇA — `.series__faixa` ("6-10 reps", 12,8 px)
mora dentro do herói e saiu na captura em Big Shoulders; `config/test_fontes`
cobra que o filho pequeno declare `var(--font)` de volta. O placar deixou de
ser a folha-lima cheia: `.recompensa` é transparente, sem borda, texto em
`--text`, e a recompensa é a NERVURA que risca — um `::before` só, 14 px de
altura, `clip-path` que desenha a régua de `--traco` E a ponta de folha no
fim, `rotate(var(--nervura)) scaleX(0 → 1)` em `--mov-nervura` (`nervura-
risca`); o número herói (`--texto-heroi`, 72 px, 900, `--brand`) conta do
zero em `--mov-nervura` (`pwa.js` lê o token) e reserva `min-width: 4ch`
porque a Big Shoulders é proporcional e a contagem sacudia a linha; os
pequenos entram em cascata DEPOIS da nervura (`--mov-cascata` × i +
`--mov-nervura`) e os botões chegam parados a 1 s (`aparece`, `steps(1)`).
O `h1` do placar é o nome da sessão + "fechado" (o mockup tinha um
"TREINO FECHADO" genérico; o nome da sessão é o que a pessoa acabou de
fazer). Com `prefers-reduced-motion` a lista é `.recompensa::before` e
`.recompensa .btn` — não `.recompensa`, que já não se move.
Os tempos foram medidos ao vivo por `getAnimations()` no CDP (nervura
600 ms, cascata +600/+680, botões +1000); `nav.py` re-emula a cada comando, então captura
estática de movimento é sempre com `movimento reduzido`.

**Dois achados do QA em produção (18/09/2026), os dois MEDIDOS na tela e
não na tabela.** (1) A barra da semana do Progresso é `--folha` sobre a
TRILHA — `--fio`, uma tinta translúcida composta na superfície —, e esse
par não está na auditoria (que mede gráfico × superfície): no Papel dava
2,97:1; `--papel-folha` foi de #1d833f para #1b7c3b (3,26 sobre a trilha,
3,6 sobre `--surface-3`), e `config/tests.py` passou a compor o fio e
medir o par. (2) A nervura do título sobe ~24 px acima do `h1`; no
`/demo/` a faixa "Ambiente de demonstração … Saiba mais" tinha 16 px de
margem e a ponta entrava 16 px na caixa do link (encostava no sublinhado).
A faixa passou a 40 px (`--espaco-7` + `--espaco-6`): com 32 a ponta caía
exatamente na base da caixa (folga 0, medido), com 40 sobram 8.
`config/test_nervura.py` prende a margem. Os pares que raspam na auditoria
(`--danger`, `--brasa` sobre `--surface-3`) não ocorrem em tela real:
medido, `--danger` só aparece sobre `--surface` (6,76 Ferro / 5,49 Papel)
e sobre a tinta de erro (6,17 / 5,8); `--brasa` só como texto da corrida.
O `agent-browser` estava BLOQUEADO pelo Smart App Control do Windows quando
isto foi feito (o QA foi por `scripts/qa/nav.py` sobre o mesmo Chrome 153);
desde 20/09/2026 o SAC está desligado e os dois rodam — ver "Limites reais
deste ambiente".

## Testes

Nome descreve o comportamento, não o método. Docstring diz **por que** aquilo
importa — de preferência com o caso real que motivou o teste.

Armadilha recorrente neste repositório: **o seletor do JavaScript e o marcador
do HTML são a mesma string.** `assertNotIn("data-x", html)` passa por acidente
porque `data-x` também está dentro do `<script>`. Ancore na classe
(`class="card resumo"`) ou no texto visível.

Contraste é medido, não julgado: `config.tests` recalcula a razão WCAG a partir
dos tokens, inclusive contra os fundos tingidos (`--brand-soft` e companhia).

**DOUTRINA DO RELÓGIO (decisão do dono, 21/09/2026): UM TESTE NUNCA LÊ O
RELÓGIO NEM O CALENDÁRIO REAL — CONGELA SEMPRE.** A suíte congela a DATA
(quarta 16/09/2026) E A HORA (12:00 locais + o decorrido desde que o runner
ligou o relógio, `HORA_DA_SUITE` em `config/relogio.py`); a hora era real até
21/09, e o minuto da máquina derrubou o gate do PR #96 duas vezes com main
verde por sorte — `analytics/test_pico_de_sessoes.py` contava sessões por
janelas absolutas de 5 min a partir de `timezone.now()` e passava 1 vez em 5.
As regras: (1) `date.today()`, `datetime.now()`, `datetime.utcnow()` e
`time.time()` são PROIBIDOS em teste — `config/test_relogio.py` varre a
árvore (`OTesteNaoLeAMaquinaTests`) e a única exceção nomeada é o
`datetime.now()` do gerador de token de senha; `time.monotonic()`/
`perf_counter()` medem duração e podem; (2) `timezone.now()`/`localdate()`
num teste já vêm congelados — são os únicos "agora" permitidos; (3) teste
que conta por janela, minuto ou hora não usa nem esse "agora": pede
`relogio.congelado_em(datetime(2026, 9, 16, 16, 0))` e recebe um instante
EXATO, parado, o mesmo que o código sob teste lê (é o que o pico de sessões
faz); (4) expectativa nunca nasce de "agora ± N horas" que possa cruzar a
meia-noite, nem de `if` sobre a hora corrente — com a hora fixa às 12:00
isso deixou de variar, mas continua sendo o desenho errado; (5) a
`noturna.yml` é o ÚNICO lugar com o relógio real (`NUTRIPLAN_DATA_REAL=1`),
e é ela que vê deriva de calendário.

**A SUÍTE VIVE NUMA QUARTA-FEIRA CONGELADA, ÀS 12:00, E A NOTURNA VIVE NO
DIA REAL (18/09/2026; hora congelada desde 21/09).**
`RunnerUnico.setup_test_environment` liga `config/relogio.py`:
`timezone.now()` devolve a DATA local `DATA_DA_SUITE` — quarta 16/09/2026,
o "pior estado" que `plans/test_stress` já congelava à mão — às
`HORA_DA_SUITE` (12:00) mais o decorrido. Só `timezone.now`: o app deriva
"hoje" de `localdate()`/`localtime()`, nunca de `date.today()`, e o
decorrido continua monotônico (`created_at` ordena; `Barrier` e timeouts
são de verdade, porque medem por `time.monotonic`). O
`default=timezone.now` de campo guardou o OBJETO da função na definição da
classe e é trocado à mão — com o cache `_get_default` esquecido, senão a
troca não muda linha nenhuma. Dois incidentes pediram isto: o push de
terça 15/09 que passou e reprovava `plans.test_stress` na quarta, e
`test_a_ficha_de_OUTRO_dia` caindo ao fatiar a suíte noutro dia (18/09) —
a ficha de outro dia mostra a variação da PRÓXIMA ocorrência, que depende
do calendário, e o teste assumia a opção 1. Teste que precisa de outro dia
usa `relogio.congelado_em(dia)` (ou o `mock.patch` de `localdate` que já
usava); teste que precisa do dia de verdade usa `relogio.relogio_real()`;
**teste nunca chama `date.today()`** — com a data congelada ele diverge de
`localdate()` e passa a medir a máquina (achievements, test_movimento e
plans.tests faziam isso e foram convertidos). `NUTRIPLAN_DATA_REAL=1`
desliga o congelamento; `NUTRIPLAN_DATA_DA_SUITE=AAAA-MM-DD` escolhe a
data — é assim que se reproduz o que a noturna achou, ou se varre a
semana atrás de teste que depende do dia. A dependência de calendário que
o congelamento esconde tem dono: `.github/workflows/noturna.yml` roda a
suíte completa toda madrugada (04:20 UTC) com a data real, o log DIZ
"Relógio: DATA REAL" (o fluxo faz `grep`), e uma issue "Suíte noturna
vermelha com a data real" abre ou ganha comentário ao cair e FECHA sozinha
na primeira verde; `simular_falha` no `workflow_dispatch` é o controle
positivo do alerta. O gate (`suite.yml`) NÃO liga o relógio real, e
`config/test_relogio.py` prende as duas metades. O que o gate mede é um
dia só, de propósito: os testes de paridade da ficha de outro dia
(`workouts/test_ficha_unica.py`) escrevem a data dos DOIS ramos — bloco
ímpar → opção 2, bloco par → opção 1 — e cada ramo fica vermelho sozinho
quando `variacao_do_dia` ignora a paridade. E a semana foi VARRIDA antes
de a noturna existir (`NUTRIPLAN_DATA_DA_SUITE` em quarta, segunda, sábado
e domingo): oito testes de `workouts` assumiam que "a sessão de hoje" é a
linha cujo `weekday` é hoje — verdade só nas primeiras posições da semana;
com cinco dias a partir de um sábado a posição 3 é A de novo, e o app
linka a ficha da linha de SEGUNDA. Teste que precisa da sessão de hoje
chama `services.sessao_do_dia(plano, localdate())`, e "outro dia" é outra
LETRA; teste que precisa de uma letra específica usa `tornar_hoje`; a
opção de hoje é `opcao_do_dia`, nunca `da_opcao(1)` fixo. O cron que o #33
tinha posto em `suite.yml` saiu: rodaria congelado e não pegaria dia
nenhum — a noite é da `noturna.yml`.

## Limites reais deste ambiente

- **O `agent-browser` É O PADRÃO DE QA DE NAVEGADOR DE NOVO (20/09/2026),
  e `scripts/qa/nav.py` (CDP) é o FALLBACK.** Histórico em uma linha: de
  14 a 20/09 o Smart App Control bloqueava o binário (`spawn`, evento
  CodeIntegrity 3077) e o `nav.py` foi a única ferramenta; o dono desligou a
  política em 20/09 e o `agent-browser` 0.38.1 voltou — provado em produção
  no mesmo dia: `open` do `/demo/`, `snapshot -i`, `click` num cartão
  (chegou em `/demo/treino/`), `screenshot` a 390 px, `vitals`. O que ele
  dá e o `nav.py` não: `snapshot` com refs para o agente, `a11y` (axe-core),
  `vitals`, `network requests`, `batch`, `set media dark|light`, `set
  offline`, `find role|text|label`. Regras que continuam: sessão própria
  (`AGENT_BROWSER_SESSION`, nova a cada execução de QA — o perfil guarda
  cookies), saída sempre para arquivo e `stdin` fechado (o daemon herda o
  stdout e um pipe espera um EOF que nunca vem), `set viewport` e `set
  media` antes do `open`. O `nav.py <sessão> open|eval|click|type|
  screenshot|viewport|cookie|tema|movimento|rede` fica para o que o
  `agent-browser` não faz — `rede 3g` (latência/banda emuladas para o
  L08), `permissao`, `movimento reduzido` — e para sites de terceiros na
  sessão logada do dono; fala CDP com o MESMO Chrome 153
  (`~/.agent-browser/browsers`). Node 24/npm 11 (WinGet) continuam
  instalados; Lighthouse e Playwright seguem de fora por decisão.
- **O mesmo bloqueio valia para `.pyd` sem assinatura no `.venv` — e
  acabou junto com o SAC.** O fontTools 4.65 vem com seis extensões
  compiladas (`bezierTools`, `cu2qu`, `qu2cu`, `momentsPen`, `iup`,
  `lexer`) e `config/test_fontes.py` errava com "Uma política de Controle
  de Aplicativo bloqueou este arquivo" — três ERROR em todo hook local, e o
  CI (Linux) verde. Os seis `.pyd` foram afastados para
  `*.pyd.bloqueado-sac` em 18/09 (o fontTools caía no Python puro, mesmo
  resultado) e DEVOLVIDOS em 20/09, com o SAC desligado: importam como
  extensão e os 13 testes de `config/test_fontes.py` passam no Windows. O
  `SkipTest` de `win32` (PR #34) fica no teste como guarda — só dispara se a
  extensão não carregar, e hoje ela carrega. O psycopg também: a
  implementação `binary` (`pq.cp312-win_amd64.pyd`) foi bloqueada na manhã
  de 20/09 e voltou à tarde; o `zz_nutriplan_libpq.pth` que a sessão de
  auditoria pôs no `.venv` para o `libpq` 16 fica, porque é inofensivo.
- **PWA não escreve no Apple Saúde nem no Health Connect** — não existe API web.
  A ponte era um TCX em `/treino/exportar/saude.tcx`; saiu em 20/09/2026 por
  decisão do dono (sem uso, e a segunda fórmula de duração morava lá).
  `workouts/health_export.py` ficou só com `resumo_da_sessao`, que o painel lê.
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
- **O SMART APP CONTROL DESTA MÁQUINA FOI DESLIGADO PELO DONO EM
  20/09/2026, e é irreversível** (`VerifiedAndReputablePolicyState = 0`;
  religar exige reinstalar o Windows). De 14 a 20/09 ele bloqueava binário
  sem assinatura com "Uma política de Controle de Aplicativo bloqueou este
  arquivo" (evento CodeIntegrity 3077), e a regra do período — `.pyd`/`.exe`
  não assinado bloqueado → Python puro, nunca remendo no teste — pagou três
  contas: o `agent-browser` (`NotSigned`) não rodava e o QA era `nav.py`
  sobre o Chrome 153 que ele baixou; os `.pyd` do fontTools foram afastados
  do `.venv` compartilhado; e o `psycopg` binário caiu na manhã de 20/09
  (`.pth` do `libpq` 16 como contorno). Tudo isso voltou a carregar no
  mesmo dia, verificado: `agent-browser` abre/lê/fotografa, `nav.py` sobe o
  Chrome 153, `psycopg.pq.__impl__ == "binary"`, os seis `.pyd` do fontTools
  importam. A mudança de configuração de segurança foi do dono, na tela de
  Segurança do Windows — a sessão não a faz nem com autorização; ela só
  verifica depois. Se o sintoma voltar a aparecer, não é o SAC: olhe a
  quarentena do Defender. **A regra "sem remendo no teste" continua valendo
  sem o SAC**: binário que não carrega se resolve na biblioteca (afastar ou
  reinstalar o `.pyd`), nunca com `skip` escrito para a máquina passar. O
  `skip` de `config/test_fontes.py` (`win32`) continua no teste como guarda,
  hoje sem gatilho; no CI (Linux) a extensão que não carrega é FALHA.
- **Nenhum processo de fundo abre janela, e todo processo de fundo nasce em
  `scripts/fundo.py`.** No Windows 11 o Windows Terminal hospeda todo console
  novo — e um processo sem console (os do Claude Code, o Agendador) que lança
  `powershell`, `cmd /c` ou `start` cria um console novo, que é uma janela na
  tela do dono. Foi assim em 16/09/2026: a tarefa `NutriPlan lembretes` abria
  um PowerShell vazio a cada 5 minutos, e `-WindowStyle Hidden` não evitava,
  porque o PowerShell lê a flag depois que o console dele já existe.
  `fundo.py rodar` lança com `CREATE_NO_WINDOW` (console que nunca aparece e
  os netos herdam — não `DETACHED_PROCESS`, que dá console nenhum e faz o
  primeiro neto de console abrir janela); `fundo.py notificar` toca por
  `winsound` e avisa por `pythonw`. `config/test_janela_de_fundo.py` varre
  `scripts/`, `artifacts/`, `.superpowers/` e as skills e fica vermelho com
  qualquer chamada dessas fora do `fundo.py`.
## Deploy

**O GATE É O CI, E NINGUÉM EMPURRA EM `main` (17/09/2026).** Um push chegou
ao GitHub naquele dia sem passar pelo reflog de nenhuma sessão desta
máquina; um gate que só existe numa máquina não é gate, porque ninguém
consegue conferir se ele rodou. Desde então:

- **DOIS fluxos desde 18/09/2026, e o gate é o RÁPIDO.** A suíte inteira,
  serial, executava em ~31 min (medido nos últimos 10 runs: instalar ~10 s
  com cache, o resto é o `manage.py test`), e com a fila local cada PR
  esperava ~32 min de runner. `suite-rapida.yml` (check **"suíte rápida"**)
  é o GATE: a suíte FATIADA em 5 por `ci/shard.py` (um job por fatia, cada
  um SERIAL, os jobs em paralelo), `--exclude-tag lento`. **Não** usamos
  `--parallel` do Django: ele roda cada processo com um clone do banco, mas
  a suíte tem teste que assume ORDEM de PK, e no CI (PR #33, Linux) UM caiu
  e o runner morreu com `cannot pickle 'traceback'`, escondendo a falha —
  fatiar mantém cada fatia idêntica ao verde serial de sempre. `ci/shard.py`
  descobre TODO módulo versionado e reparte equilibrado (peso por linhas, e
  peso extra para quem semeia um ano); `config/test_ci.py` cobra que a
  partição não deixa módulo órfão (um módulo em nenhuma fatia nunca rodaria
  no gate). O check é o job `gate` ("suíte rápida"), verde só se TODAS as
  fatias passam. Roda em todo PR, alvo < 10 min. `suite.yml` (check
  **"suíte completa"**) roda as MESMAS fatias com TUDO, inclusive `lento`,
  DEPOIS do merge (`push: main`) e à mão (`workflow_dispatch`) — não barra
  PR; a NOITE é de `noturna.yml` (a suíte com a DATA REAL e a issue de
  alerta; ver "Testes"), porque a suíte roda congelada e um cron aqui
  mediria a mesma quarta de sempre. Os dois: Postgres 16 (produção), sem
  segredo, `contents: read`, cada fatia sobe seu log e `--durations 15`.
  **`@tag("lento")` é só para teste pesado que NÃO é o único guarda de algo
  crítico** (concorrência, dourado, idempotência, segurança ficam no rápido
  mesmo quando custam) — cada um movido está justificado no relatório;
- **O GATE ESTÁ NO SERVIDOR DESDE 21/09/2026: o repositório virou PÚBLICO e
  `main` está protegida** — check "suíte rápida" obrigatório, `strict`,
  `enforce_admins`, sem force-push (conferido por `scripts/github.py
  protecao`, que imprime exatamente isso). Entre 18 e 21/09 o repositório era
  privado, a API devolvia 403 para branch protection e rulesets, e o único
  gate era o COOPERATIVO — `scripts/github.py enfileirar`/`esperar` esperando
  o check `CHECK` (= "suíte rápida") antes de mergear pela API. A fila local
  continua sendo o caminho (ela também prova o staging e promove), e ninguém
  chama `merge` à mão; a diferença é que hoje o servidor recusa o que ela
  recusaria. Público também quer dizer **minuto de Actions ilimitado** — o
  gate rápido continua valendo por tempo de espera, não por custo;
- **A FILA DE MERGE DO GITHUB NÃO EXISTE EM REPOSITÓRIO DE CONTA PESSOAL
  (17/09/2026)** — a API devolve 422/403. A resposta é a FILA LOCAL:
  `scripts/github.py enfileirar <n>` põe uma senha em
  `C:\Users\biel-\nutriplan-fila\` (fora de qualquer worktree, uma por PR,
  em ordem de chegada), e a sessão da vez faz o laço merge de `main` na
  branch → push → **espera "suíte rápida" do head certo (`esperar --sha`)**
  → merge, enquanto as outras esperam. Posse abandonada (90 min) é liberada
  sozinha. **O laço roda num WORKTREE PRÓPRIO e descartável (18/09/2026), não
  na árvore da sessão** — `git worktree add --detach` no head remoto da
  branch, merge/push/merge lá, `git worktree remove` no fim —, então a sessão
  NÃO precisa estar com a branch em HEAD e SEGUE trabalhando enquanto a fila
  anda (antes o `enfileirar` travava a árvore da sessão até a fila terminar).
  O push do worktree é `--no-verify`: o pre-push é o atalho LOCAL e redundante
  ali (o gate é o check do CI que a fila espera sobre o mesmo SHA, e a árvore
  do worktree já é a que sobe). O ruleset com a fila do GitHub
  (`corpo_da_fila`, `fila-ativar`) e o gatilho `merge_group` ficam PRONTOS
  para o dia em que o repositório morar numa organização (ou virar público) —
  decisão do dono;
- **Se a "suíte completa" quebrar** (pós-merge): foi um `lento` que
  regrediu no merge que acabou de entrar. O GitHub manda e-mail ao dono por
  run vermelho no branch padrão (é o alerta, sem segredo de webhook).
  Conserte ou reverta o merge culpado; o gate rápido não pega `lento`, então
  a correção também passa rápido. Rodar a completa à mão: `workflow_dispatch`
  na aba Actions. **Se a "Suíte noturna (data real)" quebrar**: é
  calendário ou hora — a issue "Suíte noturna vermelha com a data real" diz
  o dia e como reproduzir (`NUTRIPLAN_DATA_DA_SUITE=<dia>`);
- o fluxo é **branch → PR → `enfileirar` (espera a vez, atualiza, espera o
  check, mergeia, PROVA NO STAGING) → `promover` → `/saude/` de produção**.
  Sem `gh` nesta máquina, o helper é `scripts/github.py` (`pr`, `status`,
  `esperar`, `enfileirar [--promover]`, `promover <sha> [--esperar]`, `fila`,
  `fechar`, `protecao`; `merge` à mão só fora da fila, e é o que cria a
  corrida), com o token do Git Credential Manager — nunca impresso, nunca
  em argumento;
- o `pre-push` local virou ATALHO: no worktree descartável do SHA que sobe,
  `config` + teste dourado + doutrina + gate por letra + orçamentos, em
  poucos minutos; `NUTRIPLAN_SUITE_COMPLETA=1` roda tudo localmente como
  antes. `config/test_ci.py` prende o contrato dos dois fluxos, do hook e do
  helper.

**STAGING ANTES, PROMOÇÃO DEPOIS (21/09/2026).** Há DOIS serviços web no
Render, os dois `free`, o mesmo repositório e o mesmo `scripts/build.sh`:

| serviço | URL | banco | recebe |
|---|---|---|---|
| `nutriplan-staging` | https://nutriplan-staging.onrender.com | branch `staging` do MESMO projeto Neon (criada *schema only*: zero dado de gente real; o build semeia catálogo e demo) | **todo merge em `main`, sozinho** (`autoDeploy: true`) |
| `nutriplan` (produção) | https://nutriplan-xxfn.onrender.com | branch `production` do Neon | **só o que alguém PROMOVE** (`autoDeploy: false`) |

O merge em `main` dispara o Render — **do staging**. Produção não muda um
byte até a promoção: `scripts/promover.py <sha> --esperar` (ou
`scripts/github.py promover <sha> --esperar`, ou o botão "Promover para
produção" na aba Actions — `.github/workflows/promover.yml`,
`workflow_dispatch`, com `RENDER_API_KEY` nos segredos do repositório). Os
três caminhos são o MESMO código: exigem que o SHA esteja em `origin/main`
E que o staging já responda esse commit em `/saude/`, pedem `POST
/v1/services/<produção>/deploys {"commitId": <sha>}` ao Render e esperam
`/saude/` de produção dizer o commit. `enfileirar` termina PROVANDO o
staging (`_provar_staging`: até 12 min esperando `/saude/` do staging
responder o SHA do merge) e só promove com `--promover`; sem a flag ele
imprime o comando e para — o QA em staging (conta descartável, dois temas)
acontece ENTRE o merge e a promoção. Provado em 21/09: o PR entrou em
`main`, o staging respondeu o commit, produção continuou no anterior até o
`promover`. O staging se anuncia por `NUTRIPLAN_AMBIENTE=staging`
(`config/ambiente.py`: `X-Robots-Tag: noindex, nofollow` em toda resposta,
`<meta name="robots">`, a faixa "STAGING" em toda tela e `"ambiente"` no
`/saude/`) — em produção a variável não existe e nada disso acontece. A
chave, os tokens e o `DATABASE_URL` do staging são PRÓPRIOS (gerados na
criação, `~/.nutriplan-secrets/staging_env.json` e `staging_database_url`);
SMTP, Google e VAPID são os de produção (só conta de QA recebe e-mail do
staging; o login com Google NÃO funciona no staging até o domínio entrar
no console do Google — decisão do dono). O staging foi criado pela API
(`artifacts/criar_staging.py`, valores nunca impressos) e está declarado no
`render.yaml`, que é a verdade do painel; a branch do Neon nasceu
*schema only* e por isso veio SEM `django_migrations` — o primeiro build
caiu em "relation already exists" e o schema foi zerado uma vez
(`drop schema public cascade`) antes de o `migrate` construir tudo.
`config/test_staging.py` prende o contrato inteiro. Worktree de sessão com
o helper ANTIGO (sem `_provar_staging`) mergeia e NÃO vê produção mudar:
`git merge origin/main` antes de enfileirar, sempre. **A promoção é de um
SHA de `main`, e leva tudo que está antes dele** — por construção, não por
combinação: tudo em `main` passou pelo gate e pelo deploy automático do
staging; o que não pode ir para produção não pode estar em `main`
(pergunta da sessão de analytics, 21/09/2026).

**A REGRA DA PROMOÇÃO (decisão do dono, 21/09/2026, tarde): produção só
muda no fim de um LOTE PROVADO, e no máximo uma vez por hora.** Ninguém
mais promove "o seu SHA"; o lote é a ponta de `main`. `scripts/promover.py
--lote` (= `scripts/github.py promover-lote`) é a regra inteira, e roda em
dois lugares: no fim de TODO merge da fila (`enfileirar`, depois de provar
o staging) e no cron `promover-lote.yml`, de meia em meia hora — para o
merge que caiu numa janela fechada não depender do merge seguinte. Na
ordem: o staging tem de responder a ponta de `main` (senão "NÃO PROVADO",
nada sobe); produção já lá, nada a fazer; a última promoção — o deploy
mais novo de produção, pela API do Render, qualquer gatilho — tem de ter
mais de 60 min, senão o lote é **ADIADO** e produção não muda (é assim que
dois merges seguidos viram UMA promoção); então a prova — smoke nas rotas
públicas do staging e o **E2E de gente** (`scripts/qa/e2e_staging.py`, os
12 passos) —, e reprovou, nada sobe e o código de saída é 1; só então a
promoção de sempre. `--forcar-janela` (o `--promover` do `enfileirar`)
ignora o relógio para um hotfix e NUNCA a prova; `--sem-e2e` existe para
runner sem navegador e fica dito no log. O botão "Promover para produção"
(`promover.yml`) virou a EXCEÇÃO nomeada: promove um SHA à mão, sem E2E —
é o que o runbook usa para voltar — e desde a tarde de 21/09 **a promoção
à mão também respeita a janela** (`promover.py <sha>` recusa dentro dos
60 min; `--forcar-janela` é a porta do hotfix; o `deploy --voltar` do
runbook não passa por ela, porque incidente não espera relógio). Provado em
21/09: o próprio PR da regra (#93) subiu ao mergear (janela aberta, smoke +
E2E verdes, `7121727`); os dois merges seguintes com a janela fechada (#98,
o gitleaks, e o PR das threads/Starter) saíram "LOTE ADIADO", produção
ficou onde estava, e o `--lote` seguinte subiu os dois numa promoção só. `config/test_lote.py` prende cada cenário
com a API, o smoke e o E2E falsos.

**O BLUEPRINT DO RENDER NÃO SINCRONIZA SOZINHO (21/09/2026, tarde).**
MEDIDO: um merge que mudava só o `render.yaml` (o `startCommand`) fez um
deploy de PRODUÇÃO com trigger `blueprint_sync`, mesmo com `autoDeploy:
false` — o Blueprint aplica a definição nova e reinicia o serviço, e isso
é deploy fora do lote. O auto-sync foi desligado pela API
(`artifacts/blueprint_autosync.py off`; `status: paused`). Consequência
escrita: **mudança no `render.yaml` só chega ao painel por um Sync manual**
(Render → Blueprints → nutriplan → *Manual Sync*), que reinicia os dois
serviços — faça-o junto de um lote, e nunca sem olhar o diff que o painel
mostra. Variável de ambiente continua indo pela API (`scripts/incidente.py
rotacionar`, `artifacts/web_threads_env.py`), e o arquivo continua sendo a
verdade do que o painel DEVE ter.

**THREADS NO GUNICORN, MEDIDO — E A CONDIÇÃO DO PLANO STARTER (decisão do
dono, 21/09/2026).** O free do Render é 0,1 CPU e 512 MB, dois workers. O
k6 (`carga.yml`, degraus 5/10/25/50) mediu no staging: **sync** → teto 5
usuários simultâneos (p95 < 2 s, zero erro), p95 @10 de 0,4 s (`vivo`) a
3,7 s (`/demo/hoje`), 16 % de erro a 25; **gthread com 2 threads** → teto
5, p95 @10 de 0,7 a 4,9 s (o `/demo/hoje` piora 3,7 → 4,9 s; o resto
oscila), 20 % de erro a 25; **gthread com 4** → as rotas leves melhoram a
10 (`vivo` 0,2 s, `entrar` 0,8 s, capa 1,1 s) mas o `/demo/hoje` vai a
6,2 s e passa de 2 s já a 5 usuários (teto ABAIXO de 5), 17 % a 25. Thread
não é CPU: com 0,1 CPU, cada thread a mais é contenção nas telas pesadas,
e a diferença entre as três configurações cabe no ruído de uma CPU
compartilhada. Ficou `--worker-class gthread
--threads ${WEB_THREADS:-2}` nos dois serviços (`WEB_THREADS=2` no painel,
pela API) — ganha nas rotas leves sem perder no pior caso, e o
`config/test_gunicorn.py` prende o comando. **O lever de verdade é o
plano.** A condição para o Starter (US$ 7/mês: 0,5 CPU, 512 MB, sem sono),
que é decisão do dono e gasta dinheiro: `manage.py pico_de_sessoes
--dias 7` (uma consulta no analytics: sessões DISTINTAS na mesma janela de
5 min, o pico de cada dia) mostrando **≥ 5 sessões — o teto medido — em
dois dias da mesma semana**, ou o e-mail de 5xx disparando por carga (sem
deploy no meio). Enquanto o pico ficar em 1–4, o free basta e o que se
otimiza é consulta, não plano. Rode o comando com o role leitor
(`DATABASE_URL=$(cat ~/.nutriplan-secrets/backup_database_url)`) para não
tocar em nada.

**O STAGING TEM UM E2E NOTURNO DE ROBÔ (21/09/2026).**
`.github/workflows/e2e-noturno.yml` (04:30 de Brasília, e pelo botão) roda
`scripts/qa/e2e_staging.py` com o `agent-browser` — Chromium headless, o
mesmo do QA local — fazendo o caminho de uma pessoa: cadastro → as três
etapas do onboarding → "Calcular minha estimativa" → +250 ml de água → refeição
registrada → uma série concluída no treino → as mesmas telas em tema claro
(`set media light`) → movimento reduzido (`prefers-reduced-motion` emulado:
`getAnimations()` não pode ver nada acima de 50 ms na Home nem na execução)
→ exclusão da conta pela tela → login recusado (a prova de que sumiu). Doze
passos, uma captura por passo (390×844, escuro e claro) no artefato
`capturas-e2e` de todo run; falhou, `erro-<passo>.png`
+ o snapshot em texto, a conta é apagada mesmo assim (`finally`) e a issue
"E2E noturno falhou" abre. A conta é `qa-e2e-<run>-<data>@nutriplan.invalid`
com senha gerada no job e nunca impressa, e o roteiro só aceita um `/saude/`
que diga `"ambiente": "staging"` — produção não recebe conta de robô.
Ensaiado na máquina em 21/09: 11 de 11 em ~60 s. Quatro coisas que custaram
tentativa: `fill` não preenche `<input type=date>` (entra pelo DOM, conferido);
no Windows o `agent-browser.cmd` passa o `eval` pelo cmd.exe, que come `||`
(o roteiro chama o `.exe` direto e os `eval` evitam `||`/`&&`); o daemon do
agent-browser herda os descritores (saída em ARQUIVO, `stdin` fechado, nunca
pipe); e o CTA da ficha nova não navegou atrás do convite de instalação (o
roteiro dispensa o convite na Home e, se um clique não navega, abre o `href`).
E uma QUINTA, que custou produção parada: **`check` sai com código 0 mesmo
quando a caixa não ficou marcada**. Em 24/09/2026 o `promover-lote` das
12:27 e das 17:26 reprovou em `onboarding-1` com a SEGUNDA caixa de
consentimento desmarcada ("Para continuar, marque esta caixa" no snapshot
do erro), e o mesmo roteiro fizera 13/13 três horas antes contra o MESMO
commit do staging — as duas caixas moram DENTRO de um `<label>` clicável, e
ali o clique no rótulo pode desfazer o do input. `Navegador.marcar` só
tratava a EXCEÇÃO, que é uma guarda que não confere: ela nunca via o caso
em que o comando "deu certo" e nada mudou. Hoje ela LÊ o estado, força pelo
DOM quando ele não é o pedido (com `input` e `change`, que é o que o
`pwa.js` escuta) e FALHA ALTO com o seletor quando nem assim marca —
reprovar três passos depois é um diagnóstico que já não diz o que houve.
**A consequência operacional fica escrita: E2E vermelho PARA a promoção do
lote**, e produção fica no commit anterior até alguém consertar; foi o que
segurou `1c66b92` por cinco horas.

E a SEXTA, achada pelo conserto da quinta: **`ir` clicava sem esperar o
link**. Com as caixas marcando, o lote das 15:22 passou o onboarding inteiro
e reprovou em `serie` com "Element not found: `a[href^='/treino/agora/']`" —
o segundo `ir` do passo chegou à ficha antes de ela existir. O caminho do
app está ÍNTEGRO (reproduzido com o perfil que o roteiro cria, sete dias e
ABC: o painel linka a ficha de hoje e a ficha traz a execução); o runner é
mais lento que esta máquina e o app ANIMA a troca de página — durante a view
transition o `elementFromPoint` devolve `<html>` por ~300 ms. `ir` agora
espera o seletor, como `marcar` já fazia desde o primeiro run do Actions.

`config/test_e2e_noturno.py` prende o roteiro com um navegador falso.

**O TESTE DE CARGA É MANUAL, SÓ GET, SÓ NO STAGING (21/09/2026).**
`.github/workflows/carga.yml` (botão; entradas `degraus` = "10,25,50,75,100"
e `duracao` = "60s") roda `scripts/carga/staging.js` no k6: degraus de
usuários simultâneos, um depois do outro, cada usuário percorrendo landing,
`/saude/vivo/`, entrar e o `/demo/` (capa, hoje, treino, histórico — o app
inteiro com a pessoa fictícia, a Home custando as mesmas 41 consultas), com
pausa de 0,5–1,5 s entre rotas. Nenhuma conta nasce e nada é escrito. O
relatório (`relatorio.md`, no resumo do run e no artefato `carga`) traz o
p95 por rota em cada degrau, a taxa de erro por degrau e o **TETO**: o maior
degrau em que toda rota ficou com p95 < 2 000 ms e erro < 1 %. Limiar
estourado é RESULTADO (o k6 sai com 99 e o run fica verde com o relatório);
qualquer outro código derruba o job. O roteiro exige `"ambiente":
"staging"` no `/saude/` e o endereço de produção não aparece nele nem no
fluxo. O staging é free — dois workers síncronos do gunicorn, Neon que
hiberna —, então o teto medido é o da infraestrutura gratuita, e é isso que
se quer saber antes de pagar por mais. `config/test_carga.py` prende o
contrato e confere a sintaxe do roteiro no `node`.

`scripts/build.sh` roda collectstatic → `check --deploy` → migrate → os três
seeds, com `errexit`: build que passa prova que a migração rodou. Confira em
`/saude/` — e olhe o `"ambiente"`: `"staging"` ou `""` (produção).

O `check --deploy` vem **depois** do collectstatic e é um portão, não um aviso:
ele importa a URLconf, que resolve `static()` para o favicon em tempo de import,
e sem o manifesto isso estoura com um erro que não tem nada a ver com o que a
verificação veio checar. Com `--fail-level ERROR`, o que reprova ali não sobe —
hoje são e-mail de produção (`accounts.E001`–`E003`) e força da SECRET_KEY
(`accounts.E004`–`E006`).

**O PRE-PUSH TESTA O COMMIT QUE SOBE, NÃO A ÁRVORE DE TRABALHO (17/09/2026).**
Incidente: o push de 15/09 (terça) passou "3044 OK" e o mesmo `main`
reprovava `plans.test_stress` na quarta. Duas causas, e as duas eram do
hook: (1) o teste de orçamento de consultas media a Home e o painel NO DIA
EM QUE A SUÍTE RODAVA — 36/21 consultas num dia de descanso do fixture,
41/27 num dia de treino com série registrada —, e o teto (40/25) tinha sido
medido numa terça; (2) o hook rodava `manage.py test` na árvore de
trabalho, que não é o que sobe: arquivo não commitado entra na conta e não
no push, e vice-versa. Hoje o teste congela a data no PIOR estado (quarta,
com série registrada) e o orçamento da Home é 41 com as consultas únicas
listadas; o painel ficou em 25 porque `resumo_da_sessao` passou a receber a
sessão e a escolha que o painel já tinha (27 → 24). E o hook exporta o SHA
do push num `git worktree` descartável, copia o `.env` e testa lá
(`scripts/hooks/pre-push`; `config/test_b9_disciplina.py` cobra). Não era
N+1: nenhuma consulta cresce com o histórico
(`test_o_custo_da_tela_nao_cresce_com_os_registros`); era estado e
calendário. E `/saude/` passou a devolver `commit` (`RENDER_GIT_COMMIT`,
sete caracteres): a prova de deploy deixou de depender de a mudança ter
superfície visível.

**SEGREDO NÃO ENTRA EM COMMIT: o cofre mora fora de todo repositório e o
pre-commit barra o NOME (21/09/2026).** O cofre é `~/.nutriplan-secrets`
(`C:\Users\biel-\.nutriplan-secrets`): conferido em 21/09 que nenhum
worktree o contém e que nem `C:\Users\biel-` é repositório (`git rev-parse`
falha lá). Duas travas por cima: o ignore GLOBAL da máquina
(`~/.config/git/ignore`, apontado por `core.excludesFile`) lista
`.nutriplan-secrets/` e cada nome do cofre — `render_api_key`,
`backup_database_url`, `staging_database_url*`, `staging_env.json`,
`tarefas_token`, `disparo_token`, `vapid-nutriplan-*.env` —, e `git
check-ignore -v` de dentro de um repositório mostra a regra que pega; e o
pre-commit roda **gitleaks** (`gitleaks git --staged --config
.gitleaks.toml`, binário do WinGet `Gitleaks.Gitleaks` ou do PATH) com as
150+ regras padrão MAIS as quatro do NutriPlan em `.gitleaks.toml`: o cofre
pelo CAMINHO (barrado por existir, seja qual for o conteúdo), a chave
`rnd_…` do Render, a URL do Neon com senha e a chave SMTP da Brevo. Sem o
gitleaks instalado, `scripts/segredos.py --staged` lê o MESMO arquivo e
aplica as quatro regras em Python puro — a trava não depende de ninguém ter
instalado nada. `config/test_segredos.py` prova os dois num repositório de
teste com `render_api_key` no índice (o gitleaks é `skip` nomeado quando
ausente; o Python nunca), e o hook foi provado de verdade: `git add -f
scripts/render_api_key` + `git commit` → "leaks found: 1", HEAD parado. O
único lugar onde uma forma de segredo pode ser ESCRITA é o próprio teste
(`[allowlist]`).

## O que existe no Render (inventário de 16/09/2026, sem valores)

Um workspace ("My Workspace"), região **Oregon**, e a chave de API
`nutriplan-claude-code` fora do repositório (`RENDER_API_KEY` no ambiente da
máquina e `~/.nutriplan-secrets/render_api_key`). `scripts/render_api.py`
fala com a API sem imprimir valor nenhum, e **o verbo diz se lê ou dispara
(21/09/2026)**: leitura é `inspect` (serviços e NOMES das variáveis),
`status`, `runs`, `logs [srv] [n]` (o web por padrão); escrita e disparo
são `env`, `cron` e `disparar-deploy` / `disparar-cron`. `deploy` e
`trigger` não existem mais — alguém procurava o log de build, chamou
`deploy` e o Render construiu o mesmo commit de novo (sem dano). Um verbo
de leitura roda com `_req` recusando qualquer método que não seja GET, por
construção; `config/test_render_api.py` roda cada verbo de leitura contra
uma rede falsa e prova que nada além de GET chega nela.

- **Web service `nutriplan`** (`srv-da6f5kou01pc73fsfkqg`): plano **free**,
  deploy automático de `main`, build em `scripts/build.sh`, healthcheck
  `/saude/`. Variáveis, por nome: `DATABASE_URL` (Neon — o banco do Render
  é só rollback), `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` (Brevo, 2525),
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `PYTHON_VERSION`,
  `WEB_CONCURRENCY` e, desde 16/09/2026, `VAPID_PUBLIC_KEY`,
  `VAPID_PRIVATE_KEY`, `VAPID_ADMIN_EMAIL` (par em
  `~/.nutriplan-secrets/vapid/`; a pública começa com `BPpbVTBznicK`). Com
  elas o cartão "Lembretes" aparece e a assinatura push é gravada — provado
  em produção com conta descartável e Chrome real: `/push/inscrever/` 200,
  FCM 201, notificação exibida.
- **Lembretes SEM cron e SEM nada pago (decisão do dono, 16/09/2026).** A
  criação do cron pela API respondeu `402 Payment information is required`
  (custaria no mínimo US$ 1/mês), e a instância web continua `free`.
- **Quem DISPARA lembrete com PONTUALIDADE é o UptimeRobot (18/09/2026), e o
  `schedule` do Actions é FALLBACK.** O `schedule` do GitHub atrasa e PULA —
  MEDIDO em 18/09: ~9 rodadas em 31 h (intervalos de 2 a 5,5 h), então o
  lembrete saía a cada ~4,4 h em vez de 5 min. O primário passou a ser um
  segundo monitor do UptimeRobot em `GET /tarefas/lembretes/externo/<token>/`
  (a cada 5 min, pontual). O UptimeRobot free só manda GET/HEAD e SEM
  cabeçalho, então o token vai na URL (`NUTRIPLAN_DISPARO_TOKEN`, SEPARADO do
  Bearer do POST): `config/observabilidade.py` o redige do log do Django, mas
  ele APARECE no log de ACESSO do Render — por isso é de baixo dano (só
  dispara lembretes vencidos, idempotente, com limite de taxa de
  `INTERVALO_MINIMO_EXTERNO`). A rota é `push.views.DisparoExternoView` (GET,
  503 sem a variável, 403 com token errado; loga user-agent e origem, nunca o
  token). O `schedule` continua no `POST /tarefas/lembretes/`
  (`TarefaLembretesView`, Bearer `NUTRIPLAN_TAREFAS_TOKEN`) como FALLBACK: o
  `push/tarefas.py` SE ABSTÉM (`rodar(externo=False)`) quando um disparo
  externo cuidou há menos de `RESERVA_DO_FALLBACK` (4 min) — assim o pontual
  manda e o `schedule` só assume se o UptimeRobot cair. A memória do último
  externo é por PROCESSO (dois workers) e some no restart; errar dá no
  máximo uma rodada redundante, que a constraint do `NotificationLog` torna
  inofensiva.

- **Quem MANTÉM ACORDADO é o UptimeRobot (17/09/2026), não o Actions.** Um
  monitor HTTP(s) gratuito — conta `bielpointblank@gmail.com`, monitor
  "NutriPlan vivo" (`dashboard.uptimerobot.com/monitors/804021213`) — bate em
  `GET /saude/vivo/` a cada 5 minutos (o mínimo do plano free) e alerta por
  e-mail se cair. `/saude/vivo/` NÃO consulta o banco, de propósito: um
  monitor em `/saude/` acordaria o Neon o tempo todo e a cota de 100 CU-h
  estouraria no meio do mês (ver "Monitor externo bate em `/saude/vivo/`").
  Antes disso o "manter acordado" era um LAÇO de ~5h45 dentro da rodada do
  Actions que se re-disparava sozinho (`GITHUB_TOKEN`, `actions: write`) — a
  "corrente"; com o UptimeRobot ela perdeu a razão e saiu (o fluxo voltou a
  ser uma rodada por disparo do `schedule`). A chave do UptimeRobot, se um
  dia a API for usada, mora só no ambiente da máquina (`API Settings` no
  painel), nunca no repositório.

**A infraestrutura é 100 % gratuita — Render free + Neon free + GitHub
Actions + UptimeRobot free —, e isso implica três coisas escritas:**

- **três responsabilidades, e o UptimeRobot cuida de duas (18/09/2026).**
  MANTER ACORDADO é do UptimeRobot em `/saude/vivo/` (monitor "NutriPlan
  vivo"); DISPARAR LEMBRETE, com pontualidade, é do UptimeRobot em
  `/tarefas/lembretes/externo/<token>/` (um segundo monitor); e o `schedule`
  do Actions em `POST /tarefas/lembretes/` é o FALLBACK. Os dois monitores
  batem de 5 em 5 min (o mínimo do free) e alertam por e-mail. Por que o
  UptimeRobot e não o `schedule` para disparar: o `schedule` do GitHub ATRASA
  e PULA (MEDIDO em 17 e 18/09), e lembrete precisa de pontualidade. **Se um
  dos monitores cair** (o e-mail avisa): reative no painel; enquanto isso, o
  `schedule` (fallback) assume os lembretes quando não vê disparo externo há
  > 4 min, e o `POST` do lembrete acaba acordando o web. **Se o `schedule` do
  Actions parar** (repositório sem atividade por 60 dias, ou pane): os
  lembretes param só se o UptimeRobot TAMBÉM estiver fora; `workflow_dispatch`
  na aba Actions dispara à mão, e um commit religa o `schedule`;
- **o Neon dorme entre refeições, de propósito.** Uma consulta a cada 5 min
  o manteria acordado o dia inteiro (182 CU-h contra 100 de cota). Por isso
  a tarefa, depois de rodar, calcula a próxima refeição de quem tem
  assinatura e responde `{"pausada": true}` sem banco até 20 min antes dela
  (ou até 30 min, o que vier primeiro — assinatura nova entra na conta em no
  máximo meia hora). A pausa é por processo (dois workers) e some no
  restart. O ping de manter acordado NUNCA usa `/saude/`;
- **dependência da política do free.** Render pode mudar o tempo de sono,
  as horas gratuitas (750 h/mês por workspace hoje) ou bloquear o ping;
  UptimeRobot pode mudar o mínimo de 5 min do plano free ou o número de
  monitores; GitHub pode desligar o `schedule` de repositório sem atividade
  por 60 dias (ele avisa por e-mail) e atrasa ou pula o cron sob carga; o
  Neon pode reduzir a cota. Nada disso quebra o app — só os lembretes e o
  cold start, e cada um tem o seu dono para reativar.

**O que mudaria se um dia virar pago:** instância `starter` no Render
(~US$ 7/mês) elimina o sono, e aí o UptimeRobot vira só alerta de queda; o
cron do Render (≥ US$ 1/mês, `scripts/render_api.py cron`, bloco de exemplo
no histórico do `render.yaml` até 16/09) substituiria o `schedule` do Actions
com relógio exato — e a janela de 15 min poderia voltar a 10, e o lembrete
deixaria de atrasar; o Neon pago tira o teto de CU-h e a pausa de
`push/tarefas.py` viraria só economia. Nenhuma dessas trocas exige código
novo além de apagar o que existe para contornar o gratuito.

## Runbook de incidente

Quatro cenários, cada um com o comando exato em `scripts/incidente.py`, e
cada verbo foi **ensaiado no staging em 21/09/2026** antes de esta seção
afirmar que funciona (`config/test_runbook.py` prende o script, o texto e a
correspondência entre os dois). Três regras valem para todo verbo: quem LÊ
cai em produção por padrão e quem ESCREVE exige `--staging` ou `--producao`
por extenso; valor de segredo nunca passa por argumento nem por stdout
(entra por arquivo ou é gerado, e o novo fica em
`~/.nutriplan-secrets/rotacao/`); e **`PUT` de variável pela API do Render
NÃO redeploya** — MEDIDO: o token novo respondia 403 até o deploy —, então o
script pede o redeploy em seguida, do commit LIVE em produção (sem
`commitId` o Render subiria a ponta de `main`: uma promoção escondida dentro
de uma rotação) e da ponta de `main` no staging.

Primeiro, sempre:

```bash
.venv/Scripts/python.exe scripts/incidente.py diagnostico            # produção
.venv/Scripts/python.exe scripts/incidente.py diagnostico --staging
```

Ele diz, nesta ordem, o que está de pé: `web` (`/saude/vivo/`, sem banco),
`banco` (`/saude/`), o último deploy do Render e a idade do último run de
cada fluxo do Actions. É a ordem em que se descobre onde dói.

**Banco caiu.** Sintoma: `/saude/vivo/` 200 e `/saude/` 503 ("healthcheck
sem banco" no log) — e o UptimeRobot NÃO avisa, porque bate no `vivo`. Na
ordem: (1) `https://neonstatus.com` (AWS us-west-2): incidente deles, o app
volta sozinho; (2) Neon → projeto → Branches → o compute da branch:
`suspended` que não acorda → *Restart*; (3) dado corrompido ou apagado há
menos de 6 h: Neon → branch → *Backup & Restore* → *Restore from history*
→ instante → *Restore*. É **no lugar** e no MESMO endpoint: a branch atual
vira `<nome>_old_<instante>` (o desfazer) e a restaurada assume a URL —
ENSAIADO no staging: 0,83 s, e o app continuou respondendo `/saude/` sem
redeploy nenhum; (4) mais velho que 6 h, ou outra branch/projeto: Neon →
*New Branch* a partir de um instante, ou `scripts/restaurar.sh` do backup
próprio num Postgres local e `pg_dump | pg_restore` para a branch nova
(`docs/infra-recuperacao.md`) — a URL nova vai para um ARQUIVO fora do
repositório e:

```bash
.venv/Scripts/python.exe scripts/incidente.py banco --trocar <arquivo-com-a-url> --producao
```

ENSAIADO no staging com a branch `staging-restaurada` (criada da `staging`
com dados): `PUT` + redeploy em 1 min 30, `/saude/` ok, e `pg_stat_activity`
mostrou a conexão do app na branch nova e nenhuma na antiga; a volta é o
mesmo comando com a URL de sempre. O Postgres do Render que era o rollback
some por volta de 23/09/2026; depois disso o caminho (4) é o Neon.

**Deploy quebrou.** `deploy` lista os últimos deploys com status e commit.
`build_failed`/`update_failed`: o deploy anterior continua no ar, nada a
desfazer — conserte em `main`, o staging prova, promova. Subiu e quebrou
(`live` com a tela errando):

```bash
.venv/Scripts/python.exe scripts/incidente.py deploy --voltar <sha-do-último-bom> --producao
```

Sem a prova do staging (ele está à frente), só para SHA que está em
`origin/main`, e SEM build quando o Render ainda tem a imagem daquele
deploy: `POST /services/<id>/rollback {deployId}` — MEDIDO no free: 201,
`trigger: rollback`, direto a `update_in_progress`. O rollback **não
devolve variável de ambiente**: ele sobe a imagem antiga com o ambiente de
AGORA (MEDIDO: um rollback logo depois de trocar `DATABASE_URL` subiu com a
URL nova). ENSAIADO no staging: `cb75ee3` ← `7cbaa44` → `7cbaa44`, ~1 min
30 cada, `/saude/` dizendo o commit.

**Segredo vazou.** Um verbo, e a tabela `ONDE_MAIS` do script diz onde mais
cada segredo mora:

```bash
.venv/Scripts/python.exe scripts/incidente.py rotacionar NUTRIPLAN_TAREFAS_TOKEN --producao   # gera, grava no Render, regrava o segredo do Actions
.venv/Scripts/python.exe scripts/incidente.py rotacionar DJANGO_SECRET_KEY --producao         # a antiga vai para DJANGO_SECRET_KEY_FALLBACKS
.venv/Scripts/python.exe scripts/incidente.py rotacionar --encerrar DJANGO_SECRET_KEY --producao   # 14 dias depois: a antiga deixa de valer
.venv/Scripts/python.exe scripts/incidente.py rotacionar EMAIL_HOST_PASSWORD --producao --de-arquivo <arquivo>   # o que vem de fora (Brevo, Google, VAPID)
```

Os três que o app gera (`DJANGO_SECRET_KEY`, `NUTRIPLAN_TAREFAS_TOKEN`,
`NUTRIPLAN_DISPARO_TOKEN`) nascem no script, 64 caracteres. A chave do
Django troca COM rede de segurança: a antiga entra em
`DJANGO_SECRET_KEY_FALLBACKS` ANTES da nova entrar (o Django aceita o que a
antiga assinou — sessão, CSRF, token de redefinição, `state` do OAuth — e
assina o novo com a nova; há teste), e a janela é a idade da sessão, 14
dias, ou 3 h se aceitar deslogar todo mundo. `NUTRIPLAN_DISPARO_TOKEN` novo
exige trocar a URL do monitor no UptimeRobot à mão. Dois não passam pelo
verbo: `DATABASE_URL` (Neon → Roles → reset password → `banco --trocar`) e
`RENDER_API_KEY` (Render → Account Settings → API Keys → o arquivo
`~/.nutriplan-secrets/render_api_key` e `scripts/github.py segredo
RENDER_API_KEY <arquivo>`). O token do Git Credential Manager se rotaciona
no GitHub (Settings → Developer settings) e o GCM pede de novo no próximo
push. ENSAIADO no staging: token das tarefas — o antigo 403, o novo 200
depois do redeploy; `DJANGO_SECRET_KEY` com fallback — build passou no
`check --deploy`, `/saude/` ok; `--encerrar` — `DELETE` da variável e
redeploy.

**Actions fora.** `actions` diz a idade do último run de cada fluxo e o que
`githubstatus.com` diz do componente Actions. Actions fora **não derruba
produção**: ela só muda por promoção, e promover e voltar rodam da máquina.
O que para, e o que fazer: o gate dos PRs não roda → `main` não recebe
merge — espere; a proteção de `main` não se desliga para passar hotfix, e
a resposta a produção quebrada é `deploy --voltar`; lembretes — quem
dispara é o UptimeRobot (o `schedule` do Actions é só o fallback), e uma
rodada agora, da máquina, é:

```bash
.venv/Scripts/python.exe scripts/incidente.py actions
.venv/Scripts/python.exe scripts/incidente.py lembretes            # POST /tarefas/lembretes/ com o token da máquina
```

A fila local (`scripts/github.py enfileirar`) fica esperando o check e
solta a posse sozinha em 90 min; `schedule` parado por 60 dias sem commit,
um commit qualquer religa. ENSAIADO: `lembretes --staging` → 200 com o JSON
da rodada.

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

**E o drill é MENSAL e AUTOMÁTICO desde 21/09/2026**
(`.github/workflows/restaurar-mensal.yml`, dia 1 às 06:00 de Brasília, e pelo
botão a qualquer hora). Ele despeja produção com `backup.sh`, restaura no
Postgres 18 do próprio job com `restaurar.sh` (`MANTER_BANCO=1` deixa o banco
de pé) e confere o restaurado contra a origem com
`scripts/conferir_restauracao.py`: toda tabela com a mesma contagem — salvo
1 % ou 5 linhas, o que for maior, porque a origem continua viva e quem
registra água às 6h do dia 1 não pode disparar alarme —, o mesmo conjunto de
`django_migrations` e gente dentro. Falhou, abre (ou comenta) a issue
"Restauração mensal falhou", além do e-mail do GitHub. Três decisões:

- o dump sai pelo role **`nutriplan_leitor`** (Neon, `pg_read_all_data`, sem
  CREATE; criado em 21/09 por `artifacts/criar_leitor.py`, senha só no
  arquivo `~/.nutriplan-secrets/backup_database_url` e no segredo
  `BACKUP_DATABASE_URL` do repositório) — se o segredo vazar, lê-se, não se
  destrói. Renovar a senha é rodar o mesmo script e `scripts/github.py
  segredo BACKUP_DATABASE_URL ~/.nutriplan-secrets/backup_database_url`;
- o dump **nunca vira artefato** do run: o repositório é público e o arquivo
  tem e-mail, peso e treino de gente real. Ele vive no `$RUNNER_TEMP` e
  morre com o job; o log só tem nome de tabela e contagem;
- o cliente é o `postgresql-client-18` do PGDG e o serviço é `postgres:18`,
  pelo `SET transaction_timeout` de sempre. Ensaiado na máquina em 21/09 com
  o mesmo role: 55 tabelas, 343 KB, `RESTORE OK` no cluster 18 local.

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
## Avisos por e-mail (21/09/2026)

**Três e-mails, um app (`avisos/`), e o relógio é o de sempre.** Boas-vindas
(uma vez por conta, no cadastro por senha E por Google — `avisos.services.
boas_vindas`, chamado em `SignupView.form_valid` e no `save_user` do adapter
social; quando a verificação de e-mail existir, é essa chamada que muda de
lugar), "5 dias sem treino" e o resumo da semana. Os dois últimos NÃO têm cron:
`avisos.jobs.rodar(now)` pega carona no fim de cada rodada NÃO pausada de
`push/tarefas.rodar()` (UptimeRobot a cada 5 min; o Neon dorme entre
rodadas), e saem a partir da `hora_email` da pessoa (padrão 08:00) — em até
meia hora depois, o preço da pausa. Idempotência pela constraint de
`EmailEnviado` (pessoa, tipo, referência), com a referência do TAMANHO
certo: `conta` para o boas-vindas, a data da última série para a inatividade
(**um e-mail por pausa**, não um por dia — treinar de novo abre outra), a
semana ISO para o resumo. Só quem tem ficha ativa e onboarding feito entra na
lista; semana vazia sai mesmo assim (o zero é convite). A preferência
(`avisos.Preferencia`, `/avisos/`, link no Perfil) tem três perguntas — quais
e-mails, quais pushes, a que horas — e **a linha que não existe vale LIGADO**;
`push/services.due_slots` respeita `push_refeicoes` por `exclude` do falso.
O descadastro é por link com chave própria de 128 bits (`/avisos/sair/<chave>/
?tipo=`), GET e POST sem login e sem CSRF (RFC 8058, cabeçalhos
`List-Unsubscribe` + `List-Unsubscribe-Post` em todo e-mail), e só DESLIGA.
Os templates moram em `templates/email/` (moldura NERVURA inline, em tabela:
cliente de e-mail não lê CSS nem `transform` — a nervura é uma régua reta de
2 px e a display cai em Arial Narrow/Impact), e a pasta inteira está fora da
régua de `style=` de `config/test_design_system.py`, como o `email_senha`.
Os links dos jobs saem de `NUTRIPLAN_URL_BASE` (não há request). O envio
nunca derruba quem chamou: falha de SMTP vira `sucesso=False` no log.

**PROVADO NO STAGING COM CAIXA PÚBLICA (21/09/2026, tarde) — e duas coisas
que a prova achou.** Conta de QA criada pelo ORM no banco do staging (zero
dado real; sem senha, `set_unusable_password`; e-mail numa caixa pública
`@maildrop.cc`, legível sem conta), `POST /tarefas/lembretes/` com o token
do staging: os dois e-mails do relógio CHEGARAM pelo Brevo — "6 dias sem
treino" e "Sua semana: 1 treino, 6 séries" — com parte HTML e texto,
`List-Unsubscribe` + One-Click, e o link do rodapé desligou só a
preferência dele sem login (chave errada → 404); Perfil › Avisos gravou;
o placar gerou o PNG 1080×1350 sem peso/nome/e-mail; a conta foi apagada
pela tela (`EXCLUIR`, o caminho de quem não tem senha) e a sessão morreu.
O que a prova achou: (1) o job escrevia para `carlos.demo@nutriplan.invalid`
— o demo tem ficha ativa e onboarding feito, e `.invalid` nunca entrega —,
então `_candidatos` exclui `TLD_QUE_NAO_ENTREGA` (é também a convenção da
conta de QA); (2) o staging montava os links com a raiz de PRODUÇÃO
(`NUTRIPLAN_URL_BASE` só existia no default), e o descadastro apontava para
uma chave que só existe no banco do staging — `render.yaml` passou a
**QUEM RECEBE: caixa em que o Brevo não desistiu e — nos e-mails do
relógio — caixa PROVADA (21/09/2026, noite).** O Brevo mostrou o dia da
primeira rodada: 58 enviados, 46,6 % de HARD bounce (cadastro com gmail
inventado) e 32,8 % soft (`.invalid`). Reputação de remetente se perde
assim, e o Brevo suspende conta por isso. `avisos.brevo` copia por API —
SÓ GET, por construção, como `render_api.py` — quem bloqueou
(`GET /v3/smtp/blockedContacts` → `EmailBloqueado`: hard bounce, spam,
bloqueio) e quem ABRIU algum e-mail nosso (`GET /v3/smtp/statistics/events
?event=opened` → `EmailAberto`, a primeira abertura); roda no build
(`manage.py sincronizar_brevo`) e a cada 12 h por processo dentro da rodada
de e-mails. `enviar()` é a porta única e "pula" SEM gravar linha, nesta
ordem: `.invalid` → bloqueado → (com `exige_verificacao`) caixa nunca
provada. O boas-vindas passa `exige_verificacao=False`: é o primeiro
contato, o e-mail cuja abertura É a prova — exigir prova antes dele seria
nunca mandá-lo; inatividade e resumo exigem. `verificado()` olha primeiro o
campo da verificação de cadastro — `email_verificado_em` no usuário, o
nome combinado com a sessão de segurança pelo ledger, que ainda não
existe — e depois a tabela. A chave é `BREVO_API_KEY` (API v3, OUTRA que a
SMTP): sem ela nada sincroniza, e a consequência está escrita: até a chave
entrar no painel, `EmailAberto` fica vazia e os e-mails do relógio não saem
para ninguém — que é o estado seguro enquanto o cadastro aceita e-mail
inventado.

**A PRIMEIRA RODADA NUNCA É EM MASSA (21/09/2026, noite).** A de produção
foi: às 13:35 o job de inatividade escreveu de uma vez para toda conta
dormente com ficha ativa — "27 dias sem treino" para quem nunca mais abriu
o app —, e foi daí que veio o dia de 46,6 % de hard bounce. Duas guardas em
`rodar_inatividade`: a pausa tem de ter COMEÇADO a partir de
`NUTRIPLAN_AVISOS_INATIVIDADE_DESDE` (o dia em que o aviso foi ligado
NAQUELE ambiente; produção 21/09/2026; vazia ou ilegível vale HOJE, nunca
"tudo") — quem parou antes de o aviso existir não é cobrado por um aviso
que não existia —, e `TETO_POR_RODADA` (20) por tipo por rodada, também no
resumo semanal: o resto sai nas rodadas seguintes, de 5 em 5 min, e a
resposta do job diz quantos ficaram (`adiados`). Provado no staging com dez
contas dormentes de antes da data: zero e-mails; a pausa começada depois
recebe (`avisos/tests.py`, `PrimeiraRodadaTests`).

declará-la no bloco do staging. O que a prova NÃO cobre: o boas-vindas sai
só pelo signup, e a sessão não cria conta por formulário nem digita senha;
o remetente aparece como `…@12016072.brevosend.com` porque o domínio de
`DEFAULT_FROM_EMAIL` não está autenticado no Brevo — é configuração da
conta do dono, não código.

