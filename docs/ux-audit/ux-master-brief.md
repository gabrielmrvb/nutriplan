# NutriPlan — Brief mestre de UX

Auditoria de 14/09/2026 (segunda-feira), servidor local `127.0.0.1:8000`, Chrome 153 headless por CDP, viewports 320×568 · 375×667 · 390×844 · 430×932. Onze frentes (usuário novo, Alimentação, Treino, Progresso/Áreas/Perfil, mobile, estados e erros, cards e alvos, microcopy, mercado, perguntas do onboarding, céticos) sobre a conta recorrente `qa-execucao@local.invalid` e nove contas descartáveis `*@ux-audit.invalid`. Nada foi editado no código.

Vocabulário de evidência: **[OBSERVADA]** (vista no navegador), **[LIDA NO CÓDIGO]**, **[HIPOTÉTICA]**. Só entra na seção 5 o que foi reproduzido por um segundo auditor cético; o que não foi conferido por ele fica marcado como *não reproduzido*. Sobreposições com os workflows paralelos estão marcadas **CROSS-WORKFLOW: TRAINING** (motor/prescrição) e **CROSS-WORKFLOW: DESIGN** (paleta, tipografia, receita visual) — este brief não decide nada nesses dois territórios.

Requisitos já fechados pelo dono e **confirmados cumpridos** [OBSERVADA]: mobile-first; painel de Treino com cards A/B/C e sem lista gigante; "Começar treino" no painel abre a ficha; cada exercício da ficha abre a página do exercício sem registrar nada; vídeo na página do exercício e na execução; abrir/fechar o vídeo não navega, não entra no histórico e não perde carga/reps digitadas; barra de baixo com quatro itens (Alimentação · Treino · Progresso · Áreas) e Perfil dentro de Áreas.

Screenshots: os dos P1 confirmados e das telas-chave estão em [`screenshots/`](screenshots/) (38 arquivos). Os demais (cerca de 400) ficam em `artifacts/ux-audit/<sessão>/`, fora do repositório.

---

## 1. Mapa completo do app

Legenda: **[A]** = aba acesa na barra de baixo; **←** = o que o link visível de "voltar" faz; **⌫** = para onde o botão voltar do navegador leva (bfcache restaura estado em todas as telas testadas).

### 1.1 Anônimo

| Tela | URL | De onde se chega | Para onde vai | ← / ⌫ | Barra |
|---|---|---|---|---|---|
| Entrar | `/conta/entrar/` | qualquer URL protegida (302 com `?next=`), "Entrar" do cadastro, "Voltar para entrar" da recuperação, logout, exclusão de conta | `/` (ou `next`); "Esqueci minha senha" → `/conta/senha/`; "Criar agora" → `/conta/cadastro/`; "Continuar com Google" (não testado); marca NutriPlan → `/` → 302 de volta para entrar | ⌫ só | sem barra; convite de instalação fixo no rodapé (P1) |
| Cadastro | `/conta/cadastro/` | "Criar agora" | `/conta/onboarding/1/`; "Entrar" → entrar | ⌫ só | sem barra; convite de instalação (P1) |
| Recuperar senha | `/conta/senha/` → `/conta/senha/enviado/` | "Esqueci minha senha" | enviado → "Voltar para entrar" | marca NutriPlan → `/` → entrar (**sai do fluxo**, P3) | sem barra |
| Redefinir senha | `/conta/senha/redefinir/<token>/` | e-mail | entrar | — | não testado (SMTP) |
| Demo | `/demo/` e dez telas | **nenhum link anônimo leva aqui** (P2 MKT-07) | capa sem "Entrar"/"Criar conta" por decisão (`demo/views.py`) | — | própria |
| 404 / 403 / CSRF / offline | — | — | "Ir para o dia de hoje" → `/` | — | "N" solto no lugar da marca (P2 E06) |
| Privacidade / Termos | `/privacidade/`, `/termos/` | rodapé | — | — | — |

### 1.2 Onboarding (conta criada, `onboarding_step < 7`)

Toda URL do app redireciona ao passo pendente; pular passo por URL devolve ao passo certo [OBSERVADA]. Sem barra de abas nem mapa de áreas (`sem_tabbar`), por decisão do CLAUDE.md.

| Passo | URL | Campos | Vai para | Voltar |
|---|---|---|---|---|
| 1 Seus dados | `/conta/onboarding/1/` | sexo (segmentado), nascimento, altura, peso | 2 | — |
| 2 Seu objetivo | `/2/` | objetivo (4 cartões), rotina (4 cartões) | 3 | 1 |
| 3 Sua rotina | `/3/` | dias da semana (chips, opcional), experiência (rádio), acorda/dorme (pré-preenchidos 07:00/23:00) | 4 se ≥ 3 dias, senão 5 | 2 |
| 4 Sua divisão | `/4/` | 1 / 2 / 3 grupos por dia (cartões) | 5 | 3 |
| 5 Sua comida | `/5/` | cardápio (3 cartões), restrições (4 caixas) | 6 | 4 ou 3 |
| 6 Prioridade | `/6/` | 5 caixas de interesse + 6 rádios "qual vem primeiro" | tela de montagem (700 ms) → `/` | 5 |

Em **modo edição** (`Editar` do Perfil, `?origem=treino` do painel) o mesmo template mostra "Voltar" → origem e "Salvar" → origem com flash "Alterações salvas." — correto — mas mantém a barra "Passo N/6 · X%" (P2 PA-02).

### 1.3 Logado (`onboarding_step == 7`)

| Tela | URL | Pergunta que responde | De onde se chega | Para onde vai | ← visível | [A] |
|---|---|---|---|---|---|---|
| **Hoje** | `/` | "o que faço agora" | barra, marca NutriPlan, "Ir para o dia de hoje", "Voltar para o cardápio", Recalcular metas (do Perfil) | AGORA → `#slot-N` ou `/treino/agora/` (**P1**); água `#hidratacao`; "Registros de hoje…" → `/hidratacao/`; Lista de compras; Peso → POST `/conta/peso/`; Entender metas (details); Dados do cálculo → "Editar" → `/conta/perfil/`; Recalcular → POST `/recalcular/`; Lembretes (push); área promovida → `/treino/`, `/treino/corridas/`, `/historico/` | — | Alimentação |
| **Treino (painel)** | `/treino/` | "como é a minha semana" | barra, "Abrir a ficha da semana", "← Treino" da ficha e do exercício, "Ver minha semana", "Ver o treino" (conquistas), "Abrir o treino de hoje" (progresso) | "Começar treino"/"Continuar de onde parou" → ficha de hoje; "Ver ficha do Treino A" → **mesma** ficha; cards A1/B/C/A2 → `/treino/ficha/<id>/`; Detalhes → "Editar" → `/conta/onboarding/3/?origem=treino`; Compartilhar (canvas); Exportar → `/treino/exportar/saude.tcx` | — | Treino |
| **Ficha** | `/treino/ficha/<id>/` | "o que vou fazer hoje" | painel (3 portas), "← Ficha" e "Ver o treino completo" da execução | nome → `/treino/exercicio/<id>/`; "Fazer"/"1/4"/"Concluído: 4/4" → `/treino/agora/?exercicio=<id>` (só no dia); "Continuar de onde parou" → execução do próximo pendente | "← Treino" → `/treino/` (correto: é o pai) | Treino |
| **Exercício (leitura)** | `/treino/exercicio/<id>/` | "como se faz" | nome na ficha, título sublinhado na execução | ver vídeo (inline); Músculos trabalhados (2.º iframe, P2); "Continuar de onde parou"/"Fazer agora" → execução deste exercício (**inclusive concluído**, P1 TR-01) | "← Treino" → `/treino/` (**pula a ficha**, P2) | Treino |
| **Execução** | `/treino/agora/[?exercicio=<id>]` | "estou fazendo, e agora" | AGORA da Home, "Fazer" da ficha, "Depois" na própria tela | POST `/treino/agora/serie/`; desfazer; "Depois · próximo" → `?exercicio=`; título → leitura; "Ver o treino completo" → ficha; id inválido → 404 estrito | "← Ficha" → `/treino/ficha/<id>/` (correto) | Treino |
| **Corridas** | `/treino/corridas/` | — | Áreas, área promovida | "Começar corrida" (GPS); POST `/treino/corridas/salvar/` | **nenhum link de volta** (P3) | Áreas |
| **Progresso** | `/historico/` | "como estou indo" | barra, área promovida | peso → POST `/conta/peso/` (PRG, empilha histórico P2); "Ir para o dia de hoje" → `/`; "Abrir o treino de hoje" → `/treino/`; "Registrar o primeiro copo" → `/hidratacao/`; "Ver todas" → `/conquistas/` | — | Progresso |
| **Conquistas** | `/conquistas/` | — | Progresso ("Ver todas"), Áreas, Perfil ("Minhas conquistas") | Compartilhar (canvas); "Ver o treino" → `/treino/` | **nenhum link de volta**; aba acende **Áreas** mesmo vindo do Progresso (P3 PA-05) | Áreas |
| **Áreas** | `/areas/` | "de que o app é feito" | barra | Corrida, Hidratação, Conquistas, Lista de compras, Perfil (tiles inteiros são `<a>`) | — | Áreas |
| **Hidratação** | `/hidratacao/` | — | Áreas, "Registros de hoje…" da Home, "Registrar o primeiro copo" | +250/+500/+750, Outra quantidade, desfazer (POST `/agua/` com `de=hidratacao`); **não tem zerar** (Home tem) | **nenhum link de volta**; cada POST empilha histórico (P2 PA-03) | Áreas |
| **Lista de compras** | `/lista-de-compras/[?opcao=A\|B]` | "o que comprar" | Home, Áreas | marcar (fetch, estado absoluto); Seus itens → POST (redirect `#seus-itens`, P1 E03); "Voltar para o cardápio" → `/` (topo, não `#cardapio`, P3) | — | Alimentação |
| **Perfil** | `/conta/perfil/` | utilitário | Áreas, "Editar" de Dados do cálculo | 6× "Editar" → `/conta/onboarding/N/` (modo edição); Recalcular → POST `/recalcular/` → **Home** (P3 PA-09); Minhas conquistas; Trocar senha → `/conta/senha/trocar/`; Exportar → POST `/conta/exportar/` (JSON); Sair → POST `/conta/sair/` (confirm nativo) → entrar; Excluir → `/conta/excluir/` | — | Áreas |
| **Trocar senha** | `/conta/senha/trocar/` | — | Perfil | Perfil | "Voltar ao perfil" | **nenhuma aba** (P3) |
| **Excluir conta** | `/conta/excluir/` | — | Perfil | senha certa → entrar com flash; Cancelar → Perfil | — | sem barra (correto) |

### 1.4 Barra de baixo (quatro itens) e sincronia

Alimentação → `/`, Treino → `/treino/`, Progresso → `/historico/`, Áreas → `/areas/`. Acende por **destino** (decisão do CLAUDE.md): Treino nas quatro telas de treino; Áreas em Corridas, Hidratação, Conquistas e Perfil; Alimentação na Lista de compras; **nenhuma** em Trocar senha. 71×54 a 320 px, 84×54 a 390, rótulo 11,2 px sem corte, `safe-area-inset-bottom` aplicado — sem defeito em 14 telas × 4 larguras [OBSERVADA].

### 1.5 Onde "voltar" está errado (resumo; detalhe na seção 4)

- Exercício → "← Treino" vai ao painel, não à ficha de onde a pessoa veio (**P2**, seis auditores).
- Hidratação e Progresso: cada registro empilha uma entrada; quatro registros = cinco "voltar" para sair (**P2** PA-03).
- Marca NutriPlan em `/conta/senha/` tira a pessoa da recuperação (P3).
- Corridas, Hidratação, Conquistas: sem link de volta próprio; só a barra ou o gesto do sistema (P3).

---

## 2. Análise do onboarding

### 2.1 Medidas [OBSERVADA]

- **Telas até a Home:** 3 de conta (entrar, cadastro, e opcionalmente recuperação) + 6 passos (5 quando não há ≥ 3 dias de treino) = 9 telas no caminho feliz do cadastro.
- **Campos obrigatórios/escolhas:** 14 (nome, e-mail, senha, confirmação, sexo, nascimento, altura, peso, objetivo, rotina, dias*, divisão*, cardápio, prioridade) + 3 opcionais (experiência, acorda/dorme, restrições). *dias é opcional e divisão é condicional.
- **Toques no caminho feliz:** ~22. **Tempo:** 3 a 4 minutos digitando com calma.
- **Alturas a 390×844:** passo 1 cabe (Continuar em y=607); passo 2 1.038 px; passo 3 1.130 px; passo 4 1.067 px; passo 5 1.114 px; **passo 6 1.465 px** (Concluir em y=1.279, onze controles antes dele). A 320×568 nenhum passo rola na horizontal; passos 4 e 6 chegam a 1.343 px.
- **Pontos de abandono prováveis:** passo 4 (jargão "Peito+Tríceps+Ombro | Costas+Bíceps+Antebraço" para quem acabou de se dizer iniciante); passo 6 (cinco pilares listados duas vezes, botão fora de duas telas); **a primeira Home**, que para quem elegeu Treino abre dizendo "Hoje não tem treino na sua ficha" num dia marcado como de treino (**P1**, reproduzido quatro vezes por céticos).
- **Primeiros 5 minutos:** a pessoa entende o produto (cadastro diz "os dados da dieta vêm no passo seguinte"; cada passo explica para que serve); recebe algo útil já na Home (meta em kcal, macros, cardápio A/B com horários, água, lista de compras) — o "aha" alimentar é imediato; sente personalização (cardápio vegano de verdade, selo "sua área", horários seguindo a janela). O "aha" de treino só acontece na aba Treino, depois de a Home ter dito o contrário.
- **Sem tela de resultado:** os seis passos terminam no meio do dia comum ("AGORA · Lanche da manhã · 11:00"). Os números calculados (2.056 kcal, 149 g de proteína, 5 refeições, ABC 3 dias) nunca são entregues como resultado das respostas (P2 MKT-03).

### 2.2 Respostas às perguntas da fase 3

| Pergunta | Resposta |
|---|---|
| O que a pessoa recebe ao terminar? | A Home comum. Cardápio, água e metas estão certos e prontos; a ficha de treino **não existe ainda** (só nasce ao abrir `/treino/`), e a Home traduz isso como "descanso". |
| Alguma pergunta é feita antes de poder ter consequência? | Sim: experiência (só vale com ficha), divisão (idem, e para 3 dias duas das três opções dão a mesma ficha), janela de sono (pré-preenchida — "Continuar" declara o que ninguém escolheu), interesses/prioridade (organizam a Home, mas antes de a pessoa ter visto a Home). |
| Alguma resposta não é usada por nenhuma tela? | Nome: só aparece no e-mail de redefinição de senha [LIDA NO CÓDIGO `email_senha.html:11`]. |
| A resposta anterior aparece na pergunta seguinte? | Não. O passo 4 fala em abstrato dos "seus dias"; a docstring de `SplitPreferenceForm` promete o contrário e a tela não cumpre. |
| A pessoa consegue voltar sem perder nada? | Sim, em todos os passos; pular por URL redireciona ao passo certo; logout/login retoma no passo pendente. |
| Erro é claro? | Passo 1 sim (mensagens próprias com exemplo). Passos 2/4/5 usam "Este campo é obrigatório." do Django sob cartões; passo 6 põe o erro a 400–500 px da pergunta; foco nunca vai ao campo inválido. |
| O progresso é honesto? | Não: denominador muda no meio (3/6 → 4/5), 66% onde é 67, e "100%" aparece antes de responder o último passo. |

### 2.3 Cada pergunta e sua consequência real no código

Consumidor real de cada resposta [LIDA NO CÓDIGO], classificação e o que acontece se for adiada.

