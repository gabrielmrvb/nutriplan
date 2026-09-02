/* A corrida no navegador.
 *
 * O que este arquivo NAO faz, e e o desenho inteiro: ele nao promete
 * acompanhar a corrida com o app fechado. Uma PWA nao tem geolocalizacao em
 * segundo plano — nao e limitacao de esforco, e ausencia de API. Com a tela
 * bloqueada o navegador suspende a pagina e as leituras param.
 *
 * A resposta e dupla e honesta: Wake Lock para a tela nao apagar, e MARCAR a
 * corrida quando a pagina ficou oculta. Sem a marca, a tela mostraria uma
 * distancia menor como se fosse a real — e o pior de um numero errado e
 * parecer certo.
 *
 * As coordenadas morrem aqui. O que sobe para o servidor e distancia, tempo e
 * parciais; o tracado nao e enviado nem guardado. Rota nao diz quanto a pessoa
 * pesa, diz onde ela mora.
 */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-corrida]");
  if (!raiz || !("geolocation" in navigator)) return;

  /* Os mesmos limites de `workouts/corrida.py`. Duas copias do mesmo numero e
   * como uma delas fica para tras — e existe um teste que compara as duas
   * justamente por isso. */
  var PRECISAO_MAXIMA_M = 30.0;
  var VELOCIDADE_MAXIMA_MS = 12.5;
  var DESLOCAMENTO_MINIMO_M = 1.5;
  var RAIO_DA_TERRA_M = 6371000;

  var estado = {
    correndo: false,
    pausada: false,
    comecou: null,
    ancora: null,
    distancia: 0,
    movimentoMs: 0,
    ultimoTique: null,
    teveLacuna: false,
    marcas: [],
    proximoKm: 1000,
    ultimoAcumulado: 0,
    ultimoInstante: 0,
    vigia: null,
    trava: null,
    relogio: null
  };

  var el = {
    aviso: raiz.querySelector("[data-corrida-aviso]"),
    painel: raiz.querySelector("[data-corrida-painel]"),
    distancia: raiz.querySelector("[data-corrida-distancia]"),
    tempo: raiz.querySelector("[data-corrida-tempo]"),
    pace: raiz.querySelector("[data-corrida-pace]"),
    recado: raiz.querySelector("[data-corrida-estado]"),
    comecar: raiz.querySelector("[data-corrida-comecar]"),
    pausar: raiz.querySelector("[data-corrida-pausar]"),
    retomar: raiz.querySelector("[data-corrida-retomar]"),
    encerrar: raiz.querySelector("[data-corrida-encerrar]")
  };

  function radianos(g) { return (g * Math.PI) / 180; }

  function distanciaM(a, b) {
    var dlat = radianos(b.lat - a.lat);
    var dlon = radianos(b.lon - a.lon);
    var h =
      Math.sin(dlat / 2) * Math.sin(dlat / 2) +
      Math.cos(radianos(a.lat)) * Math.cos(radianos(b.lat)) *
        Math.sin(dlon / 2) * Math.sin(dlon / 2);
    return 2 * RAIO_DA_TERRA_M * Math.asin(Math.sqrt(h));
  }

  /* Virgula decimal: o app e pt-BR e o numero aqui e lido de relance,
   * correndo. */
  function comVirgula(numero, casas) {
    return numero.toFixed(casas).replace(".", ",");
  }

  function relogio(segundos) {
    var m = Math.floor(segundos / 60);
    var s = Math.floor(segundos % 60);
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }

  function pintar() {
    el.distancia.textContent = comVirgula(estado.distancia / 1000, 2);
    var segundos = estado.movimentoMs / 1000;
    el.tempo.textContent = relogio(segundos);
    if (estado.distancia > 20 && segundos > 0) {
      el.pace.textContent = relogio((segundos * 1000) / estado.distancia);
    } else {
      /* Abaixo de vinte metros o pace e ruido dividido por ruido. Um numero
       * que salta de 2:00 para 40:00 a cada segundo e pior que nenhum. */
      el.pace.textContent = "—";
    }
  }

  function dizer(texto) { el.recado.textContent = texto; }

  function aceitar(leitura) {
    if (leitura.accuracy != null && leitura.accuracy > PRECISAO_MAXIMA_M) return false;
    var segundos = (leitura.t - estado.ancora.t) / 1000;
    if (segundos <= 0) return false;
    var metros = distanciaM(estado.ancora, leitura);
    if (metros < DESLOCAMENTO_MINIMO_M) return false;
    if (metros / segundos > VELOCIDADE_MAXIMA_MS) return false;
    return true;
  }

  function receber(posicao) {
    if (!estado.correndo || estado.pausada) return;

    var leitura = {
      lat: posicao.coords.latitude,
      lon: posicao.coords.longitude,
      accuracy: posicao.coords.accuracy,
      t: posicao.timestamp
    };

    if (!estado.ancora) {
      if (leitura.accuracy != null && leitura.accuracy > PRECISAO_MAXIMA_M) {
        dizer("Procurando sinal de GPS...");
        return;
      }
      estado.ancora = leitura;
      if (!estado.ultimoInstante) estado.ultimoInstante = leitura.t;
      dizer("");
      return;
    }

    /* Recusou? A ancora NAO avanca. E isso que faz caminhada funcionar: a
     * proxima leitura e comparada com o ultimo ponto bom, e passa. */
    if (!aceitar(leitura)) return;

    estado.distancia += distanciaM(estado.ancora, leitura);

    /* A parcial do quilometro cheio, interpolada entre as duas leituras.
     * Atribuir ao ponto seguinte empurra cada parcial para frente, e o erro se
     * acumula uma vez por quilometro. */
    while (estado.distancia >= estado.proximoKm) {
      var faixa = estado.distancia - estado.ultimoAcumulado;
      if (faixa <= 0) break;
      var fracao = (estado.proximoKm - estado.ultimoAcumulado) / faixa;
      var instante = estado.ancora.t + fracao * (leitura.t - estado.ancora.t);
      estado.marcas.push({
        km: estado.marcas.length + 1,
        segundos: (instante - estado.ultimoInstante) / 1000
      });
      estado.ultimoInstante = instante;
      estado.proximoKm += 1000;
    }

    estado.ultimoAcumulado = estado.distancia;
    estado.ancora = leitura;
    pintar();
  }

  function erroDoGps(erro) {
    if (erro.code === erro.PERMISSION_DENIED) {
      dizer("Sem permissao de localizacao. A corrida nao pode ser registrada.");
      encerrar(true);
      return;
    }
    dizer("Sinal de GPS fraco. Continuo tentando.");
  }

  function segurarTela() {
    if (!("wakeLock" in navigator)) return;
    if (estado.trava || document.visibilityState !== "visible") return;
    navigator.wakeLock.request("screen").then(function (t) {
      estado.trava = t;
      t.addEventListener("release", function () { estado.trava = null; });
    }).catch(function () { /* recusado: a tela apaga, e a marca de lacuna avisa */ });
  }

  function soltarTela() {
    if (!estado.trava) return;
    var t = estado.trava;
    estado.trava = null;
    t.release().catch(function () {});
  }

  function tique() {
    if (!estado.correndo || estado.pausada) return;
    var agora = Date.now();
    estado.movimentoMs += agora - estado.ultimoTique;
    estado.ultimoTique = agora;
    pintar();
  }

  function comecar() {
    estado.correndo = true;
    estado.pausada = false;
    estado.comecou = new Date();
    estado.ultimoTique = Date.now();
    el.painel.hidden = false;
    el.aviso.hidden = true;
    el.comecar.hidden = true;
    el.pausar.hidden = false;
    el.encerrar.hidden = false;
    dizer("Procurando sinal de GPS...");

    estado.vigia = navigator.geolocation.watchPosition(receber, erroDoGps, {
      enableHighAccuracy: true,
      maximumAge: 0,
      timeout: 15000
    });
    estado.relogio = setInterval(tique, 1000);
    segurarTela();
  }

  function pausar() {
    estado.pausada = true;
    /* A ancora some na pausa: sem isso, o deslocamento entre pausar e retomar
     * viraria percurso. Quem parou para atravessar a rua nao correu a rua. */
    estado.ancora = null;
    el.pausar.hidden = true;
    el.retomar.hidden = false;
    dizer("Pausada. O tempo parado nao conta.");
  }

  function retomar() {
    estado.pausada = false;
    estado.ultimoTique = Date.now();
    el.retomar.hidden = true;
    el.pausar.hidden = false;
    dizer("");
    segurarTela();
  }

  function encerrar(semSalvar) {
    if (estado.vigia != null) navigator.geolocation.clearWatch(estado.vigia);
    if (estado.relogio) clearInterval(estado.relogio);
    estado.correndo = false;
    soltarTela();
    el.pausar.hidden = true;
    el.retomar.hidden = true;
    el.encerrar.hidden = true;
    el.comecar.hidden = false;

    if (semSalvar || estado.distancia < 1) {
      dizer("Corrida encerrada sem distancia registrada.");
      return;
    }
    salvar();
  }

  function identificador() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "corrida-" + Date.now() + "-" + Math.floor(Math.random() * 1e9);
  }

  function biscoito(nome) {
    var partes = document.cookie.split("; ");
    for (var i = 0; i < partes.length; i++) {
      if (partes[i].indexOf(nome + "=") === 0) return partes[i].split("=")[1];
    }
    return "";
  }

  function salvar() {
    var corpo = {
      op_id: identificador(),
      comecou_em: estado.comecou.toISOString(),
      terminou_em: new Date().toISOString(),
      distancia_m: Math.round(estado.distancia),
      duracao_s: Math.round(estado.movimentoMs / 1000),
      teve_lacuna: estado.teveLacuna,
      parciais: estado.marcas
    };
    dizer("Salvando...");
    fetch(raiz.dataset.salvar, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": biscoito("csrftoken")
      },
      body: JSON.stringify(corpo),
      credentials: "same-origin"
    }).then(function (r) {
      if (r.ok) { window.location.reload(); return; }
      dizer("Nao consegui salvar agora. Tente de novo com sinal.");
    }).catch(function () {
      dizer("Sem conexao. Tente de novo quando voltar o sinal.");
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (!estado.correndo || estado.pausada) return;
    if (document.visibilityState === "visible") {
      segurarTela();
      /* A ancora some: enquanto a pagina esteve oculta o navegador nao
       * entregou posicao, e ligar o ponto de antes ao de agora desenharia uma
       * reta que ninguem correu. */
      estado.ancora = null;
      dizer("Houve um trecho sem registro enquanto o app estava fora da tela.");
    } else {
      estado.teveLacuna = true;
    }
  });

  window.addEventListener("pagehide", soltarTela);

  el.comecar.addEventListener("click", comecar);
  el.pausar.addEventListener("click", pausar);
  el.retomar.addEventListener("click", retomar);
  el.encerrar.addEventListener("click", function () { encerrar(false); });
})();
