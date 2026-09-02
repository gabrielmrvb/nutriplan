"""
Configuracao do projeto NutriPlan.

Toda configuracao sensivel ou que muda entre ambientes vem do arquivo .env
(veja .env.example). Nada de senha hardcoded aqui.
"""
from pathlib import Path

from config import observabilidade

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-inseguro-troque-em-producao")

#: Chaves ANTIGAS que continuam validando o que ja foi assinado.
#:
#: Existe para a troca da `SECRET_KEY` nao derrubar todo mundo. O que ela
#: assina no NutriPlan: a sessao, o token de CSRF, o token de recuperacao de
#: senha, o `state` do OAuth do Google e o HMAC do contador de abuso em
#: `accounts/limites.py`. Trocar sem rede de seguranca desloga todos, invalida
#: os links de redefinicao que estao viajando por e-mail e derruba os logins do
#: Google no meio do caminho.
#:
#: Com a chave antiga aqui, o Django ACEITA o que ela assinou e ASSINA o novo
#: com a nova. A janela precisa cobrir o maior prazo em jogo, que hoje e o
#: `PASSWORD_RESET_TIMEOUT` de 3 horas — e, para nao deslogar ninguem, a idade
#: de sessao. Passada a janela, a variavel sai do ambiente e a chave antiga
#: deixa de valer.
#:
#: NOTA sobre o `check --deploy`: ele valida cada fallback com a MESMA regra da
#: chave principal (`security.W025`). A chave que o Render gera tem 44
#: caracteres — 256 bits em base64 —, entao ela dispara o aviso por
#: COMPRIMENTO enquanto estiver aqui. E esperado e temporario; o aviso some
#: junto com a variavel.
SECRET_KEY_FALLBACKS = env.list("DJANGO_SECRET_KEY_FALLBACKS", default=[])
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
    "supplements",
    "push",
    "demo",
    "achievements",
    "gestao",
    # Login com Google — o allauth como MOTOR, não como interface.
    #
    # `allauth.account` entra porque `allauth.socialaccount` depende dele: é
    # quem guarda `EmailAddress` e quem executa o login em si. O que NÃO entra
    # são as rotas dele — veja `config/urls.py`. As telas de entrar e criar
    # conta continuam sendo `AppLoginView` e `SignupView`.
    #
    # `django.contrib.sites` NÃO é necessário nesta versão: o allauth detecta
    # sozinho (`allauth.app_settings.SITES_ENABLED` lê `apps.is_installed`), e
    # sem ele as credenciais vêm de `SOCIALACCOUNT_PROVIDERS` em vez da tabela
    # `SocialApp`. É o que queremos: credencial em variável de ambiente, não em
    # linha de banco — o banco gratuito do Render é apagado por volta de
    # 23/09/2026, e credencial que mora nele some junto.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