| # | Pergunta | Consumidor no código | Classe | Consequência de adiar |
|---|---|---|---|---|
| 1 | Nome (cadastro) | só `templates/accounts/email_senha.html:11` (com `{% if %}` que tolera vazio) | **DESNECESSÁRIO** como obrigatório | nenhuma tela muda |
| 2 | E-mail, senha, confirmação | conta | ESSENCIAL AGORA | — |
| 3 | Sexo | TMB (`plans/calculations.calculate`) | ESSENCIAL AGORA | sem meta |
| 4 | Nascimento | TMB | ESSENCIAL AGORA | sem meta |
| 5 | Altura | TMB | ESSENCIAL AGORA | sem meta |
| 6 | Peso | TMB; `build_inputs` **recusa** sem peso (`plans/services.py:58-60`); meta de água 35 ml/kg | ESSENCIAL AGORA | sem meta nem água |
| 7 | Objetivo | delta calórico e proteína (`calculations.py:52-55, 84`) | ESSENCIAL AGORA | sem meta |
| 8 | Rotina fora do treino | `ACTIVITY_FACTORS` 1,25–1,60 sobre a TMB (`calculations.py:178-195`) — até 28% da meta | ESSENCIAL AGORA | meta errada em até 28% |
| 9 | Dias de treino | posição dentro da faixa de atividade (`FULL_TRAINING_WEEK=5`) e única entrada de `create_routine` (`workouts/services.py:1625`) | ESSENCIAL para Treino (já é "deixe em branco") | sem ficha; meta muda pouco |
| 10 | Experiência | só `teto_semanal_de` (`services.py:815-835`; vazio = 20 = comportamento anterior) e a frase de esforço | **ÚTIL DEPOIS** | ficha nasce igual à de hoje para quem não responde; perguntar na primeira abertura da ficha |
| 11 | Acorda/dorme | só `meal_planner.build_slots` para posicionar horários; modelo já tem 07:00/23:00 | **ÚTIL DEPOIS** | cardápio sai com a janela padrão (que já é o que acontece para quem não toca) |
| 12 | Divisão | só `split_for` em `create_routine`; condicional por `preferencia_muda_a_divisao` | **ÚTIL DEPOIS** (na primeira ficha) | ficha com a divisão padrão da frequência; perguntar com prévia real |
| 13 | Cardápio (rápido/variado/econômico) | é PESO na nota, não filtro (`style_penalty`, `meal_planner.py:323-329`); default VARIED | **ÚTIL DEPOIS** | cardápio variado; chip no cardápio remonta (`plan_is_current` já faz) |
| 14 | Restrições | ELIMINAM receitas (`candidates_for`) — vegana vendo frango é primeiro resultado errado | ESSENCIAL AGORA (custo zero para quem não tem) | cardápio errado |
| 15 | Interesses | só `interesse_em_agua` em `limiar_de_atraso` (`plans/agora.py:123-150`) e uma linha do Perfil | **ÚTIL DEPOIS** | Home canônica (estado neutro documentado) |
| 16 | Prioridade | ramos do AGORA, posição da seção na Home, limiar da água; `""` é estado de verdade (CLAUDE.md) | **ÚTIL DEPOIS** | Home canônica; nada infere de uso (decisão do CLAUDE.md preservada) |

Nenhuma pergunta adiável muda a meta calórica: a duração da sessão **não** entra na TDEE (`PlanInputs.session_minutes` só é usado como `len()`, `calculations.py:121,133`).

### 2.4 Defeitos do onboarding (resumo; detalhe nas seções 5 e 6)

- **P1** primeira Home nega o treino de hoje (ficha só nasce em `/treino/`).
- **P1** convite de instalação no cadastro, e o primeiro toque num campo o dispensa **para sempre** (`localStorage`), enquanto "Agora não" adia 30 dias.
- **P2** passo 4 sem prévia e com opções equivalentes para 3 dias (rebaixado de P1 pelo cético: `/treino/` e Perfil avisam depois, em voz alta).
- **P2** passo 6 lista os cinco pilares duas vezes (1.465 px).
- **P2** janela de sono pré-preenchida contradiz `escolhas_abertas`.
- **P2** experiência perguntada a quem não marcou dia.
- **P2** nome obrigatório sem consumidor.
- **P2** sem tela "seu plano está pronto".
- **P3** contador de passos (3/6 → 4/5, 66%, 100% antes de concluir); erros genéricos do Django; foco não vai ao campo inválido; "Os dois juntos — Os dois juntos, mais devagar"; ícone vazio em "Não quero priorizar agora"; três componentes para escolha única; sem "Nenhuma restrição"; acorda 23:00/dorme 07:00 aceito sem aviso; peso volta como "102.00".

---

## 3. Click audit

Inventário consolidado das quatro jornadas (usuário novo, Alimentação, Treino, Progresso/Áreas/Perfil), a 390×844 salvo indicação. Colunas: aparência · parece clicável? · é clicável? · onde deveria abrir · onde abre hoje · feedback visual · feedback após clique · alvo (px) · problema · severidade. "OK" = sem problema.

### 3.1 Conta e onboarding

| Tela | Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| /conta/entrar/ | Convite de instalação (Instalar / Agora não / ×) | card branco fixo, 143 px | sim | sim | não cobrir o link de criar conta | cobre metade de "Criar agora" (390) e o campo Senha + botão Entrar (320); toque num campo fora do card dispensa **para sempre** | sombra | × fecha e o link reaparece | 44×44 (×), 167×44 | primeira visita com o formulário coberto; dispensa definitiva por toque acidental | **P1** (MKT-02) |
| /conta/entrar/ | Entrar (senha errada) | primário | sim | sim | mesma tela com erro | idem: role=alert, e-mail preservado, senha limpa, foco no campo | faixa de erro | claro | 313×52 | — | OK |
| /conta/entrar/ | Olho "Mostrar a senha" | ícone no campo | sim | sim | alterna | alterna; aria-pressed e rótulo mudam | ícone | campo vira texto | 44×44 | — | OK |
| /conta/entrar/, /cadastro/ | Rodapé "Ainda não tem conta? Criar agora" / regras de senha | texto 12,8–14 px sobre a vinheta fixa | sim | sim | — | — | — | — | 44 alt. | contraste 2,2–3,0:1 na faixa da vinheta (WCAG pede 4,5) | **P1** (MOB-02) CROSS-WORKFLOW: DESIGN |
| /conta/senha/ | Campo "Email" + Enviar link | campo + primário | sim | sim | enviado | enviado, texto honesto | — | confirmação com "Voltar para entrar" | 313×52 | "Email" aqui, "E-mail" na entrada; e-mail digitado não vem pré-preenchido | P3 |
| /conta/senha/ | Marca NutriPlan | logo + nome | sim | sim | algo que faça sentido deslogado | `/` → 302 → entrar (perde a recuperação) | nenhum | — | 110×44 | tira do fluxo sem aviso | P3 |
| /conta/cadastro/ | Criar conta (senha `12345678`) | primário | sim | sim | erro sob Senha, foco nele | erros sob "Confirme a senha", foco volta ao nome, checklist não marca a regra que falhou, scrollY 0 com o erro a y≈900 | caixa rosa | nome/e-mail preservados | 313×52 | erro ancorado e foco errados; erro abaixo da dobra | P3 (NOVO-11, E12) |
| /conta/onboarding/1/ | Continuar vazio / absurdos | primário | sim | sim | erros por campo | erros por campo: "não pode estar no futuro", "≥ 100", "20 a 400 kg"; valores preservados | sob cada campo | — | 303×52 | altura 5 aceita pelo navegador (`min=0`) e recusada pelo servidor com voz do Django | P3 (E14) |
| /conta/onboarding/1/ (Voltar/Editar) | Peso pré-preenchido | input | sim | sim | — | "102.00"/"82.30" com ponto, ao lado do placeholder "75,5" e da ajuda "como 82,5" | — | — | 303×52 | contraria "vírgula decimal" do CLAUDE.md | P2 (MC-07, NOVO-10, PA-08) |
| /conta/onboarding/1/ | Sexo | segmentado 147×44 | sim | sim | marca | marca | realce | — | 147×44 | — | OK |
| /conta/onboarding/2/ | Cartões objetivo/rotina | choice-card | sim | sim | marca | marca | borda | — | 147×121 | "Os dois juntos — Os dois juntos, mais devagar."; vazio → "Este campo é obrigatório." ×2 sem `required` nativo | P3 (Q-10, MC-16, Q-09) |
| /conta/onboarding/3/ | Chips de dia | 71×44 | sim | sim | marca | marca; aria-label com nome inteiro | realce | — | 71×44 | — | OK |
| /conta/onboarding/3/ | Experiência | rádio clássico | sim | sim | marca | marca | bolinha | — | 303×51 | terceiro componente para escolha única; perguntado sem dia marcado | P2 (Q-05), P3 (MKT-06) |
| /conta/onboarding/3/ | Acorda / Dorme | dois inputs de hora pré-preenchidos | sim | sim | — | aceita 23:00/07:00 sem aviso; "Continuar" declara 07:00/23:00 sem toque | — | — | 146×52 | pré-preenchido contradiz `escolhas_abertas`; janela invertida sem aviso | P2 (Q-03), P3 |
| /conta/onboarding/3→6/ | "Passo N/M · %" | barra + texto | não | não | — | 3/6·50% → 4/5·80% → 3/5·60% → 4/6·66% → 6/6·100% antes de concluir | — | — | — | denominador muda; 100% precoce; truncamento | P3 (NOVO-13, E13, MKT-09) |
| /conta/onboarding/4/ | Três cartões de divisão | choice-card 303×135 | sim | sim | marca | marca; com 3 dias "1 grupo" e "3 grupos" viram a MESMA ficha; "1 grupo" promete 5 dias | realce | avança | 303×135 | jargão; sem prévia; opções equivalentes (o painel avisa depois) | P2 (Q-04, NOVO-08, MKT-04) CROSS-WORKFLOW: TRAINING na tabela |
| /conta/onboarding/5/ | Cardápio + restrições | rádio + 4 caixas | sim | sim | avança | avança; Vegana+Vegetariana+Sem lactose com "Rápida e econômica" entregou cardápio 100% vegano | — | — | 303×51 | sem "Nenhuma restrição"; texto do cartão promete ovo/frango para vegano | P3 (MKT-13) |
| /conta/onboarding/6/ | 5 caixas + 6 rádios + Concluir | Concluir a y=1.279 | sim | sim | pedir a prioridade junto do campo | erro no topo (y≈339), campo em y≈700+; Treino como principal sem marcar Treino marca a área (correto) | texto de erro no topo | Home | 215×52 | tela de 1.465 px; erro longe; cinco nomes duas vezes | P2 (MKT-05, Q-06), P3 (MKT-12) |
| /conta/onboarding/6/ | "Não quero priorizar agora" | cartão com slot de ícone vazio 40×40 | sim | sim | marca | marca | — | — | 303×84 | quadrado vazio | P3 (MKT-08) CROSS-WORKFLOW: DESIGN |
| /conta/onboarding/N/ em edição | Barra "Passo N/6 · X%" | stepper | não | não | não existir | existe, com botões Voltar/Salvar corretos | — | — | — | parece que vai refazer o cadastro | P2 (PA-02, MC-06, Q-08, NOVO-12) |

### 3.2 Hoje (`/`)

| Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|
| Cartão "Seu treino · sua área" (primeira Home) | card promovido, "Hoje não tem treino na sua ficha" | sim | sim | dizer que hoje tem Treino A | diz que não há; após UMA visita a /treino/ passa a "0 de N séries" | — | link leva ao painel que mostra "TREINO DE HOJE: A" | 150×44 | frase falsa no primeiro contato | **P1** (NOVO-01/MC-01/MKT-01/Q-01) |
| Mesmo cartão, após zerar os dias | "0 de 24 séries de hoje" | sim | sim | sumir ou dizer "sem dias" | continua com a ficha antiga para sempre; /treino/ diz que não há dias | — | — | — | Home contradiz o Treino; ofensiva continua cobrando treino [LIDA NO CÓDIGO `streaks.py`] | **P1** (Q-02) |
| AGORA "Ver refeição" | primário 308×47 | sim | sim | rolar até o card com cabeçalho visível | `#slot-N` com o topo do card 24 px acima do viewport | — | rolagem | 308×47 | falta `scroll-margin-top` | P2 (NOVO-02) |
| AGORA "Começar treino"/"Continuar de onde parou" | primário | sim | sim | ficha de hoje (requisito) | `/treino/agora/` (execução) | — | cai dentro de um exercício | 308×47 | mesmo rótulo do painel, destino diferente; viola requisito | **P1** (CA-04/MC-03) |
| Resumo "19:00 treino" (`.resumo-dia__treino`) | item verde ao lado de "0 de 3000 ml" (span) | sim | sim | painel | `/treino/agora/` | cor | — | — | par de itens iguais, só um responde; exibe 19:00 que o CLAUDE.md diz ter saído da interface | P2 (CA-13), P3 |
| Linha da opção A/B (`summary.option__summary`) | cartão cinza com selo A/B, sem chevron | não | sim | ingredientes e preparo | expande | cursor pointer; sem marcador | expande | 306×66 | affordance invisível | P3 |
| Registrar A / Registrar B | primário (A) / ghost (B) | sim | sim | marca e permanece no card | POST → `#slot-N`; card vira "✓ … · desfazer"; hero atualiza | — | recarrega em `#slot` com o card quase todo acima do viewport | 308×52 | confirmação nasce fora da tela; A primário contradiz "A e B fecham a mesma caloria" | P2 (NOVO-02), P3 (CA-12) |
| desfazer (refeição) | btn-link | sim | sim | volta ao estado com opções | idem, mantém posição | link | — | 61×44 | — | OK |
| Pulei | quiet 308×44 | sim | sim | "Refeição pulada · desfazer" | idem | — | hero passa a "Superávit +257 kcal/dia" com 0 kcal comidos | 308×44 | linha do hero lê-se como saldo de hoje | P2 (UXA-05) |
| Comi outra coisa | summary + formulário (descrição, 3 pares alimento/gramas, Registrar) | sim | sim | registro fora do plano | registrou; alimento inexistente **descartado em silêncio** | — | card com descrição + kcal | 306×44 / 279×52 | input ignorado sem aviso | P2 (UXA-04) |
| Ver opções (refeição futura) | verde com chevron | sim | sim | opções A/B | expande; Registrar funciona | chevron vira | — | 308×44 | — | OK |
| Água +250/+500/+750 | três tiles 87×55 (71×55 a 320) | sim | sim | soma | soma; barra e valor atualizam | — | desfazer/zerar aparecem | 87×55 | gap 6 px entre vizinhos | P3 (MOB-13) |
| desfazer (água) | btn-link 61×44 | sim | sim | remove último gole | 1500 → 750 | — | — | 61×44 | sobrepõe "zerar" em 3 px | P3 (MOB-11) |
| zerar → "apagar a água de hoje" | summary + botão vermelho 152×44 | sim | sim | confirmação inline sem deformar | ao abrir, "750 / 3000 ml" vira 3 linhas (390) e **uma letra por linha** (320, 0×208 px) | — | zera, sem desfazer | 44×44 / 152×44 | layout do cabeçalho colapsa na ação destrutiva | **P1** (UXA-02) |
| "Registros de hoje e últimos 7 dias" | link sublinhado | sim | sim | /hidratacao/ | idem | — | — | 284×44 | — | OK |
| Cartão da ofensiva | card bordado com chama | sim | não | — | nada | nenhum | — | — | único card bordado sem porta; "cumpra treino" para quem não tem dia | P3 (E14) |
| Peso de hoje · Registrar | summary + campo + Salvar | sim | sim | registra e mostra o valor | POST → topo com "Peso registrado." e "recalculamos sua meta"; o card some; valor só dentro de "Dados do cálculo" | — | meta 2830 → 3131 sem eco do dígito | 348×44 / 218×44 / 88×44 | sem eco nem correção na tela em que foi digitado | P2 (UXA-06) |
| Lista de compras | link com ícone | sim | sim | /lista-de-compras/ | idem | — | — | 138×44 | — | OK |
| Entender minhas metas · abrir | summary | sim | sim | explicação | expande | "abrir" não vira "fechar" | — | 308×44 | rótulo só na ida; "×1,44" quebra em "×1,4 / 4" | P3 (MC-10), P2 (MC-11) |
| Dados do cálculo · Editar · abrir | summary com `<a>` dentro | sim | sim | summary expande; Editar → Perfil | idem (Editar navega E alterna) | — | — | 308×55 / 49×44 | link dentro de summary | P3 (CA-16) |
| Recalcular minha meta | ghost | sim | sim | recalcula | volta ao topo com flash | — | — | 308×52 | — | OK |
| Ativar lembretes das refeições | ghost | sim | sim | pede permissão; se negada, explica | com permissão negada NADA muda (mensagem escrita e sobrescrita em 0,1 ms) | — | nenhum | 308×52 | recurso morre sem diagnóstico | **P1** (UXA-03) |
| Tab bar | 4 itens | sim | sim | /, /treino/, /historico/, /areas/ | idem | pílula verde | — | 84×54 | — | OK |

### 3.3 Treino — painel (`/treino/`)

| Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|
| "Começar treino" / "Continuar de onde parou" (hero) | primário 306×54 | sim | sim | ficha de hoje | ficha (correto) | — | — | 306×54 | mesmo rótulo com 3 destinos no app; "Continuar" abre uma lista, não onde parou | **P1** (CA-04) / P3 (MC-21) |
| "Ver ficha do Treino A · 5 exercícios" | ghost 350×52 | sim | sim | — | a MESMA ficha | — | — | 350×52 | dois botões, um destino | P3 (CA-05, MKT-11) |
| Faixa SEG A · TER B … DOM A | sete caixas que parecem chips | sim | não | ficha do dia (cards abaixo já fazem) | nada | nenhum | — | 40×61 | vestido de botão; "A" onde os cards dizem A1/A2; "DOM" quebra em "DO/M" a 320 | P3 (CA-08, CA-14), P2 (TR-09) CROSS-WORKFLOW: DESIGN |
| Cards A1 / B / C / A2 | card com letra, nome, dia, chevron, borda verde no de hoje | sim | sim | ficha | ficha correta, aria-label completo | chevron | — | 350×84 | sem `:active` (só `:hover`) | P2 (CA-06) |
| Detalhes do programa (summary) | "abrir" à direita | sim | sim | expande | expande | "abrir" fixo | — | 308×44 | texto contradiz a semana ("quatro dias viram ABCD" com A-B-C-A; "abre mais um dia" a 7 dias) | P2 (TR-10, NOVO-07) CROSS-WORKFLOW: TRAINING |
| Editar (dias) | link 47×44 | sim | sim | edição voltando ao Treino | `/conta/onboarding/3/?origem=treino`; Voltar → /treino/ | — | — | 47×44 | mostra "Passo 3/6 · 50%" | P2 (PA-02) |
| Cartão "Treino de hoje" (rodapé: 320 kg · 1 minutos · 1 séries · 1 exercícios) | tiles | não | não | — | — | — | — | — | segundo bloco com o mesmo nome do hero, números contraditórios, plural fixo | P2 (CA-05, MOB-07, MC-08, TR-14) |
| Compartilhar treino / Como post do feed | primário + ghost 308×52 | sim | sim | folha nativa com pré-visualização | canvas + navigator.share / download silencioso; a imagem diz **"TREINO CONCLUÍDO"** com 1 de 5 exercícios | — | nenhum visível | 308×52 | conteúdo falso sai do app; sem feedback; segunda primária na página | **P1** (MC-02), P3 (TR-12, CA-05) |
| Exportar para o Saúde | ghost | sim | sim | TCX | 200 attachment | — | download | 308×52 | rótulo diverge de "Exportar para o app de saúde" no fim do treino | P3 (MC-18) |

