# Padrões de mercado — Fase 2: a corrida deixa de ser meia-feature

Missão de 16/09/2026, Fase 2. Referência: `docs/briefs/mercado/BENCHMARK-2026-09.md`
(padrão d; "Strava e NRC dão registro manual e planos 5K/10K de graça"). Estado
medido: `DELTA.md` D5/U20 — `/treino/corridas/` só tem "Começar corrida" (GPS
com tela acesa), lista vazia, nada de manual, nada de plano, e a corrida não
conta na ofensiva nem no gasto. Spec vence proposta externa; divergências vão
para "recomendo rever".

## O que já existe (não refazer)

- `workouts.models.Corrida` (`op_id` único por pessoa, `comecou_em`/`terminou_em`,
  `distancia_m`, `duracao_s`, `teve_lacuna`, `parciais`; `pace_s_km`), `TracoDaCorrida`
  (só pela API), `SalvarCorridaView` (GPS, JSON) e `_conferir` com os tetos
  (`DISTANCIA_MINIMA_M=50`, `DISTANCIA_MAXIMA_M=300_000`, `DURACAO_MAXIMA_S=12h`,
  `VELOCIDADE_MAXIMA_MS=12,5`), espelhados na API e no `corrida.js`.
- `HistoricoDeCorridasView` + `corridas.html` (lista `data-list`, filtros `km`,
  `relogio`, `pace`), porta na ficha (`_corrida.html`), hub Áreas.
- Ofensiva: `plans/streaks.py::calcular` decide `treinou` por `ExerciseLog` na data.
- Doutrina: `docs/briefs/treino/TREINO.md` lido por `workouts/doutrina.py`
  (`_tabelas` genérico por cabeçalho, `_faixa`, `carregar()` com `lru_cache`,
  `ValueError` se faltar linha) e provado por `workouts/test_treino_md.py`.
- Padrão de exclusão em duas etapas: `ExcluirContaView` + `excluir_conta.html`
  (`btn--perigo`, "Cancelar"); idempotência de POST: `op_id` + constraint.

## 2.1 Registro manual, histórico, edição e exclusão

**Modelo.** `Corrida` ganha `origem` (`gps` | `manual`, padrão `gps` para o que
já existe) e `sensacao` (`leve` | `normal` | `pesada` | vazio). Migração aditiva.
GPS continua sem sensação (a tela do GPS não pergunta; fica para depois).

**Formulário** (`CorridaManualForm`): distância em km com vírgula (`Decimal`,
0,05–300), tempo `mm:ss` ou `h:mm:ss` (até 12 h), data (padrão hoje, nunca
futura), sensação (rádio, opcional). Validação reutiliza os tetos de
`corrida_views` — velocidade > 12,5 m/s recusa com a mesma frase da API
("mais rápido que o recorde dos 100 m"). `comecou_em` = data às 12:00 local
(o registro manual não tem hora; meio-dia evita cair no dia errado por fuso),
`terminou_em = comecou_em + duracao`. `op_id` vem escondido no GET
(uuid4) e a constraint `uma_corrida_por_operacao` engole o duplo toque —
mesmo padrão de `SalvarCorridaView`.

**Rotas** (`workouts/urls.py`): `corridas/nova/` (GET form, POST cria),
`corridas/<pk>/editar/` (só `origem=manual`; GPS não edita — o traço contradiria),
`corridas/<pk>/excluir/` (GET confirma, POST apaga; vale para as duas origens).
Tudo filtrado por `user` — 404 estrito para corrida alheia (como o exercício).

**Tela.** `corridas.html`: botão secundário "Registrar corrida à mão" ao lado
do GPS (o GPS continua primário — é o que o pilar promete); cada item da lista
ganha a sensação (quando houver), "à mão" discreto para `manual`, e os links
"editar" (manual) / "excluir". Edição reutiliza o mesmo template do
formulário. Exclusão: tela própria "Excluir esta corrida? 5,2 km · 28:10 ·
16/09" com `btn--perigo` e "Cancelar". Vazio: "Nenhuma corrida ainda. Comece
pelo GPS ou registre uma à mão."

**Não entra:** nota livre, foto, rota desenhada, importação de arquivo.

## 2.2 A corrida conta como treino na ofensiva e no gasto

**Ofensiva.** `plans/streaks.py::calcular`: o conjunto `treinou` passa a
incluir `localdate(comecou_em)` de toda `Corrida` da pessoa no período. Ponto
único, uma consulta a mais. Dia previsto de musculação em que a pessoa só
correu: cumpre a ofensiva (a régua é "moveu-se", não "fez a letra").

