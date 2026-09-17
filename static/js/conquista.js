/* O aviso de conquista: a fila, o Esc e o som opcional — e o interruptor
 * da tela de conquistas.
 *
 * FILA. "Próxima" avança um slide; só o último envia o formulário. Isto
 * morava inline em `partials/_conquista.html`; saiu de lá para cá quando o
 * arquivo ganhou o resto (Esc e som) — um `<script>` por responsabilidade é
 * uma pilha maior de scripts pequenos, e não um arquivo maior.
 *
 * A VARIANTE de recorde (`conquista--recorde`) nascia fixada na família do
 * slide 0 — o servidor decide isso sem JS, porque o primeiro slide não
 * precisa esperar nenhum clique. Mas quem tem "Primeiro treino" na frente de
 * dois recordes na mesma fila via os slides de recorde SEM o frame: nada
 * reavaliava a classe ao trocar de slide. Por isso "Próxima" também lê
 * `data-familia` do slide que acabou de ficar visível e liga/desliga a
 * variante — o dado já vinha no HTML (um atributo por slide, e não só no
 * container), só faltava alguém ler.
 *
 * ESC. O mesmo POST de "Continuar", por `fetch`, e o aviso some sem
 * recarregar. Não tira o foco de ninguém: o aviso nunca o tomou (é
 * `role="status"`, não `dialog`), e Esc aqui só oferece a MESMA saída que o
 * botão já oferece, para quem prefere teclado.
 *
 * SOM. Opt-in em `localStorage`, e NUNCA ligado pelo servidor — o HTML do
 * aviso não carrega marca nenhuma de "tocar". Três notas curtas por
 * `AudioContext`, e só depois de um gesto: a política de autoplay do
 * navegador recusa som antes de qualquer toque, e tentar antes disso não
 * falha alto, só fica mudo sem avisar.
 *
 * O INTERRUPTOR de /conquistas/ vive no mesmo arquivo, e roda INDEPENDENTE
 * do resto: a tela pode abrir sem nenhum aviso pendente, e o interruptor
 * precisa ler e gravar a escolha mesmo assim.
 */
(function () {
  "use strict";

  var CHAVE_SOM = "nutriplan.som-conquista";

  var caixa = document.querySelector("[data-conquista]");
  if (caixa) {
    var slides = caixa.querySelectorAll("[data-conquista-slide]");
    var form = caixa.querySelector(".conquista__fechar-form");

    caixa.addEventListener("click", function (evento) {
      var botao = evento.target.closest("[data-conquista-proxima]");
      if (!botao) return;
      evento.preventDefault();

      for (var i = 0; i < slides.length; i++) {
        if (!slides[i].hidden) {
          slides[i].hidden = true;
          if (slides[i + 1]) {
            slides[i + 1].hidden = false;
            caixa.classList.toggle(
              "conquista--recorde",
              slides[i + 1].dataset.familia === "recorde"
            );
          }
          return;
        }
      }
    });

    var fechar = function () {
      if (!form) return;
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      })
        .catch(function () {})
        .finally(function () {
          caixa.remove();
          document.body.classList.remove("tem-conquista");
        });
    };
    document.addEventListener("keydown", function (evento) {
      // Com o drawer de vídeo aberto, o Esc é DELE primeiro: fechar os dois
      // de uma vez tiraria o vídeo da tela ao mesmo tempo em que o aviso
      // muda o layout por baixo. `dialog[open]` é o mesmo sinal que
      // `pwa.js` já usa para calar o convite de instalação.
      if (evento.key === "Escape" && !document.querySelector("dialog[open]")) fechar();
    });

    var querSom = false;
    try {
      querSom = localStorage.getItem(CHAVE_SOM) === "1";
    } catch (e) {}

    if (querSom) {
      // Marca de dados, e não decisão do servidor — ver o docstring do
      // interruptor abaixo. Nada além de CSS/depuração lê isto hoje.
      caixa.setAttribute("data-som", "1");

      if (window.AudioContext) {
        var tocar = function () {
          document.removeEventListener("pointerdown", tocar);
          var ctx = new AudioContext();
          var t = ctx.currentTime;
          [523.25, 659.25, 783.99].forEach(function (freq, i) {
            var osc = ctx.createOscillator();
            var ganho = ctx.createGain();
            osc.frequency.value = freq;
            osc.connect(ganho);
            ganho.connect(ctx.destination);
            ganho.gain.setValueAtTime(0.0001, t + i * 0.13);
            ganho.gain.exponentialRampToValueAtTime(0.2, t + i * 0.13 + 0.02);
            ganho.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.13 + 0.16);
            osc.start(t + i * 0.13);
            osc.stop(t + i * 0.13 + 0.18);
          });
        };
        document.addEventListener("pointerdown", tocar, { once: true });
      }
    }
  }

  // ---------------------------------------------- o interruptor de /conquistas/
  //
  // "Tocar um som ao desbloquear": desligado por padrão (o `checked` inicial
  // só existe se `localStorage` já disser "1"), e a escolha é só do
  // navegador — não há campo nenhum que mande isto para o servidor.
  var interruptor = document.querySelector("[data-som-conquista]");
  if (interruptor) {
    try {
      interruptor.checked = localStorage.getItem(CHAVE_SOM) === "1";
    } catch (e) {}

    interruptor.addEventListener("change", function () {
      try {
        if (interruptor.checked) {
          localStorage.setItem(CHAVE_SOM, "1");
        } else {
          localStorage.removeItem(CHAVE_SOM);
        }
      } catch (e) {}
    });
  }
})();