### 3.4 Ficha (`/treino/ficha/<id>/`)

| Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|
| ← Treino | link 62×44 | sim | sim | painel | painel | sublinhado | — | 62×44 | — | OK |
| Continuar de onde parou | primário 350×52 | sim | sim | execução do próximo pendente | idem (14 depois de concluir o 11) | — | — | 350×52 | a 320 px o CTA cai atrás da barra; hint de 5 linhas antes da lista | P2 (CA-09, MOB-08) |
| Nome do exercício (`.ficha-item__ver`) | negrito sem sublinhado/chevron | **não** | sim | página do exercício | idem | nenhum | — | 229–233×44 | porta do requisito sem nenhum sinal; 47% do card não responde (numeral, vãos) | P2 (NOVO-04, TR-04, MOB-06, CA-03) |
| Fazer / Em andamento 1/4 / Concluído 4/4 | texto verde à direita | sim | sim | execução; "Concluído" deveria ser estado | execução, inclusive 4/4 → "Série None de 4"; depois exibe "Concluído: 5/4" | cor | — | 48×44 | porta para registrar num exercício terminado | **P1** (TR-01) |
| Pílula "Principal" | 11,2 px | não | não | — | — | — | — | — | em 4 de 5 itens não discrimina; "4 × 6-10" com espaços largos | P3 (CA-15) |
| Linhas em ficha de outro dia | iguais, sem "Fazer" | não | sim | página do exercício | idem | nenhum | — | 288×44 | correto não executar; mesma falta de affordance | P2 (TR-04) |

### 3.5 Exercício — leitura (`/treino/exercicio/<id>/`)

| Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|
| ← Treino | link 62×44 | sim | sim | a ficha de onde veio | `/treino/` (painel) | sublinhado | — | 62×44 | voltar não volta; a execução usa "← Ficha" e acerta | P2 (NOVO-03, TR-05, MOB-09, CA-10, MC-05, MKT-10) |
| ver vídeo (poster 128×96) | thumb com play | sim | sim | vídeo inline | iframe youtube-nocookie 308×411, autoplay mudo; URL e history inalterados; campos preservados | — | player | 128×96 | — | OK |
| fechar (vídeo) | texto branco 60×44 no canto do player | sim | sim | volta ao poster | volta | — | — | 60×44 | fica sobre a barra do YouTube (som, ⋮, título) | P2 (TR-06) CROSS-WORKFLOW: DESIGN |
| Músculos trabalhados (summary) | caixa cinza com ícone de corpo | sim | sim | anatomia | **segundo iframe** do YouTube (Shorts de terceiro com "EXPERIMENTE GRÁTIS"), 462 px, autoplay | — | dois vídeos tocando | 308×44 | propaganda de concorrente dentro do app; dois players | P2 (NOVO-05, TR-07) — curadoria CROSS-WORKFLOW: TRAINING |
| Papel: "Principal — composto, abre a sessão" | texto | não | não | — | dito do 2.º da lista; vem de `is_compound`, não de "maior dose" | — | — | — | afirma ordem que a ficha não cumpre | P2 (MC-12) CROSS-WORKFLOW: TRAINING |
| Continuar de onde parou / Fazer agora (CTA) | primário 350×52 | sim | sim | execução; nada se concluído | execução inclusive com 4/4 | — | — | 350×52 | leva a "Série None" | **P1** (TR-01) |
| Como fui | card com datas | não | não | — | — | — | — | — | "Na sua ficha" e "min" quebram | P3 CROSS-WORKFLOW: DESIGN |

### 3.6 Execução (`/treino/agora/`)

| Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|
| ← Ficha | link 55×44 | sim | sim | ficha | ficha; ⌫ restaura reps e descanso | — | — | 55×44 | — | OK |
| Título do exercício (h1 sublinhado) | 248×31 | sim | sim | leitura | leitura | sublinhado | — | **248×31** | único alvo < 44 px em nove telas | P2 (NOVO-06, CA-07, MOB-12) |
| Pastilhas 1 2 3 4 | caixas com borda/fundo, atual tracejada | sim | não | — | nada | estado | — | 54×48 | vestidas de chip sem ação | P3 (CA-08) |
| −2,5 / +2,5 | cinza 52×44 | sim | sim | ajusta | 40 → 42,5 → 40 → 37,5, vírgula; vazio → 2,5; trava em 0 | valor | — | 52×44 | 0×12 aceito em polia | OK / P3 |
| Carga / Reps | inputs 188×44 / 308×44, inputmode certo | sim | sim | — | carga "abc" → "Carga inválida — use números, como 42,5."; 9999 → "fora do que uma barra aguenta"; **reps 0 → gravado 40×1; reps 999 → 40×100** sem aviso; após erro os valores digitados somem | — | — | 188×44 | reps sem validação visível; valores descartados | P2 (TR-08, E08) |
| Concluir série N | primário 308×48 | sim | sim | grava, próxima série; ao fechar a última avisa | grava; ao fechar a última **troca de exercício em silêncio** (URL perde `?exercicio=`); em 4/4 diz "Concluir série None" e grava uma 5.ª série invisível; a 320×568 e 375×667 o botão fica **debaixo da tabbar** | pastilha + descanso | — | 308×48 | — | **P1** (TR-01, MOB-03), P2 (TR-02) |
| Descanso · pular | faixa verde, link 46×44 | sim | sim | esconde | esconde; reload restaura o tempo que falta, mas não lembra o "pular"; servidor escreve "67s", JS "1:08" | relógio, "pode ir" | — | 46×44 | pular não sobrevive; formato duplo | P3 (TR-13) |
| desfazer última série [de Supino] | link 132–288×44 | sim | sim | remove a última série de hoje | remove; se for de OUTRO exercício, nada visível muda além de "2/16 → 1/16"; segundo toque apaga a anterior; `[role=status]` vazio | — | — | 132×44 | sem feedback e sem confirmação | P2 (TR-03), P3 (MOB-12) |
| DEPOIS · Flexão de braço | rótulo + nome negrito 108×44 | sim | sim | próximo | `?exercicio=14`, descanso continua | negrito | — | 108×44 | — | OK |
| Ver o treino completo (rodapé) | ghost 350×52 | sim | sim | ficha | ficha (duplica ← Ficha); em `agora.html:88` (fim do treino) o mesmo texto vai ao painel | — | — | 350×52 | mesmo texto, dois destinos | P3 (MC-04) |
| Faixa da fila "1 marcação esperando conexão" | fixa acima da tabbar | não | não | — | a 320 px cobre +250/+500/+750; sem espaço reservado no body; sem fechar | — | — | — | esconde os botões que o próprio texto manda tocar | P2 (E07) |
| `?exercicio=999` / `abc` | 404 | — | — | 404 amigável | 404 estrito (DEBUG local); com conta sem treino cai no vazio "Hoje não tem treino" (200) | — | — | — | comportamento conforme CLAUDE.md | OK / P3 (E16) |

### 3.7 Corridas, Áreas, Hidratação, Lista, Progresso, Conquistas, Perfil

| Tela | Elemento | Aparência | Parece? | É? | Deveria abrir | Abre hoje | Feedback visual | Após clique | Alvo | Problema | Sev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| /treino/corridas/ | Começar corrida | primário 308×48 | sim | sim | inicia GPS | sem permissão: painel 0,00 km e "Sem permissão de localização. A corrida não pode ser registrada." | mensagem inline | botão igual | 308×48 | não diz como liberar; sem `geolocation` o botão fica vivo e mudo; sem link de volta | P2 (E10), P3 (TR-15) |
| /areas/ | Tiles Corrida, Hidratação, Conquistas, Lista, Perfil | tiles inteiros `<a>` | sim | sim | cada área | cada área | — | — | 169×134 / 169×102 / 350×102 | "SUAS ÁREAS" lista as duas fora da barra, não as da pessoa; "3.000 ml" vs "3000 ml"; Conquistas vazio promete "uma semana de registros" e /conquistas/ diz "a primeira série" | P3 (MC-19/MKT-14, MC-18), P2 (E05) |
| /hidratacao/ | +250/+500/+750 | 98×48 | sim | sim | soma | soma (PRG); volta ao topo com o anel | número e anel | — | 98×48 | cada toque empilha histórico (5 voltar para sair); sem apelido (Home tem "copo/garrafinha") | P2 (PA-03), P3 (MC-18) |
| /hidratacao/ | Outra quantidade + Somar | input number 50–2000 step 10 | sim | sim | soma | validação nativa; 5 ml (contornando) → "Quantidade de água inválida." sem faixa, valor perdido | — | — | 217×52 / 83×52 | erro sem faixa; sem `zerar` (Home tem) | P3 (E11) |
| /hidratacao/ | desfazer o último | btn-link 113×44 | sim | sim | remove | remove | — | — | 113×44 | — | OK |
| /hidratacao/, /historico/ | Listas semanais (`.semanas > .semana`) | 16 caixas cinza de 65 px | sim | não | linha de 32 px sem fundo (seção 43) | sub-cards por colisão de seletor (`app.css:3427` vence `:7120`) | — | — | — | +300 px por lista; regressão de CSS | P2 (CA-02) CROSS-WORKFLOW: DESIGN |
| /lista-de-compras/ | Chips Opção A / B | 77×44 | sim | sim | outra opção | recarrega; marcação por opção (documentado) | chip ativo | — | 77×44 | — | OK |
| /lista-de-compras/ | Linha do item (label + quantidade fora do label) | linha inteira parece marcável | sim | sim (só o label) | tocar em qualquer ponto marca | só o label; "~1,4 kg de arroz branco (cru)" tem `nowrap` e o nome vira **letra por linha** (label 55×388 a 320; 102×114 a 390) | caixa 44×44 | persiste | 268×50 (normal) | Mercearia ilegível; quantidade (63% da linha) não tocável | **P1** (UXA-01, MOB-01) |
| /lista-de-compras/ | Seus itens: campo + Adicionar; remover | formulário + lista | sim | sim | adiciona e mostra | adiciona; redirect `#seus-itens` pousa com o item **fora da tela, acima** (−128 a −195 px; −326 a 320); sem flash; remover sem confirmação nem mensagem | chip com contagem | — | 104×52 / 60×44 | ação principal sem evidência visível | **P1** (E03), P3 |
| /lista-de-compras/ | Voltar para o cardápio | ghost | sim | sim | `#cardapio` | topo de `/`, 700 px acima do cardápio | — | — | 308×52 | promete o cardápio, entrega o topo | P3 (MC-17) |
| /historico/ | Empty state "Ainda não há nada marcado…" + Ir para o dia de hoje | card sem `<h2>` no topo da página | sim | sim | `/` | `/` | — | — | 176×52 | primeiro card da tela é um vazio acima de Peso/Treino/Água com dado; frase contradiz a tela; "82,3kg" sem espaço | P2 (PA-04, E09, CA-11, MC-09) |
| /historico/ | Peso em quilos + Salvar | campo "82,30" + 88×44 | sim | sim | salva/edita | salva; substitui a pesagem do dia (edição invisível); erro "abc" chega como flash no topo (y=78) com o campo em y=597 sem aria-invalid | flash | — | 212×44 / 88×44 | duas casas no campo, uma na tela; erro longe; edição sem nome | P3 (E11) |
| /historico/ | Tiles das semanas de Treino/Água | tiles cinza com número | sim | não | — | nada | — | — | — | parecem navegáveis | P3 |
| /historico/ | Resumo Conquistas "Desbloqueadas 0 · Primeiro treino 1/1" + Ver todas | card + link 68×44 | sim | sim | /conquistas/ | /conquistas/ diz "1 conquista"; ao voltar o resumo vira "1"; aba acende **Áreas** | — | — | 68×44 | contradição até visitar a outra tela (`resumo` não chama `avaliar`, decisão de custo) | P2 (UXA-07), P3 (PA-05) |
| /conquistas/ | Compartilhar | ghost 117×44 | sim | sim | folha nativa | canvas + share; headless resolve "cancelado" | nenhum estado | — | 117×44 | sem feedback; `card.js:307` descarta a Promise | P3 (PA-10) |
| /conquistas/ | Volta | — | — | — | Progresso ou Áreas | só barra/⌫ | — | — | — | sem link próprio | P3 |
| /conta/perfil/ | Recalcular metas | primário 308×52 | sim | sim | Perfil com metas novas | `/` com flash | — | sai da tela | 308×52 | destino diverge do lugar do botão; rótulo diverge de "Recalcular minha meta" da Home | P3 (PA-09, MC-18) |
| /conta/perfil/ | 6× Editar | link 46×44 | sim | sim | bloco em edição, volta ao bloco | passo com "Passo N/6 · X%"; Salvar → topo do Perfil | stepper | — | 46×44 | stepper de assistente; volta sem âncora | P2 (PA-02) |
| /conta/perfil/ | Card Treinos (dt/dd) | lista chave/valor | não | não | — | "Experiên/cia", "Dia/s", "Entrou/como" a 320; "Acorda" cola em "Dias" (dois `<dl>` no mesmo card) | — | — | dt 46–63 px | quebra intra-palavra nas quatro larguras | P2 (PA-01, MOB-04) CROSS-WORKFLOW: DESIGN na solução |
| /conta/perfil/ | Minhas conquistas | `btn btn--block` sem variante | sim | sim | /conquistas/ | idem | texto verde centrado | — | 308×52 | quarta aparência de botão | P3 (CA-17) |
| /conta/perfil/ | Trocar minha senha | ghost | sim | sim | tela própria | tela com olho acessível e "Voltar ao perfil"; nenhuma aba acesa; `aria-describedby` aponta para id inexistente | — | — | 308×52 | a11y quebrada no erro | P3 (PA-06) |
| /conta/perfil/ | Exportar meus dados | ghost | sim | sim | JSON | 200 attachment, sem flash | — | — | 308×52 | sem confirmação na tela | P3 |
| /conta/perfil/ | Sair da conta | **btn--perigo vermelho** | sim | sim | logout com confirmação | confirm nativo → entrar, sem "você saiu" | vermelho | — | 308×52 | sair (reversível) mais gritante que excluir (link de texto); único logout no celular | P3 (PA-07, MC-15) CROSS-WORKFLOW: DESIGN |
| /conta/excluir/ | Excluir minha conta para sempre + senha + Cancelar | página sem barra, lista do que será apagado | sim | sim | apaga só com senha | vazio → nativo; errada → "Senha incorreta."; certa → entrar com flash | — | — | 308×52 | — | OK |
| /conta/perfil/ (meio do onboarding) | Perfil por URL | linhas vazias com unidade solta ("Idade  anos") | — | — | — | abas redirecionam ao passo 1 sem mensagem | — | — | — | só alcançável por URL | P3 |

---

## 4. Navegação: caminhos mortos, loops, duplicações, "voltar" errado, barra fora de sincronia

### 4.1 Voltar errado

| Onde | O que acontece | Esperado | Sev |
|---|---|---|---|
| `/treino/exercicio/<id>/` "← Treino" | vai a `/treino/` (dois níveis acima); quem confere os 5 exercícios da ficha faz ficha→exercício→painel→ficha a cada um | "← Ficha" para a sessão que contém o exercício (a execução já faz isso) | **P2** |
| `/hidratacao/`, `/historico/` | cada POST (PRG) empilha entrada; 4 registros = 5 "voltar" (history.length 17 medido) | um voltar sai da tela (`history.replaceState` após PRG, ou rota de POST que redireciona com `303` sem entrada extra) | **P2** |
| `/conta/senha/` marca NutriPlan | `/` → 302 → entrar; a pessoa sai da recuperação | marca inerte ou → entrar sem `next` | P3 |
| `/conta/perfil/` Recalcular metas | cai na Home | voltar ao bloco de metas do Perfil | P3 |
| `/lista-de-compras/` "Voltar para o cardápio" | topo de `/` | `/#cardapio` | P3 |
| Salvar em modo edição | topo do Perfil | bloco editado (`#bloco`) | P3 |

### 4.2 Caminhos mortos e telas sem saída própria

- **Corridas, Hidratação, Conquistas:** nenhum link de volta; só barra ou gesto do sistema. Quem chega em Hidratação pelo link da Home vê a aba pular de Alimentação para Áreas e não tem "← Hoje".
- **Demo (`/demo/`)** completo e não linkado de nenhuma tela anônima (P2 MKT-07).
- **Perfil no meio do onboarding** (só por URL): linhas vazias, abas redirecionam sem mensagem.
- **Cards-vitrine sem porta:** ofensiva na Home; tiles de semana em Progresso; faixa SEG…DOM no painel; pastilhas 1-4 na execução — todos vestidos de controle (P3 CA-08).

