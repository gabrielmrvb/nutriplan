# Auditoria 100 % em produção — 20/09/2026 (domingo)

Produção `dc971a0` (`/saude/` 200, catálogo 69/69), depois das ondas NERVURA,
ficha única/equipamento, dieta e lembretes. Auditoria como usuário REAL, do
zero: quatro contas descartáveis criadas pelo signup público
(`qa-audit-…`, `qa-medir-…`, `qa-lat-…` e a local `qa-semana-…`), cada uma
apagada pela tela ao fim com login recusado provado; demo intacto; nunca a
conta do dono. Navegador: `scripts/qa/nav.py` em processo (Chrome 153
instalado — o do agent-browser está bloqueado pelo Smart App Control desde
20/09), 390 e 1280 px, Ferro e Papel, teclado emulado (viewport 390 × 450),
3G emulado. Capturas citadas em `achados/capturas-20260920/`; o conjunto
completo (≈ 300 PNG) fica no scratchpad da sessão.

Vocabulário: evidência `[EXECUTADA]` (roteiro rodou e mediu) ·
`[OBSERVADA]` (vi na captura) · `[LIDA NO CÓDIGO]` · `[HIPOTÉTICA]`.
Classe: BUG · UX REAL · OBSERVAÇÃO · FALSO POSITIVO · LIMITAÇÃO.
Gravidade: **bloqueia** / **atrapalha** / **feio** / **ideia**.
`PROVADO EM PRODUÇÃO` ≠ `PROVADO LOCAL` (a semana simulada é local: a data
de produção não congela).

## Cobertura

| o quê | quanto |
|---|---|
| telas medidas em produção (4 regimes cada: Ferro/Papel × 390/1280) | 51 telas / 381 medições |
| foco por Tab de verdade (Input.dispatchKeyEvent) | 13 telas, 128 paradas, **0 sem anel, 0 invisíveis** |
| contraste texto × fundo efetivo (composição alfa, pseudo que cobre, irmão absoluto; controle positivo 21:1) | **0 reprovados** em todas as telas depois de tirar os artefatos da régua |
| alvos de toque < 44 × 44 em controle | **0** (só link no meio de parágrafo em Privacidade/Termos: 17 px de altura — texto corrido, isento) |
| texto < 11 px | **0** |
| rolagem horizontal | **0** telas |
| teclado aberto (390 × 450) | campo focado sempre visível acima da barra de abas (medido em Progresso, Lista, Corrida, Senha; a 1ª leitura do roteiro deu falso positivo por selector) |
| PWA | manifesto 200 (`standalone`, 192/512 `any` + `maskable`), SW ativo com 38 itens em cache, `update()` ok, Home OFFLINE servida do cache com a faixa "desatualizada" pronta |
| semana simulada (local, data congelada por dia, seg 21/09 → seg 28/09) | 8 dias, 105 séries registradas, 1 corrida, 2 pesagens, 16 refeições, 7 registros de água |
| demo × app logado | 9 rotas comparadas por títulos/seções/botões |

## Achados

Formato: `rota · passo · o que aconteceu · o que devia · captura · gravidade`. Um por linha.

### bloqueia

- (nenhum) — nenhum fluxo do primeiro uso trava: cadastro → 3 etapas → Home → 5 áreas → conta apagada, em produção, sem erro 5xx e sem beco sem saída. `[EXECUTADA]`

### atrapalha