MIDDLEWARE = [
    # PRIMEIRO de todos: o identificador precisa existir antes de qualquer
    # coisa poder falhar, senao o 500 que acontece dentro de outro middleware
    # sai sem marca — e e justamente esse que da trabalho para reconstruir.
    "config.observabilidade.MarcaDePedidoMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Comprime o HTML que o Django gera. O WhiteNoise comprime os ESTÁTICOS e
    # só eles — a página de treino saía com 622 KB crus, medidos, porque
    # renderiza a semana inteira com um ícone inline em cada linha de série.
    # Comprimida: 32 KB. Numa rede de academia essa é a diferença entre abrir e
    # desistir.
    #
    # DEPOIS do WhiteNoise, e não antes: o WhiteNoise precisa ficar colado no
    # middleware de segurança para interceptar estático cedo, e assim arquivo
    # estático nem chega aqui — ele já sai pré-comprimido por lá.
    #
    # Sobre o BREACH: o ataque explora comprimir um segredo estável ao lado de
    # conteúdo que o atacante controla. O token CSRF do Django é remascarado a
    # cada renderização justamente por isso, e nenhuma tela aqui reflete
    # entrada de terceiro junto de segredo.
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # DEPOIS da autenticação, porque precisa de `request.user`, e ANTES das
    # views, porque o caso anônimo tem que ser respondido antes do
    # `LoginRequiredMixin` transformá-lo num redirect que o cliente publicado
    # leria como sucesso. Ver `config/csrf.py`.
    "config.csrf.BarreiraDeReplayMiddleware",
    # DEPOIS da autenticação, porque ele SUBSTITUI `request.user` — antes dela,
    # o middleware de autenticação sobrescreveria a troca de volta pelo
    # visitante anônimo.
    "demo.middleware.DemoMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Exigido pelo allauth: `AccountConfig.ready()` levanta
    # `ImproperlyConfigured` sem ele, então não é opcional nem esquecível.
    #
    # DEPOIS do middleware do demo, e isso importa: o do demo recusa qualquer
    # caminho de OAuth sob `/demo/` antes que este veja o pedido.
    "allauth.account.middleware.AccountMiddleware",
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
                "accounts.context_processors.google_login",
                "accounts.context_processors.legal",
                "achievements.context_processors.conquistas_pendentes",
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

# O padrão do Django é abrir e fechar uma conexão POR PEDIDO. Contra um Postgres
# na mesma máquina isso é barato e some no ruído; contra um banco gerenciado do
# outro lado de TLS, cada pedido paga handshake antes de a primeira consulta
# sair. Numa tela que faz três consultas, o custo de conectar chega a pesar mais
# que as consultas.
#
# Um minuto, e não "para sempre": o serviço web do plano gratuito hiberna, e
# conexão pendurada em processo que vai morrer é conexão desperdiçada do lado do
# banco. Com `WEB_CONCURRENCY=2` isso são duas conexões vivas, longe de qualquer
# limite.
#
# `CONN_HEALTH_CHECKS` é o par obrigatório disto, e não um extra: conexão
# reaproveitada pode ter morrido do outro lado — o banco reiniciou, a rede caiu,
# ou (no caso de um Postgres que hiberna por inatividade) o servidor desligou
# sozinho. Sem a checagem, o primeiro pedido depois disso morre com
# `OperationalError` na cara de quem estava usando o app.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Usuario customizado desde o inicio: trocar isso depois da primeira
# migration e um dos poucos caminhos realmente dolorosos no Django.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# E-mail
# --------------------------------------------------------------------------
#
# Existe por causa da recuperação de senha: sem backend, `PasswordResetView`
# estoura ao tentar enviar, e o fluxo inteiro morre na primeira tela.
#
# O padrão é o CONSOLE, e isso é decisão, não descuido. Em desenvolvimento o
# link de redefinição aparece no terminal, que é o que se quer. Em produção,
# enquanto ninguém configurar um provedor de verdade, o console faz o e-mail
# aparecer NO LOG do Render — feio, e honesto: a alternativa seria o backend
# `smtp` sem credencial, que levanta exceção na cara de quem pediu a
# recuperação, ou o `dummy`, que descarta em silêncio e é o pior dos três,
# porque ninguém descobre que está quebrado.
#
# Para ligar e-mail real em produção, basta preencher no ambiente:
#
#   DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#   EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
#   DEFAULT_FROM_EMAIL
#
# Nenhuma credencial é inventada aqui: os padrões são vazios de propósito.
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = 10

#: O remetente. `nao-responda@` porque a caixa não é lida — e o dia em que for,
#: é uma variável de ambiente, não uma edição de código.
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="NutriPlan <nao-responda@nutriplan.app>"
)

#: Quanto tempo o link de redefinição vale, em segundos. Três horas.
#:
#: O padrão do Django é três DIAS. Link de senha que vive três dias numa caixa
#: de entrada é três dias de janela para quem tiver acesso a ela. Três horas
#: cobre com folga "pedi agora e vou ler o e-mail", que é o caso real.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 3

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "plans:today"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Login com Google
# ---------------------------------------------------------------------------
# O `ModelBackend` continua PRIMEIRO e continua sendo quem autentica e-mail e
# senha. O do allauth entra ao lado dele porque é o que sabe autenticar a
# partir de um `SocialAccount`. Nenhum comportamento do login tradicional muda.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

