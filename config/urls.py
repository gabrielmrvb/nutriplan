from allauth.urls import build_provider_urlpatterns
from django.contrib import admin
from django.urls import include, path

from push import views as push_views

from .health import HealthView

# As rotas do allauth entram PELA METADE, e a metade que fica de fora é a
# interface.
#
# `include("allauth.urls")` traria `allauth.account.urls` junto: outra tela de
# entrar, outra de criar conta, outra de trocar senha. Seriam duas interfaces
# de autenticação no mesmo app, e é a mesma armadilha que o `demo/middleware`
# documenta sobre não ter uma segunda cópia das telas — a segunda nasce igual e
# diverge na primeira correção.
#
# Então montamos só o que é motor:
#
#   `build_provider_urlpatterns()`  as rotas do provedor, que é o fluxo OAuth
#   `allauth.socialaccount.urls`    cancelamento, erro e conexões
#
# `AppLoginView` e `SignupView` continuam sendo a única porta de entrada.
# As auxiliares vão para `social/`, e não para a raiz de `conta/`.
#
# `allauth.socialaccount.urls` registra `socialaccount_connections` no caminho
# VAZIO. Montado direto sob `conta/`, ele tomava `/conta/` — que era 404 — e
# passava a renderizar a tela "contas conectadas" da biblioteca. Sob `/demo/`
# ela respondia 200 para a persona.
#
# Ela continua registrada, e de propósito: o allauth reverte esses nomes por
# dentro, e removê-los trocaria uma tela indesejada por um `NoReverseMatch` em
# algum caminho de erro. Sob um prefixo próprio, ela sai de `/conta/` e ganha
# um lugar só dela para o demo recusar.
ROTAS_SOCIAIS = build_provider_urlpatterns() + [
    path("social/", include("allauth.socialaccount.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # O service worker precisa vir da raiz: um arquivo servido de /static/ só
    # teria escopo sobre /static/ e não controlaria as páginas do app.
    path("sw.js", push_views.ServiceWorkerView.as_view(), name="service_worker"),
    path("manifest.webmanifest", push_views.ManifestView.as_view(), name="manifest"),
    path("offline/", push_views.OfflineView.as_view(), name="offline"),
    # Fica antes das rotas do app porque é o que a plataforma consulta para
    # decidir se o deploy subiu de pé.
    path("saude/", HealthView.as_view(), name="health"),
    # O modo demo NÃO tem entrada aqui. Ele monta a aplicação inteira sob
    # `/demo/` dentro de `demo.middleware`, que roda antes do resolvedor — e
    # serve as suas duas telas próprias (capa e "sobre") chamando as views
    # direto. Uma entrada aqui as deixaria fora do prefixo de script, e a capa
    # voltaria a oferecer "Entrar" e "Criar conta".
    path("conta/", include("accounts.urls")),
    # Sob `conta/` também, para o endereço do callback ficar junto do resto da
    # autenticação. O caminho real que sai daqui é
    # `/conta/google/login/callback/` — é ELE que precisa ser cadastrado no
    # Google Cloud, e ele é derivado desta linha, não escolhido.
    path("conta/", include(ROTAS_SOCIAIS)),
    path("push/", include("push.urls")),
    path("treino/", include("workouts.urls")),
    path("suplementos/", include("supplements.urls")),
    path("", include("plans.urls")),
]
