# Padrões de mercado — Fase 1: execução do treino no nível Hevy/Strong

Missão de 16/09/2026. Referência: `docs/briefs/mercado/BENCHMARK-2026-09.md`
(padrões a, b, c). Estado medido em produção: `scratchpad/avaliacao/2026-09-16-delta/DELTA.md`.
Spec vence proposta externa (`CLAUDE.md`, Autonomia): onde o benchmark
contradiz decisão escrita, esta spec segue a decisão e marca "recomendo rever".

## O que já existe (não refazer)

- `services.supera_recorde` (carga > máximo de dias anteriores; estreia = não)
  dispara `achievements.avaliar` na hora; a conquista `novo-recorde`
  (família RECORDE, repetível) é anunciada pelo overlay `.conquista`
  (`templates/partials/_conquista.html`, seção 40 do CSS); a pastilha da
  série ganha `series__recorde` "recorde"; a tela diz "Recorde: X kg".
  Provado por `workouts/test_recorde_na_hora.py` e `achievements/test_na_hora.py`.
- `load_history` já devolve `anterior[série]` (mesma série da última sessão),
  e a pastilha pendente mostra `antes_peso×antes_reps`.
- `_sugestao_de_carga`: última série de HOJE > `progressao.valor` (T2.3) >
  `anterior[série]` > `melhor_anterior`. Decisão escrita de 30/08 e T2.x
  ("frase == campo"; ninguém troca de carga entre a 1ª e a 2ª série).
- "Principal" = primeiro composto de cada grupo anunciado (`aca0939`). **1.4 feita.**
- `historico_do_exercicio`: 8 sessões, carga máxima + reps por série.
- Padrão de SVG por template: `templates/plans/_peso.html` + `_curva_de_peso`
  (polyline, `stroke: currentColor`, cor por token).

## 1.1 Recorde celebrado na hora

**Duas espécies de recorde**, por exercício, sempre contra dias ANTERIORES,
e CADA UMA é a própria regra/conquista — não uma frase condicional dentro de
uma conquista só (emendado 16/09/2026, fix wave: a primeira redação deste
parágrafo previa uma `novo-recorde` só, com a frase mudando de espécie; o que
foi construído são duas `Regra` distintas, `novo-recorde` e `melhor-serie`,
ambas na família `Familia.RECORDE`):

| espécie | definição | regra/conquista | onde já existe |
|---|---|---|---|
| carga | `weight_kg` > máximo de todos os registros anteriores | `novo-recorde` | `supera_recorde` |
| reps×carga ("melhor série") | `weight_kg × reps` da série > maior produto de uma única série anterior | `melhor-serie` | `supera_recorde` |

Regra: primeiro treino do exercício não é recorde (sem registro anterior →
conjunto vazio, já é assim). Exercício `sem_carga` (prancha em segundos): sem
recorde de nenhuma espécie. **Carga E melhor série no mesmo toque são DUAS
conquistas** — uma de cada regra —, anunciadas na MESMA fila (o `.conquista`
já é fila, não pilha, desde a decisão original desta seção).

**Detecção**: `services.supera_recorde` devolve o conjunto de espécies
superadas (`{"carga"}`, `{"melhor_serie"}`, ambos, ou vazio) numa consulta só
(`Max("weight_kg")` e o maior `weight_kg*reps` via `ExpressionWrapper`,
filtrando séries sem reps antes de comparar — uma série só com peso não pode
inflar o produto máximo). A view continua chamando `avaliar` quando o
conjunto não é vazio. `load_history` ganha `melhor_serie_anterior` (maior
produto anterior) e `melhor_serie_peso`/`melhor_serie_reps` (o registro por
trás do produto, para o FATO da tela) no mesmo laço; a linha da série ganha
`melhor_serie: bool` ao lado de `recorde: bool`.

**Anúncio, e o contrato de privacidade**: `novo-recorde` e `melhor-serie` têm
cada uma seu próprio título e frase, e NENHUMA das duas carrega número — é o
mesmo contrato que `_recorde` já tinha (a chave é `exercício:data`, nunca
`exercício:carga`, para a carga não precisar ser persistida nem vazar para
dentro de um card que a pessoa manda para um grupo). A frase diz só o
exercício: "Novo recorde: Agachamento livre." / "Melhor série: Agachamento
livre." Os NÚMEROS ("65 kg", "60 kg × 12") aparecem só na TELA DE EXECUÇÃO
(`agora.html`), nunca na conquista: na pastilha da série concluída
(`series__recorde`, texto "recorde" / "melhor série") e no fato acima do
campo ("Recorde: 65 kg" / "Melhor série: 60 kg × 10").

