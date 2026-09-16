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

**Duas espécies de recorde**, por exercício, sempre contra dias ANTERIORES:

| espécie | definição | onde já existe |
|---|---|---|
| carga | `weight_kg` > máximo de todos os registros anteriores | `supera_recorde` |
| reps×carga | `weight_kg × reps` da série > maior produto de uma única série anterior | **novo** |

Regra: primeiro treino do exercício não é recorde (sem registro anterior →
`False`, já é assim). Exercício `sem_carga` (prancha em segundos): sem recorde.

**Detecção**: `services.supera_recorde` passa a devolver o conjunto de espécies
superadas (`{"carga"}`, `{"reps_x_carga"}`, ambos, ou vazio) numa consulta só
(`Max("weight_kg")` e o maior `weight_kg*reps` via `ExpressionWrapper`). A view
continua chamando `avaliar` quando o conjunto não é vazio. `load_history`
ganha `recorde_volume_anterior` (maior produto anterior) no mesmo laço; a
linha da série ganha `recorde_volume: bool`.

**Anúncio**: a conquista `novo-recorde` continua uma por exercício por dia; a
frase dela passa a dizer a espécie ("Agachamento livre: 65 kg, sua maior carga"
/ "Agachamento livre: 60 kg × 12, seu melhor volume numa série").

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
`padding-bottom` igual à altura do aviso (mesmo mecanismo de `body.tem-convite`),
o aviso fecha também por **Esc** e por **toque fora** (mesmo POST de
`marcar_vistas` via `fetch`, `X-Requested-With: fetch`), e a fila de conquistas
NÃO aparece em página de erro: o `include` do parcial em `base.html` fica atrás
de `{% if request.resolver_match %}` — o 404 não tem `resolver_match`, e o 500
renderiza sem `request`. Teste: `elementFromPoint` não é possível no Django test; o
teste garante a classe no `body` e a regra de CSS, e o QA de produção repete
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
assim; fica um teste que pina as duas ordens lado a lado; (b) quando a
pastilha pendente não tem `anterior[série]` (a última sessão teve menos
séries), ela mostra a última série da última sessão com o rótulo "última
vez" em vez de "—".

## 1.3 Gráfico por exercício

`historico_do_exercicio` passa a 12 sessões (`DATAS_DO_HISTORICO = 12`) e
cada sessão ganha `volume` = Σ(carga × reps) das séries com carga e reps.

Dois gráficos SVG inline, um em cima do outro, na tela do exercício
(`exercicio.html`, acima da lista "Como fui") e no histórico da pessoa
(`/historico/`, bloco Treino, um par por exercício com ≥2 sessões, no máximo
os 6 de `progressao_de_carga`):

- **Carga máxima por sessão** — polyline, mesmo produtor de `_curva_de_peso`
  generalizado para `workouts/curva.py: curva(valores, largura=300, altura=64)`
  (escala pelo período, piso 0,4, `None` com <2 pontos). Última sessão marcada
  com um círculo.
- **Volume por sessão** — mesma curva, cor `--warm`.

Cores só por token (`stroke: currentColor` + classe). `role="img"` com
`aria-label` que diz o resumo ("Carga máxima: 60 kg há 12 sessões, 65 kg na
última"). Exercício `sem_carga`: sem gráficos (a lista continua). Sem
biblioteca. Orçamento de consultas: `test_exercicio_leitura.test_o_custo_e_fixo`
continua valendo — o volume sai do mesmo laço.

**Divergência registrada:** `workouts/progresso.py` recusa VOLUME TOTAL do
mês por escrito ("métrica sem ação"). Volume por sessão de UM exercício é o
segundo eixo da dupla progressão (reps sobem antes da carga) e responde
"fiz mais trabalho neste exercício?". A decisão sobre o total continua
intocada. **Recomendo rever** se o dono considerar que a mesma razão vale
aqui.

## Testes (TDD, sabotagem em cada guarda)

- `workouts/test_recorde_de_volume.py`: reps×carga supera / não supera /
  estreia / `sem_carga`; carga E volume no mesmo toque = uma conquista; frase
  diz a espécie; orçamento de consultas do POST não sobe (estender
  `test_recorde_na_hora.CONSULTAS_*`).
- `achievements/test_frame_de_recompensa.py`: variante `--recorde`, `body.tem-conquista`,
  Esc/POST por fetch, nada em 404, interruptor de som lido do template.
- `config/test_movimento.py`: as novas animações usam tokens e entram na
  lista de reduced-motion (o teste existente cobra).
- `workouts/test_prefill_por_serie.py`: pina as ordens de carga e reps; pastilha
  "última vez".
- `workouts/test_grafico_do_exercicio.py`: 12 sessões, volume por sessão,
  `curva()` (escala, piso, <2 pontos), SVG presente com carga e ausente em
  `sem_carga`, `aria-label`, cores por classe.
- Teste dourado `test_ficha_de_verdade.py`: intocado.

## Fora da Fase 1

Corrida (Fase 2), dieta (Fase 3), U2/U35/D1, o link "trocar de opção" <44 px.
