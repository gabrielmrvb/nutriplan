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
