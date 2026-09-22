"""O que o template base precisa saber e não vem da view.

A chave VAPID é PÚBLICA — vai para o navegador de propósito, é ela que
identifica o servidor na hora de assinar. A privada nunca sai do .env.

As URLs versionadas de CSS e JS entram aqui porque o `base.html` é o único
lugar que as usa, e passá-las por todas as views daria trabalho para repetir
a mesma linha em cada uma.
"""
import os

from django.conf import settings

from .assets import asset


def push(request):
    return {
        "vapid_public_key": settings.VAPID_PUBLIC_KEY,
        "app_css_url": asset("css/app.css"),
        "app_js_url": asset("js/pwa.js"),
        # Só a casca nativa carrega (login/push/saúde do aparelho); no
        # navegador o arquivo sai na primeira linha, mas nem é pedido.
        "nativo_js_url": asset("js/nativo.js"),
        "fila_js_url": asset("js/fila.js"),
        "card_js_url": asset("js/card.js"),
        "corrida_js_url": asset("js/corrida.js"),
        "conquista_js_url": asset("js/conquista.js"),
        "analytics_js_url": asset("js/analytics.js"),
        # A versão do app no cliente é o commit do deploy que renderizou a
        # página — assim o evento sabe de que versão do produto ele nasceu.
        "analytics_commit": os.environ.get("RENDER_GIT_COMMIT", "")[:7],
        # As cores da moldura do navegador, para o `<meta name="theme-color">`
        # não guardar uma segunda cópia do valor. Duas cópias é como uma delas
        # fica para trás — e ficou, por uma troca de paleta inteira.
        "PWA_THEME_COLOR": settings.PWA_THEME_COLOR,
        "PWA_LIGHT_COLOR": settings.PWA_LIGHT_COLOR,
    }
