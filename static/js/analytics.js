/* Analytics de produto — o cliente.
 *
 * O que ele é, e o que ele DELIBERADAMENTE não é:
 *
 * NÃO é a fila offline (`fila.js`). Aquela guarda dado do usuário — água,
 * refeição — com garantia de entrega única e ordem, num IndexedDB. Perder uma
 * marcação de água é perder o dado do dia. Analytics é o contrário: fogo e
 * esquece, tolerante a perda, alto volume. Misturar os dois daria à água a
 * fragilidade do analytics ou ao analytics o peso da água. São arquivos
 * separados de propósito.
 *
 * O buffer vive na memória e faz backup em `localStorage` só para sobreviver a
 * um fechamento sem rede. A drenagem normal é `fetch` (confirma e limpa); a de
 * saída da página é `sendBeacon` (dispara e esquece, e limpa otimista — beacon
 * não devolve resposta, e analytics perdido é barato).
 *
 * NÃO envia PII. As propriedades vêm de quem chama `track`, e a disciplina de
 * não mandar e-mail/nome/peso exato é da instrumentação (bloco 2) e do catálogo
 * do servidor, que recusa nome fora da lista.
 *
 * NÃO rastreia a própria gerência: /gestao/ e /admin/ ficam de fora, senão o
 * staff olhando o painel viraria "uso do produto".
 */
