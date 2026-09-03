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
    caches
      .open(CACHE)
      /* `credentials: "omit"` e o coracao disto.
       *
       * `addAll` com URL crua manda cookie (o padrao same-origin). A tela de
       * offline e renderizada pelo Django, entao ela vinha AUTENTICADA: o HTML
       * guardado no cache de estaticos trazia `data-usuario` com a chave
       * primaria de quem instalou o app, `data-autenticado="1"` e as mensagens
       * pendentes daquela sessao — consumidas ali dentro e congeladas para
       * sempre.
       *
       * O cache de estaticos NAO e limpo no logout, de proposito: CSS e icone
       * nao tem nada pessoal. Com o shell autenticado la dentro, essa premissa
       * deixava de ser verdade, e a proxima pessoa a usar o aparelho recebia o
       * identificador da anterior — que e exatamente o que `fila.js` le para
       * decidir de quem e cada operacao pendente.
       *
       * Medido no navegador: `data-usuario="717"` servido para a sessao 725. */
      .then((cache) =>
        cache.addAll(SHELL.map((url) => new Request(url, { credentials: "omit" })))
      )
      .then(() => self.skipWaiting())
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

/* A REGRA, no lugar de uma lista de endereços.
 *
 * O contrato do painel diz: `/admin/` e `/gestao/` nunca podem virar página
 * guardada, e "corrigir com regra estrutural, não lista frágil de páginas uma
 * por uma quando possível". `ehTelaOperacional` é a lista — ela impede que
 * essas duas cheguem sequer a passar pelo worker, e continua valendo. O que
 * faltava era a regra: até aqui NADA consultava a resposta antes de guardá-la,
 * então qualquer tela privada que não estivesse na lista entrava no cache.
 *
 * O servidor já diz quais são. `never_cache` responde
 * `no-cache, no-store, must-revalidate, private`, e `no-store` é literalmente
 * "não persista isto". Passar a obedecer significa que a próxima view marcada
 * com `never_cache` fica protegida sem ninguém lembrar de editar este arquivo
 * — que é a diferença entre uma regra e uma lista.
 *
 * `private` NÃO entra na condição, e é decisão. Ele significa "cache
 * compartilhado não pode guardar"; o cache de um service worker é do perfil do
 * navegador daquela pessoa, e é o mesmo cache que faz a dieta abrir no metrô.
 * Tratar `private` como proibição desligaria o app inteiro no dia em que
 * alguém marcasse uma tela comum com ele.
 *
 * As telas do app não mandam `Cache-Control` nenhum — este projeto não tem
 * middleware de cache —, então para elas nada muda. */
function podeGuardar(response) {
  /* Diretiva por diretiva, e nao uma expressao regular.
   *
   * A primeira versao usava uma regex com limite de palavra, e o escape
   * virou CARACTERE DE CONTROLE no arquivo: a expressao passou a procurar
   * 0x08 seguido de "no-store" seguido de 0x08, que nao casa com nada. A
   * funcao devolveu "pode guardar" para a tela de entrar, que manda
   * `no-store`. E os testes que liam o TEXTO do worker continuaram verdes,
   * porque a string "no-store" estava la — quem pegou foi o navegador,
   * executando a funcao contra uma resposta de verdade.
   *
   * Separar por virgula compara o TOKEN, e nao um pedaco de texto: casa
   * com "private, no-store", nao casaria com um hipotetico "no-store-x", e
   * nao tem escape nenhum que possa dar errado no caminho. */
  const diretivas = (response.headers.get("Cache-Control") || "")
    .toLowerCase()
    .split(",")
    .map(function (d) { return d.trim(); });
  return response.ok && diretivas.indexOf("no-store") === -1;
}

function store(request, response) {
  if (podeGuardar(response)) {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
  }
  return response;
}

