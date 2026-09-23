# -*- coding: utf-8 -*-
"""Os SETE itens de UX do dono, medidos no app de verdade, com prova.

Conta descartável criada pelo cadastro público do STAGING, apagada pela tela
no fim e login recusado depois — a regra do `CLAUDE.md` para QA em ambiente
publicado. Cada item tem uma asserção dura e uma captura; o passo
`seguranca` lê os cabeçalhos de uma sessão LOGADA, que é o que curl anônimo
não alcança.

    UX_BASE=https://nutriplan-staging.onrender.com python scripts/qa/verificar_ux.py

Nasceu na missão de 22/09/2026 e fica porque é a régua dos sete itens: se um
deles regredir, é aqui que aparece. Não roda no CI (precisa de navegador e
de criar conta); é instrumento de missão.

Três armadilhas que ele já pagou, e que valem para qualquer roteiro novo:

- `E2E.rodar()` termina com `ab("close")` — quem continua depois dele está
  num navegador ANÔNIMO, e a primeira varredura desta missão mediu a tela de
  login doze vezes chamando isso de "zero violação";
- o `eval` do `agent-browser` devolve JSON; com `JSON.stringify` do outro
  lado, são DUAS decodificações;
- `innerText` devolve o texto RENDERIZADO: um `h1` em caixa alta por CSS não
  casa com a frase em minúsculas do template.
"""
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(errors="replace")
from scripts.qa import e2e_staging as e2e  # noqa: E402

BASE = os.environ.get("UX_BASE", "https://nutriplan-staging.onrender.com")
CAPTURAS = Path(os.environ.get("UX_CAPTURAS", "capturas"))
RUN = "uxpwa" + time.strftime("%H%M%S")