- `/conta/entrar/` · POST com senha errada · **4,4–5,6 s** de TTFB (3 medições sem conta + 1 com conta existente); login CERTO 3,0–3,2 s (2 medições); cadastro 3,7 s · < 1 s · `entrar-erro-papel-390.png` · atrapalha · BUG (perf) `[EXECUTADA em produção]`. Causa `[LIDA NO CÓDIGO]`: PBKDF2-SHA256 com 1 000 000 iterações (padrão do Django 5.2) = 0,56 s nesta máquina e ≈ 3 s na CPU do Render free; com DOIS backends (`ModelBackend` + allauth) a senha errada paga o hash duas vezes.
- `/treino/` · domingo/sábado (depois do último dia de treino da semana) · a faixa SEG–DOM e os cartões dizem "A · Segunda-feira", enquanto o cartão "Próximo treino" diz "C · amanhã" — a rotação já mudou a letra de segunda e a tela mostra a semana que ACABOU · a semana desenhada tem de ser a mesma do "próximo treino" · `treino-painel-papel-390.png` (produção, domingo) e `2026-09-26-treino-ferro-390.png` / `2026-09-28-treino-ferro-390.png` (local: sábado diz "A segunda", segunda mostra C) · atrapalha · BUG `[EXECUTADA]`
- `/treino/` · "Treino de hoje" depois de fechar a sessão · "**42** minutos estimado" ao lado do cartão da MESMA sessão dizendo "**~59** min" (7 exercícios, 25 séries) · um número só (`workouts.models.segundos_da_sessao` é "a conta única", CLAUDE.md) · `2026-09-21-treino-ferro-390.png` · atrapalha · BUG `[EXECUTADA local]`. Causa `[LIDA NO CÓDIGO]`: `workouts/health_export.py::_duracao_estimada` é uma SEGUNDA fórmula (série × 45 s + descanso médio).
- `/treino/agora/` (e toda página) · dia seguinte ao primeiro treino · o aviso "🏆 CONQUISTA DESBLOQUEADA — Primeiro treino" volta em TODA página enquanto "Continuar" não é tocado (fica na sessão) e, na execução, **cobre o campo Reps e o botão CONCLUIR SÉRIE** (toast em y=576, CTA em 645–699 num viewport de 844) · avisar uma vez onde nasce e sair sozinho; nunca por cima da ação principal · `2026-09-22-execucao-toast-ferro-390.png` · atrapalha · UX REAL `[EXECUTADA local; em produção não reproduzível hoje — domingo sem treino]`
- `/conta/onboarding/3/` · "Criar meu plano" · 3,1 s até a Home (monta os dois planos), sem indicador além do `aria-busy` do botão · feedback de progresso ("montando seu cardápio…") · — · atrapalha · UX REAL `[EXECUTADA em produção]`

### feio

- `/treino/` · resumo do treino em andamento, a ≥ 26 rem (desktop/tablet) · o primário "COMPARTILHAR O QUE JÁ FIZ" quebra no meio da palavra ("COMPARTILHA / R O QUE JÁ FIZ") no grid de 2 colunas; a 390 fica inteiro numa linha · botão nunca quebra palavra (primário em linha própria no grid, como já é a 390) · `demo-treino-1280.png` · feio · UX REAL `[OBSERVADA no /demo/treino/ e medida: botão 195 × 80 px]`
- `/historico/` · campo "Peso" · pré-preenchido com "89,20" (duas casas) enquanto todo número de peso na tela tem uma ("89,6 kg", "90,0 kg") · uma casa decimal em todo lugar · `2026-09-27-progresso-papel-390.png` · feio · UX REAL `[OBSERVADA]`
- `/` · primeiro uso · a Home tem **3 757 px** de altura a 390: todas as refeições ainda não marcadas vêm ABERTAS com quatro botões cada (Registrar A / Registrar B / Pulei / Comi outra coisa), e a água aparece duas vezes (linha "0 de 3000 ml" sob os macros + o cartão de hidratação) · uma refeição aberta por vez (a da vez), as outras em uma linha; água uma vez · `home-primeiro-uso-ferro-390.png` · feio · UX REAL `[EXECUTADA: altura medida]`
- `/` (todas) · 1280 px · o app é a coluna do celular centralizada (≈ 440 px úteis; ≈ 800 px vazios de cada lado) — coerente, mas o desktop não aproveita nada · decisão de produto (ver Fase 3) · `home-ferro-1280.png` · feio · OBSERVAÇÃO `[OBSERVADA]`
- `/treino/` e `/treino/ficha/<id>/` · qualquer dia · "Instale o NutriPlan" (cartão fixo) + aviso de conquista (fixo) + barra de abas (fixa) podem se empilhar no rodapé: três camadas fixas na mesma borda · um flutuante por vez · `2026-09-24-execucao-ferro-390.png` · feio · UX REAL `[OBSERVADA]`

### ideia (o que a semana simulada mostrou e a tela não conta)

