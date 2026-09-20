# Auditoria 100 % em produção — 20/09/2026, parte B (sessão infra)

Complemento de `achados/auditoria-20260920.md` (sessão auditoria, mesma data).
A missão chegou a duas sessões ao mesmo tempo; a divisão está no ledger
(15:36): a parte A fez a Fase 1 em produção como usuário real, a semana
simulada e o demo × app por títulos; esta parte B fez o que a A não cobriu
com a mesma profundidade — **PWA de ponta a ponta** (manifesto, ícones,
pré-cache, offline de verdade, atualização do service worker), **tempo até
interativo por rota** (frio × quente), **axe-core em 37 rotas**, **foco por
Tab**, **páginas de erro**, **demo × app por estrutura** e o **custo por tela
em consultas** — e a Fase 3 inteira.

Produção `dc971a0` (depois `cf11109`, só LICENSE/.gitignore). Navegador:
`agent-browser` 0.38.1 (o Smart App Control foi desligado pelo dono neste
dia; `scripts/qa/nav.py` é o fallback), Chrome 153, 390 × 844 e 1280 × 800,
Ferro (`prefers-color-scheme: dark`) e Papel. Régua visual: a MESMA da parte
A (`lib.py::JS_MEDIR`, copiada para `audit-b/medir.js`), para as duas
sessões medirem com um critério só. Em produção só GET; **nenhuma conta
criada e nenhuma senha digitada por esta sessão** (regra da plataforma desta
sessão; a parte A tinha permissão e usou quatro contas descartáveis). O
lado "app logado" foi o servidor LOCAL no commit de produção, logado como o
MESMO Carlos do seed por cookie de sessão gerado no servidor
(`scripts/qa/sessao.py`).

Vocabulário: evidência `[EXECUTADA]` · `[OBSERVADA]` · `[LIDA NO CÓDIGO]` ·
`[HIPOTÉTICA]`; classe BUG · UX REAL · OBSERVAÇÃO · FALSO POSITIVO ·
LIMITAÇÃO; gravidade **bloqueia** / **atrapalha** / **feio** / **ideia**.
`PROVADO EM PRODUÇÃO` ≠ `PROVADO LOCAL`.

## Cobertura

| o quê | quanto | onde |
|---|---|---|
| manifesto, 4 ícones (PIL: tamanho real, margem do maskable, fundo), 3 atalhos, `<head>` de 3 rotas, favicon, `sw.js` e os 8 itens do pré-cache (status, tipo, `Cache-Control`, bytes) | tudo 200; zona segura medida | produção `[EXECUTADA]` |
| SW registrado na 1ª visita, controlador na 2ª, conteúdo do cache no navegador, `set offline` | 9 itens em `nutriplan-v6` | produção `[EXECUTADA]` |
| offline DE VERDADE (servidor derrubado) para a Home visitada, o login (no-store) e uma rota nunca vista; volta da rede; atualização do SW com estático novo (versão, `waiting`, caches, folha no cache, erros de página) | 3 cenários + 1 atualização | local, commit de produção `[EXECUTADA]` |
| tempo até interativo: TTFB/FCP/DCL/load, bytes e requisições por rota, FRIO (sessão nova, sem SW) e QUENTE (2ª abertura com SW) | 17 rotas × 2 + 3 a 1280 | produção `[EXECUTADA]` |
| axe-core 4.12 (`agent-browser a11y`) | 17 rotas públicas/demo em produção + 20 rotas logadas local | `[EXECUTADA]` |
| foco por Tab de verdade (`press Tab`, `:focus-visible`, anel, visibilidade) | 7 telas, 121 paradas | prod + local `[EXECUTADA]` |
| 404, 403 de CSRF, 405, nos dois temas | prod + local | `[EXECUTADA]` |
| /demo/ × app logado (mesmo Carlos, mesmo commit): títulos, cabeçalhos, botões, formulários, cartões, estados vazios, altura; régua visual nos dois temas | 9 pares | `[EXECUTADA]` |
| consultas e tempo de render por tela logada (Carlos, 487 séries) | 9 telas | local `[EXECUTADA]` |

## Achados

Formato: `rota · passo · o que aconteceu · o que devia · captura · gravidade · classe · evidência`.

### bloqueia

