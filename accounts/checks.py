"""Verificações de configuração que rodam antes de o servidor subir.

Existem por causa de um risco concreto, e não por completude: o backend de
e-mail tem um padrão SEGURO PARA DESENVOLVIMENTO — o console — e um padrão
seguro para desenvolvimento é um padrão perigoso para produção. Se alguém
apagar as variáveis do Render daqui a seis meses, o Django volta para o console
sem reclamar, e cada "esqueci minha senha" passa a escrever um link de
redefinição VÁLIDO no log da plataforma.

Nada avisaria. A tela continuaria dizendo "verifique seu e-mail", a pessoa
nunca receberia nada, e quem tivesse acesso ao log teria a chave da conta.

Registrada com `deploy=True`, então ela roda em `manage.py check --deploy` — que
`scripts/build.sh` passou a executar — e NÃO no `check` implícito de todo
comando. A distinção não é estética: o runner de teste do Django troca o
backend por `locmem` e roda com `DEBUG=False`, e uma verificação comum
derrubaria a suíte inteira acusando a configuração de teste de ser produção
mal configurada. Foi o que aconteceu na primeira versão desta função.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

#: Backends que NÃO entregam e-mail para uma pessoa de verdade.
#:
#: `console` e `file` escrevem o conteúdo em algum lugar legível — que é ótimo
#: no laptop e é vazamento em produção. `dummy` e `locmem` descartam, e o
#: silêncio é pior: ninguém descobre que a recuperação de senha parou.
BACKENDS_DE_MENTIRA = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
)

#: Cada campo que o SMTP precisa, com o nome da variável de ambiente que o
#: preenche — a mensagem de erro cita a variável, e não o atributo do Django,
#: porque quem lê está no painel do Render e não no settings.
CAMPOS_DE_SMTP = (
    ("EMAIL_HOST", "EMAIL_HOST"),
    ("EMAIL_HOST_USER", "EMAIL_HOST_USER"),
    ("EMAIL_HOST_PASSWORD", "EMAIL_HOST_PASSWORD"),
    ("DEFAULT_FROM_EMAIL", "DEFAULT_FROM_EMAIL"),
)


@register(Tags.security, deploy=True)
def email_de_producao_esta_configurado(app_configs, **kwargs):
    """Com `DEBUG=False`, exige backend real e credencial presente.

    Só roda fora de `DEBUG`: em desenvolvimento e nos testes o console
    continua sendo o certo, e é o que faz o link aparecer no terminal.

    A verificação NUNCA imprime o valor de nada — apenas o nome da variável que
    está faltando. Uma checagem de configuração que despeja a credencial no log
    para "ajudar a diagnosticar" cria o problema que veio evitar.
    """
    if settings.DEBUG:
        return []

    problemas = []
    backend = getattr(settings, "EMAIL_BACKEND", "")

    if backend in BACKENDS_DE_MENTIRA:
        problemas.append(
            Error(
                "Em produção o e-mail está no backend %r, que não entrega "
                "mensagem para ninguém." % backend.rsplit(".", 2)[-2],
                hint=(
                    "A recuperação de senha ficaria escrevendo links válidos no "
                    "log (console/file) ou descartando em silêncio (dummy/locmem). "
                    "Defina DJANGO_EMAIL_BACKEND="
                    "django.core.mail.backends.smtp.EmailBackend e as variáveis "
                    "de SMTP no ambiente."
                ),
                id="accounts.E001",
            )
        )
        return problemas

    faltando = [variavel for atributo, variavel in CAMPOS_DE_SMTP
                if not getattr(settings, atributo, "")]
    if faltando:
        problemas.append(
            Error(
                "Faltam variáveis de e-mail em produção: %s." % ", ".join(faltando),
                hint=(
                    "Sem elas o envio falha na hora em que alguém pedir "
                    "recuperação de senha. Preencha no painel do provedor de "
                    "hospedagem — nunca no código."
                ),
                id="accounts.E002",
            )
        )

    if not getattr(settings, "EMAIL_USE_TLS", False) and not getattr(
        settings, "EMAIL_USE_SSL", False
    ):
        problemas.append(
            Error(
                "O SMTP de produção está sem TLS.",
                hint=(
                    "A credencial SMTP e o corpo do e-mail — que carrega o link "
                    "de redefinição — trafegariam em texto claro. Defina "
                    "EMAIL_USE_TLS=True."
                ),
                id="accounts.E003",
            )
        )

    return problemas


#: O valor que `config/settings.py` usa quando a variável não existe. É
#: deliberadamente feio: um segredo padrão que PARECE segredo é pior do que um
#: que se denuncia sozinho na primeira leitura.
CHAVE_DE_DESENVOLVIMENTO = "dev-inseguro-troque-em-producao"

#: A régua do próprio Django (`SECRET_KEY_MIN_LENGTH`). Repetida aqui de
#: propósito: lá ela é constante privada de `django.core.checks.security.base`,
#: e importá-la amarraria este arquivo a um detalhe interno do framework.
TAMANHO_MINIMO_DA_CHAVE = 50


@register(Tags.security, deploy=True)
def chave_secreta_de_producao_e_forte(app_configs, **kwargs):
    """Impede o deploy quando a SECRET_KEY é fraca, e não só avisa.

    Mora em `accounts` porque o que essa chave assina é, em boa parte, coisa
    daqui: o token de redefinição de senha, a sessão e o CSRF. Quem tem a chave
    forja um link de "esqueci minha senha" para qualquer e-mail cadastrado —
    é a mesma falha que o resto deste arquivo existe para evitar, pela porta
    dos fundos.

    O Django já reclama disso sozinho, em `security.W009`. O problema é a
    letra: W de warning. `scripts/build.sh` roda `check --deploy` com
    `--fail-level ERROR`, então o aviso passava batido em todo deploy, e a
    produção do NutriPlan subiu meses com ele aceso sem que nada travasse.

    A causa era a plataforma, não descuido: `generateValue: true` no
    `render.yaml` gera 256 bits em base64, o que dá 44 caracteres — abaixo dos
    50 que o Django exige. O gerador do Render produz, sem avisar, uma chave
    que a régua do Django reprova.

    Nada aqui imprime a chave. As mensagens citam TAMANHO, nunca conteúdo: uma
    verificação que despeja o segredo no log do build para "ajudar a
    diagnosticar" cria o problema que veio evitar.
    """
    if settings.DEBUG:
        return []

    problemas = []
    chave = getattr(settings, "SECRET_KEY", "") or ""

    if not chave or chave == CHAVE_DE_DESENVOLVIMENTO:
        problemas.append(
            Error(
                "A SECRET_KEY de produção é o valor padrão de desenvolvimento.",
                hint=(
                    "Ela assina sessão, CSRF e o token de redefinição de senha: "
                    "com o padrão público, qualquer pessoa forja um link de "
                    "recuperação para qualquer conta. Defina DJANGO_SECRET_KEY "
                    "no painel, com pelo menos %d caracteres."
                    % TAMANHO_MINIMO_DA_CHAVE
                ),
                id="accounts.E004",
            )
        )
        return problemas

    if len(chave) < TAMANHO_MINIMO_DA_CHAVE:
        problemas.append(
            Error(
                "A SECRET_KEY de produção tem %d caracteres; o mínimo é %d."
                % (len(chave), TAMANHO_MINIMO_DA_CHAVE),
                hint=(
                    "É o que o Render entrega com `generateValue: true` — 256 "
                    "bits em base64 dão 44 caracteres. Gere uma chave própria "
                    "e guarde a antiga em DJANGO_SECRET_KEY_FALLBACKS durante a "
                    "troca, para não deslogar todo mundo."
                ),
                id="accounts.E005",
            )
        )

    for posicao, antiga in enumerate(getattr(settings, "SECRET_KEY_FALLBACKS", [])):
        if len(antiga or "") < TAMANHO_MINIMO_DA_CHAVE:
            problemas.append(
                Error(
                    "O fallback nº %d de SECRET_KEY tem %d caracteres; o mínimo "
                    "é %d." % (posicao + 1, len(antiga or ""),
                               TAMANHO_MINIMO_DA_CHAVE),
                    hint=(
                        "Fallback existe para a janela de troca de chave, e "
                        "vale só até as sessões antigas expirarem. Se a chave "
                        "velha era curta demais, tire-a da lista em vez de "
                        "carregá-la: ela continua assinando o que já foi "
                        "emitido."
                    ),
                    id="accounts.E006",
                )
            )

    return problemas
