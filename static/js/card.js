/* O card compartilhável do NutriPlan.
 *
 * Generaliza o card que já existia dentro de `workouts/routine.html`, e não
 * abre um sistema paralelo: aquele desenhava só "treino concluído", em 1080x1350,
 * com as cores escritas à mão no meio do JavaScript. Duas coisas mudaram:
 *
 *   1. AS CORES VÊM DOS TOKENS. `getComputedStyle` lê as mesmas variáveis que a
 *      interface usa. O card antigo tinha `#090c0b` fixo — o grafite ESVERDEADO
 *      que o design system abandonou quando o matiz foi para o azul (`#0d0f12`).
 *      O card estava divulgando uma identidade que o app não tem mais, e nada
 *      apontava isso porque hex fixo não quebra.
 *
 *   2. DOIS FORMATOS. 1080x1350 continua sendo o do feed, e 1080x1920 entra para
 *      o story. Nenhum dos dois é redimensionamento do outro: o story tem espaço
 *      vertical de sobra e a margem de segurança das barras do Instagram, então
 *      as duas medidas de recuo são diferentes de propósito.
 *
 * Desenhado em canvas NO APARELHO, como antes. Uma imagem por conquista por
 * pessoa seria processamento e armazenamento para um arquivo que vive trinta
 * segundos até virar story.
 *
 * PRIVACIDADE. Este arquivo desenha o que recebe, e quem decide o que ele
 * recebe é o servidor. Carga levantada, peso corporal, medida e restrição
 * alimentar não chegam aqui — ver `achievements/regras.py`, que explica por que
 * a chave do recorde é `exercício:data` e não `exercício:carga`.
 */
