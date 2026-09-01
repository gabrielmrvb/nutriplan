/* A fila de escritas offline.
 *
 * O que ela cobre e por quê:
 *
 *   água, marcação de refeição, carga de série.
 *
 * São as três coisas que a pessoa marca no meio de outra atividade — de pé
 * na academia, na fila do mercado, com o elevador descendo — e são as três
 * em que perder a marcação por falta de sinal significa perder o dado do dia.
 *
 * O que ela NÃO cobre, e isso é decisão e não esquecimento: assistente de
 * treino, recalibragem de metas e geração de plano. As três leem o estado do
 * servidor para decidir o que fazer. Enfileirá-las produziria decisões tomadas
 * sobre dados velhos — uma substituição de exercício calculada sobre a ficha
 * de ontem, aplicada amanhã.
 *
 * **Sobre o Background Sync.** A API existe no Chrome e não existe no Safari do
 * iPhone, que é metade dos aparelhos deste app. Então ela entra como bônus: o
 * mecanismo principal é o evento `online` mais uma drenagem na abertura da
 * página, que funciona em todo lugar.
 *
 * **Sobre repetir.** A rede não garante entrega única, então cada item da fila
 * carrega um identificador gerado aqui e o servidor lembra o que já aplicou.
 * Sem isso, reenviar "+500 ml" duas vezes registraria um litro que ninguém
 * bebeu — água soma.
 */
