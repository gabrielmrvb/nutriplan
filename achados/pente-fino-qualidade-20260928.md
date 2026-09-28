# Pente-fino de qualidade — 28/09/2026

Sete frentes, ordem do dono: 3 → 1 → 5 → 6 → 2 → 7. O #162 não estava em `main` no início, então as ondas 1 e 3 esperam e a missão começou pela 5. Harness: o da auditoria visual (`notas.py` + `comparar.py`), servidor local 8218, banco `nutriplan_qualidade`, três personas pelo cadastro público (academia dia 12 em descanso, corredora dia 1, casa dia 1 em dia de treino), 390 escuro/claro e 1280.

## Onda 5 — estados

1. **Medido antes** [OBSERVADA], em 159 capturas: a corredora via "Treino · Sem ficha · Montar treino" na Home, "0 dias de treino · 0 recordes" nas Conquistas, com o vazio mandando para "Ver o treino" e só metas de treino em "Próximas", e no Progresso o tile e a seção de treino com "Abrir o treino de hoje".
2. **Dia 1, Hidratação:** "Últimos 7 dias" listava 22/09 a 27/09, antes de a conta existir, e cobrava "0/7". Agora a janela começa na conta, e no dia 1 o bloco não aparece.
3. **Dia 1, Progresso:** "Treinos 0 de 1 ↓" às 14h, para um treino que ainda podia acontecer. Agora hoje só conta quando já tem série, e o tile diz "Hoje é dia de treino."
4. **#138 (decisão do dono):** a Home de quem não faz musculação traz Alimentação e Corrida, sem cartão de treino. O Progresso troca o treino pela corrida. As Conquistas de quem não faz musculação mostram só metas de corrida e de alimentação. As regras novas (primeira corrida, 5/10/25 corridas, primeira refeição, 7/30 dias registrando) valem para todos; as de corrida aparecem só para quem corre. Registrado no `CLAUDE.md`.
5. **Custo:** "tem ficha?", corridas e dias com refeição saem numa consulta só. Progresso e Conquistas continuam no mesmo número de consultas (`plans.test_stress` verde).
6. **Provas:** 4 arquivos de teste novos, vermelhos antes. Sabotagem 7/7 vermelha. `plans` + `achievements`: 1.077 testes OK. Na revisão adversarial por subagente, nenhum achado.
7. **Notas Ti/Es/Cc:** remedidas nas mesmas cenas; nenhuma caiu (0 pioras). Os critérios observados sobem em Ev (estado vazio) na Home, nas Conquistas e no Progresso da corredora e na Hidratação do dia 1.
8. **Ficou de fora, com dono:** `/treino/` da corredora (hoje só texto e um link; o botão de ativar a musculação deveria ser o principal) e "Exercícios que já fiz" para quem não faz musculação. As duas telas estão em `templates/workouts/`, com a sessão da Parte 2 no ledger. Voltam no fim.
9. **Dia de descanso** (academia, dia 12): Home ("Descanso · Próximo: amanhã, A") e painel do Treino já davam o próximo passo. Nada a mudar.
10. **Em produção** (7a22a12, [OBSERVADA]): uma conta descartável criada pelo cadastro público como corredora. A Home não tem "Montar treino" e tem "Registrar corrida". As Conquistas mostram corrida e alimentação. O Progresso traz "Registrar a primeira corrida". A Hidratação do dia 1 não tem a semana. A conta foi apagada pela tela e o login dela foi recusado depois.

## Onda 6 — voz

1. **Inventário:** partiu do da auditoria visual (277 linhas de botões e títulos) e foi completado varrendo o texto literal de todos os templates (fora os de gestão) atrás de punição, linguagem de contrato, jargão de software e siglas soltas.
2. **Guia:** `docs/VOZ.md`, uma página com tom, pessoa (sempre "você"), proibidos com a alternativa, exceções declaradas (legal, `demo/sobre`, gestão, "falha" no treino) e a referência à régua de "plano"/"dieta" que já existia.
3. **Régua:** `config/test_voz.py` lê o texto literal, inclusive o de dentro de `{% translate %}`. Tem controle positivo por categoria, e a sabotagem ficou 2/2 vermelha.
4. **Achado principal:** a FAQ da ofensiva ainda dizia "o app diz o que faltou" e "dois de três". A frase tinha saído da Home em 24/09, e a regra real é "treino e mais uma" no dia de treino. A FAQ foi reescrita a partir do código (`Dia.completo`).
5. **"Combinado"** (palavra de contrato, achado 7b de 24/09): saiu da legenda e dos títulos do mapa do Progresso e do "?" da área de treino.
6. **"Usuário fictício":** virou "pessoa fictícia" na landing e no demo.
7. **O que ficou, de propósito:** as siglas TDEE e TMB só aparecem entre parênteses depois do termo em português, em "Dados do cálculo". "Déficit" e "superávit" continuam, porque são português corrente.
8. **Provas:** régua mais i18n, linguagem, ajuda, demo, evolução e landing: 132 testes OK.
9. **Notas:** a mudança é só de texto, com o mesmo comprimento ± 1 linha. Nenhuma tela mudou de estrutura.
10. **Não coberto:** texto calculado no servidor (frases em Python). A régua lê templates. As frases de `plans/evolucao.py` foram corrigidas à mão, e as outras ficam para uma régua de mensagens se o padrão voltar.

## Onda 2 — laço principal (resíduo)