**Não muda:** `achievements` (contrato escrito em `regras.py:8-12`: "treinou =
um ExerciseLog na data"; `test_nao_ha_conquista_de_dado_que_o_app_nao_tem`
fixa as famílias) — conquista de corrida é onda futura, registrado.

**Gasto.** `plans/calculations.py` rejeita MET por escrito para o **plano**
(o fator de atividade cobre o dia a dia). A corrida registrada entra **por
cima**, líquida e visível: `gasto_kcal(corrida, peso_kg) = round(0,9 × peso_kg
× km)` (≈1 kcal/kg/km bruto; ≈0,9 líquido do repouso — fonte no CORRIDA.md).
`day_summary` ganha `gasto_corrida_kcal` (soma das corridas do dia) e
`remaining_kcal` soma esse valor; a Home mostra "+320 kcal da corrida de hoje"
na linha do saldo quando houver. **Recomendo rever:** quem se declarou
"altamente ativo" por correr todo dia conta a corrida duas vezes; a alternativa
(descontar do fator) é decisão de produto e não entra aqui.

## 2.3 Planos 5K e 10K

**Doutrina** `docs/briefs/corrida/CORRIDA.md`, no formato do TREINO.md, com
tabelas lidas por `workouts/doutrina_corrida.py` (mesmo parser genérico —
extrair `_tabelas`/`_faixa` de `workouts/doutrina.py` para reutilizar, não
copiar):

- `| plano | nivel | semanas | sessoes_por_semana |` (4 linhas: 5K/10K ×
  iniciante/intermediário; 8 semanas; 3 sessões);
- `| plano | nivel | semana | sessao | descricao | minutos |` (8 × 3 × 4 = 96
  linhas — o texto da sessão, ex.: "8 × (1 min corrida + 1 min caminhada)").
- Seção **Fontes**: NHS Couch to 5K (estrutura 9 semanas comprimida em 8 com
  a fonte dizendo por quê), Hal Higdon 10K Novice/Intermediate, ACSM para o
  gasto por km. O teste cobra a seção.
- `## Gasto`: a fórmula e o fator 0,9, lidos pelo motor (`| medida | valor |`).

**Modelo** `PlanoDeCorrida(user, plano, nivel, comecou_em: date, ativo)` — um
ativo por pessoa (constraint parcial). Semana atual = `(hoje − comecou_em) // 7 + 1`,
limitada a 8; depois da 8ª o plano fica "concluído".

**Tela.** Em `/treino/corridas/`: sem plano → "Quer um plano? 5K ou 10K, 8
semanas" → `corridas/plano/` escolhe plano e nível (começa hoje). Com plano →
cartão "Semana N de 8 · Plano 5K iniciante" com as 3 sessões da semana e
quais já contam como feitas: sessão `k` da semana está feita quando existe
a `k`-ésima corrida (manual ou GPS) dentro da semana. "Trocar/encerrar plano"
desativa. Sem lembrete, sem notificação.

## 2.4 "GPS fraco" apagado após leitura boa (B29)

`static/js/corrida.js::receber`: hoje `dizer("")` só na primeira âncora
(l. 167); uma leitura aceita com âncora existente (l. 173–196) deixa a
mensagem. Correção: `dizer("")` em toda leitura aceita. Teste no padrão de
`test_corrida_v1.py::OErroDizOQueAconteceuTests` (`corpo_da_funcao("receber")`
contém a limpeza fora do ramo da âncora). LIMITAÇÃO: headless não emula
leitura boa; a prova dinâmica fica para aparelho.

## Testes

- `workouts/test_corrida_manual.py`: form (vírgula, `mm:ss`/`h:mm:ss`, data
  futura, tetos, velocidade), criação com `op_id` (duplo POST = uma corrida),
  edição só manual (GPS → 404), exclusão em duas etapas, corrida alheia → 404,
  lista mostra sensação/"à mão"/links.
- `plans/test_streaks.py`: corrida no dia previsto cumpre a ofensiva; dia sem
  nada não cumpre (o teste existente continua).
- `plans/test_gasto_da_corrida.py`: fórmula lida do CORRIDA.md; `day_summary`
  soma; Home mostra a linha só quando há corrida.
- `workouts/test_corrida_md.py`: leitor × documento (como `test_treino_md.py`),
  96 sessões, fontes, `ValueError` com linha faltando; semana atual; sessão
  feita pela k-ésima corrida.
- `workouts/test_corrida_v1.py`: B29.
- Intocados: `test_ficha_de_verdade.py`, `test_treino_md.py`, contratos da API
  (`api/tests.py` — a API não muda nesta fase; `origem` sai como `gps` no JSON
  existente sem mexer no contrato).

## Fora da Fase 2

Conquistas de corrida, API manual, sensação no GPS, importação, mapa.
