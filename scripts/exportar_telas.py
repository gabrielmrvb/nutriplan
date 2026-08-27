"""
Exporta telas do NutriPlan como HTML autocontido, para análise externa.

POR QUE ISTO EXISTE, e não um "gerar_arquivo_unico.py"
-----------------------------------------------------
O NutriPlan é Django: as páginas nascem no servidor, exigem login, consultam o
PostgreSQL e são várias — não existe um `index.html` para embrulhar. Juntar o
projeto "num arquivo só" como se faz num app estático não é possível nem
desejável aqui.

O equivalente honesto é este: renderizar cada tela já logada e gravar o
resultado com o CSS e o JS embutidos. Sai um arquivo por tela, cada um abrindo
sozinho no navegador, sem servidor, sem banco e sem login. Serve para duas
coisas ao mesmo tempo:

  · mandar para uma IA analisar (ela lê o HTML e o CSS de verdade)
  · tirar as capturas de tela sem precisar autenticar o navegador

Como rodar:

    .venv/Scripts/python.exe scripts/exportar_telas.py

Sai em `.ui_snapshots/html/`.
"""

import io
import json
import os
import re
import sys

import django

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, ".ui_snapshots", "html")

sys.path.insert(0, RAIZ)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.staticfiles import finders  # noqa: E402
from django.test import Client  # noqa: E402

# O cliente de teste se apresenta como host "testserver", que a produção
# recusa — e recusar é o comportamento certo dela. Liberar aqui, dentro deste
# processo, mantém o `settings.py` do app intocado: nada disso vaza para o
# servidor de verdade.
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

EMAIL_DEMO = "joao@demo.local"

# Cada tela: (nome do arquivo, URL, rótulo humano, ajustes no HTML).
# `abrir_details` recebe o texto do <summary> e força aquele bloco aberto — é
# assim que a captura mostra "Comi outra coisa" expandido, sem precisar de um
# navegador que clique.
TELAS = [
    {
        "nome": "01-onboarding-objetivo",
        "url": "/conta/onboarding/2/",
        "rotulo": "Onboarding · Seu objetivo",
    },
    {
        "nome": "02-onboarding-divisao",
        "url": "/conta/onboarding/4/",
        "rotulo": "Onboarding · Sua divisão de treino",
    },
    {
        "nome": "03-diario-alimentar",
        "url": "/",
        "rotulo": "Dashboard · Diário alimentar",
    },
    {
        "nome": "04-diario-comi-outra-coisa",
        "url": "/",
        "rotulo": 'Dashboard · "Comi outra coisa" expandido',
        "abrir_details": "Comi outra coisa",
    },
    {
        "nome": "05-ficha-de-treino",
        "url": "/treino/",
        "rotulo": "Ficha de treino · Divisão",
    },
    {
        "nome": "06-ajustes-perfil",
        "url": "/conta/perfil/",
        "rotulo": "Ajustes · Seus dados",
    },
]


def ler_estatico(caminho_url):
    """Acha um arquivo de /static/ no disco e devolve o conteúdo."""
    relativo = caminho_url.split("/static/", 1)[-1].split("?")[0]
    achado = finders.find(relativo)
    if not achado:
        return None
    with io.open(achado, encoding="utf-8", errors="replace") as arquivo:
        return arquivo.read()


def embutir(html):
    """Troca <link> e <script src> pelo conteúdo dos arquivos.

    O que não for encontrado vira um comentário dizendo o que faltou — melhor
    do que uma referência quebrada que ninguém percebe.
    """
    faltando = []

    def trocar_css(achado):
        href = achado.group(1)
        if not href.startswith("/static/"):
            return achado.group(0)
        conteudo = ler_estatico(href)
        if conteudo is None:
            faltando.append(href)
            return "<!-- nao encontrado: {} -->".format(href)
        return "<style>\n/* {} */\n{}\n</style>".format(href, conteudo)

    html = re.sub(
        r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"[^>]*>',
        trocar_css, html,
    )

    def trocar_js(achado):
        src = achado.group(1)
        if not src.startswith("/static/"):
            return "<!-- script externo removido: {} -->".format(src)
        conteudo = ler_estatico(src)
        if conteudo is None:
            faltando.append(src)
            return "<!-- nao encontrado: {} -->".format(src)
        conteudo = conteudo.replace("</script>", "<\\/script>")
        return "<script>\n/* {} */\n{}\n</script>".format(src, conteudo)

    html = re.sub(r'<script[^>]+src="([^"]+)"[^>]*></script>', trocar_js, html)

    # Registro do service worker não funciona em file:// e joga erro no console.
    html = html.replace("navigator.serviceWorker.register", "void 0 && navigator.serviceWorker.register")

    return html, faltando