### 4.3 Loops e redundâncias

- **Três alvos para a mesma ficha na primeira dobra do painel:** "Continuar de onde parou" (y=458), "Ver ficha do Treino A" (y=565), card A1 (y=863).
- **"Continuar de onde parou" com três destinos:** Home → execução; painel → ficha; ficha e leitura → execução (leitura inclusive de exercício concluído). **P1** (CA-04/MC-03), porque o caminho mais usado (Home) pula a ficha que o dono fechou como etapa.
- **"Começar treino" com dois destinos** (Home → execução, painel → ficha) — mesma família.
- **Seis rótulos para `/treino/`:** "Treino", "← Treino", "Ver minha semana", "Ver o treino completo" (fim do treino), "Abrir a ficha da semana", "Abrir o treino de hoje", "Ver o treino". E "Ver o treino completo" aponta para duas telas diferentes em `agora.html` (linhas 88 e 528). P2 (MC-04).
- **Quatro nomes para `/`:** "Hoje", "Alimentação", "dia de hoje", "cardápio". P3 (MC-17).
- **"Editar" de Dados do cálculo** na Home vai ao Perfil, onde há outro "Editar" — dois toques para o passo 1. P3.
- **← Ficha + "Ver o treino completo"** na execução: mesmo destino, dois alvos. P3.

### 4.4 Barra fora de sincronia

- `/conquistas/` acende **Áreas** mesmo vindo de Progresso ("Ver todas") — a tela mora em dois lugares e `nav='profile'` fixo erra para metade das chegadas (P3 PA-05).
- `/hidratacao/` acende Áreas quando se chega pela Home (coerente por destino, mas sem "voltar").
- `/conta/senha/trocar/`: nenhuma aba (P3).
- Tudo o mais acende a aba certa por destino [OBSERVADA em 14 telas].

### 4.5 Estado contraditório entre telas (navegação de dado)

- Home diz "não tem treino" / "0 de 24 séries" enquanto `/treino/` diz o contrário (**P1** ×2).
- Progresso diz "Desbloqueadas 0" com "Primeiro treino 1/1" até alguém visitar `/conquistas/` (P2).
- Painel: "~43 min · 16 séries" no topo e "1 minutos · 1 séries" no rodapé, ambos "Treino de hoje" (P2).
- Execução mostra 4 pastilhas e "4/16" enquanto ficha diz "5/4" e painel soma 5 séries (**P1** TR-01).

---

## 5. Problemas reproduzidos

### 5.1 Confirmados pelos céticos (com passos, esperado × observado, severidade, screenshot)

Cada item abaixo foi reproduzido por um segundo auditor, em conta e sessão próprias, em 14/09/2026. Severidade = a confirmada pelo cético (três foram rebaixados).

#### P1-01 · A primeira Home nega o treino de hoje — a ficha só nasce em `/treino/`
IDs de origem: NOVO-01, MC-01, MKT-01, Q-01 (quatro reproduções independentes).
**Passos:** criar conta; passo 3 marcar Seg (hoje é segunda); passo 6 prioridade Treino; Concluir → `/`. Ler o resumo ("— descanso") e o cartão "Seu treino · sua área" ("Hoje não tem treino na sua ficha. A semana inteira está lá."). Abrir `/treino/` → "TREINO DE HOJE · A". Voltar a `/` → "Hoje treino · 0 de N séries".
**Esperado:** a Home mostra o Treino A desde a primeira abertura, ou diz "sua ficha ainda vai ser montada — abrir".
**Observado [OBSERVADA ×5]:** afirmação falsa em dois lugares (resumo e cartão) no primeiro contato após declarar Treino como principal; corrige-se só depois de visitar a aba. **Causa [LIDA NO CÓDIGO]:** `sync_active_routine` só em `workouts/views.py:103` e `:655`; `plans/views.py:344-350` recusa montar de propósito (razão válida: a tela de comida não cria ficha por efeito colateral); `accounts/views.py:662` (Concluir) também não monta; `_area_promovida.html:29-43` só tem os ramos "tem treino" / "não tem" — falta "ainda não montada". A tela de montagem diz "Estruturando a sua divisão de treino…" e não estrutura.
**Severidade:** P1 (informação incorreta no lugar em que a personalização deveria provar valor; não bloqueia, dado correto no banco). **Correção:** ou montar a rotina no Concluir do onboarding e ao salvar dias pelo Perfil (CROSS-WORKFLOW: TRAINING decide quem chama `sync_active_routine`), ou um terceiro ramo no template e em `estado_do_treino` distinguindo "sem plano com dias cadastrados" de "descanso". Teste: pessoa recém-cadastrada com dia de treino hoje, primeira GET da Home, `assertNotContains("Hoje não tem treino")`.
**Screenshot:** [`screenshots/P1-ficha-nao-montada-home.png`](screenshots/P1-ficha-nao-montada-home.png)

#### P1-02 · Removidos todos os dias, a Home mostra a ficha antiga para sempre
ID: Q-02.
**Passos:** conta com ficha ABC; `/conta/onboarding/3/?origem=treino` desmarcar todos os dias, Salvar → `/treino/` diz "Falta dizer em quais dias você treina". Abrir `/` → "Seu treino · 0 de 24 séries de hoje · Abrir a ficha da semana". Visitar `/treino/` e `/treino/agora/` (ambos dizem que não há treino) e reabrir `/` → idêntica.
**Esperado:** Home sem ficha (ou "Montar treino"), como as telas de treino.
**Observado [OBSERVADA + banco]:** `training_days = []` e `TrainingPlan.is_active=True` continua; a meta calórica recalculou na hora (2809 → 2750) porque `plan_is_current` compara `training_days_per_week`, mas nada desativa a rotina. **Agravante [LIDA NO CÓDIGO]:** `plans/streaks.py:_dias_de_treino` lê o plano ativo — a ofensiva vai cobrar treino em Seg/Qua/Sex de quem declarou não treinar (não observado no navegador; se confirmado, sobe a P0 por "incorreto").
**Severidade:** P1. **Correção:** ao salvar zero dias, desativar a rotina ativa (plano é retrato, como a dieta faz) ou `estado_do_treino` devolver vazio quando `not has_training_days(user)` — e a ofensiva respeitar a mesma régua. Teste: editar dias para nenhum e afirmar que Home e ofensiva não mencionam séries/treino.
**Screenshot:** [`screenshots/P1-ficha-obsoleta-zero-dias.png`](screenshots/P1-ficha-obsoleta-zero-dias.png)

#### P1-03 · Lista de compras: nome do alimento letra por letra na Mercearia
IDs: UXA-01, MOB-01.
**Passos:** `/lista-de-compras/` (Opção A), rolar até Mercearia, olhar "Arroz branco cozido" com "~1,4 kg de arroz branco (cru)". Repetir a 320 e 430.
**Esperado:** nome legível em 1–2 linhas; quantidade quebra ou encolhe; linha inteira marca.
**Observado [OBSERVADA ×3]:** a 390 o nome vira 5 linhas ("Arroz / branc / o / cozid / o", label 102×114, nome 40,7 px de largura); a 320 vira **uma letra por linha** (label 55×388, Feijão 19 linhas, li de 457 px) — quatro itens somam ~1.690 px em 568 de viewport; a 430 ainda 3 linhas com corte intra-palavra. A quantidade (194 px = 63% da linha) fica fora do `<label>` e não marca. Sem rolagem horizontal — a regra foi cumprida ao custo da altura. **Causa [LIDA NO CÓDIGO]:** `app.css:3161-3178` `.shopping__qty { flex:none; white-space:nowrap }` + `.shopping__name { min-width:0 }` + `overflow-wrap:anywhere`; e `plans/compra.py` repete o nome do alimento dentro da quantidade.
**Severidade:** P1. **Correção:** deixar a quantidade quebrar (ou empilhar abaixo do nome), não repetir o nome na quantidade ("~1,4 kg (cru)"), `overflow-wrap: normal` no nome, quantidade dentro do `label`. CROSS-WORKFLOW: DESIGN só na forma final.
**Screenshots:** [`P1-lista-nome-letra-por-letra-390.png`](screenshots/P1-lista-nome-letra-por-letra-390.png), [`P1-lista-nome-letra-por-letra-320.png`](screenshots/P1-lista-nome-letra-por-letra-320.png)

#### P1-04 · "zerar" a água colapsa o valor que está prestes a ser apagado
ID: UXA-02.
**Passos:** Home com algum gole registrado; tocar "zerar" no cabeçalho do cartão de água. Repetir a 320×568.
**Esperado:** confirmação "apagar a água de hoje" sem deformar o valor.
**Observado [OBSERVADA ×2]:** a 390 `.agua__valor` vai de 147×21 a 39×62 (três linhas: "250 /", "3000", "ml"), cartão de 236 para 280 px; a 320 vai a **0×208 px, um caractere por linha**, cartão cresce 183 px; o `<details>` (141 px) é menor que o botão (152 px), que transborda. **Causa [LIDA NO CÓDIGO]:** `app.css:4278-4283` `.agua__topo` flex com `.agua__valor {flex:1; min-width:0}` e `.agua__zerar {flex:none}`; o details aberto soma "zerar" + botão na mesma linha.
**Severidade:** P1 (o número fica ilegível no momento da ação destrutiva; não bloqueia). **Correção:** confirmação em linha própria abaixo do cabeçalho; `white-space: nowrap` no valor.
**Screenshots:** [`P1-agua-zerar-colapsa-390.png`](screenshots/P1-agua-zerar-colapsa-390.png), [`P1-agua-zerar-colapsa-320.png`](screenshots/P1-agua-zerar-colapsa-320.png)

#### P1-05 · "Ativar lembretes" com permissão negada não dá feedback nenhum
ID: UXA-03.
**Passos:** navegador com notificações bloqueadas (`Notification.permission === 'denied'`); Home → "Ativar lembretes das refeições"; observar o texto acima do botão.
**Esperado:** "Permissão negada. Dá para liberar nas configurações do navegador." permanece.
**Observado [OBSERVADA ×2, MutationObserver]:** o status recebe a frase e **0,1 ms depois** volta a "Um aviso 10 minutos antes de cada refeição, no celular."; botão e texto idênticos a antes; segundo toque, idem. **Causa [LIDA NO CÓDIGO]:** `pwa.js:95-130` — `enable()` chama `say('Permissão negada…')` e devolve `null`; o `.then` do onclick chama `render(registration, null)`, que cai no `else` e sobrescreve.
**Severidade:** P1 (recurso fica inalcançável sem diagnóstico). **Correção:** `render()` não sobrescrever quando `enable()` devolveu `null` por permissão negada (ou `render` receber o estado da permissão).
**Screenshot:** [`P1-lembretes-sem-feedback.png`](screenshots/P1-lembretes-sem-feedback.png) (tela final idêntica à inicial — essa é a evidência).

#### P1-06 · Exercício concluído mostra "Série None de 4" e grava uma 5.ª série invisível
ID: TR-01.
**Passos:** concluir as 4 séries do Supino (a tela avança sozinha); voltar à ficha e tocar "Concluído: 4/4" (ou "Continuar de onde parou" na leitura); ler; preencher 40/8 e tocar "Concluir série None".
**Esperado:** exercício concluído não oferece registro: pastilhas feitas, "Exercício concluído", no máximo desfazer e próximo.
**Observado [OBSERVADA ×2]:** "Série None de 4", "Concluir série None", campos vazios, descanso reaparece; tocar sem preencher recarrega sem mensagem; preenchendo, grava a 5.ª: leitura "40 × 8, 8, 8, 8, 8", ficha "Concluído: 5/4", painel "5 séries · 1600 kg", execução continua com 4 pastilhas e "4/16" — quatro telas, dois totais. "desfazer" reverte. **Causa [LIDA NO CÓDIGO]:** `_primeira_serie_livre` devolve `None` com 1..N feitas; `agora.html:173, 324, 339, 354` imprimem `atual.proxima_serie` sem guarda (só `estado.concluido` da sessão inteira tem ramo); `append_set` aceita série extra de propósito (teto 20).
**Severidade:** P1. **Correção:** ramo "exercício concluído" na execução (pastilhas + "concluído" + desfazer + próximo; sem formulário, ou formulário explícito "registrar série extra"); CTA da leitura e "Concluído" da ficha viram estado, não porta.
**Screenshot:** [`P1-execucao-serie-none.png`](screenshots/P1-execucao-serie-none.png)

#### P1-07 · Vinheta fixa das telas de entrada derruba o contraste do rodapé para 2,2–3,0:1
ID: MOB-02. **CROSS-WORKFLOW: DESIGN** (a vinheta veio do commit "a entrada perde a moldura"); a régua de legibilidade é deste brief.
**Passos:** `/conta/entrar/` e `/conta/cadastro/` a 390×844 e 320×568; rolar ao fim; medir o fundo no centro horizontal do quarto inferior do viewport.
**Esperado:** ≥ 4,5:1 no texto secundário de 12,8–14 px.
**Observado [OBSERVADA ×2, pixel da captura]:** `.auth--entrada::before` é `position:fixed` com radial de 55% de preto ancorado em 50% 108%; "Ainda não tem conta? Criar agora" sobre rgb 157–168 → 2,4–2,7:1; regras de senha do cadastro 3,5 → 2,7:1; "Já tem conta? Entrar" a 320 sobre rgb 152–160 → 2,25–2,5:1; pé do viewport 1,6–1,9:1. Botões primários, labels e campos continuam acima de 4,5. `config.tests` mede contraste só contra tokens — a suíte está verde sobre uma promessa quebrada.
**Severidade:** P1. **Correção (DESIGN):** vinheta a ≈12–15% no ponto mais forte, ou presa ao documento abaixo do último texto; QA: teste que calcule contraste do `--text-muted` sobre o pior ponto do gradiente.
**Screenshots:** [`P1-entrada-vinheta-contraste-320.png`](screenshots/P1-entrada-vinheta-contraste-320.png), [`P1-entrada-vinheta-contraste-login-390.png`](screenshots/P1-entrada-vinheta-contraste-login-390.png)

#### P1-08 · "Concluir série" fica debaixo da tabbar a 375×667 e fora da tela a 320×568
ID: MOB-03.
**Passos:** `/treino/agora/` a 375×667 e 320×568, scrollY 0; medir `.agora__concluir` e `nav.tabbar`; `elementFromPoint` no centro do botão.
**Esperado:** a ação que se repete a cada série visível sem rolar num iPhone SE/8.
**Observado [OBSERVADA ×2]:** a 375 o botão ocupa 611–659 com a tabbar em 588–656 → `elementFromPoint` devolve `NAV.tabbar`; a 320 o botão está em 611–659 num viewport de 568. Após rolar, funciona (há padding). O que consome a dobra: app-bar 60 + título/progresso ~90 + nome 40 + thumb com dica 96 + "Série N de M" + frase de RIR + 4 chips + Carga + Reps.
**Severidade:** P1. **Correção (ordem dos blocos — CROSS-WORKFLOW: DESIGN na forma):** após a primeira série, recolher thumb+dica num `<details>`; ou bloco Carga/Reps/Concluir `position: sticky; bottom: calc(var(--tabbar-h) + safe-area)`. Meta: `bottom` do botão ≤ topo da tabbar a 375×667 sem rolar.
**Screenshot:** [`P1-execucao-concluir-fora-da-dobra-375.png`](screenshots/P1-execucao-concluir-fora-da-dobra-375.png)

#### P1-09 · Offline, enfileirar não muda nada na tela
ID: E02.
**Passos:** simular `navigator.onLine=false` (a guarda que `fila.js:532` usa); em `/hidratacao/` tocar +250; em `/treino/agora/` tocar "Concluir série 1".
**Esperado:** retorno local (total sobe, série marcada "aguardando rede").
**Observado [OBSERVADA ×2]:** a página não navega, a faixa "1 marcação esperando conexão" aparece, o form recebe `class="set-row--done"` — e nada mais muda: anel "500 ml", botões iguais; "Série 1 de 3", linhas "—", botão ainda "Concluir série 1". `.set-row--done` **não existe** em nenhum stylesheet (0 regras); o comentário em `fila.js:666-670` descreve um sumiço que não acontece. Tocar de novo enfileira uma segunda série com `op_id` distinto (por design da captura) sem indício de que a primeira contou. Não testado: falha real de socket, SW.
**Severidade:** P1. **Correção:** ouvir `nutriplan:enfileirado` por tela (água: somar o ml ao painel e marcar o botão; execução: escrever a série com selo "aguardando rede" e avançar o rótulo; refeição: "Registrada · aguardando rede") e dar estilo à classe já emitida; teste que procure a regra no CSS (espírito do `test_design_system`).
**Screenshot:** [`P1-offline-sem-retorno.png`](screenshots/P1-offline-sem-retorno.png)