#: O NutriPlan não tem campo `username`, e o allauth precisa saber disso.
#:
#: Sem estas duas linhas, ERRAR A SENHA no login tradicional devolvia 500.
#:
#: O caminho: com senha certa o `ModelBackend` responde primeiro e nada mais
#: roda. Com senha errada ele devolve `None`, o Django cai no backend do
#: allauth, e `_authenticate_by_username` filtra por
#: `USER_MODEL_USERNAME_FIELD` — que vale "username" por padrão. Como
#: `USERNAME_FIELD = "email"` e o campo `username` foi removido do modelo, o
#: ORM levanta `FieldError`.
#:
#: `None` faz aquele método desistir logo na primeira guarda; `{"email"}` diz
#: qual é a chave de verdade. Um erro de digitação na senha é o caminho mais
#: percorrido de qualquer tela de login, e ele não pode ser um 500.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
#: O cadastro é o nosso `SignupForm`; isto só mantém o allauth coerente com o
#: modelo quando ele monta e-mail de conta social.
ACCOUNT_SIGNUP_FIELDS = ["email*"]

#: As credenciais. Sem elas o botão simplesmente não aparece e o app sobe
#: igual — um deploy sem variável configurada não pode derrubar o site.
# --------------------------------------------------------------------------
# Documentos legais
# --------------------------------------------------------------------------
#
# Política de Privacidade e Termos de Uso precisam identificar QUEM responde
# pelo tratamento dos dados. Esse dado não está no código porque não é do
# código: é do Gabriel, e inventá-lo seria publicar informação falsa num
# documento cujo propósito inteiro é ser confiável.
#
# Enquanto estiverem vazios, as duas páginas se declaram RASCUNHO e não são
# linkadas do cadastro nem do login. Elas continuam acessíveis por URL direta
# para revisão, e continuam testadas — o que não acontece é serem apresentadas
# como documento final do beta.
#
# Preenchidos, o aviso some e os links aparecem. Nenhum outro código muda.
LEGAL_RESPONSAVEL = env("LEGAL_RESPONSAVEL", default="")
LEGAL_CONTATO = env("LEGAL_CONTATO", default="")

#: Só é documento, e não rascunho, quando as duas coisas existem.
LEGAL_PUBLICADO = bool(LEGAL_RESPONSAVEL and LEGAL_CONTATO)

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")
GOOGLE_LOGIN_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# A política de vínculo mora em `accounts.adapters`, e é a decisão de produto
# desta feature. O que fica aqui são os interruptores que a sustentam.
SOCIALACCOUNT_ADAPTER = "accounts.adapters.NutriPlanSocialAccountAdapter"

#: Existe para uma coisa só: recusar conta desativada sem quebrar a página.
#:
#: O `respond_user_inactive` padrão faz `reverse("account_inactive")`, e essa
#: rota mora em `allauth.account.urls` — que este projeto não monta. Sem este
#: adapter, uma conta desativada COM Google já vinculado recebia 500 em vez de
#: uma recusa.
ACCOUNT_ADAPTER = "accounts.adapters.NutriPlanAccountAdapter"

#: NÃO entrar numa conta local só porque o e-mail bate.
#:
#: Este é o interruptor central da política. `False` é o padrão do allauth, e
#: está escrito aqui de propósito: um dia alguém vai considerar ligá-lo para
#: tirar a tela de confirmação de senha do caminho, e precisa encontrar o
#: motivo antes do interruptor. O motivo é que o NutriPlan não tem recuperação
#: de senha — controlar o e-mail não é, hoje, um fator de autenticação aqui, e
#: ligar isto criaria uma porta para a conta que não existia.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False

#: Sem tela intermediária de cadastro do allauth: quem chega com identidade
#: válida do Google já tem tudo o que a conta precisa (e-mail e nome). O que
#: falta é o onboarding, que é nosso.
SOCIALACCOUNT_AUTO_SIGNUP = True