- (nenhum) — o PWA instala, pré-cacheia, serve offline e se atualiza; nenhuma rota pública ou do demo dá 5xx; nenhum controle sem foco.

### atrapalha

- `/conquistas/` (e `/demo/conquistas/`) · abrir a tela · **TTFB 1,07 s frio / 1,19 s quente** em produção, contra 250–350 ms de toda outra tela; local, para o Carlos (487 séries), **252 consultas, 159 repetidas** (75 × BEGIN + SELECT + COMMIT: `avaliar` fazia um `get_or_create` transacional POR DETECÇÃO, e o recorde detecta um par exercício×data por exercício) — cresce com o histórico · três consultas fixas · `perf/tempos.json` · atrapalha · BUG `[EXECUTADA em produção e local; causa LIDA NO CÓDIGO]` → **corrigido no PR #42** (252 → 28 consultas, 100 → 38 ms local).
- `/` (e `/conta/peso/`, `/recalibrar/`, `/demo/hoje/`, que renderizam a Home) · "Dados do cálculo" · axe `nested-interactive` (serious): `<a>Editar</a>` DENTRO do `<summary>` — dois alvos num toque, e o teclado não chega ao segundo · controle nunca dentro de `<summary>` · — · atrapalha · BUG `[EXECUTADA]` → **corrigido no PR #43**.
- `/conta/onboarding/1/`, `/2/`, `/3/`, `/treino/corridas/nova/` · listas de escolha · axe `listitem` (serious): `<ul role="group">` em `partials/field.html` e `partials/choice_cards.html` troca a semântica da lista e deixa 2 + 24 + 17 + 4 `<li>` órfãos — o leitor de tela perde "item 1 de N" · grupo envolvendo a lista, `<ul>` sem `role` · — · atrapalha · BUG `[EXECUTADA]` → **corrigido no PR #43** (junto: a faixa "página do cache" de `base.html`, `<ul role="status">`, mesma classe de defeito, invisível ao axe porque nasce escondida).

### feio

- ~~`/manifest.webmanifest` · ícones `maskable` · margem de 22,9 % / 22,7 %, "o dobro dos 10 % da zona segura"~~ → **FALSO POSITIVO, desmentido pelo protótipo** (`proto/maskable-12`, mosaico em `achados/capturas-20260920-b/maskable-antes-depois.png`): os 10 % valem para arte que cabe num CÍRCULO; a marca é QUADRADA (o "N" com a folha), e um quadrado dentro do círculo de raio 40 % tem lado máximo 0,8/√2 = 56,6 % — margem de **21,7 %**. Com 12 % o canto do N sai cortado no recorte circular do Android. Os 22,9 % de hoje são a geometria certa. MANTER.
- `/` (Carlos, 1ª visita ao Progresso) · toast "🏆 Conquista desbloqueada" · a celebração segue a pessoa por TODA página até "Continuar" — em `/historico/`, `/lista-de-compras/` e `/conta/perfil/` seguidos, cobrindo um item da lista de compras; depois "1 de 5 · Novo recorde" com "Próxima" · uma vez, onde nasce · `demo/006-app_lista-de-compras_390.png` · feio (a parte A mediu o pior caso, sobre o CTA da execução, como atrapalha) · UX REAL `[OBSERVADA local]` → é tema da parte A (Fase 2 dela).

### ideia

- `/static/css/app.css` · primeira visita · **340 093 bytes brutos / 106 KB gzip (br 105 KB), e 60 % do arquivo é COMENTÁRIO** (sem comentários: 134 631 bytes, **23 KB gzip**); a cobertura de regras por CDP (24 rotas × 2 temas × 2 larguras, todo `<details>` aberto, campo focado) usa 87 % dos bytes de regra — o peso não é CSS morto, é comentário que vai para o navegador de quem usa · a maior transferência da primeira visita depois do HTML: 222–250 KB no total por rota fria (8–12 requisições), FCP frio de **1,2–2,2 s** (mediana 1,59 s) num Wi-Fi de escritório; no 3G da parte A, 4–6 s. As fontes são 70 KB nos dois `.woff2` (35 + 35, ~490 ms cada, frias). QUENTE (SW + cache) o FCP cai para 290–810 ms e o TTFB (250–670 ms, o servidor) passa a mandar · tirar os comentários da cópia servida no `collectstatic` (a fonte continua comentada) — `proto/css-sem-comentarios`: 23,4 KB gzip / 19,4 KB br medidos; é pós-processo, e "nada de build step" é decisão do dono · `perf/tempos.json` · ideia · OBSERVAÇÃO `[EXECUTADA]`.
- `/demo/hoje/` · quente · HTML de 62 KB decodificado (10 KB na rede): 20 formulários (um por refeição × marcar/desfazer/comi-outra-coisa) na Home de 3 056 px · a parte A registrou a altura como feio; aqui fica o custo · ideia · OBSERVAÇÃO `[EXECUTADA]`.

