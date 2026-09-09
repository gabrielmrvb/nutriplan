
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
    corpo.set("food_id", caixa.getAttribute("data-food"));
    corpo.set("opcao", caixa.getAttribute("data-opcao"));
    corpo.set("semana", caixa.getAttribute("data-semana"));
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
