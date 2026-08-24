/* Service worker do NutriPlan.
 *
 * Estratégia por tipo de recurso:
 *
 *   navegação (HTML)  -> rede, com a tela de offline como plano B
 *   CSS e JS          -> rede, com o cache como plano B
 *   ícones e imagens  -> cache primeiro
 *
 * CSS e JS ficaram em cache-first até 24/08/2026 e isso deu errado de um jeito
 * caro: o HTML novo chegava pela rede e a folha de estilo continuava vindo do
 * cache antigo, então o app aparecia sem estilo — parecendo quebrado, não
 * desatualizado. Depender de alguém lembrar de trocar a versão do cache a cada
 * deploy é garantia de repetir isso.
 *
 * A troca custa uma requisição condicional por arquivo (o navegador manda
 * If-None-Match e o servidor responde 304 em alguns bytes), e mantém o app
 * abrindo offline, porque o cache continua sendo o plano B.
 */
const CACHE = "{{ cache_version }}";
const OFFLINE_URL = "{{ offline_url }}";
const SHELL = [OFFLINE_URL{% for asset in shell %}, "{{ asset }}"{% endfor %}];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  // Limpa versões antigas do cache — sem isso o disco do usuário só cresce.
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* Só entra no cache o que é estático e do próprio site. Guardar HTML de
 * usuário logado seria servir o dia de uma pessoa para outra no mesmo
 * dispositivo — e ainda mostraria dieta desatualizada depois de cada
 * marcação. */
function isCacheable(request) {
  const url = new URL(request.url);
  return url.origin === self.location.origin && url.pathname.startsWith("/static/");
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
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  if (!isCacheable(request)) return;

  if (isAppCode(request)) {
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

  // Ícone e imagem podem vir do cache sem risco: o conteúdo do arquivo não
  // muda, e é isso que faz o app abrir rápido.
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
