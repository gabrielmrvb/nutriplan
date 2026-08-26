"""
Configuracao do projeto NutriPlan.

Toda configuracao sensivel ou que muda entre ambientes vem do arquivo .env
(veja .env.example). Nada de senha hardcoded aqui.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-inseguro-troque-em-producao")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps do projeto
    "accounts",
    "catalog",
    "plans",
    "workouts",
    # Removido: sobrevive um deploy só para o `migrate` encontrar a migração
    # que derruba as tabelas do módulo. Sai daqui e do disco no commit
    # seguinte — um app apagado nunca roda migração nenhuma, e o schema
    # ficaria órfão em produção para sempre.
    "coaching",
    "push",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "push.context_processors.push",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/nutriplan",
    )
}

# Usuario customizado desde o inicio: trocar isso depois da primeira
# migration e um dos poucos caminhos realmente dolorosos no Django.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "plans:today"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
def staticfiles_backend(debug: bool) -> str:
    """Qual storage de estáticos usar.

    É função, e não um `if` solto, por causa de uma armadilha que já mordeu
    duas vezes: isto é decidido no MOMENTO DA IMPORTAÇÃO do settings. Quem
    troca `DEBUG` depois — um perfil que importa este módulo, o runner de
    testes — não desfaz a escolha, e passa a acreditar numa configuração que
    não é a que está valendo. Como função, a regra pode ser conferida
    diretamente, com o valor de `debug` que se quiser.

    O storage com manifesto exige `collectstatic` rodado antes; em
    desenvolvimento e nos testes isso quebraria todo `{% static %}`.
    """
    if debug:
        return "django.contrib.staticfiles.storage.StaticFilesStorage"
    return "whitenoise.storage.CompressedManifestStaticFilesStorage"


STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": staticfiles_backend(DEBUG)},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Web Push (usados a partir da etapa 5)
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_ADMIN_EMAIL = env("VAPID_ADMIN_EMAIL", default="admin@example.com")

# O padrão do Django é "same-origin", que remove o cabeçalho Referer em toda
# requisição para fora do site. O player do YouTube usa esse cabeçalho para
# decidir se aquele domínio pode embutir o vídeo — sem ele, o iframe da aba de
# treino respondia "Erro 153: erro de configuração do player".
#
# "strict-origin-when-cross-origin" (o padrão dos navegadores hoje) entrega
# apenas a ORIGEM para destinos externos: o YouTube fica sabendo que o pedido
# veio do NutriPlan e não descobre em qual página, o que num app que sabe peso
# e objetivo de quem usa é exatamente a linha que interessa preservar.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

#: Origens confiáveis para POST vindo de HTTPS. Sem isto o Django devolve 403
#: em qualquer formulário do site publicado, porque ele compara a origem do
#: pedido com esta lista antes de aceitar o token de CSRF.
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- Domínio dado pela plataforma de hospedagem ---
#
# Render e Railway sorteiam o domínio no primeiro deploy e o publicam numa
# variável de ambiente. Lê-la aqui evita o passo manual de copiar o endereço
# para ALLOWED_HOSTS depois que o site já subiu — que é onde todo mundo trava
# na primeira vez, com um 400 sem explicação na tela.
PLATFORM_HOST = env("RENDER_EXTERNAL_HOSTNAME", default="") or env(
    "RAILWAY_PUBLIC_DOMAIN", default=""
)
if PLATFORM_HOST:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, PLATFORM_HOST]
    CSRF_TRUSTED_ORIGINS = [f"https://{PLATFORM_HOST}", *CSRF_TRUSTED_ORIGINS]

if not DEBUG:
    # A plataforma termina o TLS e conversa HTTP com o processo do Django. Sem
    # este cabeçalho o `SECURE_SSL_REDIRECT` abaixo enxerga "http", redireciona
    # para https, recebe o mesmo pedido de novo e o navegador desiste por
    # excesso de redirecionamentos. Já custou uma tarde de depuração num túnel
    # que não enviava o cabeçalho; aqui Render e Railway enviam.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

#: O `check --deploy` cobra `SECURE_HSTS_PRELOAD`, e a resposta aqui é não de
#: propósito. Entrar na lista de preload dos navegadores é uma decisão
#: praticamente irreversível — o domínio passa a ser HTTPS-only em todo
#: navegador do mundo, e sair da lista leva meses. Num subdomínio emprestado
#: (`*.onrender.com`) isso nem sequer é possível de forma isolada. O dia em que
#: o app tiver domínio próprio e estiver estável, aí sim vale ligar.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --- Web Push (VAPID) ---
# Sem chave configurada o app continua funcionando: a tela simplesmente não
# oferece notificação, em vez de quebrar. É o que permite rodar em dev, em CI
# e no primeiro deploy sem ter gerado chave nenhuma ainda.
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_ADMIN_EMAIL = env("VAPID_ADMIN_EMAIL", default="")

#: Nome curto e completo do PWA, usados no manifest.
PWA_NAME = "NutriPlan"
PWA_SHORT_NAME = "NutriPlan"
PWA_THEME_COLOR = "#090c0b"
PWA_BACKGROUND_COLOR = "#090c0b"
