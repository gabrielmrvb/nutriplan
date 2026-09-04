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

  /* A corrida passa a viver no aparelho enquanto acontece.
   *
   * Antes disto ela vivia SÓ nesta variável: recarregar a página, o navegador
   * matar a aba, ou o `fetch` do fim falhar por falta de sinal — que é o caso
   * comum, porque quem corre está na rua — e a corrida sumia. A tela dizia
   * "Não consegui salvar agora", os botões voltavam ao início, e não existia
   * "de novo".
   *
   * A chave leva o id da pessoa de propósito. `localStorage` é por ORIGEM e
   * não por conta: sem isso, uma corrida interrompida seria oferecida a quem
   * entrasse depois no mesmo navegador — e gravada na conta DELE, porque quem
   * decide o dono é o `request.user` do servidor, nunca o que o cliente
   * manda. */
  var CHAVE = "nutriplan.corrida." + (document.body.dataset.usuario || "anon");

  var estado = {
    /* Nasce com a corrida, e não na hora de salvar.
     *
     * O model tem constraint de unicidade em `(user, op_id)` justamente para o
     * reenvio não duplicar. Gerando a chave dentro de `salvar()`, cada nova
     * tentativa inventava uma chave nova — a proteção existia no servidor e o
     * cliente a desligava. */
    opId: null,
    correndo: false,
    /* Carimbo de fim. Declarado aqui, e nao criado no meio do caminho: e ele
     * que a retomada le para saber se a corrida acabou e so falta subir. */
    terminou: null,
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
    guardar();
    pintar();
  }

  function erroDoGps(erro) {
    if (erro.code === erro.PERMISSION_DENIED) {
      /* Descartar so quando nao ha o que perder.
       *
       * A permissao pode ser revogada NO MEIO — o iOS faz isso quando o app
       * fica em segundo plano, e basta um toque errado num novo pedido. Antes,
       * `encerrar(true)` jogava fora a corrida inteira e ainda dizia "sem
       * distancia registrada", que era falso: havia 5 km registrados.
       *
       * Com distancia, o encerramento e o normal: grava e tenta subir. Achado
       * em revisao independente. */
      if (estado.distancia >= 1) {
        dizer("A localizacao foi negada. Encerrando e guardando o que ja foi.");
        encerrar(false);
        return;
      }
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
    guardar();
    pintar();
  }

  /* LISTA BRANCA, e nunca `JSON.stringify(estado)`.
   *
   * `estado.ancora` é uma leitura do GPS: tem latitude e longitude. Guardar o
   * estado inteiro contrabandearia para o `localStorage` exatamente o dado que
   * o model recusa guardar no banco — e com o agravante de ficar no aparelho,
   * legível por qualquer script da própria origem.
   *
   * Enumerar o que ENTRA, e não o que sai, é o que mantém isso verdadeiro
   * quando alguém acrescentar um campo novo ao estado: campo novo fica de
   * fora até alguém decidir o contrário. */
  function guardar() {
    if (!estado.opId) return;
    try {
      localStorage.setItem(CHAVE, JSON.stringify({
        opId: estado.opId,
        comecou: estado.comecou ? estado.comecou.toISOString() : null,
        terminou: estado.terminou ? estado.terminou.toISOString() : null,
        distancia: estado.distancia,
        movimentoMs: estado.movimentoMs,
        teveLacuna: estado.teveLacuna,
        marcas: estado.marcas,
        proximoKm: estado.proximoKm,
        ultimoAcumulado: estado.ultimoAcumulado,
        ultimoInstante: estado.ultimoInstante,
        pausada: estado.pausada,
        encerrada: !estado.correndo && !!estado.terminou
      }));
    } catch (e) {
      /* Modo privado e cota cheia levantam aqui. A corrida em andamento não
       * pode parar por causa disso — ela só deixa de ter rede de segurança, e
       * é melhor correr sem rede que não correr. */
    }
  }

  function esquecer() {
    try { localStorage.removeItem(CHAVE); } catch (e) { /* idem */ }
  }

  function guardado() {
    try {
      var cru = localStorage.getItem(CHAVE);
      return cru ? JSON.parse(cru) : null;
    } catch (e) {
      return null;
    }
  }

  function comecar() {
    /* Corrida nova começa do ZERO, e isto não é obviedade.
     *
     * Antes, `comecar()` só era chamada uma vez por carregamento de página:
     * o salvamento bem-sucedido recarrega a tela. Agora que falhar de salvar
     * NÃO é fim de linha, a pessoa pode tocar "Começar" de novo na mesma
     * instância — e sem zerar aqui, a corrida nova nasceria com a distância, o
     * tempo e as parciais da anterior.
     *
     * Achado em revisão independente. O efeito seria uma corrida de 2 km
     * reportada como 7 km, sem nada na tela sugerindo o erro. */
    estado.opId = identificador();
    estado.terminou = null;
    estado.correndo = true;
    estado.pausada = false;
    estado.ancora = null;
    estado.distancia = 0;
    estado.movimentoMs = 0;
    estado.teveLacuna = false;
    estado.marcas = [];
    estado.proximoKm = 1000;
    estado.ultimoAcumulado = 0;
    estado.ultimoInstante = 0;
    estado.comecou = new Date();
    estado.ultimoTique = Date.now();
    pintar();
    el.painel.hidden = false;
    el.aviso.hidden = true;
    el.comecar.hidden = true;
    el.pausar.hidden = false;
    el.encerrar.hidden = false;
    dizer("Procurando sinal de GPS...");

    ligarSensores();
    guardar();
  }

  /* Extraída porque a retomada de uma corrida recuperada também precisa dela:
   * depois de um reload não existe `watchPosition` nem relógio, e sem religá-los
   * o botão "Retomar" mudaria os rótulos da tela sem voltar a contar nada. */
  function ligarSensores() {
    if (estado.vigia == null) {
      estado.vigia = navigator.geolocation.watchPosition(receber, erroDoGps, {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 15000
      });
    }
    if (!estado.relogio) estado.relogio = setInterval(tique, 1000);
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
    guardar();
  }

  function retomar() {
    estado.pausada = false;
    estado.ultimoTique = Date.now();
    /* Vale para os dois caminhos: a pausa comum, em que a corrida nunca parou
     * de existir, e a retomada depois de um reload, em que ela existe no
     * `localStorage` e mais nada. `correndo` e o `hidden` do "Comecar" so
     * estao errados no segundo caso. */
    estado.correndo = true;
    el.comecar.hidden = true;
    el.retomar.hidden = true;
    el.pausar.hidden = false;
    el.encerrar.hidden = false;
    dizer("");
    ligarSensores();
    guardar();
  }

  function encerrar(semSalvar) {
    if (estado.vigia != null) navigator.geolocation.clearWatch(estado.vigia);
    if (estado.relogio) clearInterval(estado.relogio);
    /* Zerar os IDs, e não só limpar os sensores.
     *
     * `ligarSensores()` só religa quando eles estão nulos. Deixando os IDs
     * antigos aqui, a corrida SEGUINTE — na mesma instância de página, que é o
     * que acontece quando o salvamento falha e a tela não recarrega — não
     * religaria `watchPosition` nem o relógio: a tela mostraria "Pausar" e
     * "Encerrar", pareceria estar contando, e nenhum metro seria registrado.
     *
     * Medido: depois de um salvamento falho, tocar "Começar" de novo não
     * chamava `watchPosition`. Achado em revisão independente, e introduzido
     * por mim junto com a guarda de `ligarSensores()`. */
    estado.vigia = null;
    estado.relogio = null;
    estado.ancora = null;
    estado.correndo = false;
    soltarTela();
    el.pausar.hidden = true;
    el.retomar.hidden = true;
    el.encerrar.hidden = true;

    if (semSalvar || estado.distancia < 1) {
      dizer("Corrida encerrada sem distancia registrada.");
      esquecer();
      el.comecar.hidden = false;
      return;
    }
    /* O carimbo de fim vira estado ANTES da tentativa de envio: se ela falhar,
     * é ele que a retomada usa para saber que a corrida acabou e só falta
     * subir — em vez de oferecer "retomar" uma corrida que já terminou. */
    estado.terminou = new Date();
    guardar();
    salvar();
  }

  function identificador() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "corrida-" + Date.now() + "-" + Math.floor(Math.random() * 1e9);
  }

  /* A mesma leitura do `pwa.js`, com regex e nao com split em "; ": o
   * separador de `document.cookie` nem sempre traz o espaco, e a versao com
   * split falharia em silencio — devolvendo token vazio, que o servidor
   * recusa com 403 e o app mostraria como "nao consegui salvar". */
  /* Regex LITERAL, e nao `new RegExp` com string: num literal de string do
   * JavaScript, "\s" vira apenas "s" — o padrao viraria `(^|;)s*csrftoken=`,
   * que casa a letra "s" e nao espaco em branco. Com um cookie precedido de
   * espaco, o token voltaria vazio, o servidor responderia 403 e a tela diria
   * "nao consegui salvar" sem ninguem entender por que.
   *
   * O `pwa.js` ja lia assim, e copiar o padrao dele em vez de reescrever era o
   * caminho desde o comeco. */
  function tokenCsrf() {
    var achado = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return achado ? achado[2] : "";
  }

  function salvar() {
    var corpo = {
      /* A chave da corrida, e não uma nova a cada tentativa. É ela que faz o
       * segundo envio devolver a corrida que já existe em vez de criar outra. */
      op_id: estado.opId,
      comecou_em: estado.comecou.toISOString(),
      terminou_em: (estado.terminou || new Date()).toISOString(),
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
        "X-CSRFToken": tokenCsrf()
      },
      body: JSON.stringify(corpo),
      credentials: "same-origin"
    }).then(function (r) {
      if (r.ok) {
        /* Só agora o registro local deixa de fazer sentido. Apagá-lo antes da
         * confirmação seria trocar "a corrida não subiu" por "a corrida não
         * existe mais em lugar nenhum". */
        esquecer();
        window.location.reload();
        return;
      }
      /* 4xx que não seja de rede é problema do conteúdo, e insistir não
       * conserta. Guardar mesmo assim é melhor que descartar: a corrida fica
       * onde alguém pode olhar. */
      /* So agora o botao volta. Enquanto o envio estava em voo, ele ficou
       * escondido: um toque ali comecaria uma corrida NOVA por cima da que
       * ainda estava tentando subir, e o `reload()` do sucesso mataria a nova
       * em silencio. */
      el.comecar.hidden = false;
      dizer("Nao consegui salvar. A corrida esta guardada neste aparelho.");
    }).catch(function () {
      el.comecar.hidden = false;
      dizer("Sem conexao. A corrida esta guardada e sobe quando o sinal voltar.");
    });
  }

  /* A corrida interrompida, oferecida de volta.
   *
   * NÃO retoma sozinha: entre a interrupção e a pessoa reabrir a tela podem
   * ter passado duas horas, e continuar contando o tempo inventaria duração.
   * Quem decide é ela. */
  function recuperar() {
    var salvo = guardado();
    if (!salvo) return;

    /* Registro que não dá para usar é APAGADO, e não ignorado.
     *
     * Medido no navegador: um registro com `comecou` nulo e marcado como
     * encerrado fazia `salvar()` estourar em `estado.comecou.toISOString()`. O
     * erro não some sozinho — o registro continua no aparelho, e a tela quebra
     * de novo TODA vez que alguém a abre. Ignorar em silêncio daria o mesmo
     * resultado: uma corrida presa que nunca sobe e nunca sai da frente.
     *
     * Uma corrida sem início ou sem chave não é recuperável de jeito nenhum —
     * o servidor recusaria as duas. Perder o registro quebrado é melhor que
     * deixar a tela inutilizável. */
    if (!salvo.opId || !salvo.comecou) {
      esquecer();
      return;
    }

    estado.opId = salvo.opId;
    estado.comecou = salvo.comecou ? new Date(salvo.comecou) : null;
    estado.terminou = salvo.terminou ? new Date(salvo.terminou) : null;
    estado.distancia = salvo.distancia || 0;
    estado.movimentoMs = salvo.movimentoMs || 0;
    estado.teveLacuna = !!salvo.teveLacuna;
    estado.marcas = salvo.marcas || [];
    estado.proximoKm = salvo.proximoKm || 1000;
    estado.ultimoAcumulado = salvo.ultimoAcumulado || 0;
    estado.ultimoInstante = salvo.ultimoInstante || 0;
    pintar();
    el.painel.hidden = false;
    el.aviso.hidden = true;

    if (salvo.encerrada) {
      /* Escondido pelo mesmo motivo do `encerrar()`: comecar uma corrida nova
       * por cima de um reenvio em voo perde as duas. */
      el.comecar.hidden = true;
      dizer("Uma corrida ficou sem subir. Tentando de novo...");
      salvar();
      return;
    }

    /* Não terminada: a distância já contada não se perde, e a pessoa escolhe
     * entre continuar de onde parou ou encerrar e guardar o que existe. */
    estado.pausada = true;
    estado.correndo = false;
    el.comecar.hidden = true;
    el.retomar.hidden = false;
    el.encerrar.hidden = false;
    dizer("Uma corrida ficou aberta. Retome ou encerre para guardar.");
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

  /* Quando o sinal volta, a corrida que ficou guardada sobe sozinha. E o
   * `op_id` estavel e o que torna isso seguro: se o envio anterior tiver
   * chegado sem a resposta voltar, o servidor devolve a mesma corrida em vez
   * de criar uma segunda. */
  window.addEventListener("online", function () {
    var salvo = guardado();
    if (salvo && salvo.encerrada && estado.opId === salvo.opId) salvar();
  });

  el.comecar.addEventListener("click", comecar);
  el.pausar.addEventListener("click", pausar);
  el.retomar.addEventListener("click", retomar);
  el.encerrar.addEventListener("click", function () { encerrar(false); });

  recuperar();
})();
