from allauth.urls import build_provider_urlpatterns
from django.contrib import admin

from . import admin_entrada, admin_seguranca
from django.templatetags.static import static as static_url
from django.urls import include, path
from django.views.generic.base import RedirectView

from push import views as push_views

from . import legal
from .health import HealthView, VivoView

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

# Roda no import de urls.py, que acontece DEPOIS do autodiscover do admin —
# `accounts` vem antes de `allauth` em INSTALLED_APPS, então tirar as telas de
# dentro de `accounts/admin.py` não encontraria nada registrado ainda.
admin_seguranca.esconder_segredos_de_terceiros()

urlpatterns = [
    # ANTES de `admin.site.urls`, e a ordem é a integração inteira.
    #
    # `reverse("admin:login")` devolve `/admin/login/`, que é o mesmo caminho
    # declarado aqui — e a resolução de URL usa a PRIMEIRA correspondência.
    # Então o redirecionamento que o próprio Admin faz para quem não está
    # autenticado cai nesta view, sem middleware e sem tocar no AdminSite.
    #
    # O motivo: o primeiro operador administrativo entra por Google e não tem
    # senha utilizável. Ver `config/admin_entrada.py`.
    # O painel de negócio, com chave própria. Vem antes do admin por
    # coerência com o resto do bloco, e não por precedência: os prefixos não
    # colidem.
    path("gestao/", include("gestao.urls")),
    path("admin/login/", admin_entrada.entrada_do_admin),
    path("admin/", admin.site.urls),
    # O service worker precisa vir da raiz: um arquivo servido de /static/ só
    # teria escopo sobre /static/ e não controlaria as páginas do app.
    # O navegador pede `/favicon.ico` na RAIZ, sozinho, sem olhar o `<link>`.
    #
    # O arquivo existe e é servido em `/static/icons/favicon.ico`; a raiz
    # respondia 404 em toda visita, local e em produção — conferido nos dois.
    # Um redirecionamento permanente resolve sem inventar rota de arquivo:
    # quem pergunta uma vez aprende o caminho e não pergunta de novo.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static_url("icons/favicon.ico"), permanent=True),
        name="favicon",
    ),
    path("sw.js", push_views.ServiceWorkerView.as_view(), name="service_worker"),
    path("manifest.webmanifest", push_views.ManifestView.as_view(), name="manifest"),
    path("offline/", push_views.OfflineView.as_view(), name="offline"),
    # Fica antes das rotas do app porque é o que a plataforma consulta para
    # decidir se o deploy subiu de pé.
    path("saude/", HealthView.as_view(), name="health"),
    # Liveness, sem banco: responde se o PROCESSO esta de pe. Ver
    # `config/health.py` para por que as duas perguntas sao separadas.
    path("saude/vivo/", VivoView.as_view(), name="liveness"),

    # Páginas legais. Públicas de propósito: quem está decidindo se cria conta
    # é justamente quem precisa ler o que fazemos com os dados dele, e exigir
    # login para isso inverteria a ordem da decisão.
    #
    # `TemplateView` direto e sem app novo: são duas páginas de texto, sem
    # model, sem formulário e sem estado. Um app inteiro para isso seria
    # estrutura sem conteúdo.
    path("privacidade/", legal.Privacidade.as_view(), name="privacidade"),
    path("termos/", legal.Termos.as_view(), name="termos"),
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
    path("conquistas/", include("achievements.urls")),
    path("", include("plans.urls")),
]
