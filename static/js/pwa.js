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
      /* UM FLUTUANTE POR VEZ (decisão do dono, 20/09/2026): a auditoria
       * mediu três camadas fixas empilhadas no rodapé — convite, toast de
       * conquista e barra de abas. O toast é a notícia; o convite espera a
       * próxima tela. */
      if (document.querySelector(".conquista")) return true;
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

  /* ONBOARDING — "você faz musculação?" esconde o bloco da academia
   * (22/09/2026). Com "não", experiência, equipamento, dias e divisão somem
   * (`[data-so-musculacao]`) e a nota `[data-sem-musculacao]` aparece; o
   * servidor ignora o bloco do mesmo jeito, então sem JavaScript nada
   * quebra — só fica mais comprido. */
  var soMusculacao = document.querySelector("[data-so-musculacao]");
  if (soMusculacao) {
    var respostas = document.querySelectorAll('input[name="musculacao"]');
    var semMusculacao = document.querySelector("[data-sem-musculacao]");
    function acertarMusculacao() {
      var nao = false;
      respostas.forEach(function (r) { if (r.checked && r.value === "nao") nao = true; });
      soMusculacao.hidden = nao;
      if (semMusculacao) semMusculacao.hidden = !nao;
    }
    respostas.forEach(function (r) { r.addEventListener("change", acertarMusculacao); });
    acertarMusculacao();
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

/* TOQUE DURANTE A TRANSIÇÃO (22/09/2026): o primeiro toque não se perde.
 *
 * MEDIDO no Chrome 153: enquanto a view transition entre páginas anima
 * (`--mov-tela`), `elementFromPoint` devolve `<html>` — o clique é
 * despachado no documento e nenhum botão o recebe. São 280–320 ms depois
 * de o documento novo começar, mais num celular lento; é a janela em que
 * quem já sabe onde vai tocar toca. `pointer-events: none` na árvore de
 * pseudo-elementos não muda nada (medido). Então o toque que caiu no
 * `<html>` é GUARDADO e REPETIDO no elemento que está naquele ponto quando
 * `viewTransition.finished` resolve — a nova tela já está no lugar desde o
 * primeiro quadro (ela entra com fade e 12 px de deslize), então o ponto é
 * o que a pessoa viu. Um toque só, o último; sem transição não há
 * `viewTransition` e nada disto roda. */
(function () {
  "use strict";
  window.addEventListener("pagereveal", function (evento) {
    var transicao = evento.viewTransition;
    if (!transicao || !transicao.finished) return;
    var toque = null;
    function guardar(ev) {
      if (ev.target !== document.documentElement && ev.target !== document.body) return;
      toque = { x: ev.clientX, y: ev.clientY };
    }
    document.addEventListener("click", guardar, true);
    function repetir() {
      document.removeEventListener("click", guardar, true);
      if (!toque) return;
      var alvo = document.elementFromPoint(toque.x, toque.y);
      if (!alvo || alvo === document.documentElement || alvo === document.body) return;
      var acionavel = alvo.closest("a, button, summary, label, input, select, textarea, [role=button]") || alvo;
      acionavel.click();
    }
    transicao.finished.then(repetir, repetir);
  });
})();

/* RASCUNHO DO FORMULÁRIO (22/09/2026): nada digitado se perde em silêncio.
 *
 * Item 2 da missão de UX: "enviar a etapa 2 ou a corrida derruba a sessão
 * e descarta o que digitei". O POST recusado por CSRF (token velho: outra
 * aba entrou de novo, ou o worker serviu a página do cache num cold start)
 * e a sessão que expirou com o formulário aberto (302 para o login) tinham
 * o mesmo fim — o formulário voltava vazio. Aqui todo `<form data-rascunho>`
 * grava os campos no `localStorage` enquanto a pessoa digita (chave por
 * caminho e por pessoa, validade de um dia) e os devolve quando o MESMO
 * formulário reabre com o campo VAZIO: o que o servidor reabriu preenchido
 * (erro de validação, edição) manda. O envio marca o rascunho como
 * `enviado`; a página seguinte, se for OUTRA, apaga — deu certo. Fora:
 * senha, token, arquivo e campo escondido, por construção. */
(function () {
  "use strict";
  var VALIDADE_MS = 24 * 60 * 60 * 1000;
  var FORA = { "password": 1, "file": 1, "hidden": 1, "submit": 1, "button": 1 };
  function chave(form) {
    var quem = document.body.getAttribute("data-usuario") || "";
    return "nutriplan:rascunho:" + quem + ":" + (form.getAttribute("data-rascunho") || location.pathname);
  }
  function ler(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } }
  function gravar(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function apagar(k) { try { localStorage.removeItem(k); } catch (e) {} }
  function campos(form) {
    return [].filter.call(form.elements, function (el) {
      if (!el.name || el.name === "csrfmiddlewaretoken") return false;
      var tipo = (el.type || "").toLowerCase();
      return !FORA[tipo];
    });
  }
  function colher(form) {
    var dados = {};
    campos(form).forEach(function (el) {
      var tipo = (el.type || "").toLowerCase();
      if (tipo === "checkbox" || tipo === "radio") {
        if (!dados[el.name]) dados[el.name] = [];
        if (el.checked) dados[el.name].push(el.value);
      } else if (el.tagName === "SELECT" && el.multiple) {
        dados[el.name] = [].map.call(el.selectedOptions, function (o) { return o.value; });
      } else {
        dados[el.name] = el.value;
      }
    });
    return dados;
  }
  function vazio(form, nome) {
    var lista = campos(form).filter(function (el) { return el.name === nome; });
    return lista.every(function (el) {
      var tipo = (el.type || "").toLowerCase();
      if (tipo === "checkbox" || tipo === "radio") return !el.checked;
      return !el.value;
    });
  }
  /* O servidor reabriu o formulário COM ERRO: os campos trazem o que a
   * pessoa acabou de enviar, e isso é mais novo que o rascunho. Sem erro é
   * um GET limpo — valor inicial, padrão ("07:00") ou o que já estava salvo
   * —, e o rascunho, digitado depois de a pessoa ver esses valores, vence. */
  function reabertoComErro(form) {
    return !!form.querySelector('[aria-invalid="true"], .field__errors');
  }
  function devolver(form, dados) {
    var devolvidos = 0;
    var comErro = reabertoComErro(form);
    Object.keys(dados).forEach(function (nome) {
      if (comErro && !vazio(form, nome)) return;
      var valor = dados[nome];
      campos(form).filter(function (el) { return el.name === nome; }).forEach(function (el) {
        var tipo = (el.type || "").toLowerCase();
        if (tipo === "checkbox" || tipo === "radio") {
          var marcar = Array.isArray(valor) && valor.indexOf(el.value) > -1;
          if (marcar !== el.checked) { el.checked = marcar; devolvidos++; }
        } else if (el.tagName === "SELECT" && el.multiple) {
          [].forEach.call(el.options, function (o) { o.selected = valor.indexOf(o.value) > -1; });
          devolvidos++;
        } else if (valor && el.value !== valor) {
          el.value = valor; devolvidos++;
        }
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
    return devolvidos;
  }
  function avisar(form) {
    var nota = document.createElement("p");
    nota.className = "hint rascunho__nota";
    nota.setAttribute("role", "status");
    nota.textContent = "Devolvemos o que você tinha digitado aqui.";
    form.insertBefore(nota, form.firstChild);
  }
  /* A página seguinte a um envio, se for OUTRA, apaga o rascunho enviado. */
  function limparEnviados() {
    try {
      for (var i = localStorage.length - 1; i >= 0; i--) {
        var k = localStorage.key(i);
        if (!k || k.indexOf("nutriplan:rascunho:") !== 0) continue;
        var r = ler(k);
        if (!r) { apagar(k); continue; }
        var velho = !r.em || Date.now() - r.em > VALIDADE_MS;
        var enviadoEOutraPagina = r.enviado && r.caminho !== location.pathname;
        if (velho || enviadoEOutraPagina) apagar(k);
      }
    } catch (e) {}
  }
  function ligar(form) {
    var k = chave(form);
    var guardado = ler(k);
    if (guardado && guardado.dados && Date.now() - (guardado.em || 0) <= VALIDADE_MS) {
      if (devolver(form, guardado.dados) > 0) avisar(form);
    }
    var temporizador = null;
    function salvar() {
      gravar(k, { em: Date.now(), caminho: location.pathname, dados: colher(form), enviado: false });
    }
    form.addEventListener("input", function () { clearTimeout(temporizador); temporizador = setTimeout(salvar, 250); });
    form.addEventListener("change", function () { clearTimeout(temporizador); temporizador = setTimeout(salvar, 250); });
    form.addEventListener("submit", function () {
      clearTimeout(temporizador);
      gravar(k, { em: Date.now(), caminho: location.pathname, dados: colher(form), enviado: true });
    });
  }
  function iniciar() {
    limparEnviados();
    document.querySelectorAll("form[data-rascunho]").forEach(ligar);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();

/* FOCO NO ERRO (22/09/2026): a tela vai até o primeiro campo inválido.
 *
 * O servidor reabre o formulário no TOPO, e o campo recusado pode estar
 * duas dobras abaixo — "Este campo é obrigatório." sem campo nenhum à
 * vista (item 3 da missão de UX; medido no peso da Home e no fim da etapa
 * 1). Toda página: o primeiro `[aria-invalid="true"]` é rolado para o meio
 * da tela e recebe o foco. Quem já tem `autofocus` na página manda — o
 * navegador o focou antes deste script, e dois focos brigando é pior que
 * nenhum. Foco em campo de texto abre o teclado no celular, e é isso
 * mesmo: a pessoa vai corrigir o que digitou. Um `<details>` fechado em
 * volta do campo é aberto antes, senão o foco cai no vazio. Sem `smooth`:
 * a rolagem é instantânea nos dois regimes de movimento. */
(function () {
  "use strict";
  function focar() {
    if (document.querySelector("[autofocus]")) return;
    var campo = document.querySelector('[aria-invalid="true"]');
    if (!campo) return;
    var details = campo.closest && campo.closest("details");
    while (details) { details.open = true; details = details.parentElement && details.parentElement.closest("details"); }
    campo.scrollIntoView({ block: "center" });
    try { campo.focus({ preventScroll: true }); } catch (e) { campo.focus(); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", focar);
  else focar();
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
    /* O toque já foi filtrado por `reduzido()`; o gate aqui é a segunda
       trava, para quem chamar a função por outro caminho. */
    if (reduzido()) { details.open = true; return; }
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
    if (reduzido()) { details.open = false; return; }
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

/* TECLADO ABERTO RECOLHE A BARRA (decisão do dono, 20/09/2026): com o
 * teclado aberto sobram ~450 px a 390, e a barra de abas fixa ocupava 68
 * deles (medido na auditoria em Progresso, Lista e Corrida manual). Enquanto
 * um campo de texto tem o foco, o corpo ganha `teclado-aberto` e o CSS
 * recolhe a barra — e o convite de instalação, que não tem o que fazer sobre
 * um teclado. Só campos que abrem teclado: botão, rádio, caixa e `range` não
 * contam, senão a barra sumiria ao tocar num rádio do onboarding.
 * `config/test_teclado_e_flutuantes.py` prende a estrutura; o comportamento
 * foi provado no navegador (agent-browser, 390 × 450). */
(function () {
  var ABRE_TECLADO = /^(text|search|email|url|tel|number|password|date|time)$/;
  function abreTeclado(el) {
    if (!el) return false;
    if (el.tagName === "TEXTAREA") return true;
    if (el.tagName === "INPUT") return ABRE_TECLADO.test((el.getAttribute("type") || "text").toLowerCase());
    return el.isContentEditable === true;
  }
  document.addEventListener("focusin", function (e) {
    if (abreTeclado(e.target)) document.body.classList.add("teclado-aberto");
  });
  document.addEventListener("focusout", function (e) {
    if (abreTeclado(e.target)) document.body.classList.remove("teclado-aberto");
  });
})();

/* ==========================================================================
   COMPARTILHAR O PLACAR (retenção, 21/09/2026)

   O treino fechado vira uma imagem de 1080×1350 — retrato 4:5, o formato
   que feed e story aceitam sem cortar — desenhada AQUI, no aparelho, em
   canvas: sem servidor, sem dependência nova. O desenho é o da direção
   NERVURA: chão `--bg`, a régua diagonal (`--nervura`, −14°) com a ponta
   de folha na extremidade, o título em caixa alta na display e os números
   em Archivo; o laranja (`--terra`) é só da carga, como na execução.

   Os CINCO dados vêm dos `data-compartilhar-*` do botão, já formatados
   pelo servidor em pt-BR. Nada é lido do resto da página nem recalculado —
   é o que garante que peso corporal, e-mail e nome não entram na imagem
   (a mesma régua de `card.js`). O compartilhar em si é
   `NutriPlanCard.compartilhar` (`card.js`, servido em toda página logada e
   pré-cacheado pelo service worker): Web Share com arquivo quando
   `navigator.canShare({files})` diz sim, senão `<a download>` criado na
   hora. Uma segunda cópia aqui seria a que envelhece. O `<a download>`
   nasce solto do documento, então o guarda do link-botão acima não o vê —
   e o botão não é marcado como "carregando": a bandeja ou o download é a
   resposta.

   As cores saem de `getComputedStyle` dos tokens — a fonte da verdade — com
   os hex de Ferro de reserva; a execução escreve `modo-foco`, então na
   tela do placar os tokens já resolvem para o Ferro. As fontes são pedidas
   por `document.fonts.load` antes de desenhar, com teto de 1,5 s: sem rede
   `fonts.load` pode não voltar, e a imagem sai na fallback em vez de o
   botão ficar mudo. `prefers-reduced-motion` não entra: é imagem parada.

   Ao terminar, o botão dispara `nutriplan:placar-compartilhado` com o
   canvas e o nome do arquivo — é o gancho do QA de navegador (o PNG é lido
   dali por `toDataURL`) e de quem quiser reagir sem reler a imagem.
   ========================================================================== */
(function () {
  "use strict";

  var LARGURA = 1080;
  var ALTURA = 1350;
  var MARGEM = 96;
  /* `--traco` é 2 px na tela; a imagem tem a densidade de uma captura a 3×
     (1080 para ~360 de largura útil), então a régua leva 6 — em 2 a régua
     sumiria no feed. A ponta de folha segue a mesma escala (16×14 → 48×42). */
  var TRACO = 6;
  var PONTA_LARGURA = 48;
  var PONTA_ALTURA = 42;
  var NERVURA_GRAUS = -14;
  var ESPERA_FONTES_MS = 1500;
  var DISPLAY = '"Big Shoulders Display", "Arial Narrow", Impact, sans-serif';
  var TEXTO = 'Archivo, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  var ARQUIVO = "nutriplan-treino-";
  var ocupado = false;

  function token(nome, reserva) {
    var valor = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
    return valor || reserva;
  }

  function paleta() {
    return {
      fundo: token("--bg", "#0b140f"),
      marca: token("--brand", "#43df7a"),
      carga: token("--terra", "#e8a33d"),
      texto: token("--text", "#f2f6f2"),
      fraco: token("--text-mute", "#a9bbae"),
    };
  }

  /* Pede as duas faces que a imagem usa. Resolve sempre — com as fontes ou
     com o teto — e nunca rejeita. */
  function fontes() {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    var pedidas = Promise.all([
      document.fonts.load('900 120px "Big Shoulders Display"'),
      document.fonts.load("600 40px Archivo"),
    ]).catch(function () {});
    var teto = new Promise(function (resolve) { setTimeout(resolve, ESPERA_FONTES_MS); });
    return Promise.race([pedidas, teto]);
  }

  /* O ícone do app (o mesmo `<link rel="icon">` de 192 px que toda página
     leva), para a marca no rodapé. Sem ele — fora do ar, ou a página sem o
     link — a marca é só o wordmark; o desenho nunca espera mais que o teto. */
  function icone() {
    return new Promise(function (resolve) {
      var link = document.querySelector('link[rel="icon"][sizes="192x192"]');
      if (!link || !link.href) return resolve(null);
      var img = new Image();
      var decidido = false;
      function fim(ok) {
        if (decidido) return;
        decidido = true;
        resolve(ok ? img : null);
      }
      img.onload = function () { fim(true); };
      img.onerror = function () { fim(false); };
      setTimeout(function () { fim(false); }, ESPERA_FONTES_MS);
      img.src = link.href;
    });
  }

  /* Quebra por palavra dentro de `largura`: nome de sessão é comprido por
     natureza ("Costas, bíceps, antebraço e trapézio"). */
  function linhas(g, texto, largura) {
    var saida = [];
    var atual = "";
    texto.split(" ").forEach(function (palavra) {
      var tentativa = atual ? atual + " " + palavra : palavra;
      if (atual && g.measureText(tentativa).width > largura) {
        saida.push(atual);
        atual = palavra;
      } else {
        atual = tentativa;
      }
    });
    if (atual) saida.push(atual);
    return saida;
  }

  function fonte(g, peso, tamanho, familia, espaco) {
    g.font = peso + " " + tamanho + "px " + familia;
    if ("letterSpacing" in g) g.letterSpacing = (espaco || 0) + "px";
  }

  /* A régua que risca: nasce em (x, y), sobe a −14° pela direita e termina
     na ponta de folha — o mesmo `clip-path` do `.recompensa::before`. */
  function nervura(g, cor, x, y, comprimento) {
    g.save();
    g.translate(x, y);
    g.rotate(NERVURA_GRAUS * Math.PI / 180);
    g.fillStyle = cor;
    g.fillRect(0, -TRACO, comprimento - PONTA_LARGURA, TRACO);
    g.beginPath();
    g.moveTo(comprimento - PONTA_LARGURA, -PONTA_ALTURA);
    g.lineTo(comprimento, 0);
    g.lineTo(comprimento - PONTA_LARGURA, 0);
    g.closePath();
    g.fill();
    g.restore();
  }

  function desenhar(dados, imagemDoIcone) {
    var canvas = document.createElement("canvas");
    canvas.width = LARGURA;
    canvas.height = ALTURA;
    var g = canvas.getContext("2d");
    var cor = paleta();
    var util = LARGURA - MARGEM * 2;

    g.fillStyle = cor.fundo;
    g.fillRect(0, 0, LARGURA, ALTURA);
    g.textBaseline = "alphabetic";
    g.textAlign = "left";

    /* TÍTULO — "Treino B · Costas e bíceps": a letra vira sobretítulo na cor
       da marca, o nome vira o herói em caixa alta. Sem o separador, tudo é
       o nome. Até duas linhas a 120; a partir da terceira desce para 96. */
    var partes = dados.sessao.split(" · ");
    var sobretitulo = partes.length > 1 ? partes.shift() : "";
    var titulo = partes.join(" · ").toUpperCase();
    var y = 200;
    if (sobretitulo) {
      fonte(g, 800, 52, DISPLAY, 4);
      g.fillStyle = cor.marca;
      g.fillText(sobretitulo.toUpperCase(), MARGEM, y);
    }
    var corpo = 120;
    var passo = 116;
    fonte(g, 900, corpo, DISPLAY, 1);
    var tituloEmLinhas = linhas(g, titulo, util);
    if (tituloEmLinhas.length > 2) {
      corpo = 96;
      passo = 94;
      fonte(g, 900, corpo, DISPLAY, 1);
      tituloEmLinhas = linhas(g, titulo, util).slice(0, 3);
    }
    y += corpo + 24;
    g.fillStyle = cor.texto;
    tituloEmLinhas.forEach(function (linha, i) {
      g.fillText(linha, MARGEM, y + i * passo);
    });
    var fimDoTitulo = y + (tituloEmLinhas.length - 1) * passo + 20;

    /* RODAPÉ — a marca, discreta: o protagonista é o treino de quem posta. */
    var icone = 88;
    var topoDoRodape = ALTURA - MARGEM - icone;

    /* O MIOLO — carga, séries e minutos — centrado entre título e rodapé.
       Alturas relativas à linha de base da carga: o glifo sobe 150, o
       rótulo fica a +64, os números pequenos a +254 e os rótulos a +312 e
       +352. */
    var alturaDoMiolo = 150 + 352;
    var livre = (topoDoRodape - 40) - (fimDoTitulo + 40);
    var baseDaCarga = fimDoTitulo + 40 + Math.max(0, (livre - alturaDoMiolo) / 2) + 150;

    /* A nervura nasce à esquerda, sob a carga, e sobe por trás dela até a
       ponta — desenhada ANTES dos números, como o `::before` do placar. */
    nervura(g, cor.marca, 0, baseDaCarga + 34, Math.round(LARGURA * 0.82));

    /* A carga cabe na largura útil: 210 leva até "123.456"; um número maior
       (ninguém levanta um milhão de kg numa sessão, mas o desenho não é quem
       decide isso) desce de tamanho até caber, em vez de sair pela borda. */
    var tamanhoDaCarga = 210;
    fonte(g, 800, tamanhoDaCarga, TEXTO, -6);
    var heroi = dados.heroi || dados.kg;
    while (g.measureText(heroi).width > util && tamanhoDaCarga > 96) {
      tamanhoDaCarga -= 10;
      fonte(g, 800, tamanhoDaCarga, TEXTO, -6);
    }
    g.fillStyle = cor.carga;
    g.fillText(heroi, MARGEM, baseDaCarga);
    fonte(g, 600, 38, TEXTO, 6);
    g.fillStyle = cor.fraco;
    g.fillText(dados.heroiRotulo || "KG LEVANTADOS", MARGEM, baseDaCarga + 64);

    /* Os rótulos dizem o que a tela diz — "min entre o primeiro e o último
       registro" não é "duração do treino", que ninguém mede —, em duas linhas
       cada um: numa só o dos minutos estourava a borda direita (medido). */
    var colunas = [
      [dados.series, ["SÉRIES", "REGISTRADAS"]],
      [dados.minutos, ["MIN ENTRE O PRIMEIRO", "E O ÚLTIMO REGISTRO"]],
    ];
    colunas.forEach(function (coluna, i) {
      var x = MARGEM + i * (util / 2 + 24);
      fonte(g, 700, 110, TEXTO, -3);
      g.fillStyle = cor.texto;
      g.fillText(coluna[0], x, baseDaCarga + 254);
      fonte(g, 600, 30, TEXTO, 4);
      g.fillStyle = cor.fraco;
      coluna[1].forEach(function (linha, j) {
        g.fillText(linha, x, baseDaCarga + 312 + j * 40);
      });
    });

    var x = MARGEM;
    if (imagemDoIcone) {
      g.drawImage(imagemDoIcone, x, topoDoRodape, icone, icone);
      x += icone + 24;
    }
    fonte(g, 900, 64, DISPLAY, -1);
    var baseDaMarca = topoDoRodape + icone / 2 + 22;
    g.fillStyle = cor.texto;
    g.fillText("Nutri", x, baseDaMarca);
    g.fillStyle = cor.marca;
    g.fillText("Plan", x + g.measureText("Nutri").width, baseDaMarca);

    return canvas;
  }

  document.addEventListener("click", function (evento) {
    var alvo = evento.target;
    if (!alvo || typeof alvo.closest !== "function") return;
    var botao = alvo.closest("[data-compartilhar-placar]");
    if (!botao || ocupado || !window.NutriPlanCard) return;
    evento.preventDefault();
    ocupado = true;

    var dados = {
      sessao: botao.dataset.compartilharSessao || "",
      series: botao.dataset.compartilharSeries || "",
      kg: botao.dataset.compartilharKg || "",
      /* O herói do cartão é o da tela: kg com carga, repetições sem
       * (peso do corpo, 22/09/2026). `kg` fica para quem lê o dado antigo. */
      heroi: botao.dataset.compartilharHeroi || botao.dataset.compartilharKg || "",
      heroiRotulo: botao.dataset.compartilharHeroiRotulo || "KG LEVANTADOS",
      minutos: botao.dataset.compartilharMinutos || "—",
      data: botao.dataset.compartilharData || "",
    };
    var nome = ARQUIVO + (dados.data || new Date().toISOString().slice(0, 10)) + ".png";

    function terminar(canvas, resultado) {
      botao.dispatchEvent(new CustomEvent("nutriplan:placar-compartilhado", {
        bubbles: true,
        detail: { canvas: canvas, nome: nome, via: resultado && resultado.via },
      }));
    }

    /* `ocupado` cobre só o DESENHO (fontes + ícone + canvas, menos de um
       segundo): um toque duplo nesse intervalo não desenha duas vezes. Ele
       solta assim que a entrega é pedida, e não quando ela termina: a
       bandeja do Web Share pode ficar aberta o tempo que a pessoa quiser —
       e em navegador sem interface ela nunca fecha —, e um botão travado
       até lá seria um botão morto. Segundo `share()` com o primeiro aberto
       é o navegador que recusa (InvalidStateError), e `card.js` traduz em
       "cancelado". */
    Promise.all([fontes(), icone()]).then(function (pronto) {
      var canvas = desenhar(dados, pronto[1]);
      var entrega = window.NutriPlanCard.compartilhar(canvas, nome, "Treino fechado · NutriPlan");
      ocupado = false;
      return entrega.then(
        function (resultado) { terminar(canvas, resultado); },
        function () { terminar(canvas, null); }
      );
    }).catch(function () { ocupado = false; });
  });
})();

/* ==========================================================================
   DESCANSO (a execução do treino, 22/09/2026)

   Era uma faixa fina dentro do <main>, com o JavaScript inline na página:
   contava "79s" e virava "1:13" no meio do próprio descanso, sumia da tela
   assim que alguém rolava para ver as séries, e não tinha como pedir mais
   tempo. Aqui ele é um cronômetro de verdade:

   - UM formato, `m:ss`, do primeiro ao último segundo (o servidor manda o
     primeiro quadro pronto em `estado.descanso_relogio`);
   - "+30 s" para quem precisa de mais — o alvo fica no `sessionStorage`,
     então recarregar no meio não devolve o tempo original;
   - som OPCIONAL ao zerar, lembrado no aparelho e DESLIGADO por padrão
     (quem treina com música não quer bipe); a vibração continua para todos,
     longa, porque no fim do descanso o telefone está no banco;
   - `wakeLock` enquanto o descanso corre, onde existir: a tela apagando no
     meio é o que faz a pessoa perder a conta;
   - o número vem do SERVIDOR (`agora - created_at da última série`), então
     trocar de aba ou recarregar continua caindo no tempo certo.

   Por que aqui e não na página: a troca do <main> sem recarga recria os
   scripts do <main> a cada série, e este cresceu. Registrado uma vez,
   reencontra o bloco por MutationObserver. O contrato com a troca continua
   sendo `window.__descansoTique` — ela o limpa ANTES de tirar os nós, senão
   o descanso da série anterior vibra "pode ir" por cima do placar.
   ========================================================================== */
(function () {
  "use strict";
  var CHAVE_SOM = "nutriplan:descanso-som";
  var CHAVE_ALVO = "nutriplan:descanso-alvo";
  var PASSO = 30;
  var bloqueio = null;

  function guardado(armazem, chave) {
    try { return window[armazem].getItem(chave); } catch (e) { return null; }
  }
  function guardar(armazem, chave, valor) {
    try {
      if (valor === null) window[armazem].removeItem(chave);
      else window[armazem].setItem(chave, valor);
    } catch (e) { /* janela privada, cota cheia: o descanso continua funcionando */ }
  }

  function mmss(segundos) {
    var m = Math.floor(segundos / 60), s = segundos % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function porExtenso(segundos) {
    var m = Math.floor(segundos / 60), s = segundos % 60;
    if (!m) return segundos + " segundos";
    if (!s) return m + (m === 1 ? " minuto" : " minutos");
    return m + (m === 1 ? " minuto e " : " minutos e ") + s + " segundos";
  }

  /* A TELA NÃO APAGA ENQUANTO O DESCANSO CORRE. Só onde existe (Chrome,
     Android, Safari 16.4+); o `catch` cobre a aba em segundo plano, que o
     navegador recusa. Soltar é obrigação: o bloqueio esquecido drena
     bateria depois do treino. */
  function segurarTela() {
    if (!navigator.wakeLock || bloqueio) return;
    navigator.wakeLock.request("screen").then(function (b) { bloqueio = b; }, function () {});
  }
  function soltarTela() {
    if (!bloqueio) return;
    try { bloqueio.release(); } catch (e) { /* já solto */ }
    bloqueio = null;
  }

  /* O bipe é sintetizado — nenhum arquivo para baixar, nenhuma requisição.
     Dois tons curtos, e o contexto nasce no toque que ligou o som, então o
     navegador não o bloqueia. */
  function bipar() {
    var Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    try {
      var ctx = new Audio();
      [0, 0.18].forEach(function (atraso) {
        var osc = ctx.createOscillator(), ganho = ctx.createGain();
        osc.frequency.value = 880;
        ganho.gain.setValueAtTime(0.0001, ctx.currentTime + atraso);
        ganho.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + atraso + 0.01);
        ganho.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + atraso + 0.14);
        osc.connect(ganho); ganho.connect(ctx.destination);
        osc.start(ctx.currentTime + atraso);
        osc.stop(ctx.currentTime + atraso + 0.16);
      });
      setTimeout(function () { try { ctx.close(); } catch (e) {} }, 800);
    } catch (e) { /* sem áudio: a vibração e o texto continuam */ }
  }

  function iniciar(area) {
    if (!area || area.dataset.descansoVivo === "1") return;
    area.dataset.descansoVivo = "1";
    var relogio = area.querySelector("[data-descanso-relogio]");
    var aviso = document.querySelector("[data-descanso-aviso]");
    var botaoSom = area.querySelector("[data-descanso-som]");
    var restante = parseInt(area.dataset.descanso, 10) || 0;

    /* O "+30 s" sobrevive à recarga: o alvo (hora absoluta) fica no
       `sessionStorage` e só vale enquanto for MAIOR que o que o servidor
       manda — passada a série, o servidor manda o descanso novo e o alvo
       velho é descartado sozinho. */
    var alvo = parseInt(guardado("sessionStorage", CHAVE_ALVO), 10) || 0;
    var faltam = Math.round((alvo - Date.now()) / 1000);
    if (alvo && faltam > restante && faltam < 3600) restante = faltam;
    else guardar("sessionStorage", CHAVE_ALVO, null);

    function falar(texto) { if (aviso) aviso.textContent = texto; }
    function pintar() { if (relogio) relogio.textContent = mmss(Math.max(0, restante)); }

    function parar() {
      if (window.__descansoTique) clearInterval(window.__descansoTique);
      window.__descansoTique = null;
      soltarTela();
    }

    if (botaoSom) {
      var ligado = guardado("localStorage", CHAVE_SOM) === "1";
      botaoSom.setAttribute("aria-pressed", ligado ? "true" : "false");
      botaoSom.addEventListener("click", function () {
        ligado = botaoSom.getAttribute("aria-pressed") !== "true";
        botaoSom.setAttribute("aria-pressed", ligado ? "true" : "false");
        guardar("localStorage", CHAVE_SOM, ligado ? "1" : null);
        if (ligado) bipar();  /* o toque que liga também prova que dá para ouvir */
      });
    }

    var mais = area.querySelector("[data-descanso-mais]");
    if (mais) {
      mais.addEventListener("click", function () {
        restante += PASSO;
        guardar("sessionStorage", CHAVE_ALVO, String(Date.now() + restante * 1000));
        area.classList.remove("descanso--fim");
        pintar();
        falar("Mais " + PASSO + " segundos de descanso.");
      });
    }

    var pular = area.querySelector("[data-descanso-pular]");
    if (pular) {
      pular.addEventListener("click", function () {
        parar();
        guardar("sessionStorage", CHAVE_ALVO, null);
        area.hidden = true;
        falar("Descanso pulado.");
      });
    }

    /* O anúncio sai um instante DEPOIS de a página assentar: conteúdo que já
       está no HTML no carregamento não é anunciado — região viva avisa sobre
       MUDANÇA. Duas falas por descanso, e só duas. */
    setTimeout(function () { if (restante > 0) falar("Descanso de " + porExtenso(restante) + "."); }, 300);

    pintar();
    if (restante <= 0) return;
    segurarTela();
    if (window.__descansoTique) clearInterval(window.__descansoTique);
    var tique = setInterval(function () {
      restante -= 1;
      if (restante <= 0) {
        parar();
        guardar("sessionStorage", CHAVE_ALVO, null);
        area.classList.add("descanso--fim");
        if (relogio) relogio.textContent = "pode ir";
        falar("Descanso terminado, pode ir.");
        /* CHAMAR DE LONGE, e por isso o padrão é longo: no fim do descanso o
           aparelho está no banco e a pessoa de costas para ele. É o oposto do
           toque curto de gravar a série. `navigator.vibrate` não existe no
           iPhone — o `if` não é otimização, é metade dos aparelhos. */
        if (navigator.vibrate) navigator.vibrate([200, 100, 400]);
        if (guardado("localStorage", CHAVE_SOM) === "1") bipar();
        return;
      }
      pintar();
    }, 1000);
    window.__descansoTique = tique;
  }

  function procurar() { iniciar(document.querySelector("[data-descanso]")); }

  /* A tela em segundo plano perde o bloqueio por decisão do navegador; ao
     voltar, se o descanso ainda corre, ele é pedido de novo. */
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && window.__descansoTique) segurarTela();
    else if (document.visibilityState !== "visible") soltarTela();
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", procurar);
  else procurar();
  /* A troca do <main> sem recarga põe um bloco NOVO no lugar (ou nenhum, no
     placar): o observador é o que faz o cronômetro nascer de novo sem um
     `<script>` na página. */
  var raiz = document.querySelector("main") || document.body;
  if (window.MutationObserver && raiz) {
    new MutationObserver(function () { procurar(); }).observe(raiz, { childList: true, subtree: true });
  }
})();

/* ==========================================================================
   FOTO DE EXERCÍCIO QUE NÃO CARREGA (22/09/2026)

   As fotos do catálogo vêm de uma CDN (free-exercise-db, domínio público):
   na academia, com rede ruim ou operadora que bloqueia o domínio, o `<img>`
   fica um RETÂNGULO VAZIO — foi o que o dono viu como "a miniatura fica em
   branco". O espaço reservado só vale quando ele vai ser preenchido; aqui
   não vai, então ele sai e a linha começa no nome.

   `error` não borbulha, por isso o ouvinte é de CAPTURA e no `document`:
   um só, para a ficha inteira (até doze fotos) e para a execução, inclusive
   depois da troca do <main> sem recarga.
   ========================================================================== */
(function () {
  "use strict";
  document.addEventListener("error", function (evento) {
    var alvo = evento.target;
    if (!alvo || alvo.tagName !== "IMG") return;
    if (!alvo.classList.contains("ficha-item__foto") &&
        !alvo.classList.contains("demo__foto") &&
        !alvo.classList.contains("forma__foto")) return;
    alvo.remove();
  }, true);
})();

/* ==========================================================================
   TROCAR NA FICHA (22/09/2026)

   "trocar" é um LINK para a leitura do exercício, ancorado em "Outras
   formas" — e é assim que ele funciona sem JavaScript, no histórico e ao
   compartilhar. Daqui ele vira uma FOLHA sobre a ficha: escolher como fazer
   um movimento não devia custar sair da lista e voltar a ela.

   O que este bloco faz, e só: busca a MESMA página do link, recorta a seção
   `#outras-formas` e a mostra num `<dialog>` (foco preso e Esc de graça).
   Qualquer falha — rede, HTML inesperado, navegador sem `showModal` — cai
   na navegação de sempre; nada aqui é a única porta para nada.

   O "Trocar" de dentro da folha é um POST normal, interceptado para a ficha
   recarregar no lugar de ir para a leitura: o card precisa mostrar o
   exercício novo, e é a ficha que a pessoa está olhando.
   ========================================================================== */
(function () {
  "use strict";
  if (!window.fetch || !window.DOMParser) return;
  var folha = document.querySelector("[data-folha-troca]");
  if (!folha || !folha.showModal) return;
  var corpo = folha.querySelector("[data-folha-corpo]");
  var titulo = folha.querySelector(".folha-troca__titulo");

  function fechar() {
    if (folha.open) folha.close();
  }

  folha.addEventListener("click", function (evento) {
    /* O clique no backdrop fecha: `<dialog>` não faz isso sozinho, e um
       painel que só fecha pelo botão é o que faz alguém achar que travou. */
    if (evento.target === folha) fechar();
    if (evento.target.closest("[data-folha-fechar]")) fechar();
  });

  document.addEventListener("click", function (evento) {
    var link = evento.target.closest && evento.target.closest("[data-trocar]");
    if (!link) return;
    if (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.button !== 0) return;
    evento.preventDefault();
    link.setAttribute("aria-busy", "true");
    fetch(link.href, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("HTTP " + resposta.status);
        return resposta.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var secao = doc.querySelector("#outras-formas");
        if (!secao) throw new Error("sem seção");
        corpo.replaceChildren(document.importNode(secao, true));
        if (titulo && link.dataset.trocarNome) {
          titulo.textContent = "Outras formas de " + link.dataset.trocarNome.toLowerCase();
        }
        folha.showModal();
      })
      .catch(function () { location.href = link.href; })
      .then(function () { link.removeAttribute("aria-busy"); });
  });

  /* O POST da troca sai daqui e a FICHA recarrega: o card precisa mostrar o
     exercício novo, e a leitura do exercício (para onde a view redireciona)
     é outra tela. Sem `fetch`, o formulário já teria seguido o caminho de
     sempre — este ouvinte só existe dentro da folha. */
  folha.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!(form instanceof HTMLFormElement) || !navigator.onLine) return;
    evento.preventDefault();
    var botao = evento.submitter;
    if (botao) { botao.setAttribute("aria-busy", "true"); botao.disabled = true; }
    fetch(form.action, {
      method: "POST", body: new FormData(form), credentials: "same-origin",
      redirect: "follow", headers: { "X-Requested-With": "fetch" },
    }).then(function () {
      location.reload();
    }).catch(function () {
      form.submit();
    });
  });
})();
/* ==========================================================================
   TOKEN DE CSRF — o do cookie, não o da renderização (22/09/2026)
   ==========================================================================

   A RAIZ do "a sessão caiu e perdi o que digitei". Não há logout em POST
   nenhum neste app; o que há é 403 de CSRF, por dois caminhos medidos:

     1. a página veio do cache do service worker — ele serve a cópia guardada
        quando a rede passa de três segundos — e o campo escondido carrega o
        token de uma sessão anterior;
     2. a pessoa entrou de novo (outra aba, ou a sessão tinha vencido) e
        `login()` chamou `rotate_token()`: o segredo do cookie mudou, e a aba
        aberta continua com o token velho no HTML.

   Nos dois o COOKIE está certo. A fila offline já fazia exatamente isto
   (`fila.js`, "o token é trocado pelo do MOMENTO DO ENVIO") e por isso nunca
   sofreu; quem sofria era o formulário comum — a etapa 2 do cadastro e o
   registro de corrida, os dois longos, os dois citados pelo dono.

   Não enfraquece nada: o cookie só é legível por JavaScript da PRÓPRIA
   origem, que é de onde a defesa vem, e o servidor continua recusando token
   de outro segredo (`config/test_csrf_do_cookie.py` prova os dois lados). É
   o mesmo que a documentação do Django manda fazer em requisição AJAX.

   Duas vezes, e as duas são necessárias: no carregamento, para a página
   vinda do cache nascer certa; e no `submit`, em CAPTURA, para a aba que
   ficou aberta horas enviar com o token de agora. */
(function () {
  "use strict";

  function doCookie() {
    var achado = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return achado ? achado[2] : "";
  }

  function renovar(raiz) {
    var token = doCookie();
    /* Sem cookie não há o que renovar, e escrever "" apagaria o token que o
       servidor mandou — trocar um 403 por outro. */
    if (!token || !raiz || !raiz.querySelectorAll) return;
    var campos = raiz.querySelectorAll("input[name=csrfmiddlewaretoken]");
    for (var i = 0; i < campos.length; i++) {
      if (campos[i].value !== token) campos[i].value = token;
    }
  }

  renovar(document);
  /* `pagereveal` e o mesmo evento que a re-entrega do toque usa: e quando a
     pagina da transicao aparece, inclusive vinda do bfcache. */
  window.addEventListener("pageshow", function () { renovar(document); });
  document.addEventListener("submit", function (evento) {
    renovar(evento.target);
  }, true);
})();