- `/` · dia 4 (depois de treino completo dia 1, 2 refeições/5, 1 L de água; dia 2 3/5 + 0,5 L + treino parcial) · ofensiva "**0 dias — Comece hoje**" — e continua 0 no dia 7 mesmo com 4 refeições de 5, 1,5 L e treino fechado: a régua pede 80 % das refeições **e** 90 % da água (2,7 L de 3 L) **e** o treino, todos no mesmo dia · a ofensiva tem de ser alcançável por quem usa o app de verdade (ver Fase 3: água domina) · `2026-09-27-home-papel-390.png` · ideia · UX REAL `[EXECUTADA local; regra LIDA NO CÓDIGO em plans/streaks.py]`
- `/treino/agora/` · quinta (2ª vez da letra A) · nenhum "última vez", carga vazia, sem SUBIR: a opção 2 da letra tem exercícios DIFERENTES da opção 1 (seg: supino reto c/ barra, supino na máquina, crucifixo c/ halteres…; qui: supino inclinado c/ halteres, crucifixo na máquina, crossover…), então um exercício só repete de 2 em 2 semanas — a adaptação de carga (T2.1/T2.3) e o "recorde" só têm o que dizer a partir da 3ª semana; Conquistas mostra "0 recordes" depois de uma semana com carga subindo · a alternância de opções é decisão de produto; o custo dela na progressão não está escrito em lugar nenhum da tela · `2026-09-24-execucao-ferro-390.png` · ideia · OBSERVAÇÃO `[EXECUTADA local; conferido no banco: 0 exercícios em comum entre 21/09 e 24/09]`
- `/historico/`, `/lista-de-compras/`, `/treino/corridas/nova/` · teclado aberto · a barra de abas continua fixa e ocupa 68 dos ≈ 450 px que sobram com o teclado (medido) · esconder a barra enquanto um campo tem foco (padrão de mercado) · `teclado-historico.png` · ideia · UX REAL `[EXECUTADA: emulação]`
- `/conta/onboarding/3/` · "Criar meu plano" · o botão é enviado por `fetch`; um toque duplo rápido manda dois POST (o roteiro fez isso sem querer: dois `POST /conta/onboarding/3/` seguidos) · desabilitar no primeiro toque · — · ideia · OBSERVAÇÃO `[EXECUTADA local; sem efeito visível — os dois planos saem iguais]`
- `/privacidade/`, `/termos/` · 7 491 e 4 295 px de altura a 390; links no texto com 17 px de altura · sumário no topo; links com `padding` vertical · `—` · ideia · OBSERVAÇÃO

### FALSO POSITIVO (da régua, registrados para ninguém refazer)

- contraste 1,1–1,9:1 em `.option__name`, `.fora__rotulo`, `.option__how` (Home, onboarding 3): texto dentro de `<details>` FECHADO guarda a cor computada do tema anterior no Chrome 153 — não está na tela. Régua corrigida (ignora conteúdo de details fechado).
- contraste 1,13:1 em `.btn--primary` e em `.segmented__texto` selecionado: o fundo é um `::before` com `inset: 0` (botão) ou um irmão absoluto `.segmented__fundo` (segmented), não um ancestral. Régua corrigida.
- contraste 1,59:1 no `h1` de Privacidade/Termos: a nervura (`::after` de 2 px) atrás do título não é fundo. Régua corrigida.
- "texto em 5 linhas" em `label.choice-card` e "ver vídeo" em 4 linhas: cartão com filhos em bloco e botão que cobre a mídia — não é texto corrido.
- `/treino/corridas/nova/` "distância 'abc' aceita": o erro estava em `.field__errors li`, que o seletor do roteiro não lia. Reconferido: "Use números, como 5,2." aparece.
- `/conta/cadastro/` "sem erro ao enviar vazio": `required` nativo segura o envio; e no servidor os quatro "Este campo é obrigatório." aparecem.
- `/treino/ficha/<id>/` "sem porta para a execução": domingo — a ficha de OUTRO dia não executa, por regra.
- `/lista-de-compras/` TTFB 2,8 s: uma vez; três medições seguintes 0,40–0,45 s (o Neon acordando ou o primeiro cálculo).

## Medições

### Tempo por rota (produção, Wi-Fi da mesa, primeira visita da conta; ms)

| rota | TTFB | interativo | load | HTML (bytes na rede) | altura a 390 |
|---|---:|---:|---:|---:|---:|
| `/conta/entrar/` | 392 | 849 | 1 236 | 3 792 | 844 |
| `/conta/cadastro/` | 249 | 260 | 275 | 10 960 | 1 033 |
| `/conta/onboarding/1/` | 302 | 333 | 339 | 4 079 | 944 |
| `/conta/onboarding/2/` | 788 | 814 | 826 | 30 442 | 2 072 |
| `/conta/onboarding/3/` | 867 | 908 | 913 | 28 661 | 2 444 |
| `/` (Hoje) | 686–967 | 704–991 | 779–1 008 | **78 198** | **3 757** |
| `/areas/` | 478 | 530 | 538 | 12 001 | 844 |
| `/hidratacao/` | 307 | 347 | 367 | 19 306 | 2 106 |
| `/historico/` | 477 | 508 | 519 | 16 961 | 2 122 |
| `/lista-de-compras/` | 402–445 (2 837 uma vez) | 430 | 446 | 34 928 | 4 425 |
| `/conquistas/` | 352 | 403 | 410 | 13 201 | 1 317 |
| `/treino/` | 344–581 | 383–589 | 389–594 | 30 175 | 1 354 |
| `/treino/ficha/<id>/` | 311–481 | 339–511 | 352–520 | 13 514–16 570 | 929–1 209 |
| `/treino/exercicio/<id>/` | 399–722 | 429–747 | 634–847 | 19 994–20 963 | 1 553–1 759 |
| `/treino/corridas/` | 292–402 | 304–430 | 310–918 | 12 587 | 982 |
| `/treino/corridas/nova/` | 269 | 288 | 296 | 12 851 | 1 151 |
| `/treino/corridas/plano/` | 267 | 295 | 302 | 13 132 | 1 132 |
| `/conta/perfil/` | 335–447 | 367–475 | 373–480 | 17 274 | 3 158 |
| `/conta/senha/trocar/` | 380 | 408 | 414 | 13 745 | 1 051 |
| `/conta/excluir/` | 304 | 327 | 333 | 9 923 | 844 |
| `/privacidade/` | 338 | 356 | 363 | 17 445 | 7 491 |
| `/termos/` | 435 | 477 | 484 | 12 475 | 4 295 |
| `/demo/` | 277 | 293 | 566 | 16 135 | 1 896 |
| 404 | 251 | 267 | 271 | 7 211 | 844 |