(function () {
  "use strict";

  var CFG = window.NUTRIPLAN_ANALYTICS || {};
  var ENDPOINT = CFG.endpoint || "/analytics/e/";
  var VERSAO = CFG.app_version || "";

  var rota = location.pathname;
  // A gerência e o admin não são "uso do produto".
  if (rota.indexOf("/gestao/") === 0 || rota.indexOf("/admin/") === 0) {
    return;
  }

  var CHAVE_BUFFER = "np_ev";
  var CHAVE_SESSAO = "np_sess";
  var LIMITE_BUFFER = 20; // drena ao chegar aqui
  var INTERVALO = 15000; // e a cada 15 s
  var MAX_ERROS = 5; // erro.js por carga de página

  var buffer = [];
  var erros = 0;
  var timer = null;

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "x" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function ler(chave) {
    try {
      return JSON.parse(localStorage.getItem(chave) || "null");
    } catch (e) {
      return null;
    }
  }
  function guardar(chave, valor) {
    try {
      localStorage.setItem(chave, JSON.stringify(valor));
    } catch (e) {
      /* modo privado, cota — segue sem persistência */
    }
  }

  function sessao() {
    var s;
    try {
      s = sessionStorage.getItem(CHAVE_SESSAO);
      if (!s) {
        s = uuid();
        sessionStorage.setItem(CHAVE_SESSAO, s);
      }
    } catch (e) {
      s = s || uuid();
    }
    return s;
  }

  function dispositivo(largura) {
    if (largura < 768) return "mobile";
    if (largura < 1024) return "tablet";
    return "desktop";
  }

  function contexto() {
    var largura = window.innerWidth || 0;
    var escuro = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
    var standalone =
      (window.matchMedia && matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
    return {
      session_id: sessao(),
      device: dispositivo(largura),
      width: largura,
      theme: escuro ? "ferro" : "papel",
      pwa: !!standalone,
      app_version: VERSAO,
    };
  }

  /* A superfície pública: track(nome, props). */
  function track(nome, props) {
    buffer.push({
      name: nome,
      props: props || {},
      route: location.pathname,
      referrer: buffer.length === 0 ? document.referrer || "" : "",
      ts: Date.now(),
    });
    guardar(CHAVE_BUFFER, buffer);
    if (buffer.length >= LIMITE_BUFFER) drenar();
    else agendar();
  }

  function agendar() {
    if (timer) return;
    timer = setTimeout(function () {
      timer = null;
      drenar();
    }, INTERVALO);
  }

  function corpo(eventos) {
    var c = contexto();
    c.events = eventos;
    return JSON.stringify(c);
  }

  /* Drenagem normal: fetch, confirma e limpa. Falhou (sem rede)? Devolve ao
   * buffer e persiste — a próxima tentativa (intervalo, ou evento `online`)
   * reenvia. */
  function drenar() {
    if (!buffer.length) return;
    if (navigator.onLine === false) {
      guardar(CHAVE_BUFFER, buffer);
      return;
    }
    var lote = buffer.splice(0, 50);
    fetch(ENDPOINT, {
      method: "POST",
      body: corpo(lote),
      keepalive: true,
      credentials: "same-origin",
      headers: { "Content-Type": "text/plain" },
    })
      .then(function (r) {
        if (!r.ok && r.status >= 500) throw new Error("servidor");
        guardar(CHAVE_BUFFER, buffer); // sucesso: o que sobrou é o novo buffer
      })
      .catch(function () {
        buffer = lote.concat(buffer); // devolve para reenviar
        guardar(CHAVE_BUFFER, buffer);
      });
  }

  /* Saída da página: sendBeacon dispara e esquece, e limpamos otimista. Se o
   * beacon falhar (raro), perdemos aqueles eventos — barato. O que não pode é
   * duplicar com um fetch posterior, e limpar evita isso. */
  function drenarNaSaida() {
    if (!buffer.length) return;
    var lote = buffer.splice(0);
    guardar(CHAVE_BUFFER, buffer);
    try {
      var blob = new Blob([corpo(lote)], { type: "text/plain" });
      var ok = navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, blob);
      if (!ok) {
        buffer = lote.concat(buffer);
        guardar(CHAVE_BUFFER, buffer);
      }
    } catch (e) {
      buffer = lote.concat(buffer);
      guardar(CHAVE_BUFFER, buffer);
    }
  }

  /* --- Eventos automáticos --- */

  function automaticos() {
    track("tela.vista", {});

    // TTI aproximado: quando o DOM ficou interativo (navigation timing).
    try {
      var nav = performance.getEntriesByType("navigation")[0];
      if (nav && nav.domInteractive) {
        track("tela.interativa", { ms: Math.round(nav.domInteractive) });
      }
    } catch (e) {
      /* sem navigation timing, sem TTI */
    }

    // Erro de JS, com teto por carga de página.
    window.addEventListener("error", function (ev) {
      if (erros >= MAX_ERROS) return;
      erros += 1;
      var msg = (ev && ev.message ? String(ev.message) : "erro").slice(0, 200);
      track("erro.js", { mensagem: msg, rota: location.pathname });
    });

    // Instalação da PWA.
    window.addEventListener("appinstalled", function () {
      track("pwa.instalada", {});
      drenar();
    });

    // EVENTO AO ABRIR: SÓ o que o template marcar com `data-evento-ao-abrir`
    // (24/09/2026). Ele existe para o primeiro degrau do funil de entrada — a
    // landing —, e nasceu no CLIENTE depois de a primeira versão ter nascido
    // no servidor e quebrar uma garantia: `/` anônima é a página mais barata
    // do app, com ZERO consulta (`plans/test_landing.py`), porque é ela que o
    // visitante novo vê com o Render dormindo e o Neon à parte. Um INSERT ali
    // custaria o banco em toda visita, inclusive as de robô.
    //
    // Não é `tela.vista` com filtro de rota: `/` é a landing para quem não
    // entrou e o app para quem entrou, e o mesmo caminho contaria os dois.
    var aoAbrir = document.querySelector("[data-evento-ao-abrir]");
    if (aoAbrir) track(aoAbrir.getAttribute("data-evento-ao-abrir"), {});

    // Cliques genéricos: SÓ o que o template marcar com data-evento.
    document.addEventListener(
      "click",
      function (ev) {
        var alvo = ev.target && ev.target.closest && ev.target.closest("[data-evento]");
        if (!alvo) return;
        track(alvo.getAttribute("data-evento"), {});
      },
      true
    );
  }

  /* --- Ciclo de vida --- */

  // Recupera o que ficou de uma sessão anterior sem rede.
  var pendentes = ler(CHAVE_BUFFER);
  if (pendentes && pendentes.length) {
    buffer = pendentes.concat(buffer);
  }

  window.addEventListener("online", drenar);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") drenarNaSaida();
  });
  window.addEventListener("pagehide", drenarNaSaida);

  automaticos();
  drenar(); // manda a tela.vista e o que tiver pendente

  // Deixa o produto disparar eventos de negócio.
  window.npTrack = track;
})();