#### P1-10 · Item avulso adicionado à lista pousa fora da tela, sem confirmação
ID: E03.
**Passos:** `/lista-de-compras/` → "Seus itens" → digitar → Adicionar.
**Esperado:** ver o item novo (ou um flash).
**Observado [OBSERVADA ×2]:** redirect `?opcao=A#seus-itens`; a 390 scrollY=3368 (máximo), seção em −195 px, item em −128/−56 — inteiro acima do viewport, que mostra "Como usar"; sem `[role=status]`/`.flash`. A 320 seção em −388 e scrollY < máximo (não é só clamp). A 430 o item aparece de raspão. **Causa [LIDA NO CÓDIGO]:** `shopping.html:107` sem `scroll-margin-top`; `plans/views.py:938` só redireciona. [HIPOTÉTICA] o encolhimento do layout entre o salto do fragmento e o layout final não foi isolado.
**Severidade:** P1 (ação principal sem evidência; convida a duplicar). **Correção:** `messages.success("X entrou na lista")` + âncora no próprio item com `scroll-margin-top` da app-bar; ou formulário no topo da seção com o item logo abaixo.
**Screenshot:** [`P1-lista-item-adicionado-fora-da-tela.png`](screenshots/P1-lista-item-adicionado-fora-da-tela.png)

#### P1-11 · "Continuar de onde parou"/"Começar treino": um rótulo, três destinos — e a Home pula a ficha
IDs: CA-04, MC-03 (+ TR-11, MOB-10, MKT-11, MC-21, CA-05 como P3 derivados).
**Passos:** ler os hrefs: Home `.agora__cta` → `/treino/agora/`; Home `.resumo-dia__treino` → `/treino/agora/`; painel `.btn--hoje` → `/treino/ficha/<id>/`; ficha → `/treino/agora/?exercicio=<próximo>`; leitura → `/treino/agora/?exercicio=<este>` (inclusive concluído). Tocar o da Home.
**Esperado:** rótulo é promessa de destino; "Começar treino" → ficha em toda porta (requisito fechado).
**Observado [OBSERVADA ×2]:** o toque da Home cai em "Treinando" dentro de um exercício. **[LIDA NO CÓDIGO]** `plans/agora.py:75-95` usa `reverse("workouts:now")` para os dois rótulos; `routine.html:248` documenta a decisão oposta com o defeito exato ("caía dentro de um movimento sem ter visto o treino"); `today.html:309` idem.
**Severidade:** P1 (caminho mais frequente viola o requisito; vocabulário inconsistente). Nuance: "Continuar" cair no próximo pendente é defensável quando já há séries hoje; o P1 mora em "Começar treino" e na Home. **Correção:** `acao.url` → `workouts:ficha` para "Começar treino"; decidir explicitamente o ramo "Continuar" e `.resumo-dia__treino` (→ painel); reservar "Continuar de onde parou" para o que retoma de fato; no painel "Abrir a ficha de hoje"; na leitura "Fazer este exercício". Teste em `config/test_b6_navegacao.py`: todo link com texto "Começar treino" resolve para `workouts:ficha`.
**Screenshots:** [`P1-continuar-de-onde-parou-home.png`](screenshots/P1-continuar-de-onde-parou-home.png), [`P1-continuar-de-onde-parou-execucao.png`](screenshots/P1-continuar-de-onde-parou-execucao.png)

#### P1-12 · "Compartilhar treino" com treino parcial gera imagem "TREINO CONCLUÍDO"
ID: MC-02.
**Passos:** `/treino/` com 4 de 16 séries (a tela diz "20% do treino"); rolar ao cartão do rodapé; renderizar o canvas do botão.
**Esperado:** peça honesta ("Treino de hoje · 4 de 16 séries") ou botão só ao concluir.
**Observado [OBSERVADA ×2, canvas renderizado]:** título "TREINO CONCLUÍDO" acima de "Peito, tríceps e ombro", 1 exercício / 4 séries / 1280 kg. **[LIDA NO CÓDIGO]** `routine.html:611` mostra o cartão com `resumo_hoje.tem_dados` (qualquer série); `:747-757` chama `desenhar("TRAINING_COMPLETE")` sem checar progresso; `card.js:191` escreve o título fixo. Colateral: "Minha evolucao. Meu plano." aparece duas vezes, uma sem acento (`routine.html:736`) — P3 DESIGN.
**Severidade:** P1 (conteúdo falso sai do app; números verdadeiros, rótulo mente). **Correção:** título condicionado a `estado.concluido` ("Treino em andamento · N de M séries" antes) e botão "Compartilhar o que já fiz"; ou cartão só ao concluir.
**Screenshots:** [`P1-compartilhar-treino-parcial.png`](screenshots/P1-compartilhar-treino-parcial.png), [`P1-compartilhar-card-treino-concluido.png`](screenshots/P1-compartilhar-card-treino-concluido.png)

#### P1-13 · Convite de instalação antes de existir conta, e um toque acidental o dispensa para sempre
IDs: MKT-02, MOB-05, NOVO-09, E15.
**Passos:** sessão limpa, abrir `/conta/cadastro/` (ou `/conta/entrar/`) a 390×844 e 320×568; observar o cartão; clicar em `input[name=first_name]`; recarregar; abrir `/conta/entrar/`.
**Esperado:** convite só depois do onboarding (ou da primeira ação de valor); toque fora só esconde na visita.
**Observado [OBSERVADA ×4]:** cartão fixo de 143 px cobre o campo Senha e as regras (cadastro), Senha + botão Entrar a 320 e metade de "Criar agora" a 390 (entrar); toque dentro do cartão não chega ao que está embaixo; um clique no campo do nome → `hidden`, `localStorage.nutriplan_pwa_dismissed="true"` — persistente após reload e em outras telas. **[LIDA NO CÓDIGO]** `pwa.js:321-324` clique fora chama `dispensar()` (definitivo, l.222-227), enquanto "Agora não" adia 30 dias (l.236-245): a resposta branda deliberada é mais leve que o acidente.
**Severidade:** P1. **Correção:** `data-sem-convite` escrito pelo servidor em cadastro, login, recuperação, onboarding e páginas de erro (o mecanismo já existe); toque fora só esconde na visita; dispensa definitiva só no "×"; momento certo: após a primeira refeição marcada ou série concluída. Mantém a regra de nunca cobrir a tabbar (`push/tests.py`).
**Screenshot:** [`P1-convite-instalacao-no-cadastro.png`](screenshots/P1-convite-instalacao-no-cadastro.png)

#### Reproduzidos e rebaixados a P2 pelos céticos

- **E01 · Sessão expirada engole o toque em silêncio** (P1 → **P2**). Reproduzido: cookie invalidado + POST `/agua/` → `/conta/entrar/?next=/agua/` sem frase; após login, Home com 500 ml (o toque se perdeu). Rebaixado porque (a) `config/acoes.py` `AcaoDeTela.get` já faz o GET em `/agua/` devolver a tela da ação — a metade "rota só-POST" do título está desatualizada; (b) nada foi gravado errado, a tela certa e o botão estão ali; (c) sessão de 2 semanas (padrão do Django) expirando no meio de um toque é raro. Correção: mensagem em `/conta/entrar/` quando há `next` ("Sua sessão venceu. O que você tocou não foi salvo — entre e refaça.") [`P2-sessao-expirada-login.png`](screenshots/P2-sessao-expirada-login.png).
- **CA-02 · `.semanas > .semana` vira 16 sub-cards** (P1 → **P2**). Reproduzido em Progresso (2 listas × 8) e Hidratação (7): 2 colunas, fundo cinza, 64,8 px por linha, valor caindo na linha 2; `app.css:3427` (0,2,0) vence `:7120` (0,1,0) em TODAS as listas porque as quatro usam as mesmas classes — o comentário de l.3414 descreve o defeito espelhado e a "correção" inverteu quem perde. Rebaixado: toda a informação está presente e correta; custo é ~300 px por lista e o número deslocado; a barra continua comparável entre treino e água (mesma coluna). CROSS-WORKFLOW: DESIGN na solução (renomear a família do peso) [`P2-progresso-semanas-subcards.png`](screenshots/P2-progresso-semanas-subcards.png).
- **Q-04 · Passo 4: opções equivalentes para 3 dias, sem prévia** (P1 → **P2**). Reproduzido: `split_for` com 3 dias dá UM→ABC, DOIS→ABC2, TRES→ABC. Rebaixado porque `/treino/` e Perfil avisam em voz alta ("Você escolheu 1 grupo por dia, que precisa de 5 dias… o app aplicou ABC") e a ficha é coerente — o defeito é de MOMENTO (explicação depois da decisão) e o cartão "1 grupo" com cinco dias é promessa vazia nessa frequência. `preferencia_muda_a_divisao` docstring envelheceu (diz False para 3 dias; é True). Tabela é CROSS-WORKFLOW: TRAINING [`P2-passo4-divisao-3-dias.png`](screenshots/P2-passo4-divisao-3-dias.png).

### 5.2 Problemas P2/P3 não submetidos a cético (uma observação, evidência declarada)

Todos os demais itens da seção 3 e da seção 7 têm uma única observação [OBSERVADA] (ou [LIDA NO CÓDIGO] quando indicado) e não passaram por um segundo auditor. Os mais relevantes, com o que a observação única viu:

| ID | Título | Evidência | Sev |
|---|---|---|---|
| NOVO-03 / TR-05 / MOB-09 / CA-10 / MC-05 / MKT-10 | "← Treino" no exercício pula a ficha | [OBSERVADA] por seis auditores, mas nenhum como cético formal; `href="/treino/"` | P2 |
| NOVO-04 / TR-04 / MOB-06 / CA-03 | Nome do exercício sem affordance; 47% do card morto | [OBSERVADA] ×4; cursor pointer, sem sublinhado/chevron; link 233×44 em card 350×66 | P2 |
| NOVO-05 / TR-07 | Dois iframes + anúncio de terceiro em "Músculos trabalhados" | [OBSERVADA] ×2; `iframes.length === 2` | P2 |
| NOVO-06 / CA-07 / MOB-12 | Título da execução 248×31 | [OBSERVADA] ×3; `app.css:5855-5862` | P2 |
| NOVO-07 / TR-10 | Texto do programa contradiz a semana | [OBSERVADA] ×2 | P2 CROSS-WORKFLOW: TRAINING |
| NOVO-02 | Ver refeição / Registrar A deixam o cabeçalho fora da tela | [OBSERVADA]; `getBoundingClientRect().top = −24` | P2 |
| TR-02 | Fechar a última série troca de exercício em silêncio | [OBSERVADA] | P2 |
| TR-03 | Desfazer série de outro exercício sem feedback/confirmação | [OBSERVADA] | P2 |
| TR-06 | "fechar" sobre a barra do YouTube | [OBSERVADA] | P2 CROSS-WORKFLOW: DESIGN |
| TR-08 / E08 | Reps 0 → 1; 999 → 100, sem aviso; valores somem após erro | [OBSERVADA] ×2 | P2 |
| TR-09 | "DOM" quebra em "DO/M" a 320 | [OBSERVADA] | P2 CROSS-WORKFLOW: DESIGN |
| UXA-04 | Alimento não reconhecido descartado em silêncio | [OBSERVADA] | P2 |
| UXA-05 | "Superávit +257 kcal/dia" lê-se como saldo de hoje | [OBSERVADA] + comentário em `today.html:130-175` | P2 |
| UXA-06 | Peso salvo sem eco nem correção na Home | [OBSERVADA] | P2 |
| UXA-07 | "Desbloqueadas 0" ao lado de "1/1" até visitar Conquistas | [OBSERVADA] + CLAUDE.md (`resumo` não chama `avaliar`) | P2 |
| PA-01 / MOB-04 | `dt` quebra intra-palavra; dois `<dl>` no mesmo card | [OBSERVADA] ×2 nas quatro larguras | P2 CROSS-WORKFLOW: DESIGN na solução |
| PA-02 / MC-06 / Q-08 / NOVO-12 | Editar mostra "Passo N/6 · X%" | [OBSERVADA] ×4 | P2 |
| PA-03 | Cada POST em Hidratação/Progresso empilha histórico | [OBSERVADA]; history.length 17 | P2 |
| PA-04 / E09 / CA-11 / MC-09 | Progresso abre com vazio sem título acima de dados | [OBSERVADA] ×4 | P2 |
| E04 | Sem dias: "Descanso também é parte do plano" para quem nunca montou ficha | [OBSERVADA] | P2 |
| E05 | Conquista vazia promete duas coisas (Áreas × Conquistas) | [OBSERVADA] | P2 |
| E06 | "N" solto nas páginas 404/403/CSRF/offline | [OBSERVADA] em produção (GET) | P2 CROSS-WORKFLOW: DESIGN no tamanho |
| E07 | Faixa da fila cobre +250/+500/+750 a 320 | [OBSERVADA] disparando os eventos à mão | P2 |
| E10 | GPS negado sem caminho de volta; sem `geolocation` botão mudo | [OBSERVADA] + `corrida.js:21,190-215` | P2 |
| CA-05 / MOB-07 / MC-08 / TR-14 | Dois "Treino de hoje", duas primárias, plural fixo | [OBSERVADA] ×4 | P2 |
| CA-06 | Cards de sessão sem `:active` | [LIDA NO CÓDIGO] `app.css:2017-2043, 2556` | P2 |
| CA-09 / MOB-08 | Ficha: hint antes da lista; CTA fora da dobra a 320 | [OBSERVADA] ×2 | P2 |
| CA-13 | Home escreve "19:00" do treino que saiu da interface | [OBSERVADA] + CLAUDE.md | P2 |
| MC-04 | Seis rótulos para `/treino/`; "Ver o treino completo" com dois destinos | [LIDA NO CÓDIGO] + [OBSERVADA] | P2 |
| MC-07 / NOVO-10 / PA-08 | Peso "82.30" no campo | [OBSERVADA] ×3 | P2 |
| MC-11 | "×1,44" quebra em "×1,4 / 4" | [OBSERVADA] | P2 |
| MC-12 | "Principal — composto, abre a sessão" no 2.º da lista | [OBSERVADA] + `exercicio.html:54` | P2 CROSS-WORKFLOW: TRAINING |
| MKT-03 | Sem tela "seu plano está pronto" | [OBSERVADA] | P2 |
| MKT-05 / Q-06 | Passo 6 lista os pilares duas vezes (1.465 px) | [OBSERVADA] ×2 | P2 |
| MKT-07 | Demo não linkado das telas anônimas | [OBSERVADA] | P2 |
| Q-03 | Janela de sono pré-preenchida | [OBSERVADA] + `forms.py:530-533` | P2 |
| Q-05 | Experiência perguntada sem dia marcado | [OBSERVADA] | P2 |
| Q-07 | Nome obrigatório sem consumidor | [LIDA NO CÓDIGO] | P2 |

### 5.3 Não reproduzidos

Nenhum item submetido aos céticos deixou de ser reproduzido: **21 de 21 confirmados** (18 na severidade original, 3 rebaixados). O que os céticos corrigiram no relato original:
- MOB-01: a 430 são **3** linhas, não 2.
- CA-02: a barra continua comparável entre treino e água — a perda é contra a largura pretendida, não entre listas.
- CA-04: a quarta tela é o **detalhe** do exercício, não a execução; o alvo da ficha é o próximo pendente (14), não o 11.
- E01: "next aponta para rota só-POST" está desatualizado (`AcaoDeTela.get` existe).
- TR-01: tocar o CTA sem preencher **não grava** e não avisa (detalhe novo).
- MOB-03: até o campo Reps já fica parcialmente coberto a 375.

Uma leitura transitória ("1 de 16 séries" na Home logo após Recalcular metas, voltando a "2 de 16") não foi reproduzida e não foi atribuída — provavelmente outro workflow usando a mesma conta.

---

## 6. Screenshots (índice)

Pasta [`screenshots/`](screenshots/). Caminhos relativos a este arquivo.

**P1 confirmados**
- `P1-ficha-nao-montada-home.png` — P1-01, primeira Home negando o treino de hoje
- `P1-ficha-obsoleta-zero-dias.png` — P1-02
- `P1-lista-nome-letra-por-letra-390.png`, `P1-lista-nome-letra-por-letra-320.png` — P1-03
- `P1-agua-zerar-colapsa-390.png`, `P1-agua-zerar-colapsa-320.png` — P1-04
- `P1-lembretes-sem-feedback.png` — P1-05
- `P1-execucao-serie-none.png` — P1-06
- `P1-entrada-vinheta-contraste-320.png`, `P1-entrada-vinheta-contraste-login-390.png` — P1-07
- `P1-execucao-concluir-fora-da-dobra-375.png` — P1-08
- `P1-offline-sem-retorno.png` — P1-09
- `P1-lista-item-adicionado-fora-da-tela.png` — P1-10
- `P1-continuar-de-onde-parou-home.png`, `P1-continuar-de-onde-parou-execucao.png` — P1-11
- `P1-compartilhar-treino-parcial.png`, `P1-compartilhar-card-treino-concluido.png` — P1-12
- `P1-convite-instalacao-no-cadastro.png` — P1-13

**P2 confirmados / representativos**
- `P2-sessao-expirada-login.png` — E01
- `P2-progresso-semanas-subcards.png` — CA-02
- `P2-passo4-divisao-3-dias.png` — Q-04
- `P2-execucao-dois-videos-anuncio.png` — NOVO-05/TR-07
- `P2-perfil-dt-quebra-palavra.png` — PA-01/MOB-04

