# O que o Claude Design propôs e não entrou

A spec ganha. Este arquivo é o registro token a token — e, como o Claude
Design leu o `DESIGN.md` e o `app.css` e devolveu os tokens IGUAIS, ele é
também o registro do que ele propôs **fora** dos tokens: copy, estados,
componentes novos. Nada disso entra por conta própria; o que é melhor que o
app de hoje vai para "Recomendo rever", que é decisão do dono.

Fontes: `artifacts/claude-design/export/` (fora do git) — o design system
(`design-system/`, 166 arquivos, gerado em 16/09/2026 a partir da semente de
`scripts/montar_semente.py`) e o projeto das seis telas (`telas/`). Inventário
em [`inventario-export.md`](inventario-export.md); comparação de tokens por
`scripts/tokens_do_export.py`.

## Tokens — 32 de 32 iguais

`scripts/tokens_do_export.py artifacts/claude-design/export/design-system`,
16/09/2026 18:33: 64 tokens lidos em 70 arquivos; dos 32 tokens de cor da
direção C (Mesa), **32 iguais, 0 diferentes, 0 ausentes, 0 novos**. Os
`--ferro-*` (32) vieram idênticos e ficam fora da comparação por construção.
Nenhum hex fora da paleta nos seis mockups, nenhuma `font-family`, nenhum
`border-radius` cru, nenhum emoji; a Execução nasce com `body.modo-foco`.

| token | proposto pelo Claude Design | spec (direção C) | motivo |
|---|---|---|---|
| — | — | — | nenhuma diferença: o export escreveu os tokens do `app.css` e do `DESIGN.md` como estão |

## Fora dos tokens — proposto e NÃO adotado

| onde | proposta | motivo |
|---|---|---|
| design system | componentes React (`components/*.jsx`, `_ds_bundle.js`) sobre as classes reais do app | o app é Django + templates, sem build; `.jsx` é referência de leitura, não código a importar (`inventario-export.md` classifica como `referencia`) |
| design system | `Icone`, invólucro do `<use href="#icone-…">` | o template usa `<use>` direto e o `stroke-width` já mora em cada `<symbol>` (`config/test_sprite.py`); um invólucro é a quarta versão do mesmo botão |
| design system | `.modo-mesa`, par explícito de `.modo-foco` para forçar Mesa dentro de uma página escura | só existe para especimens lado a lado; no app o regime é do `<body>`, escrito pelo servidor |
| Hoje | cores dos macros por atributo `[data-macro="proteina|carboidrato|gordura"]` com tokens de escopo | o app pinta por classe (`--brand`, `--carb`, `--fat`); atributo para estilo é o caminho que o `CLAUDE.md` evita (`data-*` é gancho de JS, teste ancora em classe) |
| Treino, Entrada | "Estado da tela" — chips de andaime acima do telefone para alternar os estados (dia sem treino, semana completa, erro no campo, sessão vencida) | andaime do mockup, não cromo do app; os estados reais vêm do servidor |
| mockups | React 18 + Babel standalone de `unpkg.com` para compilar JSX no navegador | o app não carrega script de terceiros; os mockups só rodam assim para o preview |
| Ficha | "Complementares desta sessão — **opcionais**. Entram quando sobrar tempo. Não contam para as 20 séries da sessão." | **contradiz a doutrina**: complementar é prescrito e conta no volume (`TREINO.md`; `CLAUDE.md` "o modelo declara os grupos que o NOME promete, e o resto é COMPLEMENTAR"). A ficha real diz "Complementares desta sessão" sem "opcionais" |
| Execução | "Sugestão: manter 14 kg" como linha solta | a adaptação da carga é `Progressao(estado, valor, razao)` e já preenche o campo — frase == campo (`workouts/adaptacao.py`); uma segunda frase de sugestão seria dois idiomas para o mesmo número |

## Recomendo rever (proposta melhor que o app de hoje — decisão do dono)