POST: cadastro **3,71 s** · etapa 1 1,56 s · etapa 2 1,56 s · etapa 3 ("Criar meu plano") **3,08 s** · login certo **3,0–3,2 s** · senha errada **4,4–5,6 s**.

3G emulado (400 ms/400 kbps): `/` load 645 ms, `/treino/` 355, `/historico/` 430, `/treino/agora/` 404 — o HTML é pequeno o bastante para o 3G não doer; o que dói é o hash da senha.

### Foco por Tab (390, Ferro)

Ordem sempre: marca "NutriPlan" → conteúdo → barra de abas; anel `--brand` visível em 100 % das paradas. Paradas: entrar 7 · cadastro 6 · senha 6 · onboarding 1 3 · Home 11 · Áreas 10 · Hidratação 14 · Progresso 14 · Lista 4 · Conquistas 10 · Treino 13 · Corridas 5. Sem link "pular para o conteúdo" (observação, não achado).

### A semana simulada (local, data congelada por dia, hora real)

| dia | o que fiz | o que a tela disse |
|---|---|---|
| seg 21/09 | cadastro, onboarding, 2 refeições, 1 L, pesei 90, treino A completo (25 séries) | AGORA "Almoço 14:30"; recompensa "PEITO E TRÍCEPS FECHADO · 5 000 kg · 25 séries"; toast "Primeiro treino" |
| ter 22/09 | 3 refeições, 0,5 L, treino B parcial (5 séries) | toast ainda em TODA página e cobrindo o CTA da execução; "Continuar" resolve; painel "22 % do treino · 2 de 9 exercícios" |
| qua 23/09 | nada | painel: C "Pernas e ombros" é hoje; nada cobra o dia anterior parcial |
| qui 24/09 | corrida 5,2 km/28:10, 3 refeições, 0,5 L, treino A (opção 2) completo a 22,5 kg | execução SEM "última vez" (exercícios diferentes da 2ª); Home "+419 kcal da corrida"; ofensiva 0 |
| sex 25/09 | 4 refeições, 1,5 L, treino B (opção 2) completo | "7 de 7 exercícios com série" no dia anterior; recompensa 4 800 kg |
| sáb 26/09 | 2 refeições | "DIA DE DESCANSO … PRÓXIMO TREINO C · segunda" com os cartões dizendo "A · Segunda-feira" |
| dom 27/09 | pesei 89,2 | Progresso: 56 % aderência, 1 262 kcal/dia (meta 2 281), 5 dias com registro, 2 pesagens → 89,6 kg, treino 4 dias, água média 875 ml; Conquistas "1 conquista · 4 dias de treino · **0 recordes**"; ofensiva 0 |
| seg 28/09 | abri | painel: C · "Segunda-feira · Quinta-feira" — a rotação continuou (certo); execução do Leg press sem histórico (1ª vez) |

### Demo × app logado

Mesmas rotas, mesmos títulos e seções; o que o demo tem a mais é DADO (dias de histórico, conquistas, "Compartilhar", "Exportar para o Saúde") e a capa de marketing (`/demo/`: "Quem está usando", "As telas do aplicativo"). **Nenhuma funcionalidade prometida pelo demo falta no app**, e nada do app falta no demo. A capa não tem formulário (só GET). `[EXECUTADA]`

### O que NÃO é achado (medido limpo)

Contraste (todas as telas, 4 regimes) · alvos de toque · texto ≥ 11 px · rolagem horizontal · foco por Tab · títulos "… · NutriPlan" em toda página · 404 com a cara do app · erros de formulário por campo (login, cadastro, corrida) · exportação de dados (JSON como anexo) e TCX (302 com aviso quando não há treino) · manifesto/SW/offline · "Lembretes" na Home (VAPID ativo) · os 4 equipamentos no Perfil remontam a ficha na hora e sem "regenerar?" (completa 7 ex., básica, casa c/ halteres, só peso do corpo) · exclusão de conta pela tela apaga de verdade (login recusado 4×).
