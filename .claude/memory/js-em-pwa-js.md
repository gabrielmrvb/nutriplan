---
name: js-em-pwa-js
description: o JavaScript da página mora em static/js/pwa.js; app.js existe mas NÃO é servido
metadata:
  type: reference
---
`app_js_url` aponta para `pwa.js`. Código posto em `static/js/app.js`
passa em teste de endpoint e não roda no navegador — foi assim que a
marcação da lista de compras "funcionou" sem salvar nada. Ouvinte de
mudança vai delegado no `document`.

Fonte: CLAUDE.md:2191-2195
