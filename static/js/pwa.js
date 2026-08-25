/* Instalação do app, registro do service worker e assinatura das notificações.
 *
 * Tudo aqui é opcional por construção: navegador sem suporte, permissão
 * negada ou chave VAPID ausente apenas escondem o botão. Nada disso pode
 * impedir o app de funcionar — notificação é acessório, dieta é o produto.
 */
(function () {
  "use strict";

  var button = document.querySelector("[data-push-toggle]");
  var status = document.querySelector("[data-push-status]");
  var supported =
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

  function say(text) {
    if (status) status.textContent = text;
  }

  function urlBase64ToUint8Array(base64String) {
    // A chave VAPID vem em base64url; a API do navegador quer bytes.
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var raw = window.atob(base64);
    return Uint8Array.from(raw.split("").map(function (c) {
      return c.charCodeAt(0);
    }));
  }

  function csrfToken() {
    var match = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return match ? match[2] : "";
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    });
  }

  instalacao();

  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.register("/sw.js").then(function (registration) {
    if (!button) return;
    if (!supported || !window.NUTRIPLAN_VAPID_KEY) {
      button.hidden = true;
      return;
    }

    registration.pushManager.getSubscription().then(function (subscription) {
      render(registration, subscription);
    });
  });

  function render(registration, subscription) {
    if (!button) return;
    button.hidden = false;
    if (subscription) {
      button.textContent = "Desativar lembretes";
      say("Você recebe um aviso 10 minutos antes de cada refeição.");
    } else {
      button.textContent = "Ativar lembretes das refeições";
      say("Um aviso 10 minutos antes de cada refeição, no celular.");
    }

    button.onclick = function () {
      button.disabled = true;
      var action = subscription ? disable(subscription) : enable(registration);
      action
        .then(function (next) {
          button.disabled = false;
          render(registration, next);
        })
        .catch(function () {
          button.disabled = false;
          say("Não deu para mudar os lembretes agora. Tente de novo.");
        });
    };
  }

  function enable(registration) {
    return Notification.requestPermission().then(function (permission) {
      if (permission !== "granted") {
        say("Permissão negada. Dá para liberar nas configurações do navegador.");
        return null;
      }
      return registration.pushManager
        .subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(window.NUTRIPLAN_VAPID_KEY),
        })
        .then(function (subscription) {
          return post("/push/inscrever/", subscription.toJSON()).then(function () {
            return subscription;
          });
        });
    });
  }

  function disable(subscription) {
    var endpoint = subscription.endpoint;
    return subscription.unsubscribe().then(function () {
      return post("/push/cancelar/", { endpoint: endpoint }).then(function () {
        return null;
      });
    });
  }


  /* ------------------------------------------------------------------ *
   * Convite de instalação
   * ------------------------------------------------------------------ */

  /* Android e desktop: o navegador avisa quando o site cumpre os requisitos
   * (manifest válido, service worker, HTTPS) e deixa a gente escolher a hora
   * de perguntar. iPhone: o Safari não dispara evento nenhum e não tem API de
   * instalação — a única saída é ensinar o caminho do menu Compartilhar.
   *
   * Em ambos, o convite só aparece para quem ainda não instalou. Repetir
   * "instale o app" para quem já instalou é o tipo de banner que faz a pessoa
   * ignorar todos os outros avisos do app.
   */
  function instalacao() {
    var banner = document.querySelector("[data-install]");
    if (!banner) return;

    var dica = banner.querySelector("[data-install-hint]");
    var instalar = banner.querySelector("[data-install-go]");
    var saidas = banner.querySelectorAll("[data-install-close]");
    var CHAVE = "nutriplan:convite-dispensado-em";
    var SETE_DIAS = 7 * 24 * 60 * 60 * 1000;
    var convite = null;

    function jaInstalado() {
      return (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true
      );
    }

    function ehIOS() {
      // iPadOS moderno se apresenta como Mac; o toque é o que o denuncia.
      var ua = window.navigator.userAgent;
      return /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && "ontouchend" in document);
    }

    /* Guarda QUANDO foi dispensado, não apenas QUE foi.
     *
     * A primeira versão guardava um "1" e o convite nunca mais voltava. Some
     * cedo demais: quem fecha na primeira visita, antes de saber se o app
     * presta, perde a oferta para sempre. Sete dias é tempo de a pessoa
     * decidir se voltou a usar — e curto o bastante para o convite ainda
     * significar alguma coisa quando reaparecer. */
    function dispensadoRecentemente() {
      try {
        var quando = parseInt(window.localStorage.getItem(CHAVE), 10);
        if (!quando) return false;
        return Date.now() - quando < SETE_DIAS;
      } catch (e) {
        // Modo privado pode recusar o armazenamento. Sem memória, o convite
        // reaparece na próxima visita — chato, mas melhor que quebrar.
        return false;
      }
    }

    /* Esconder não basta: a barra é `position: fixed`, então não ocupa espaço
     * no layout e pousa em cima do rodapé da página. A classe no `body` é o
     * que faz a página reservar a altura dela — e some junto com o convite. */
    function esconder() {
      banner.hidden = true;
      document.body.classList.remove("tem-convite");
    }

    function dispensar() {
      esconder();
      try {
        window.localStorage.setItem(CHAVE, String(Date.now()));
      } catch (e) {}
    }

    function mostrar() {
      if (jaInstalado() || dispensadoRecentemente()) return;
      banner.hidden = false;
      document.body.classList.add("tem-convite");
    }

    for (var i = 0; i < saidas.length; i++) saidas[i].onclick = dispensar;

    // Esc fecha, como em qualquer diálogo.
    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && !banner.hidden) dispensar();
    });

    window.addEventListener("beforeinstallprompt", function (event) {
      // Segurar o evento é o que troca o banner do navegador (que aparece na
      // hora que ele quiser) por este, que aparece dentro do layout do app.
      event.preventDefault();
      convite = event;
      mostrar();
    });

    window.addEventListener("appinstalled", dispensar);

    if (instalar) {
      instalar.onclick = function () {
        if (!convite) return;
        convite.prompt();
        convite.userChoice.then(function (escolha) {
          // Aceitou ou recusou, o convite sai da tela: o evento é de uso único
          // e insistir na mesma visita é o que faz banner virar praga.
          dispensar();
          convite = null;
        });
      };
    }

    if (ehIOS() && !jaInstalado()) {
      if (dica) {
        dica.textContent = "No Safari: toque em Compartilhar e depois em \u201cAdicionar \u00e0 Tela de In\u00edcio\u201d.";
      }
      // Sem `beforeinstallprompt` no iOS, o botão "Instalar" não teria o que
      // fazer — um botão que não faz nada é pior que botão nenhum.
      if (instalar) instalar.hidden = true;
      mostrar();
    }
  }

})();