**Frame de recompensa**: entrada animada do `.conquista` e pulso do emoji,
CSS puro na seção 47 (Movimento), com tokens (`--mov-sucesso`, `--ease`) —
`config/test_movimento.py` proíbe duração escrita à mão — e desligado por
`prefers-reduced-motion` (lista da seção 47). Variante `.conquista--recorde`
com fundo `--brand-soft`. Nada de confete: anti-padrão escrito na skill de UX.

**Som opcional**: opt-in. Interruptor "Tocar um som ao desbloquear" na tela
`/conquistas/`, guardado em `localStorage` (`nutriplan.som-conquista`);
padrão desligado. Quando ligado, o overlay toca um acorde curto por
`AudioContext` (três notas, ~0,4 s), só depois de um gesto do usuário na
sessão (política de autoplay). Sem arquivo de áudio.

**N1 (bug achado no DELTA)**: o overlay fixo cobre o CTA do rodapé de toda
página até "Continuar". Correção: `body.tem-conquista` recebe
`padding-bottom` igual à altura do aviso (mesmo mecanismo de
`body.tem-convite`), e o aviso fecha por **Esc** (mesmo POST de
`marcar_vistas` via `fetch`, `X-Requested-With: fetch`) e pelo botão
**Continuar** — SEM toque fora (emendado 16/09/2026, fix wave: a primeira
redação deste parágrafo previa fechar também por toque fora; o parcial
(`partials/_conquista.html`) tem doutrina própria contra isso — "Deliberadamente
NÃO interrompe: aparece ancorado embaixo, não escurece a tela e não rouba o
foco", `role="status"` e não `dialog` — e um fechamento por toque fora
contradiria essa doutrina).

A fila de conquistas NÃO aparece em página de erro, e o mecanismo NÃO é
`request.resolver_match` sozinho (emendado 16/09/2026, fix wave: a primeira
redação estava errada — um `Http404` levantado DENTRO de uma view já
resolvida, ex. `get_object_or_404` em `/treino/exercicio/999999/`, também
deixa `resolver_match` preenchido; só a URL que não resolve fica com ele em
`None`). O mecanismo real: `config/urls.py` declara `handler404`/`handler403`
(`config/erros.py`), reimplementados a partir do contrato de
`django.views.defaults.page_not_found`/`permission_denied` com
`pagina_de_erro=True` a mais no contexto; `base.html` calha o `{% include %}`
do parcial e a classe `tem-conquista` do `body` atrás de `not
pagina_de_erro` (mantendo `request.resolver_match` na condição também,
inofensivo). O 500 continua fora deste mecanismo — `server_error` renderiza
sem `request` e sem estender `base.html` (regra própria, `config/test_b8_paginas_de_erro.py`).
Teste: `elementFromPoint` não é possível no Django test; o teste garante a
classe no `body`, a regra de CSS, e as duas telas de erro (404 de URL que
não resolve e 404 levantado dentro de uma view), e o QA de produção repete
a captura `d23`.

## 1.2 Pré-preenchimento por série

**Decisão: manter a ordem atual do campo** (hoje > T2.3 > mesma série da
última sessão > mais pesada), porque trocar por "mesma série da última
sessão" antes de "hoje" faz a 2ª série abrir com 60 depois de a pessoa ter
feito 62,5 na 1ª sob uma sugestão SUBIR — e `ajuste` devolve `None` com série
anotada hoje, de propósito. A "mesma série da última sessão" já é visível em
cada pastilha. **Recomendo rever** só se o dono preferir o comportamento
literal do Hevy (sem motor de progressão).

O que muda: (a) `_sugestao_de_reps` passa a seguir a MESMA ordem da carga
(hoje > piso quando `REPS_NO_PISO` > `anterior[série].reps`) — hoje já é
assim; fica um teste que pina as duas ordens lado a lado; (b) REVERTIDO em
17/09: a pastilha de uma série que nunca existiu (última sessão com menos
séries) continua "—". `test_pastilha.py` já decide isso, pelo mesmo
princípio de `_sugestao_de_carga` ("nunca um chute"). Recomendo rever só se
o dono quiser o comportamento literal do Hevy.