**Telas-chave (390×844, página inteira)**
- `tela-entrar-390.png`, `tela-cadastro-390.png`
- `tela-onboarding-1.png`, `tela-onboarding-4.png`, `tela-onboarding-6.png`
- `tela-hoje-full.png`, `tela-treino-full.png`, `tela-ficha-full.png`, `tela-exercicio-full.png`, `tela-execucao-full.png`
- `tela-areas-full.png`, `tela-progresso-full.png`, `tela-perfil-full.png`, `tela-hidratacao-full.png`, `tela-lista-compras-full.png`

Os demais screenshots citados nas seções 3 e 5.2 (ex.: `artifacts/ux-audit/ux-treino/20-execucao-concluir-serie-none.png`) estão fora do repositório.

---

## 7. Severidade: contagem

Contagem **após deduplicação** (um defeito reportado por várias frentes conta uma vez; a severidade é a do cético quando houve).

| Sev | Critério | Quantidade |
|---|---|---|
| **P0** | bloqueia, perde dado ou registra errado sem saída | **0** |
| **P1** | informação falsa, ação principal sem evidência, ilegível ou inalcançável no fluxo central — reversível | **13** (todos confirmados por cético) |
| **P2** | confunde, contradiz, custa rolagem/toques, quebra régua do repositório; recuperável em uma tela | **41** (3 confirmados por cético; 38 com uma observação) |
| **P3** | polimento, copy, consistência, alvo colado, feedback de baixo custo | **51** |
| **OK** | verificado e sem problema | ~60 elementos |

Distribuição dos P1 por área: Treino 5 (P1-01, 02, 06, 08, 11, 12 — seis contando o compartilhamento), Alimentação/Lista 3 (03, 04, 10), transversal 4 (05 push, 07 entrada, 09 offline, 13 convite).

Lista dos P3 (dedup): rótulo Email/E-mail; marca sai da recuperação; erro do cadastro ancorado errado + abaixo da dobra (NOVO-11/E12); "Os dois juntos" (Q-10/MC-20); acorda/dorme invertido sem aviso; contador de passos (NOVO-13/E13/MKT-09); erro do passo 6 longe do campo (MKT-12); faixa SEG…DOM e pastilhas vestidas de botão (CA-08); "A" vs "A1" (CA-14); Sair vermelho (PA-07/MC-15); option summary sem affordance; resumo água span vs treino link; ofensiva sem porta; "abrir" fixo (MC-10); campo do peso com duas casas; tiles de semana parecem navegáveis; remover item sem feedback; "Voltar para o cardápio" → topo (MC-17); "3.000"/"3000", "82,50"/"82,3", "Recalcular metas"/"minha meta", "Saúde"/"app de saúde" (MC-18/PA-08); AGORA às 10:05 sem "pendente desde" (UXA-08); Compartilhar sem feedback (TR-12/PA-10); pular não sobrevive reload + "67s"/"1:08" (TR-13); 0×12 aceito; "Ver o treino completo" duplica ← Ficha; GPS sem link de volta (TR-15); Conquistas acende Áreas (PA-05); `aria-describedby` órfão (PA-06); Recalcular → Home (PA-09); Perfil no meio do onboarding; Hidratação sem zerar; Exportar sem confirmação; desfazer/zerar sobrepostos 3 px (MOB-11); gap 6 px na água (MOB-13); erro como flash longe do campo (E11); textos genéricos do Django e altura `min=0` (E14, MC-16); 404 sem porta de treino (E16); Registrar A primário vs B ghost (CA-12); Principal em 4 de 5 (CA-15); Editar dentro de summary (CA-16); `btn` sem variante e duas versões do botão de água (CA-17); card-destino sem loading (CA-18); Hidratação repete a origem da meta (CA-19); jargão "sinergista"/RIR/"na execução" (MC-13); voz "Registrar A" vs "Pulei" (MC-14); "Suas áreas" (MC-19/MKT-14); três componentes de escolha única (MKT-06); ícone vazio (MKT-08); sem "Nenhuma restrição" (MKT-13); nota de privacidade (MKT-15); `required` nativo ausente (Q-09); "Minha evolucao" sem acento.

---

## 8. Comparação com padrões atuais (mercado)

Referências: Duolingo, Noom, Headspace, Flo, Hevy, Strong, Fitbod, Yazio/Lifesum/MyFitnessPal, Things 3, Todoist (fontes na frente de mercado; padrões lidos em análises de texto, não observados nos apps).

| Referência (padrão) | NutriPlan hoje | Lacuna | Adaptação proposta | Por quê |
|---|---|---|---|---|
| Duolingo/Fitbod: a primeira tela depois do quiz PROVA que a resposta virou algo | primeira Home nega o treino de hoje | P1-01 | montar a ficha no Concluir, ou copy "ainda não montada" | "state change visibility": sem prova, a pessoa não tem evidência de que funcionou |
| Noom/Yazio/Lifesum: tela do plano ao fim do quiz | seis passos terminam no meio do dia comum | MKT-03 | cartão de resultado só na primeira visita: kcal, macros, refeições, divisão, dias, UMA ação "Ver meu dia" | converte seis telas de pergunta em evidência; sem promessa de data (o motor não faz) |
| Hevy: primeira série em < 90 s, sem quiz obrigatório; Duolingo: lição antes do cadastro | conta + 6 passos antes de qualquer tela; demo pronto e não linkado | MKT-07 | link "Ver o app com dados de exemplo" em login/cadastro; CTA "Criar minha conta" na CAPA do demo (não na barra, respeitando `demo/views.py`) | reduz o compromisso antes do valor com o que já existe |
| Noom/Duolingo: resposta anterior reaparece na pergunta seguinte | passo 4 fala em abstrato dos "seus dias" | MKT-04/Q-04 | "Você treina 3 dias (Seg, Qua, Sex)" e a semana resultante em cada cartão (`split_for` já decide) | pergunta concreta; a docstring do form já promete isso |
| Headspace/Duolingo: "marque todas" e "qual primeiro" são duas perguntas, a segunda só com o que foi marcado | passo 6 lista os cinco duas vezes | MKT-05/Q-06 | chips só com nome na segunda pergunta; JS progressivo esconde os não marcados; servidor continua validando | 1.465 → ~900 px sem reabrir a decisão "prioridade é pergunta própria" |
| Fitbod: pedido de permissão COM contexto e DEPOIS do primeiro treino | convite de instalação no cadastro; toque acidental dispensa para sempre | P1-13 | convite após a primeira ação de valor; toque fora só esconde | o pedido chega antes do valor e é consumido por um gesto que não era resposta |
| Duolingo/Noom: um componente de opção do início ao fim | segmentado + cartão + rádio clássico para a mesma operação | MKT-06 | cartão para escolha com frase; segmentado para duas palavras; rádio clássico fora do wizard | constância faz "toque no cartão, Continuar" virar automático — CROSS-WORKFLOW: DESIGN |
| Duolingo/Noom: a barra mede o feito; o texto mede a posição | "100%" antes de responder; 66% onde é 67 | MKT-09 | `round((posicao−1)/total*100)`; 100% na tela de montagem | a barra só chega ao fim quando termina |
| Flo/Noom: "Nenhuma dessas" fecha lista múltipla | restrições sem "Nenhuma" | MKT-13 | caixa "Nenhuma restrição" (o passo 6 já usa esse princípio) | distingue "não tenho" de "pulei" |
| Flo: depósito de confiança antes de dado íntimo | passo 1 explica o uso, não o que NÃO é feito | MKT-15 | uma `.form__nota`: "Seus dados ficam só na sua conta…" (se for contratualmente verdade) | o CLAUDE.md já trata peso como dado de saúde; falta dizer na tela |
| Things/iOS: "voltar" nomeia e leva à tela anterior | "← Treino" pula a ficha | NOVO-03 | "← Ficha"/"← Treino A1" na leitura | um nível por vez |
| Hevy/Strong: um CTA primário por tela; rotinas como lista secundária | painel com duas primárias e três alvos para a mesma ficha | CA-05/MKT-11 | uma primária; remover "Ver ficha do Treino A"; Compartilhar como ghost | hierarquia diz o que fazer |
| Hevy/Strong: descanso automático, valores anteriores, desfazer, progresso "Exercício 1/8 · 1/25" | **já cumprido** | — | preservar | é o padrão do mercado, e está aqui |
| Things/iOS: `:active` uniforme em tudo que é tocável | botões, choice-card, tabbar, chips têm; cards de sessão não | CA-06 | acrescentar `.sessao-cartao` e parentes às três listas | "a diferença entre tocar uma vez e tocar quatro" (comentário do próprio CSS) |

---

## 9. O que está bom e deve permanecer

Com a decisão do CLAUDE.md quando houver. Nada aqui deve ser "consertado".

- **Arquitetura de três telas de Treino** (painel → ficha → execução), cada uma respondendo uma pergunta; ficha de outro dia não executa (linha é `<div>`); escolha de exercício estrita (404 em id inválido). *CLAUDE.md: "A área de Treino são TRÊS telas"; "A ficha de OUTRO dia não executa"; "Escolher exercício é ESTRITO".*
- **Vídeo inline** na leitura e na execução: abre no lugar do poster, fecha sem navegar, sem entrada no histórico, sem perder carga/reps; bfcache restaura vídeo e anatomia abertos ao voltar. *CLAUDE.md: "Sobreposição: `<details>` antes de `<dialog>`, e TELA antes das duas."* Requisito do dono cumprido.
- **Execução no padrão Hevy/Strong:** ±2,5 com vírgula, carga sugerida da última vez, pastilhas, descanso automático com "pular" e "pode ir", reload mostra o tempo que FALTA, "Depois" mantém o descanso, desfazer idempotente, peso do corpo esconde ±2,5. *CLAUDE.md: idempotência por `op_id`, retry do `IntegrityError`, dia viaja com o evento.*
- **Erros de carga** humanos ("Carga inválida — use números, como 42,5.", "fora do que uma barra aguenta").
- **Barra de quatro itens** cabendo a 320 (71×54), acendendo por destino, com safe-area; **zero rolagem horizontal** em 14 telas × 4 larguras; **zero fonte < 11 px**; **um único alvo < 44×44** em ~200 medidos. *CLAUDE.md: "Alvo de toque: 44px de altura E de largura"; "Nada rola na horizontal"; "A barra de baixo responde FREQUÊNCIA; o mapa responde ESTRUTURA".*
- **Toque duplo protegido** nos quatro pontos testados (+250, Concluir série, desfazer, Adicionar): `disabled` + `aria-busy` no tick seguinte, com pulso.
- **Ações destrutivas com degrau:** "zerar" → "apagar a água de hoje" (diz o que vai acontecer); Sair com confirmação; Excluir em página própria, sem barra, com a lista do que será apagado (7 planos, 1 água, 2 pesagens…), senha obrigatória, flash ao apagar — provado ponta a ponta.
- **Home: toda ação é POST + redirect com âncora** (`#slot-N`, `#hidratacao`): funciona sem JS, voltar não repete ação, a pessoa não perde o lugar na página longa. Água soma no banco (`Least(F("ml") + ml, 10000)`). *CLAUDE.md: "Água soma NO BANCO".*
- **Personalização visível e honesta:** selo "sua área", card promovido logo abaixo do resumo e nunca acima do AGORA, cardápio 100% vegano com restrição marcada, horários seguindo a janela, quem não declarou nada vê a Home canônica. *CLAUDE.md: "A Home organiza pela área principal, e o AGORA continua sendo o primeiro bloco"; "Quem não declarou nada vê a Home de antes"; "Interesse ORGANIZA; ele não restringe".*
- **Passo 6:** "Não quero priorizar agora" é resposta legítima; marcar a principal marca a área; uma área dispensa a pergunta; erro claro sem perder marcações. *CLAUDE.md: "A prioridade é uma pergunta PRÓPRIA".*
- **Onboarding:** cadastro mínimo; passo salvo a cada Continuar; retomada exata após logout; pular por URL redireciona; escolhas abrem SEM padrão marcado (`escolhas_abertas`); cada passo explica para que serve a resposta; validação humana com exemplo no passo 1; chips de dia com aria-label completo; a divisão que cede, cede em voz alta no painel e no Perfil. *CLAUDE.md: "Preferência de divisão que cede, cede EM VOZ ALTA".*
- **Login e recuperação:** erro com role=alert, e-mail preservado, senha limpa, frase útil; olho com aria-pressed; "se existir uma conta…", validade de 3 h, dica do spam.
- **Lista de compras:** marcação por estado absoluto, persistente, por opção A/B; texto explica "~" e cru/cozido. *CLAUDE.md: "A marcação da lista é ESTADO ABSOLUTO".*
- **Estados vazios que convidam:** Treino e Água no Progresso (dentro do próprio card, com a saída ao lado — modelo para o de refeições), Conquistas, Corridas, Hidratação, `/treino/` sem dias ("Cadastrar meus dias de treino" com `?origem=treino` e Salvar voltando ao Treino). *CLAUDE.md: "Estado vazio é convite".*
- **Páginas de erro** com cara do produto, sem vazar framework, com saída; 500 autocontido de propósito.
- **Sistema visual existente:** 70 tokens, `.card`/`.btn`/`.chip`/`.pill`/`.tile`/`.data-list`/`.empty-state`/`.hint`; `.card .card` = 0 em todas as telas; `.card__head a`, `.btn-link` e `a.chip` crescem a 44 px por padding negativo sem mudar o visual (padrão a copiar). *CLAUDE.md: "Antes de criar componente novo, procure".*
- **Progresso:** gráfico SVG com `role=img` e aria-label que resume a série; validação do peso completa ("abc", 500, vazio, "82.25").
- **Exportações:** JSON com `Content-Disposition` e nome datado; TCX com nota honesta sobre Saúde/Health Connect.
- **Demo** completo com personagem fictício declarado.

---

## 10. O que deve ser removido

- **"Ver ficha do Treino A · N exercícios"** no painel — destino idêntico ao CTA; o card A1 já é a segunda porta (CA-05, MKT-11). Ganha ~100 px de dobra.
- **"19:00" do treino na Home** (`.agora__detalhe` e `.resumo-dia__treino`) — valor que saiu da interface em 10/09/2026 e que a pessoa não pode editar (CA-13). *CLAUDE.md: "exibir um valor que não participa de nada e não dá para editar faz procurar o botão que não existe".*
- **Barra "Passo N/6 · X%" em modo edição** (PA-02).
- **Classe morta `set-row--done`** em `fila.js` (ou dar-lhe estilo real) e o comentário que descreve um sumiço que não acontece (E02).
- **Segundo iframe de "Músculos trabalhados"** enquanto o primeiro está aberto — um player por vez; e mídia com banner de terceiro sai da curadoria (NOVO-05/TR-07; a escolha da mídia é CROSS-WORKFLOW: TRAINING).
- **Pílula "Principal" em 4 de 5 itens** — etiqueta que não discrimina (CA-15).
- **Repetição do nome do alimento dentro da quantidade** ("~1,4 kg de arroz branco (cru)") — o nome está no label ao lado (P1-03).
- **Frase "calculada a partir do seu peso"** duplicada na mesma dobra de Hidratação (CA-19).
- **Hint de cinco linhas sobre "aparece duas vezes na semana"** antes da lista da ficha — vai para depois da lista ou para um `<details>` (CA-09).
- **"Ver o treino completo"** duplicando "← Ficha" na execução (um só).
- **`btn` sem variante** em "Minhas conquistas" (CA-17).
- **"Editar" dentro de `<summary>`** em "Dados do cálculo" (CA-16).
- **Convite de instalação** em cadastro, login, recuperação, onboarding e páginas de erro (P1-13).
- **Campo "Nome" como obrigatório** no cadastro (Q-07) — opcional ou no Perfil (ver Decisões para o dono).
- **Frase "Descanso também é parte do plano — é nele que o músculo cresce"** para quem nunca cadastrou dia (E04) — o vazio de `/treino/` já diz o certo.
- **"cumpra treino"** na ofensiva de quem não tem dia previsto (E14).
- **Rótulo "Compartilhar treino" com título "Treino concluído"** enquanto o treino não está concluído (P1-12).

---

## 11. Novo fluxo proposto (mapa alvo)

Mudanças em relação ao mapa da seção 1 — só o que muda. Barra de baixo, cinco pilares, Perfil em Áreas e as três telas de Treino permanecem.