#: O provedor já entrega o e-mail verificado; pedir verificação nossa por cima
#: seria mandar a pessoa confirmar o que o Google acabou de confirmar.
#:
#: A justificativa antiga era outra — "o projeto não tem EMAIL_BACKEND
#: configurado" — e deixou de valer quando a recuperação de senha entrou. A
#: decisão fica de pé pelo motivo que sempre foi o bom; o motivo que caducou
#: saiu daqui para não virar argumento zumbi na próxima leitura.
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "none"

#: Guardar `access_token` e `refresh_token` seria guardar credencial de acesso
#: à conta Google de alguém para nunca mais usar: o NutriPlan só precisa saber
#: QUEM é a pessoa, no instante do login.
SOCIALACCOUNT_STORE_TOKENS = False

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        # Credencial vinda de `settings`, e não da tabela `SocialApp`: o
        # allauth monta um `SocialApp` em memória a partir disto, sem tocar no
        # banco.
        "APP": {
            "client_id": GOOGLE_CLIENT_ID,
            "secret": GOOGLE_CLIENT_SECRET,
            "key": "",
        },
        # O mínimo para saber quem é a pessoa. Nada de Gmail, Drive, Calendar
        # ou contatos — e pedir a mais empurraria o app para a revisão de
        # escopos sensíveis do Google sem nenhuma contrapartida.
        "SCOPE": ["openid", "email", "profile"],
        "AUTH_PARAMS": {"access_type": "online"},
        # Exige a assinatura do `id_token`, que é o que transforma "o cliente
        # disse que é fulano" em "o Google assinou que é fulano".
        "OAUTH_PKCE_ENABLED": True,
    }
}

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
# Recusa por CSRF num replay da fila responde de forma preservável em vez
# de 403: o cliente publicado apaga o item em qualquer 4xx, e o token
# guardado nele fica velho depois de QUALQUER login — inclusive o da
# própria pessoa voltando. A view continua não executando.
CSRF_FAILURE_VIEW = "config.csrf.falha_de_csrf"

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

    #: Liga a leitura de `X-Forwarded-For` no limite de recuperação de senha.
    #:
    #: Só aqui, no bloco de produção, e nunca em desenvolvimento: fora de um
    #: proxy conhecido, ler o cabeçalho é confiar em quem não se conhece — quem
    #: manda o pedido escolheria o próprio identificador.
    #:
    #: O que o Render entrega, e o que ele NÃO entrega, está documentado em
    #: `accounts/limites.ip_do_pedido`. Em resumo: o cliente é o PRIMEIRO item
    #: e o cabeçalho continua falsificável, então o limite por origem é
    #: best-effort e quem protege a cota são os tetos globais.
    USA_PROXY_CONFIAVEL = True

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
# As duas precisam ser IDÊNTICAS ao `--bg` do tema escuro em app.css.
#
# Elas pintam o que o navegador desenha ANTES e EM VOLTA da página: a barra de
# status do Android, a tela de abertura do app instalado, a faixa acima do
# conteúdo no iPhone. Divergir do fundo real produz uma emenda visível de meio
# segundo toda vez que o app abre — e foi o que aconteceu: a paleta passou para
# #0d0f12 e estas duas ficaram no verde-preto antigo.
#
# Há teste comparando as duas com o token do CSS.
PWA_THEME_COLOR = "#0d0f12"
PWA_BACKGROUND_COLOR = "#0d0f12"

# O `--bg` do tema claro. Só o `<meta>` usa: o manifesto declara UMA cor, e o
# sistema operacional não troca a tela de abertura do app instalado conforme o
# tema do aparelho.
PWA_LIGHT_COLOR = "#f4f6f5"


# ==========================================================================
# Observabilidade
# ==========================================================================
#
# Ver `config/observabilidade.py` para o desenho e para o que NAO se registra.
# Em resumo: identificador por pedido, 5xx com traceback, e redacao do token de
# redefinicao — que viaja na URL e apareceria no log de acesso num 500.
LOGGING = observabilidade.configuracao(DEBUG)
