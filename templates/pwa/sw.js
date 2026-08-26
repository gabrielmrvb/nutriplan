/* Service worker do NutriPlan.
 *
 * Estratégia por tipo de recurso:
 *
 *   navegação (HTML)     -> rede, com a tela de offline como plano B
 *   estático com ?v=hash -> cache primeiro (abre instantâneo, mesmo offline)
 *   estático sem versão  -> rede revalidando, com o cache como plano B
 *
 * A distinção pelo `?v=` é o ponto inteiro deste arquivo, então vale explicar.
 *
 * CSS e JS já ficaram em cache-first uma vez e deu errado de um jeito caro: o
 * HTML novo chegava pela rede e a folha de estilo continuava vindo do cache
 * antigo, então o app aparecia sem estilo — parecendo quebrado, não
 * desatualizado. A correção da época foi ir buscar CSS e JS na rede sempre.
 *
 * Isso deixou de ser necessário quando o endereço passou a carregar o hash do
 * conteúdo (`app.css?v=1a2b3c4d`, veja push/assets.py): cada versão do arquivo
 * tem uma URL própria, e o cache é indexado pela URL inteira, query incluída.
 * Conteúdo novo => URL nova => o cache não tem o que servir de errado, e busca
 * na rede sozinho. Servir do cache um arquivo cujo endereço promete um
 * conteúdo específico não é arriscado; é o uso correto do cache.
 *
 * O caminho sem versão continua revalidando, porque aí a URL não promete nada.
 */
const CACHE = "{{ cache_version }}";
/* As páginas ficam num cache SEPARADO, e a separação é de privacidade, não de
   organização: HTML autenticado carrega o nome, o peso e a dieta da pessoa.
   Num aparelho compartilhado, sair da conta precisa levar isso embora — e
   levar só isso, sem derrubar o cache de CSS e ícones que não tem nada
   pessoal. Quem apaga é o pwa.js, ao ver que ninguém está autenticado. */
const CACHE_PAGINAS = "{{ cache_version }}-paginas";
const VERSAO = "{{ asset_version }}";
const OFFLINE_URL = "{{ offline_url }}";
const SHELL = [OFFLINE_URL{% for asset in shell %}, "{{ asset }}"{% endfor %}];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

/* Joga fora o que sobrou de versões anteriores.
 *
 * São duas limpezas diferentes, e faltar qualquer uma faz o cache só crescer:
 *
 * 1. caches de gerações antigas (`nutriplan-v4` quando já estamos na v5);
 * 2. dentro do cache atual, os arquivos de builds passados. Cada deploy muda o
 *    `?v=` e cria um registro novo, e o antigo ficaria ali para sempre — numa
 *    máquina de desenvolvimento chegaram a nove pares de CSS e JS empilhados.
 */
function limpar() {
  const limpezaDeGeracoes = caches
    .keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))));

  const limpezaDeVersoes = caches.open(CACHE).then((cache) =>
    cache.keys().then((requests) =>
      Promise.all(
        requests
          .filter((request) => {
            const versao = new URL(request.url).searchParams.get("v");
            return versao !== null && versao !== VERSAO;
          })
          .map((request) => cache.delete(request))
      )
    )
  );

  return Promise.all([limpezaDeGeracoes, limpezaDeVersoes]);
}

self.addEventListener("activate", (event) => {
  event.waitUntil(limpar().then(() => self.clients.claim()));
});

/* Só entra no cache o que é estático e do próprio site. Guardar HTML de
 * usuário logado seria servir o dia de uma pessoa para outra no mesmo
 * dispositivo — e ainda mostraria dieta desatualizada depois de cada
 * marcação. */
function isCacheable(request) {
  const url = new URL(request.url);
  return url.origin === self.location.origin && url.pathname.startsWith("/static/");
}

/* Tem hash do conteúdo no endereço? Então este arquivo é imutável: o que essa
 * URL responde hoje é o que ela vai responder sempre. */
function isVersioned(request) {
  return new URL(request.url).searchParams.has("v");
}

/* Aparência e comportamento do app: precisam bater com o HTML que veio agora.
 * Uma folha de estilo velha com marcação nova não é "uma versão atrás", é uma
 * tela quebrada. */
function isAppCode(request) {
  return /\.(css|js)$/.test(new URL(request.url).pathname);
}

