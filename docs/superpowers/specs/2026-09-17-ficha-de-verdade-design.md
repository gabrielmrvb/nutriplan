# A sessão entregue como ficha de academia de verdade — design (17/09/2026)

**Objetivo (verificável):** intermediário, 5 dias, `abc2`, duração Padrão →
a letra A tem ≥ 6 exercícios (≥ 4 peito, ≥ 2 tríceps), 21–28 séries diretas
e 55–65 minutos nas DUAS opções; com Completo, 60–80 minutos. Hoje: 4
exercícios, 13 séries, ~36 minutos.

**Caminho:** arquitetural (toca motor, catálogo, doutrina, hook, planos
ativos e deploy). O dono está em viagem e mandou decidir por padrão e trazer
só vetos; as decisões abaixo são as escolhidas, cada uma com a razão.

## Fase 0 — main vermelho

**Medido (17/09):** `plans.test_stress` não tem N+1. Perfilado por sítio de
chamada em sete dias da semana com a data congelada: a Home faz 36 consultas
em dia de descanso e 41 em dia de treino (`estado_do_treino`: sessão + dois
prefetches, escolha do dia, opção recomendada, histórico, séries de hoje —
uma de cada); o painel faz 21 em descanso, 23 em treino e 27 quando há série
registrada hoje (`resumo_da_sessao` refaz a sessão, a escolha e o descanso
que o painel já tinha). O orçamento (40/25) foi medido numa terça — dia de
descanso do fixture seg/qua/sex — e o pre-push de 15/09 (terça) passou por
isso: o teste dependia do calendário.

**Decisões:**
- `resumo_da_sessao(user, dia=None, sessao=None, escolha=None)` recebe a
  sessão e a escolha que o painel já carregou e lê o descanso do prefetch —
  três consultas a menos no pior dia (27 → 24);
- o teste congela a data no PIOR estado (dia de treino com série registrada)
  e mede lá; o orçamento da Home sobe para 41 com a lista das seis consultas
  únicas escrita no teste;
- o hook de pre-push passa a rodar a suíte num `git worktree` do SHA que
  está subindo, e não na árvore de trabalho — é o incidente registrado no
  CLAUDE.md: uma árvore suja (ou um dia de descanso) validava um HEAD que a
  suíte reprovaria.

## Fase 1 — gate POR LETRA

`opcoes_em_producao.LETRAS_COM_OPCOES_EM_PRODUCAO` vira o CONJUNTO das
letras que produção tem com duas opções (16 pares `(split, letra)`), e o
teste reprova se qualquer uma delas sair com uma — não por contagem total.
Hoje reprova em `abcd C` e `abcde D`; a Fase 4 resolve.

## Fase 2 — `docs/briefs/treino/TREINO.md`

O contrato do gerador, por nível × tipo de dia (`um_grupo`, `dois_grupos`,
`tres_grupos`, `inferior`, `superior`, `full`): exercícios por grupo por
sessão, séries por exercício, séries diretas por sessão, séries diretas por
grupo por semana POR FREQUÊNCIA do grupo (1×/2×/3×), proporção
composto/isolamento, descanso, duração esperada. Fontes: Schoenfeld, Ogborn
& Krieger 2017 (dose-resposta, ≥ 10 séries/semana); Schoenfeld et al. 2019
(30+ séries/semana em treinados); Israetel/RP (MEV–MAV–MRV, MRV sobe com
frequência); Helms, *Muscle & Strength Pyramid*; Baz-Valle et al. 2022
(12–20). Onde a literatura diverge das referências do dono — semana
12–18 contra sessões de 21–28 duas vezes por semana —, o documento explica:
a faixa de 12–18 vale para grupo treinado UMA vez; treinado duas, 18–26
(MAV alto → MRV); três, 22–30. As tabelas são lidas do disco por
`workouts/test_treino_md.py`, que cobra o gerador com o mesmo número — como
`config/test_design_system.py` cobra o `DESIGN.md`.

Formato das tabelas no documento: blocos `| nível | tipo de dia | ... |` com
os valores numéricos em colunas fixas, para o teste parsear.