| onde | proposta do Claude Design | o que o app faz hoje | por que vale olhar |
|---|---|---|---|
| Hoje, resumo do dia | uma frase de RITMO ao lado do anel: "No ritmo do déficit planejado para hoje." | "faltam 735 kcal · 3/5 refeições" | transforma número em veredito; é copy de produto (o app não faz promessa — a frase precisa ser verdadeira por cálculo, não por tom) |
| Hoje, refeição vencida | "Passou das 18:00. Registrar agora ainda entra no dia de hoje." + botão "Ver as duas opções" | estado "vencida" sem a frase | diz a consequência (ainda conta) em vez do mecanismo |
| Hoje, A/B | nota: "A e B fecham a mesma caloria. O que muda são os macros — se a proteína é o que importa hoje, o número está no card de cada opção." | as duas opções sem a explicação | explica por que existem duas; copy curta |
| Hoje, rodapé | cartão "Aderência de hoje — 20% do dia — 3/5 refeições · 0% água · treino aberto", com a regra escrita ("conta refeição registrada, meta de água e treino cumprido") | aderência mora no Progresso e na ofensiva | uma leitura do dia inteiro na própria Home; precisa da mesma régua da ofensiva (`plans/test_streaks.py`) para não virar segundo número |
| Treino, painel | tile "último: 6 dias atrás" ao lado de "~44 min" e "19:00"; "~165 min por semana" no programa | painel mostra sessão, duração e horário | "há quanto tempo" é o fato que falta ao painel; custa uma consulta (`ExerciseLog` da sessão) |
| Execução | "Recorde: 16 kg" ao lado da carga da última vez; "DEPOIS → Rosca martelo" (o próximo exercício) | carga da última vez; sem recorde, sem próximo | recorde é motivação com dado real (`ExerciseLog` max); "depois" tira a dúvida de "o que vem" sem sair da tela — cabe na onda 6 (T4.x) |
| Execução | "última vez: 14×12" sob cada pílula de série | as pílulas só numeram | histórico por série, não por exercício; depende de `load_history` já trazer por série (traz) |
| Progresso | tiles de semana: "78% aderência · 5 de 7 dias", "2 080 kcal/dia · meta 2 100", "2,4 L água/dia · meta 3,0 L", "3/4 treinos · A, B e C", com a régua escrita embaixo | tiles existentes com outra composição | quatro números, cada um com meta ao lado — mesma métrica, mais legível; a régua escrita ("aderência conta…") é o que o `CLAUDE.md` pede de todo número |
| Progresso, peso | lista por SEMANA ("semana de 14/09 · 1 pesagem · −0,1") em vez de por registro | registros individuais | agrupa ruído diário em tendência; precisa decidir a semana de referência (segunda) |
| Progresso, conquistas | cartão por conquista com ícone do sprite e PROGRESSO ("5/7 · faltam 2 dias"; "2/5 dias na meta"), "Duas desbloqueadas de nove" | conquista feita/não feita, com emoji | progresso parcial é o que faz conquista virar meta; os glifos novos (troféu, medalha) não existem no sprite — T3.6 |
| Entrada | benefício em uma linha: "Refeições, treino e água do dia em uma tela — e o histórico que mostra se está pegando."; ajudas de campo: "O mesmo e-mail que você usou no cadastro." / "Mínimo de 8 caracteres. O olho mostra o que você digitou." | "Bom te ver de volta." sem benefício; campos sem ajuda | copy; a ajuda da senha nomeia o olho, que hoje é ícone mudo |
| design system, tipografia | QUATRO pesos (400 corpo · 500 rótulo · 600 título · 700 número) no lugar dos onze do CSS (500…800, com 620/650/680/720/750/780) | 11 pesos distintos (era 12 até 16/09) | é a régua da T3.2, e só faz sentido junto com a decisão da fonte (sem `@font-face`, `system-ui` não tem os degraus intermediários de verdade) |
| design system, Áreas | tela Áreas recriada pela descrição, com aviso | `/areas/` real | não estava nas seis telas; se a Áreas entrar na próxima rodada, mandar a captura (`artifacts/claude-design/seed/capturas/areas-*.png` já existe) |

## Para o dono decidir

As linhas de "Recomendo rever" que mudam decisão FECHADA do repositório:

1. **Aderência na Home** — o `CLAUDE.md` decidiu que a Home organiza pela
   área principal e o AGORA vem primeiro; um cartão de aderência do dia é
   seção nova, e a régua tem de ser a da ofensiva.
2. **Recorde e "depois" na execução** — a execução mostra UM exercício por
   decisão ("Nada que se use DURANTE a série mora na ficha"); "depois" é um
   nome, não um segundo exercício, mas é a fronteira que aquela decisão
   guarda.
3. **Quatro pesos** — depende da fonte (T3.2), que é decisão do dono com
   download e gate de tamanho.
4. **Conquistas com progresso** — muda `achievements` (regra e tela), fora
   da campanha de design.

O resto é copy e composição: entra tela a tela, com teste do texto visível.
