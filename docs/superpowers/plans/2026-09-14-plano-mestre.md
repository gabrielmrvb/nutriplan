# Plano mestre — UX × Treino × Design, em ondas publicáveis

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline, com checkpoints) sob o protocolo `nutriplan-missao`. Steps use
> checkbox (`- [ ]`) syntax for tracking. Subagente só em tarefa de arquivos
> disjuntos; `workouts/services.py`, `workouts/views.py`,
> `templates/workouts/agora.html`, `templates/plans/today.html`,
> `static/js/pwa.js`, `static/js/fila.js` e `static/css/app.css` são
> SERIALIZADOS — nunca dois subagentes ao mesmo tempo neles.

**Goal:** Integrar os três briefs de 13-14/09/2026 (UX, Treino, Design) num
único caminho de execução em que cada onda termina publicada: primeiro o app
para de mentir e de perder toque (onda 1), depois o treino diz a verdade e se
adapta como LEITURA pura (onda 2), depois tudo o que é comportamento e copy
que não depende de pele (onda 2b), e só então — atrás de UMA decisão do dono
— a fundação de design (onda 3), a experiência tela a tela (onda 4), o motor
em três camadas (onda 5) e o polimento (onda 6).

**Architecture:** Django 5.2, templates servidos, `app.css` único, JS sem
build (`pwa.js`/`fila.js`/`sw.js`). Ondas 0, 1, 2 e 2b: **zero migration**.
Onda 5: migrations **só `AddField`**, `UPDATE = 0` provado sobre banco
populado, ficha de todo mundo byte a byte igual até a última sub-onda. Toda
regra nova de treino é função pura em módulo sem `django.db`
(`workouts/adaptacao.py`, `workouts/parametros.py`, `workouts/ambientes.py`).
Toda classe de estado é escrita pelo servidor (nunca `:has()`), todo
parâmetro de retorno é lista fechada (nunca `next` livre), toda catraca de
valor cru só desce.

**Tech Stack:** Django 5.2.17 · PostgreSQL (portátil, `pg_ctl start` antes
de tudo) · agent-browser 0.37.1 (QA, sessão própria, saída em arquivo) ·
Render (deploy por `git push`, `scripts/build.sh`) · Neon (banco).

**Spec:** os três briefs (ver §1), os dois pareceres dos céticos (respondidos
em §0), os REQUISITOS A e as PREFERÊNCIAS FECHADAS do dono (transcritos em
Global Constraints).

## Global Constraints

- **Requisitos A (decididos; nunca perguntar de novo):** mobile-first; Home
  de Treino com cards A/B/C sem lista gigante; "Começar treino" leva à
  FICHA; cada exercício da ficha é clicável e mostra a execução sem
  registrar/iniciar/alterar nada; vídeos curados reaproveitados, associação
  por nome validado; vídeo na execução; abrir/fechar vídeo não perde estado;
  histórico preservado; motor sem "4x10 universal"; frequência não duplica
  volume; prescrição individualizada por objetivo/experiência/
  disponibilidade/histórico/evidência; determinística e testável, sem IA
  generativa decidindo.
- **Preferências fechadas:** RIR/RPE interno, linguagem simples, sem
  formulário por série, pergunta só quando melhora a decisão; equipamento em
  três camadas (motor entende / exercício disponível / vídeo validado), sem
  travar por 9 vídeos; barra de 4 itens e Perfil em Áreas; autonomia técnica
  para o reversível e de baixo risco.
- **Classes:** A requisito decidido; B evidência forte (autonomia); C decisão
  genuína de produto (só estas sobem ao dono); D refutado/decidido contra;
  E lacuna real (declarada). Problema evidente de clique, navegação,
  acessibilidade, consistência ou comportamento incorreto NUNCA é C.
- **Regra de ouro do CLAUDE.md:** decisão medida só se revê com medição nova,
  citando o parágrafo. Migrations aditivas, sem UPDATE em massa, sem apagar
  histórico. Nada de `:has()`. Alvo 44×44. Catracas de valores crus só descem.
- **Já feito — descrever como existe, não replanejar:** `be83b03..9430f78`
  (13-14/09/2026, `origin/main`): instrução de esforço
  (`workouts.models.instrucao_de_esforco`), pastilha carga × reps + "última
  vez", foco preservado após concluir/desfazer, recorde na hora, Progresso
  sem arredondar, peso do corpo sem carga, notas verdadeiras, POSTER de 96 px
  com player no toque (`_demonstracao.html`, decisão d406fe0), rota de
  leitura `/treino/exercicio/<id>/` com nome clicável em qualquer dia, dupla
  progressão (`services.proxima_carga`, degrau ABSOLUTO 2,5/5 kg, sessão
  incompleta ⇒ `None` — decisão do dono em 13/09), "Como fui" (oito sessões
  CRUAS, `CONSULTAS_DA_LEITURA = 8`). Suíte 2873 verde, deploy provado.
- **Orçamentos que não sobem:** `CONSULTAS_DA_EXECUCAO = 20`,
  `CONSULTAS_DA_LEITURA = 8`, ficha ≤ 15, painel ≤ 25, Progresso ≤ 26,
  Home 15/25 (medidos, ver os testes que os prendem). Subir qualquer um
  exige medição escrita no commit.
- **Larguras de QA:** 320 / 375 / 390 / 430 / 1024, em toda tela tocada, nos
  dois temas a partir da onda 3. A dobra do CTA "Concluir série" continua
  medida também em **360×800** (régua de d406fe0/30/08): qualquer item que
  some linha acima do CTA mede y ANTES e DEPOIS.
- **Higiene:** conta de QA local (`qa-redesign-treino@local.invalid`,
  pk 1176), dados restaurados ao fim; demo pública intocada; `git add` por
  caminho; `artifacts/` (317 MB) fora do commit; `.agents/` e `AGENTS.md`
  não são deste plano — não commitar sem o dono.
- **Cadeia por onda (o gate):** testes dirigidos → sabotagem com controle
  positivo → QA agent-browser nas 5 larguras → suíte completa → `check
  --deploy` → `makemigrations --check` → `git diff --check` → commit por
  unidade → push pelo `pre-push` → deploy provado por sinal observável →
  `/saude/` → smoke. Notificação sonora ao fechar cada onda e ao precisar
  do dono.

---

## Estado de execução — 15/09/2026

**Ondas 0 e 1 CONCLUÍDAS** (22 commits sobre `9430f78` contando este, 5 pushes; cada push
provado em produção por sinal observável, `/saude/` e smoke). Suíte: 2873
→ 2960+ testes. Registro das sabotagens em `scratchpad/sabotagem_onda1.txt`
da sessão (T1.1–T1.18, cada uma vermelha e restaurada).

- `3e497b7` Onda 0: os três briefs, o plano mestre e a régua visual entram no repositório
- `377a444` Onboarding: a ficha nasce no Concluir, e zero dias desliga a rotina
- `1cf3f15` Treino: um verbo, um destino — "Começar" abre a ficha, "Continuar" abre a execução
- `b7ecedb` Home: o relógio da tela vira costura, e dois testes param de depender da hora
- `a6b13a5` Execução: exercício concluído é um estado, não "Série None de 4"
- `7231d08` Execução: "Concluir série" gruda acima da tabbar — e o sticky volta a funcionar no app inteiro
- `93506f0` Treino: a tela pergunta ao exercício, e não ao campo — e dois comentários param de envelhecer
- `f17aaa4` Lista de compras: a quantidade não repete o nome, e mora dentro do rótulo
- `70a7ee1` Água: zerar não empurra o número para duas linhas, e nenhum par de alvos se toca
- `99109c3` Lembretes e GPS: permissão negada é um estado que a tela mostra — e não apaga 0,1 ms depois
- `d3777e9` Compartilhar: a imagem não diz "concluído" com 4 de 16 séries
- `6698d4a` Progresso: a família do peso vira `.pesagem`, e as barras de treino e água voltam a 32 px
- `576f71e` Lista: "entrou na lista" tem flash e pousa no item; toda âncora respeita a barra de cima
- `c1e518e` Entrada: a vinheta cai de 55 % para 12 %, e o rodapé volta a ler a 4,5:1
- `105b06a` Hoje: a segunda classe de opções tocáveis também congela o relógio
- `0cd8fa8` Convite de instalação: só depois de entrar e da primeira ação — e tocar fora não dispensa
- `c1ac4ac` Leitura do exercício: volta para onde a pessoa veio; a linha da ficha inteira é a porta
- `56ed401` Execução: reps fora de 1..100 são recusadas; fechar e desfazer falam; desfazer de outro pede o segundo toque
- `8a09c36` Execução e leitura: um player por página — "Músculos trabalhados" é texto, sem vídeo de terceiro
- `f3283d0` Três avisos que faltavam: sessão vencida, alimento não reconhecido, peso com o número
- `a17e7b2` Offline: o toque aparece na tela na hora — água, refeição e série

**Desvios do plano, com o motivo:**

- **T1.15** — o brief pedia "200 com o valor preservado"; a convenção de
  `ConcluirSerieView` é PRG com mensagem (é o que a carga inválida já faz),
  e o HTML ganhou `pattern` para o navegador barrar antes de enviar. Orçamento
  do POST 16 → 17 com medição escrita (`series_de_hoje` em uma consulta).
- **T1.18 / UXA-06** — a faixa fixa "Peso de hoje · Corrigir" na Home foi
  RECUSADA: fere a decisão medida da dobra (740/776,
  `ConvitePesagemNoPainelTests`: "estado ocupado sem ação pendente é espaço da
  dobra gasto"). O eco mora na mensagem ("Peso registrado: 82,50 kg."), e
  corrigir continua em Progresso. **PA-03** (histórico cresce a cada água)
  fica em E: exige envio sem navegação, que é o caminho online de `fila.js`.
- **T1.5** — `FOLGA_*` não foram removidos: são o registro de uma medição
  citado por `_teto_em_segundos` e por um teste.
- **T1.2** — achado fora do brief: treino SEM HORÁRIO (toda conta nova desde
  10/09) nunca chegava ao cartão AGORA; ramo 2-D com cinco testes.
- **T1.4** — achado fora do brief: `overflow-x: hidden` no `body` quebrava
  TODO `position: sticky` (a `.app-bar` nunca grudou). Saiu, com teste.
- **T1.12** — 15 % deixava `--text-mute` em 4,39:1 na borda; a vinheta ficou
  em 12 % (4,66), com o teto de 15 % guardado como intenção.
- **Relógio** — dois lotes foram rejeitados pelo `pre-push` por testes que
  liam a hora da máquina (`plans/test_opcoes_tocaveis.py`, o meu
  `test_verbos_do_treino`); nasceu a costura `plans.views.relogio` e os
  testes congelam a hora.
- **agent-browser** continua bloqueado pelo Controle de Aplicativo do
  Windows; `scripts/qa/nav.py` (CDP) fez todo o QA, com `permissao` e
  `offline` acrescentados nesta onda.

**C-ONB EXECUTADA FORA DE ORDEM (15/09/2026)** — o dono pausou a onda 2
antes de T2.1 começar (nada iniciado, nada a preservar) porque a produção
ainda mostrava "Passo 1/6 · 16%". O plano de execução está em
`2026-09-15-onboarding-tres-etapas.md`; T4.8 fica satisfeita por ele e não
volta a existir na onda 4. Resumo: três rotas reais (1 Sobre você · 2 Seu
objetivo e rotina · 3 Sua personalização), etapas 2 e 3 compostas dos cinco
`ModelForm` antigos (`EtapaCompostaView`), divisão progressiva a partir de
`MINIMO_DE_DIAS_PARA_DIVISAO`, "Criar meu plano" montando cardápio E ficha,
`0032` remapeando quem estava no meio, `ONBOARDING_DONE = 7` intacto. A
revisão adversarial achou um BUG real que nenhum teste media — a edição da
divisão remontava a ficha lendo `user.profile` em cache, com a preferência
velha — e ele foi coberto e corrigido antes do push. Sabotagens (7, todas
vermelhas) em `scratchpad/sabotagem_onb.txt`.

**Onda 2 — retomada em 15/09/2026 com a missão "Variações intercambiáveis
de treino" incorporada como primeiro lote** (plano em
`2026-09-15-variacoes-de-treino.md`, push `9e45a78`, provado em produção):
uma letra, até N opções equivalentes, `EscolhaDeTreino`, versão rápida,
painel por letra. Entre a C-ONB e a onda 2 entrou também a missão de Motion
Design (`2026-09-15-motion.md`, push `37fdc14`).

**Próxima:** onda 2, T2.1 (`workouts/adaptacao.py`) em diante.

---

## 0. Correções dos céticos — o que entrou e o que não

**Aplicadas (cético 1):**

1. **C-RESET saiu das decisões** → §5 como D com condição de reabertura
   escrita. Contrariava a decisão do dono de 13/09 ("DESCER fica fora"), a
   mesma que o plano usava para classificar `AD-descer-por-reps` como D.
   A v1 (RETOMAR/ESTAGNADO só falam e suspendem SUBIR) fica B na onda 2.
2. **C-SOBRA virou E**: a preferência fechada já responde (A); o que falta é
   o NÚMERO de `medir_progressao`. Só vira C se cruzar o gatilho (§5).
