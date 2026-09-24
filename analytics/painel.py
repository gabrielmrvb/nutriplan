"""O painel de analytics — cinco telas sob /gestao/analytics/.

Mesma permissão da gerência (`PainelDeGestaoMixin`, `ver_painel_de_gestao`), e
não `is_staff`: a doutrina do `gestao/acesso.py` diz por quê (staff é sobre o
Django Admin; "como o produto vai" é outra pergunta).

Cada tela fica abaixo de 15 consultas (`test_painel_orcamento.py`) e não cresce
com o volume — a camada `consultas.py` faz o trabalho, aqui é só montar.
"""
import csv

from django.http import Http404, HttpResponse
from django.views.generic import TemplateView

from gestao.acesso import PainelDeGestaoMixin

from . import catalogo, consultas

PERIODOS = (7, 30, 90)


def _periodo(request):
    try:
        dias = int(request.GET.get("dias", 30))
    except (TypeError, ValueError):
        dias = 30
    return dias if dias in PERIODOS else 30


def _pontos(serie, chave="n", largura=680, altura=120):
    """Geometria de uma linha do tempo para um <polyline> SVG."""
    if not serie:
        return {"pontos": "", "max": 0, "barras": []}
    valores = [linha[chave] for linha in serie]
    maximo = max(valores) or 1
    n = len(serie)
    passo = largura / max(n - 1, 1)
    pontos = " ".join(
        "%.1f,%.1f" % (i * passo, altura - (v / maximo) * (altura - 8))
        for i, v in enumerate(valores)
    )
    barras = [
        {"x": i * passo, "h": (v / maximo) * (altura - 8), "v": v,
         "rotulo": linha.get("dia") or linha.get("valor") or ""}
        for i, (v, linha) in enumerate(zip(valores, serie))
    ]
    return {"pontos": pontos, "max": maximo, "barras": barras,
            "largura": largura, "altura": altura}


class VisaoGeralView(PainelDeGestaoMixin, TemplateView):
    template_name = "analytics/visao_geral.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dias = _periodo(self.request)
        total, erros = consultas.erros_js(dias)
        ctx.update(
            {
                "aba": "analytics",
                "sub": "geral",
                "sem_tabbar": True,
                "dias": dias,
                "periodos": PERIODOS,
                "dau": consultas.ativos(1),
                "wau": consultas.ativos(7),
                "mau": consultas.ativos(30),
                "por_dia": _pontos(consultas.eventos_por_dia(dias)),
                "top_eventos": consultas.top_eventos(dias),
                "top_rotas": consultas.top_rotas(dias),
                "erros_total": total,
                "erros": erros,
            }
        )
        return ctx


