/* A CONVERSA COM O DJANGO. So este arquivo sabe o formato da API.
 *
 * A regra da fila, que veio do contrato ja publicado em `docs/api-v1.md` e nao
 * foi inventada aqui:
 *
 *   2xx  -> apaga o registro local
 *   409  -> apaga o registro local E reporta. Reenviar nao muda nada
 *   5xx  -> mantem e tenta depois
 *   rede -> mantem e tenta depois
 *
 * O 409 e o unico que costuma ser implementado errado. Ele significa "este
 * `op_id` ja existe com OUTRO conteudo" — e insistir e garantia de nunca
 * esvaziar a fila. Por isso ele apaga: o servidor ja decidiu, e o primeiro
 * envio venceu.
 */
(function (global) {
  "use strict";

  var BASE = "https://nutriplan-xxfn.onrender.com";
  var CHAVE_TOKEN = "token_do_app";
  var Prefs = null;
  try {
    Prefs =
      (global.Capacitor &&
        global.Capacitor.Plugins &&
        global.Capacitor.Plugins.Preferences) ||
      null;
  } catch (e) {
    Prefs = null;
  }

  function guardarToken(t) {
    if (Prefs) {
      return Prefs.set({ key: CHAVE_TOKEN, value: t });
    }
    global.localStorage.setItem(CHAVE_TOKEN, t);
    return Promise.resolve();
  }

  function lerToken() {
    if (Prefs) {
      return Prefs.get({ key: CHAVE_TOKEN }).then(function (r) {
        return r ? r.value : null;
      });
    }
    return Promise.resolve(global.localStorage.getItem(CHAVE_TOKEN));
  }

  function entrar(email, senha) {
    return fetch(BASE + "/api/v1/token/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email, senha: senha })
    })
      .then(function (r) {
        return r.json().then(function (corpo) {
          return { status: r.status, corpo: corpo };
        });
      })
      .then(function (r) {
        if (r.status !== 200) {
          /* A recusa e byte a byte igual exista o e-mail ou nao — e assim que
           * o servidor foi escrito, e repetir a mensagem dele aqui mantem a
           * propriedade. Nao invente "usuario nao encontrado". */
          throw new Error(r.corpo.erro || "nao foi possivel entrar");
        }
        return guardarToken(r.corpo.token).then(function () {
          return r.corpo.usuario;
        });
      });
  }

  /* Envia a corrida. Devolve `{acao: "apagar"|"manter", ...}` — a decisao da
   * fila sai daqui, e nao do chamador, para que a regra fique num lugar so. */
  function sincronizar(corrida) {
    return lerToken().then(function (token) {
      if (!token) {
        return { acao: "manter", motivo: "sem token" };
      }
      var corpo = {
        op_id: corrida.opId,
        comecou_em: corrida.comecouEm,
        terminou_em: new Date().toISOString(),
        duracao_s: Math.round(
          (Date.now() - new Date(corrida.comecouEm).getTime()) / 1000
        ),
        /* Os pontos vao CRUS. O servidor recalcula e ignora qualquer distancia
         * que mandemos — por isso `distancia_m` nem e enviado: mandar um numero
         * que sera jogado fora so criaria a duvida de qual dos dois vale. */
        pontos: corrida.pontos
      };

      return fetch(BASE + "/api/v1/corridas/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + token
        },
        body: JSON.stringify(corpo)
      })
        .then(function (r) {
          return r.json().then(function (c) {
            return { status: r.status, corpo: c };
          });
        })
        .then(function (r) {
          if (r.status >= 200 && r.status < 300) {
            return {
              acao: "apagar",
              motivo: r.status === 201 ? "criada" : "ja existia",
              oficial: r.corpo
            };
          }
          if (r.status === 409) {
            return {
              acao: "apagar",
              motivo: "conflito: " + (r.corpo.divergiram || []).join(", "),
              oficial: r.corpo.guardado
            };
          }
          if (r.status === 401) {
            return { acao: "manter", motivo: "token invalido ou vencido" };
          }
          if (r.status >= 400 && r.status < 500) {
            /* 4xx que nao e 401 nem 409 e defeito do cliente, e reenviar
             * repetiria o mesmo erro para sempre. Apaga e reporta. */
            return { acao: "apagar", motivo: r.corpo.erro || "recusada" };
          }
          return { acao: "manter", motivo: "servidor indisponivel" };
        })
        .catch(function (e) {
          /* Falha de REDE. Nunca apaga: e o caso para o qual a fila existe. */
          return { acao: "manter", motivo: "sem rede (" + e.message + ")" };
        });
    });
  }

  global.NutriApi = {
    base: BASE,
    entrar: entrar,
    lerToken: lerToken,
    sincronizar: sincronizar
  };
})(window);
