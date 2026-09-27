# QA exploratório — 27/09/2026

Só medição. Nenhum código e nenhum PR. Produção estava em `9fc406d` (`/saude/`).

## Método e limite

- **Produção, anônima.** Passei por landing, `/demo/` (capa, hoje, alimentação, treino, progresso, corridas, conquistas, áreas), `/ajuda/`, `/ajuda/o-que-mudou/`, cadastro e entrar. Tudo por GET, nos dois recortes. No demo não fiz nenhum POST, então ele ficou intacto.
- **Personas logadas, local.** A regra de segurança desta sessão proíbe criar conta e digitar senha fora de localhost, e o dono escolheu o formato híbrido. As três personas rodaram num worktree detached **no mesmo commit de produção** (`9fc406d`), com banco novo (`nutriplan_qa_explor`, semeado pelo mesmo `build.sh`) e servidor em `127.0.0.1:8291`. Os caminhos foram os de verdade: signup público, as três etapas, e exclusão pela tela com login recusado nas três contas (`restam: 0`). O que é do Render (latência, cold start) só foi medido na parte anônima.
- **Recortes.** Cada tela foi medida a 390×844 no escuro e a 1280×900 no claro. As réguas rodaram no DOM: rolagem horizontal, alvo menor que 44 px, texto menor que 11 px, texto cortado, "opção A/B", palavras punitivas, jargão, `errors`/`console` do agent-browser e tempo de navegação. 146 medições estão em `capturas-qa-exploratorio-20260927/medidas.jsonl` e há 169 capturas.
- **"Nenhum GET grava".** Comparei os contadores de `pg_stat_user_tables` antes e depois de cada varredura só de GET e conferi no código o que mudou. Os eventos de analytics chegam por `POST /analytics/e/` (conferido no log do servidor), então não contam.
- **Personas.** p1 = academia completa, intermediário, ABC em 4 dias, com hoje (domingo) como dia de treino. p2 = só peso do corpo, iniciante, seg/qua/sex, com hoje como descanso. p3 = não faz musculação, só corrida.

## Confirmações pedidas

| Pergunta | Resultado | Captura |
|---|---|---|
| Herói e cartão da letra com o mesmo número | **Sim.** A: 7 ex · 25 séries · ~59 min no herói e no cartão. B, depois da troca: 9 · 24 · 57 nos dois. p2 A: a ficha diz 5 · 15 · ~42 e o cartão também | `p1-treino-390-dark.png`, `p1-treino-B-hoje-390-dark.png`, `p2-ficha-A-outro-dia-390-dark.png` |
| Nenhum GET grava | **Não.** `GET /avisos/` insere `avisos_preferencia` (`Preferencia.de` → `get_or_create`, `avisos/models.py:50`). Reproduzido nas três personas. Execução, ficha, Home e Progresso por GET: zero escrita | `medidas.jsonl` (diff de stats) |
| Sem "opção A/B" em texto | **Sim nas telas.** A expressão só aparece em `/ajuda/o-que-mudou/`, como citação do texto antigo ("'Opção A' e 'Opção B' viraram…") | `prod-ajuda-mudou-390-dark.png` |
| Sem nota de gerência em `/ajuda/o-que-mudou/` | **Sim.** Nenhum PR, commit, arquivo, "dono" ou "medido" no `<main>` | `prod-ajuda-mudou-1280-light.png` |
| JS vivo depois de trocar de série | **Sim.** A troca de série acontece sem recarga (a marca em `window` sobreviveu), e o cronômetro contou de 1:18 a "pode ir". "+2,5" mudou a carga (40 → 42,5 e 42,50 → 45). Zero `<script>` sem nonce no `<main>` e zero erro JS | `p1-serie-concluida-s1-390-dark.png`, `p1-descanso-fim-390-dark.png` |
| Primeira carga (Render hiberna) | **Não medido a frio.** O UptimeRobot mantém o serviço acordado: a primeira abertura da landing levou 1,73 s de parede. Nas telas do demo, o evento `load` ficou entre 300 e 1 070 ms (a maior foi `/demo/alimentacao/`, 1 067 ms a 390) | `medidas.jsonl` |

