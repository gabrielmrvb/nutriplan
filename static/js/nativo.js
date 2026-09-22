/* O que só existe DENTRO do app instalado (a casca Capacitor, `nativo/`).
 *
 * Carrega em toda tela, mas sai na primeira linha quando o WebView não é a
 * casca: no navegador este arquivo não faz nada. Três coisas:
 *
 *   1. LOGIN NATIVO — o Google recusa OAuth em WebView, então o SDK do
 *      aparelho devolve um `id_token` e o servidor o verifica
 *      (`/conta/entrar/nativo/`). Apple só no iPhone.
 *   2. PUSH NATIVO — o app não tem Web Push; o token do FCM é registrado em
 *      `/push/nativo/registrar/`, e o mesmo cartão "Lembretes" da Home passa
 *      a ligar/desligar isso. Tocar na notificação abre a URL que veio nela.
 *   3. SAÚDE DO APARELHO — Apple Saúde / Health Connect: a pessoa toca em
 *      "Importar do aparelho" e o que for lido vai para
 *      `/treino/corridas/aparelho/` e `/conta/peso/aparelho/`.
 *
 * Nada aqui é obrigatório: plugin ausente, permissão negada ou servidor fora
 * apenas escondem o controle ou mostram uma frase. O app funciona sem.
 */
