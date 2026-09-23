# Missão UX + PWA redondo — o que foi medido, o que foi corrigido

**Sessão `ux-pwa` (3146901b), 22/09/2026.** Alvo: os sete itens de UX do dono
e a varredura de qualidade, sem trabalho de loja/nativo.

Produção estava em `9df3e55` e `main`/staging em `6a7649b` quando a missão
começou. O diff entre os dois, fora de `nativo/`, `.github/`, `docs/` e
`achados/`, é **vazio** — a superfície web dos dois é a mesma, e é por isso
que a medição feita no staging vale para o que está no ar.

---

## 1. Os sete itens: o que a medição achou

Os sete já tinham sido atacados na missão de UX anterior (lotes 1 a 5, PRs
#108–#112, todos em produção). Esta missão **mediu cada um no app de
verdade** antes de tocar em qualquer coisa — conta descartável criada pelo
cadastro público do staging, apagada pela tela no fim, login recusado depois
(`scratchpad/uxpwa/verificar.py`, 32 asserções).

| # | item do dono | veredito | prova |
|---|---|---|---|
| 1 | sessão cai e perde dados no envio | **defeito de RAIZ ainda aberto** | ver seção 2 |
| 2 | equipamento do cadastro reverte | **não reproduz** | "só o peso do corpo" chega à etapa 3, ao Perfil e à ficha gerada (zero aparelho na lista) |
| 3 | erro não aponta o campo | **corrigido e provado** | corrida e reportar: `aria-invalid`, foco de teclado, rolagem até o campo e `aria-describedby` apontando o erro |
| 4 | prioridade não muda a Home | **corrigido e provado** | o cartão "Seu treino" nasce com selo "sua área", antes das refeições, com a ação do dia |
| 5 | falta "não faço musculação" | **corrigido e provado** | marcar "não faço" esconde o bloco da academia e mostra a nota |
| 6 | "aderência 20%" no primeiro dia | **corrigido e provado** | a caixa diz "1/1 Refeições · hoje, até agora", sem porcentagem; a linha do dia diz "até agora" |
| 7 | botão não responde ao primeiro toque | **corrigido e provado** | o link da barra é alcançável em repouso e `pwa.js` re-entrega o toque perdido na transição |

As três "falhas" da primeira rodada eram do meu instrumento, não do app, e
estão registradas aqui porque cada uma é uma armadilha que volta:

- o item 4 exigia botão `btn--primary`, e o cartão do dia de DESCANSO traz
  `btn--ghost` ("Ver a semana") — de propósito;
- o item 6 media a tela de Progresso de quem ainda não registrou nada, onde
  a caixa de aderência **não existe** (`{% if totals.days %}`);
- o item 7 usava `.tabbar a, nav a`, e lista de seletores resolve em ordem
  de DOCUMENTO: casava com a barra DE CIMA.

E uma quarta, a mais cara: a primeira varredura usou `E2E.rodar()`, que
fecha o navegador no `finally`. Tudo depois dela rodou anônimo, e doze telas
logadas foram medidas como **tela de login** — "zero violação" que não
media nada. O instrumento passou a chamar os passos direto.

---

## 2. ACHADO DE SEGURANÇA (o que o dono pediu para destacar)

A queixa "a sessão cai e eu perco o que digitei" foi perseguida até a raiz,
e a mesma medição — uma sessão **logada** do staging, lendo os cabeçalhos
pelo `fetch` same-origin, que é o que curl anônimo não alcança — devolveu
dois achados. **Os dois são de configuração, e os dois são de segurança, não
só de UX.**

### 2.1 Tela logada respondia SEM `Cache-Control` (moderado)

`/historico/`, `/treino/` e `/conta/perfil/` não mandavam diretiva nenhuma.
Sem diretiva o navegador guarda por heurística, e o que ele guarda aqui é
peso, altura, e-mail, objetivo e histórico de treino — dado de saúde, o
mesmo que a etapa 1 do cadastro pede autorização para tratar (LGPD art. 11).
Consequência concreta num aparelho de casa: **sair da conta e apertar VOLTAR
redesenhava a tela da pessoa anterior a partir do disco**, sem passar pelo
servidor.

Corrigido por `config.cache_privado.CachePrivadoMiddleware`: `private,
no-cache, must-revalidate` em toda resposta HTML de sessão autenticada que
não declare a própria diretiva.

E **nada de `no-store`**, o que parece mais seguro e não é: o service worker
recusa guardar resposta com `no-store` (é o cache dele que faz a dieta abrir
no metrô) e o Chrome desliga o bfcache numa página `no-store` — que é
exatamente o "Voltar ao formulário" devolvendo o que a pessoa digitou. O
teste lê a régua do próprio worker para as duas pontas não divergirem.

Provado no navegador, com o app **instalado** (janela `--app=`, modo
standalone): a tela logada continua no cache do worker e abre sem rede
depois da mudança.

### 2.2 Não havia Content-Security-Policy em rota nenhuma (moderado)

Medido em produção e no staging: nenhuma rota manda CSP. CSP não conserta um
XSS; ela limita o estrago de um que exista, e num app com esse dado o limite
vale o trabalho. Está sendo corrigido com política medida e nonce por
resposta (ver o PR correspondente).

### 2.3 O que ESTÁ certo, e foi conferido

- `sessionid` é `HttpOnly` (o JavaScript só enxerga `csrftoken`, que é para
  isso mesmo), `Secure` e `SameSite=Lax`;
- HSTS de um ano com `includeSubDomains`; `X-Frame-Options: DENY`;
  `X-Content-Type-Options: nosniff`; `Referrer-Policy:
  strict-origin-when-cross-origin`; `Cross-Origin-Opener-Policy: same-origin`;
- **não há `logout()` em POST nenhum** — só na exclusão da conta. A queixa
  não era logout;
- a sessão deslizante do lote 4 está no ar: quem usa todo dia não é mais
  deslogado a cada 14 dias.

### 2.4 A raiz do item 1, e por que ela não é um bypass

Sobrava o 403 de CSRF, por dois caminhos medidos: a página veio do **cache
do service worker** (ele serve a cópia guardada quando a rede passa de 3 s)
com o token de uma sessão anterior; ou a pessoa **entrou de novo em outra
aba** e `login()` chamou `rotate_token()`. Nos dois o cookie está certo e só
o campo escondido do HTML está velho — e `fila.js` já trocava o token pelo do
momento do envio, que é por que a água marcada sem rede nunca sofreu. Quem
sofria era o formulário COMUM, o longo: a etapa 2 do cadastro e o registro de
corrida, os dois citados pelo dono.

`pwa.js` passou a reescrever `csrfmiddlewaretoken` com o valor do cookie no
carregamento, no `pageshow` (bfcache) e no `submit` em captura. **Não
enfraquece nada**, e há teste dos dois lados: o valor cru do cookie é aceito
(se `CSRF_COOKIE_MASKED` for ligado um dia, o teste cai antes da produção) e
token de outro segredo continua 403. É o que a documentação do Django manda
fazer em requisição AJAX; a defesa vem de o cookie só ser legível por
JavaScript da PRÓPRIA origem.

Provado no navegador: campo trocado por `token-de-outra-sessao-ja-vencido`,
o envio passa e a corrida é gravada — onde o staging, com o código de hoje,
devolve "Este envio não pôde ser confirmado".

---

## 3. A varredura de qualidade

### 3.1 Acessibilidade e larguras de celular

`scratchpad/uxpwa/varredura.py`: doze telas (Home, Progresso, Treino,
Corridas, Perfil, Áreas, Conquistas, Avisos, Hidratação, Ajuda, Entrar,
Cadastro), **nos dois temas**, com `axe-core`; e a régua de layout a **360,
390 e 430 px**, também nos dois temas.

**Zero violação do axe. Zero rolagem horizontal. Zero texto abaixo de 11 px.
Zero alvo de toque abaixo de 44 px.**

A mesma varredura foi repetida em **768, 1024 e 1280 px**, nos dois temas
(tablet e desktop, as duas larguras que o B8 pede além do celular): zero
violação, zero rolagem horizontal, zero achado. As capturas de cada tela nos
dois temas ficam em `capturas/` das duas execuções.

A única coisa que a régua acusou era falso positivo dela: a caixa dos Termos
no cadastro tem 19×19 px, mas o ALVO é o `<label>` em volta — medido,
298×121 px a 390. A régua passou a medir o rótulo, que é o que a WCAG 2.5.8
mede.

### 3.2 O PWA, instalado, offline e na volta da rede

Duas provas. No staging, com conta descartável e o `agent-browser`: o
service worker controla a página, o manifesto é `standalone` com ícones de
192 e 512, `/treino/` abre **sem rede** vindo do cache, o "+250 ml" sem rede
vira "esperando conexão", e a fila **drena** quando a rede volta (o valor
fica em 250 e o aviso some).

E no servidor local, com o app **de verdade instalado** — janela em modo de
aplicativo (`--app=`), que é a que o atalho de um PWA abre: `display-mode:
standalone` confirmado, worker no controle, o convite de instalação
ausente (é o que "instalado" muda no código deste app), a tela logada
guardada no cache do worker **mesmo com o `Cache-Control` novo**, e o
Progresso abrindo sem rede.

Registrado para quem repetir: o CDP **não** emula `display-mode` —
`Emulation.setEmulatedMedia` com essa feature deixa
`matchMedia('(display-mode: standalone)')` em `false`. O que dá janela
standalone de verdade é subir o Chrome com `--app=<url>`.

### 3.3 Texto de erro e de botão

Auditoria de leitura sobre `templates/` e os `forms.py`/`views.py`.
**Nenhuma palavra em inglês** em texto visível e **nenhuma mensagem padrão
do Django sem tradução** — os dois tipos que mais aparecem em app assim.
Oito achados de consistência, todos pequenos; os quatro que moram em
`workouts/` foram passados para a sessão que está redesenhando aquela área.

---

## 3.4 A verificação final, depois de tudo publicado

Com produção em `e291533` (os dois PRs de segurança), a régua rodou de novo
contra o staging no MESMO commit, com conta descartável nova:
**29 asserções, ZERO falhas** — os sete itens, mais os três cabeçalhos:

- `Cache-Control: private, no-cache, must-revalidate` nas quatro telas com
  dado de saúde (antes: nenhuma diretiva);
- `Content-Security-Policy` completa em todas elas (antes: nenhuma);
- `sessionid` invisível ao JavaScript, como já era.

E o item 1 mudou de sinal: a régua ainda escreve `token-de-outra-aba` no
campo escondido, e **o envio agora SALVA a corrida** em vez de cair no 403.
O instrumento foi atualizado para cobrar isso — o antes está no histórico,
o depois é a asserção.

## 4. O que foi entregue

| PR | o que faz | prova |
|---|---|---|
| **#126** | `Cache-Control: private, no-cache, must-revalidate` na tela logada; token de CSRF lido do cookie | suíte completa verde (4269, OK); navegador: token velho e o envio passa; app instalado: a tela continua no cache do worker |
| **#128** | `Content-Security-Policy` com nonce por resposta, política medida | suíte completa verde (4286, OK); 19 telas sem violação, controle positivo, vídeo e fotos exercidos |
| **#129** | texto no plural, "Sua conta", título da 500, placeholder do peso; a régua do CSP pulando o corpo do script; `scripts/qa/verificar_ux.py` | suíte completa verde (4286, OK); sabotagem da régua vermelha |

#126 e #128 foram promovidos para **produção** no lote `e291533` e
conferidos lá; #129 mergeou (`6732bbd`) e sobe no lote seguinte — a regra do
dono é lote provado, no máximo uma vez por hora, e quem promove é o cron.

## 5. Decisões que tomei sozinha

1. **`private, no-cache, must-revalidate` e não `no-store`** — `no-store`
   desligaria o cache de páginas do service worker (a dieta deixaria de
   abrir no metrô) e o bfcache (o "Voltar ao formulário" do 403). Medido:
   com a diretiva nova, a tela logada CONTINUA no cache do worker.
2. **Renovar o token de CSRF pelo cookie, em vez de só tratar o 403** — o
   dono pediu raiz, não remendo. O rascunho e a página em português
   continuam como rede de segurança para o caso que sobra (sessão que
   venceu de verdade).
3. **CSP enforced, não report-only** — sem endpoint de relatório, o
   report-only não relata para ninguém; o que dá confiança é a varredura de
   console com controle positivo, e ela foi feita.
4. **A casca nativa fica fora da CSP** — o Capacitor injeta a própria ponte
   e não conhece o nonce. Um XSS no navegador da vítima não muda o
   User-Agent dela, então a isenção não é porta.
5. **`style-src` com `'unsafe-inline'`** — a barra de progresso é
   `style="width: {{ pct }}%"` calculado pelo servidor, exceção que já
   estava escrita no `CLAUDE.md`. Estilo inline não executa código.
6. **Os quatro achados de texto em `workouts/` ficaram com a sessão que está
   redesenhando o Treino** — combinado pelo canal entre sessões, para não
   brigar no merge com um redesenho inteiro daquela área.

## 6. O que a CSP quebrou na suíte, e por que isso é informação

Quatro testes de SEGURANÇA ficaram vermelhos quando a política entrou, e
nenhum deles por um defeito: `LimiteDeRecuperacaoTests`,
`RecuperacaoDeSenhaTests`, `TetoDiarioTests` e `ARecusaNaoVirouOraculoTests`
comparam **duas respostas byte a byte** para provar que a recusa não é
oráculo — bloqueado, senha errada e conta inexistente respondem a mesma
coisa. O nonce é sorteado por resposta, então duas respostas idênticas
passaram a diferir.

`accounts.tests.sem_o_que_muda_por_resposta` normaliza o token de CSRF e o
nonce, e só eles. Vale registrar porque a próxima pessoa que puser um valor
por resposta no HTML vai derrubar os mesmos quatro testes, e vai achar que
quebrou segurança.

## 7. O que NÃO foi feito, e por quê

- **A promoção para produção é do cron**, não minha: a regra do dono é lote
  provado, no máximo uma vez por hora. O PR #126 mergeou, o staging provou
  (`da79d62`) e o lote ficou ADIADO por estar dentro da janela de 60 min —
  produção sobe no `--lote` seguinte, sem ninguém empurrar.
- **Nenhum trabalho de loja ou nativo**, como o dono pediu. A casca do
  Capacitor só aparece aqui como uma linha da política de CSP (ela não
  recebe a política), e o achado aberto do iOS da missão anterior continua
  aberto.
- **Os quatro achados de texto em `workouts/`** ficaram com a sessão que
  está redesenhando aquela área inteira, por acordo entre as duas sessões.

## 8. O que preciso de você

Nada. Nenhum item cai nas quatro condições de parada (dinheiro novo, dado
real de produção, direção não escrita, credencial que não existe).