## Ficou bom

1. Nenhuma rolagem horizontal, nenhum texto abaixo de 11 px e nenhum erro JS ou de console, em nenhuma das 146 medições (todas as rotas, as 3 personas, 390 escuro e 1280 claro).
2. Onboarding completo nas três personas: "Calcular minha estimativa" leva à Home em 1,3–1,4 s (local, as 3). Captura `p1-onb3-preenchida-390-dark.png`.
3. Execução: "Concluir série" sem recarga, cronômetro de descanso até "pode ir", alvos de +30 s, pular e som com 44×44 (p1, 390). Captura `p1-descanso-fim-390-dark.png`.
4. "Fazer outro treino" com série já feita pede confirmação e diz que as séries continuam registradas. Herói e cartão de B batem, e o volume de 495 kg confere (40×6 + 42,5×6) (p1, `/treino/`, 390). Captura `p1-treino-B-hoje-390-dark.png`.
5. "Comi outra coisa": o datalist tem 62 alimentos, 150 g de arroz dão 192 kcal, e o nome fora do catálogo **avisa** ("Não encontramos 'frango'…"). Registrar e Não comi também funcionaram. O kcal bate entre Alimentação e Home (449) (p1, `/alimentacao/`, 390). Captura `p1-alimentacao-apos-3-acoes-390-dark.png`.
6. Água: 750 ml iguais na Home, em Hidratação e no Progresso (p2, 390). Captura `p2-home-agua-750-390-dark.png`.
7. Corrida à mão gravou 5,2 km em 28:30 e 5:29 min/km, e aparece na Home e no Progresso (p3, 390). Captura `p3-corridas-pos-390-dark.png`.
8. Exclusão pela tela e login recusado nas 3 contas. Captura `p1/01-login-recusado.png` e as equivalentes de p2 e p3.

## Ficou ruim

| # | Rota | Persona | Viewport | Gravidade | O que acontece | Captura |
|---|---|---|---|---|---|---|
| R1 | `/historico/` | p1 | 390 e 1280 | **média** | O cartão CARDÁPIO diz "— · Marque uma refeição para a aderência começar", mas havia 3 marcadas hoje (registrada, pulada, outra coisa). A Home, na mesma hora, diz "1/5 refeições · 1 fora". São duas telas com números diferentes | `p1-progresso-pos-390-dark.png`, `p1-home-pos-390-dark.png` |
| R2 | `/` (ofensiva) | p1, p2 | 390 e 1280 | **média** | Depois de registrar uma refeição (p1) ou 750 ml de água (p2), a ofensiva continua dizendo "0 dias · Comece hoje: registre uma refeição ou um copo d'água". O convite é para fazer o que a pessoa acabou de fazer | `p1-home-pos-390-dark.png`, `p2-home-agua-750-390-dark.png` |
| R3 | `/` (cartão Treino) | p3 | 390 e 1280 | **média** | Quem respondeu "não faço musculação" vê "Sem ficha · A sua ficha ainda não foi montada · **Montar treino**". Enquanto isso, `/treino/` diz "Você disse que não faz musculação" | `p3-home-pos-1280-light.png`, `p3-treino-390-dark.png` |
| R4 | `/treino/`, `/treino/agora/` | p2 | 390 | **média** | Em dia de descanso não há "Fazer outro treino" nem "treinar mesmo assim". A execução responde "Hoje não tem treino na sua rotina" e a ficha de outro dia não executa. Quem quer treinar no domingo não consegue | `p2-treino-descanso-390-dark.png`, `p2-agora-dia-descanso-390-dark.png` |
| R5 | `/conquistas/` | p3 | 390 | baixa | Quem só corre lê "A primeira chega quando você registrar a primeira série de um treino · VER O TREINO". Nenhuma conquista existe para corrida | `p3-conquistas-pos-390-dark.png` |
| R6 | `/avisos/` | p1–p3 | — | baixa | O GET grava a linha de preferência (ver a tabela de confirmações). O efeito é inofensivo, mas quebra a regra "GET não grava" | `avisos/models.py:50` |
| R7 | `/treino/` | p1 | 390 e 1280 | baixa | O `summary` "Fazer outro treino" tem 25 px de altura (289×25 a 390, 938×25 a 1280), abaixo da régua de 44 px | `p1-treino-outro-treino-390-dark.png` |
| R8 | `/treino/ficha/<id>/` | p2 | 390 | baixa | O subtítulo diz "Empurrar — peitoral, **sinergista** e deltoide". "Sinergista" é jargão, e está na primeira tela de quem é iniciante | `p2-ficha-A-outro-dia-390-dark.png` |

