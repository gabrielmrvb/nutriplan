/* Instalação do app, registro do service worker e assinatura das notificações.
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

  instalacao();

  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.register("/sw.js").then(function (registration) {
    if (!button) return;

    /* ACHADO A2 — esconder o botão sem corrigir o texto deixava instrução
       órfã na tela.

       O `return` daqui escondia o controle e saía SEM chamar `say()`, então
       a frase que o servidor escreve continuava de pé: "Ative para receber
       um aviso 10 minutos antes de cada refeição". O cartão mandava ativar
       uma coisa que não tinha como ativar. Todos os outros ramos deste
       arquivo atualizam a frase; só este não atualizava.

       Medido em produção: `NUTRIPLAN_VAPID_KEY` é string vazia, e o
       navegador suporta Notification, PushManager e serviceWorker. Ou seja,
       o ramo que disparava era o da CHAVE, e a tela dizia que o problema era
       a pessoa não ter clicado.

       As duas causas dizem coisas diferentes porque pedem coisas diferentes:
       navegador sem suporte é do aparelho de quem lê, chave ausente é
       nosso. Inventar chave não é opção — o estado é real, e o que estava
       errado era a tela mentir sobre ele. */
    if (!supported || !window.NUTRIPLAN_VAPID_KEY) {
      button.hidden = true;
      say(
        supported
          ? "Os lembretes ainda não estão disponíveis. Nada para fazer aqui por enquanto."
          : "Este navegador não recebe lembretes. O resto do app funciona normalmente."
      );
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


  /* ------------------------------------------------------------------ *
   * Convite de instalação
   * ------------------------------------------------------------------ */

  /* Android e desktop: o navegador avisa quando o site cumpre os requisitos
   * (manifest válido, service worker, HTTPS) e deixa a gente escolher a hora
   * de perguntar. iPhone: o Safari não dispara evento nenhum e não tem API de
   * instalação — a única saída é ensinar o caminho do menu Compartilhar.
   *
   * Em ambos, o convite só aparece para quem ainda não instalou. Repetir
   * "instale o app" para quem já instalou é o tipo de banner que faz a pessoa
   * ignorar todos os outros avisos do app.
   */
  function instalacao() {
    var banner = document.querySelector("[data-install]");
    if (!banner) return;

    var dica = banner.querySelector("[data-install-hint]");
    var instalar = banner.querySelector("[data-install-go]");
    var CHAVE = "nutriplan_pwa_dismissed";
    //: Chaves de versões anteriores. Continuam sendo lidas porque trocar o
    //: nome não pode ressuscitar o convite justamente para quem já disse não.
    var CHAVES_ANTIGAS = ["pwa_prompt_dismissed", "nutriplan:convite-dispensado-em"];
    var convite = null;

    function jaInstalado() {
      return (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true
      );
    }

    function ehIOS() {
      // iPadOS moderno se apresenta como Mac; o toque é o que o denuncia.
      var ua = window.navigator.userAgent;
      return /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && "ontouchend" in document);
    }

    /* Fechou uma vez, não volta mais neste aparelho.
     *
     * Houve uma versão com prazo de sete dias, na ideia de que quem fecha na
     * primeira visita ainda não sabe se o app presta. A prática desmentiu: um
     * convite que reaparece é um convite que a pessoa já respondeu, e
     * perguntar de novo é insistência. Quem mudar de ideia instala pelo menu
     * do próprio navegador, que é onde essa opção mora de todo jeito.
     *
     * A chave antiga continua sendo lida para quem já tinha recusado antes
     * desta mudança — trocar o nome da chave não pode ressuscitar o convite
     * justamente para quem já disse não. */
    function dispensado() {
      try {
        var loja = window.localStorage;
        if (loja.getItem(CHAVE) === "true") return true;
        for (var i = 0; i < CHAVES_ANTIGAS.length; i++) {
          if (loja.getItem(CHAVES_ANTIGAS[i])) return true;
        }
        return false;
      } catch (e) {
        // Modo privado pode recusar o armazenamento. Sem memória, o convite
        // reaparece na próxima visita — chato, mas melhor que quebrar.
        return false;
      }
    }

    /* Esconder não basta: a barra é `position: fixed`, então não ocupa espaço
     * no layout e pousa em cima do rodapé da página. A classe no `body` é o
     * que faz a página reservar a altura dela — e some junto com o convite. */
    function esconder() {
      banner.hidden = true;
      document.body.classList.remove("tem-convite");
    }

    function dispensar() {
      esconder();
      try {
        window.localStorage.setItem(CHAVE, "true");
      } catch (e) {}
    }

    function mostrar() {
      if (jaInstalado() || dispensado()) return;
      banner.hidden = false;
      document.body.classList.add("tem-convite");
    }

    /* Quatro maneiras de sair, e todas ligadas no documento em vez de nos
     * botões.
     *
     * Delegação e não `botao.onclick` porque um handler preso a um elemento
     * específico depende de aquele elemento existir no instante em que este
     * código roda. Preso ao documento, funciona mesmo que o cartão seja
     * redesenhado depois — e um convite que não fecha é o pior defeito que
     * este app já teve. */
    document.addEventListener("click", function (evento) {
      if (banner.hidden) return;

      // `closest` só existe em Element. Clique que nasce em nó de texto ou no
      // próprio documento chega aqui como outra coisa, e sem esta guarda o
      // handler quebraria — deixando o convite preso na tela, que é
      // exatamente o defeito que ele veio consertar.
      var alvo = evento.target;
      if (!alvo || typeof alvo.closest !== "function") return;

      if (alvo.closest("[data-install-close]")) {
        evento.preventDefault();
        dispensar();
        return;
      }

      // Toque fora do cartão também dispensa. Sem cortina escura por cima da
      // tela: a cortina seria exatamente o bloqueio que este convite não pode
      // causar. O clique continua chegando ao que estiver embaixo.
      if (!alvo.closest("[data-install]")) dispensar();
    });

    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && !banner.hidden) dispensar();
    });

    window.addEventListener("beforeinstallprompt", function (event) {
      // Segurar o evento é o que troca o banner do navegador (que aparece na
      // hora que ele quiser) por este, que aparece dentro do layout do app.
      event.preventDefault();
      convite = event;
      mostrar();
    });

    window.addEventListener("appinstalled", dispensar);

    if (instalar) {
      instalar.addEventListener("click", function () {
        if (!convite) return;
        convite.prompt();
        convite.userChoice.then(function () {
          // Aceitou ou recusou, o convite sai da tela: o evento é de uso único
          // e insistir na mesma visita é o que faz banner virar praga.
          dispensar();
          convite = null;
        });
      });
    }

    if (ehIOS() && !jaInstalado()) {
      if (dica) {
        dica.textContent = "No Safari: toque em Compartilhar e depois em \u201cAdicionar \u00e0 Tela de In\u00edcio\u201d.";
      }
      // Sem `beforeinstallprompt` no iOS, o botão "Instalar" não teria o que
      // fazer — um botão que não faz nada é pior que botão nenhum.
      if (instalar) instalar.hidden = true;
      mostrar();
    }
  }

  /* Sair da conta leva as páginas em cache junto.
   *
   * O cache de navegação guarda HTML autenticado — nome, peso, dieta e treino
   * da pessoa. Num aparelho compartilhado, deixar isso para trás depois de sair
   * seria entregar o dado ao próximo que abrir o app sem senha nenhuma.
   *
   * Só o cache de PÁGINAS é apagado. CSS e ícones ficam: não têm nada pessoal,
   * e derrubá-los faria a próxima abertura baixar tudo de novo.
   *
   * Roda sempre que a tela abre sem sessão — o que cobre sair pelo botão,
   * a sessão vencer e o token ser invalidado do outro lado. */
  function limparPaginas() {
    if (!window.caches) return Promise.resolve();
    return caches.keys().then(function (nomes) {
      return Promise.all(
        nomes
          .filter(function (n) { return n.indexOf("-paginas") !== -1; })
          .map(function (n) { return caches.delete(n); })
      );
    }).catch(function () { /* sem cache para limpar, e so */ });
  }

  /* SEGUNDA camada: qualquer tela aberta sem sessao. */
  if (document.body && document.body.dataset.autenticado === "0") {
    limparPaginas();
  }

  /* TERCEIRA camada: a pagina restaurada do bfcache.
   *
   * As duas camadas acima limpam o cache do SERVICE WORKER. O botao Voltar nao
   * passa por ele: o navegador guarda a pagina JA RENDERIZADA num cache
   * proprio (bfcache) e a devolve viva, sem rede e sem service worker. Se a
   * sessao terminou nesse meio tempo, a tela da pessoa anterior reaparece
   * inteira — nome, peso, dieta.
   *
   * MEDIDO no Chromium deste ambiente: depois do logout, Voltar re-requisitou
   * a pagina e caiu no login, ou seja o vazamento NAO se reproduziu aqui. Mas
   * o Safari do iPhone e a plataforma principal deste PWA, ele restaura com
   * mais folga, e ignora o `Clear-Site-Data` que `SairView` manda. Esta camada
   * e a que cobre esse caso.
   *
   * REVALIDA EM VEZ DE RECARREGAR SEMPRE: `location.reload()` cego custaria
   * uma ida ao servidor e a rolagem perdida em TODO Voltar dentro da propria
   * sessao, que e o uso normal. `redirect: "manual"` faz o 302 do login chegar
   * como resposta opaca, e e so nesse caso que a tela e trocada. */
  window.addEventListener("pageshow", function (evento) {
    if (!evento.persisted) return;
    if (!document.body || document.body.dataset.autenticado !== "1") return;

    fetch(location.href, {
      method: "HEAD",
      cache: "no-store",
      redirect: "manual",
      credentials: "same-origin",
    }).then(function (r) {
      /* `opaqueredirect` e o 302 para o login; 401/403 cobrem quem responder
       * assim. Falha de rede NAO derruba a tela: sem conexao, a pessoa que
       * ainda esta logada continua vendo o app offline, que e o produto. */
      if (r.type === "opaqueredirect" || r.status === 401 || r.status === 403) {
        location.reload();
      }
    }).catch(function () { /* offline: deixa a tela como esta */ });
  });

  /* PRIMEIRA camada: o proprio clique em "Sair".
   *
   * Ela nao substitui a de cima — antecipa. A camada anonima depende de a
   * pagina SEGUINTE chegar, e se a rede cair no meio do logout a sessao pode
   * acabar no servidor sem nenhuma tela nova aparecer. Limpar no submit custa
   * nada: quem desistisse do logout so perderia paginas guardadas, que voltam
   * na proxima visita.
   *
   * `capture` porque o formulario faz `submit` e a pagina comeca a sair: sem
   * capturar na descida, o ouvinte pode nao chegar a rodar.
   *
   * O que NENHUMA das duas cobre: aparelho que fica offline logo depois de a
   * sessao expirar no servidor. Nenhuma tela anonima chega, e o worker nao tem
   * como adivinhar que a sessao morreu. Esta em `docs/privacidade-local.md`. */
  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!form || form.tagName !== "FORM") return;
    if (new URL(form.action, location.origin).pathname !== "/conta/sair/") return;
    limparPaginas();
  }, true);

  /* ------------------------------------------------------ olho da senha */

  /* Mostrar e esconder a senha.
   *
   * Digitar senha forte às cegas num teclado de celular é onde a pessoa erra e
   * desiste — e "senha incorreta" depois de três tentativas não diz se o erro
   * foi de dedo ou de memória.
   *
   * `aria-pressed` e não uma classe: o estado é exatamente o que o atributo
   * descreve, e quem usa leitor de tela recebe "pressionado" sem eu escrever
   * nada a mais. O CSS lê o mesmo atributo para riscar ou não o ícone.
   *
   * O foco volta para o campo depois de alternar: quem tocou no olho estava
   * digitando, e devolver o cursor evita um segundo toque.
   */
  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-ver-senha]");
    if (!botao) return;

    var campo = botao.parentElement.querySelector("input");
    if (!campo) return;

    var mostrando = campo.type === "text";
    campo.type = mostrando ? "password" : "text";
    botao.setAttribute("aria-pressed", String(!mostrando));
    botao.setAttribute(
      "aria-label", mostrando ? "Mostrar a senha" : "Ocultar a senha"
    );

    /* O cursor volta para o fim do texto: trocar o `type` do campo o manda
     * para a posição zero, e quem estava no meio de digitar perderia o lugar. */
    var fim = campo.value.length;
    campo.focus();
    try { campo.setSelectionRange(fim, fim); } catch (e) { /* type=email não aceita */ }
  });

  /* ------------------------------------------------ retorno ao enviar */

  /* O toque precisa dizer "recebi" antes do servidor responder.
   *
   * "Comi esta" e "Pulei" fazem POST e esperam o redirecionamento. Numa rede
   * de academia isso leva segundos, e nesses segundos a tela fica idêntica ao
   * que era: nada se move, e a pessoa toca de novo. O segundo toque não
   * duplica nada — `update_or_create` cuida disso —, mas ensina que o botão
   * não funciona.
   *
   * `setTimeout(0)` e não desabilitar na hora: desabilitar dentro do próprio
   * evento de `submit` faz o navegador descartar o `name`/`value` do botão em
   * parte dos casos, e é justamente o `status=done` que viajaria nele.
   *
   * O caminho de VOLTA reabilita: quem toca em "voltar" recebe a página do
   * cache do navegador exatamente como saiu — com o botão travado — e ficaria
   * olhando um formulário morto. */
  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!form || form.tagName !== "FORM") return;
    if ((form.method || "").toLowerCase() !== "post") return;
    if (evento.defaultPrevented) return;

    var botao = form.querySelector("[type=submit]:focus") ||
                document.activeElement;
    if (!botao || !form.contains(botao) || botao.type !== "submit") {
      botao = form.querySelector("[type=submit]");
    }
    if (!botao) return;

    setTimeout(function () {
      botao.disabled = true;
      botao.setAttribute("aria-busy", "true");
    }, 0);
  });

  window.addEventListener("pageshow", function () {
    document.querySelectorAll("[type=submit][aria-busy]").forEach(function (b) {
      b.disabled = false;
      b.removeAttribute("aria-busy");
    });
  });

  /* Enfileirado sem rede: o envio não vai acontecer agora, então o botão
   * volta. Sem isto, marcar uma refeição offline deixaria o botão travado
   * até a pessoa recarregar a página. */
  document.addEventListener("nutriplan:enfileirado", function (evento) {
    var form = evento.target;
    if (!form || !form.querySelectorAll) return;
    form.querySelectorAll("[type=submit]").forEach(function (b) {
      b.disabled = false;
      b.removeAttribute("aria-busy");
    });
  });

  /* MAPA DE ÁREAS — só as conveniências.
   *
   * O `<details>` já abre e fecha sozinho no clique, e continua funcionando
   * com o JavaScript desligado. O que falta é o que todo menu aberto deve:
   * fechar no Escape e fechar quando se toca fora dele. Sem isso, um menu
   * aberto no celular fica de pé enquanto a pessoa rola a tela inteira.
   *
   * Nada aqui é foco preso: `<details>` foi escolhido justamente para não
   * precisar de `inert`, que foi o conserto caro do convite de instalação. */
  var mapa = document.querySelector("[data-mapa]");
  if (mapa) {
    document.addEventListener("keydown", function (evento) {
      if (evento.key !== "Escape" || !mapa.open) return;
      mapa.open = false;
      /* O foco volta para o botão que abriu: fechar com o teclado e deixar o
       * foco no nada faria o Tab seguinte recomeçar do topo da página. */
      var botao = mapa.querySelector("summary");
      if (botao) botao.focus();
    });

    document.addEventListener("click", function (evento) {
      if (mapa.open && !mapa.contains(evento.target)) mapa.open = false;
    });
  }

})();
