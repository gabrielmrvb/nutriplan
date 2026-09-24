# Missão A — dado errado

**24/09/2026** · branch `dado/numeros-honestos` (base `origin/main` `6f570f0`)
· três commits, um por defeito · PR aberto, sem merge.

O contrato: **nenhum número que o app mostra pode divergir do que ele
guarda.** Os três defeitos foram reproduzidos no navegador antes de o código
ser tocado, corrigidos com teste vermelho-antes e uma sabotagem cada, e
provados de novo no navegador depois.

Vocabulário de evidência: `[EXECUTADA]` (rodei), `[OBSERVADA]` (vi na tela),
`[LIDA NO CÓDIGO]`, `[LIMITAÇÃO]`.

## Como foi medido

Servidor local na porta 8033 sobre o banco `nutriplan_dado` (Postgres
portátil desta máquina), `agent-browser` 0.38.1 a **390×844, tema escuro**,
movimento reduzido. Conta de teste `qa-dado-20260923@nutriplan.invalid`
(senha gerada, nunca impressa), criada com três dias de vida, cinco dias de
treino, cardápio de cinco refeições, água e refeições de dois dias
anteriores. As ações que a missão pede — registrar série, trocar
equipamento, reler o Progresso — aconteceram **no navegador**; só o estado
inicial nasceu pelo ORM.

Roteiros em `scratchpad/` (`conta_dado.py`, `repro1.py`, `repro2.py`,
`repro3.py`, `axe_dado.py`); capturas em
`achados/capturas/missao-a/{antes,depois}/` — `capturas/` é ignorada pelo
git (`.gitignore:77`), então as imagens ficam nesta máquina e o que viaja no
PR é a MEDIÇÃO transcrita aqui.

---

## 1. O histórico do exercício mostrava a carga errada

**O que era.** Três séries registradas pela execução — 60 kg × 8, 62,5 × 7,
62,5 × 6 — e a leitura do exercício (`/treino/exercicio/12/`, "Como fui")
escrevendo `[OBSERVADA]`:

```
24/09    62,50 × 8, 7, 6
```

O banco estava certo: `ExerciseLog` sempre teve `set_number` e `weight_kg`
por linha, e a consulta devolveu `(1, 60.00, 8) (2, 62.50, 7) (3, 62.50, 6)`
`[EXECUTADA]`. Era a LEITURA que perdia a série:
`services.historico_do_exercicio` reduzia o dia a `max(weight_kg)` e juntava
as repetições numa lista; o template as unia com `join`. A primeira série,
feita a 60, aparecia a 62,5.

**O que virou** `[OBSERVADA]`:

```
24/09    60 × 8 · 62,50 × 7 · 62,50 × 6 · 1.292,50 kg no total
```

Cada dia passa a trazer `series` (número, carga e reps de cada uma, na ordem
do `set_number`) e `volume` — a soma de carga × reps, a conta que a pessoa
consegue refazer no papel; sem ela uma lista de pares não fecha. `carga` (o
máximo do dia) e `reps` continuam existindo porque é de `carga` que a curva
do exercício é desenhada.

`templates/workouts/_series_do_dia.html` é **uma** parcial para as duas
listas — o exercício em foco e o original da troca ("No lugar de X") —, e
foi por serem duas cópias que a carga máxima chegou às duas. Quem decide
mostrar o kg é a SÉRIE, e não o `sem_carga` de quem inclui: `weight_kg` é
NOT NULL e o peso do corpo grava zero, então "0,00 × 8" seria o mesmo
defeito ao contrário.

**Como provei.** `workouts/test_historico_serie_a_serie.py`, 6 testes
`[EXECUTADA]`. Vermelhos antes, com a mensagem sendo o próprio defeito
(`'60' not found in '62,50 × 8, 7, 6'`). **Sabotagem:** mudar a carga da
série 1 para 47,50 no banco tem de mudar a linha da tela — antes não mudava,
porque só o máximo era impresso.

Capturas: `antes/01-exercicio-historico.png`,
`depois/01-exercicio-historico.png`.

