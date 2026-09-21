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
  /* O estado "a pessoa negou" é um VALOR, e não `null`. `enable()` devolvia
   * `null` depois de escrever "Permissão negada…", e o `.then` do clique
   * chamava `render(registration, null)` — que caía no ramo sem inscrição e
   * sobrescrevia a frase 0,1 ms depois (UX P1-05, medido com
   * MutationObserver). Botão e texto voltavam ao início; quem tinha
   * bloqueado as notificações nunca lia o que fazer. */
  var NEGADA = "negada";
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
      /* AS DUAS CAUSAS CONTINUAM DIFERENTES, e agora até na forma.

         Navegador sem suporte é do aparelho de quem lê: a frase fica, porque
         ela é informação — a pessoa pode abrir o app noutro navegador.

         Chave ausente é nosso, e não há nada que quem lê possa fazer. Um cartão
         inteiro dizendo "nada para fazer aqui por enquanto" é placeholder de
         funcionalidade inexistente, e some junto com o botão.

         O que o A2 proibia — esconder o botão e deixar a frase mandando ativar
         — não volta em nenhum dos dois: ou a frase é corrigida, ou o cartão
         inteiro sai. */
      if (supported) {
        var cartao = status && status.closest("section");
        if (cartao) cartao.hidden = true;
      } else {
        say("Este navegador não recebe lembretes. O resto do app funciona normalmente.");
      }
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
      say("Você recebe um aviso até 20 minutos antes de cada refeição.");
    } else if (Notification.permission === "denied") {
      /* Quem já negou lê isso ao abrir a tela, e não só depois de tocar. O
       * botão fica: o navegador não pergunta de novo, mas a pessoa pode
       * liberar nas configurações e voltar. */
      button.textContent = "Ativar lembretes das refeições";
      say("Permissão negada. Dá para liberar nas configurações do navegador.");
    } else {
      button.textContent = "Ativar lembretes das refeições";
      say("Um aviso até 20 minutos antes de cada refeição, no celular.");
    }

    button.onclick = function () {
      button.disabled = true;
      var action = subscription ? disable(subscription) : enable(registration);
      action
        .then(function (next) {
          button.disabled = false;
          if (next === NEGADA) return;
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
        return NEGADA;
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

    //: Quantos dias "Agora não" adia o convite.
    //:
    //: Trinta, o teto da faixa que a campanha define (7 a 30). Perto do teto
    //: porque a decisão anterior deste arquivo foi tornar a dispensa
    //: DEFINITIVA — "um convite que reaparece é um convite que a pessoa já
    //: respondeu" —, e adiar pouco reintroduziria a insistência que aquela
    //: decisão tirou. O "×" continua definitivo; só o "Agora não" adia.
    var DIAS_DE_ADIAMENTO = 30;
    var CHAVE_ADIADO = "nutriplan_pwa_adiado_ate";

    function adiar() {
      esconder();
      try {
        var ate = Date.now() + DIAS_DE_ADIAMENTO * 24 * 60 * 60 * 1000;
        window.localStorage.setItem(CHAVE_ADIADO, String(ate));
      } catch (e) {}
    }

    function adiado() {
      try {
        var ate = parseInt(window.localStorage.getItem(CHAVE_ADIADO) || "0", 10);
        // Relógio de aparelho anda para trás, e uma data absurdamente no
        // futuro esconderia o convite para sempre. Passou do teto, o
        // adiamento é ignorado — errar mostrando é melhor que errar sumindo.
        var teto = Date.now() + DIAS_DE_ADIAMENTO * 24 * 60 * 60 * 1000;
        return ate > Date.now() && ate <= teto;
      } catch (e) {
        return false;
      }
    }

    /* ONDE O CONVITE NÃO APARECE, e cada item tem motivo próprio.
     *
     * `data-sem-convite` vem do servidor: execução do treino e corrida em
     * andamento são telas de uma coisa só, e um cartão fixo cobrindo o rodapé
     * delas atrapalha a tarefa que a pessoa foi fazer.
     *
     * `dialog[open]` é o drawer de vídeo, que prende o foco. Um convite
     * pousando por cima dele é um segundo pedido de atenção sobre o primeiro.
     */
    function horaRuim() {
      if (document.body.hasAttribute("data-sem-convite")) return true;
      return !!document.querySelector("dialog[open]");
    }

    function mostrar() {
      if (jaInstalado() || dispensado() || adiado() || horaRuim()) return;
      /* BOTÃO SEM EVENTO NÃO APARECE.
       *
       * `beforeinstallprompt` é de uso único: depois de `prompt()` o objeto
       * guardado deixa de valer, e `convite` volta a ser nulo. Se o cartão
       * reaparecesse nesse estado, "Instalar" seria um botão que não faz nada
       * — pior que não ter botão, porque parece que o app quebrou.
       *
       * No iPhone ele já era escondido por outro caminho, e lá o cartão
       * continua útil: o texto é a instrução do menu Compartilhar, que nunca
       * dependeu de evento nenhum. */
      if (instalar) instalar.hidden = !convite;
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

      if (alvo.closest("[data-install-later]")) {
        evento.preventDefault();
        adiar();
        return;
      }

      if (alvo.closest("[data-install-close]")) {
        evento.preventDefault();
        dispensar();
        return;
      }

      // Toque fora do cartão ESCONDE, nesta visita — e não dispensa para
      // sempre: quem tocou num botão da tela com o cartão aberto não
      // respondeu ao convite, respondeu à tela (UX P1-13, D5). Sem cortina
      // escura por cima: a cortina seria exatamente o bloqueio que este
      // convite não pode causar. O clique continua chegando ao que estiver
      // embaixo. Dispensa definitiva só no "×"; adiar só no "Agora não".
      if (!alvo.closest("[data-install]")) esconder();
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

  /* SEGUNDA camada: qualquer tela aberta sem sessao.

     MENOS o shell de offline. Ele sai com `data-autenticado="0"` porque e
     pre-cacheado sem identidade de proposito — nao porque a sessao acabou. O
     worker o entrega quando o servidor demora ou a rede cai, e ler isso como
     "sem sessao" APAGAVA as paginas que a pessoa logada tinha em cache:
     medido em 16/09/2026, todo cold start que virava shell jogava fora o
     cache e transformava a tela seguinte em shell tambem. */
  if (
    document.body &&
    document.body.dataset.autenticado === "0" &&
    !document.body.dataset.shellOffline
  ) {
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

  /* O LINK-BOTÃO TAMBÉM AVISA QUE ESTÁ INDO.
   *
   * `<a class="btn">` que leva a outra tela — "Ver o treino completo",
   * "Começar treino" — ficava mudo entre o toque e a página nova. Numa rede
   * de academia são segundos com a tela idêntica, e a pessoa toca de novo.
   * O `<button type=submit>` já recebe `aria-busy` acima; o link recebe o
   * MESMO nome de estado e a mesma receita visual: a classe é o gancho do
   * CSS (`.btn.is-carregando`, par de `.btn[aria-busy]`), e o atributo é o
   * que o leitor de tela anuncia.
   *
   * A página nova É a confirmação; o estado só cobre o intervalo. Nada aqui
   * afirma sucesso, nada é desligado — o link continua sendo um link, e um
   * segundo toque só repete a mesma navegação.
   *
   * Fica de fora o que NÃO troca esta página: `target` (abre em outra aba),
   * `download`, âncora na mesma tela (`#`), `mailto:` e `javascript:`;
   * clique com modificador ou botão que não é o principal (abre em nova aba,
   * e esta fica); e o que outro ouvinte já cancelou (`defaultPrevented`).
   * Em todos esses, marcar seria prometer uma página que não vem — e a
   * marca nunca seria limpa. */
  document.addEventListener("click", function (evento) {
    if (evento.defaultPrevented || evento.button !== 0) return;
    if (evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
    var alvo = evento.target;
    if (!alvo || typeof alvo.closest !== "function") return;
    var link = alvo.closest("a.btn[href]");
    if (!link || link.classList.contains("is-carregando")) return;
    if (link.hasAttribute("target") || link.hasAttribute("download")) return;
    /* `data-arquivo`: a resposta é um arquivo (Content-Disposition:
     * attachment) e a página não troca — o link de exportar o TCX. Não é
     * `download` porque a view pode responder com redirect e mensagem quando
     * não há treino hoje, e `download` faria o navegador SALVAR aquele HTML. */
    if (link.hasAttribute("data-arquivo")) return;
    var destino = (link.getAttribute("href") || "").trim();
    if (/^(#|mailto:|tel:|sms:|javascript:)/i.test(destino)) return;

    link.classList.add("is-carregando");
    link.setAttribute("aria-busy", "true");
  });

  /* Voltar pelo histórico traz a página do bfcache exatamente como saiu —
   * com o link marcado. Mesmo caminho de volta do botão de envio, acima. */
  window.addEventListener("pageshow", function () {
    document.querySelectorAll(".btn.is-carregando").forEach(function (b) {
      b.classList.remove("is-carregando");
      b.removeAttribute("aria-busy");
    });
  });

  /* O TOQUE OFFLINE APARECE NA TELA NA HORA (UX P1-09 / E02 / E07).
   *
   * Sem rede o formulário não navega: `fila.js` guarda o pedido e dispara
   * `nutriplan:enfileirado` no formulário. Até aqui a tela só devolvia o
   * botão — o número da água continuava o mesmo, a série não aparecia na
   * pastilha, a refeição continuava "pendente". Parecia que não tinha
   * funcionado, e a pessoa tocava de novo, enfileirando duas vezes.
   *
   * Cada tela escreve o que o servidor escreveria, com um selo "aguardando
   * rede" — a nota já existe no HTML, escondida (`[data-aguardando-rede]`),
   * e o JavaScript só a mostra. Nada aqui grava: quando a rede volta, a fila
   * drena e a página recarregada mostra o que o servidor tem. A tela é
   * reconhecida pela AÇÃO do formulário, com as mesmas rotas de `fila.js`. */
  /* O `detail` do evento é o objeto de campos que `fila.js` guardou
   * (`dados`): chave → valor, já sem o `op_id` da página. */
  function valorDoPar(dados, nome) {
    return dados && dados[nome] != null ? String(dados[nome]) : "";
  }
  function mostrarNota(raiz, texto) {
    var nota = raiz.querySelector("[data-aguardando-rede]");
    if (!nota) return;
    nota.textContent = texto;
    nota.hidden = false;
  }
  function aguaEnfileirada(form, dados) {
    /* `[data-agua]` e não `.agua`: a classe só existe no cartão da Home, e a
     * tela de Hidratação ficava muda ao toque sem rede — o anel em 500 e
     * nenhuma nota (avaliação de 16/09/2026, B11). As duas telas levam o
     * marcador e o número em `[data-agua-total]`. */
    var cartao = form.closest("[data-agua]");
    if (!cartao) return;
    var ml = parseInt(valorDoPar(dados, "ml"), 10);
    var valor = cartao.querySelector("[data-agua-total]");
    if (valor && !isNaN(ml)) {
      var atual = parseInt(valor.textContent.replace(/\D/g, ""), 10) || 0;
      var novo = ml === 0 ? 0 : atual + ml;
      valor.textContent = String(novo);
      /* O anel acompanha o número quando a tela diz a meta. */
      var anel = cartao.querySelector("[data-agua-meta]");
      var meta = anel ? parseInt(anel.getAttribute("data-agua-meta"), 10) : NaN;
      if (anel && meta > 0) {
        anel.style.setProperty("--pct", String(Math.min(100, Math.round(novo * 100 / meta))));
      }
    }
    mostrarNota(cartao, "Registrado — aguardando rede.");
  }
  function refeicaoEnfileirada(form) {
    var artigo = form.closest(".meal");
    if (!artigo) return;
    artigo.classList.add("meal--pendente-rede");
    mostrarNota(artigo, "Registrada — aguardando rede.");
  }
  function serieEnfileirada(form, dados) {
    var secao = form.closest(".agora");
    if (!secao) return;
    var pastilha = secao.querySelector(".series__item--atual");
    if (pastilha) {
      pastilha.classList.remove("series__item--atual");
      pastilha.classList.add("series__item--feita", "series__item--pendente-rede");
      var peso = valorDoPar(dados, "weight_kg");
      var reps = valorDoPar(dados, "reps");
      var texto = (peso ? peso : "") + (reps ? "×" + reps : "");
      var carga = pastilha.querySelector(".series__carga, .series__antes");
      if (carga) {
        carga.className = "series__carga num";
        carga.textContent = texto || "✓";
      }
      var proxima = pastilha.nextElementSibling;
      if (proxima && proxima.classList.contains("series__item")) {
        proxima.classList.add("series__item--atual");
      }
    }
    var titulo = secao.querySelector(".series__titulo");
    var numero = titulo && titulo.querySelector("b.num");
    var total = titulo && titulo.querySelector("span.num");
    var botao = form.querySelector(".agora__concluir");
    if (numero) {
      var n = parseInt(numero.textContent, 10);
      var m = total ? parseInt(total.textContent, 10) : NaN;
      if (!isNaN(n)) {
        /* Fechou a última: o título diz "Concluído — 3 de 3", como o
         * servidor diria; o formulário fica, porque a série a mais continua
         * valendo e a página não recarrega sem rede. */
        if (!isNaN(m) && n + 1 > m) {
          numero.textContent = String(m);
          if (titulo.firstChild && titulo.firstChild.nodeType === 3) {
            titulo.firstChild.textContent = "Concluído — ";
          }
        } else {
          numero.textContent = String(n + 1);
        }
        if (botao) botao.textContent = "Concluir série " + (n + 1);
      }
    }
    mostrarNota(secao, "Série guardada — aguardando rede.");
  }
  document.addEventListener("nutriplan:enfileirado", function (evento) {
    var form = evento.target;
    if (!form || !form.getAttribute) return;
    var acao = new URL(form.getAttribute("action") || location.href, location.origin).pathname;
    var dados = evento.detail || {};
    if (/^\/agua\/$/.test(acao)) aguaEnfileirada(form, dados);
    else if (/^\/refeicao\/\d+\/marcar\/$/.test(acao)) refeicaoEnfileirada(form);
    else if (/^\/treino\/agora\/serie\/$/.test(acao)) serieEnfileirada(form, dados);
  });

  /* ONBOARDING — a divisão de treino aparece quando os dias pedem.
   *
   * A etapa 2 pergunta a divisão só a partir de N dias de treino (N vem do
   * servidor em `data-dias-minimos`, lido da tabela do motor). Sem
   * JavaScript o servidor decide do mesmo jeito: recusa o envio sem divisão
   * e reabre a tela com o bloco visível. Aqui o bloco aparece na hora em
   * que a pessoa marca o dia que o torna necessário — e some se ela
   * desmarca — para ninguém enviar e voltar. */
  var revela = document.querySelector("[data-revela-divisao]");
  if (revela) {
    var minimo = parseInt(revela.dataset.diasMinimos, 10) || 0;
    var dias = document.querySelectorAll('input[name="weekdays"]');
    function acertarDivisao() {
      var marcados = 0;
      dias.forEach(function (d) { if (d.checked) marcados++; });
      revela.hidden = marcados < minimo;
    }
    dias.forEach(function (d) { d.addEventListener("change", acertarDivisao); });
    acertarDivisao();
  }

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

/* ------------------------------------------------------------------ */
/* LISTA DE COMPRAS: a marcação vai para o servidor.                   */
/*                                                                     */
/* A caixa avisava que valia "só enquanto a página estiver aberta".    */
/* Quem recarrega no meio do corredor perdia tudo o que já pegou — e   */
/* esta é justamente a tela que se usa andando pelo mercado.           */
/*                                                                     */
/* O pedido manda o ESTADO ABSOLUTO (`marcado=1|0`), nunca "alterne".  */
/* Ele pode chegar duas vezes: a fila offline reenvia quando a resposta */
/* se perde, e um "alterne" reproduzido desfaz o que a pessoa fez. É o  */
/* mesmo defeito que a água pagou para aprender, evitado aqui pela     */
/* FORMA do pedido em vez de por um identificador.                     */
/*                                                                     */
/* A caixa NÃO espera a resposta para mudar de estado: no mercado a    */
/* rede é ruim, e uma caixa que só marca depois do servidor responder  */
/* faz a pessoa tocar duas vezes. Ela marca na hora; o servidor        */
/* alcança depois — e sem rede a fila guarda o pedido.                 */
(function () {
  "use strict";

  var lista = document.querySelector("[data-lista-compras]");
  if (!lista) return;

  function token() {
    var campo = document.querySelector("[name=csrfmiddlewaretoken]");
    return campo ? campo.value : "";
  }

  /* Delegação no DOCUMENTO, e não no `div` do endereço.
   *
   * A primeira versão escutava no próprio `[data-lista-compras]`, que é um
   * elemento vazio e escondido — as caixas não são filhas dele, então o evento
   * nunca chegava e nada era salvo. O `div` guarda o endereço; quem escuta é o
   * documento. */
  document.addEventListener("change", function (evento) {
    var caixa = evento.target;
    if (!caixa || !caixa.hasAttribute || !caixa.hasAttribute("data-marcar")) return;

    var corpo = new URLSearchParams();
    corpo.set("csrfmiddlewaretoken", token());
    /* O item avulso é chaveado pelo próprio `pk`; o do cardápio, pela
       tríade (alimento, opção, dia). A mesma rota atende os dois. */
    if (caixa.hasAttribute("data-avulso")) {
      corpo.set("avulso_id", caixa.getAttribute("data-avulso"));
    } else {
      corpo.set("food_id", caixa.getAttribute("data-food"));
      corpo.set("opcao", caixa.getAttribute("data-opcao"));
      corpo.set("semana", caixa.getAttribute("data-semana"));
    }
    corpo.set("marcado", caixa.checked ? "1" : "0");

    fetch(lista.getAttribute("data-lista-compras"), {
      method: "POST",
      body: corpo,
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "fetch",
      },
      credentials: "same-origin",
    }).catch(function (erro) {
      /* Sem rede o `fetch` rejeita, e a caixa fica marcada na tela. Isso é
         deliberado: perder o risco de quem já pegou o produto é pior que uma
         marcação que o servidor ainda não viu. O console guarda o erro em vez
         de ele sumir como rejeição não tratada. */
      console.error("NutriPlan: não consegui salvar a marcação", erro);
    });
  });
})();

/* ---------------------------------------------------------------- envio
 * Botão que trava depois do primeiro toque. O plano gratuito do Render acorda
 * em ~50 s, e nesse intervalo um segundo toque em "Entrar" manda o POST duas
 * vezes — e o segundo chega com o CSRF da sessão que o primeiro já trocou.
 *
 * Delegado no `document`, como o resto deste arquivo: qualquer formulário
 * que marque o botão com `data-envia` ganha o comportamento. O texto de
 * espera vem de `data-envia-texto`, para o rótulo continuar sendo do
 * template e não do script. O `setTimeout` de zero é o que deixa o
 * navegador serializar o formulário ANTES de o botão ficar `disabled` —
 * botão desabilitado não entra no corpo, e um `submit` com `name` sumiria. */
(function () {
  "use strict";
  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!form || !form.querySelector) return;
    var botao = form.querySelector("[data-envia]");
    if (!botao || botao.disabled) return;
    var texto = botao.getAttribute("data-envia-texto");
    setTimeout(function () {
      botao.disabled = true;
      botao.setAttribute("aria-busy", "true");
      if (texto) botao.textContent = texto;
    }, 0);
  });
})();

/* ==========================================================================
   MOVIMENTO — sanfonas, ecos e contagens (15/09/2026)

   Fora do bloco do service worker de propósito: nada aqui depende dele, e
   um navegador sem SW continua tendo sanfona que abre com suavidade.

   Os tempos vêm dos tokens `--mov-*` do CSS (uma fonte só), e TUDO consulta
   `prefers-reduced-motion` antes de mexer: quem pediu menos movimento recebe
   o comportamento nativo, sem nenhuma animação em JavaScript.
   ========================================================================== */
(function () {
  "use strict";
  var raiz = document.documentElement;

  function reduzido() {
    return !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  /* Lê um token de tempo do `:root`, em milissegundos. */
  function tempo(nome, padrao) {
    var valor = getComputedStyle(raiz).getPropertyValue(nome).trim();
    var numero = parseFloat(valor);
    if (!numero) return padrao;
    return valor.indexOf("ms") > -1 ? numero : numero * 1000;
  }
  function token(nome, padrao) {
    var valor = getComputedStyle(raiz).getPropertyValue(nome).trim();
    return valor || padrao;
  }
  var CURVA = token("--ease", "cubic-bezier(.2, .8, .3, 1)");
  var PASSO = token("--mov-passo", "6px");

  /* SANFONAS — `<details>` abre e fecha com a altura acompanhando.
   *
   * O navegador troca `open` de uma vez: a refeição saltava de 44 para
   * 422 px sem quadro intermediário (baseline de 15/09/2026). Aqui o toque
   * no `summary` é interceptado, a altura de partida e de chegada são
   * MEDIDAS, e o `<details>` anima entre as duas com `overflow: clip`
   * enquanto o conteúdo entra (ou sai) em fade. Ao terminar, os estilos
   * em linha saem e o elemento volta a ser um `<details>` comum — o CSS de
   * `[open]` continua mandando, o `toggle` continua disparando, o foco
   * continua no `summary`, e nada rola.
   *
   * Fica de fora: quem pedir `data-sem-animacao`, e todo toque que caiu
   * num controle dentro do `summary`. Sem `Element.animate` (ou com movimento reduzido), o clique
   * segue nativo. */
  document.addEventListener("click", function (evento) {
    var summary = evento.target.closest && evento.target.closest("summary");
    if (!summary) return;
    var details = summary.parentElement;
    if (!details || details.tagName !== "DETAILS") return;
    if (details.hasAttribute("data-sem-animacao")) return;
    if (evento.target.closest("a, button, input, select, textarea, label")) return;
    if (!details.animate || reduzido()) return;
    evento.preventDefault();
    if (details.dataset.animando) return;
    /* O toque nativo já foca o `summary`; o interceptado também deve. */
    if (document.activeElement !== summary && summary.focus) summary.focus({ preventScroll: true });
    if (details.open) fecharSanfona(details, summary);
    else abrirSanfona(details, summary);
  });

  function conteudoDe(details, summary) {
    return Array.prototype.filter.call(details.children, function (filho) { return filho !== summary; });
  }

  function abrirSanfona(details, summary) {
    var de = details.offsetHeight;
    details.dataset.animando = "1";
    details.style.overflow = "clip";
    details.open = true;
    var ate = details.offsetHeight;
    details.style.height = de + "px";
    var ms = tempo("--mov-expansao", 250);
    var anim = details.animate([{ height: de + "px" }, { height: ate + "px" }], { duration: ms, easing: CURVA });
    conteudoDe(details, summary).forEach(function (filho) {
      filho.animate([{ opacity: 0, transform: "translateY(calc(-1 * " + PASSO + "))" }, { opacity: 1, transform: "none" }],
                    { duration: ms, easing: CURVA, delay: ms * .2, fill: "backwards" });
    });
    anim.onfinish = anim.oncancel = function () { limpar(details); };
  }

  function fecharSanfona(details, summary) {
    var de = details.offsetHeight;
    /* A altura fechada é MEDIDA fechando e reabrindo antes de qualquer
       pintura — assim o CSS de `[open]` (a margem do `summary`, por
       exemplo) entra na conta, e o fim da animação não dá um salto. */
    var rolagem = window.scrollY;
    details.open = false;
    var ate = details.offsetHeight;
    details.open = true;
    /* O documento encurtou por um instante e a rolagem pode ter sido
       fixada no layout fechado; com a página alta de novo, ela volta. */
    if (window.scrollY !== rolagem) window.scrollTo(window.scrollX, rolagem);
    details.dataset.animando = "1";
    details.style.overflow = "clip";
    details.style.height = de + "px";
    var ms = tempo("--mov-expansao", 250);
    conteudoDe(details, summary).forEach(function (filho) {
      filho.animate([{ opacity: 1 }, { opacity: 0 }], { duration: ms * .6, easing: CURVA, fill: "forwards" });
    });
    var anim = details.animate([{ height: de + "px" }, { height: ate + "px" }], { duration: ms, easing: CURVA });
    anim.onfinish = anim.oncancel = function () {
      details.open = false;
      /* Os fades ficaram em `forwards`; cancelados, o conteúdo volta ao
         normal para a próxima abertura. */
      conteudoDe(details, summary).forEach(function (filho) {
        filho.getAnimations().forEach(function (a) { a.cancel(); });
      });
      limpar(details);
    };
  }

  function limpar(details) {
    details.style.height = "";
    details.style.overflow = "";
    delete details.dataset.animando;
  }

  /* MEMÓRIA DE UM TOQUE, entre uma página e a seguinte.
   *
   * O app é multi-página: registrar água, marcar refeição e concluir série
   * são POST → redirect → GET. O que a tela seguinte precisa saber para
   * animar — de onde o número saiu, qual cartão acabou de mudar, se a pessoa
   * avançou ou voltou — é gravado aqui, no `sessionStorage`, no instante do
   * envio, e lido UMA vez ao carregar. Nada disto afirma sucesso: o
   * servidor respondeu, a página nova É a confirmação, e a animação só
   * mostra a diferença entre o que estava e o que está. */
  function guardar(chave, valor) { try { sessionStorage.setItem(chave, valor); } catch (e) {} }
  function retirar(chave) {
    try { var v = sessionStorage.getItem(chave); if (v !== null) sessionStorage.removeItem(chave); return v; }
    catch (e) { return null; }
  }

  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!form || !form.getAttribute) return;
    if (form.dataset.celebra) guardar("nutriplan:celebra", form.dataset.celebra);
    if (form.dataset.direcao) guardar("nutriplan:direcao", form.dataset.direcao);
    var acao = new URL(form.getAttribute("action") || location.href, location.origin).pathname;
    if (/^\/agua\/$/.test(acao)) {
      var total = document.querySelector("[data-agua-total]");
      var barra = document.querySelector("[data-agua-barra]");
      if (total) guardar("nutriplan:agua-antes", total.textContent.trim());
      if (barra) guardar("nutriplan:agua-barra-antes", barra.style.width || "");
    }
  });
  document.addEventListener("click", function (evento) {
    var alvo = evento.target.closest && evento.target.closest("a[data-direcao]");
    if (alvo) guardar("nutriplan:direcao", alvo.dataset.direcao);
  });
  /* Sem rede o envio ficou na fila e a página não muda: a memória do toque
     não pode esperar pelo próximo carregamento, horas depois. */
  document.addEventListener("nutriplan:enfileirado", function () {
    retirar("nutriplan:celebra");
    retirar("nutriplan:agua-antes");
    retirar("nutriplan:agua-barra-antes");
  });

  /* ÁGUA — o eco do toque: "+250 ml" sobe do botão e some.
   *
   * Nasce no toque e não espera o servidor: é o eco do DEDO, não a
   * confirmação do registro (essa é o número da página seguinte, que conta
   * do valor antigo ao novo). Um por toque; o elemento se apaga ao
   * terminar. Sem rede o formulário não navega e o eco fica sendo o único
   * retorno imediato — o aviso "guardado, aguardando rede" vem logo atrás. */
  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest && evento.target.closest("[data-agua-eco]");
    if (!botao || reduzido()) return;
    var eco = document.createElement("span");
    eco.className = "agua__eco";
    eco.setAttribute("aria-hidden", "true");
    eco.textContent = botao.dataset.aguaEco;
    (botao.parentNode || botao).appendChild(eco);
    var fim = function () { if (eco.parentNode) eco.parentNode.removeChild(eco); };
    eco.addEventListener("animationend", fim);
    setTimeout(fim, tempo("--mov-sucesso", 500) * 2);
  });

  /* Conta de `de` até `ate` em `ms`, com a curva de saída, e escreve com
     `formatar`. `requestAnimationFrame`, e o valor final é escrito SEMPRE —
     o número certo não depende de o relógio ter chegado. */
  function contar(elemento, de, ate, ms, formatar) {
    if (reduzido() || !window.requestAnimationFrame || de === ate) {
      elemento.textContent = formatar(ate);
      return;
    }
    var inicio = null;
    function quadro(agora) {
      if (inicio === null) inicio = agora;
      var t = Math.min(1, (agora - inicio) / ms);
      var suave = 1 - Math.pow(1 - t, 3);
      elemento.textContent = formatar(de + (ate - de) * suave);
      if (t < 1) requestAnimationFrame(quadro);
      else elemento.textContent = formatar(ate);
    }
    requestAnimationFrame(quadro);
  }

  /* Lê "2.055", "82,4", "68%" e devolve {valor, formatar} que reescreve no
     mesmo formato pt-BR — milhar com ponto, decimal com vírgula, sufixo
     preservado. Qualquer texto que não seja só um número devolve null. */
  function numeroDe(texto) {
    var m = /^\s*(-?[\d.]+)(,(\d+))?\s*(%?)\s*$/.exec(texto);
    if (!m) return null;
    var inteiro = m[1].replace(/\./g, "");
    if (!/^-?\d+$/.test(inteiro)) return null;
    var decimais = m[3] ? m[3].length : 0;
    var milhar = /\d\.\d{3}/.test(m[1]);
    var valor = parseFloat(inteiro + (m[3] ? "." + m[3] : ""));
    var sufixo = m[4] || "";
    return {
      valor: valor,
      formatar: function (n) {
        var fixo = Math.abs(n).toFixed(decimais);
        var partes = fixo.split(".");
        var i = partes[0];
        if (milhar) i = i.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
        return (n < 0 ? "-" : "") + i + (partes[1] ? "," + partes[1] : "") + sufixo;
      }
    };
  }

  /* AO CARREGAR: o que a página anterior deixou, e o que esta anuncia. */
  function aoCarregar() {
    /* A direção gravada por "Voltar"/"Continuar" só vale para a etapa
       seguinte do cadastro, que a lê antes da primeira pintura (script em
       linha de `step.html`). Qualquer outra página que a encontre — a edição
       pelo Perfil termina no Perfil — a descarta, senão a próxima visita ao
       cadastro entraria pelo lado errado. */
    if (!raiz.hasAttribute("data-transicao")) retirar("nutriplan:direcao");

    /* O cartão que acabou de mudar (refeição marcada) ganha `is-recem`;
       o CSS anima só ele. */
    var celebra = retirar("nutriplan:celebra");
    if (celebra) {
      var cartao = document.getElementById(celebra);
      if (cartao) cartao.classList.add("is-recem");
    }

    /* A água conta do valor de antes ao de agora, e a barra preenche a
       partir de onde estava — desfazer e zerar contam para baixo. */
    var total = document.querySelector("[data-agua-total]");
    var antes = retirar("nutriplan:agua-antes");
    var barraAntes = retirar("nutriplan:agua-barra-antes");
    if (total && antes !== null) {
      var de = numeroDe(antes), ate = numeroDe(total.textContent.trim());
      if (de && ate && de.valor !== ate.valor) {
        contar(total, de.valor, ate.valor, tempo("--mov-sucesso", 500), ate.formatar);
        /* BATER META (CORTE): a esquina superior se desdobra e o número
           cresce uma vez — só no toque que CRUZA a meta, nunca nos seguintes. */
        var meta = parseFloat((total.closest("[data-agua-meta]") || {}).getAttribute
          ? total.closest("[data-agua-meta]").getAttribute("data-agua-meta") : "");
        if (meta && de.valor < meta && ate.valor >= meta) {
          var dono = total.closest(".agua-card") || total.closest(".ring--agua");
          if (dono) dono.classList.add("is-meta");
        }
        var barra = document.querySelector("[data-agua-barra]");
        if (barra && barraAntes && !reduzido() && barra.animate) {
          /* A barra já tem `encher` (0 → largura) no CSS; as duas juntas
             fariam a barra recuar no fim. Só a que parte do valor anterior. */
          barra.style.animation = "none";
          barra.animate([{ width: barraAntes }, { width: barra.style.width || "0%" }],
                        { duration: tempo("--mov-sucesso", 500), easing: CURVA });
        }
      }
    }

    animarNumeros(document);
  }

  /* Números que contam até o valor (Progresso) e listas escalonadas. Fora
     de `aoCarregar` porque a execução do treino TROCA o <main> por fetch
     ("Concluir série" sem recarga, 20/09/2026): o placar da última série
     chega num <main> que o DOMContentLoaded nunca viu, e sem esta chamada
     o número não contava do zero nem a cascata recebia `--i` — a
     coreografia da NERVURA sumia exatamente no momento que existe para
     recompensar. `raiz` é o documento no carregamento e o <main> novo na
     troca; os nós velhos já saíram, então nada conta duas vezes. */
  function animarNumeros(raiz) {
    /* Começam em 60 % do valor, não em zero: o número já é legível no
       primeiro quadro, e o movimento diz "chegou" em vez de fazer a pessoa
       esperar para ler. */
    Array.prototype.forEach.call(raiz.querySelectorAll("[data-conta]"), function (el) {
      var n = numeroDe(el.textContent);
      if (!n || !n.valor) return;
      /* `data-conta="zero"` é o placar: a carga total conta do ZERO em
         `--mov-nervura`, com a mesma curva da régua, e só depois de a
         nervura ter riscado (NERVURA, 17/09/2026). */
      var doZero = el.getAttribute("data-conta") === "zero";
      var comecar = function () { contar(el, doZero ? 0 : n.valor * .6, n.valor, tempo(doZero ? "--mov-nervura" : "--mov-sucesso", doZero ? 600 : 500), n.formatar); };
      if (doZero && !reduzido()) { el.textContent = n.formatar(0); setTimeout(comecar, tempo("--mov-nervura", 600)); }
      else comecar();
    });

    /* Listas escalonadas: cada filho recebe o índice, e o CSS o transforma
       em atraso. O teto de 8 é para a nona linha não chegar meio segundo
       depois — dali em diante tudo entra junto com a oitava. */
    Array.prototype.forEach.call(raiz.querySelectorAll("[data-escalonado]"), function (lista) {
      Array.prototype.forEach.call(lista.children, function (filho, i) {
        filho.style.setProperty("--i", Math.min(i, 8));
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", aoCarregar);
  else aoCarregar();
  document.addEventListener("nutriplan:pagina-trocada", function (evento) {
    animarNumeros((evento.detail && evento.detail.raiz) || document.querySelector("main") || document);
  });
})();

/* PÁGINA DO CACHE — a faixa que diz "isto pode estar desatualizado".
 *
 * O service worker entrega a cópia guardada de uma tela quando o servidor
 * passa de três segundos (paciência esgotada) ou quando a rede cai. Medido em
 * produção em 16/09/2026 (avaliação, B6): no cold start do plano gratuito a
 * Home saía do cache com o saldo de ANTES e nenhuma tela dizia isso — a
 * pessoa via o dia de ontem como se fosse o de agora.
 *
 * O worker não mexe no HTML que entrega; ele LEMBRA o que entregou. Esta
 * página pergunta "de onde vim?" ao carregar, e o worker responde só quando
 * a resposta veio do cache — com o motivo, porque a frase é diferente:
 * "o servidor está demorando" não é "você está sem conexão". Quando a rede
 * finalmente responde, o worker avisa ("pagina-nova-disponivel") e a faixa
 * passa a oferecer "Atualizar", que recarrega — agora com o servidor
 * acordado, a mesma paciência de três segundos basta.
 *
 * A faixa é a `.flash` de sempre, escondida no HTML e preenchida aqui: um
 * segundo componente para o mesmo aviso é o que a seção de design proíbe. */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;

  var faixa = document.querySelector("[data-aviso-cache]");
  if (!faixa) return;
  var texto = faixa.querySelector("[data-aviso-cache-texto]");
  var atualizar = faixa.querySelector("[data-aviso-cache-atualizar]");

  var FRASES = {
    demora: "O servidor está demorando — esta tela é a última versão salva e pode estar desatualizada.",
    "sem-rede": "Você está sem conexão — esta tela é a última versão salva e pode estar desatualizada.",
    nova: "O servidor respondeu: há uma versão mais nova desta tela.",
  };

  function mostrar(frase, comBotao) {
    if (texto) texto.textContent = frase;
    if (atualizar) atualizar.hidden = !comBotao;
    faixa.hidden = false;
  }

  if (atualizar) {
    atualizar.addEventListener("click", function () { location.reload(); });
  }

  navigator.serviceWorker.addEventListener("message", function (event) {
    var dado = event.data || {};
    if (dado.tipo === "pagina-do-cache") {
      if (dado.redeChegou) mostrar(FRASES.nova, true);
      else mostrar(FRASES[dado.motivo] || FRASES.demora, true);
    } else if (dado.tipo === "pagina-nova-disponivel") {
      mostrar(FRASES.nova, true);
    }
  });

  function perguntar() {
    var controlador = navigator.serviceWorker.controller;
    if (!controlador) return;
    controlador.postMessage({ tipo: "de-onde-vim", url: location.href });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", perguntar);
  else perguntar();
})();