```
ANÔNIMO
  entrar ──"Ver o app com dados de exemplo"──▶ demo (capa com "Criar minha conta")
  entrar ◀──▶ cadastro (nome opcional; sem convite de instalação)
  senha/ ── marca inerte (não sai do fluxo)

ONBOARDING (3 telas antes do primeiro cardápio — ver seção 12)
  1 dados ─▶ 2 objetivo + rotina + dias (opcional) + restrições (details) ─▶ montagem
  montagem: monta dieta E FICHA (quando há dias) ─▶ cartão "Seu plano está pronto" ─▶ Hoje

HOJE
  AGORA "Começar treino" ─▶ FICHA de hoje            (hoje: execução)   P1-11
  AGORA "Continuar de onde parou" ─▶ execução do próximo pendente (mantém)
  resumo "treino" ─▶ painel /treino/                  (hoje: execução)
  cartão da área Treino: 3 ramos — tem treino / descanso / ficha ainda não montada  P1-01
  sem plano com zero dias: sem cartão de séries        P1-02
  Ver refeição / Registrar ─▶ card com cabeçalho visível (scroll-margin)   NOVO-02
  "Dados do cálculo · Editar" ─▶ /conta/onboarding/1/ direto (não Perfil)  MC-10

TREINO (painel)
  UMA primária "Começar treino" / "Abrir a ficha · 1 de 5 feitos" ─▶ ficha
  (remove "Ver ficha do Treino A")
  cards A1/B/C/A2 ─▶ ficha (com :active)
  rodapé "Feito hoje" (renomeado), Compartilhar como ghost, título honesto  P1-12
  Editar dias ─▶ passo 3 SEM stepper ─▶ Salvar ─▶ /treino/ (e desativa plano com zero dias)

FICHA
  h1 ─▶ linha de fatos ─▶ CTA ─▶ lista (hint depois)                CA-09
  card inteiro = link para a leitura, com seta; "Fazer" como segundo alvo 44×44  CA-03
  "Concluído: 4/4" = estado (não porta)                              P1-06

EXERCÍCIO (leitura)
  "← Ficha A1" ─▶ ficha de origem (?de=ficha, lista fechada)          NOVO-03
  um player por vez; "fechar" fora da barra do YouTube
  CTA "Fazer este exercício" (só se pendente)

EXECUÇÃO
  exercício concluído: pastilhas + "Concluído" + desfazer + próximo   P1-06
  Carga/Reps/Concluir dentro da dobra a 375 (sticky ou details da dica)  P1-08
  ao fechar a última: "Supino concluído · 4/4 — agora: Flexão"       TR-02
  desfazer: "Série 2 do Supino desfeita" em [role=status]            TR-03/MOB-12
  offline: série escrita com selo "aguardando rede"                  P1-09

HIDRATAÇÃO / PROGRESSO
  POST não empilha histórico (replaceState após PRG)                  PA-03
  "← Hoje" quando se chega pela Home; "zerar" nas duas telas
  Progresso: vazio de refeições dentro da seção, com título           PA-04

LISTA
  Adicionar ─▶ flash + âncora no item                                 P1-10
  "Voltar para o cardápio" ─▶ /#cardapio

CONQUISTAS
  aba = a de origem (Progresso ou Áreas) via ?de=, ou nenhuma         PA-05
  link de volta próprio

ÁREAS
  "SUAS ÁREAS" ─▶ "MAIS ÁREAS" (rótulo; conteúdo não muda)            MC-19
  módulo Conquistas com a mesma frase de vazio de /conquistas/        E05

PERFIL
  Editar ─▶ formulário SEM stepper ─▶ Salvar ─▶ Perfil#bloco           PA-02
  Recalcular ─▶ Perfil#metas                                          PA-09
  Sair como ghost; Excluir mantém link                                PA-07 (DESIGN)

ENTRADA (login/cadastro)
  sem convite de instalação; vinheta com contraste ≥ 4,5:1 (DESIGN)   P1-07, P1-13
  login por redirecionamento com next: "Sua sessão venceu…"           E01
```

---

## 12. Novo onboarding proposto

### 12.1 Mínimo para o primeiro resultado (cardápio + metas + ficha)

**Três telas antes do primeiro cardápio** (hoje: cadastro + 6 passos, 15 perguntas; proposto: 9 perguntas). Nenhuma pergunta adiada muda a meta calórica (seção 2.3).

| Tela | Campos | Nota |
|---|---|---|
| Cadastro | e-mail, senha, confirmação; **nome opcional** | ou nome removido e perguntado no Perfil (Decisão D3) |
| 1 · Seus dados | sexo, nascimento, altura, peso | inalterada; cabe numa tela |
| 2 · Seu plano | objetivo (cartões); rotina fora do treino (cartões); **"em quais dias você treina?"** (chips, opcional, "pode deixar em branco"); **"alguma restrição?"** (caixas + "Nenhuma restrição", recolhidas em `<details>` "Tenho restrição alimentar") | restrições ficam porque ELIMINAM receitas — vegana vendo frango é primeiro resultado errado; custo zero para quem não tem |
| Montagem | monta dieta **e ficha** (quando há dias) — a frase "Estruturando a sua divisão de treino…" passa a ser verdade | fecha o P1-01 na raiz (CROSS-WORKFLOW: TRAINING decide se `sync_active_routine` é chamado aqui) |
| Resultado (primeira visita) | cartão no topo da Home: meta kcal, macros, N refeições, divisão e dias; UMA ação "Ver meu dia" | sem gráfico, sem promessa de data (MKT-03) |

### 12.2 Personalização progressiva: onde cada pergunta adiada é feita

Padrão a estender: o que `/treino/` sem dias já faz (convite + `?origem=` em lista fechada + Salvar voltando à origem).

| Pergunta adiada | Onde e quando | Como | Estado de quem não responde |
|---|---|---|---|
| **Experiência** | painel `/treino/` na primeira abertura da ficha | cartão "Montada para quem treina há mais de 6 meses — é o seu caso?" com os três níveis; Salvar remonta (`plano é retrato`) | `""` → teto 20 (comportamento de hoje); Perfil diz "não informada" |
| **Divisão** | mesmo cartão, só para ≥ 3 dias | com a **prévia real por frequência** ("Com 3 dias: A-B-C — peito/tríceps, costas/bíceps, pernas/ombros"); opções equivalentes fundidas | divisão padrão da frequência; o painel já explica em voz alta |
| **Janela de sono** | topo do cardápio de Hoje | linha "Refeições distribuídas das 07:00 às 23:00 · ajustar" (`?origem=hoje`) abrindo só os dois campos | 07:00–23:00 declaradamente (é o que já acontece) |
| **Cardápio rápido/variado/econômico** | cardápio de Hoje | chip "Prefiro receitas rápidas" que remonta (`plan_is_current` já invalida) | VARIED (default do modelo) |
| **Interesses + prioridade** | Home a partir do segundo dia de uso; sempre em Áreas › Perfil | UMA pergunta: "Qual área organiza sua Home?" (cinco + "nenhuma"); marcar a principal marca o interesse (como `clean` já faz); interesses adicionais na mesma tela como caixas secundárias | `prioridade == ""` → Home canônica (estado de verdade, CLAUDE.md) |
| **Nome** | Perfil | campo opcional | e-mail de senha já tolera vazio |
| **Instalação do PWA** | após a primeira refeição marcada ou série concluída | convite com contexto; toque fora só esconde | — |
| **Lembretes push** | após a primeira refeição marcada | botão com contexto ("aviso 10 min antes de cada refeição") e feedback real quando negado | — |

### 12.3 Regras do wizard que ficam

- Progresso mede o **feito** (`(posicao−1)/total`), texto mede posição; 100% só na montagem.
- Escolhas abrem em branco (`escolhas_abertas`) — inclusive hora de acordar/dormir se ela ficar no wizard.
- Erro ancorado ao campo (`add_error('prioridade', …)`), `autofocus` no primeiro inválido, `required` nativo no primeiro rádio do grupo, mensagens próprias ("Escolha um objetivo para continuar.").
- Um componente por tipo de escolha (cartão para escolha com frase; segmentado para duas palavras) — CROSS-WORKFLOW: DESIGN.
- Modo edição sem stepper, com título de bloco.
- Decisões preservadas: prioridade é pergunta própria; uso não é intenção declarada; interesse organiza sem restringir; o passo de divisão vem depois dos dias.

---

## 13. Sistema de cards — CROSS-WORKFLOW: DESIGN

Este brief fixa **regras de uso** (quando cada tier aparece, o que pode ser tocado, o que se aninha); a receita visual (raio, sombra, contorno, cor) é do workflow de design. Inventário medido [LIDA NO CÓDIGO + OBSERVADA] em CA-01.

### 13.1 Três tiers

| Tier | Papel | Exemplos hoje | Interação |
|---|---|---|---|
| **PAINEL** | seção da página; contém ações; nunca é link | `.card` (106 usos), `.meal`, `.pesar`, `.ofensiva`, `.today-hero`, `.agora-card` | nenhuma no próprio card |
| **ITEM** | linha de lista: **ou é destino, ou tem ação — nunca os dois** | `.sessao-cartao`, `.modulo` (destino); `.option`, `.ficha-item` (ação); `.semana` (linha) | link cobrindo 100% da área OU botões com variante declarada |
| **ETIQUETA** | rótulo sem superfície tocável | `.pill`, `.chip` estático, `.session__badge`, `.tile` | nenhuma; não veste borda+fundo+quina de controle |

### 13.2 Seis regras

1. **Painel nunca é link.** Ação mora em botão dentro dele, com variante declarada (`btn--primary`/`--ghost`/`btn-link`); `.btn` sem variante é proibido (teste por grep).
2. **Card-destino = `<a>` cobrindo 100% da área**, seta à direita, `:active` da seção 10, cursor pointer. Segundo alvo (ex.: "Fazer") é irmão de 44×44 com ≥ 8 px de folga. Área tocável ≥ 90% do card (teste em `TouchTargetTests`).
3. **Superfície não contém superfície do mesmo tier.** Item dentro de painel é o único aninhamento permitido, com UMA receita (hoje há três raios para o mesmo nível — DESIGN escolhe).
4. **Uma ação primária por tela.** Segundas ações são ghost/btn-link. Hoje: painel de Treino tem duas primárias; Home tem até seis com refeições abertas.
5. **Mesmo rótulo ⇒ mesmo destino.** "Continuar de onde parou", "Começar treino", "Ver o treino completo" hoje violam.
6. **Elemento não interativo não toma emprestada a receita de elemento interativo** (faixa SEG…DOM, pastilhas de série, tiles de semana).

### 13.3 Famílias e estados

| Família | Estados obrigatórios | Onde falta hoje |
|---|---|---|
| Painel | repouso · com dado · vazio (dentro do próprio painel, com a saída ao lado) · erro inline | Progresso (vazio fora da seção); Dia a dia sem título |
| Item-destino | repouso · `:active` · `aria-busy` ao navegar (cold start de 50 s) · hoje/atual (texto + borda, nunca só cor) | `.sessao-cartao` sem `:active`; nenhum card-destino tem loading (CA-18) |
| Item-ação | pendente · feito (com desfazer) · pulado · aguardando rede · erro | refeição e água não têm "aguardando rede"; série idem (P1-09) |
| Item de execução | série pendente · atual · feita · **exercício concluído** | estado concluído inexistente (P1-06) |
| Etiqueta | estática; "hoje"/"sua área"/"principal" por texto | ok |
| Botão | primário · ghost · quiet · link · perigo (só irreversível) · `disabled`+`aria-busy` | Sair usa perigo; `btn` sem variante; duas versões do botão de água |

### 13.4 Testes a acrescentar (config/test_design_system.py e config/tests)

- `.card .card` continua 0 (já vale; congelar).
- Todo `<a>` com classe de card está nas três listas de `:active`/transition/reduced-motion.
- Área tocável de `.ficha-item` ≥ 90%.
- Nenhum `class="btn"` sem variante nos templates.
- `.semana` de treino/água não recebe `background`/`padding` (CA-02).

---

## 14. Regras de interação

**Expectativa do clique**
- O que parece tocável é tocável; o que é tocável parece (chevron, sublinhado ou cor). Vale para o nome do exercício na ficha (hoje invisível) e para a linha da opção A/B.
- O rótulo diz o destino, e o mesmo rótulo tem sempre o mesmo destino. "Voltar" (←) volta UM nível e nomeia o nível ("← Ficha A1").
- Toda tela fora da barra tem link de volta próprio (Corridas, Hidratação, Conquistas hoje não têm).
- Uma primária por tela.

**Alvos**
- 44×44 nas duas dimensões (régua do CLAUDE.md; um único alvo hoje abaixo: 248×31). Folga ≥ 8 px entre alvos vizinhos (desfazer/zerar sobrepostos em 3 px; água com 6 px).
- Card-destino: o card inteiro. Segundo alvo separado por ≥ 8 px.
- A ação principal da tela cabe na dobra a 375×667 sem rolar (execução hoje não cabe; ficha a 320 não cabe).

**Feedback**
- Toda ação muda algo visível **onde o dedo está** em < 100 ms (`:active`) e confirma o resultado no lugar (estado do card) ou em `[role=status]` — inclusive desfazer ("Série 2 desfeita"), adicionar item, compartilhar ("imagem salva"/"cancelado"), exportar.
- Feedback nasce **dentro do viewport**: `scroll-margin-top` da app-bar em toda âncora; após POST com PRG a página pousa no que mudou.
- Offline: retorno local imediato com selo "aguardando rede"; a faixa da fila reserva espaço e não cobre botões.
- Permissão negada (push, GPS) diz o que aconteceu **e como reverter**; texto não é sobrescrito.
- Erro de formulário: colado ao campo, `aria-invalid` + `aria-describedby` com id existente, foco no primeiro inválido, valores digitados preservados (execução hoje descarta), mensagem com exemplo e faixa.
- Card-destino recebe `aria-busy` até `pageshow` (cold start).

**Ações destrutivas**
- Reversível (sair, desfazer): sem confirmação, com feedback do que foi desfeito.
- Irreversível de baixo custo (zerar água, remover item avulso): confirmação inline que **diz o que vai acontecer** ("apagar a água de hoje"), sem deformar o que está sendo apagado; ou desfazer por alguns segundos.
- Irreversível de alto custo (excluir conta): página própria, lista do que será apagado, senha. (Já é assim.)
- Vermelho só no irreversível; Sair não é vermelho.
- Desfazer que atinge outro contexto (série de outro exercício) nomeia o alvo e pede confirmação a partir do segundo toque.

**Toque duplo e reenvio**
- Botão de POST: `disabled` + `aria-busy` no tick seguinte (já é assim). Idempotência por `op_id` onde a fila reenvia (água, série, desfazer, suplemento); refeição por `update_or_create`; lista por estado absoluto. *CLAUDE.md.*
- Offline, a página não recarrega entre toques: cada captura sorteia seu `op_id`, e a tela precisa mostrar que o primeiro contou para o segundo não ser um erro.
- POST com PRG não empilha histórico: um "voltar" sai da tela.

**Vídeo e sobreposição**
- Um player por vez; "fechar" fora da área que o embed usa; abrir/fechar não navega nem perde estado (já é assim).
- `<details>` antes de `<dialog>`, tela antes das duas. *CLAUDE.md.*

**Números**
- Vírgula decimal e uma regra de milhar em toda tela (`floatformat`/`number_format`), inclusive no valor inicial dos inputs; `white-space: nowrap` em número ("×1,44"). *CLAUDE.md.*

---

## 15. Roadmap em três ondas

### Onda 1 — CONFIANÇA (cliques, navegação, voltar, cards, perigosas, erros)

Tudo que é P1 e o que faz a tela mentir ou o toque se perder.

| # | Item | IDs | Dono |
|---|---|---|---|
| 1.1 | Home: terceiro ramo "ficha ainda não montada" no cartão da área e no resumo; montar a ficha no Concluir do onboarding e ao salvar dias | P1-01 | UX + **TRAINING** (quem chama `sync_active_routine`) |
| 1.2 | Zero dias desativa a rotina (Home e ofensiva respeitam `has_training_days`) | P1-02 | UX + TRAINING |
| 1.3 | "Começar treino" → ficha em toda porta; "Continuar" e resumo decididos; rótulos por destino; teste em `test_b6_navegacao` | P1-11, MC-04, MC-21 | UX |
| 1.4 | Execução: estado "exercício concluído"; sem "Série None"; CTA/"Concluído" viram estado | P1-06 | UX |
| 1.5 | Execução: Concluir dentro da dobra a 375 (sticky ou dica recolhida) | P1-08 | UX + DESIGN |
| 1.6 | Lista: quantidade quebra, sem repetir o nome; dentro do label | P1-03 | UX + DESIGN |
| 1.7 | Água: confirmação de zerar em linha própria; `nowrap` no valor; folga entre desfazer/zerar | P1-04, MOB-11 | UX |
| 1.8 | Lista: flash + âncora no item adicionado com `scroll-margin-top` | P1-10, NOVO-02 (mesma `scroll-margin`) | UX |
| 1.9 | Push: `render()` não sobrescreve "Permissão negada"; GPS diz como reverter; sem `geolocation` botão desabilitado | P1-05, E10 | UX |
| 1.10 | Offline: retorno local por tela em `nutriplan:enfileirado`; estilo para a classe; faixa reserva espaço; teste que procura a regra no CSS | P1-09, E07 | UX |
| 1.11 | Convite de instalação fora de cadastro/login/onboarding/erros; toque fora só esconde | P1-13 | UX |
| 1.12 | Compartilhar: título honesto por estado; botão só/com rótulo "o que já fiz" | P1-12 | UX |
| 1.13 | Vinheta das telas de entrada com contraste ≥ 4,5:1 + teste de contraste sobre gradiente | P1-07 | **DESIGN** + QA |
| 1.14 | "← Ficha" na leitura do exercício (`?de=ficha`, lista fechada) | NOVO-03 | UX |
| 1.15 | Ficha: card inteiro é link com seta; "Fazer" como segundo alvo | CA-03 | UX + DESIGN |
| 1.16 | Reps: recusar fora do teto com mensagem; preservar valores após erro | TR-08 | UX (teto: TRAINING) |
| 1.17 | Desfazer série: status "Série N de X desfeita"; confirmação quando é de outro exercício; aviso ao fechar a última série | TR-02, TR-03, MOB-12 | UX |
| 1.18 | Login por redirecionamento: "Sua sessão venceu…" | E01 | UX |
| 1.19 | Sessão/Progresso: PRG sem empilhar histórico | PA-03 | UX |
| 1.20 | Um player por vez; "fechar" fora da barra do YouTube; mídia sem banner de terceiro | NOVO-05, TR-06 | UX + DESIGN (+ TRAINING na curadoria) |
| 1.21 | `.semanas` sem colisão de seletor + teste | CA-02 | DESIGN |
| 1.22 | Alimento não reconhecido em "Comi outra coisa" avisa | UXA-04 | UX |
| 1.23 | Peso: eco do valor com "editar" na Home | UXA-06 | UX |
| 1.24 | Título 248×31 → 44 px | NOVO-06 | UX |