## Dá pra melhorar

| # | Rota | Persona | Viewport | Gravidade | Observação | Captura |
|---|---|---|---|---|---|---|
| M1 | `/treino/agora/`, `/historico/` | p1 | 390 | baixa | A carga aparece em três formas: "40×6", "42,50×6" e o campo "42,5". O Progresso também escreve "42,50 kg" | `p1-descanso-fim-390-dark.png`, `p1-progresso-pos-390-dark.png` |
| M2 | `/treino/corridas/` × `/` | p3 | 390 | baixa | A mesma corrida aparece como "5,20 km" na lista e "5,2 km" na Home | `p3-corridas-pos-390-dark.png`, `p3-home-pos-390-dark.png` |
| M3 | `/` × `/treino/` | p1 | 390 | baixa | Depois de 2 séries de A e da troca para B, a Home mostra "TREINO 0/24 séries · Começar" e não menciona o que já foi feito hoje. O Treino mostra "495 kg de volume". Além disso, o herói de A dizia "14 % do treino", contado por exercício (1/7), enquanto a execução dizia "2/25 séries" | `p1-home-pos-390-dark.png`, `p1-treino-B-hoje-390-dark.png` |
| M4 | `/treino/` (tira e cartões) | p1 | 390 | baixa | Depois da troca, o cartão A continua dizendo "Segunda-feira · Domingo" e B diz "Quarta-feira · HOJE", num domingo | `p1-treino-B-hoje-390-dark.png` |
| M5 | `/treino/ficha/<id>/` | p2 | 390 | baixa | Exercício sem vídeo ganha um quadrado com o mesmo número do canto ("1 · 1", "4 · 4"), o que parece placeholder. O título "Pernas completo" também é estranho | `p2-ficha-A-outro-dia-390-dark.png`, `p2-treino-descanso-390-dark.png` |
| M6 | `/historico/` | p1, p2, p3 | 390 | baixa | No primeiro dia, a água aparece com a seta "750 ml ↓", uma tendência sem dado anterior. A legenda da corrida é "sem registro · dia cheio", copiada da alimentação. E "O que mais você registrou" sai como lista com marcador | `p1-progresso-pos-390-dark.png`, `p3-progresso-pos-390-dark.png` |
| M7 | `/conta/onboarding/3/` | p1 | 390 | baixa | "Divisão · 2 grupos por dia" encosta em "Que tipo de cardápio você quer?" sem respiro. O cartão "Não quero priorizar agora" tem a caixa do ícone vazia | `p1-onb3-preenchida-390-dark.png` |
| M8 | `/alimentacao/` | p1 | 390 | baixa | A conta nasceu às 07:4x, então o café das 07:30 fica fora e nada abre como "agora". A tela inteira fica fechada, e o café aparece como uma refeição futura, sem marca de "antes do cadastro" | `p1-alimentacao-390-dark.png` |

Descartados como artefato de medição:

- inputs "alimento" de 34×52 dentro de `<details>` fechado (aberto, o campo mede 185×52);
- a barra de abas no meio das capturas `--full`;
- os `vis-oculto` que a régua de texto cortado pegava.