(function (raiz) {
  "use strict";

  var FORMATOS = {
    feed: { w: 1080, h: 1350, topo: 150, base: 150 },
    /* O story reserva mais respiro em cima e embaixo: é onde o Instagram
     * desenha o nome de quem postou e a caixa de resposta. Conteúdo colado
     * nessas bordas fica coberto no aparelho de quem vê. */
    story: { w: 1080, h: 1920, topo: 380, base: 420 }
  };

  /* Os tipos que o card sabe desenhar hoje.
   *
   * Os três últimos estão declarados e NÃO implementados, de propósito: são os
   * que dependem de dado que o NutriPlan ainda não coleta. Deixá-los nomeados
   * aqui é o que permite `tipoConhecido()` recusar com uma mensagem clara em
   * vez de desenhar um card vazio. */
  var TIPOS = {
    TRAINING_COMPLETE: desenharTreino,
    STREAK: desenharNumeroGrande,
    PERSONAL_RECORD: desenharConquista,
    WEEKLY_GOAL: desenharConquista,
    BODY_PROGRESS: null,
    RUN_COMPLETE: null,
    CHALLENGE_COMPLETE: null
  };

  function token(nome, alternativa) {
    var v = getComputedStyle(document.documentElement)
      .getPropertyValue(nome)
      .trim();
    return v || alternativa;
  }

  function paleta() {
    /* As alternativas existem para o card não sair preto num contexto onde as
     * variáveis não resolvem — canvas fora do documento, por exemplo. São os
     * valores ATUAIS do tema escuro, e precisam ser revisados junto dele. */
    return {
      fundo: token("--bg", "#0d0f12"),
      cartao: token("--surface", "#15181e"),
      borda: token("--border", "#2a2e39"),
      marca: token("--brand", "#4ade9b"),
      texto: token("--text", "#ffffff"),
      fraco: token("--text-mute", "#8b93a3")
    };
  }

  var FONTE = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif";

  function caixaArredondada(g, x, y, w, h, r) {
    /* `roundRect` é recente demais para o Safari que ainda circula nas
     * academias; o caminho à mão funciona em tudo. */
    g.beginPath();
    g.moveTo(x + r, y);
    g.arcTo(x + w, y, x + w, y + h, r);
    g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r);
    g.arcTo(x, y, x + w, y, r);
    g.closePath();
  }

  function fundo(g, f, cor) {
    g.fillStyle = cor.fundo;
    g.fillRect(0, 0, f.w, f.h);

    /* Um halo atrás do número, e é o único enfeite. Existe porque retângulo
     * escuro com texto branco não é imagem que alguém posta. */
    var meio = f.topo + (f.h - f.topo - f.base) / 2;
    var brilho = g.createRadialGradient(f.w / 2, meio, 40, f.w / 2, meio, 620);
    brilho.addColorStop(0, "rgba(74,222,155,.18)");
    brilho.addColorStop(1, "rgba(74,222,155,0)");
    g.fillStyle = brilho;
    g.fillRect(0, 0, f.w, f.h);
  }

  function marca(g, f, cor) {
    /* Discreta, e no rodapé: o protagonista é o resultado de quem postou. Um
     * logo grande transformaria a conquista da pessoa em anúncio, e aí ela
     * simplesmente não posta. */
    g.textAlign = "center";
    g.fillStyle = cor.marca;
    g.font = "700 34px " + FONTE;
    g.fillText("NUTRIPLAN", f.w / 2, f.h - f.base + 60);

    g.fillStyle = cor.fraco;
    g.font = "400 26px " + FONTE;
    g.fillText("Minha evolução. Meu plano.", f.w / 2, f.h - f.base + 106);
  }

  function titulo(g, f, cor, texto) {
    g.textAlign = "center";
    g.fillStyle = cor.fraco;
    g.font = "700 30px " + FONTE;
    g.fillText(texto.toUpperCase(), f.w / 2, f.topo + 40);
  }

  function numeroGrande(g, f, cor, valor, rotulo) {
    var meio = f.topo + (f.h - f.topo - f.base) / 2;
    g.textAlign = "center";

    g.fillStyle = cor.texto;
    g.font = "800 260px " + FONTE;
    g.fillText(String(valor), f.w / 2, meio + 60);

    g.fillStyle = cor.marca;
    g.font = "700 46px " + FONTE;
    g.fillText(rotulo.toUpperCase(), f.w / 2, meio + 150);
  }

  function frase(g, f, cor, texto) {
    g.textAlign = "center";
    g.fillStyle = cor.fraco;
    g.font = "400 34px " + FONTE;

    /* Quebra por palavra: nome de exercício é comprido por natureza, e uma
     * linha só estouraria a largura no card como estoura na ficha. */
    var largura = f.w - 200;
    var linhas = [];
    var atual = "";
    texto.split(" ").forEach(function (palavra) {
      var tentativa = atual ? atual + " " + palavra : palavra;
      if (g.measureText(tentativa).width > largura && atual) {
        linhas.push(atual);
        atual = palavra;
      } else {
        atual = tentativa;
      }
    });
    if (atual) linhas.push(atual);

    var y = f.h - f.base - 40 - (linhas.length - 1) * 46;
    linhas.forEach(function (linha) {
      g.fillText(linha, f.w / 2, y);
      y += 46;
    });
  }

  /* ---------------------------------------------------------- os desenhos */

  function desenharNumeroGrande(g, f, cor, d) {
    titulo(g, f, cor, d.titulo || "Conquista");
    numeroGrande(g, f, cor, d.valor, d.rotulo || "");
    if (d.frase) frase(g, f, cor, d.frase);
  }

  function desenharConquista(g, f, cor, d) {
    titulo(g, f, cor, d.titulo || "Conquista");

    var meio = f.topo + (f.h - f.topo - f.base) / 2;
    g.textAlign = "center";
    g.fillStyle = cor.texto;
    g.font = "800 96px " + FONTE;
    g.fillText(d.destaque || "", f.w / 2, meio + 20);

    if (d.rotulo) {
      g.fillStyle = cor.marca;
      g.font = "700 40px " + FONTE;
      g.fillText(d.rotulo.toUpperCase(), f.w / 2, meio + 90);
    }
    if (d.frase) frase(g, f, cor, d.frase);
  }

  function desenharTreino(g, f, cor, d) {
    titulo(g, f, cor, "Treino concluído");

    var meio = f.topo + (f.h - f.topo - f.base) / 2;
    g.textAlign = "center";
    g.fillStyle = cor.texto;
    g.font = "800 72px " + FONTE;
    g.fillText(d.nome || "Treino", f.w / 2, f.topo + 150);

    /* Três blocos, e não uma tabela: no story a pessoa vê por dois segundos. */
    var blocos = [
      [d.exercicios, "exercícios"],
      [d.series, "séries"],
      [d.volume, "kg de volume"]
    ].filter(function (b) {
      return b[0] !== undefined && b[0] !== null && b[0] !== "";
    });

    var altura = 150;
    var espaco = 26;
    var total = blocos.length * altura + (blocos.length - 1) * espaco;
    var y = meio - total / 2 + 40;

    blocos.forEach(function (bloco) {
      g.fillStyle = cor.cartao;
      caixaArredondada(g, 120, y, f.w - 240, altura, 28);
      g.fill();
      g.strokeStyle = cor.borda;
      g.lineWidth = 2;
      g.stroke();

      g.fillStyle = cor.texto;
      g.font = "800 64px " + FONTE;
      g.fillText(String(bloco[0]), f.w / 2, y + 82);

      g.fillStyle = cor.fraco;
      g.font = "600 28px " + FONTE;
      g.fillText(bloco[1].toUpperCase(), f.w / 2, y + 122);

      y += altura + espaco;
    });

    if (d.frase) frase(g, f, cor, d.frase);
  }

  /* ------------------------------------------------------------- fachada */

  function tipoConhecido(tipo) {
    return typeof TIPOS[tipo] === "function";
  }

  function desenhar(tipo, dados, formato) {
    if (!tipoConhecido(tipo)) {
      throw new Error("Card sem desenho para o tipo " + tipo);
    }
    var f = FORMATOS[formato] || FORMATOS.feed;
    var c = document.createElement("canvas");
    c.width = f.w;
    c.height = f.h;

    var g = c.getContext("2d");
    var cor = paleta();

    fundo(g, f, cor);
    TIPOS[tipo](g, f, cor, dados || {});
    marca(g, f, cor);
    return c;
  }

  /* Compartilhar de verdade quando o aparelho sabe — é o caminho do celular, e
   * leva direto ao Instagram ou ao WhatsApp. No desktop a API não existe, e aí
   * baixar é o que sobra.
   *
   * O que este código NÃO faz, e não pode prometer: publicar no Instagram
   * sozinho. A web não tem essa API. `navigator.share` abre a bandeja do
   * sistema e QUEM ESCOLHE é a pessoa — sempre com um gesto dela. */
  function podeCompartilharArquivo(arquivo) {
    return !!(navigator.canShare && navigator.canShare({ files: [arquivo] }));
  }

  function compartilhar(canvas, nome, titulo) {
    return new Promise(function (resolve) {
      canvas.toBlob(function (blob) {
        if (!blob) return resolve({ ok: false, via: "sem-blob" });

        var arquivo = new File([blob], nome, { type: "image/png" });
        if (podeCompartilharArquivo(arquivo)) {
          navigator
            .share({ files: [arquivo], title: titulo })
            .then(function () { resolve({ ok: true, via: "share" }); })
            .catch(function () {
              /* Cancelar não é erro: a pessoa mudou de ideia. */
              resolve({ ok: false, via: "cancelado" });
            });
          return;
        }

        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = nome;
        link.click();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        resolve({ ok: true, via: "download" });
      }, "image/png");
    });
  }

  /* Um handler so, delegado, para os dois lugares que compartilham conquista:
   * o aviso que aparece depois da serie e a tela "Minhas conquistas". Dois
   * listeners fariam o mesmo trabalho em dois arquivos, e um dos dois ficaria
   * para tras.
   *
   * Tudo o que ele desenha vem de `data-`, escrito pelo servidor. Nenhum campo
   * e lido do DOM da pagina nem do perfil — e o que garante que peso corporal,
   * e-mail e carga nao entrem no card por acidente. */
  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-conquista-share]");
    if (!botao) return;
    evento.preventDefault();

    var d = botao.dataset;
    var tipo = tipoConhecido(d.tipo) ? d.tipo : "WEEKLY_GOAL";
    var canvas = desenhar(tipo, {
      titulo: d.titulo || "Conquista",
      frase: d.frase || "",
      valor: d.valor || "",
      rotulo: d.rotulo || "",
      destaque: d.destaque || ""
    }, d.formato === "feed" ? "feed" : "story");

    compartilhar(canvas, "conquista-nutriplan.png", d.titulo || "Minha conquista");
  });

  raiz.NutriPlanCard = {
    FORMATOS: FORMATOS,
    desenhar: desenhar,
    compartilhar: compartilhar,
    tipoConhecido: tipoConhecido,
    podeCompartilharArquivo: podeCompartilharArquivo
  };
})(window);
