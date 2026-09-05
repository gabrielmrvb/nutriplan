/* A FRONTEIRA DE GEOLOCALIZACAO — o contrato e nosso, nao do plugin.
 *
 * Nenhum outro arquivo deste app pode importar o plugin de background
 * geolocation. Todos falam com `NutriGeo`, e so este arquivo sabe qual
 * biblioteca esta atras.
 *
 * POR QUE ISSO IMPORTA AQUI, E NAO E CERIMONIA
 *
 * A escolha do plugin ainda pode mudar, e a alternativa madura e PAGA (399 USD
 * no Transistorsoft). Se a logica de corrida chamasse o plugin direto, trocar
 * de fornecedor seria reescrever o app. Com a fronteira, e reescrever este
 * arquivo.
 *
 * O CONTRATO
 *
 *   NutriGeo.disponivel()          -> boolean   (roda em navegador tambem?)
 *   NutriGeo.pedirPermissao()      -> Promise<"concedida"|"negada">
 *   NutriGeo.iniciar(aoPonto)      -> Promise<sessao>
 *   sessao.encerrar()              -> Promise<void>
 *
 * O ponto entregue e SEMPRE deste formato, venha de onde vier:
 *
 *   { lat: number, lon: number, t: number, accuracy: number|null }
 *
 * `t` e SEGUNDOS desde o inicio da sessao, nao epoch. E o que o motor Python
 * espera em `workouts/corrida.py`, e converter aqui evita que cada chamador
 * invente a propria conta.
 *
 * O FALLBACK DE NAVEGADOR NAO E PARA PRODUCAO
 *
 * Quando o plugin nao existe (a pagina aberta num navegador comum, durante
 * desenvolvimento), caimos em `navigator.geolocation`. Isso serve para abrir a
 * tela e ver o layout — NAO serve para provar background, e `modo()` diz qual
 * dos dois esta ativo justamente para que nenhum relatorio confunda os dois.
 */
(function (global) {
  "use strict";

  var plugin = null;
  try {
    /* O plugin e registrado pelo Capacitor no objeto global. Ausencia dele e
     * caso NORMAL no navegador, e nao erro. */
    plugin =
      (global.Capacitor &&
        global.Capacitor.Plugins &&
        global.Capacitor.Plugins.BackgroundGeolocation) ||
      null;
  } catch (e) {
    plugin = null;
  }

  function modo() {
    return plugin ? "nativo" : "navegador";
  }

  function disponivel() {
    return Boolean(plugin || (global.navigator && global.navigator.geolocation));
  }

  function normalizar(bruto, comecouEm) {
    /* Um so lugar converte. O plugin devolve `latitude/longitude`; o navegador
     * devolve `coords.latitude`. Se cada chamador normalizasse, a primeira
     * troca de plugin quebraria em cinco lugares. */
    var lat = bruto.latitude;
    var lon = bruto.longitude;
    var acc = bruto.accuracy;
    if (lat === undefined && bruto.coords) {
      lat = bruto.coords.latitude;
      lon = bruto.coords.longitude;
      acc = bruto.coords.accuracy;
    }
    return {
      lat: lat,
      lon: lon,
      t: (Date.now() - comecouEm) / 1000,
      accuracy: acc === undefined || acc === null ? null : acc
    };
  }

  function pedirPermissao() {
    /* No caminho nativo quem pede e o proprio plugin, no `addWatcher`. Aqui a
     * promessa existe para a tela poder explicar ANTES do dialogo do sistema —
     * exigencia de review das duas lojas, e simplesmente decente. */
    if (!disponivel()) {
      return Promise.resolve("negada");
    }
    return Promise.resolve("concedida");
  }

  function iniciarNativo(aoPonto, comecouEm) {
    return new Promise(function (resolve, reject) {
      plugin
        .addWatcher(
          {
            /* O texto da notificacao persistente. No Android ele NAO e
             * enfeite: e a contrapartida exigida pelo sistema para o app
             * continuar recebendo posicao com a tela apagada. */
            backgroundMessage: "Registrando seu percurso.",
            backgroundTitle: "Corrida em andamento",
            requestPermissions: true,
            stale: false,
            /* Sem distanceFilter: o filtro de ruido e de teleporte e do motor
             * Python, que e a fonte autoritativa. Filtrar aqui tambem criaria
             * dois filtros para ajustar, e o do cliente venceria em silencio. */
            distanceFilter: 0
          },
          function (posicao, erro) {
            if (erro) {
              /* NEGACAO NAO E FALHA TRANSITORIA. O plugin entrega o motivo, e
               * quem chamou precisa distinguir "sem permissao" de "sem sinal"
               * para dizer a coisa certa na tela. */
              aoPonto(null, erro);
              return;
            }
            aoPonto(normalizar(posicao, comecouEm), null);
          }
        )
        .then(function (id) {
          resolve({
            modo: "nativo",
            encerrar: function () {
              return plugin.removeWatcher({ id: id });
            }
          });
        })
        .catch(reject);
    });
  }

  function iniciarNavegador(aoPonto, comecouEm) {
    var id = global.navigator.geolocation.watchPosition(
      function (p) {
        aoPonto(normalizar(p, comecouEm), null);
      },
      function (e) {
        aoPonto(null, e);
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 }
    );
    return Promise.resolve({
      modo: "navegador",
      encerrar: function () {
        global.navigator.geolocation.clearWatch(id);
        return Promise.resolve();
      }
    });
  }

  function iniciar(aoPonto) {
    var comecouEm = Date.now();
    if (plugin) {
      return iniciarNativo(aoPonto, comecouEm);
    }
    if (global.navigator && global.navigator.geolocation) {
      return iniciarNavegador(aoPonto, comecouEm);
    }
    return Promise.reject(new Error("sem geolocalizacao neste ambiente"));
  }

  global.NutriGeo = {
    modo: modo,
    disponivel: disponivel,
    pedirPermissao: pedirPermissao,
    iniciar: iniciar
  };
})(window);
