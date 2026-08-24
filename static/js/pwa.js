/* Registro do service worker e assinatura das notificações.
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
})();
