# Premium Polish — escopo original B1 a B11

RECUPERADO do transcript da sessão, não reconstruído. O corpo abaixo é cópia
literal da mensagem que definiu o escopo; nada foi reescrito, reordenado,
renomeado ou deduzido a partir do estado atual do app.

## Procedência

| | |
|---|---|
| fonte | transcript da sessão `9219ee0d-5c65-42b8-a70e-06ac12144638.jsonl` |
| linha | 29190 |
| papel | mensagem do usuário |
| data | 2026-09-02T16:39:43.443Z |
| título da missão | MISSÃO — FECHAMENTO DE ACEITAÇÃO + PREMIUM POLISH |

O escopo aparece como a FASE B daquela missão. As fases A, C e D da mesma
mensagem tratam de outros assuntos (provas humanas, auditoria de cache e
backlog) e não fazem parte de B1–B11.

### Não confundir com a missão anterior

Em 2026-09-01T17:45:27Z houve outra missão de polimento, "MISSÃO — NUTRIPLAN PREMIUM UI/UX POLISH
V1" (linha 21650 do mesmo transcript). Ela **não usa rótulos B** — a lista dela
é numerada de 1 a 8 e trata de prioridades gerais. É anterior e distinta; não é
uma versão de B1–B11, e não foi misturada aqui.

### Emenda posterior a B7

Doze minutos depois, em 2026-09-02T16:51:05.068Z, a mensagem "REFINAMENTO B7 / FASE C — PRIVACIDADE
LOCAL DA PWA" (linha 29246) ampliou B7: mandou inventariar TODA persistência
client-side (Cache Storage, IndexedDB, localStorage, sessionStorage, estado do
service worker, filas offline) e não apenas `CACHE_PAGINAS`. Esse refinamento
foi executado e publicado; B7 abaixo fica na redação original, e a emenda está
registrada aqui para não se perder.

---

FASE B — PREMIUM POLISH
==================================================

Enquanto as duas provas humanas estiverem bloqueadas,
avance autonomamente no Premium Polish.

NÃO redesenhar o NutriPlan.

Preservar:

- verde da marca;
- identidade;
- estrutura;
- componentes existentes;
- arquitetura atual.

Objetivo:
fazer parecer produto final, não protótipo.

==================================================
B1 — LOGIN / CADASTRO
==================================================

Auditar visualmente em viewport real:

375px
430px
768px
desktop.

Melhorar:

- hierarquia;
- identidade NutriPlan;
- CTA;
- estados de erro;
- Google login;
- espaçamento;
- contraste;
- teclado/mobile;
- loading.

Não mexer no fluxo de autenticação funcional
sem necessidade comprovada.

==================================================
B2 — HOJE
==================================================

Auditar:

- primeira dobra;
- resumo do dia;
- refeição atual;
- água;
- treino;
- pendências;
- excesso de informação;
- estados vazios.

O usuário deve entender em poucos segundos:

“O que eu preciso fazer agora?”

Não criar dashboard lotado.

==================================================
B3 — TREINO
==================================================

Polir:

- entrada da ficha;
- início do treino;
- exercício atual;
- vídeo;
- séries;
- descanso;
- feedback de conclusão;
- pós-treino;
- acesso à Corrida.

Não mudar novamente o motor de volume/duração
sem defeito comprovado.

==================================================
B4 — PROGRESSO V2
==================================================

A funcionalidade já foi publicada.

Agora auditar visualmente:

Resumo
→ Peso
→ Treino
→ Água
→ Histórico detalhado.

Confirmar em viewport REAL:

- ordem;
- leitura;
- barras;
- zero states;
- datas;
- unidades;
- texto;
- contraste;
- touch targets;
- ausência de scroll horizontal.

Nunca usar viewport 0×0 como evidência.

==================================================
B5 — /GESTAO
==================================================

Polir somente onde houver benefício operacional.

Não transformar em dashboard de vaidade.

Manter:

Painel
Pessoas
Atividade.

Não adicionar:

pagamentos
assinaturas
cupons

enquanto esses sistemas não existem.

==================================================
B6 — NAVEGAÇÃO
==================================================

Estado atual permanece:

Dieta
Treino
Progresso
Perfil

[manter a estrutura real atualmente publicada]

Corrida continua alcançável pelo Treino
até validação física.

Depois do teste em aparelho,
avaliar promoção para:

Dieta
Treino
Corrida
Progresso
Perfil

Não promover antes.

Preservar o guardrail TodaTelaTemPortaTests.

==================================================
B7 — PWA / SERVICE WORKER
==================================================

Preservar a correção crítica:

/admin/
e
/gestao/

NUNCA podem ser cacheados como páginas privadas navegáveis.

Auditar se existe outra rota autenticada contendo PII
que ainda entra em CACHE_PAGINAS.

Não assumir que corrigir apenas Admin/Gestao
resolveu todas as superfícies privadas.

Se encontrar outras:
corrigir com regra estrutural,
não lista frágil de páginas uma por uma quando possível.

Adicionar teste regressivo.

==================================================
B8 — VISUAL QA REAL
==================================================

Para cada tela alterada:

- renderizar;
- navegar de verdade;
- provar que existe porta;
- testar 375px;
- testar 430px;
- testar tablet;
- testar desktop;
- verificar scroll horizontal;
- verificar target >= 44px;
- contraste;
- tamanho mínimo;
- estado vazio;
- estado cheio;
- loading;
- erro quando aplicável.

Não considerar HTTP 200 equivalente a UX funcional.

==================================================
B9 — DISCIPLINA DE TESTES
==================================================

Preservar os guardrails sistêmicos criados:

RotasExtrasDoAdminTests
TodaTelaTemPortaTests
ComentarioDeTemplateNaoVazaTests
MatrizDeCapabilityTests

E preservar a regra:

NUNCA rodar suíte dirigida
enquanto suíte completa estiver usando o mesmo test_nutriplan.

Antes de qualquer nova execução:
verificar se existe runner ativo.

==================================================
B10 — SEGURANÇA
==================================================

Não reabrir:

- change_profile;
- add_user;
- senha de terceiros;
- SocialToken;
- SocialApp;
- SocialAccount;
- EmailAddress;
- WeightEntry standalone;
- permissões amplas.

Mudança visual não pode ressuscitar capability.

==================================================
B11 — TESTES / PUBLICAÇÃO
==================================================

Para cada lote coerente de polish:

testes dirigidos
→ sabotage relevante se houver regra nova
→ browser QA
→ suíte completa
→ gate
→ commit
→ push
→ hook
→ deploy
→ smoke.

Não produzir dezenas de commits cosméticos sem validação visual.