class ExplorarView(PainelDeGestaoMixin, TemplateView):
    template_name = "analytics/explorar.html"

    def get(self, request, *args, **kwargs):
        dados = self._dados(request)
        if request.GET.get("formato") == "csv":
            return self._csv(dados)
        return self.render_to_response(self.get_context_data(dados=dados, **kwargs))

    def _dados(self, request):
        dias = _periodo(request)
        nome = request.GET.get("evento")
        if nome and not catalogo.existe(nome):
            nome = None
        agrupar = request.GET.get("agrupar") or None
        filtros = {}
        for chave in list(consultas.ATRIBUTOS) + ["opcao", "origem", "letra"]:
            valor = request.GET.get("f_" + chave)
            if valor:
                filtros[chave] = valor
        linhas = consultas.explorar(nome, dias, filtros, agrupar) if nome else []
        return {"dias": dias, "nome": nome, "agrupar": agrupar,
                "filtros": filtros, "linhas": linhas}

    def _csv(self, dados):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="analytics.csv"'
        w = csv.writer(resp)
        chave = "valor" if dados["agrupar"] else "dia"
        w.writerow([chave, "eventos", "pessoas"])
        for linha in dados["linhas"]:
            w.writerow([linha.get(chave), linha.get("n"), linha.get("pessoas")])
        return resp

    def get_context_data(self, dados=None, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dados = dados or self._dados(self.request)
        grafico = _pontos(dados["linhas"], "n") if dados["linhas"] else None
        ctx.update(
            {
                "aba": "analytics",
                "sub": "explorar",
                "sem_tabbar": True,
                "periodos": PERIODOS,
                "catalogo": sorted(catalogo.CATALOGO),
                "atributos": sorted(consultas.ATRIBUTOS),
                "grafico": grafico,
                **dados,
            }
        )
        return ctx


class FunilView(PainelDeGestaoMixin, TemplateView):
    template_name = "analytics/funil.html"

    #: Funis prontos, e um livre por querystring (`?passos=a,b,c`).
    PRONTOS = {
        "onboarding": ["onboarding.iniciado", "onboarding.etapa_concluida",
                       "onboarding.concluido", "treino.iniciado"],
        "ativacao": ["conta.criada", "onboarding.concluido",
                     "dieta.refeicao_registrada", "treino.serie_concluida"],
    }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dias = _periodo(self.request)
        pedido = self.request.GET.get("passos")
        if pedido:
            passos = [p for p in pedido.split(",") if catalogo.existe(p)]
            nome = "livre"
        else:
            nome = self.request.GET.get("funil", "onboarding")
            passos = self.PRONTOS.get(nome, self.PRONTOS["onboarding"])
        etapas = consultas.funil(passos, dias) if len(passos) >= 2 else []
        base = etapas[0]["pessoas"] if etapas else 0
        for e in etapas:
            e["pct"] = round(100 * e["pessoas"] / base) if base else 0
            e["mediana_min"] = round(e["mediana_s"] / 60, 1) if e["mediana_s"] else None
        ctx.update(
            {
                "aba": "analytics", "sub": "funil", "sem_tabbar": True,
                "dias": dias, "periodos": PERIODOS,
                "prontos": list(self.PRONTOS), "funil_nome": nome,
                "etapas": etapas,
            }
        )
        return ctx


class EntradaView(PainelDeGestaoMixin, TemplateView):
    """ONDE A PESSOA DESISTE — o funil de entrada por coorte.

    A tela "Funil" ao lado é a ferramenta genérica (qualquer sequência de
    eventos, total da janela). Esta é a PERGUNTA de produto, com os passos
    nomeados na ordem em que a pessoa os vive e o resultado por coorte de dia
    ou de semana. As duas convivem porque respondem coisas diferentes: uma é
    "como converte esta sequência?", a outra é "como a entrada foi na
    terça?".

    O número que a tela destaca é a taxa DO PASSO ANTERIOR, e não a do topo:
    "de quem chegou na etapa 2, quantos terminaram?" é a pergunta que aponta
    o degrau quebrado; a do topo só diz que o funil é um funil.
    """

    template_name = "analytics/entrada.html"
    GRANULARIDADES = ("dia", "semana")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dias = _periodo(self.request)
        por = self.request.GET.get("por")
        por = por if por in self.GRANULARIDADES else "dia"
        coortes, total = consultas.funil_de_entrada(dias, por=por)
        rotulos = {chave: rotulo for chave, rotulo, _n, _f in consultas.PASSOS_DE_ENTRADA}
        for etapa in total["etapas"]:
            etapa["rotulo"] = rotulos[etapa["chave"]]
        ctx.update(
            {
                "aba": "analytics", "sub": "entrada", "sem_tabbar": True,
                "dias": dias, "periodos": PERIODOS,
                "por": por, "granularidades": self.GRANULARIDADES,
                # Da coorte mais RECENTE para a mais antiga: a tela abre no
                # que acabou de acontecer, que é o que se olha todo dia.
                "coortes": list(reversed(coortes)),
                "total": total,
                "passos": [rotulos[c] for c in rotulos],
            }
        )
        return ctx


class UsoPorAreaView(PainelDeGestaoMixin, TemplateView):
    """O QUE A BASE USA DE FATO — registros e pessoas por área, por semana.

    REGISTRO, e não visita: abrir a tela de água não é beber água, e um painel
    que conta aberturas mede curiosidade. A lista de eventos por área é
    `consultas.EVENTOS_DA_AREA`, a mesma de onde a retenção tira o "voltou".
    """

    template_name = "analytics/uso.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semanas = consultas.uso_por_area(semanas=8)
        ctx.update(
            {
                "aba": "analytics", "sub": "uso", "sem_tabbar": True,
                "areas": list(consultas.EVENTOS_DA_AREA),
                "semanas": list(reversed(semanas)),
            }
        )
        return ctx


class RetencaoView(PainelDeGestaoMixin, TemplateView):
    template_name = "analytics/retencao.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "aba": "analytics", "sub": "retencao", "sem_tabbar": True,
                "linhas": consultas.retencao(semanas=8),
                "semanas": range(8),
                # D1 / D7 / D30 por coorte de cadastro (24/09/2026): a matriz
                # acima é a curva de longo prazo (semana a semana de
                # retorno); esta é a régua de produto, e "voltou" é ter
                # REGISTRADO alguma coisa, não ter aberto o app.
                "degraus": consultas.DEGRAUS_DE_RETENCAO,
                "coortes": list(reversed(consultas.retencao_por_coorte(semanas=8))),
            }
        )
        return ctx


class UsuarioView(PainelDeGestaoMixin, TemplateView):
    template_name = "analytics/usuario.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        chave = (self.request.GET.get("id") or "").strip()
        eventos = consultas.linha_do_tempo(chave) if chave else None
        ctx.update(
            {
                "aba": "analytics", "sub": "usuario", "sem_tabbar": True,
                "chave": chave, "eventos": eventos,
            }
        )
        return ctx