**O que NÃO mudou de propósito.** A curva de carga continua sendo do máximo
por sessão (`progresso.py` decidiu que a tela não inventa métrica); e1RM
continua fora. O volume leva ponto de milhar, que é a régua do placar
(achado #16 das personas), e não uma convenção nova.

---

## 2. O histórico sumia quando a ficha era remontada

**O que era.** Com as três séries registradas, trocar o equipamento em
Perfil › Treinos › Editar (`/conta/onboarding/2/` → Salvar) para "só o peso
do corpo" e deixar a ficha ser remontada no dia seguinte fazia
`/treino/exercicio/12/` responder **404** `[OBSERVADA]`, com as três séries
intactas no banco `[EXECUTADA]`. O histórico só existia na exportação.

Nota de reprodução: no MESMO dia a ficha não é remontada ("há série
registrada hoje, então a ficha muda amanhã"), e por isso a troca de
equipamento sozinha não reproduz — o 404 aparece na remontagem. No roteiro,
as séries foram movidas para ontem e `sync_active_routine` foi chamado, que
é o que o app faz sozinho na primeira Home do dia seguinte `[EXECUTADA]`.

`ExercicioView` buscava o exercício DENTRO do plano ativo `[LIDA NO CÓDIGO]`.

**O que virou.** Uma segunda porta, mais forte que a primeira: **o exercício
em que ESTA pessoa registrou série é dela**, esteja ele na ficha de hoje ou
não. O IDOR não afrouxa — a condição é sobre `logs__user`, que é a própria
pessoa. `is_active` não é exigido por essa porta: exercício aposentado nunca
é apagado, e quem treinou um deles continua tendo o que ler. Quem apagou a
rotina inteira também abre.

Quem chega assim lê `[OBSERVADA]`:

> Este exercício não está na sua ficha de hoje — ele saiu quando a ficha foi
> remontada. O que você registrou continua aqui embaixo.

E "Na sua ficha"/"Quando" somem, em vez de imprimir uma prescrição que não
existe.

A porta ganhou maçaneta: **`/treino/exercicios/` — "Exercícios que já fiz"**
— lista tudo em que a pessoa registrou série, com quantas séries e a data da
última, em UMA consulta (o filtro e as duas agregações na mesma junção). O
link está no cabeçalho de "Seu programa" no painel e no de "Como fui" na
leitura (`.card__head a`, o link de 44 px que essas telas já usam).

**Como provei.** `workouts/test_historico_sobrevive_a_ficha.py`, 13 testes
`[EXECUTADA]`; vermelhos antes com `404 != 200`. **Sabotagem:** apagar as
séries devolve o 404 — é o REGISTRO que abre a página, e não "qualquer id".
Continuam 404: id inexistente e exercício de outra pessoa.

No navegador, depois `[OBSERVADA]`: `/treino/exercicio/12/` responde 200 com
"Supino inclinado com halteres", a linha `23/09 60 × 8 · 62,50 × 7 · 62,50 ×
6 · 1.292,50 kg no total`, o aviso acima, e `/treino/exercicios/` mostrando
"Supino inclinado com halteres · 3 séries · 23/09".

Capturas: `antes/02-exercicio-404-depois-da-troca.png`,
`depois/02-exercicio-depois-da-troca.png`,
`depois/02b-exercicios-que-ja-fiz.png`.

**Correção de rota minha, no meio do caminho:** a primeira versão da tela
nova inventou `.data-list__item` / `__nome` / `__valor`, que **não existem**
no CSS desta branch. A régua de toque mediu 214×17 no link `[EXECUTADA]`.
Refeita sobre `.ficha-lista` + `.ficha-item`, que é o componente da ficha —
"uma lista numerada em que cada linha é uma porta para a leitura do
exercício" é exatamente esta tela — e a régua voltou a zero.

---

## 3. Os números do Progresso, e a ofensiva das três telas

### 3a. A média de kcal e a aderência tinham denominadores diferentes

**O que era.** Desde 22/09/2026 `adherence_pct` é dos DIAS FECHADOS — hoje
ainda está acontecendo. `avg_kcal` continuou somando TODOS os dias, hoje
incluído, e ao lado imprimia "meta: 2 161", que é a meta de um dia inteiro
`[LIDA NO CÓDIGO]`. Dois números na mesma caixa com recortes diferentes: a
média caía toda manhã (um dia novo entra com o café), subia durante o dia, e
no primeiro dia de uso ela era o café da manhã chamado de "kcal/dia".

**O que virou.** Os dois leem o mesmo recorte. Medido na conta de teste: a
caixa dizia `899 kcal` (média de 539 + 1 403 + 755 ÷ 3, com o 539 sendo o
dia em andamento) e passou a dizer `1 079` (1 403 + 755 ÷ 2, os dois dias
fechados) `[OBSERVADA]`. Sem dia fechado, `avg_kcal` é `None` como a
porcentagem, e a caixa diz o que ela TEM: `539 kcal · hoje, até agora`
`[OBSERVADA]` na conta de dia 1.

### 3b. A ofensiva passou a ter uma porta só

**O que era.** As três telas já contaram diferente: até 22/09 as Conquistas
chamavam `streaks.calcular` sem `meta_agua_ml`, a água "fechava" todo dia, e
com a régua "treino e (dieta ou água)" cada dia de descanso dos 400 do
histórico fechava sozinho — "3 dias de ofensiva" no dia 1, "401 / 3" para
quem não tem dia de treino, com a Home dizendo 0 ao lado (achado #4 das
personas). A correção de então foi passar a meta nos dois lugares, o que
deixou a régua dependendo de o chamador **lembrar**.

**O que virou.** `streaks.para_a_tela` deriva a meta do plano ativo, e
nenhuma tela escolhe a sua. Home e Conquistas emprestam o plano que já
carregaram (`plano=`): zero consulta a mais, orçamentos de
`plans/test_stress` intactos `[EXECUTADA]`.

**A sabotagem é a medida do risco:** com `calcular` nu de volta em
`achievements.reunir`, o teste que compara as três telas devolve
`{(None, 11), (3000, 0)}` `[EXECUTADA]` — onze dias numa tela e zero na
outra, sobre a mesma conta. É o defeito antigo, reproduzido em teste.

### 3c. A frase de ontem diz o número

**O que era** `[OBSERVADA]`, na Home da conta de teste:

> Recomeça hoje: treino no dia de treino, mais dieta ou água. **Ontem faltou
> dieta ou água.**

A pessoa tinha registrado 3 refeições de 5 e bebido 1 500 ml de uma meta de
3 000 — ela registrou as duas coisas; o que faltou foi CHEGAR na meta.

**O que virou** `[OBSERVADA]`:

> Recomeça hoje: treino no dia de treino, mais dieta ou água. **Ontem: 3 de
> 5 refeições e água 1,5 de 3 L.**

`Dia` passou a carregar as medidas (séries, refeições feitas/previstas,
água/meta) e `pendencias_medidas` as escreve. A contagem de séries vem no
MESMO `GROUP BY` que já lia as datas — nenhuma consulta nova. Num dia de
treino sem série, a frase diz "nenhuma série num dia de treino".

`falta_hoje` continua com o rótulo curto, de propósito: hoje ainda dá para
fazer, e ali a pergunta é o que fazer, não quanto faltou. A ordem da frase —
convite primeiro, ontem depois — é a decisão de 22/09 e não muda.

### O que a determinação mediu

Cinco GET seguidos de `/historico/` e o GET que vem do redirect do POST do
peso, na mesma conta `[EXECUTADA]`:

| | antes | depois |
|---|---|---|
| GET 1–5 | `50% · 899 kcal` (as cinco iguais) | `50% · 1079 kcal` (as cinco iguais) |
| pós-POST do peso | `50% · 899 kcal` | `50% · 1079 kcal` |

**Honestidade sobre o relato:** a variação que a missão descreve — "20 % ·
783", depois "15 % · 591", depois "14 % · 559" — **não se reproduziu como
leituras seguidas**: as cinco leituras já eram idênticas entre si antes da
correção, e o POST do peso não movia a caixa. O que existe no código, e foi
corrigido, é a causa que produz aqueles três números ao longo de um dia: a
média incluía o dia em andamento, então ela caía quando um dia novo entrava
com pouca caloria e subia à medida que a pessoa comia — três leituras em
horas diferentes do mesmo dia davam três médias, sobre dados que a pessoa
não tinha mudado de propósito. Depois da correção a caixa não se move com o
relógio: há teste lendo o mesmo banco às 7h, 13h, 20h e 23h e exigindo um
único resultado.

**A "3 dias de ofensiva no dia 1" não reproduziu:** na conta de teste, Home,
Progresso e Conquistas já diziam **0** `[EXECUTADA]` — a correção de 22/09
está de pé em `main`. O que esta missão fez foi tirar a régua da memória do
chamador e prender as três telas num teste.

**Como provei.** `plans/test_numeros_do_progresso.py`, 14 testes
`[EXECUTADA]`, mais a atualização de duas expectativas antigas que seguiam a
regra velha (`plans/tests.py`, `plans/test_ofensiva_comeca_na_conta.py`),
cada uma com a razão escrita no próprio teste.

Capturas: `antes/03-historico-get1.png`, `antes/03-historico-pos-post.png`,
`antes/04-ofensiva-home.png`; `depois/` os mesmos, mais
`depois/03b-progresso-primeiro-dia.png` e
`depois/04b-ofensiva-home-dobra.png`.

`[LIMITAÇÃO]` A captura "antes" da Home é do viewport (390×844) e a frase da
ofensiva fica abaixo da dobra — as duas capturas da Home saíram com os
mesmos bytes. A prova do texto de antes é a saída do roteiro
(`Ontem faltou dieta ou água`), registrada acima, e o teste que fica vermelho
sem a correção.

---

## Qualidade

- **Suíte completa** `[EXECUTADA]`: ver a última linha desta seção.
- **axe** nas três telas mudadas (`/treino/exercicio/<id>/`,
  `/treino/exercicios/`, `/historico/`) a **390 e 1280, escuro e claro** —
  12 combinações, **zero violações** `[EXECUTADA]`.
- **Régua de toque e rolagem** nas mesmas telas a 360, 390 e 1280: zero alvo
  abaixo de 44 px, zero texto abaixo de 11 px, zero rolagem horizontal
  `[EXECUTADA]`.
- `manage.py check`, `makemigrations --check`, `git diff --check`: limpos.
  Nenhuma migration — os três defeitos eram de leitura.

## A conta de teste foi apagada pela tela

`[EXECUTADA]` `/conta/excluir/` com a senha da própria conta (gerada pelo
roteiro, nunca impressa), botão "Excluir minha conta para sempre". A tela
respondeu **"Conta de qa-dado-20260923@nutriplan.invalid apagada"**, a
sessão morreu na hora (`/historico/` passou a devolver `/conta/entrar/`), e
o banco confirma: `User.objects.filter(email=...).exists()` é `False` e não
sobrou conta nenhuma `[EXECUTADA]`. Captura em `depois/05-conta-excluida.png`.

A conta auxiliar do "primeiro dia" (`qa-dado-dia1@…`, criada só para a
captura da caixa sem média) foi apagada pelo ORM: a senha dela foi gerada e
descartada no mesmo comando, então não havia como passar pela tela. Tudo
isso viveu no banco LOCAL `nutriplan_dado` desta máquina; produção e staging
não foram tocados.

## Outros números divergentes que achei no caminho — LISTA, não corrigi

Como a missão pede, ficam para a próxima:

1. **"1 dias com registro"** na caixa do Progresso. Sem plural; aparece em
   toda conta de primeiro dia `[OBSERVADA]`.
2. **`achievements.resumo` GRAVA numa requisição GET.** É decisão escrita
   (ela desbloqueia a regra que chegou a 100 % para não mostrar barra cheia
   com "Desbloqueadas 0"), mas a consequência é que a PRIMEIRA leitura do
   Progresso num dia pode mostrar um número de conquistas diferente da
   segunda — "mesmos dados, números diferentes" pela porta de trás
   `[LIDA NO CÓDIGO]`.
3. **`tracking.history` recorta o dia de HOJE pelo relógio**
   (`previstas_ate_agora`), então a linha de hoje no "dia a dia" muda de
   porcentagem ao longo do dia: 100 % às 7h, 20 % às 23h, com o mesmo
   registro `[EXECUTADA]`. É a decisão de 22/09 e a linha diz "até agora" —
   mas é o único número da tela que ainda se move sozinho.
4. **`Max("slot__plan_id")` escolhe o plano mais novo do dia.** Quem
   recalcula a estimativa no meio do dia passa a ser julgado, naquele dia,
   pelo denominador do plano novo `[LIDA NO CÓDIGO]`.
5. **Código morto encontrado de passagem:** `plans.views._curva_de_peso`
   continua exportando a curva antiga ao lado da nova, e
   `workouts.progresso.progressao_de_carga` é lida só pelo Progresso.

## Decisões que tomei sozinha

- **O volume da sessão entrou junto com as séries.** A missão pede que
  "o volume da sessão por exercício seja igual a séries × reps × carga"; sem
  o número na tela não havia o que conferir. Ponto de milhar pela régua do
  placar.
- **`avg_kcal` é `None` sem dia fechado**, e não zero. Zero é um número, e a
  tela imprimia "0 kcal/dia · meta 2 161" para quem ainda não tinha
  registrado nada — a mesma falsa precisão que a porcentagem já evitava.
- **A frase de ontem nomeia só os pilares que FALHARAM**, com os números
  deles. A doutrina de 22/09 ("pendências diz o que FECHA o dia, não a lista
  de tudo que faltou") continua valendo; o que mudou é que cada item traz o
  número. A letra da sessão ("1 série do B") ficou de fora: ela exigiria uma
  consulta a `workouts` dentro de `streaks`, e a missão proíbe tocar no
  motor da ficha.
- **A lista "Exercícios que já fiz" usa `.ficha-lista`/`.ficha-item`**, o
  componente da ficha, em vez de classes novas.
- **O link para a lista mora em dois cabeçalhos** (painel de Treino e
  leitura do exercício) e em nenhum lugar novo da navegação: a barra de
  abas e o mapa de áreas não mudaram.
- **O exercício APOSENTADO com histórico abre.** `is_active` deixou de ser
  exigido pela porta do histórico; `ExerciseLog` é `CASCADE` e o catálogo
  nunca apaga, então o dado existe e a pessoa tem direito a lê-lo.

## O que preciso de você

nada.