3. **C-EQ virou B** (5c é B): sessão de 1-2 exercícios fere o piso do
   próprio veredito (comportamento incorreto nunca é C), e "preferência que
   cede, cede EM VOZ ALTA" já dá o caminho ABCDE→ABCD/ABC2 por
   `divisao_explicada`. A pergunta residual ("preset não suportado aparece
   riscado com a razão ou some?") é reversível e de baixo risco: decidida
   com autonomia — **riscado, com a razão lida de `Veredito.sem_substituto`**,
   porque sumir esconde o que falta e o que se está fazendo para destravar.
   E a nota do cético vale: presets aparecem JÁ, sem esperar nove vídeos.
4. **Onda 2, item 1, dividido**: (a) B — `workouts/adaptacao.py` puro,
   `Progressao.estado` Enum, `MUDA_CARGA`, frase == campo, `sessoes`/
   `ultimo_registro` no mesmo laço; (b) SUBIR_DOBRADO, teto 10% e
   "referência = primeira completa em 4 datas" ficam **adormecidos (E)** até
   `medir_progressao`, e se subirem, sobem como C citando a docstring de
   `proxima_carga` (`workouts/services.py:2245-2270`) e a decisão de 13/09.
   A regra "última data; incompleta ⇒ `None`" continua sendo a regra.
5. **Capa de largura total condicionada**: a faixa de 96 px (d406fe0) é o
   padrão. Qualquer capa exige medição PRÉVIA do y de "Concluir série" nas 5
   larguras + 360×800; se sair da dobra a 360×800 ou 390×844, vira D. O item
   está marcado como REVISÃO DE DECISÃO MEDIDA, não como "só a forma muda".
6. **Home dividida em duas**: bug/decisão escrita (B, onda 2b) e "refeição
   da vez expandida, demais colapsadas, mini-anéis" — alternativa material
   à Home canônica — virou **C-HOME** própria (§3).
7. **Onda 2, item 6 reescrito**: régua de teste com o contrato 4/4/3/3 como
   piso (não "≥ 4 uniforme"), citando o parágrafo do contrato; trava por
   OCORRÊNCIA classificada E até a matriz {4..7}×{12,20,24}×faixa provar
   que não fere as TRÊS TRAVAS nem esvazia sessão.
8. **"Como fui" descrito como existe** (lista crua, 8 datas, 8 consultas);
   sparkline é acréscimo condicionado: carga bruta, sem e1RM/volume, sem
   subir `CONSULTAS_DA_LEITURA`, a lista crua continua a fonte visível.
9. **Sprite em `base.html` com medição obrigatória** (ficha/painel/execução
   antes e depois) e `{% if %}` fora do shell offline, como o mapa faz.
10. **C-FORCA saiu das decisões** → §5 como D nesta campanha, com custo.

**Recusada (cético 1, item 9), com motivo:** a observação sobre
`workouts/test_carga_offline_v2.py` "untracked" envelheceu. Verificado em
14/09 ao escrever este plano: `HEAD = 9430f78 = origin/main`, o arquivo está
em `git ls-files`, e a árvore só tem `artifacts/`, `.agents/`, `AGENTS.md` e
`docs/ux-audit/` sem rastreio. A pré-condição fica escrita mesmo assim
(onda 0, T0.1) — o que se recusa é a premissa, não a verificação.

**Aplicadas (cético 2):**

1. **P1-11 e os dois testes travados**: escolhida a alternativa (a) — o
   destino do PAINEL continua fixo em `workouts:ficha`
   (`workouts/tests.py:2327 test_the_destination_stays_put_because_the_target_screen_walks`
   fica verde, só o VERBO muda, como `routine.html:250` já faz); "Continuar
   de onde parou" → execução do próximo pendente SÓ no cartão AGORA da Home
   (`plans/agora.py`), com `plans/tests.py:3072` reescrito de `workouts:now`
   para `workouts:ficha` no "Começar treino" e a docstring citando o
   requisito A. Controle positivo nos dois lugares.
2. **Onda 4 não é refém de C-DIR**: nasceu a **onda 2b — COMPORTAMENTO E
   COPY SEM PELE**, com tudo o que era B e não usa token, fonte ou família
   de cartão (COPY E NÚMEROS, E14, "19:00", PA-05, PA-08, MC-12, MKT-07/D7,
   E16, Q-09, DV-P0.2 bugs de token/seletor). A onda 4 ficou só com PELE.
3. **Elegível não substitui ativo**: as nove guardas continuam sobre
   `is_active=True`; os nove halteres entram com `active: false` e
   `padrao`/`variante` preenchidos; `elegiveis()` = ativo ∧ mídia com teste
   `elegiveis() == ativos` (catraca: divergir = alguém ativou sem mídia).
   `test_video_direto.py:112/157/163` listados nos arquivos.
4. **`medir.js` versionado** em `scripts/qa/medir.js` com baseline em
   `docs/design-audit/baseline-home-390.json` — e ANTES de C-DIR (onda 0),
   porque não toca `app.css` e a onda 2b já precisa dele.
5. **`sync_active_routine` só com `has_training_days`**; P1-01 e P1-02 no
   mesmo commit (T1.1), com controle "Concluir com zero dias → 302, zero
   `TrainingPlan`".
6. **`podar()` ganha chamador**: `manage.py podar_operacoes` no fim de
   `scripts/build.sh`, com teste `VALIDADE_DIAS (30) > 7` (janela da fila).
7. **`partials/sparkline.html` nasce na onda 3 (DV-C)**, e a ordem da onda 4
   está escrita: PROGRESSO antes de LEITURA.
8. **CLAUDE.md em duas etapas**: 5b reescreve só "o motor não lê
   equipment"; "NÃO EXISTE CAMPO DE AMBIENTE" só no commit da 5c, junto com
   a inversão de `OProdutoNaoPrometeAmbienteTests` (:566).
9. **`onboarding_step` não é reutilizado**: wizard novo com escala própria,
   `RunPython` só para quem está ABAIXO de `ONBOARDING_DONE` (7,
   `accounts/models.py:419`), teste para step ∈ {1..6}.
10. **Linhas atualizadas** (`fila.js:594` dispara / `:669` e `pwa.js:532`
    consomem `nutriplan:enfileirado`; `pwa.js:169` `CHAVE =
    "nutriplan_pwa_dismissed"`); regra geral: âncora textual ao lado da linha.

**Recusadas (cético 2):** nenhuma na substância. Variações de forma: (4)
versionar `medir.js` na onda 0 e não como primeiro commit da 3; (7) mover a
parcial para a onda 3 em vez de só declarar a ordem — as duas coisas foram
feitas.

---

## 1. Origem — os três briefs, e o que JÁ existe

| brief | caminho | tamanho |
|---|---|---|
| UX | `docs/ux-audit/ux-master-brief.md` (+ `docs/ux-audit/screenshots/`, 38 capturas, 3,9 MB) | 1.007 linhas |
| TREINO | `<scratchpad>/pesquisa-treino/brief-treino-v2.md` (v1: `brief-treino.md`; medições em `frente-equipamento-medicoes.md`, `notas-rir.md`, `notas-volume.md`) | 1.928 linhas |
| DESIGN | `<scratchpad>/design-audit/design-master-brief.md` (+ `direcao-c-mesa-e-ferro.md`, `direcao-B-mock.html`, `juiz2-veredito.md`, `juiz2-medir-home.json`, `medir.js`, `censo*.json`) | 744 linhas |

`<scratchpad>` = `C:\Users\biel-\AppData\Local\Temp\claude\C--Users-biel--nutriplan-infra\1bb661e7-3fa5-4011-8340-56a44206375b\scratchpad`
— **é por sessão e some**. A onda 0 copia os dois briefs de lá para
`docs/briefs/` (T0.2), senão a origem deste plano deixa de existir.

**O que já existe e este plano descreve, sem replanejar:**

- Execução (`/treino/agora/`): instrução de esforço por série e nível
  (`.series__esforco`); pastilha "62,5 kg × 9" e "antes 60 × 10"; concluir e
  desfazer voltam ao exercício em foco (`?exercicio=`); recorde na hora
  (`avaliar` no ramo de gravação, teto 20); poster de 96 px com fotos do
  `media_map.json` e player montado NO TOQUE, destruído ao fechar
  (`_demonstracao.html`, `_demonstracao_js.html`); peso do corpo sem carga
  obrigatória, Prancha em segundos; dupla progressão com razão escrita
  (`proxima_carga` — SUBIR/MANTER/`None`).
- Leitura (`/treino/exercicio/<id>/`): sem formulário, com poster, cue,
  "também trabalha" e "Como fui" (oito datas cruas, uma consulta).
- Ficha (`/treino/ficha/<id>/`): lista numerada, nome clicável em qualquer
  dia, "Fazer" só hoje, ≤ 15 consultas, 8,9-11,7 kB.
- Fila offline v2: série como EVENTO sem `set_number`, `op_id` sorteado na
  captura, `dia` no corpo, `seq` na drenagem, `fila.js`/`sw.js` comparados
  por teste (`workouts/test_carga_offline_v2.py`, provado no navegador em
  08/09).
- Motor: `prescrever_semana` com teto por experiência, três travas de aparo,
  cinco camadas de tempo, realocação de órfãos, título honesto, `A1/A2` só
  na tela; `Exercise.sem_carga` (9430f78) em vez de `equipment` no motor.
- Sistema visual: 70 tokens, `config/test_design_system.py` com catracas,
  `config/tests.py` recalculando contraste; famílias `card/btn/chip/pill/
  tile/data-list/empty-state/hint`; escala de camadas de seis degraus.

---

## 2. Conflitos resolvidos

1. **Quem chama `sync_active_routine` (UX P1-01/D2 × TREINO).** TREINO é
   dona da função; ganha dois chamadores — Concluir do onboarding
   (`accounts/views.py:662`, ramo `proximo >= ONBOARDING_DONE`) e Salvar do
   passo 3 com `?origem=treino` —, **sempre atrás de `has_training_days`**
   (`create_routine` levanta `NoTrainingDays`, `services.py:1627`). A tela
   de comida continua não montando ficha (`plans/views.py:347`). Terceiro
   ramo "ainda não montada" em `_area_promovida.html` e no resumo. → T1.1.
2. **Poster 4:3 de 96 px (TREINO, d406fe0) × capa 16:9 sangrando + thumb
   na ficha (DESIGN).** O poster fica: identidade por nome, zero iframe
   servido, fotos de domínio público. **A ficha NÃO ganha thumb** (TREINO
   lista como regressão; CLAUDE.md: "nada que se use DURANTE a série mora
   na ficha", orçamento medido). A capa de largura total na execução/leitura
   é REVISÃO DE DECISÃO MEDIDA: só entra se a medição prévia do y do CTA
   mantiver a dobra a 360×800 e 390×844; senão a faixa de 96 px fica e o
   item vira D. → T4.2, T4.4.
3. **CTA atrás da tabbar (UX P1-08 × DESIGN sticky × TREINO espaçamento).**
   Sticky em `--camada-flutuante`, abaixo de `--camada-navegacao`, entra
   na onda 1 com os tokens de hoje (único que garante a dobra a 320×568 com
   a frase de sugestão mais longa); o Ferro só reveste na onda 4. Régua da
   TREINO mantida: y do botão antes e depois. → T1.4.
4. **`body.modo-foco` (DESIGN) × dona da rota (TREINO).** `ModoTreinoView`
   e a corrida em andamento passam `modo_foco=True` no contexto; `base.html`
   escreve a classe (servidor, nunca `:has()`); teste conta exatamente dois
   templates. A execução não ganha regra nova por isso. → T4.2.
5. **Mídia de "Músculos trabalhados" (UX D6 × TREINO L03 × memória "3D
   cancelado").** Código ≠ curadoria: o segundo player SAI agora
   (comportamento incorreto), "Músculos trabalhados" vira texto de
   `muscle_group` + `secondary_muscles`; vídeo de anatomia volta só por
   exercício curado, um player por vez; 3D não reabre. → T1.16.
6. **Reps fora de 1..100 (UX recusa × TREINO clamp).** Teto da TREINO;
   comportamento da UX: recusa com mensagem e valores preservados (200 +
   erro, não 302). A fila não muda: `required`/`max` no HTML impedem o item
   inválido antes da captura. → T1.15.
7. **Exercício concluído sem formulário (UX P1-06 × TREINO aceita série
   extra).** O servidor continua aceitando até 20, idempotente por `op_id`
   (a fila reenvia). A TELA renderiza o ramo concluído sem
   `<form class="registro">`, com terciário explícito "registrar série
   extra". → T1.3.
8. **Sprite em `base.html`, linho, fonte própria (DESIGN × CLAUDE.md).**
   Sprite: a decisão registrada é sobre o MAPA (sem ícone para não copiar
   desenhos) — promover o único sprite preserva a razão, o mapa continua sem
   `<use>`, e entra com medição de peso e `{% if %}` fora do shell offline.
   Fonte: um `.woff2` via `collectstatic` não é framework nem build step —
   condicionada a tamanho ≤ 80 KB e `tnum` presentes (fontTools). Linho:
   `test_tema_claro` congela um VALOR, não uma medição; muda junto com
   C-DIR, com a razão escrita no teste e recuo `#f6f5f1`. → T3.1, T3.2, T3.6.
9. **Barra de baixo acende por destino (UX 1.4 × CLAUDE.md "nenhuma aba
   acende").** O código é a verdade e está certo por destino; o parágrafo
   envelheceu e é reescrito na onda 6. Conquistas acende a aba de origem via
   `?de=` em lista fechada. → T2b.3, T6.4.
10. **Home ≤ 1.900 px (DESIGN) × o que sai (UX).** Sai o que UX listou;
    explicações viram `.nota` + details. A altura alvo permanece
    [HIPOTÉTICA] até a captura; a catraca só entra depois de medida. O
    colapso das refeições futuras é C-HOME. → T2b.2, T4.1.
11. **`--recem` escrito pelo servidor (DESIGN) × contrato da fila intacto
    (TREINO).** O sinal viaja no REDIRECT como parâmetro de lista fechada
    (`?feita=N`), lido no GET; zero campo no POST, zero coluna, zero mudança
    em `ROTAS`. Offline, o retorno local é `nutriplan:enfileirado`. → T4.2, T6.1.
12. **"Continuar de onde parou" (UX D4 × `test_the_destination_stays_put`).**
    Painel: destino fixo (ficha), verbo muda. Home (cartão AGORA): "Continuar"
    → execução do próximo pendente. → T1.2.

---

## 3. Decisões C para o dono — só as genuínas

Três. As outras quatro do plano anterior desceram (C-EQ → B; C-RESET,
C-SOBRA, C-FORCA → §5). Nenhuma bloqueia as ondas 0, 1, 2 e 2b.

**Decididas pelo dono em 14/09/2026:** C-DIR = (A) Mesa & Ferro corrigida
(com a fonte própria condicionada a medir); C-HOME = (A) refeição da vez
aberta, as demais colapsadas; C-ONB = (B) três telas + personalização
progressiva. Nenhuma das três volta a ser perguntada.

### C-DIR — direção visual (necessária ANTES da onda 3)

**Pergunta:** "Mesa & Ferro" corrigida (Mesa clara no app; Ferro só na
execução, na corrida em andamento e no tema escuro; DM Sans Variable
condicionada a medir; linho `#f5f3ee` com recuo `#f6f5f1`; sprite em
`base.html`) — ou Direção B pura — ou não redesenhar a pele agora?

- (A) C corrigida. Custo: onda 3 inteira (tokens, 4 pesos, raios, botões,
  cards, inputs), `test_tema_claro`/`test_design_system` editados com razão
  escrita, captura no escuro antes de tocar `app.css`.
- (B) B pura: única com mock renderizado, mais vendável no Treino; custa
  segunda paleta `*-viva` que quebra brand/folha, `--surface-focus` preta na
  Home, alimentação "A com quinas retas", Archivo ~90 KB.
- (C) Não redesenhar: só as correções já nas ondas 1-2b; o produto continua
  "painel administrativo bem organizado".

**Recomendação:** (A). Dois juízes independentes convergiram (46/60 e
43/60): cobre o app inteiro, nasce do produto, prova unidade pelo que não
muda. (A) sem a fonte própria é subconjunto válido — a fonte é o item mais
reversível.

### C-HOME — a refeição da vez expandida, as demais colapsadas (ANTES de T4.1)

**Pergunta:** na Home, a refeição da vez vira o único cartão aberto (A/B
segmented, um "Registrar", Pulei/Outra terciários) e as demais viram linhas
de 56 px que abrem inline — com três mini-anéis no resumo? Ver os alimentos
de uma refeição futura passa a custar UM toque; registrar continua custando
o mesmo (mesmos POSTs).

- (A) Sim: Home mais curta (alvo hipotético ≤ 1.900 px a 390), foco na
  refeição que importa agora. Custo: um toque para ver o futuro.
- (B) Não: todas as refeições continuam abertas; entram só as remoções B
  (T2b.2) e a pele (T4.1) sobre a estrutura de hoje.

**Recomendação:** (A), com a lista de alimentos da refeição futura em
`<details>` (sem JS, sem estado perdido no voltar) e medição de altura
antes/depois no commit. "Quem não declarou nada vê a Home de antes" continua
verdade: a ordem canônica e a ausência de selo não mudam com isso.

### C-ONB — onboarding em três telas (ANTES de T4.8)

**Pergunta:** encurtar para três telas antes do primeiro cardápio, com
personalização progressiva (experiência/divisão no painel com prévia real,
sono/estilo no cardápio, prioridade na Home a partir do 2.º dia)?

- (A) Manter 6 passos e só corrigir (montar a ficha no Concluir, passo 6
  compacto, prévia real, contador honesto, erro no campo) — já nas ondas 1 e
  2b; sete perguntas continuam antes de terem consequência.
- (B) Três telas + montagem que monta dieta E ficha + cartão "seu plano está
  pronto"; perguntas adiadas nos lugares em que têm consequência. Custo
  médio: wizard com escala própria, `RunPython` só para quem está abaixo de
  DONE, três cartões com `?origem=`. Nenhuma pergunta adiada muda a meta
  calórica (medido).
- (C) Duas telas: como B, mas a tela 2 fica longa a 320.

**Recomendação:** (B), preservando: prioridade é pergunta própria; uso não é
intenção declarada; escolhas abrem em branco; `prioridade == ""` é estado de
verdade. Enquanto não decidida, (A) avança — é subconjunto de (B).

---

## 4. Ondas

Formato de cada tarefa: **id de origem · classe · arquivos · passos**. Os
passos seguem sempre: teste que falha → vermelho → implementação → verde →
sabotagem (com o que precisa ficar vermelho) → QA no navegador nas 5
larguras (320/375/390/430/1024; + 360×800 quando mexe acima do CTA) →
commit. Onde um passo é óbvio, ele está abreviado, não omitido.

### Onda 0 — PRÉ-CONDIÇÕES (3 tarefas, 1 push, sem decisão)

#### T0.1 — árvore, banco, suíte, conta de QA

**Origem:** cético 1 (item 9) · **Classe:** B · **Arquivos:** nenhum de
produção.

- [ ] `git status` limpo salvo `artifacts/`, `.agents/`, `AGENTS.md`,
  `docs/ux-audit/`; `HEAD == origin/main` (hoje `9430f78`).
- [ ] `pg_ctl start`; `manage.py check`; `manage.py makemigrations --check`.
- [ ] Suíte completa uma vez (baseline: 2873 verde em 9430f78) — registrar
  o número no scratchpad; nada abaixo disso é aceito nas ondas seguintes.
- [ ] Conta 1176 restaurada com `scratchpad/restaurar_qa.py` (ou recriada
  com `criar_qa.py`); zero `ExerciseLog` dela ao terminar.

#### T0.2 — os briefs viram parte do repositório

**Origem:** §1 · **Classe:** B · **Arquivos:** Create `docs/briefs/2026-09-13-treino-v2.md`,
`docs/briefs/2026-09-14-design.md`, `docs/briefs/2026-09-14-ux.md` (mover
`docs/ux-audit/ux-master-brief.md` para lá ou linkar); `docs/ux-audit/screenshots/`
entra (3,9 MB, uma vez); `direcao-c-mesa-e-ferro.md`, `juiz2-veredito.md`
entram em `docs/briefs/design/`.

- [ ] Copiar; conferir que nenhum arquivo traz dado de pessoa real (grep por
  `@` fora de `local.invalid`).
- [ ] `git add` por caminho; commit "Briefs de 13-14/09 entram no repositório".

#### T0.3 — `medir.js` versionado, com baseline

**Origem:** cético 2 (item 4), DESIGN DV-PROVA · **Classe:** B ·
**Arquivos:** Create `scripts/qa/medir.js` (de `scratchpad/design-audit/medir.js`),
`docs/design-audit/baseline-home-390.json` (de `juiz2-medir-home.json`),
`scripts/qa/medir.md` (como rodar: `agent-browser` + conta 1176 + 390 px);
Test: `config/test_medir_js.py` (novo).

- [ ] **Teste que falha:** o JSON de baseline tem as chaves que o script
  emite (`fontes`, `pesos`, `raios`, `sombras`, `fundos`), lidas por regex
  do próprio script — sabotar uma chave no JSON → vermelho.
- [ ] Implementar (copiar + documentar). Verde. Commit.
- [ ] **Gate da onda 0:** `check`, `makemigrations --check`, `diff --check`,
  push pelo `pre-push`, `/saude/`. Sem deploy visível: só documentação e
  script. Notificação sonora.

---

### Onda 1 — CONFIANÇA (18 tarefas, 2-4 pushes, zero migration, zero decisão)

Objetivo: parar de mentir e de perder toque — os 13 P1 confirmados por
cético, os P2 de navegação que os acompanham e o que 9430f78 deixou aberto.

#### T1.1 — a ficha nasce quando a pessoa termina de responder; zero dias desliga a rotina

**Origem:** UX P1-01 + D2 + P1-02 (Q-02) / TREINO `sync_active_routine`
(conflito 1; cético 2 item 5) · **Classe:** B · **Arquivos:** Modify
`accounts/views.py` (:662 ramo `proximo >= ONBOARDING_DONE`; save do passo 3
com `?origem=treino`), `accounts/forms.py` (save do passo 3),
`workouts/services.py` (`sync_active_routine` idempotente; `estado_do_treino`
vazio sem dias), `plans/streaks.py` (`_dias_de_treino` lê o plano ATIVO),
`templates/plans/_area_promovida.html`, `plans/agora.py`,
`templates/plans/today.html` (ramo "ainda não montada"); Tests:
`accounts/tests.py`, `plans/test_streaks.py`, `workouts/tests.py`.

- [ ] **Teste que falha:** (a) conta nova com dia de treino hoje e
  prioridade Treino: primeira GET de `/` após Concluir NÃO contém "Hoje não
  tem treino" e o resumo não diz "descanso"; `TrainingPlan` ativo existe;
  (b) Concluir com ZERO dias → 302, zero `TrainingPlan`, zero 500;
  (c) editar dias para nenhum → `TrainingPlan.is_active == False`, Home não
  menciona séries, ofensiva não cobra treino em Seg/Qua/Sex;
  (d) controle: GET de `/` (plans) continua sem criar `TrainingPlan`
  (`plans/views.py:347`).
- [ ] Vermelho → implementar (`if has_training_days(user): sync_active_routine(user)`
  nos dois chamadores; zero dias ⇒ `is_active=False` no plano ativo — plano é
  retrato, não se apaga) → verde.
- [ ] **Sabotagem:** remover a guarda `has_training_days` → (b) vermelho (500);
  remover a desativação → (c) vermelho.
- [ ] QA: cadastro completo com conta descartável local, 5 larguras na Home.
- [ ] Commit `Onboarding: a ficha nasce no Concluir, e zero dias desliga a rotina`.

#### T1.2 — "Começar treino" abre a FICHA em toda porta; "Continuar" só na Home

**Origem:** UX P1-11 + D4 + MC-04 + MC-21 (cético 2 item 1; conflito 12) ·
**Classe:** A/B · **Arquivos:** Modify `plans/agora.py:75-95`,
`templates/plans/today.html:309`, `templates/workouts/routine.html:248-250`,
`templates/workouts/agora.html` (:88 e :528, "Ver o treino completo" com UM
destino), `config/test_b6_navegacao.py`, `plans/tests.py:3064-3072`
(`workouts:now` → `workouts:ficha`, docstring com o requisito A),
`workouts/tests.py:2316-2344` (mantido; docstring ganha "o verbo muda, o
destino não").

- [ ] **Teste que falha:** (a) todo link com texto "Começar treino" (Home,
  painel, leitura) resolve para `workouts:ficha`; (b) cartão AGORA da Home
  com série de hoje: rótulo "Continuar de onde parou" → `workouts:now`
  (`?exercicio=<próximo pendente>`), e sem série hoje → "Começar treino" →
  ficha; (c) painel com série hoje: href continua `workouts:ficha`, rótulo
  "Abrir a ficha de hoje"; (d) `.resumo-dia__treino` → painel; (e) leitura:
  "Fazer este exercício"; (f) um único texto por destino
  (`test_nomenclatura` por destino).
- [ ] Vermelho → implementar → verde. **Sabotagem:** trocar o `reverse` do
  painel para `now` → (c) e `test_the_destination_stays_put` vermelhos;
  trocar o da Home → (a) vermelho.
- [ ] QA 5 larguras: Home → ficha → execução; Home com série → execução.
- [ ] Commit.

#### T1.3 — exercício concluído não mostra "Série None"

**Origem:** UX P1-06 (TR-01) (conflito 7) · **Classe:** B · **Arquivos:**
Modify `templates/workouts/agora.html` (:173/:324/:339/:354 — ramo
`atual.proxima_serie is None`), `workouts/views.py` (`ModoTreinoView`,
contexto `concluido`), `templates/workouts/_item_da_ficha.html` ("Concluído
N/N"), `templates/workouts/exercicio.html` (CTA some quando concluído);
Test: `workouts/tests.py`.

- [ ] **Teste que falha:** com `_primeira_serie_livre == None`: GET sem
  `<form class="registro">`, sem a string "None", com "concluído", com
  pastilhas, desfazer, próximo e um `<a>`/`<button>` "registrar série extra"
  que reabre o formulário (`?extra=1`, lista fechada); **controle positivo:**
  POST de série extra continua gravando (até 20, `op_id` idempotente).
- [ ] Vermelho → implementar → verde. **Sabotagem:** forçar o ramo com
  formulário → vermelho; remover a aceitação do POST → controle vermelho.
- [ ] QA 5 larguras com a conta 1176 (4/4 séries e desfazer no fim).
- [ ] Commit.

#### T1.4 — o botão "Concluir série" nunca fica atrás da tabbar

**Origem:** UX P1-08 (MOB-03) + TREINO UX-CTA-320 (conflito 3) ·
**Classe:** B · **Arquivos:** Modify `static/css/app.css` (§ execução:
`.agora__concluir { position: sticky; bottom: calc(var(--tabbar-h) +
env(safe-area-inset-bottom)); z-index: var(--camada-flutuante); }`),
`templates/workouts/agora.html` (agrupar Carga/Reps/Concluir no bloco
sticky), `push/tests.py` (nada acima de `--camada-navegacao` além da própria
navegação e do aviso).

- [ ] **Medir ANTES:** y de "Concluir série" em 320×568, 360×800, 375×667,
  390×844, 430×932 com `scratchpad/medir_cta.sh` (ou `scripts/qa/medir.js`).
- [ ] **Teste que falha:** `app.css` declara `.agora__concluir` com
  `position: sticky` e `z-index: var(--camada-flutuante)` (teste textual
  como `push/tests` faz); controle: `--camada-flutuante <
  --camada-navegacao` continua guardado.
- [ ] Implementar → verde. **Sabotagem:** `z-index: var(--camada-navegacao)`
  → vermelho.
- [ ] QA: `elementFromPoint` no centro do botão devolve o botão em todas as
  larguras com a frase de sugestão mais longa; `.series__esforco` em uma
  linha a 320; y DEPOIS registrado no commit.
- [ ] Commit.

#### T1.5 — "bodyweight" sai das telas e das docstrings; a doc de "NUNCA aumenta" é reescrita

**Origem:** TREINO ONDA-0 + VI-docs-envelhecidas · **Classe:** B ·
**Arquivos:** Modify `workouts/views.py:771`, `templates/workouts/agora.html`
(×7) e `exercicio.html:73` (→ `exercise.sem_carga`), `agora.html:409-438`
(reescrever: a progressão SOBE desde b14efff), docstrings
`workouts/services.py:11-15/53-80/283-287/391/409`, `accounts/forms.py:721`,
`accounts/models.py:466`, `historico_do_exercicio` (10→20 no texto),
`workouts/tests.py:4886` (docstring) e `FOLGA_*` mortos.

- [ ] **Teste que falha:** `grep "bodyweight"` = 0 em `workouts/views.py` e
  `templates/workouts/`; **controle positivo:** sabotar `Exercise.sem_carga`
  para `False` derruba `workouts/test_peso_do_corpo.py:77`.
- [ ] Vermelho → implementar → verde. Commit `Treino: o que a tela pergunta
  ao exercício, e não ao campo`.

#### T1.6 — a lista de compras não repete o nome do alimento na quantidade

**Origem:** UX P1-03 (UXA-01/MOB-01) · **Classe:** B · **Arquivos:** Modify
`plans/compra.py`, `templates/plans/shopping.html` (quantidade DENTRO do
`<label>`), `static/css/app.css:3161-3178` (`overflow-wrap: normal` no nome;
quantidade empilha abaixo); Test: `plans/tests.py`.

- [ ] **Teste que falha:** para cada item, a string da quantidade não contém
  `Food.name`; o `<label>` contém `.shopping__qty`.
- [ ] Vermelho → implementar → verde. **Sabotagem:** reintroduzir o nome
  na quantidade → vermelho.
- [ ] QA 320/375/390/430/1024: nenhum `.shopping__name` com > 2 linhas
  (medido por `getClientRects().length`).
- [ ] Commit.

#### T1.7 — zerar a água não empurra o número para duas linhas

**Origem:** UX P1-04 (UXA-02) + MOB-11 + MOB-13 · **Classe:** B ·
**Arquivos:** Modify `templates/plans/_agua.html` (confirmação em linha
própria abaixo do cabeçalho), `static/css/app.css:4278-4283`
(`.agua__valor { white-space: nowrap }`; folga ≥ 8 px entre desfazer/zerar
e entre +250/+500/+750); Test: `config/tests.TouchTargetTests`.

- [ ] Teste: a confirmação não é irmã do `.agua__valor`; QA: com o details
  aberto `.agua__valor` tem 1 linha a 320 e 390; nenhum par de alvos com
  distância < 8 px. Implementar; sabotagem: tirar o `nowrap` → QA vermelho.
- [ ] Commit.

#### T1.8 — "Permissão negada" não é sobrescrito; GPS negado diz como liberar

**Origem:** UX P1-05 (UXA-03) + E10 · **Classe:** B · **Arquivos:** Modify
`static/js/pwa.js:95-130` (`render()` recebe o estado da permissão),
`static/js/corrida.js:21/190-215`, `templates/workouts/corridas.html`
(botão desabilitado com razão sem `geolocation`); Test: `push/tests.py`
(contrato lendo `pwa.js`, como faz com `sw.js`).

- [ ] **Teste que falha:** o ramo `null` por permissão negada não chama
  `render` com o texto padrão (regex sobre o arquivo); `corridas.html`
  contém o texto de como liberar.
- [ ] Implementar → verde. Sabotagem: devolver o texto padrão → vermelho.
- [ ] QA (agent-browser com permissão negada via CDP): `[data-push-status]`
  contém "Permissão negada" 1 s depois; corridas com `geolocation` negado
  mostra a razão.
- [ ] Commit.

#### T1.9 — o toque offline aparece na tela na hora

**Origem:** UX P1-09 (E02) + E07 · **Classe:** B · **Arquivos:** Modify
`static/js/fila.js` (`:594` dispara `nutriplan:enfileirado`; `:669`
consome), `static/js/pwa.js:532` (ouvinte por tela: água soma ao painel e
marca o botão; execução escreve a série com selo "aguardando rede" e avança
o rótulo; refeição "Registrada · aguardando rede"), `static/css/app.css`
(a classe emitida ganha estilo; a faixa da fila reserva espaço no `body`),
`templates/plans/_agua.html`, `templates/workouts/agora.html`; Test:
`push/tests.py`.

- [ ] **Teste que falha:** a classe que `fila.js` emite existe em `app.css`;
  `nutriplan:enfileirado` tem consumidor em `pwa.js` para as três telas
  (regex por `data-tela`); `fila.js` e `sw.js` continuam idênticos onde o
  teste já compara.
- [ ] Implementar → verde. Sabotagem: apagar o ouvinte da execução → vermelho.
- [ ] QA offline por CDP (o cenário de 08/09 mais a tela): 3 toques → 3
  séries "aguardando rede" na tela, 3 itens com `op_id` distintos, drenagem
  para 2/3/4; a faixa da fila não cobre botão a 320.
- [ ] Commit.

#### T1.10 — o convite de instalação não aparece para quem ainda não entrou

**Origem:** UX P1-13 (MKT-02) + D5 · **Classe:** B · **Arquivos:** Modify
`templates/base.html` (`data-sem-convite` escrito pelo servidor),
`accounts/views.py` (cadastro, login, recuperação, onboarding), `templates/404.html`,
`403.html`, `static/js/pwa.js:169` (`CHAVE`; toque fora só esconde na
visita; dispensa definitiva só no ×; convite após a primeira refeição
marcada ou série concluída); Tests: `accounts/tests.py`, `config/tests.py`,
`push/tests.py`.

- [ ] **Teste que falha:** as cinco telas anônimas e o 404 renderizam
  `data-sem-convite`; contrato em `pwa.js`: o handler de clique fora não
  escreve `nutriplan_pwa_dismissed`; `push/tests` continua provando que o
  convite nunca cobre a tabbar.
- [ ] Implementar → verde. Sabotagem: remover o atributo do login → vermelho.
- [ ] QA: login/cadastro a 320 sem convite; Home após uma refeição marcada
  com convite. Commit.

#### T1.11 — a imagem de compartilhar não diz "concluído" com 4 de 16

**Origem:** UX P1-12 (MC-02) + D8 · **Classe:** B · **Arquivos:** Modify
`templates/workouts/routine.html:611/736/747-757`, `static/js/card.js:191`;
Test: `workouts/tests.py`.

- [ ] Teste lendo `card.js`/`routine.html`: "TREINO CONCLUÍDO" só sob
  `estado.concluido`; rótulo "Compartilhar o que já fiz" antes de concluir;
  "Minha evolução" com acento. Implementar; sabotagem: tirar a condição →
  vermelho. Commit.

#### T1.12 — o rodapé do login lê a 4,5:1 sobre o pior ponto do gradiente

**Origem:** DESIGN P1-07 (MOB-02) + CT-18 · **Classe:** B · **Arquivos:**
Modify `static/css/app.css` §35 (vinheta `.auth--entrada::before` sai ou
≤ 15 %), `config/tests.py` (contraste de `--text-muted` sobre o ponto mais
escuro do gradiente, recalculado a partir dos tokens).

- [ ] Teste que falha (o cálculo novo com a vinheta de hoje) → implementar →
  verde. Sabotagem: vinheta a 40 % → vermelho. QA: pixel do rodapé a 320 e
  390. Commit.

#### T1.13 — "entrou na lista" tem flash e âncora; toda âncora respeita a app-bar

**Origem:** UX P1-10 (E03) + NOVO-02 · **Classe:** B · **Arquivos:** Modify
`plans/views.py:938` (`messages.success` + `#item-<id>`),
`templates/plans/shopping.html:107`, `templates/plans/today.html`
(`#slot-N`, `#seus-itens`, `#hidratacao`), `static/css/app.css`
(`scroll-margin-top: var(--appbar-h)` nas âncoras).

- [ ] Teste: o redirect carrega a âncora e a mensagem. QA: item novo dentro
  do viewport a 320/390/430; "Ver refeição" pousa com o topo do card ≥ 0.
  Commit.

#### T1.14 — "← Ficha A1" na leitura; a linha da ficha inteira é a porta

**Origem:** UX NOVO-03 + CA-03 + NOVO-06 · **Classe:** B · **Arquivos:**
Modify `workouts/views.py` (`ExercicioView` lê `?de=` em lista fechada
`{"ficha", "agora", "painel"}`), `templates/workouts/exercicio.html`,
`templates/workouts/_item_da_ficha.html` (linha inteira `<a>` com seta;
"Fazer" segundo alvo 44×44 com ≥ 8 px), `static/css/app.css:5855-5862`
(`.agora__nome-link` ≥ 44×44); Tests: `workouts/tests.py`,
`config/tests.TouchTargetTests`.

- [ ] **Teste que falha:** `?de=ficha` → href da ficha com "← Ficha A1"
  (rótulo de `nomear_ocorrencias`); `?de=qualquer` → padrão (painel);
  `?de=//evil` nunca vira href; área tocável de `.ficha-item` ≥ 90 %.
- [ ] Implementar → verde. Sabotagem: aceitar `de` livre → vermelho. QA 5
  larguras. Commit.

#### T1.15 — reps fora de 1..100 são recusadas com o valor preservado; a última série diz o que vem

**Origem:** UX TR-08/E08 + TR-02 + TR-03/MOB-12 × TREINO (conflito 6) ·
**Classe:** B · **Arquivos:** Modify `workouts/views.py`
(`ConcluirSerieView` :782-788: 200 + erro em vez de clamp),
`templates/workouts/agora.html:373-398` (`required`, `min`, `max`;
`[role=status]` "Supino concluído · 4/4 — agora: Flexão"; desfazer escreve
"Série N do X desfeita"; confirmação a partir do segundo toque quando é de
OUTRO exercício); Test: `workouts/tests.py`.

- [ ] **Teste que falha:** POST `reps=999` → 200, erro, `value="999"`
  preservado, zero `ExerciseLog`; POST `reps=0` idem; POST `reps=10` grava
  (controle); redirect após a última série carrega o status;
  `workouts/test_carga_offline_v2.py` continua verde (o HTML tem `max=100`
  — a fila nunca captura item inválido).
- [ ] Implementar → verde. Sabotagem: voltar o clamp → vermelho. QA. Commit.

#### T1.16 — um player por página; "Músculos trabalhados" é texto

**Origem:** UX NOVO-05/TR-07 + TR-06 + D6 (conflito 5) · **Classe:** B ·
**Arquivos:** Modify `templates/workouts/_demonstracao.html`,
`_demonstracao_js.html:29-79`, `exercicio.html`, `agora.html`,
`static/css/app.css` ("fechar" fora da barra do YouTube); Tests:
`workouts/test_lista_de_hoje.py:311`, `test_video_direto.py:459`.

- [ ] **Teste que falha:** o HTML servido não tem segundo `[data-demo]`;
  "Músculos trabalhados" contém `muscle_group` e `secondary_muscles`
  (texto); zero `<iframe` servido continua.
- [ ] Implementar → verde. QA: `document.querySelectorAll("iframe").length ≤ 1`
  após abrir vídeo e a seção de músculos; campos preservados ao abrir/fechar
  (requisito A). Commit. **Nota:** 3D não reabre (memória do projeto).

#### T1.17 — `.semanas > .semana` do peso não veste as listas de treino e água

**Origem:** DESIGN CA-02 (SBS-01) · **Classe:** B · **Arquivos:** Modify
`static/css/app.css:3402-3439` vs `:7118-7140` (renomear a família do peso
para `.pesagens`), `templates/plans/historico.html`, `hidratacao.html`;
Test: `config/tests.py`.

- [ ] Teste textual: `.semanas .semana` não recebe `background`/`padding`
  fora de `.pesagens`. QA: altura das listas de treino/água cai de 552 para
  ≤ 260 px a 390. Commit.

#### T1.18 — sessão vencida, PRG que não empilha histórico, alimento não reconhecido, peso ecoado

**Origem:** UX E01 + PA-03 + UXA-04 + UXA-06 · **Classe:** B · **Arquivos:**
Modify `accounts/views.py`, `templates/accounts/login.html` ("Sua sessão
venceu. O que você tocou não foi salvo." quando há `next`), `static/js/pwa.js`
(`history.replaceState` após pouso de PRG em Hidratação/Progresso),
`plans/views.py` (aviso de alimento inexistente em "Comi outra coisa"),
`templates/plans/today.html` (peso salvo ecoa o valor com "editar").

- [ ] Testes: GET `/conta/entrar/?next=/` contém "sessão venceu" e sem
  `next` não contém; POST com alimento inexistente devolve aviso; Home após
  peso mostra o valor. QA: `history.length` não cresce com 4 registros de
  água. Commit.

#### Fechamento da onda 1 (gate)

- [ ] Sabotagens de T1.1-T1.18 executadas, vermelhas e restauradas (registro
  em `scratchpad/sabotagem_onda1.txt`).
- [ ] QA agent-browser em 320/375/390/430/1024: Hoje, painel, ficha,
  execução, leitura, lista, hidratação, login; 0 alvos < 44×44, 0 rolagem
  horizontal, 0 fonte < 11 px (`scratchpad/alvos.py`, `a11y.py`).
- [ ] Suíte completa ≥ baseline + testes novos; `check --deploy`;
  `makemigrations --check`; `git diff --check`; commits por unidade; push
  pelo `pre-push`; deploy provado (`class="agora__concluir"` no CSS servido
  ou 404 de `/treino/agora/?exercicio=0` no demo); `/saude/`; smoke: primeira
  Home de conta nova com dia de treino hoje (local), execução com exercício
  concluído no demo. Conta 1176 com zero `ExerciseLog`. Notificação sonora.

---

### Onda 2 — TREINO HONESTO (7 tarefas, 1-2 pushes, zero migration, zero decisão)

Objetivo: adaptação como LEITURA pura, ficha que concorda com o motor,
instrumento de medição em produção. O MOTOR NÃO MUDA DE REGRA.

#### T2.1 — `workouts/adaptacao.py`: a progressão vira módulo puro com estado nomeado

**Origem:** TREINO AD-load-history-sessoes + AD-manter-frase-igual-campo +
AD-determinismo-congelado (cético 1 item 4a) · **Classe:** B · **Arquivos:**
Modify `workouts/services.py:2003-2067` (`load_history` expõe `sessoes`
(≤ 10 datas) e `ultimo_registro` do MESMO laço — uma consulta),
`:2186-2324` (`proxima_carga` vira alias de `adaptacao.ajuste`); Create
`workouts/adaptacao.py` (`Progressao(valor, estado: Enum, razao)`,
`MUDA_CARGA = {SUBIR}`, `ajuste(item, sessoes, ultimo_registro, hoje)`);
Test: `workouts/test_dupla_progressao.py` (os casos de b14efff continuam),
`workouts/test_adaptacao.py` (novo); CLAUDE.md (parágrafo "adaptação é
leitura").

- [ ] **Teste que falha:** pureza textual de `adaptacao.py` (sem `django.db`,
  `timezone`, `requests`; controle positivo: inserir `from django.db import`
  → vermelho); 60/60/55 na série 3 ⇒ MANTER com valor 60 e a frase cita 60
  (frase == campo, lendo `value=` e o `<b class="num">`); os cinco casos de
  b14efff intactos; `CONSULTAS_DA_EXECUCAO = 20` inalterado.
- [ ] Implementar → verde. **Sabotagem:** `>=` → `>` em "fechou" → vermelho;
  `sessoes[:10]` → `[:1]` → o teste de `ultimo_registro` vermelho.
- [ ] Commit `Treino: a adaptação é um módulo puro, e o estado tem nome`.
  **Adormecido (E):** SUBIR_DOBRADO, teto 10 %, referência em 4 datas.

#### T2.2 — a última série de composto diz "pare com 1 a 2 sobrando, mesmo passando de N"

**Origem:** TREINO RIR-ultima-serie-faixa-nao-e-teto + PR-idade-65-cauteloso
+ EX-estados-no-mesmo-span · **Classe:** B · **Arquivos:** Modify
`workouts/models.py:768-806` (`instrucao_de_esforco(item, serie,
experiencia, cauteloso=False)`), `workouts/services.py` (`cauteloso =
perfil.age >= 65`, lido no mesmo ponto que `experiencia`),
`templates/workouts/agora.html:462-476` (estados novos no MESMO
`<span class="agora__anterior-sugestao">`); Tests: `workouts/test_esforco.py`,
`test_dupla_progressao.py` (ATelaTests).

- [x] **Teste que falha:** rep_max=10, última série de composto → contém
  "mesmo passando de 10" e não "falha"; rep_max=15 → não contém;
  `age >= 65` + composto → nunca "falha"; `_sugestao_de_*` leem `MUDA_CARGA`.
- [x] Medir y do CTA ANTES; implementar → verde; sabotagem: `<= 12` → `<= 5`
  → vermelho. QA: `.series__esforco` uma linha a 320; y DEPOIS nas 5
  larguras + 360×800 com a frase mais longa. Commit.
  *Feito em 17/09/2026: 16 testes em `test_esforco.py`; cinco sabotagens
  vermelhas (teto 5, idade exclusiva, `cauteloso` não chega à tela, isolador
  do cauteloso à falha, última série sem aviso). Medido a 320/360/375/390/
  430/1280: a frase de 44 caracteres ("Pare com 1–2 sobrando, mesmo passando
  de 10.") quebrava em DUAS linhas a 320 e 360 — ficou "1 a 2 sobrando,
  mesmo passando de 10." (37), uma linha em todas; CTA com a mesma altura
  de linha da frase de antes (40 caracteres). `agora.html` não foi tocado:
  os estados novos no `<span class="agora__anterior-sugestao">` são do T2.3.*

#### T2.3 — RETOMAR e ESTAGNADO falam; nunca baixam número

**Origem:** TREINO AD-retomar-v1-frase + AD-estagnado-v1-manter-e-dizer +
AD-sessao-perdida-nao-compensa + AD-adaptacao-e-leitura (C-RESET saiu) ·
**Classe:** B · **Arquivos:** Modify `workouts/adaptacao.py` (R2/R3: gap ≥ 21
dias ⇒ RETOMAR — mesma carga, SUBIR suspenso, reps no piso, frase; ≥ 28
acrescenta "comece mais leve se precisar" — nunca número menor; R5:
ESTAGNADO após três sessões sem avanço ⇒ "manter e dizer",
`estagnado_persistente` como trava contra frase em cadeia); Tests:
`workouts/test_adaptacao.py`, `plans/test_stress.py` (medição sintética).

- [x] **Teste que falha:** matriz gap ∈ {0,14,20,21,27,28,90} × fechou ×
  tronco/perna × completa/parcial; estagnação 60×{8,8,7}/{8,8,8}/{8,9,7} ⇒
  ESTAGNADO; reps `None` ⇒ MANTER; **quatro negativos que congelam o veto:**
  semana 8 == semana 1 sem histórico novo; ontem perdido não muda hoje;
  frequência observada não altera dia/teto/split; nenhuma escrita em
  `SessionExercise` (o módulo é puro — controle textual).
- [x] Implementar → verde. **Sabotagem:** 21 → 15 e 21 → 0 derrubam a matriz;
  RETOMAR devolvendo `carga * 0.9` → vermelho ("nunca número menor").
- [x] Distribuição de estados sobre o ano sintético de `test_stress` escrita
  no commit; "estagnado" > 30 % ⇒ recalibrar ANTES de publicar. Commit.
  *Feito em 17/09/2026 (`workouts/test_retomar_estagnado.py`, 24 testes;
  nove sabotagens vermelhas: 21→15, 21→0, ×0,9, ruído 1→2, reps None→0,
  platô sem prazo, sem trava persistente, SUBIR vencendo RETOMAR, reps
  fora do piso). Ano sintético (1.254 aberturas, 50 exercícios): manter
  71,9 %, retomar 21,7 %, sem sugestão 4,0 %, subir 1,8 %, estagnado 0,7 %
  — o retomar é do gerador (6 de 50 exercícios por dia). `agora.html`
  imprime `Progressao.rotulo` (uma linha); QA local a 320–1280: RETOMAR
  em 3 linhas no span, campo 60 e reps no piso; ESTAGNADO com o verbo
  "manter"; CTA no mesmo y.*

#### T2.4 — o instrumento: `medir_progressao`, guarda do recorde, convite de nível, poda

**Origem:** TREINO MEDIR-PROGRESSAO + RE-recordload-guarda +
AD-convite-atualizar-experiencia + L08-medicao + RE-poda-synced-operation
(cético 2 item 6) · **Classe:** B · **Arquivos:** Create
`workouts/management/commands/medir_progressao.py` (só SELECT: SUBIR→SUBIR,
reps−rep_max, paradas exatas em rep_max, retomar sem pausa, gaps),
`accounts/management/commands/podar_operacoes.py` (chama
`SyncedOperation.podar()`); Modify `scripts/build.sh` (depois dos seeds:
`python manage.py podar_operacoes`), `workouts/views.py:487`
(`RecordLoadView`: `supera_recorde` antes de `avaliar`), `plans/progresso.py`
+ `templates/plans/historico.html` (convite a atualizar o nível: ≥ 180 dias
e ≥ 24 datas, só iniciante/`""`); Tests: `workouts/test_medir_progressao.py`
(novo), `accounts/tests.py`, `workouts/test_recorde_na_hora.py`.

- [x] **Teste que falha:** `medir_progressao` sobre `PopulatedAccountMixin`:
  `assertNumQueries` só SELECT (capturar e afirmar que nenhuma começa por
  UPDATE/INSERT/DELETE), `ExerciseLog.count()` igual antes/depois;
  `SyncedOperation.VALIDADE_DIAS (30) > 7` com a razão na docstring (a poda
  nunca apaga `op_id` que um item drenável reenviaria); `podar_operacoes`
  apaga só o vencido; `RecordLoadView` abaixo do recorde não chama `avaliar`
  (teto 16); convite com 200 dias/30 datas sim, 100 dias não, intermediário
  nunca — dentro do teto 26.
- [x] Implementar → verde. **Sabotagem:** `>= 180` → `>= 0` → vermelho;
  `VALIDADE_DIAS = 5` → vermelho. **Medição L08** com agent-browser em 3G
  emulado: POST→302→GET e destruição do iframe, número no commit (é o
  insumo de "fetch sem recarga", E). Commit.
  *Feito em 17/09/2026 (`workouts/test_instrumento.py`, 15 testes; quatro
  sabotagens vermelhas — convite a 0 dias, validade 5, guarda removida,
  UPDATE dentro do medidor). Ajustes medidos: o teto do POST sem recorde
  ficou em 24 (a rota da ficha grava e relê mais que a da execução); o
  convite custa UMA consulta com o nível no WHERE, e o Progresso foi de
  26 para 27. L08 com `nav.py rede 3g` (o agent-browser está bloqueado
  pelo Controle de Aplicativo): POST→302→GET de 31 KB, load 180–330 ms no
  Wi-Fi e ~550 ms no 3G lento; o iframe aberto morre com a recarga.*

#### T2.5 — a ficha concorda com o motor: "Principal" só no principal, notas visíveis, frase dos dias

**Origem:** CRUZADO FI-principal-concorda-com-motor + MC-12 + CA-15 +
FI-notas-visiveis-na-ficha + FI-frase-dos-dias + TR-10/NOVO-07 + L14-linha +
PE-textos-tres-dias · **Classe:** B · **Arquivos:** Modify
`workouts/views.py:343-412/570-628` (`item.grau` de
`prioridades_da_sessao`), `templates/workouts/_item_da_ficha.html:41-47`,
`exercicio.html:53` ("Composto principal desta sessão" / "Composto de
apoio" / "Isolador", sem promessa de ordem), `routine.html:538-606`
(`divisao_explicada`; frase "X de Y dias planejados nas últimas 4 semanas",
nunca porcentagem), Create `templates/workouts/_notas_do_plano.html` (um
markup, dois includes com `{% if %}`), Modify `workouts/services.py:283-287`,
`accounts/forms.py:721`, `accounts/models.py:466`, `plans/progresso.py:40`
(três textos "até três dias pula o passo 4" corrigidos).

- [ ] **Teste que falha:** ficha do C "Pernas completo": exatamente UM
  `ficha-item__papel` "Principal" por grupo anunciado (sabotagem
  `is_compound` no lugar de `grau` → 3 → vermelho); iniciante 5 dias: a
  segunda passagem de A contém "quem está começando"; frase dos dias vs
  `split_for(4, pref)` nas três preferências; texto do programa não contém
  "abre mais um dia" com 7 dias; "5 de 12", nunca "42 %"; orçamentos 15/25
  inalterados.
- [ ] Implementar → verde. QA 5 larguras na ficha e no painel. Commit.

#### T2.6 — a régua da variedade é o contrato 4/4/3/3; o volume por sessão é congelado

**Origem:** TREINO PR-piso-semanal-regua + PR-volume-por-sessao-11 (L12-2
→ E; cético 1 item 7) · **Classe:** B · **Arquivos:** Modify
`workouts/test_prescricao_referencia.py` (célula discriminante "30 min × 3
dias"; assinaturas gravadas em `workouts/data/assinaturas_prescricao.json`);
nenhum arquivo de motor.

- [ ] **Teste que falha:** contrato 4/4/3/3 como PISO (peito 4, costas 4,
  tríceps 3, bíceps 3, em séries fracionárias) de três dias para cima em
  45-60 min, citando o parágrafo "O catálogo cobre o contrato de variedade";
  ~11 exercícios por sessão medido e congelado por assinatura; iniciante 4d
  não termina com passagem de 1 exercício/14 min.
- [ ] **Sabotagem:** `>= 3` do bíceps → `>= 1` no teste → precisa continuar
  vermelho quando o motor entrega 1 (controle com `escolher_para_o_tempo`
  sabotado para remover isoladores primeiro). `test_tempo_curto`,
  `test_reparticao_semanal`, `test_dois_grupos_por_dia` intocáveis e verdes.
- [ ] Commit. **Trava por ocorrência: E** — só volta com a matriz
  {4..7}×{12,20,24}×faixa provando que não fere as TRÊS TRAVAS.

#### T2.7 — textos com fonte, só se couberem sem empurrar o CTA

**Origem:** TREINO PR-iniciante-texto-dor + PR-goal-cut-texto +
PR-semana-de-manutencao-frase + L13 · **Classe:** B · **Arquivos:** Modify
`templates/workouts/ficha.html` (dor não é progresso nas primeiras semanas
— iniciante; a carga não cai por causa da dieta — `goal == cut`),
`agora.html` (linha de aproximação na série 1 de composto),
`workouts/services.py` (`nota_da_divisao`: manutenção com 1 sessão/1 série).

- [ ] Teste: presença condicionada (`goal == cut`; `experiencia ==
  iniciante`); ausência fora. Medir y do CTA antes/depois; se piorar a
  360×800, a linha de aproximação vai para a ficha. Commit.

#### Fechamento da onda 2 (gate)

- [ ] Sabotagens registradas; tetos 20/25/26 inalterados; suíte; `check`;
  `makemigrations --check`; `diff --check`; push; deploy provado (o demo
  renderiza `class="agora__anterior-sugestao"` com um estado nomeado);
  `/saude/`; smoke: `medir_progressao` em produção (via shell do Render, só
  SELECT) e `podar_operacoes` no log do build; CLAUDE.md com os parágrafos
  de adaptação e determinismo no mesmo push. Notificação sonora.

---

### Onda 2b — COMPORTAMENTO E COPY SEM PELE (6 tarefas, 1-2 pushes, zero decisão)

Tudo o que era B na onda 4 e não usa token, fonte nem família de cartão.
Independente de C-DIR, C-HOME e C-ONB.

#### T2b.1 — copy e números: um nome por destino, vírgula decimal em tudo

**Origem:** UX MC-04 + MC-17 + MC-13 + MC-14 + MC-18 + MC-11 + 2.9 ·
**Classe:** B · **Arquivos:** Modify `templates/**` (seis rótulos de
`/treino/` → um; quatro nomes de `/` → "Hoje"; "sinergista"/"na execução"
fora; voz uniforme nos botões da refeição; "3.000" com uma regra de milhar;
uma casa no peso em campo e tela; `nowrap` em `dd.num`), `config/test_nomenclatura.py`,
`plans/templatetags`.

- [ ] **Teste que falha:** rótulo por destino único para `/treino/` e `/`;
  varredura por regex `\d\.\d` (ponto decimal) nas rotas renderizadas de
  teste = 0. Implementar → verde. Sabotagem: um "62.50" num template →
  vermelho. Commit.

#### T2b.2 — Home: o que sai, sem mudar a estrutura

**Origem:** UX seção 10 + E14 + CA-13 + MC-10 + CA-19 · **Classe:** B ·
**Arquivos:** Modify `templates/plans/today.html`, `plans/agora.py`,
`templates/plans/_agua.html`, `plans/tests.py`.

- [ ] **Teste que falha:** Home não renderiza `start_time` ("19:00" — valor
  fora da interface desde 10/09); "Ver ficha" duplicado sai (um destino por
  texto — T1.2 já cobre); hint de 5 linhas vira `<details>`; frase da meta
  aparece UMA vez; ofensiva sem "cumpra treino" para quem não tem dia
  (E14); "Superávit" rotulado "planejado"; "pendente desde 07:30" no lugar
  de "pendente"; "Editar" fora do `<summary>`.
- [ ] Implementar → verde. **Medir a altura da Home a 390 antes e depois**
  (`scripts/qa/medir.js`) e escrever no commit — sem catraca ainda. Commit.

#### T2b.3 — `?de=` em lista fechada: Conquistas acende a aba de origem; Hidratação volta para Hoje

**Origem:** UX PA-05 + 2.14 + MC-19 · **Classe:** B · **Arquivos:** Modify
`plans/views.py` (Hidratação `?de=hoje`), `achievements/views.py`
(`?de=progresso|areas`), `templates/plans/hidratacao.html`,
`achievements/templates/`, `config/test_nomenclatura.py`.

- [ ] Teste: `/conquistas/?de=progresso` acende Progresso; `?de=x` cai no
  padrão; Hidratação com `?de=hoje` tem "← Hoje"; mesma frase de vazio em
  Áreas e /conquistas/. Commit.

#### T2b.4 — entrada e onboarding: erro no campo, vírgula no peso, contador honesto, passo 6 compacto

**Origem:** UX PA-08 + PA-02/MC-06 + PA-09 + Q-09/MC-16 + NOVO-11/E12 +
MKT-05/Q-06 + C-ONB (A) (subconjunto de B) · **Classe:** B · **Arquivos:**
Modify `accounts/forms.py` (`PesoField` com vírgula no valor inicial;
`add_error('prioridade')`), `accounts/views.py` (contador
`(posicao−1)/total`, 100 % só na montagem), `templates/accounts/onboarding_*.html`
(passo 6: segunda pergunta só com o marcado; JS progressivo; servidor
valida), `templates/partials/field.html` (`id="<campo>_error"`,
`aria-describedby`, `autofocus` no primeiro inválido), `templates/accounts/perfil.html`
(modo edição SEM stepper; Salvar → `#bloco`; Recalcular → `#metas`);
Tests: `accounts/tests.py`.

- [ ] **Teste que falha:** `PesoField` renderiza "82,5"; passo 6 com erro
  tem `field__errors` colado ao grupo e `autofocus`; contador nunca mostra
  100 % antes da montagem; modo edição não renderiza `wizard__label`;
  "Nenhuma restrição" existe; `aria-describedby` aponta para id existente;
  Perfil no meio do onboarding devolve com mensagem.
- [ ] Implementar → verde. Sabotagem: contador `posicao/total` → vermelho.
  QA 5 larguras nos seis passos. Commit.

#### T2b.5 — Perfil, lista, corridas, demo e 404: comportamento

**Origem:** UX PA-01/MOB-04 + PA-07 + MKT-07/D7 + E16 + lista "Voltar para
o cardápio" · **Classe:** B · **Arquivos:** Modify
`templates/accounts/perfil.html` (`dt` com `overflow-wrap: normal`; Sair
sem classe de perigo; Excluir com), `templates/plans/shopping.html` ("Voltar
para o cardápio" → `/#cardapio`; remover com `messages`), `demo/views.py` +
`templates/demo/capa.html` (CTA "Criar minha conta" na CAPA — a decisão de
demo tirou saídas da BARRA, não da capa), `templates/accounts/login.html`,
`cadastro.html` (link "Ver o app com dados de exemplo"), `templates/404.html`
(porta de treino quando o caminho começa por `/treino/`); Tests:
`demo/tests.py`, `accounts/tests.py`.

- [ ] Teste: demo linkado de login e cadastro; capa com CTA; 404 de
  `/treino/x/` contém link para `/treino/`; Sair não tem `--perigo`. QA
  5 larguras: nenhum `dt` com quebra intra-palavra. Commit.

#### T2b.6 — bugs de token e seletor que não dependem de direção

**Origem:** DESIGN DV-P0.2 (CT-11, CT-03, E06) · **Classe:** B · **Arquivos:**
Modify `static/css/app.css:2697` (`var(--linha)` indefinida →
`--border`), `--shadow-deep` preto sob o hero (→ token existente),
`.agua-card > .agua` moldura dupla, `background-attachment: fixed` sai,
5 hex fora do `:root` viram token; `templates/404.html`, `403.html`,
`403_csrf.html`, `offline.html` ("N" solto → `partials/marca.html`);
Test: `config/test_design_system.py` (hex fora do `:root` = 0, catraca).

- [ ] **Teste que falha:** toda `var(--x)` usada em `app.css` está definida
  (parser simples); hex fora do `:root` = 0; 404 renderiza a marca.
  Implementar → verde. Sabotagem: um `var(--nada)` → vermelho. QA nas 4
  páginas de erro a 320. Commit.

#### Fechamento da onda 2b (gate)

- [ ] Como nas anteriores. Deploy provado (Home do demo sem "19:00";
  `/conquistas/?de=progresso` acende a aba); `/saude/`; smoke. Notificação
  sonora — **e aqui o dono é chamado para C-DIR, C-HOME e C-ONB**, com o
  app já publicado nas três ondas anteriores.

---

### Onda 3 — FUNDAÇÃO DE DESIGN (8 tarefas, 1-2 pushes; depende de C-DIR)

Sem redesenhar tela nenhuma, mas todas mudam de pele. Catracas só descem;
toda edição de teste de valor travado leva a razão escrita.

#### T3.0 — captura no TEMA ESCURO e os três artboards (antes de tocar `app.css`)

**Origem:** DESIGN DV-PROVA · **Classe:** B · **Arquivos:** `artifacts/`
(fora do commit), `docs/design-audit/` (só as capturas de referência, ≤ 2 MB).

- [ ] Capturar Hoje/painel/execução/progresso a 320 e 390 nos DOIS temas
  (o escuro nunca foi capturado nesta campanha); rodar `scripts/qa/medir.js`
  e guardar `antes.json`. Três artboards de C a 390 com a fonte carregada.
  Sem commit de código.

#### T3.1 — tokens: Mesa no `:root`, Ferro no escuro e em `body.modo-foco`

> **17/09/2026 (CORTE, PR #6):** feito INVERTIDO — o Ferro é a base no `:root`, o Papel o derivado em `prefers-color-scheme: light`, `:root.modo-foco` (classe no `<html>`) força o Ferro; a execução escreve a classe. Valores da tabela do `DESIGN.md` com quatro ajustes medidos; 274 pares, 0 reprovados. `docs/superpowers/plans/2026-09-16-onda-3-corte.md`.


**Origem:** DESIGN DV-T1 + correções dos juízes (conflito 8) · **Classe:**
C→B (após C-DIR) · **Arquivos:** Modify `static/css/app.css` §1 (bloco
Mesa em `:root`; bloco Ferro em `@media (prefers-color-scheme: dark)`
guardado por `:root:not([data-theme="light"])` E em `:root[data-theme="dark"]`
E em `body.modo-foco`, com HEX LITERAIS nos três — `_tokens()` só lê
`#rrggbb`; `--agua/--brasa/--terra/--chama` com alias temporário de
`--accent/--warm`; Ferro `--text-mute` `#96a29c` (5,10:1); 4 `--peso-*`;
`--espaco-1…8` em grade de 4; raios 24/16/12/8; `--fio/--fio-forte`;
`--dur-resposta/transicao/celebra`; `shadow.rest/lift/edge`; saem
`--shadow-deep`, `--grad-brand`, `--glow`; linho `#f5f3ee` com recuo
`#f6f5f1` se amarelar na tela), `config/tests.py` (`test_tema_claro` com a
razão nova; pares ≥ 5,0 nos dois temas), `config/test_design_system.py`
(catracas descem; `font-weight` só nos 4 tokens; `--accent` proibido fora
de água; cor de pilar proibida em `.btn`; `.modo-foco` só redefine cor,
densidade e sombra), `config/settings` (`PWA_THEME_COLOR`).

- [ ] **Teste que falha:** contraste recalculado em bg/surface/surface-2/
  surface-3/brand-soft nos dois temas ≥ 5,0 para texto quieto; `_tokens()`
  lê o bloco Ferro (controle: sabotar um hex do Ferro → vermelho);
  `TETO_FONT_SIZE_CRU` e `TETO_ESPACO_CRU` menores que 120/247.
- [ ] Implementar → verde. QA 5 larguras × 2 temas nas 4 telas de T3.0.
  Commit com a tabela `medir.js` antes/depois.

#### T3.2 — fonte própria, condicionada a medir

> **17/09/2026 (CORTE, PR #8):** feito — Bodoni Moda (display, só em herói ≥ 20 px) + Karla (texto), 70 580 B (gate 260 KB), `tnum` nas duas medido com fontTools, quatro pesos, SW pré-cacheia. Não é a DM Sans deste item: a direção escolhida trocou a fonte.


**Origem:** DESIGN DV-T2 · **Classe:** C→B (após C-DIR) · **Arquivos:**
Create `static/fonts/DMSans[opsz,wght].woff2` + `LICENSE` (OFL); Modify
`static/css/app.css` §1 (`@font-face`, `font-display: swap`,
`font-optical-sizing: auto`, fallback `system-ui`), `push/assets.py`
(`VERSIONED`), `templates/pwa/sw.js` (precache); Test: `push/tests.py`.

- [ ] **GATE TÉCNICO antes de qualquer commit:** fontTools mede tamanho
  (latin+latin-ext) e presença de `tnum`; > 80 KB ou sem `tnum` ⇒ o item
  vira E e o app fica em `system-ui`.
- [ ] Teste: `sw.js` e `assets.py` concordam (o teste que já compara);
  QA: `document.fonts.check` verdadeiro a 390; h1 medido Windows × fallback.
  Commit.

#### T3.3 — famílias de cartão e componentes (com `ring.html` e `sparkline.html`)

> **17/09/2026 (CORTE, PR #9):** a quina é a folha (`--corte-g`/`--corte`/`--corte-p`) e o cartão é faixa sem sombra; famílias `.prato/.cartao/.nota` e `sparkline.html` NÃO nasceram — a direção resolveu a hierarquia por tipografia e superfície, não por família de caixa.


> **16/09/2026 (noite, N1):** só a MEDIDA — cartão dentro de cartão = 0 em sete rotas (`config/test_cartoes.py`). As famílias esperam três decisões de direção (fio no topo × esquerda; `.card` alias × reescrita; sombra do prato).


**Origem:** DESIGN DV-C + DV-K (cético 2 item 7) · **Classe:** B ·
**Arquivos:** Modify `static/css/app.css` §5 (`.prato` uma por tela, fio de
pilar 3 px, sem sombra; `.cartao` hairline raio 16 linhas 56/64; `.nota`
surface-2 raio 8; `.painel` + `--foco`; `.eyebrow`; `.metrica` unidade
colada; `.stat` + `.stat-grid`; `.tag`; `.rail` 2 alturas; `.card` alias de
`.cartao` durante a migração); Create `templates/partials/ring.html`,
`templates/partials/sparkline.html` (SVG inline do template, sem biblioteca;
colunas 64 px; meta tracejada; hoje na cor do pilar; `aria-label`; lista em
`<details>` "dia a dia"); Test: `config/test_design_system.py`.

- [ ] **Teste que falha:** `.card .card` = 0 em toda rota renderizada;
  `.prato` ≤ 1 por template; overlines/métricas por grep descem (16 → 1) e
  viram catraca; `sparkline.html` com 7 valores renderiza 7 `<rect>` e um
  `aria-label` com os números.
- [ ] Implementar → verde. Commit.

#### T3.4 — botões: seis variantes, uma escala de `:active`

> **17/09/2026 (CORTE, PR #9):** `.btn` com `--corte`, primário lima cheia; nada clicável é pílula (teste). As variantes `--tonal`/`--texto`/`--icone` não entraram: o contrato CORTE fecha a lista em primary/ghost/quiet/perigo/sm/block.


> **16/09/2026 (noite, N5):** parcial — `class="btn"` sem variante = 0 (lista fechada), `.mapa__area` na escala única, `is-carregando` em `<a class="btn">` (`data-arquivo` exclui o TCX). Restou: `--tonal`/`--texto`/`--icone`, alturas 52/48/44, "um primário por template" (inviável por página — ver `fatos-onda-3.md`).


**Origem:** DESIGN DV-B + PA-07 + CA-06 · **Classe:** B · **Arquivos:**
Modify `static/css/app.css` §10 (`.btn` + `--primary` 52 / `--tonal` 48 /
`--texto` 44 / `--perigo` contorno / `--icone` / `--sm`; uma regra
`:active .96`; uma de reduced-motion), `static/js/pwa.js` (`is-carregando`
em `<a class="btn">`), templates das 14 famílias; Test:
`config/test_design_system.py` (`test_pressing_anything_uses_the_same_scale`
mantido; `class="btn"` sem variante = 0; um `.btn--primary` por template).

- [ ] Teste que falha → implementar → verde. QA: alturas computadas ∈
  {52,48,44}; todo `<a>` com classe de card na lista de `:active`. Commit.

#### T3.5 — inputs: uma receita de campo, um foco

> **17/09/2026 (CORTE, PR #9):** campo e visto de escolha em folha; `.choice-list--dias → .segmented--envolve`. Sufixo de unidade e checkbox círculo 24 ficaram (backlog "Design / Onda 3").


> **16/09/2026 (noite, N2 de `2026-09-16-onda-3-noite.md`):** feito — foco `--brand` nos cinco controles, `--glow` anel de 1 px, `[aria-invalid]` no CSS e ids do `aria-describedby` em `field.html`. Restou: 52/raio 12/`--surface-2` no campo, sufixo de unidade, renome `.segmented--envolve`, checkbox círculo 24.


**Origem:** DESIGN DV-I + PA-06 · **Classe:** B · **Arquivos:** Modify
`static/css/app.css` §11 (52, raio 12, `--surface-2` OU `--fio-forte`
≥ .46 — nunca branco + .22, medido 1,58:1; foco = borda 2 px `--brand` em
todo controle; `[aria-invalid]` com mensagem colada; sufixo de unidade no
campo; `.choice-list--dias` → `.segmented--envolve`; checkbox de lista
círculo 24 em alvo 44), `templates/partials/field.html`, `accounts/forms.py`.

- [ ] Teste: `aria-invalid` ≥ 1 no CSS e no `field.html` em erro; contraste
  da fronteira ≥ 3:1 medido. Implementar; QA nos formulários a 320. Commit.

#### T3.6 — sprite em `base.html`, com medição e fora do shell offline

> **17/09/2026 (CORTE, PR #9):** a folha de recompensa na última série (`services.Placar`, `folha-sobe`, conta do zero, cascata 80 ms), `corte-abre` e `corte-desdobra`. Emoji → glifo nas conquistas continua pendente (backlog).


> **16/09/2026 (noite, N3):** feito — sprite na base fora do shell, traço 2 em cada `<symbol>`, ficha +2 939 B medidos (< +4 KB). Restou: emoji → glifo nas conquistas (3 desenhos + `card.js`), ponto duotone, chevron único.


**Origem:** DESIGN DV-S (cético 1 item 9; conflito 8) · **Classe:** B ·
**Arquivos:** Modify `templates/partials/icones.html` (~14 glifos, traço 2,
ponto duotone `fill: var(--cor-pilar)`), `templates/base.html`
(`{% if not offline %}{% include %}{% endif %}` — como o mapa),
`achievements/regras.py:81/188/203`, `achievements/models.py:116` (3 glifos
no lugar dos emoji), `static/css/app.css` (chevron único girando 240 ms).

- [ ] **Medir ANTES:** tamanho de ficha (2 e 7 exercícios), painel e
  execução em bytes (`scratchpad/medir.py`).
- [ ] **Teste que falha:** `mapa_de_areas.html` não contém `<use`; nenhum
  emoji em `templates/achievements`; `<symbol` do conjunto aparece UMA vez
  por página; o shell offline (`offline.html` servido pelo SW) NÃO contém
  o sprite.
- [ ] Implementar → verde. **Medir DEPOIS** e escrever no commit; se a
  ficha passar de +4 KB, o sprite vai só nas páginas que usam (`{% if %}`
  por `nav`). Commit citando "Três ausências no mapa" e "ficha 8,9 kB".

#### T3.7 — motion: três durações; keyframes órfãos com destino

> **17/09/2026 (CORTE):** `--mov-recompensa` (.45 s) e `--mov-cascata` (80 ms) entraram COM consumidor; `prefers-reduced-motion` desliga os três momentos novos; `nav.py movimento normal|reduzido` para fotografar movimento (o headless respondia `reduce`).


> **16/09/2026 (noite, N4):** feito — `varrer` e os quatro órfãos saíram, catraca de órfãos em zero, 760 → 750. `encher` ficou.


**Origem:** DESIGN DV-M · **Classe:** B · **Arquivos:** Modify
`static/css/app.css` (`varrer .9s` sai; `encher` ao abrir FICA — teste e
docstring; `serie-ok`, `serie-anel`, `descanso-acabando`, `esqueleto` ganham
consumidor na onda 6 ou saem; `font-weight: 760` da corrida editado com
razão), `config/test_design_system.py`.

- [ ] Teste: `test_the_bars_fill_from_zero_when_the_screen_opens` verde;
  durações cruas = 0 fora dos três tokens (catraca). Commit.

#### Fechamento da onda 3 (gate)

- [ ] C-DIR respondida; fontTools medido; suíte com catracas MENORES;
  contraste ≥ 5,0 nos dois temas; `medir.js` antes/depois anexado; QA 5
  larguras × 2 temas em Hoje/painel/execução/progresso/login; `check`;
  `makemigrations --check` (zero migration nesta onda); push; deploy
  provado (o CSS servido contém `--fio-forte`); `/saude/`; smoke visual em
  produção. Notificação sonora.

---

### Onda 4 — EXPERIÊNCIA POR TELA (9 tarefas, um commit publicável por tela; depende da onda 3)

Ordem obrigatória: T4.1 → T4.2 → T4.3 → T4.5 (PROGRESSO) → T4.4 (LEITURA)
→ T4.6 → T4.7 → T4.9 → T4.8 (só com C-ONB).

#### T4.1 — HOME em pele nova (+ C-HOME se aprovada)

**Origem:** DESIGN Home + UX UXA-05 + UXA-08 + CA-16 + CA-12 · **Classe:** B
(pele) / C-HOME (colapso) · **Arquivos:** Modify `templates/plans/today.html`,
`_agua.html`, `_area_promovida.html`, `plans/agora.py`, `static/css/app.css`,
`plans/tests.py`.

- [ ] Pele (B): prato AGORA com fio `--brand`; seção "Hoje" com `.metrica`
  48; `.stat-grid` água/treino; água = seção com fio `--agua`, sem cartão
  externo; ofensiva = stat `--chama`; cartão promovido com fio na cor do
  pilar; explicações em `.nota` + details.
- [ ] C-HOME (A): refeição da vez = único cartão aberto; demais = linhas 56
  com `<details>`; 3 mini-anéis. **Teste:** mesmos POSTs para registrar
  (agent-browser conta os pedidos); Home neutra continua na ordem canônica.
- [ ] Um `.btn--primary` por dobra; `.card .card` = 0; altura medida a 390
  antes/depois — só então a catraca `ALTURA_HOME_390` entra. QA 5 larguras
  × 2 temas. Commit.

#### T4.2 — EXECUÇÃO EM FERRO

**Origem:** DESIGN enxertos 1-6 + TREINO modo_foco + `--recem` (conflitos
2, 4, 11) · **Classe:** B · **Arquivos:** Modify `workouts/views.py:631-721`
(`modo_foco=True`), `templates/base.html` (`body class="modo-foco"` pelo
contexto), `templates/workouts/agora.html`, `_demonstracao.html`,
`_demonstracao_js.html`, `static/css/app.css`, `static/js/pwa.js`
(`navigator.vibrate(10)`; anima `data-de` com `?feita=N`), `workouts/tests.py`,
`config/test_design_system.py`.

- [ ] **Medir ANTES** y do CTA nas 5 larguras + 360×800 (d406fe0).
- [ ] **Teste que falha:** `body.modo-foco` só em execução e corrida em
  andamento (GET das rotas + grep: exatamente dois templates passam o
  contexto); `.modo-foco` só redefine cor/densidade/sombra (teste sobre o
  bloco); `?feita=N` fora de 1..20 ignorado; `CONSULTAS_DA_EXECUCAO = 20`.
- [ ] Implementar: cabeçalho sticky com eyebrow + rail 4 px `--folha`;
  nome 22/680 com alvo 44; tira de séries (feita `--folha`+✓, atual
  `--surface-focus`, pendente contorno); cockpit `display-foco`
  `clamp(3.5rem,18vw,4.5rem)` tabular com −/+ 56×56 (`type=number` e
  `name=` intocados); CTA sticky (T1.4) revestido; descanso = rail que
  esquenta em `--chama` nos últimos 10 s.
- [ ] **Capa de largura total (REVISÃO DE DECISÃO MEDIDA):** só depois de
  tudo acima, medir y do CTA com a capa 4:3 de largura total a 360×800 e
  390×844; se sair da dobra → a faixa de 96 px fica e a capa é D, com a
  medição no commit citando d406fe0.
- [ ] QA 320-1024 × 2 temas: `.series__esforco` uma linha; `iframes ≤ 1`;
  campos preservados ao abrir/fechar vídeo; `test_carga_offline_v2` verde.
  Commit.

#### T4.3 — PAINEL + FICHA

**Origem:** DESIGN + UX CA-05 + CA-09 + CA-14 + MOB-07 + TR-14 + CA-08 +
TR-09 + CA-06 + MC-18 (conflito 2: SEM thumb) · **Classe:** B · **Arquivos:**
Modify `templates/workouts/routine.html`, `ficha.html`,
`_item_da_ficha.html`, `static/css/app.css`, `config/test_nomenclatura.py`
(selo do hero == `rotulo` do card), `workouts/test_lista_de_hoje.py`.

- [ ] Painel: h1 28; prato "Treino de hoje" com fio `--folha`; `.stat` 3-up;
  anel só > 0 %; UM CTA; hero com `rotulo` A1/A2; sessões = `.cartao` de
  64 com chip da letra e `:active`; faixa SEG…DOM sem receita de botão,
  "DOM" inteiro a 320. Ficha: cabeçalho compacto (fio só se hoje), ordem
  h1 → `.stat` → CTA → lista, hint DEPOIS da lista; "4 × 6–10" tabular;
  `.tag` Principal só no principal (T2.5).
- [ ] Teste: um `.btn--primary` no painel; zero exercício listado no painel;
  ficha ≤ 15 consultas e sem `<img>` de exercício. QA 5 larguras × 2 temas.
  Commit.

#### T4.5 — PROGRESSO

**Origem:** DESIGN sparkline + prato do peso + UX PA-04/E09/CA-11/MC-09 +
UXA-07 · **Classe:** B · **Arquivos:** Modify `templates/plans/historico.html`
(usa `partials/sparkline.html` de T3.3), `plans/progresso.py`,
`achievements/` (resumo sem `avaliar`), `static/css/app.css`, `plans/tests.py`.

- [ ] Prato do peso (fio `--terra`) com `.metrica` 48 + "kg" colado + `.tag`
  de delta + pontos; registro de peso em details; Treino = 8 colunas
  `--folha`, Água = 7 `--agua`; vazio de refeições DENTRO da seção, abaixo
  dos blocos com dado; conquistas em `.stat-grid` coerente com /conquistas/;
  "82,3 kg" com espaço.
- [ ] Teste: teto 26 inalterado (`resumo` sem `avaliar`); vazio de refeições
  tem `card__head` e não é o primeiro bloco quando há peso. QA: altura das
  listas (1.104 → ~200 px). Commit.

#### T4.4 — LEITURA DO EXERCÍCIO (depois de T4.5)

**Origem:** DESIGN capa + UX MC-12 + "Como fui" (cético 1 item 8) ·
**Classe:** B · **Arquivos:** Modify `templates/workouts/exercicio.html`,
`workouts/views.py`.

- [ ] `.stat` para séries/reps/descanso com `nowrap` ("1:20 min" não
  quebra); papel de `item.grau`; CTA "Fazer este exercício" só se pendente;
  "← Ficha A1" (T1.14). **"Como fui" continua a lista crua** (8 datas, uma
  consulta); a sparkline entra POR CIMA, só com carga bruta (sem e1RM/volume
  — decisão de `progresso.py`), lida do mesmo dado, e a lista fica em
  `<details>` como fonte visível.
- [ ] Teste: `CONSULTAS_DA_LEITURA = 8` inalterado; `test_exercicio_leitura`
  verde. Capa: mesma régua de T4.2. QA. Commit.

#### T4.6 — HIDRATAÇÃO + ÁREAS + CONQUISTAS

**Origem:** DESIGN + UX E05 + E11 + MKT-14 · **Classe:** B · **Arquivos:**
Modify `templates/plans/hidratacao.html`, `areas.html`,
`achievements/templates`, `static/css/app.css`.

- [ ] Hidratação: `--agua` em 3 lugares; +250/+500/+750 tonais; "Somar" com
  forma de botão; 7 colunas com meta; KPIs em `.stat-grid`; "Sobre a meta"
  em `.nota` + details; zerar também aqui; erro de quantidade com a faixa e
  valor preservado. Áreas: glifos do sprite; tile principal = única
  `--surface-focus` + selo; "SUAS ÁREAS" → "MAIS ÁREAS". Conquistas:
  `.stat-grid`, fio `--chama` + data, Compartilhar tonal com estado.
- [ ] Teste: "não é prescrição" continua na página; frase de vazio
  idêntica. QA. Commit.

#### T4.7 — ENTRADA + ONBOARDING (pele)

**Origem:** DESIGN + UX MC-07/NOVO-10 + MKT-12 + MKT-09 + MKT-13 + MKT-06 +
MKT-08 + MKT-15 + Q-10 · **Classe:** B · **Arquivos:** Modify
`templates/accounts/*`, `static/css/app.css`.

- [ ] Um shell de entrada (`.auth--entrada` como o comentário promete); um
  cabeçalho (marca pequena + h1 28); Google tonal; checklist de senha que
  marca ao digitar; "E-mail" com hífen. Onboarding: sem cartão externo; UM
  componente de escolha (choice-card 2×2 com ícone; linhas 64 com check à
  direita); segmented com indicador; ícone só quando existe; "Os dois
  juntos" com frase distinta; nota de privacidade só se for verdade
  contratual.
- [ ] Teste: nenhuma tela anônima renderiza o convite (T1.10 continua);
  dois shells = 0. QA 5 larguras × 2 temas. Commit.

#### T4.9 — PERFIL + LISTA + CORRIDAS + EXCLUIR (pele)

**Origem:** DESIGN + UX MC-17 + E10 · **Classe:** B · **Arquivos:** Modify
`templates/accounts/perfil.html`, `plans/shopping.html`,
`workouts/corridas.html`, `templates/accounts/excluir.html`,
`static/css/app.css`.

- [ ] Perfil: cabeçalho com nome/iniciais; lista agrupada (`.cartao` 56
  rótulo/valor/chevron); metas em `.stat-grid`; Sair terciário, Excluir
  perigo. Lista: linha 56 com círculo 24 em alvo 44; corredor pegajoso;
  explicação em `.nota`. Corridas: `.stat` 3-up em prato `--brasa`; erro de
  GPS em faixa `--danger`; corrida em andamento em Ferro (`modo_foco`).
  Excluir: h1 28, ícone de alerta, perigo cheio só na confirmação.
- [ ] QA 5 larguras. Commit.

#### T4.8 — ONBOARDING EM TRÊS TELAS (só com C-ONB = B)

**Origem:** UX D1 + 2.2 + MKT-03 + Q-03/Q-04/Q-05/MKT-04 (cético 2 item 9)
· **Classe:** C→B · **Arquivos:** Modify `accounts/views.py` (wizard com
escala PRÓPRIA — `PassoV2`, nunca a de `onboarding_step` de hoje),
`accounts/forms.py`, Create `accounts/migrations/00xx_onboarding_v2.py`
(`AddField onboarding_v2_step`; `RunPython` só para `onboarding_step <
ONBOARDING_DONE`, mapeando 1..6 → passo v2 correspondente, sem tocar em quem
terminou), `templates/accounts/onboarding_*.html`,
`templates/workouts/routine.html` (cartão "seu plano está pronto"; pergunta
de experiência/divisão com prévia real por frequência),
`templates/plans/today.html` (sono/estilo `?origem=hoje`; prioridade a
partir do 2.º dia), `config/test_nomenclatura.py`, `accounts/tests.py`.

- [ ] **Teste que falha:** caminho feliz com 3 telas e 9 perguntas; para
  cada `onboarding_step ∈ {1..6}` a migration cai num passo v2 definido e
  NENHUM vira "terminado" por aritmética; quem terminou: `UPDATE = 0`; quem
  não responde experiência fica em teto 20 e o Perfil diz "não informada";
  `prioridade == ""` continua Home canônica; onboarding sem tabbar nem mapa;
  montagem monta dieta E ficha (T1.1).
- [ ] Implementar → verde. Sabotagem: mapear step 5 → DONE → vermelho. QA
  5 larguras. Commit. Migration provada sobre banco populado local.

#### Fechamento da onda 4 (gate)

- [ ] Por tela: suíte, QA 5 larguras × 2 temas, `medir.js` no commit,
  nenhum orçamento subiu, deploy, smoke da tela publicada. Ao fechar: Prova
  1 (sobreposição Mesa×Ferro a 390) e Prova 2 (lado a lado com Hevy/Yazio/
  Oura) em `docs/design-audit/`. Notificação sonora.

---

### Onda 5 — MOTOR EM TRÊS CAMADAS (4 tarefas + trabalho humano paralelo; 3 pushes)

Migrations só `AddField`, `UPDATE = 0`, ficha de todo mundo byte a byte
igual até 5c. Nenhuma decisão do dono (C-EQ desceu a B).

#### T5a — CATÁLOGO classificado; nove halteres inativos com padrão

**Origem:** TREINO EQ-elegiveis-derivado + EQ-taxonomia-padrao +
EQ-classificacao-dos-36 + EQ-requer-banco + L03-codigo + L03-loop +
EQ-nove-halteres-entram (cético 2 item 3) · **Classe:** B · **Arquivos:**
Modify `workouts/models.py` (`Exercise.objects.elegiveis()` = ativo ∧
`video_url` ∧ `animation_url` ∧ frames — derivado, sem booleano), Create
`workouts/migrations/0021_padrao_variante_banco.py` (só `AddField`:
`padrao` TextChoices fechado ~21, `variante`, `requer_banco`; `""` inerte),
Modify `workouts/data/exercises.json` (classificação dos 36: "multi-padrão =
padrão do grupo primário"; nove halteres com `active: false` + padrão e
variante), `workouts/management/commands/seed_workouts.py:100-125`
(`video_start/video_end` em `defaults` SÓ quando a chave existe; `null`
apaga de propósito), `workouts/services.py:1192/1742` (leem `elegiveis()`),
`workouts/test_video_direto.py` (:112 nomes oficiais vivos; :157 nenhum
vídeo em dois; :163 embed montável — continuam sobre `is_active=True`),
`test_treino_v4.py:323-330` (catraca `CONFERIDOS` por igualdade),
`test_capacidade_de_ambiente.py:36-43`, `BACKLOG.md:262-264`.

- [ ] **Teste que falha:** `elegiveis() == filter(is_active=True)` (catraca:
  divergir = alguém ativou sem mídia); todo ativo tem `padrao`; migration
  sobre banco populado: `UPDATE = 0`, folhas do grafo; equivalência de
  `create_routine` nos cinco perfis de QA antes/depois; seed: linha sem a
  chave não sobrescreve `video_start` existente; `#t=` só em `video`.
- [ ] Implementar → verde. **Sabotagem:** `:1192` → `is_active` → vermelho;
  `Exercise(is_active=True, video_url="")` em calves nunca prescrito;
  ativar um haltere no JSON → `elegiveis() == ativos` vermelho.
- [ ] Commits SEPARADOS: (1) migration + classificação; (2) nove halteres
  inativos (nenhuma ficha muda; leitura devolve 404). Decisão do loop
  registrada no BACKLOG. Gate + deploy (build roda `migrate` → seeds);
  smoke: ficha de um perfil de teste idêntica antes/depois.

#### T5b — MOTOR: `ParametrosDoMotor`, escada de substituição, veredito real

**Origem:** TREINO EQ-parametros-do-motor + EQ-encaixe-unico +
EQ-escada-obrigatoria + EQ-dedupe + EQ-unilateral + EQ-variante +
EQ-conferencia-unica + EQ-degrada-com-aviso + EQ-veredito-pelo-motor-real +
PR-tempo-curto-contrato-minimo (cético 2 item 8) · **Classe:** B ·
**Arquivos:** Create `workouts/parametros.py` (`ParametrosDoMotor` frozen;
`parametros_de(user)` ÚNICO leitor de Profile/TrainingDay em `workouts`),
`workouts/ambientes.py` (`Permitidos`; `substituir_por_equipamento` pura:
escada padrão+variante → padrão → grupo+composto → grupo; ordem por NOME;
dedupe; cópia não salva com a dose do modelo; órfão registrado;
`permitidos=None` ⇒ no-op byte a byte); Modify
`workouts/services.py:169-200/1135-1268/1618-1805` (`_prescricao_confere`
compara `(exercise_id, sets, rep_min, rep_max, rest)` contra a prescrição
com os MESMOS parâmetros; o subconjunto contra o catálogo cru SAI
`:1770-1781`; `aviso_de_equipamento` com partes tipadas — "Sem máquina, leg
press virou afundo", nunca "treino pior"), `workouts/test_capacidade_de_ambiente.py`
(`veredito_do_motor(permitidos)` recomputado e congelado por igualdade;
`test_o_motor_nao_le_equipamento` reescrito como positivo),
`test_prescricao_referencia.py`, CLAUDE.md (SÓ "o motor não lê equipment"
invertido, com a razão).

- [ ] **Teste que falha:** anti-laço — ficha com substituto + dez
  `sync_active_routine` ⇒ zero remontagem (sabotagem: restaurar a
  comparação crua → laço); congelamento `permitidos=None ==
  Permitidos(todos)` nos cinco perfis; controle positivo `{DUMBBELL,
  BODYWEIGHT}` muda ≥ 1 item; textual: `services.py` sem `user.profile`
  fora de `parametros.py`; veredito congelado (dar vídeo a "Agachamento
  goblet" no teste ⇒ muda); "Rápido" nunca perde o único empurrar/puxar/
  perna; controle positivo de `rest_seconds` na conferência; routine ≤ 25.
- [ ] Implementar → verde. Gate + deploy; smoke: ficha idêntica antes/depois.

#### T5c — PERFIL: presets por equipamento, não suportado riscado com a razão

**Origem:** TREINO EQ-perfil-booleans + PE-teste-nao-oferece-reescrito +
EQ-pergunta-no-passo-3-gate + EQ-abcde-sob-restricao + FI-chip-equipamento +
FI-notas (C-EQ → B, cético 1 item 3) · **Classe:** B · **Arquivos:** Create
`accounts/migrations/0032_equipamento_do_perfil.py` (cinco booleans default
TRUE + `equipamento_confirmado` FALSE; preset é projeção, não coluna);
Modify `accounts/models.py` (`permitidos_de(profile)` devolve `None` com
tudo TRUE — no-op é VALOR), `accounts/forms.py:444-605` (presets Academia ·
Casa com halteres · Só o corpo + details "personalizar"; `save` grava
`confirmado=True` só quando algo foi postado), `templates/accounts/perfil.html`
(preset NÃO SUPORTADO riscado com a razão de `Veredito.sem_substituto`;
PARCIAL entrega ficha degradada com aviso nomeando o que faltou),
`onboarding_3.html` (a pergunta só entra quando existe preset além de
academia PARCIAL ou SUPORTADO — `presets_oferecidos()`),
`workouts/services.py` (`split_for` sob restrição: ABCDE → ABCD/ABC2 EM VOZ
ALTA por `divisao_explicada`, nunca sessão abaixo do piso),
`templates/workouts/_item_da_ficha.html` (chip `get_equipment_display`
medido a 320; `plan.notes` visível quando há aviso), `workouts/test_capacidade_de_ambiente.py:566-633`
(`OProdutoNaoPrometeAmbienteTests` invertido NO MESMO commit), CLAUDE.md
("NÃO EXISTE CAMPO DE AMBIENTE" reescrito aqui, e só aqui).

- [ ] **Teste que falha:** `UPDATE = 0` sobre banco populado; passo 3 em
  branco não grava `confirmado` nem altera booleans; postar `casa_halteres`
  grava os cinco certos; trocar `tem_maquina` remonta a ficha UMA vez e a
  nota nomeia a troca; NÃO SUPORTADO nunca prescreve (piso) e aparece
  riscado com a razão; ABCDE sob restrição cai para ABCD com `divisao_explicada`
  dizendo por quê; `presets_oferecidos()` com o veredito de hoje ⇒
  `TrainingForm` sem o campo (controle: sabotar o veredito → campo aparece);
  substituto nasce sem carga sugerida; chip ≥ 11 px sem rolagem a 320.
- [ ] Implementar → verde. QA 5 larguras no Perfil e na ficha. Gate +
  deploy; smoke: trocar `tem_maquina` num perfil de teste em produção
  remonta uma vez e a nota nomeia a troca.

#### T5h — CURADORIA HUMANA (paralela desde T5a; trabalho do dono)

**Origem:** TREINO L03-curadoria + EQ-decimo-de-costas +
VI-autoplay-safari-pwa · **Classe:** E (este ambiente não assiste vídeo) ·
**Arquivos:** `workouts/data/exercises.json`, `animacoes.json`,
`media_map.json`, `workouts/test_video_direto.py`.

- [ ] Tabela dos 35 Shorts entregue ao dono (`scripts/curar_videos.py`
  lê o CSV preenchido); cada `video_start/video_end` entra em `CONFERIDOS`
  (o teste fica vermelho para ser ATUALIZADO, não afrouxado); trocar o vídeo
  do Agachamento livre e esvaziar `VIDEO_SEM_CARGA_CONHECIDO`; vídeo +
  animação + fotos para os nove halteres — o veredito congelado acusa cada
  um que vira elegível e `presets_oferecidos()` acende a opção sozinho;
  décimo de costas; autoplay no iPhone. Cada item publicável isolado.

#### Fechamento da onda 5 (gate)

- [ ] Suíte após cada sub-onda; migrations provadas (`UPDATE = 0`, folhas);
  equivalência nos cinco perfis; deploy (build roda `migrate` → seeds →
  `podar_operacoes`); smoke por sub-onda como acima; CLAUDE.md no mesmo
  commit de cada sub-onda. Notificação sonora.

---

### Onda 6 — POLIMENTO (4 tarefas, 1 push; depende da onda 4)

#### T6.1 — microinterações: `--recem`, háptico, rail, `.tag` PR, loading em `<a>`, confirmação destrutiva

**Origem:** DESIGN 9.4 + UX CA-18 + TR-12/PA-10 + MC-10 + TR-13 ·
**Classe:** B · **Arquivos:** Modify `static/css/app.css`, `static/js/pwa.js`,
`static/js/card.js:307` (a Promise deixa de ser descartada: "gerando…/
salva/cancelado"), `templates/**` (`.acao-perigosa` para água e excluir
conta; `aria-busy` em card-destino até `pageshow`; "abrir" → chevron em
`[open]`; "pular" descanso persistido; um formato de relógio desde o
primeiro paint).

- [ ] Teste: keyframes sem consumidor = 0 (catraca); `card.js` trata
  rejeição (teste lendo o arquivo); nenhum `.btn` sem `is-carregando` em
  navegação de card. QA. Commit.

#### T6.2 — UX 3.x restantes

**Origem:** UX CA-08 + MOB-13 + CA-17 + MKT-13 + MKT-15 + CA-12 + MC-16 +
P3 diversos · **Classe:** B · **Arquivos:** `templates/**`, `static/css/app.css`.

- [ ] Pastilhas e tiles sem receita de botão; botão de água unificado nas
  duas telas; marca inerte em `/conta/senha/`; Exportar com um rótulo e
  confirmação; "você saiu"; Registrar A/B com a mesma variante; ofensiva com
  porta ou sem moldura; textos do Django substituídos; 0×12 em polia com
  aviso brando. Teste: `TouchTargetTests` 0 alvos < 44×44; nenhum elemento
  não interativo com classe de botão. Commit.

#### T6.3 — limpeza de CSS e a migração final dos crus

**Origem:** DESIGN limpeza · **Classe:** B · **Arquivos:** Modify
`static/css/app.css` (`.esqueleto`, `.set-row`, `.choice-list--inline`,
`.pill--warm`, `.dias-com-registro` saem; duplicatas; seções 17/20 ausentes
e 28 duplicada; os 247 espaçamentos e 120 tamanhos crus caem no degrau mais
próximo — lote próprio com captura antes/depois), `config/test_design_system.py`.

- [ ] Catracas no piso novo (só descem); captura 320/390 × 2 temas antes/
  depois; classes sem consumidor = 0. Commit.

#### T6.4 — documentação: CLAUDE.md, BACKLOG, memória

**Origem:** CRUZADO (conflito 9) · **Classe:** B · **Arquivos:** `CLAUDE.md`,
`BACKLOG.md`, memória do projeto.

- [ ] Reescrever: a aba Áreas acende por destino; o mapa é `<details>` mais
  aba Áreas; 70 tokens e 89 % de sombras já não batem; por que o sprite
  entrou em `base.html`; por que uma webfont não é framework; "Design" com
  as três famílias de cartão e a regra de três das cores; docstring de
  `preferencia_muda_a_divisao`; BACKLOG:675-683 (poda) fechado. Revisão de
  leitura contra o código (grep dos parágrafos citados). Commit.

#### Fechamento da onda 6 (gate)

- [ ] Suíte; catracas no piso; captura 5 larguras × 2 temas; deploy; smoke;
  CLAUDE.md conferido contra o código. Notificação sonora de fechamento da
  campanha.

---

## 5. D e E

**D — refutado ou decidido contra (não volta sem medição nova que cite o parágrafo):**

| id | motivo |
|---|---|
| C-RESET (B): carga menor no retorno 0,9×/0,8× e RESET −10 % | Decisão do dono de 13/09 ("DESCER fica fora"); 0,9/0,8/10 % são calibração sem RCT (Bosquet 2013 dá os dias, Mitter 2022 o ruído). **Reabre SÓ** com 4-6 semanas de `medir_progressao` mostrando "retomar ≥ 28" e "estagnado" por mês E o dono revendo a decisão de 13/09 — nunca por sabotagem de teste. |
| C-FORCA: objetivo de treino "força" (`Profile.objetivo_treino`) | D nesta campanha, registrado com custo: campo novo, catálogo em 3-6 reps (hoje nenhum), reverter o descanso de 26/08, sessões mais longas. Evidência que sustenta a diferença: Currier 2023; ACSM 2026. |
| AD-descer-por-reps-abaixo-do-piso | Idem 13/09; reabre só junto com C-RESET. |
| SUBIR_DOBRADO / teto 10 % / referência em 4 datas | Muda três regras da docstring de `proxima_carga` (:2245-2270) — é E até o número existir, e C se subir. |
| L11 descanso 80→90 s | Decisão de 26/08; Singer 2024: indiferença acima de 90 s. Só acoplado a C-FORCA. |
| L02 vídeo no topo 38vh; capa de largura total sem medição | Refutado com conta (391 px > 371, d406fe0). A capa só entra com y do CTA medido a 360×800 e 390×844. |
| L09 `SPLIT_BY_FREQUENCY[4] = AB` / 7.º dia descanso | No-op; quebra o contrato 4/4/3/3; o 7.º dia é dado da pessoa. |
| L14 revisão semanal + conquista + retenção | Remonta a ficha; conquistas existem; `gestao/tests` proíbe "retenção". Sobra a linha "X de Y dias" (T2.5). |
| L16 "Trocar por…" no meio do treino | Sem sistema de troca; reavaliar (não reabrir) depois de 5b. |
| L12-2 trava por OCORRÊNCIA como quarta trava | "O aparo tem TRÊS TRAVAS, e as três vieram de medição"; "em quatro dias a segunda passagem de A é SUBCONJUNTO". E até a matriz provar. |
| RIR-experiencia-nao-prediz | Halperin β = −0,006; Remmert 2023. |
| RIR-nao-decide-volume / volume por pump, dor, prontidão | Sem ensaio; A-16 (determinístico); Hickmott 2022. |
| EQ-pesos-disponiveis; EQ-inferir-ambiente/nível/prioridade do uso; EQ-midia-aprovada-booleano; EQ-rotacao-por-sessao | Preferência sem consumidor; "uso não é intenção declarada" (0024); camada 3 é derivada; plano é retrato (Kassiano 2022). |
| PR-full-body-por-nivel; PR-regra-por-sexo/ciclo; PR-aderencia-redeclarar-dias | Refutados duas vezes; Refalo/Nuckols 2025, Colenso-Semple 2023; frequência observada nunca altera `TrainingDay`. |
| AD-deload por calendário/reativo; AD-e1rm-tolerancia | Coleman 2024; Pancar 2026; Bell 2023/2024 sem RCT; sem 1RM no app. |
| FI-no-lugar-de-coluna; EX-fileira-de-exercicios-no-topo; fallback `pedido or atual` | Coluna sem consumidor; "a execução mostra UM exercício"; escolha estrita com 404. |
| Miniatura do exercício na ficha (56×56) | TREINO: regressão; CLAUDE.md: ficha é preparação com orçamento medido. |
| Enxertos recusados de A e B: display 300; cartão a 1,06:1; renomear `--text-mute`; `--surface-focus` escura na Home; condensada; canto reto; família `*-viva`; mini-bloco escuro na Home | Contradizem `test_o_destaque_nao_depende_so_da_cor_de_fundo` e a doutrina brand/folha. O regime é por TELA. |
| Mascote; anatomia 3D; utilitárias `.mt-4`; `:has()`; `order` no flexbox | "A pessoa é a protagonista"; memória do 3D; CLAUDE.md. |
| "Continuar de onde parou" da Home para a ficha; nome obrigatório no cadastro | Etapa a mais no meio do treino; consumidor único tolera vazio. |

**E — lacuna real, declarada:**

| id | o que falta |
|---|---|
| C-SOBRA (chips "daria mais quantas?") | O NÚMERO: ≥ 30 % de SUBIR→SUBIR com parada exata em rep_max, em 4-6 semanas de `medir_progressao`. Preferência fechada já aponta (A); só vira C se cruzar. |
| SUBIR_DOBRADO, teto 10 %, referência 4 datas; calibrações 21/28 dias, 3 sessões, +1 rep, 180 dias/24 datas, 30 % | Direções vêm da literatura; números são de praticante; `medir_progressao` é o instrumento. |
| L03-curadoria dos 35 Shorts; nove halteres; décimo de costas; autoplay Safari PWA | 0/35 conferidos; este ambiente não assiste vídeo (T5h, humano). |
| L08 registrar série sem recarregar (fetch) | Só com o número de T2.4 (POST→302→GET em 3G); identidade continua do servidor. |
| EQ-faixa-do-substituto; EQ-troca-manual-customizada; PR-degrau-kg-por-exercicio; AD-teto-em-dois-passos; AD-volume-por-calendario | Dependem do veredito real (5b), de mídia, ou de dado de uso. |
| Tamanho e `tnum` da DM Sans; linho sob o clarão; Home ≤ 1.900 px; Progresso ≤ 1.600 px; tema escuro | [HIPOTÉTICAS] até fontTools, captura na tela e `medir.js`; o escuro nunca foi capturado (T3.0). |
| Ofensiva cobrando treino de quem removeu todos os dias | Lida no código; T1.1(c) responde no navegador. |
| Quantas contas têm ≥ 65 anos; se "mesmo passando de N" muda comportamento; veredito de hoje | Podem ser zero; entram como função pura ou frase; o veredito só é conhecido em 5b. |
| Safari/iPhone, teclado virtual, OAuth Google, e-mail real, push concedido, GPS real, folha nativa de compartilhamento, produção além de GETs | Não provados por nenhuma auditoria; QA manual no aparelho, declarado. |

---

## 6. Regras de execução

1. **Nunca `git add -A`.** Sempre por caminho. `artifacts/` (317 MB) NUNCA
   entra; `.agents/` e `AGENTS.md` não são deste plano e ficam fora até o
   dono decidir; `docs/ux-audit/` entra em T0.2 depois de conferido.
2. **Conta demo intocada.** QA local na conta 1176 (dados restaurados ao
   fim; zero `ExerciseLog` dela ao terminar cada onda); em produção, só
   GETs no demo e escritas num perfil de teste próprio, nunca no demo.
3. **Notificação sonora** (tan-tan-tan-TAAAN + banner, `scratchpad/notificar.sh`)
   ao fechar cada onda (deploy provado + smoke) e sempre que uma decisão C
   for necessária — C-DIR, C-HOME, C-ONB, ao fim da onda 2b.
4. **Arquivos serializados** (cabeçalho): um subagente por vez. Subagente só
   em tarefa de arquivos disjuntos, com contrato de propriedade escrito.
5. **Todo teste novo é sabotado** com controle positivo antes do commit, e a
   sabotagem fica registrada (`scratchpad/sabotagem_ondaN.txt`). Teste que
   passa pelo motivo errado é o defeito que a régua existe para impedir.
6. **Toda decisão medida citada** no commit que a revê (d406fe0, 30/08,
   26/08, 13/09, "TRÊS TRAVAS", "ficha 8,9 kB", `proxima_carga`).
7. **Catracas só descem.** Toda edição de `test_design_system`/`test_tema_claro`
   leva a razão escrita e o número novo menor.
8. **Orçamentos de consultas não sobem** sem medição escrita no commit.
9. **Nenhum `:has()`, nenhum `next` livre, nenhum campo novo no POST da
   fila, nenhuma migration que não seja `AddField`** — e toda migration
   provada com `UPDATE = 0` sobre banco populado local antes do push.
10. **O `pre-push` roda a suíte completa (~27 min)** — não contornar; push
    por onda, commits por unidade dentro dela.
11. **Deploy provado por sinal observável** (string no HTML/CSS servido,
    rota nova respondendo), depois `/saude/`, depois smoke. Monitor externo
    continua em `/saude/vivo/`.
12. **Linha + âncora textual** em toda referência de código deste plano;
    ao executar, conferir a âncora — as linhas envelhecem.

---

## Self-review

- **Cobertura dos briefs:** UX P1-01…P1-13 → T1.x; P2/P3 → onda 2b e 6;
  seções 10-12 → T2b.2, C-HOME, C-ONB/T4.8. TREINO ONDA-0 → T1.5; AD-* → T2.1-
  T2.3 (v1) e E; RIR/PR/EX → T2.2, T2.5-T2.7; EQ-* → T5a-T5c; MEDIR/RE-* →
  T2.4; L03/VI → T5h. DESIGN DV-T1/T2/C/K/B/I/S/M/PROVA → onda 3;
  DV-P0.2 → T2b.6; telas → onda 4; limpeza → T6.3.
- **Céticos:** 21 correções aplicadas, 1 premissa recusada com verificação
  (§0). Nenhuma sugestão ficou sem resposta.
- **Placeholders:** `00xx` em T4.8 é o próximo número livre de `accounts/migrations`
  no momento da execução (após `0032` de T5c, se a onda 5 vier antes — a
  ordem entre 4.8 e 5c é a das decisões, e o executor confere).
- **Consistência:** `sync_active_routine` só atrás de `has_training_days`
  (T1.1); `?de=`/`?feita=`/`?origem=`/`?extra=` sempre lista fechada;
  `sparkline.html` nasce em T3.3 e é usada em T4.5 antes de T4.4;
  `modo_foco` escrito por `base.html` em exatamente dois templates; a faixa
  de 96 px é o padrão e a capa é revisão medida (T4.2/T4.4); "elegível"
  nunca substitui "ativo" nas guardas (T5a); CLAUDE.md invertido em duas
  etapas (5b/5c).
- **Independência das ondas:** 0, 1, 2 e 2b não dependem de decisão
  nenhuma e são publicáveis sozinhas; 3 depende de C-DIR; 4.1 de C-HOME
  só na metade do colapso; 4.8 de C-ONB; 5 de nenhuma.