/* As telas operacionais NÃO passam pelo service worker.
 *
 * O motivo não é offline — é o cache. A estratégia de navegação guarda uma
 * cópia de cada página visitada em `CACHE_PAGINAS`, e essas duas mostram dado
 * de OUTRAS pessoas: a tela de detalhe de uma conta traz e-mail, perfil e
 * pesagens; a lista do painel de gestão traz o e-mail de todas. Guardadas no
 * cache, elas sobrevivem ao logout e ficam legíveis para qualquer coisa com
 * acesso ao perfil do navegador.
 *
 * E nenhuma delas precisa funcionar offline: não fazem parte do app que a
 * pessoa instala. Deixar passar direto é a resposta para as duas coisas.
 */
function ehTelaOperacional(url) {
  return (
    url.origin === self.location.origin &&
    (url.pathname.startsWith("/admin/") || url.pathname.startsWith("/gestao/"))
  );
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (ehTelaOperacional(new URL(request.url))) return;

  if (request.mode === "navigate") {
    /* Rede primeiro, com PACIÊNCIA LIMITADA.
     *
     * Rede primeiro sozinha tem um buraco que não aparece no escritório: rede
     * de academia raramente "cai", ela demora. O `fetch` não rejeita, ele fica
     * pendurado — e o app mostra tela branca por dez, quinze segundos com uma
     * cópia perfeitamente boa da página guardada ao lado.
     *
     * Passados três segundos, serve o cache e deixa a rede terminar em
     * segundo plano: o que ela trouxer entra no cache para a próxima abertura.
     * Quem tem rede boa nunca vê a diferença — a resposta chega bem antes.
     *
     * Não é stale-while-revalidate: SWR serviria o cache PRIMEIRO, sempre, e
     * numa tela que mostra a série que a pessoa acabou de registrar isso é
     * mostrar o estado anterior de propósito. O limite de paciência dá a
     * velocidade sem a mentira.
     *
     * A tela de offline continua existindo para quem nunca visitou a página. */
    const PACIENCIA_MS = 3000;

    const doCache = () =>
      caches.match(request, { cacheName: CACHE_PAGINAS })
        .then((cached) => cached || caches.match(OFFLINE_URL));

    const daRede = fetch(request)
      .then((response) => {
        // `podeGuardar` e não `response.ok`: uma página que o servidor marcou
        // `no-store` responde 200 e mesmo assim não pode ficar guardada.
        if (podeGuardar(response)) {
          const copia = response.clone();
          caches.open(CACHE_PAGINAS).then((c) => c.put(request, copia));
        }
        return response;
      });

    event.respondWith(
      new Promise((resolve) => {
        let respondido = false;
        const responder = (r) => {
          if (respondido || !r) return;
          respondido = true;
          resolve(r);
        };

        const relogio = setTimeout(
          () => doCache().then(responder),
          PACIENCIA_MS
        );

        daRede
          .then((r) => { clearTimeout(relogio); responder(r); })
          .catch(() => { clearTimeout(relogio); doCache().then(responder); });
      })
    );

    /* A rede continua correndo mesmo depois de a página do cache ter sido
       entregue — é ela que atualiza o cache para a próxima abertura. Sem o
       `waitUntil`, o navegador pode encerrar o worker antes de ela terminar. */
    event.waitUntil(daRede.catch(() => {}));
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

/* PRECISA ser o mesmo número de `static/js/fila.js`. Um teste compara os dois
 * arquivos, porque o dia em que só um subir, o outro leva `VersionError` e
 * para de drenar a fila sem dizer nada. */
const FILA_VERSAO = 2;

/* A ausência de `onupgradeneeded` aqui foi o defeito: este service worker
 * abria o banco na versão 1 sem handler nenhum e, quando chegava PRIMEIRO — o
 * que acontece num evento `sync` —, o IndexedDB criava `nutriplan-fila` COM
 * ZERO STORES. Dali em diante `fila.js` encontrava um banco v1 já existente,
 * seu `onupgradeneeded` nunca disparava, e toda gravação offline morria com
 * `NotFoundError`. Permanentemente, porque a versão nunca subia.
 *
 * Agora os dois lados sabem criar a store. Quem abrir primeiro deixa o banco
 * pronto para o outro. */
function abrirFila() {
  return new Promise((resolve, reject) => {
    const pedido = indexedDB.open(FILA_BANCO, FILA_VERSAO);
    pedido.onupgradeneeded = () => {
      const db = pedido.result;
      if (!db.objectStoreNames.contains(FILA_LOJA)) {
        db.createObjectStore(FILA_LOJA, { keyPath: "op_id" });
      }
    };
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
  /* A leitura entrou no MESMO try da abertura, e não é detalhe: `itensDaFila`
   * abre uma transação, e era ela que estourava `NotFoundError` quando o banco
   * estava sem a store. Fora do try, isso virava rejeição não tratada dentro
   * do service worker — invisível para quem estava usando o app. */
  /* `db` é declarado AQUI, e não dentro do `try`. Com `const db` lá dentro
   * ele fica preso ao bloco: `removerDaFila(db, ...)` lançava `ReferenceError`
   * que o `catch` do laço engolia — nenhum item saía da fila — e o `db.close()`
   * do fim lançava solto, rejeitando `drenarFila()`. Como quem chama é
   * `event.waitUntil`, o Background Sync lia isso como falha e REAGENDAVA:
   * gravava, não removia, e tentava de novo. */
  let db;
  let itens;
  try {
    db = await abrirFila();
    itens = await itensDaFila(db);
  } catch (e) {
    return;
  }
  for (const item of itens) {
    try {
      /* O worker NÃO TEM DOM: não há como ele saber quem está logado. O que
         ele tem é o dono gravado no próprio item, e é isso que ele declara ao
         servidor — que compara com a sessão antes de mudar qualquer coisa.

         Este caminho é o mais perigoso da fila: roda em evento `sync`,
         possivelmente sem nenhuma aba aberta, e nenhuma correção do lado da
         página o alcança. Item sem dono não recebe o cabeçalho, e o servidor
         recusa — é a quarentena chegando aqui também. */
      const cabecalhos = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "fetch",
        "X-NutriPlan-Replay": "1",
      };
      if (item.dono) cabecalhos["X-NutriPlan-Dono"] = item.dono;

      const resposta = await fetch(item.url, {
        method: "POST",
        credentials: "same-origin",
        headers: cabecalhos,
        body: new URLSearchParams(item.dados),
        /* Sem seguir redirect: o 302 para o login terminaria numa página 200
           que a regra abaixo leria como sucesso. */
        redirect: "manual",
      });
      /* O worker NÃO renova o CSRF, e isso é decisão.
         Ele não tem DOM nem acesso a `document.cookie`, e buscar o token
         exigiria um endpoint novo só para isso. Não precisa: com o token
         velho o servidor responde de forma preservável, o item fica, e a
         próxima abertura do app sincroniza pelo `fila.js`, que tem o token
         atual. O worker adianta o que dá e não perde nada.

         `continue` e não `break`: um item de outra pessoa, ou com token
         velho, não pode travar a fila inteira e impedir que o item de quem
         ESTÁ logado sincronize. */
      if (resposta.type === "opaqueredirect") continue;
      if (resposta.status === 401 || resposta.status === 403) continue;
      if (resposta.status >= 500) continue;
      if (resposta.ok || (resposta.status >= 400 && resposta.status < 500)) {
        await removerDaFila(db, item.op_id);
      }
    } catch (e) {
      /* Rede caiu: este item fica para a próxima. `continue` e não `break` —
         um item que falha não pode impedir os outros de tentarem. */
      continue;
    }
  }
  /* Fechar não pode derrubar o `waitUntil`: uma rejeição aqui vira sync
   * falhado e reagendamento, por um erro que não impede nada. */
  try {
    db.close();
  } catch (e) {
    /* já fechado, ou o banco sumiu debaixo do worker */
  }
}

self.addEventListener("sync", (event) => {
  if (event.tag === "nutriplan-fila") event.waitUntil(drenarFila());
});