1. **Dica quebrando letra a letra** (caça-bugs BA9), reproduzida a 390 no exercício de peso do corpo sem vídeo: a dica ficava com 49 px, uma sílaba por linha.
2. **Causa:** o aviso "Sem demonstração cadastrada" não tinha largura fixa na linha flex do `.demo`.
3. **Conserto só de CSS:** `.demo` quebra a linha, o aviso ocupa a linha inteira e a dica desce. Os templates de `workouts/` ficaram intocados, porque a Parte 2 os segura no ledger.
4. **Provas:** `config/test_dica_sem_video.py`, vermelho antes. Réguas de design verdes. Captura depois: a frase aparece inteira e o bloco ficou mais baixo. Notas da execução sem queda.
5. **O resto da onda 2 ficou bloqueado:** Treino no dia de treino (2,05), Ficha (2,29) e execução estão abaixo de 2,5 pelo legado de CSS e pelo markup de `templates/workouts/`, que a sessão da Parte 2 segura hoje. Volta quando ela liberar.

## Ondas 1 e 3 — esperando o #162

6. O #162 ("Missão B — quem entra não desiste") segue aberto, com o check verde e fora da fila. Pela regra do dono, onboarding (1) e bloqueantes (3) esperam por ele. Deixei no ledger o aviso da sobreposição com as Conquistas da onda 5.

## Incidente no caminho — E2E da promoção

7. O lote do #196 reprovou em "cadastro: não consegui marcar input[name=termos]" e parou produção para todo mundo. O snapshot estava em `/termos/`: o `check` clicava no centro do cartão de consentimento e caía no link "Termos", o que vinha desde o lote 5 do sistema visual.
8. O conserto (#198) faz o `marcar` pelo `e.click()` no próprio input. Deu 14/14 no staging, e a promoção provou produção em 7a22a12.

## Onda 7 — alimentação (parada para a escolha do dono)

9. Três direções no canvas "Alimentação: três direções", com a tela atual ao lado (390 escuro e 1280 claro): **A · o diário** (a conta meta − comido = falta primeiro, refeições em linhas com registro de um toque), **B · a refeição da vez** (a refeição do momento é o herói, com as duas receitas lado a lado e "Comi esta"; o dia vira uma linha do tempo) e **C · o que falta fechar** (quanto falta de caloria e de proteína primeiro, e o almoço diz quanta proteína cada receita fecha). Os números vêm da persona real. Nenhum código foi escrito.

## Mapa de calor remedido

A função de nota é a da auditoria: Ti, Es e Cc medidos nas capturas finais, e os critérios observados vêm da auditoria. Ajustes observados nesta missão, só em Ev: corredora na Home 1→2, nas Conquistas 1→3 (e Vo 1→3) e no Progresso 2→3; casa no Progresso 2→3. "Histórico" some 0,09 contra a coluna do lote 6 só porque a amostra é outra: aqui são três personas e lá era uma. Na mesma amostra, antes e depois ficam em 2,48. As telas de execução não entraram na amostra deste harness.

| tela | auditoria (27/09) | sistema visual (28/09) | pente-fino (28/09) | cenas |
|---|---|---|---|---|
| Landing | 1.95 | 2.52 | **2.52** | 3 |
| Cadastro | 2.57 | 2.86 | **2.86** | 3 |
| Entrar | 2.57 | 2.86 | **2.86** | 3 |
| Onboarding 1 | 2.00 | 2.52 | **2.52** | 9 |
| Onboarding 2 | 1.27 | 2.08 | **2.08** | 9 |
| Onboarding 3 | 1.43 | 2.14 | **2.14** | 9 |
| Home | 1.83 | 2.17 | **2.22** | 9 |
| Treino · dia de treino | 1.42 | 2.05 | **2.05** | 3 |
| Treino · descanso | 2.12 | 2.38 | **2.38** | 3 |
| Treino · sem musculação | 2.04 | 2.25 | **2.25** | 3 |
| Ficha | 2.26 | 2.29 | **2.29** | 6 |
| Alimentação · fechada | 1.93 | 2.39 | **2.39** | 9 |
| Alimentação · refeição aberta | 1.83 | 2.29 | **2.29** | 3 |
| Alimentação · comi outra coisa | 1.72 | 2.12 | **2.12** | 3 |
| Corrida | 2.13 | 2.25 | **2.25** | 9 |
| Progresso | 1.87 | 2.09 | **2.17** | 9 |
| Conquistas | 1.83 | 2.30 | **2.48** | 9 |
| Histórico (exercícios que já fiz) | 2.36 | 2.57 | **2.48** | 9 |
| Conta · Mais | 3.00 | 3.00 | **3.00** | 9 |
| Conta · Perfil | 1.71 | 2.00 | **2.00** | 9 |
| Ajuda | 1.60 | 2.33 | **2.33** | 6 |
| /demo/ | 1.67 | 2.29 | **2.29** | 3 |

**O que preciso de você:** escolher uma das três direções da Alimentação (ou pedir uma mistura). Fora isso, nada.

**Decidi sozinho** (por quê · como reverter):
- A ofensiva sai do "a caminho" de quem não faz musculação. Por quê: `_ofensiva` exige um dia treinado e nunca fecharia para essa pessoa. Como reverter: tirar `Familia.OFENSIVA` de `FAMILIAS_DE_MUSCULACAO`.
- "Comi outra coisa" conta para as conquistas de refeição. Por quê: pela doutrina da ofensiva, registrar honesto não pode custar. Como reverter: tirar `OFF_PLAN` do filtro em `achievements/services.reunir`.
- A corrida entra na Home de quem não faz musculação mesmo sem ter sido declarada. Por quê: sem ficha, é o movimento que o app tem a oferecer. Como reverter: filtrar `CARTOES_SEM_MUSCULACAO` por `declarados`.
- A onda 2 foi só CSS, para não tocar `templates/workouts/`. Como reverter: `git revert` do commit da dica.
