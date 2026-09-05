/* A fiacao da tela. Logica de dominio mora em corrida.js/geo.js/api.js. */
(function () {
  "use strict";

  var el = function (id) {
    return document.getElementById(id);
  };
  var corrida = null;
  var relogio = null;

  function log(msg) {
    var agora = new Date().toISOString().slice(11, 19);
    el("log").textContent = agora + "  " + msg + "\n" + el("log").textContent;
  }

  function doisDigitos(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function relogioTexto(segundos) {
    var m = Math.floor(segundos / 60);
    var s = Math.floor(segundos % 60);
    return doisDigitos(m) + ":" + doisDigitos(s);
  }

  function comVirgula(n, casas) {
    /* pt-BR: virgula decimal. A mesma regra do app web. */
    return n.toFixed(casas).replace(".", ",");
  }

  /* MAIOR INTERVALO ENTRE LEITURAS — a metrica que prova o background.
   *
   * Se o GPS parar com a tela bloqueada, a distancia pode ate parecer
   * plausivel, mas aparece um buraco de varios minutos entre dois pontos. Este
   * numero e o que transforma "acho que continuou" em evidencia. */
  function maiorIntervalo(pontos) {
    var maior = 0;
    for (var i = 1; i < pontos.length; i++) {
      var d = pontos[i].t - pontos[i - 1].t;
      if (d > maior) {
        maior = d;
      }
    }
    return maior;
  }

  function pintar() {
    if (!corrida) {
      return;
    }
    var km = corrida.distanciaProvisoriaM / 1000;
    el("distancia").textContent = comVirgula(km, 2);
    el("pontos").textContent = String(corrida.pontos.length);

    var seg = corrida.comecouEm
      ? (Date.now() - new Date(corrida.comecouEm).getTime()) / 1000
      : 0;
    el("tempo").textContent = relogioTexto(seg);
    el("pace").textContent =
      km > 0.05 ? relogioTexto(seg / km) + "/km" : "—";

    var ultimo = corrida.pontos[corrida.pontos.length - 1];
    el("diag-ultimo").textContent = ultimo
      ? comVirgula(ultimo.t, 1) + "s (±" + (ultimo.accuracy === null ? "?" : Math.round(ultimo.accuracy)) + "m)"
      : "—";
    el("diag-gap").textContent =
      corrida.pontos.length > 1 ? comVirgula(maiorIntervalo(corrida.pontos), 1) + "s" : "—";

    if (corrida.ultimoErro) {
      el("estado-corrida").textContent = "Aviso: " + corrida.ultimoErro;
    }
  }

  function mostrarCorrida() {
    el("secao-entrar").hidden = true;
    el("secao-corrida").hidden = false;
  }

  el("botao-entrar").addEventListener("click", function () {
    el("erro-entrar").textContent = "";
    NutriApi.entrar(el("email").value.trim(), el("senha").value)
      .then(function (usuario) {
        log("entrou como " + (usuario.email || "?"));
        mostrarCorrida();
      })
      .catch(function (e) {
        el("erro-entrar").textContent = e.message;
        log("falha ao entrar: " + e.message);
      });
  });

  el("botao-iniciar").addEventListener("click", function () {
    corrida = new NutriCorrida();
    corrida
      .iniciar(function () {
        pintar();
      })
      .then(function () {
        log("corrida iniciada, op_id=" + corrida.opId);
        log("modo de GPS: " + NutriGeo.modo());
        el("botao-iniciar").hidden = true;
        el("botao-encerrar").hidden = false;
        el("estado-corrida").textContent =
          "Registrando. Pode bloquear a tela e guardar o telefone.";
        relogio = setInterval(pintar, 1000);
      })
      .catch(function (e) {
        log("nao consegui iniciar: " + e.message);
        el("estado-corrida").textContent = "Nao consegui iniciar: " + e.message;
      });
  });

  el("botao-encerrar").addEventListener("click", function () {
    if (!corrida) {
      return;
    }
    clearInterval(relogio);
    el("estado-corrida").textContent = "Encerrando...";
    corrida
      .encerrar()
      .then(function () {
        log("encerrada com " + corrida.pontos.length + " pontos");
        el("estado-corrida").textContent = "Sincronizando...";
        return NutriApi.sincronizar(corrida);
      })
      .then(function (r) {
        log("sync: " + r.acao + " (" + r.motivo + ")");
        if (r.acao === "apagar") {
          /* O numero OFICIAL chega aqui e substitui o provisorio. E o unico
           * lugar do app onde a distancia deixa de ser um palpite do aparelho. */
          if (r.oficial && typeof r.oficial.distancia_m === "number") {
            el("distancia").textContent = comVirgula(r.oficial.distancia_m / 1000, 2);
            log("oficial do servidor: " + r.oficial.distancia_m + " m");
          }
          el("estado-corrida").textContent = "Sincronizada. " + r.motivo;
          return NutriCorrida.esquecer();
        }
        el("estado-corrida").textContent =
          "Guardada no aparelho (" + r.motivo + "). Vai subir depois.";
      })
      .then(function () {
        el("botao-iniciar").hidden = false;
        el("botao-encerrar").hidden = true;
      });
  });

  /* ABERTURA: diagnostico e recuperacao, sempre nesta ordem. */
  el("diag-geo").textContent = NutriGeo.disponivel()
    ? NutriGeo.modo()
    : "indisponivel";
  el("diag-store").textContent = NutriCorrida.modoArmazenamento();

  NutriApi.lerToken().then(function (t) {
    if (t) {
      mostrarCorrida();
      log("token encontrado no aparelho");
    }
  });

  NutriCorrida.recuperar().then(function (c) {
    if (!c) {
      return;
    }
    corrida = c;
    mostrarCorrida();
    pintar();
    if (c.estado === "interrompida") {
      /* O app foi morto no meio. NAO retomamos o rastreio sozinhos: o watcher
       * morreu com o processo, e voltar a gravar agora deixaria um buraco no
       * meio que ninguem saberia explicar. */
      el("estado-corrida").textContent =
        "Havia uma corrida interrompida com " + c.pontos.length +
        " pontos. Encerre para sincronizar o que foi registrado.";
      el("botao-iniciar").hidden = true;
      el("botao-encerrar").hidden = false;
      log("corrida recuperada do disco: " + c.opId);
    }
  });
})();
