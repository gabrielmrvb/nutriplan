# `medir.js` — a régua visual de uma tela

Conta, numa página aberta no navegador, o que a auditoria de design de
14/09/2026 mediu: altura da página, cartões, bordas e sombras visíveis,
texto em caixa alta, tamanhos e pesos de fonte, raios, fundos e tipos de
botão. É a régua do "antes × depois" de qualquer onda que mexa em
`static/css/app.css`.

## Como rodar

O script é uma IIFE que DEVOLVE um objeto: cole em `Runtime.evaluate`
(`scripts/qa/nav.py <sessão> eval "$(cat scripts/qa/medir.js)"`), no console
do DevTools, ou em `agent-browser eval`. `nav.py` fala CDP com o Chrome
headless que o `agent-browser` baixou (`~/.agent-browser/browsers/`), para
quando o binário do `agent-browser` estiver bloqueado — foi o caso em
14/09/2026, pelo Controle de Aplicativo do Windows. Ele precisa de
`websocket-client` no venv (`pip install websocket-client`; dependência de
QA, fora do `requirements.txt` de produção). Sempre com a mesma conta de QA
(local, `qa-redesign-treino@local.invalid`, pk 1176), a mesma largura
(390 × 844) e o mesmo tema (claro), senão o depois não é comparável com o
antes.

    .venv/Scripts/python.exe scripts/qa/nav.py medir viewport 390 844
    .venv/Scripts/python.exe scripts/qa/nav.py medir open http://127.0.0.1:8000/
    .venv/Scripts/python.exe scripts/qa/nav.py medir eval "$(cat scripts/qa/medir.js)"

## O baseline

`docs/design-audit/baseline-home-390.json` é a Home (`/`) medida ANTES da
fundação de design, em `9430f78`. `config/test_medir_js.py` cobra que toda
chave que o script emite exista no baseline — acrescentou métrica ao
script, regrave o baseline no mesmo commit, com a data no campo `_medido_em`.

O que se compara: `sizes` (24 tamanhos de fonte distintos), `weights`
(14 pesos), `radii` (6 raios), `shadowed` (25 sombras), `bgs` (fundos) e
`btnKinds` (receitas de botão). A direção "Mesa & Ferro" promete menos de
cada um; o número é o que prova.

`pageH` é comparável só NA MESMA HORA e no mesmo estado: o cartão AGORA e
as refeições vencidas mudam com o relógio. O juiz 2 mediu 3 143 px; a
mesma conta restaurada (`restaurar_qa.py`: zero refeição, zero água, zero
série no dia) deu 4 067 px às 19h29 de 14/09 com a MESMA estrutura. Para
medir altura antes × depois, meça os dois no mesmo horário.