## 1.3 Gráfico por exercício

**Emendado 16/09/2026 (fix wave), a partir de uma ruling na ledger
(`.superpowers/sdd/2026-09-16-mercado-fase-1-treino/progress.md`): o par no
`/historico/` (um gráfico por exercício, ao lado dos 6 de
`progressao_de_carga`) fica ADIADO para uma onda futura.** A tela do
exercício já é a superfície primária de "como estou indo neste movimento", e
duplicar a mesma curva no histórico é YAGNI nesta fase — custo se a ruling
estiver errada: o benchmark (b) fica só na tela do exercício, não no
histórico agregado. O que segue descreve só o que FOI construído.

`historico_do_exercicio` passa a 12 sessões (`DATAS_DO_HISTORICO = 12`). UM
gráfico SVG inline na tela do exercício (`exercicio.html`, acima da lista
"Como fui"):

- **Carga máxima por sessão** — polyline, mesmo produtor de `_curva_de_peso`
  generalizado para `workouts/curva.py: curva(valores, largura=300, altura=64)`
  (escala pelo período, piso 0,4, `None` com <2 pontos). Última sessão marcada
  com um círculo.

Cores só por token (`stroke: currentColor` + classe). `role="img"` com
`aria-label` que diz o resumo ("Carga máxima: 60 kg há 12 sessões, 65 kg na
última"). Exercício `sem_carga`: sem gráfico (a lista continua). Sem
biblioteca. Orçamento de consultas: `test_exercicio_leitura.test_o_custo_e_fixo`
continua valendo — a curva é montada em Python a partir do `historico` que a
view já buscava, sem consulta a mais.

**Volume por sessão NÃO foi construído** (emendado 16/09/2026: a primeira
redação previa um segundo gráfico, "Volume por sessão", cor `--warm`, lado a
lado com a carga máxima). `workouts/progresso.py` recusa VOLUME TOTAL do mês
por escrito ("métrica sem ação"), e `historico_do_exercicio` já documenta a
mesma régua ("sem e1RM nem volume — a tela não inventa métrica"). A tensão
que a primeira redação registrou como **"recomendo rever"** — volume por
sessão de UM exercício seria o segundo eixo da dupla progressão, e
responderia "fiz mais trabalho neste exercício?" — foi resolvida a favor da
decisão já escrita, pela doutrina de Autonomia do `CLAUDE.md` (spec vence
proposta externa quando o benchmark contradiz decisão escrita). Sem ruling
nova que reabra a divergência, o volume continua fora.

## Testes (TDD, sabotagem em cada guarda)

- `workouts/test_recorde_de_volume.py`: reps×carga (melhor série) supera /
  não supera / estreia / `sem_carga`; **carga E melhor série no mesmo toque
  = DUAS conquistas** (emendado 16/09/2026: a primeira redação previa uma
  conquista só) — `test_carga_e_melhor_serie_no_mesmo_toque_sao_duas_conquistas`;
  cada regra usa o próprio título na frase; orçamento de consultas do POST
  não sobe (estende `test_recorde_na_hora.CONSULTAS_*`).
- `achievements/test_frame_de_recompensa.py`: variante `--recorde`, `body.tem-conquista`,
  Esc/POST por fetch, nada em 404, interruptor de som lido do template.
- `config/test_movimento.py`: as novas animações usam tokens e entram na
  lista de reduced-motion (o teste existente cobra).
- `workouts/test_prefill_por_serie.py`: pina as ordens de carga e reps; pastilha
  "última vez".
- `workouts/test_grafico_do_exercicio.py`: 12 sessões, `curva()` (escala,
  piso, <2 pontos), SVG de carga máxima presente com carga e ausente em
  `sem_carga`, `aria-label`, cores por classe. SÓ carga máxima — sem "volume
  por sessão" (emendado 16/09/2026: ver §1.3).
- Teste dourado `test_ficha_de_verdade.py`: intocado.

## Fora da Fase 1

Corrida (Fase 2), dieta (Fase 3), U2/U35/D1, o link "trocar de opção" <44 px.