(function () {
  "use strict";

  var Cap = window.Capacitor;
  if (!Cap || !Cap.isNativePlatform || !Cap.isNativePlatform()) return;

  var plugins = Cap.Plugins || {};
  var plataforma = Cap.getPlatform();
  var DIAS_DE_IMPORTACAO = 30;

  function csrf() {
    var m = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return m ? m[2] : "";
  }

  function postar(url, corpo, comoJson) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: comoJson
        ? { "Content-Type": "application/json", "X-CSRFToken": csrf() }
        : { "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf() },
      body: comoJson ? JSON.stringify(corpo) : new URLSearchParams(corpo).toString(),
    });
  }

  /* ------------------------------------------------------------------ *
   * 1. Login nativo (Google nas duas plataformas, Apple no iPhone)
   * ------------------------------------------------------------------ */
  function login() {
    var botoes = document.querySelectorAll("[data-login-nativo]");
    if (!botoes.length || !plugins.SocialLogin) return;
    var erro = document.querySelector("[data-login-nativo-erro]");
    var config = window.NUTRIPLAN_LOGIN_NATIVO || {};

    function avisar(texto) {
      if (!erro) return;
      erro.textContent = texto;
      erro.hidden = !texto;
    }

    var pronto = plugins.SocialLogin.initialize({
      google: config.googleWebClientId
        ? { webClientId: config.googleWebClientId, iOSClientId: config.googleIosClientId, iOSServerClientId: config.googleWebClientId }
        : undefined,
      apple: plataforma === "ios" ? {} : undefined,
    }).catch(function () { return null; });

    botoes.forEach(function (botao) {
      botao.addEventListener("click", function () {
        var provedor = botao.getAttribute("data-login-nativo");
        botao.disabled = true;
        avisar("");
        pronto
          .then(function () {
            return plugins.SocialLogin.login({
              provider: provedor,
              options: provedor === "google" ? { scopes: ["email", "profile"] } : { scopes: ["email", "name"] },
            });
          })
          .then(function (resposta) {
            var r = (resposta && resposta.result) || {};
            var token = (r.idToken) || (r.identityToken) || (r.profile && r.profile.identityToken);
            if (!token) throw new Error("sem id_token");
            var nome = r.profile ? [r.profile.givenName, r.profile.familyName].filter(Boolean).join(" ") : "";
            return postar("/conta/entrar/nativo/", { provedor: provedor, id_token: token, nome: nome }, false);
          })
          .then(function (resposta) {
            if (!resposta.ok) throw new Error("recusado");
            /* O servidor responde o redirect do allauth; `fetch` o segue e
             * `resposta.url` é onde ele parou (onboarding ou Home). */
            window.location.href = resposta.url || "/";
          })
          .catch(function (e) {
            botao.disabled = false;
            /* Cancelar não é erro: a pessoa fechou a folha do sistema. */
            var cancelou = e && /cancel/i.test(e.message || "");
            avisar(cancelou ? "" : "Não deu para entrar agora. Tente de novo ou use e-mail e senha.");
          });
      });
    });
  }

  /* ------------------------------------------------------------------ *
   * 2. Push nativo (FCM; no iPhone o FCM fala com o APNs)
   * ------------------------------------------------------------------ */
  function push() {
    var botao = document.querySelector("[data-push-toggle]");
    var status = document.querySelector("[data-push-status]");
    var FCM = plugins.FirebaseMessaging;
    if (!FCM) return;

    /* O cartão da Home é o mesmo; quem manda nele aqui é este arquivo, e
     * não o caminho Web Push do `pwa.js` (que não existe no WebView). */
    window.NUTRIPLAN_PUSH_NATIVO = true;

    FCM.addListener("notificationActionPerformed", function (evento) {
      var url = evento && evento.notification && evento.notification.data && evento.notification.data.url;
      if (url) window.location.href = url;
    });

    function dizer(texto) { if (status) status.textContent = texto; }

    function guardado() {
      try { return window.localStorage.getItem("nutriplan_fcm_token") || ""; } catch (e) { return ""; }
    }
    function guardar(token) {
      try { token ? window.localStorage.setItem("nutriplan_fcm_token", token) : window.localStorage.removeItem("nutriplan_fcm_token"); } catch (e) {}
    }

    function desenhar(ligado) {
      if (!botao) return;
      botao.hidden = false;
      botao.textContent = ligado ? "Desativar lembretes" : "Ativar lembretes das refeições";
      dizer(ligado ? "Você recebe um aviso até 20 minutos antes de cada refeição."
                   : "Um aviso até 20 minutos antes de cada refeição, neste aparelho.");
    }

    desenhar(!!guardado());

    if (botao) {
      botao.addEventListener("click", function () {
        botao.disabled = true;
        var ligado = !!guardado();
        var acao = ligado
          ? postar("/push/nativo/remover/", { token: guardado() }, true).then(function () { guardar(""); return false; })
          : FCM.requestPermissions()
              .then(function (p) {
                if (p.receive !== "granted") throw new Error("negada");
                return FCM.getToken();
              })
              .then(function (r) {
                return postar("/push/nativo/registrar/", { token: r.token, plataforma: plataforma }, true).then(function (resposta) {
                  if (!resposta.ok) throw new Error("servidor");
                  guardar(r.token);
                  return true;
                });
              });
        acao
          .then(function (ligadoAgora) { botao.disabled = false; desenhar(ligadoAgora); })
          .catch(function (e) {
            botao.disabled = false;
            desenhar(!!guardado());
            if (e && e.message === "negada") {
              dizer("Permissão negada. Dá para liberar nas configurações do aparelho.");
            } else {
              dizer("Não deu para mudar os lembretes agora. Tente de novo.");
            }
          });
      });
    }

    /* O token pode ser trocado pelo Firebase a qualquer momento. */
    FCM.addListener("tokenReceived", function (evento) {
      if (!evento || !evento.token || !guardado()) return;
      postar("/push/nativo/registrar/", { token: evento.token, plataforma: plataforma }, true).then(function () { guardar(evento.token); });
    });
  }

  /* ------------------------------------------------------------------ *
   * 3. Saúde do aparelho (Apple Saúde / Health Connect)
   * ------------------------------------------------------------------ */
  function saude() {
    var botao = document.querySelector("[data-saude-importar]");
    var status = document.querySelector("[data-saude-status]");
    var Health = plugins.HealthPlugin;
    if (!botao) return;
    if (!Health) { botao.hidden = true; return; }

    function dizer(texto) { if (status) { status.textContent = texto; status.hidden = !texto; } }

    Health.isHealthAvailable().then(function (r) {
      botao.hidden = !(r && r.available);
      if (!r || !r.available) {
        dizer(plataforma === "android"
          ? "Este aparelho não tem o Health Connect instalado."
          : "Este aparelho não tem o app Saúde.");
      }
    }).catch(function () { botao.hidden = true; });

    botao.addEventListener("click", function () {
      botao.disabled = true;
      dizer("Lendo do aparelho…");
      var desde = new Date(Date.now() - DIAS_DE_IMPORTACAO * 86400000).toISOString();
      var ate = new Date().toISOString();
      Health.requestHealthPermissions({ permissions: ["READ_WORKOUTS", "READ_WEIGHT", "READ_DISTANCE"] })
        .then(function () {
          return Promise.all([
            Health.queryWorkouts({ startDate: desde, endDate: ate, includeHeartRate: false, includeRoute: false, includeSteps: false })
              .catch(function () { return { workouts: [] }; }),
            Health.queryRecords({ startDate: desde, endDate: ate, dataType: "weight" })
              .catch(function () { return { records: [] }; }),
          ]);
        })
        .then(function (partes) {
          var corridas = (partes[0].workouts || [])
            .filter(function (w) { return /run/i.test(w.workoutType || ""); })
            .map(function (w) {
              return {
                id: String(w.id || (w.startDate + "-" + w.duration)),
                comecou_em: w.startDate,
                terminou_em: w.endDate,
                distancia_m: Math.round(w.distance || 0),
                duracao_s: Math.round(w.duration || 0),
                tipo: "running",
                fonte: w.sourceName || "",
              };
            });
          var pesagens = (partes[1].records || []).map(function (r) {
            return { data: String(r.startDate).slice(0, 10), peso_kg: r.value };
          });
          return Promise.all([
            corridas.length ? postar("/treino/corridas/aparelho/", { corridas: corridas }, true).then(function (r) { return r.json(); }) : { importadas: 0 },
            pesagens.length ? postar("/conta/peso/aparelho/", { pesagens: pesagens }, true).then(function (r) { return r.json(); }) : { gravadas: 0 },
          ]);
        })
        .then(function (r) {
          botao.disabled = false;
          var c = r[0].importadas || 0;
          var p = r[1].gravadas || 0;
          if (!c && !p) {
            dizer("Nada novo para importar nos últimos " + DIAS_DE_IMPORTACAO + " dias.");
            return;
          }
          dizer("Importado: " + c + " corrida" + (c === 1 ? "" : "s") + " e " + p + " pesagem" + (p === 1 ? "" : "s") + ".");
        })
        .catch(function () {
          botao.disabled = false;
          dizer("Não deu para ler do aparelho. Confira as permissões de saúde nas configurações.");
        });
    });
  }

  login();
  push();
  saude();
})();