## Fase 3 — faixas por tipo de dia e tetos de tempo

- `FAIXA_POR_TETO_SEMANAL` (12–15 / 15–18 / 16–20) sai. Entra
  `faixa_de_series(nivel, tipo_de_dia)` lida de `workouts/doutrina.py`, que
  carrega o TREINO.md UMA vez (o documento é a fonte; o módulo é o leitor).
- O teto semanal por grupo passa a depender da FREQUÊNCIA do grupo na semana
  (`teto_semanal(nivel, ocorrencias)`), em séries efetivas, derivado das
  faixas diretas do TREINO.md mais a folga do secundário.
- `TETO_POR_DURACAO[COMPLETO] = 90`; Padrão 60; Rápido 30; rótulos remedidos
  DEPOIS da ativação, com os números do gerador ("Padrão — até 60 min",
  "Completo — até 90 min, a ficha inteira").
- `TETO_RAPIDO_MIN = 40` fica.
- Teste dourado em `workouts/test_ficha_de_verdade.py`, imutável: as três
  frequências (3 dias ABC, 4 dias ABC, 5 dias abc2) × três níveis, Padrão e
  Completo. Se não passar com o catálogo dos 64, ajusta-se o motor ou o
  catálogo — nunca o teste.

## Fase 4 — ativação dos 28

- Foto conferida = vista por mim (as duas de cada), mesma pessoa e mesmo
  movimento entre `0.jpg` e `1.jpg`, sem marca d'água; a fonte é a
  free-exercise-db (licença Unlicense/domínio público — conferida no
  repositório). `scratchpad/shots-dose/mosaico.html`: um arquivo, foto +
  nome + fonte + licença + vídeo escolhido, para veto pelo celular.
- Os quatro contratos de mídia valem: `video` recebe o melhor candidato de
  Short achado por busca, com `video_titulo` do oEmbed conferido por
  `titulo_confere`; a anatomia (`animacoes.json`) recebe o "Músculos
  Trabalhados" do MESMO padrão de movimento já curado (mesmos músculos) ou
  um achado por busca — com a limitação declarada no mosaico: título
  conferido, quadro não assistido.
- `manage.py desativar_exercicio "<nome>"` deixa pronto o veto: `is_active`
  false no banco E `active: false` no JSON (o seed reativaria).
- Gate por letra depois: os 16 continuam, `abcd C` e `abcde D` voltam.

## Fase 5 — planos ativos

Política: plano ativo antigo NÃO é remontado. `sync_active_routine` só
remonta quando a pessoa pede (botão regenerar) ou o plano ficou INVÁLIDO
(sessão sem exercício ativo, dia sem sessão). A conferência
`routine_is_current` deixa de disparar remontagem por diferença de
prescrição: passa a marcar `plan.desatualizado` (propriedade calculada, sem
migration) e a Home mostra um aviso único e dispensável — "Seu treino pode
ficar mais completo — regenerar?". A dispensa é gravada em
`TrainingPlan.aviso_dispensado_em` (`DateTimeField null`, migration
aditiva), e não no navegador: um aviso que volta em cada aparelho é ruído.
Regenerar = `create_routine` (o plano antigo fica, é retrato).
Testes: plano `ab` antigo continua igual após o deploy; ao regenerar,
recebe a nova. Demo é re-semeado com a versão nova.

## Fase 6 — fechamento

Sabotagem de cada regra do TREINO.md e do teste dourado → revisão
adversarial (somente leitura) → correções → suíte completa → push → prova
de deploy → `/saude/` → smoke → QA em produção com conta descartável
(intermediário, 5 dias, abc2, Padrão): ficha de A com as duas opções,
exercícios e minutos, Completo também → conta apagada → demo intacta.
Falha em produção = reverter o deploy e avisar.

## Fora do escopo (proibido)

Afrouxar o teste dourado; `accounts`/`achievements` além do necessário;
ativar exercício sem foto conferida; `MINUTOS_POR_DURACAO` (cardápio).
