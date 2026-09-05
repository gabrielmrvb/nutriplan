/* A CORRIDA NO APARELHO: estado, persistencia e recuperacao.
 *
 * Este arquivo NAO calcula a corrida oficial. Ele acumula pontos e mostra
 * numeros PROVISORIOS na tela, porque sem eles a pessoa correria olhando para
 * um cronometro vazio. O numero final vem do servidor, e substitui o
 * provisorio quando a sincronizacao volta.
 *
 * A distincao esta no nome das coisas de proposito: `provisorio` aparece na
 * tela e `oficial` so existe depois do POST. Um dia alguem vai querer "usar o
 * numero que ja esta na tela" para nao esperar a rede — e vai encontrar um
 * campo chamado provisorio.
 *
 * POR QUE `Preferences` E NAO `localStorage`
 *
 * A corrida precisa sobreviver ao app ser MORTO pelo sistema. No Android com
 * pouca memoria e no iOS por politica, isso acontece no meio de uma corrida
 * longa — que e exatamente quando a pessoa mais tem a perder. `Preferences` e
 * armazenamento nativo; `localStorage` vive no WebView, que morre junto.
 *
 * O `op_id` NASCE ANTES DO PRIMEIRO PONTO
 *
 * Nao no fim, na hora de enviar. Se ele nascesse no envio, uma corrida
 * recuperada depois de um crash ganharia um `op_id` novo e o servidor a trataria
 * como outra corrida — a duplicata que a idempotencia existe para impedir.
 */
(function (global) {
  "use strict";

  var CHAVE = "corrida_em_andamento";
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

  /* Sem o plugin (navegador de desenvolvimento), cai em localStorage. Continua
   * NAO servindo para provar recuperacao de crash, e `modoArmazenamento()` diz
   * qual dos dois esta ativo. */
  function guardar(dados) {
    var texto = JSON.stringify(dados);
    if (Prefs) {
      return Prefs.set({ key: CHAVE, value: texto });
    }
    global.localStorage.setItem(CHAVE, texto);
    return Promise.resolve();
  }

  function ler() {
    if (Prefs) {
      return Prefs.get({ key: CHAVE }).then(function (r) {
        return r && r.value ? JSON.parse(r.value) : null;
      });
    }
    var v = global.localStorage.getItem(CHAVE);
    return Promise.resolve(v ? JSON.parse(v) : null);
  }

  function esquecer() {
    if (Prefs) {
      return Prefs.remove({ key: CHAVE });
    }
    global.localStorage.removeItem(CHAVE);
    return Promise.resolve();
  }

  function modoArmazenamento() {
    return Prefs ? "nativo" : "navegador";
  }

  function novoOpId() {
    /* `crypto.randomUUID` existe no WebView moderno; o fallback nao precisa ser
     * criptografico — a chave e por PESSOA, entao colisao entre dois aparelhos
     * de gente diferente nao e problema. */
    if (global.crypto && global.crypto.randomUUID) {
      return global.crypto.randomUUID();
    }
    return "op-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
  }

  function metrosEntre(a, b) {
    /* Haversine, so para o numero PROVISORIO da tela. A distancia que vale e a
     * que `workouts/corrida.py` calcula sobre os mesmos pontos. */
    var R = 6371000;
    var f1 = (a.lat * Math.PI) / 180;
    var f2 = (b.lat * Math.PI) / 180;
    var df = ((b.lat - a.lat) * Math.PI) / 180;
    var dl = ((b.lon - a.lon) * Math.PI) / 180;
    var h =
      Math.sin(df / 2) * Math.sin(df / 2) +
      Math.cos(f1) * Math.cos(f2) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function Corrida() {
    this.opId = null;
    this.comecouEm = null;
    this.pontos = [];
    this.distanciaProvisoriaM = 0;
    this.estado = "parada";
    this.sessao = null;
    this.ultimoErro = null;
  }

  Corrida.prototype.iniciar = function (aoMudar) {
    var eu = this;
    eu.opId = novoOpId();
    eu.comecouEm = new Date().toISOString();
    eu.pontos = [];
    eu.distanciaProvisoriaM = 0;
    eu.estado = "ativa";

    return global.NutriGeo.iniciar(function (ponto, erro) {
      if (erro) {
        eu.ultimoErro = erro.message || String(erro);
        aoMudar(eu);
        return;
      }
      var anterior = eu.pontos[eu.pontos.length - 1];
      if (anterior) {
        eu.distanciaProvisoriaM += metrosEntre(anterior, ponto);
      }
      eu.pontos.push(ponto);

      /* GRAVA A CADA PONTO, e nao a cada N. Um app morto entre duas gravacoes
       * perde o trecho — e o trecho perdido e sempre o mais recente, que e o
       * que a pessoa acabou de correr. O custo e uma escrita por segundo em
       * armazenamento nativo, que e barato perto de perder a corrida. */
      eu.salvar();
      aoMudar(eu);
    }).then(function (sessao) {
      eu.sessao = sessao;
      return eu.salvar().then(function () {
        return eu;
      });
    });
  };

  Corrida.prototype.salvar = function () {
    return guardar({
      opId: this.opId,
      comecouEm: this.comecouEm,
      pontos: this.pontos,
      estado: this.estado
    });
  };

  Corrida.prototype.encerrar = function () {
    var eu = this;
    eu.estado = "encerrada";
    var parar = eu.sessao ? eu.sessao.encerrar() : Promise.resolve();
    return parar.then(function () {
      return eu.salvar().then(function () {
        return eu;
      });
    });
  };

  /* RECUPERACAO: chamada na abertura do app, sempre.
   *
   * Se havia corrida no disco, ela volta. Uma corrida `ativa` recuperada NAO
   * volta a rastrear sozinha: o watcher morreu com o processo, e retomar sem a
   * pessoa saber produziria um buraco no meio que ninguem explicaria. A tela
   * oferece encerrar e sincronizar o que existe. */
  Corrida.recuperar = function () {
    return ler().then(function (dados) {
      if (!dados) {
        return null;
      }
      var c = new Corrida();
      c.opId = dados.opId;
      c.comecouEm = dados.comecouEm;
      c.pontos = dados.pontos || [];
      c.estado = dados.estado === "ativa" ? "interrompida" : dados.estado;
      for (var i = 1; i < c.pontos.length; i++) {
        c.distanciaProvisoriaM += metrosEntre(c.pontos[i - 1], c.pontos[i]);
      }
      return c;
    });
  };

  Corrida.esquecer = esquecer;
  Corrida.modoArmazenamento = modoArmazenamento;
  global.NutriCorrida = Corrida;
})(window);