### Onda 2 — EXPERIÊNCIA (onboarding, hierarquia, cliques a menos, vazios, mensagens, feedback)

| # | Item | IDs |
|---|---|---|
| 2.1 | Onboarding em três telas + montagem que monta tudo + cartão "seu plano está pronto" (Decisão D1) | Q-00, MKT-03 |
| 2.2 | Personalização progressiva: experiência e divisão no painel (com prévia real); janela de sono e estilo no cardápio; prioridade na Home a partir do 2.º dia (Decisão D2) | Q-03, Q-04, Q-05, MKT-04 |
| 2.3 | Passo 6 compacto (chips na segunda pergunta; JS progressivo; erro no campo) enquanto D1 não decide | MKT-05, Q-06, MKT-12 |
| 2.4 | Modo edição sem stepper; Salvar volta ao bloco; Recalcular volta ao Perfil | PA-02, PA-09 |
| 2.5 | Painel de Treino: uma primária; sem "Ver ficha"; rodapé "Feito hoje" com plural; hero com `rotulo` | CA-05, CA-14, MOB-07 |
| 2.6 | Ficha: ordem h1 → fatos → CTA → lista; hint depois; pílula "Principal" só onde discrimina | CA-09, CA-15 |
| 2.7 | Progresso: vazio de refeições dentro da seção com título; conquistas coerentes (resumo lê a próxima mais barata ou a barra não diz 1/1 sem "desbloqueada") | PA-04, UXA-07 |
| 2.8 | Copy: seis rótulos de `/treino/` → um; "dia de hoje" → "Hoje"; "Suas áreas" → "Mais áreas"; conquista vazia com uma fonte; "descanso" só para quem tem rotina; jargão; voz dos botões da refeição; "Principal — abre a sessão"; texto do programa condicionado à frequência | MC-04, MC-17, MC-19, E05, E04, MC-13, MC-14, MC-12, TR-10 |
| 2.9 | Números: vírgula no valor inicial dos inputs, uma casa no peso, uma regra de milhar, `nowrap` em `dd.num` | MC-07, MC-11, MC-18 |
| 2.10 | Hero da Home: "Superávit" rotulado como planejado; AGORA "pendente desde 07:30" | UXA-05, UXA-08 |
| 2.11 | Demo linkado de login/cadastro; CTA na capa | MKT-07 |
| 2.12 | Erros: mensagens próprias nos passos 2/4/5, `required` nativo, foco no inválido, flash com `role=alert`, campo marcado inválido em Progresso/Hidratação, `aria-describedby` com id existente | MC-16, Q-09, E11, PA-06, E12 |
| 2.13 | Tela do exercício: "Como fui" e "Papel" com frases sem promessa de ordem | MC-12 |
| 2.14 | Corridas/Hidratação/Conquistas com link de volta; Conquistas acende a aba de origem; `zerar` em Hidratação | PA-05 |
| 2.15 | Perfil: `dt` com largura mínima ou empilhado; um `<dl>` por card; Sair como ghost | PA-01, PA-07 (DESIGN) |
| 2.16 | 404 com porta de treino quando o caminho começa por `/treino/`; "N" → marca nas páginas de erro | E16, E06 |

### Onda 3 — POLIMENTO (animações, microinterações, transições, refinamento)

| # | Item | IDs |
|---|---|---|
| 3.1 | `:active` em todo card-destino; `aria-busy` em navegação de card até `pageshow` | CA-06, CA-18 |
| 3.2 | Rótulo "abrir" → "fechar" (ou chevron) em `[open]` | MC-10 |
| 3.3 | "pular" descanso persistido; relógio com um formato desde o primeiro paint | TR-13 |
| 3.4 | Compartilhar com estado "gerando…"/"salva"/"cancelado" (treino e conquista) | TR-12, PA-10 |
| 3.5 | Faixa SEG…DOM e pastilhas de série sem receita de botão; "DOM" a 320 | CA-08, TR-09 (DESIGN) |
| 3.6 | Um componente de escolha única no wizard; ícone só quando existe; "Os dois juntos" com efeito | MKT-06, MKT-08, Q-10 (DESIGN) |
| 3.7 | Registrar A/B com a mesma variante ou motivo no rótulo | CA-12 (DESIGN) |
| 3.8 | Gap 8 px na fileira de água; botão de água unificado nas duas telas | MOB-13, CA-17 |
| 3.9 | "Nenhuma restrição"; nota de privacidade no passo 1; contador de passos honesto | MKT-13, MKT-15, MKT-09 |
| 3.10 | Marca inerte na recuperação de senha; "Voltar para o cardápio" → `#cardapio`; Exportar com confirmação; "você saiu" | P3 diversos |
| 3.11 | Cards-vitrine (ofensiva, tiles de semana) ganham porta ou perdem a moldura | P3 |
| 3.12 | Hidratação sem repetir a origem da meta | CA-19 |

---

## 16. Testes necessários

### 16.1 End-to-end (fase 21) — uma prova por fluxo, no navegador

| Fluxo | Prova | Guarda |
|---|---|---|
| Cadastro → onboarding → primeira Home | conta nova com dia de treino hoje e prioridade Treino: a primeira GET de `/` **não contém** "Hoje não tem treino" e o resumo não diz "descanso"; contém "Treino A" ou "ainda não foi montada" | P1-01 |
| Editar dias para nenhum | Home não menciona séries; ofensiva não cobra treino naquele dia | P1-02 |
| Home → Começar treino | destino é `workouts:ficha`; painel idem; leitura "Fazer este exercício" só se pendente | P1-11 |
| Ficha → exercício → ← | volta à ficha de origem | NOVO-03 |
| Execução completa de um exercício | após a 4.ª série: tela seguinte contém "concluído" e o próximo; reabrir o exercício concluído não contém "None" nem formulário de registro; POST extra recusado ou explícito | P1-06, TR-02 |
| Execução a 375×667 | `bottom` de `.agora__concluir` ≤ topo da tabbar sem rolar | P1-08 |
| Execução offline (CDP `Network.emulateNetworkConditions offline`) | 3 toques → 3 itens com `op_id` distintos; a tela mostra 3 séries "aguardando rede"; drenagem termina em 2, 3, 4 | P1-09 + CLAUDE.md |
| Água: zerar | com o details aberto, `.agua__valor` tem 1 linha a 320 | P1-04 |
| Água: sessão expirada | POST com cookie inválido → login contém "sessão venceu" | E01 |
| Lembretes com permissão negada | após o clique, `[data-push-status]` contém "Permissão negada" 1 s depois | P1-05 |
| Lista de compras a 320/390/430 | nenhum `.shopping__name` com mais de 2 linhas; `.shopping__qty` dentro do `label` | P1-03 |
| Lista: adicionar item | item novo dentro do viewport após o pouso; flash presente | P1-10 |
| Compartilhar treino parcial | canvas/título não contém "concluído" quando `estado.concluido` é falso | P1-12 |
| Login/cadastro anônimos | `[data-install]` ausente; contraste do rodapé ≥ 4,5:1 medido em pixel | P1-13, P1-07 |
| Perfil → Editar → Salvar | sem "Passo N/6"; volta a `#bloco` | PA-02 |
| Hidratação: 4 registros → 1 voltar | `history.length` não cresce com PRG | PA-03 |
| Toque duplo | +250, Concluir série, desfazer, Adicionar: um efeito por par de toques (já passa; congelar) | E17 |
| Vídeo | abrir/fechar não muda URL nem `history.length`; carga/reps preservadas; `iframes.length ≤ 1` | requisito + TR-07 |
| Alvos e rolagem | 0 alvos < 44×44; `scrollWidth − innerWidth = 0`; 0 fontes < 11 px em 14 telas × 4 larguras (já passa; congelar) | CLAUDE.md |

### 16.2 Testes de estrutura por problema (suíte Django)

| Teste | Onde | Problema |
|---|---|---|
| `estado_do_treino` distingue "sem plano com dias cadastrados" de "descanso"; `_area_promovida.html` tem o terceiro ramo | `plans/tests` | P1-01 |
| Salvar zero dias deixa `TrainingPlan.is_active=False` (ou `estado_do_treino` vazio); `streaks._dias_de_treino` devolve vazio | `workouts/tests`, `plans/test_streaks.py` | P1-02 |
| Todo `<a>`/`<button>` com texto "Começar treino" resolve para `workouts:ficha`; "Continuar de onde parou" tem um único destino | `config/test_b6_navegacao.py` | P1-11 |
| `_primeira_serie_livre == None` ⇒ a execução renderiza o ramo concluído e não imprime "None" | `workouts/tests` | P1-06 |
| `set-row--done` (ou a classe que a substituir) existe em `app.css`; `nutriplan:enfileirado` tem consumidor por tela | `push/tests.py` (espírito de `test_design_system`) | P1-09 |
| `render()` de push não sobrescreve `say()` de permissão negada — teste de contrato lendo `pwa.js` | `push/tests.py` | P1-05 |
| Cadastro, login, recuperação, onboarding e 404 renderizam `data-sem-convite` | `accounts/tests`, `config/tests` | P1-13 |
| Contraste de `--text-muted` sobre o pior ponto do gradiente de `.auth--entrada::before` ≥ 4,5 | `config/tests` | P1-07 |
| `plans/compra.py` não repete `Food.name` dentro da quantidade | `plans/tests` | P1-03 |
| Redirect de item avulso emite `messages.success` e âncora no item | `plans/tests` | P1-10 |
| `card.js` título de treino condicionado ao estado (teste lendo o arquivo, como `push/tests.py` faz com sw.js) | `workouts/tests` | P1-12 |
| Leitura do exercício com `?de=ficha` contém `href` da ficha | `workouts/tests` | NOVO-03 |
| Área tocável de `.ficha-item` ≥ 90%; `.agora__nome-link` na lista de 44 px | `config/tests.TouchTargetTests` | CA-03, NOVO-06 |
| `.semana` de treino/água sem `background` no CSS computado | `config/tests` | CA-02 |
| Todo `<a>` com classe de card está nas três listas de `:active` | `config/test_design_system.py` | CA-06 |
| Nenhum `class="btn"` sem variante nos templates | `config/test_design_system.py` | CA-17 |
| Valor inicial de `PesoField` renderiza com vírgula | `accounts/tests` | MC-07 |
| Reps acima do teto é recusado com mensagem, não saturado; valores preservados no re-render | `workouts/tests` | TR-08 |
| Frase de vazio de Conquistas: Áreas e `/conquistas/` idênticas | `config/test_nomenclatura.py` | E05 |
| Selo do hero do painel == selo do card de hoje (`rotulo`) | `config/test_nomenclatura.py` | CA-14 |
| Modo edição não renderiza `wizard__label`/barra | `accounts/tests` | PA-02 |
| Home não renderiza `start_time` de `TrainingSession` | `plans/tests` | CA-13 |
| `field.html` escreve `id="<campo>_error"` no `<ul class=field__errors>` | `config/tests` | PA-06 |
| Texto do programa não contém "abre mais um dia" com 7 dias, nem "ABCD" com A-B-C-A | `workouts/tests` | TR-10 (TRAINING) |
| Demo linkado de login e cadastro; capa com CTA de criar conta | `demo/tests`, `accounts/tests` | MKT-07 |
| Progresso vazio de refeições tem `card__head` | `plans/tests` | PA-04 |

### 16.3 O que esta auditoria NÃO provou

Sem rede real (só `navigator.onLine` forçado e eventos disparados à mão); Safari/iPhone; teclado virtual reduzindo o viewport; tema escuro; haptics/`:active` com toque físico; OAuth Google; e-mail de recuperação real; push com permissão concedida; GPS real; folha nativa de compartilhamento; produção além de GETs; regras de prescrição (TRAINING); paleta/tipografia (DESIGN).

---

## Decisões para o dono

Tudo acima que é clique, navegação, voltar, acessibilidade, consistência ou comportamento incorreto **não** é decisão — entra nas ondas. O que altera materialmente o produto está aqui, com alternativas e custo.

### D1 · Encurtar o onboarding para três telas antes do primeiro cardápio
- **Hoje:** cadastro + 6 passos (5 sem ≥ 3 dias), 15 perguntas, ~22 toques, 3–4 min; primeira Home contradiz o treino.
- **A — Manter 6 passos e só corrigir** (P1-01, passo 6 compacto, prévia no passo 4, stepper honesto). Custo: baixo (templates/forms). Mantém sete perguntas antes de terem consequência.
- **B — Três telas + personalização progressiva** (seção 12): cadastro, dados, "seu plano" (objetivo, rotina, dias, restrições); experiência/divisão no painel, sono/estilo no cardápio, prioridade na Home a partir do 2.º dia. Custo: médio (views do wizard, `passos_de`, três cartões novos com `?origem=`, migração de `onboarding_step`, testes de `test_nomenclatura`/onboarding). Ganha: 9 perguntas, 3 telas, cada pergunta adiada feita com a consequência à vista. Risco: quem nunca abre o painel fica com teto 20 e divisão padrão — que já é o comportamento de quem não responde hoje.
- **C — Duas telas** (fundir dados + plano). Custo: como B; tela 2 fica longa a 320.
- Recomendação do auditor: **B**. Preserva as decisões do CLAUDE.md (prioridade própria, uso não é intenção, escolhas em branco).

### D2 · Quem monta a ficha de treino, e quando
- **Hoje:** só `/treino/` (`sync_active_routine`), por decisão de `plans/views.py` (tela de comida não cria ficha). O Concluir do onboarding e o Salvar dos dias também não montam. Consequência: P1-01 e P1-02.
- **A — Montar no Concluir e ao salvar dias** (e desativar com zero dias). Custo: baixo; a tela de montagem já diz que faz isso. Mantém a Home sem criar nada. **CROSS-WORKFLOW: TRAINING** decide o ponto de chamada.
- **B — Só copy** ("sua ficha ainda vai ser montada — abrir"). Custo: mínimo. Continua mostrando um estado intermediário que não precisava existir.
- Recomendação: **A + o terceiro ramo de B** (o ramo protege contra plano nulo por qualquer outro motivo).

### D3 · Nome no cadastro
- **Hoje:** obrigatório, primeiro campo, usado só no e-mail de senha.
- **A — Opcional.** Custo: trivial. **B — Remover e perguntar no Perfil.** Custo: trivial + copy. **C — Manter e USAR** (cumprimentar na Home, no cartão de resultado). Custo: baixo; dá consequência ao que já se pede.
- Recomendação: **C ou A**; nunca obrigatório sem consumidor.

### D4 · "Continuar de onde parou" da Home: ficha ou execução?
- O requisito fechado cobre "Começar treino → ficha". "Continuar" (já há série hoje) cair no próximo pendente é defensável e é o que a ficha faz.
- **A — Tudo → ficha** (um destino, uma etapa a mais para quem está no meio do treino). **B — Começar → ficha; Continuar → execução; rótulos distintos em cada tela** (seção 11). Custo igual (um `reverse` e três rótulos).
- Recomendação: **B**, com "Continuar de onde parou" reservado ao que retoma de fato.

### D5 · Momento do convite de instalação e do pedido de push
- **Hoje:** convite na primeira tela anônima; push por botão na Home.
- **A — Após o onboarding.** **B — Após a primeira ação de valor** (primeira refeição marcada ou série concluída), com contexto. Custo: A trivial (`data-sem-convite`); B baixo (um sinal de "primeira ação" já existe em ofensiva/conquistas).
- Recomendação: **B**.

### D6 · Mídia de "Músculos trabalhados"
- **Hoje:** segundo iframe do YouTube, de terceiro, com banner de personal trainer concorrente. A memória do projeto fechou "anatomia = vídeo real com start; não reabrir o 3D".
- **A — Manter o vídeo, um player por vez, curadoria sem banner** (CROSS-WORKFLOW: TRAINING na curadoria: exige assistir). **B — Trocar por texto/lista de músculos** (o dado `secondary_muscles` já existe) e deixar só o vídeo de execução. Custo: A alto (curadoria manual de mídia por exercício); B baixo.
- Recomendação: **B agora, A quando houver curadoria** — o app não deve exibir propaganda de terceiro na tela de execução enquanto isso.

### D7 · Demo como "ver antes de se comprometer"
- **Hoje:** demo completo, não linkado; capa sem entrada/cadastro por decisão.
- **A — Linkar de login/cadastro e pôr CTA na capa.** Custo: trivial. Risco: `demo/views.py` tirou as saídas da BARRA por saída acidental; a capa é decisão intencional. **B — Deixar como está** (portfólio).
- Recomendação: **A**.

### D8 · Compartilhar treino parcial
- **A — Só ao concluir.** **B — Sempre, com título honesto** ("Treino em andamento · 4 de 16"). Custo igual. Recomendação: **B** (quem quer mostrar "o que já fiz" pode; a peça nunca mente).