function store(request, response) {
  if (response.ok) {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  if (request.mode === "navigate") {
    /* Rede primeiro, e o que voltar fica guardado. Sem rede, a própria página
       de ontem é servida — o que muda o app de "não abre" para "abre com o
       dado de ontem", que é a diferença entre inútil e útil no metrô.

       A tela de offline continua existindo para o caso de nunca ter visitado
       aquela página. */
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copia = response.clone();
            caches.open(CACHE_PAGINAS).then((c) => c.put(request, copia));
          }
          return response;
        })
        .catch(() =>
          caches.match(request, { cacheName: CACHE_PAGINAS })
            .then((cached) => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

  if (!isCacheable(request)) return;

  if (isAppCode(request) && !isVersioned(request)) {
    // `cache: "no-cache"` obriga a revalidar com o servidor. Sem isso o
    // `fetch` daqui de dentro pode ser respondido pelo cache HTTP do próprio
    // navegador — que foi exatamente o que serviu CSS velho depois de o cache
    // do service worker já ter sido corrigido. Revalidar custa um 304.
    event.respondWith(
      fetch(new Request(request, { cache: "no-cache" }))
        .then((response) => store(request, response))
        .catch(() => caches.match(request))
    );
    return;
  }

  // Daqui para baixo: arquivo versionado, ícone ou imagem. Todos podem vir do
  // cache sem risco de servir algo diferente do que a URL promete — e é isso
  // que faz o app abrir instantâneo na segunda vez, inclusive sem internet.
  event.respondWith(
    caches.match(request).then(
      (cached) => cached || fetch(request).then((response) => store(request, response))
    )
  );
});

self.addEventListener("push", (event) => {
  let payload = { title: "NutriPlan", body: "Hora da sua refeição.", url: "/" };
  if (event.data) {
    try {
      payload = Object.assign(payload, event.data.json());
    } catch (e) {
      payload.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "{{ shell.2 }}",
      badge: "{{ shell.2 }}",
      tag: payload.tag || "nutriplan",
      data: { url: payload.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";

  // Se o app já está aberto, foca a janela em vez de abrir outra aba.
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});


/* Drenagem em segundo plano.
 *
 * Duplica a leitura da fila que o `fila.js` faz, e a duplicação é consciente:
 * é o preço de o reenvio funcionar com a aba fechada. A alternativa — acordar
 * um cliente para ele drenar — só ajuda quando existe cliente aberto, que é
 * quase o mesmo que o evento `online` já cobre.
 *
 * Não existe no Safari do iPhone. Lá o caminho é o `online` do `fila.js`, e é
 * por isso que ele é o mecanismo principal e este é o bônus.
 */
const FILA_BANCO = "nutriplan-fila";
const FILA_LOJA = "pendentes";

function abrirFila() {
  return new Promise((resolve, reject) => {
    const pedido = indexedDB.open(FILA_BANCO, 1);
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(pedido.error);
  });
}

function itensDaFila(db) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(FILA_LOJA, "readonly");
    const pedido = tx.objectStore(FILA_LOJA).getAll();
    pedido.onsuccess = () => resolve(pedido.result || []);
    pedido.onerror = () => reject(pedido.error);
  });
}

function removerDaFila(db, id) {
  return new Promise((resolve) => {
    const tx = db.transaction(FILA_LOJA, "readwrite");
    tx.objectStore(FILA_LOJA).delete(id);
    tx.oncomplete = resolve;
    tx.onerror = resolve;
  });
}

async function drenarFila() {
  let db;
  try {
    db = await abrirFila();
  } catch (e) {
    return;
  }
  const itens = await itensDaFila(db);
  for (const item of itens) {
    try {
      const resposta = await fetch(item.url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Requested-With": "fetch",
        },
        body: new URLSearchParams(item.dados),
      });
      /* 4xx sai da fila: reenviar não conserta conteúdo recusado, e manter
         faria a pessoa carregar para sempre algo que nunca vai passar. */
      if (resposta.ok || (resposta.status >= 400 && resposta.status < 500)) {
        await removerDaFila(db, item.op_id);
      }
    } catch (e) {
      /* Rede caiu de novo: fica para a próxima tentativa. */
      break;
    }
  }
  db.close();
}

self.addEventListener("sync", (event) => {
  if (event.tag === "nutriplan-fila") event.waitUntil(drenarFila());
});
