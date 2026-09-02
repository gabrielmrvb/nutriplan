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

  /* De quem é esta sessão. Vazio quando ninguém está logado.
   *
   * A fila vive no IndexedDB, que pertence ao NAVEGADOR e não à sessão: ela
   * atravessa o logout inteira. Sem dono, uma operação que a pessoa A
   * enfileirou sem rede seria ENVIADA usando a sessão de quem estivesse
   * autenticado depois — e o drenar acontece no primeiro carregamento de
   * página, sem ninguém pedir.
   *
   * O envio é o que está provado. A GRAVAÇÃO na outra conta não: medido com a
   * stack real, o CSRF do item fica velho depois de qualquer login e o
   * servidor recusa antes da view. Corrigir o cliente continua valendo — uma
   * proteção que só funciona porque outra camada é atravessada antes não é
   * desenho, é sorte —, mas a afirmação honesta para aqui.
   *
   * Apagar a fila no logout fecharia esse caminho e criaria outro problema:
   * a pessoa perderia a água e as refeições que marcou sem rede. Por isso a
   * fila é SEPARADA por dono, e não esvaziada — o que é de A continua lá,
   * esperando A voltar.
   */
  function dono() {
    return (document.body && document.body.dataset.usuario) || "";
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

  /* Só o que é DESTA pessoa. Igualdade estrita, e nenhum atalho.
   *
   * Sem dono NÃO quer dizer "é de quem está logado". Quer dizer que não dá
   * para saber de quem é — e adivinhar é o vazamento que esta separação
   * existe para fechar. A primeira versão desta função ADOTAVA o item sem
   * dono para o usuário atual, com a desculpa de que a janela era curta.
   * Janela curta para vazar dado de outra pessoa continua sendo vazar.
   */
  function meus() {
    var eu = dono();
    if (!eu) return Promise.resolve([]);
    return tudo().then(function (itens) {
      return (itens || []).filter(function (i) { return i.dono === eu; });
    });
  }

  /* Operações guardadas antes de a separação existir.
   *
   * Não são enviadas por ninguém, e não são apagadas. Não enviar porque não
   * há como saber de quem são; não apagar porque podem ser água ou refeição
   * que alguém marcou de verdade, sem rede.
   *
   * Ficam aqui esperando uma decisão de produto — está no backlog como
   * RECUPERAÇÃO/EXPIRAÇÃO DE FILA OFFLINE LEGADA. Esta função existe para que
   * essa decisão possa ser tomada olhando o que tem, em vez de no escuro.
   */
  function emQuarentena() {
    return tudo().then(function (itens) {
      return (itens || []).filter(function (i) { return !i.dono; });
    });
  }

  /* A conta foi EXCLUÍDA — não é a mesma coisa que sair.
   *
   * Sair guarda a fila para a volta. Excluir significa que não há volta: a
   * conta que receberia aquelas operações deixou de existir no servidor, e
   * mantê-las é guardar dado pessoal de alguém que pediu para sumir.
   *
   * O gatilho é o SERVIDOR confirmando a exclusão, e não o clique em
   * "Excluir": tentativa não é conclusão, e se o POST falhasse a pessoa
   * perderia o que marcou sem rede com a conta ainda de pé.
   *
   * Remove só o que é daquele dono. Fila de outra conta no mesmo aparelho e
   * itens em quarentena continuam onde estão.
   */
  function esquecerConta(quem) {
    if (!quem) return Promise.resolve();
    return tudo().then(function (itens) {
      return Promise.all(
        (itens || [])
          .filter(function (i) { return i.dono === quem; })
          .map(function (i) { return remover(i.op_id); })
      );
    }).catch(function () { /* sem fila, e so */ });
  }

  /* ------------------------------------------------------------ contagem */

  function avisar(quantos) {
    document.dispatchEvent(
      new CustomEvent("nutriplan:fila", { detail: { pendentes: quantos } })
    );
  }

  function recontar() {
    return meus().then(function (itens) {
      avisar((itens || []).length);
      return itens || [];
    });
  }

  /* -------------------------------------------------------------- envio */

  /* O dono viaja no CABEÇALHO, e o servidor o usa como pré-condição.
   *
   * Escolher a conta continua sendo do servidor, por `request.user`. Este
   * cabeçalho diz outra coisa: "esta operação foi criada esperando a sessão de
   * fulano". Se a sessão atual for de outra pessoa, o servidor recusa antes de
   * mudar qualquer coisa.
   *
   * Isso é necessário porque esta aba pode estar VELHA: cookie de sessão é do
   * navegador, não da aba. A pessoa pode ter saído e outra entrado numa aba
   * vizinha, e daqui não há como saber. */
  /* O token do MOMENTO DO ENVIO, e não o que estava no formulário.
   *
   * A fila copia o `FormData` inteiro, então o item guarda o
   * `csrfmiddlewaretoken` de quando a pessoa marcou a água sem rede. Esse
   * token é de transporte, não é dado da operação: `login()` chama
   * `rotate_token`, e depois de qualquer entrada — inclusive a da própria
   * pessoa voltando — ele fica velho.
   *
   * Medido: o Django lê `csrfmiddlewaretoken` do POST PRIMEIRO e só olha o
   * cabeçalho se o campo estiver vazio. Acrescentar `X-CSRFToken` sem trocar
   * o campo não adiantaria nada.
   */
  function tokenAtual() {
    var achado = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return achado ? achado[2] : "";
  }

  function enviar(item) {
    var dados = {};
    Object.keys(item.dados).forEach(function (k) { dados[k] = item.dados[k]; });
    var atual = tokenAtual();
    if (atual) dados.csrfmiddlewaretoken = atual;

    var corpo = new URLSearchParams(dados);
    var cabecalhos = {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-Requested-With": "fetch",
      "X-NutriPlan-Replay": "1",
    };
    if (item.dono) cabecalhos["X-NutriPlan-Dono"] = item.dono;
    return fetch(item.url, {
      method: "POST",
      credentials: "same-origin",
      headers: cabecalhos,
      body: corpo,
      /* Sem seguir redirect. Um POST recusado por falta de sessão vira 302
       * para o login, e o `fetch` seguiria até uma página 200 — que o
       * tratamento abaixo leria como sucesso e apagaria a operação. */
      redirect: "manual",
    });
  }

  function drenar() {
    if (!navigator.onLine) return Promise.resolve();
    /* Sem sessão não há para onde drenar, e tentar seria mandar a operação de
     * alguém para um servidor que a atribuiria a quem quer que estivesse
     * logado. O `online` dispara sem perguntar quem está na tela. */
    if (!dono()) return Promise.resolve();

    return meus().then(function (itens) {
      /* Em série e não em paralelo: são poucas, e a ordem importa quando duas
       * marcações tocam a mesma refeição. */
      return (itens || []).reduce(function (antes, item) {
        return antes.then(function () {
          return enviar(item)
            .then(function (r) {
              /* 4xx é o servidor recusando o conteúdo — reenviar não conserta,
               * e manter na fila faria a pessoa carregar para sempre um item
               * que nunca vai passar. Sai da fila. */
              /* Só sai da fila com PROVA de aplicação.
               *
               * A regra publicada era "2xx ou 4xx removem", e ela foi medida:
               * depois de qualquer login o token do item fica velho, o CSRF
               * responde 403, e o item era apagado. A pessoa perdia a
               * marcação que fez sem rede — inclusive só por ter saído e
               * voltado.
               *
               * Agora a remoção exige sucesso. O que PRESERVA:
               *
               *   503 ...... o servidor dizendo que a operação não pode ser
               *              aplicada agora (sessão, dono ou CSRF)
               *   401/403 .. autenticação ou CSRF por qualquer outro caminho
               *   5xx ...... erro do servidor
               *   redirect . sem sessão, não há o que sincronizar
               *
               * 4xx de CONTEÚDO continua removendo: um valor que o servidor
               * recusa não melhora com reenvio, e manter faria a pessoa
               * carregar para sempre algo que nunca vai passar. */
              if (r.type === "opaqueredirect") return;
              if (r.status === 401 || r.status === 403) return;
              if (r.status >= 500) return;
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

    guardar({
      op_id: dados.op_id,
      url: form.action,
      dados: dados,
      em: Date.now(),
      dono: dono(),
    })
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

  /* A conta acabou de ser excluída? O servidor diz, e diz uma vez só. */
  if (document.body && document.body.dataset.contaExcluida) {
    esquecerConta(document.body.dataset.contaExcluida).then(recontar);
  }

  window.NutriPlanFila = {
    drenar: drenar,
    recontar: recontar,
    permitida: permitida,
    dono: dono,
    meus: meus,
    emQuarentena: emQuarentena,
    esquecerConta: esquecerConta,
  };
})();