class Verificacao(e2e.E2E):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.resultados = []

    # ---------------------------------------------------------------- base
    def js(self, expr):
        """O `eval` do agent-browser devolve JSON. Quando o JS já responde uma
        string JSON (`JSON.stringify(...)`), a primeira decodificação entrega a
        STRING — e é preciso decodificar de novo para virar objeto."""
        valor = self.ab.eval(expr).strip()
        for _ in range(2):
            try:
                novo = json.loads(valor)
            except ValueError:
                break
            valor = novo
            if not isinstance(valor, str):
                break
        return valor

    def foto(self, nome):
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        self.ab("screenshot", str(CAPTURAS / (nome + ".png")))

    def ok(self, item, afirmacao, valor, esperado=True):
        passou = (valor == esperado) if not callable(esperado) else esperado(valor)
        self.resultados.append((item, afirmacao, passou, valor))
        print("   %s %-58s %s" % ("OK  " if passou else "FALHA", afirmacao, "" if passou else repr(valor)[:120]))
        return passou

    def abrir(self, caminho, espera=1200):
        self.ab("open", BASE + caminho, timeout=180)
        self.ab("wait", str(espera))

    # ------------------------------------------------------- 5 + 2: cadastro
    def item_5_e_2(self):
        """Musculação "não faço" esconde academia; depois, com "sim" e SÓ O
        PESO DO CORPO, o equipamento persiste até a ficha."""
        print("== item 5: opção 'não faço treino de força'")
        self.cadastro()
        self.onboarding_1()
        self.ab.marcar("input[name=musculacao][value=nao]")
        self.ab("wait", "600")
        estado = self.js("(function(){var b=document.querySelector('[data-so-musculacao]');"
                         "var d=document.querySelector('[data-sem-musculacao]');"
                         "return JSON.stringify({blocoEscondido: !!(b && b.hidden), notaVisivel: !!(d && !d.hidden),"
                         " equipamentoVisivel: !!document.querySelector('input[name=equipamento]:not([hidden])') && !document.querySelector('[data-so-musculacao]').hidden})})()")
        self.ok(5, "marcar 'não faço' esconde o bloco da academia", estado["blocoEscondido"])
        self.ok(5, "e mostra a nota explicando", estado["notaVisivel"])
        self.foto("item5-nao-faco")

        print("== item 2: equipamento 'só o peso do corpo' persiste")
        self.ab.marcar("input[name=musculacao][value=sim]")
        self.ab("wait", "400")
        for nome, valor in (("goal", "cut"), ("activity_level", "light"),
                            ("experiencia", "iniciante"), ("equipamento", "peso_corporal")):
            self.ab.marcar("input[name=%s][value=%s]" % (nome, valor))
        for dia in (0, 2, 4):
            self.ab.marcar("input[name=weekdays][value='%d']" % dia)
        self.ab("wait", "500")
        self.ab.marcar("input[name=split_preference][value=three]")
        self.foto("item2-etapa2-peso-do-corpo")
        self.enviar()
        self.ab.esperar_url("**/conta/onboarding/3/")
        texto = self.js("JSON.stringify(document.querySelector('main').innerText)")
        self.ok(2, "a etapa 3 resume 'Só o peso do corpo'", "peso do corpo" in texto.lower())
        self.onboarding_3()
        self.abrir("/conta/perfil/", 1500)
        perfil = self.js("JSON.stringify(document.querySelector('main').innerText)")
        self.ok(2, "o Perfil mostra 'peso do corpo'", "peso do corpo" in perfil.lower())
        self.foto("item2-perfil")

    def item_2b_ficha(self):
        """A ficha GERADA reflete o equipamento: nada de barra/máquina."""
        print("== item 2b: a ficha gerada respeita o equipamento")
        self.abrir("/treino/", 2500)
        ficha = self.js("(function(){var a=document.querySelector('a[href*=\"/treino/ficha/\"]');return a?a.getAttribute('href'):''})()")
        if ficha:
            self.abrir(ficha, 2500)
        nomes = self.js("JSON.stringify([].slice.call(document.querySelectorAll('main li, main .exercicio, main h3')).map(function(e){return e.innerText.trim()}).join(' | '))")
        proibidos = [p for p in ("barra", "polia", "máquina", "halter", "smith") if p in nomes.lower()]
        self.ok(2, "a ficha de peso do corpo não traz aparelho", proibidos, esperado=[])
        self.foto("item2-ficha")

    # --------------------------------------------------------------- item 3
    def item_3(self):
        print("== item 3: erro de validação aponta o campo")
        for rota, nome in (("/treino/corridas/nova/", "corrida"), ("/ajuda/reportar/", "reportar")):
            self.abrir(rota, 1500)
            self.js("(function(){var f=document.querySelector('main form');f.noValidate=true;f.requestSubmit();return 1})()")
            self.ab("wait", "1500")
            estado = self.js("(function(){var i=document.querySelector('[aria-invalid=\"true\"]');if(!i)return JSON.stringify({achou:false});"
                             "var r=i.getBoundingClientRect();var d=i.getAttribute('aria-describedby');"
                             "return JSON.stringify({achou:true,foco:document.activeElement===i,visivel:r.top>=0&&r.bottom<=innerHeight,"
                             "descrito:!!(d&&document.getElementById(d.split(' ')[0])),campo:i.name})})()")
            self.ok(3, "%s: campo marcado com aria-invalid" % nome, estado.get("achou"))
            if estado.get("achou"):
                self.ok(3, "%s: recebe foco de teclado" % nome, estado["foco"])
                self.ok(3, "%s: fica visível (rolou até ele)" % nome, estado["visivel"])
                self.ok(3, "%s: aria-describedby aponta o erro" % nome, estado["descrito"])
            self.foto("item3-" + nome)

    # --------------------------------------------------------------- item 6
    def item_6(self):
        print("== item 6: aderencia dos primeiros dias")
        # A caixa de aderencia so nasce com `totals.days`: sem nenhum registro o
        # Progresso esta no estado vazio e nao afirma nada. Marcar uma refeicao
        # e o que poe o primeiro dia na conta -- e e o dia 1 da pessoa.
        self.abrir("/", 2500)
        self.home()
        self.refeicao()
        self.abrir("/historico/", 2500)
        estado = self.js(r"""(function(){
          var t = document.querySelector('.tiles .tile');
          var linha = document.querySelector('.history-row__meals');
          return JSON.stringify({
            caixa: t ? t.innerText.replace(/\s+/g,' ').trim() : null,
            rotulo: t ? ((t.querySelector('.tile__label')||{textContent:''}).textContent) : null,
            meta: t ? ((t.querySelector('.tile__meta')||{textContent:''}).textContent) : null,
            linha: linha ? linha.textContent.trim() : null
          });
        })()""")
        print("      (caixa:", estado.get("caixa"), "| linha:", estado.get("linha"), ")")
        self.ok(6, "a primeira caixa nao e porcentagem de aderencia",
                "%" not in (estado.get("caixa") or ""))
        self.ok(6, "ela conta as refeicoes de hoje", (estado.get("rotulo") or "").strip() == "Refeições")
        self.ok(6, "e diz 'hoje, ate agora'", "até agora" in (estado.get("meta") or ""))
        self.ok(6, "a linha do dia diz 'ate agora', nao 'no plano'",
                "até agora" in (estado.get("linha") or ""))
        self.foto("item6-progresso-dia1")

    # --------------------------------------------------------------- item 4
    def item_4(self):
        print("== item 4: a prioridade muda a tela Hoje")
        self.abrir("/", 2500)
        estado = self.js(r"""(function(){
          var c = document.querySelector('.area-promovida');
          if (!c) return JSON.stringify({cartao:false});
          var acoes = [].slice.call(c.querySelectorAll('a.btn, button.btn, a.btn-link'))
                        .map(function(b){return b.className + ' :: ' + b.textContent.trim()});
          var secoes = [].slice.call(document.querySelectorAll('main section'));
          var refeicao = document.querySelector('.meal');
          return JSON.stringify({
            cartao: true,
            titulo: (c.querySelector('h2')||{}).textContent.trim(),
            acoes: acoes,
            fato: (c.querySelector('.area-promovida__fato')||{textContent:''}).textContent.trim().replace(/\s+/g,' '),
            antesDasRefeicoes: !!(refeicao && (c.compareDocumentPosition(refeicao) & 4)),
            posicao: secoes.indexOf(c) + 1, secoes: secoes.length
          });
        })()""")
        self.ok(4, "a Home tem o cartao da area principal", estado.get("cartao"))
        self.ok(4, "com pelo menos uma acao para dentro da area", len(estado.get("acoes") or []) > 0)
        self.ok(4, "e ele vem ANTES das refeicoes", estado.get("antesDasRefeicoes"))
        print("      (area: %r | secao %s de %s | acoes: %s)"
              % (estado.get("titulo"), estado.get("posicao"), estado.get("secoes"), estado.get("acoes")))
        print("      (fato:", estado.get("fato"), ")")
        self.foto("item4-home-prioridade")

    # --------------------------------------------------------------- item 7
    def item_7(self):
        print("== item 7: o primeiro toque durante a transição")
        self.abrir("/", 2000)
        medida = self.js("""(function(){
          var alvo = document.querySelector('.tabbar .tabbar__item');
          if (!alvo) return JSON.stringify({erro:'sem alvo'});
          var r = alvo.getBoundingClientRect();
          var antes = document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
          return JSON.stringify({alcancavel: !!(antes && (antes===alvo || alvo.contains(antes) || (antes.closest && antes.closest('a')===alvo))),
                                 porCima: antes ? (antes.tagName + '.' + antes.className) : null});
        })()""")
        self.ok(7, "o link da barra é alcançável em repouso", medida.get("alcancavel"))
        print("      (por cima do link:", medida.get("porCima"), ")")
        js_pwa = self.js("(function(){var s=[].slice.call(document.querySelectorAll('script[src]'))"
                         ".filter(function(e){return /pwa[.][^/]*js/.test(e.src)})[0];"
                         "return fetch(s.src).then(function(r){return r.text()}).then(function(t){"
                         "return JSON.stringify({replay: t.indexOf('pagereveal')>0, finished: t.indexOf('viewTransition.finished')>0})})})()")
        self.ok(7, "o pwa.js tem o replay do toque no pagereveal", js_pwa.get("replay"))
        self.ok(7, "e reentrega no viewTransition.finished", js_pwa.get("finished"))

    # --------------------------------------------------------------- item 1
    def item_1(self):
        """O ANTES desta missão está no histórico: com o token velho no campo
        escondido, o envio caía em "Este envio não pôde ser confirmado" e o
        que a pessoa digitou só voltava pelo rascunho. O DEPOIS é este: o
        mesmo envio SALVA, porque `pwa.js` reescreve o token com o do cookie.
        A rede de segurança (403 em português + rascunho) continua existindo
        para o caso que sobra — a sessão que venceu de verdade."""
        print("== item 1: token velho no formulário, e o que acontece")
        self.abrir("/treino/corridas/nova/", 1500)
        self.ab("fill", "input[name=distancia_km]", "7,5")
        self.ab("fill", "input[name=tempo]", "00:42:10")
        self.ab("wait", "800")
        self.js("(function(){document.querySelector('main form input[name=csrfmiddlewaretoken]').value='token-de-outra-aba';"
                "document.querySelector('main form').requestSubmit();return 1})()")
        self.ab("wait", "2500")
        pagina = self.js("JSON.stringify({titulo:document.title,caminho:location.pathname,"
                         "h1:(document.querySelector('h1')||{textContent:''}).textContent.trim()})")
        print("      (depois:", pagina, ")")
        self.ok(1, "o envio com token velho NÃO cai no 403", "não pôde ser confirmado" not in pagina["h1"].lower())
        self.ok(1, "e a corrida foi gravada (saiu do formulário)", pagina["caminho"] != "/treino/corridas/nova/")
        self.foto("item1-token-velho-passa")

    # ----------------------------------------------------- cabeçalhos
    def seguranca(self):
        """Os cabeçalhos e cookies que uma sessão LOGADA recebe de verdade.

        Medido de dentro da própria origem (`fetch` same-origin enxerga todos
        os cabeçalhos de resposta), e não por curl anônimo: o que interessa é
        a tela com dado de saúde, que só existe logado."""
        print("== auditoria: cabeçalhos e cookies da sessão logada")
        self.abrir("/", 1500)
        dados = self.js(r"""(function(){
          var rotas = ['/', '/historico/', '/treino/', '/conta/perfil/', '/conta/entrar/'];
          return Promise.all(rotas.map(function(r){
            return fetch(r, {credentials:'same-origin'}).then(function(res){
              var h = {};
              ['cache-control','content-security-policy','x-frame-options','strict-transport-security',
               'referrer-policy','x-content-type-options','vary','permissions-policy',
               'cross-origin-opener-policy','cross-origin-resource-policy','cross-origin-embedder-policy']
                .forEach(function(n){ var v = res.headers.get(n); if (v) h[n] = v; });
              return {rota:r, status:res.status, cabecalhos:h};
            });
          })).then(function(tudo){
            return JSON.stringify({rotas: tudo, cookiesVisiveisAoJS: document.cookie.split('; ').map(function(c){return c.split('=')[0]}).sort()});
          });
        })()""")
        for r in dados["rotas"]:
            print("   %-18s %s  %s" % (r["rota"], r["status"], r["cabecalhos"]))
        print("   cookies que o JavaScript enxerga:", dados["cookiesVisiveisAoJS"])
        self.ok("seg", "sessionid NAO e legivel pelo JavaScript (HttpOnly)",
                "sessionid" not in dados["cookiesVisiveisAoJS"])
        privadas = [r for r in dados["rotas"] if r["rota"] not in ("/", "/conta/entrar/")]
        self.ok("seg", "toda tela com dado de saude manda Cache-Control",
                all(r["cabecalhos"].get("cache-control") for r in privadas))
        self.ok("seg", "e nenhuma delas pode ficar em cache compartilhado",
                all("private" in (r["cabecalhos"].get("cache-control") or "") or
                    "no-store" in (r["cabecalhos"].get("cache-control") or "") for r in privadas))
        self.ok("seg", "ha Content-Security-Policy",
                all(r["cabecalhos"].get("content-security-policy") for r in dados["rotas"]))
        self.seguranca_medida = dados

    # ---------------------------------------------------------------- final
    def relatorio(self):
        falhas = [r for r in self.resultados if not r[2]]
        print("\n== RESUMO: %d asserções, %d falhas" % (len(self.resultados), len(falhas)))
        for item, afirmacao, _, valor in falhas:
            print("   item %s: %s -> %r" % (item, afirmacao, valor))
        return falhas


PASSOS = ("item-5-e-2", "item-2b-ficha", "item-3", "item-4", "item-7", "item-6", "seguranca", "item-1", "excluir", "login-recusado")


def main():
    ambiente = e2e.ambiente_de(BASE)
    print("== alvo:", BASE, "| ambiente:", repr(ambiente) or "produção")
    e2e.PASSOS = PASSOS
    v = Verificacao(BASE, CAPTURAS, RUN)
    codigo = v.rodar()
    falhas = v.relatorio()
    sys.exit(1 if (codigo or falhas) else 0)


if __name__ == "__main__":
    main()