### FALSO POSITIVO e LIMITAÇÃO (registrados para ninguém refazer)

- `/offline/` "traz identidade": a régua achou a STRING `data-usuario` — o atributo está vazio (`data-usuario=""`, `data-autenticado="0"`); o shell é neutro. A armadilha do CLAUDE.md (seletor = marcador) aplicada à própria auditoria. FALSO POSITIVO.
- `set offline on` do agent-browser (CDP `Network.emulateNetworkConditions`) vale para o DOCUMENTO, não para o `fetch` do service worker: com "offline" ligado, uma rota nunca vista recebeu a 404 de PRODUÇÃO — o SW buscou na rede de verdade. Por isso o offline foi provado LOCAL com o servidor DERRUBADO. LIMITAÇÃO (da emulação, não do produto).
- 404 local "genérica": `DJANGO_DEBUG=true` no servidor de QA; a 404 de produção é a própria, com caminho de volta. FALSO POSITIVO.
- página LOGADA (`/`, `/treino/`) no cache do SW: é DESIGN ("rede primeiro com paciência limitada" guarda a própria página para servir sem rede com a faixa "última versão salva"), não vazamento — a rota nunca vista recebe o shell neutro. FALSO POSITIVO.

## O que está BOM e foi provado (para a nota da Fase 4)