(function () {
  "use strict";

  var BANCO = "nutriplan-fila";
  var LOJA = "pendentes";

  /* VERSÃO 2, e a subida de 1 para 2 é a correção de um defeito que apagava
   * gravação offline em silêncio.
   *
   * O service worker abria ESTE MESMO banco em `abrirFila()` sem
   * `onupgradeneeded`. Se ele chegasse primeiro — o que acontece num evento
   * `sync` —, o IndexedDB criava o banco na versão 1 COM ZERO STORES, porque
   * não havia handler para criar nenhuma. A partir dali o banco ficava
   * envenenado para sempre: este arquivo abria na versão 1, encontrava um
   * banco v1 já existente, o `onupgradeneeded` nunca disparava, e
   * `transaction("pendentes")` estourava com
   *
   *   NotFoundError: One of the specified object stores was not found
   *
   * em toda marcação de refeição, água e carga feita sem rede. A versão nunca
   * subia, então nada se recuperava sozinho.
   *
   * Subir para 2 força o `onupgradeneeded` a rodar nos bancos já envenenados e
   * criar a store que falta. É MIGRAÇÃO, não `deleteDatabase()`: um banco são
   * mantém as operações pendentes que ainda não foram enviadas, e ninguém
   * perde o que registrou offline.
   *
   * `templates/pwa/sw.js` PRECISA declarar o mesmo número. Se um subir e o
   * outro não, o que ficou para trás recebe `VersionError` e para de drenar a
   * fila. Um teste em `push/tests.py` compara os dois arquivos. */
  var VERSAO = 2;

  /* Só estas rotas. Um curinga aqui seria a porta para enfileirar coisa que
   * depende de estado do servidor. */
  var ROTAS = [
    /^\/agua\/$/,
    /^\/refeicao\/\d+\/marcar\/$/,
    /^\/treino\/exercicio\/\d+\/carga\/$/,
  ];

  function permitida(url) {
    var caminho = new URL(url, location.origin).pathname;
    return ROTAS.some(function (r) { return r.test(caminho); });
  }

  function identificador() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    /* Navegador antigo: hora mais aleatório é colisão improvável o bastante
     * para uma fila que vive minutos. */
    return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function abrir() {
    return new Promise(function (resolve, reject) {
      var pedido = indexedDB.open(BANCO, VERSAO);
      pedido.onupgradeneeded = function () {
        var db = pedido.result;
        if (!db.objectStoreNames.contains(LOJA)) {
          db.createObjectStore(LOJA, { keyPath: "op_id" });
        }
      };
      pedido.onsuccess = function () { resolve(pedido.result); };
      pedido.onerror = function () { reject(pedido.error); };
    });
  }

  function comLoja(modo, trabalho) {
    return abrir().then(function (db) {
      return new Promise(function (resolve, reject) {
        /* Cinto e suspensório. Depois da subida para a versão 2 isto não
         * deveria acontecer nunca — mas o defeito que ela conserta se
         * manifestava exatamente aqui, com um `NotFoundError` cru que não
         * dizia de onde vinha. Se um dia voltar, que volte dizendo o nome. */
        if (!db.objectStoreNames.contains(LOJA)) {
          db.close();
          reject(new Error(
            "A fila offline do NutriPlan está sem a loja '" + LOJA + "'. " +
            "O banco existe numa versão antiga sem a store."
          ));
          return;
        }
        var tx = db.transaction(LOJA, modo);
        var resultado = trabalho(tx.objectStore(LOJA));
        tx.oncomplete = function () { db.close(); resolve(resultado && resultado.result); };
        tx.onerror = function () { db.close(); reject(tx.error); };
      });
    });
  }

  function guardar(item) { return comLoja("readwrite", function (l) { return l.put(item); }); }
  function remover(id) { return comLoja("readwrite", function (l) { return l.delete(id); }); }
  function tudo() { return comLoja("readonly", function (l) { return l.getAll(); }); }

  /* ------------------------------------------------------------ contagem */

  function avisar(quantos) {
    document.dispatchEvent(
      new CustomEvent("nutriplan:fila", { detail: { pendentes: quantos } })
    );
  }

  function recontar() {
    return tudo().then(function (itens) {
      avisar((itens || []).length);
      return itens || [];
    });
  }

  /* -------------------------------------------------------------- envio */

  function enviar(item) {
    var corpo = new URLSearchParams(item.dados);
    return fetch(item.url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "fetch",
      },
      body: corpo,
    });
  }

  function drenar() {
    if (!navigator.onLine) return Promise.resolve();

    return tudo().then(function (itens) {
      /* Em série e não em paralelo: são poucas, e a ordem importa quando duas
       * marcações tocam a mesma refeição. */
      return (itens || []).reduce(function (antes, item) {
        return antes.then(function () {
          return enviar(item)
            .then(function (r) {
              /* 4xx é o servidor recusando o conteúdo — reenviar não conserta,
               * e manter na fila faria a pessoa carregar para sempre um item
               * que nunca vai passar. Sai da fila. */
              if (r.ok || (r.status >= 400 && r.status < 500)) return remover(item.op_id);
            })
            .catch(function () { /* rede caiu de novo: fica para a próxima */ });
        });
      }, Promise.resolve());
    }).then(recontar);
  }

  /* ---------------------------------------------------- interceptação */

  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!form || form.tagName !== "FORM") return;
    if (form.method.toLowerCase() !== "post" || !permitida(form.action)) return;
    /* Online e com fetch: o caminho normal segue. A fila é para a falta de
     * rede, não um substituto do POST. */
    if (navigator.onLine) return;

    evento.preventDefault();

    var dados = {};
    new FormData(form).forEach(function (v, k) { dados[k] = v; });
    dados.op_id = identificador();

    guardar({ op_id: dados.op_id, url: form.action, dados: dados, em: Date.now() })
      .then(recontar)
      .then(function () {
        /* A tela precisa reagir: sem retorno, marcar offline parece não ter
         * funcionado e a pessoa toca de novo, enfileirando duas vezes. */
        form.dispatchEvent(
          new CustomEvent("nutriplan:enfileirado", { bubbles: true, detail: dados })
        );
      });
  });

  window.addEventListener("online", drenar);
  document.addEventListener("DOMContentLoaded", function () {
    recontar().then(drenar);
  });

  /* Bônus onde existe: o navegador reenvia mesmo com a aba fechada. */
  if ("serviceWorker" in navigator && "SyncManager" in window) {
    navigator.serviceWorker.ready
      .then(function (reg) { return reg.sync.register("nutriplan-fila"); })
      .catch(function () { /* sem sync em segundo plano, o evento online basta */ });
  }

  /* ------------------------------------------------------------ a faixa */

  document.addEventListener("nutriplan:fila", function (evento) {
    var faixa = document.querySelector("[data-fila]");
    if (!faixa) return;
    var quantos = evento.detail.pendentes;
    faixa.hidden = quantos === 0;
    if (quantos) {
      var texto = faixa.querySelector("[data-fila-texto]");
      texto.textContent =
        quantos === 1
          ? "1 marcação esperando conexão"
          : quantos + " marcações esperando conexão";
    }
  });

  /* Retorno imediato ao enfileirar: sem ele, marcar offline parece não ter
   * funcionado e a pessoa toca de novo. O formulário some da tela como se
   * tivesse sido enviado, porque do ponto de vista dela foi. */
  document.addEventListener("nutriplan:enfileirado", function (evento) {
    var form = evento.target;
    if (form && form.classList) form.classList.add("set-row--done");
  });

  window.NutriPlanFila = { drenar: drenar, recontar: recontar, permitida: permitida };
})();