def abrir_details(html, texto_do_summary):
    """Deixa aberto o <details> cujo <summary> começa com este texto.

    Por que um script injetado, e não um `open=` escrito no HTML: a primeira
    versão fazia isso com expressão regular e marcava o `<details>` errado — o
    primeiro do documento, que é uma opção de refeição, e que o acordeão da
    página fechava logo em seguida. Casar pelo texto do <summary> depois que a
    página terminou de carregar acerta o alvo e sobrevive ao JavaScript dela.

    As repetições no `setTimeout` existem porque alguns scripts da página
    mexem nos `<details>` durante a inicialização; abrir de novo depois é mais
    barato do que descobrir a ordem exata de cada um.
    """
    injecao = """
<script>
/* injetado por scripts/exportar_telas.py — só para a captura de tela */
(function () {
  var ALVO = %s;
  function abrir() {
    var achou = 0;
    document.querySelectorAll('details').forEach(function (d) {
      var s = d.querySelector('summary');
      if (s && s.textContent.trim().indexOf(ALVO) === 0) { d.open = true; achou++; }
    });
    document.documentElement.dataset.detailsAbertos = achou;
  }
  if (document.readyState === 'complete') abrir();
  else window.addEventListener('load', abrir);
  setTimeout(abrir, 200);
  setTimeout(abrir, 600);
})();
</script>
""" % (json.dumps(texto_do_summary),)

    if "</body>" in html:
        return html.replace("</body>", injecao + "</body>", 1), 1
    return html + injecao, 1


def exportar():
    Usuario = get_user_model()
    try:
        usuario = Usuario.objects.get(email=EMAIL_DEMO)
    except Usuario.DoesNotExist:
        sys.exit(
            "Usuário de demonstração '{}' não existe.\n"
            "Rode os seeds ou troque EMAIL_DEMO no topo deste arquivo.".format(EMAIL_DEMO)
        )

    cliente = Client()
    # `force_login` entra sem senha: este script não precisa saber a senha de
    # ninguém, e nada é gravado no banco.
    cliente.force_login(usuario)

    os.makedirs(SAIDA, exist_ok=True)
    resultados = []

    for tela in TELAS:
        resposta = cliente.get(tela["url"], follow=True)
        destino_final = resposta.redirect_chain[-1][0] if resposta.redirect_chain else tela["url"]

        if resposta.status_code != 200:
            resultados.append((tela["nome"], "ERRO {}".format(resposta.status_code), destino_final, 0))
            continue

        html = resposta.content.decode("utf-8", errors="replace")
        html, faltando = embutir(html)

        aviso_details = ""
        if tela.get("abrir_details"):
            html, n = abrir_details(html, tela["abrir_details"])
            if not n:
                aviso_details = " (nao achei o <details> de '{}')".format(tela["abrir_details"])

        caminho = os.path.join(SAIDA, tela["nome"] + ".html")
        with io.open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write(html)

        situacao = "ok" + aviso_details
        if faltando:
            situacao += " · faltou: " + ", ".join(sorted(set(faltando)))
        resultados.append((tela["nome"], situacao, destino_final, len(html)))

    largura = max(len(r[0]) for r in resultados)
    print("Telas exportadas em .ui_snapshots/html/\n")
    for nome, situacao, destino, tamanho in resultados:
        print("  {:<{w}}  {:>6}  {}".format(
            nome, "{:.0f} KB".format(tamanho / 1024) if tamanho else "—",
            situacao, w=largura))
        if destino not in ("/", "") and not destino.endswith(
                next((t["url"] for t in TELAS if t["nome"] == nome), "")):
            print("  {:<{w}}  {:>6}  redirecionou para {}".format("", "", destino, w=largura))


if __name__ == "__main__":
    exportar()