- **PWA**: manifesto completo (`id`, `standalone`, `display_override`, `lang`, 4 ícones, 3 atalhos vivos), `<head>` com as metas de iOS e `mobile-web-app-capable`, `sw.js` com `no-store`, pré-cache de 8 itens todos 200 e imutáveis (`max-age=315360000, immutable`), SW ativo na 1ª visita e controlando na 2ª, uma geração só de cache. **Offline de verdade** (servidor derrubado): a Home visitada volta do cache com a faixa "Você está sem conexão — esta tela é a última versão salva", o login (`no-store`) e uma rota nunca vista recebem o shell "Sem conexão" NEUTRO (`data-autenticado="0"`, `data-usuario=""`); a rede volta e a Home é a viva. **Atualização do SW**: estático novo → versão nova → sem `waiting` depois de duas navegações, o cache do shell fica SÓ com a folha nova (a antiga sai), zero erros de página. `[EXECUTADA local]`
- **Desempenho quente**: mediana de FCP **392 ms** e DCL **354 ms** com o SW; 6–17 KB por rota; HTTP/2. O que sobra é o servidor (TTFB 250–670 ms no Render free + Neon) — e `/conquistas/`, corrigido.
- **Acessibilidade**: axe-core limpo em **35 de 37 rotas** (as 2 violações vêm de parciais e estão corrigidas no PR #43); foco por Tab com anel em **121 de 121 paradas**, ordem lógica, nada fora da tela; 403 de CSRF e 404 com a página própria e caminho de volta.
- **Demo × app**: os 9 pares têm títulos, cabeçalhos, cartões e formulários IDÊNTICOS (mesmo Carlos, mesmo commit) — o demo não promete nada que o app não tenha nem esconde nada que o app tenha; a única diferença é o toast de conquista, que o demo não mostra porque recusa POST. As 8 promessas da capa apontam para telas que existem e fazem o que a frase diz.

## Medições (tabela)

TTI por rota em produção, 390 px, Ferro. FRIO = sessão nova sem SW; QUENTE = 2ª abertura com SW.

| rota | frio: TTFB / FCP / DCL / load (ms) · KB · req | quente: TTFB / FCP / DCL (ms) · KB |
|---|---|---|
| `/conta/entrar/` | 343 / 1880 / 1045 / 1318 · 222 KB · 8 | 256 / 340 / 316 · 11 KB |
| `/conta/cadastro/` | 310 / 1796 / 1309 / 1575 · 222 KB · 8 | 265 / 328 / 301 · 11 KB |
| `/conta/senha/` | 300 / 1188 / 824 / 1257 · 221 KB · 8 | 261 / 320 / 295 · 8 KB |
| `/privacidade/` | 347 / 1664 / 1335 / 1665 · 225 KB · 8 | 248 / 384 / 324 · 18 KB |
| `/termos/` | 298 / 1588 / 838 / 1163 · 223 KB · 8 | 316 / 404 / 376 · 13 KB |
| `/offline/` | 250 / — / 274 / 275 · 6 KB · 3 | 250 / 288 / 269 · 6 KB |
| `/demo/` | 405 / 1392 / 879 / 1179 · 242 KB · 11 | 278 / 360 / 339 · 17 KB |
| `/demo/hoje/` | 692 / 2160 / 1362 / 1674 · 248 KB · 11 | 669 / 808 / 762 · 63 KB |
| `/demo/treino/` | 531 / 1564 / 1115 / 1422 · 245 KB · 11 | 551 / 644 / 616 · 32 KB |
| `/demo/treino/corridas/` | 345 / 1664 / 1352 / 1783 · 250 KB · 12 | 295 / 392 / 354 · 13 KB |
| `/demo/hidratacao/` | 356 / 1732 / 1010 / 1293 · 243 KB · 11 | 367 / 576 / 523 · 20 KB |
| `/demo/conta/perfil/` | 475 / 1640 / 1155 / 1593 · 242 KB · 11 | 326 / 484 / 444 · 18 KB |
| `/demo/areas/` | 345 / 1204 / 848 / 1131 · 241 KB · 11 | 289 / 360 / 322 · 13 KB |
| `/demo/sobre/` | 360 / 1280 / 873 / 1300 · 242 KB · 11 | 253 / 324 / 293 · 13 KB |
| `/demo/historico/` | 470 / 1428 / 1037 / 1523 · 243 KB · 11 | 534 / 656 / 583 · 35 KB |
| `/demo/lista-de-compras/` | 453 / 1524 / 1073 / 1369 · 243 KB · 11 | 331 / 404 / 386 · 25 KB |
| `/demo/conquistas/` | **1067** / 2052 / 1635 / 1928 · 242 KB · 11 | **1191** / 1264 / 1242 · 16 KB |

Mediana frio: FCP 1 588 · DCL 1 045 · load 1 369 ms. Mediana quente: FCP 392 · DCL 354 ms. A 1280 (quente): `/demo/hoje/` FCP 756, `/demo/treino/` 504, `/demo/historico/` 512 ms.

Consultas e render por tela logada (local, Carlos, 2ª abertura): `/conquistas/` **252 (159 rep.) 100 ms** → 28 / 38 ms com o PR #42 · `/` 43 (6) 74 ms · `/historico/` 27 (2) 34 ms · `/treino/` 21 (3) 37 ms · `/lista-de-compras/` 18 (2) 23 ms · `/conta/perfil/` 18 (4) 20 ms · `/hidratacao/` 13 (2) 15 ms · `/areas/` 8 · `/treino/corridas/` 4.

Ícones: `any` 192/512 com 1,0 % / 0,4 % de margem (sangrados, certo); `maskable` 192/512 com 22,9 % / 22,7 % (para arte quadrada a zona segura circular pede 21,7 % — certo); `apple-touch-icon` 180 × 180, canto opaco. Pré-cache: 646 KB brutos (CSS 340 KB, fontes 70 KB, ícones 159 KB, JS 86 KB).

## Onde estão os roteiros e as capturas

Scratchpad da sessão (`…/e5d582f4…/scratchpad/audit-b/`): `ab.py` (o agent-browser como biblioteca — saída em ARQUIVO, nunca em pipe: o daemon herda os descritores), `medir.js`, `pwa.py`, `desempenho.py`, `demo_x_app.py`, `a11y_erros.py`, `sw_local.py`, `servidor.py`; resultados em `pwa/`, `perf/`, `demo/`, `a11y/`, `sw/` (achados.json + PNG + logs). As capturas citadas estão em `achados/capturas-20260920-b/`.
