"""Dá acesso administrativo a uma conta que JÁ existe.

Produção subiu com `staff = 0`: `/admin/` existe, está publicado, e não há
ninguém que consiga entrar. Este comando fecha isso — e o desenho dele é todo
sobre o que ele se RECUSA a fazer.

Não aceita senha, em nenhuma forma. Um comando que recebe senha por argumento a
deixa no histórico do shell e na lista de processos; um que a gera e imprime a
deixa no log do terminal. Aqui a conta já tem a senha que a pessoa escolheu, e
o comando não toca nela.

Não cria conta. `--email` que não existe é erro, não convite: criar em silêncio
transformaria um typo numa conta administrativa fantasma com e-mail que ninguém
controla.

Não marca `is_superuser`. Superuser ignora o sistema de permissões inteiro, e a
diferença entre "pode administrar o NutriPlan" e "pode tudo que o Django
permite" é a única coisa que separa um erro de operação de um incidente.

Aceita `--email` ou `--id`, e o segundo existe por uma restrição concreta: o
repositório do NutriPlan é PÚBLICO e o Render gratuito não tem shell, então o
identificador que o build usa viaja no código.

A primeira versão disto usava o SHA-256 do e-mail, com o argumento de que o
hash "permite confirmar um palpite, não descobrir o endereço". O argumento é
falso: o espaço de e-mails é pequeno e enumerável, e testar milhões de
candidatos contra um digest É descobrir. Hash de e-mail não é anonimização.

A chave primária não tem esse problema — é um inteiro sequencial que não
carrega nada sobre a pessoa.

`--bootstrap` marca a promoção inicial e é ONE-SHOT: uma vez registrada em
`RegistroAdministrativo`, ela não acontece de novo. A trava é a trilha e não o
estado da conta, e a diferença importa — se alguém for deliberadamente removido
do grupo amanhã, um redeploy antigo não pode devolver o acesso por conta
própria.

Uso:

    python manage.py promover_admin --email pessoa@exemplo.com
    python manage.py promover_admin --id 42 --bootstrap
    python manage.py promover_admin --email pessoa@exemplo.com --papel suporte
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AcaoAdministrativa, RegistroAdministrativo
from accounts.papeis import ADMINISTRADORES, SUPORTE, sincronizar_papeis

PAPEL_POR_APELIDO = {"admin": ADMINISTRADORES, "suporte": SUPORTE}


class Command(BaseCommand):
    help = "Dá acesso administrativo a uma conta existente, sem tocar na senha."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument(
            "--id",
            type=int,
            dest="pk",
            help="Chave primária da conta. Não é PII, e é o que o build usa.",
        )
        parser.add_argument(
            "--bootstrap",
            action="store_true",
            help="Promoção inicial, uma vez só. Recusa se a trilha já registrou.",
        )
        parser.add_argument(
            "--papel",
            choices=sorted(PAPEL_POR_APELIDO),
            default="admin",
        )

    @transaction.atomic
    def handle(self, *args, **opcoes):
        User = get_user_model()
        papel = PAPEL_POR_APELIDO[opcoes["papel"]]
        email = (opcoes["email"] or "").strip().lower()
        pk = opcoes["pk"]

        if bool(email) == bool(pk):
            raise CommandError("Informe --email OU --id, e apenas um deles.")

        # `select_for_update` segura a linha até o fim da transação. Dois
        # deploys simultâneos são improváveis, mas o custo de proteger é uma
        # cláusula e o custo de não proteger é a trilha ganhar dois eventos
        # PRIMEIRO_ADMIN para a mesma pessoa — que é justamente o registro que
        # uma investigação futura vai usar para saber quando tudo começou.
        base = User.objects.select_for_update()
        if email:
            usuario = base.filter(email__iexact=email).first()
            procurado = email
        else:
            usuario = base.filter(pk=pk).first()
            procurado = f"a conta #{pk}"

        if usuario is None:
            raise CommandError(
                f"Não existe conta correspondente a {procurado}. "
                "Este comando promove quem já se cadastrou; ele não cria conta."
            )

        if opcoes["bootstrap"] and RegistroAdministrativo.objects.filter(
            alvo=usuario, acao=AcaoAdministrativa.PRIMEIRO_ADMIN
        ).exists():
            # A trava é a TRILHA, não o estado da conta.
            #
            # "Se não é staff, promove" seria mais simples e estaria errado: no
            # dia em que alguém for deliberadamente removido do grupo, o próximo
            # deploy devolveria o acesso sozinho — desfazendo uma decisão
            # administrativa sem ninguém pedir e sem nada acusar.
            self.stdout.write(
                f"A conta #{usuario.pk} já passou pelo bootstrap inicial. "
                "Nada a fazer."
            )
            return

        # Os grupos são sincronizados ANTES de usar: o papel precisa refletir os
        # models de hoje, não os de quando alguém rodou isto pela primeira vez.
        sincronizar_papeis()
        grupo = Group.objects.get(name=papel)

        # "Primeiro" vem da TRILHA, não do estado.
        #
        # Era `not User.objects.filter(is_staff=True).exists()`, e a constraint
        # de unicidade expôs o defeito: depois de uma revogação não existe mais
        # nenhum staff, então a promoção seguinte seria gravada como PRIMEIRO
        # de novo — dois "começos" para a mesma história, e o banco recusando a
        # segunda com um erro que não explica nada.
        primeiro = not RegistroAdministrativo.objects.filter(
            acao=AcaoAdministrativa.PRIMEIRO_ADMIN
        ).exists()
        antes = {
            "is_staff": usuario.is_staff,
            "grupos": sorted(usuario.groups.values_list("name", flat=True)),
        }

        usuario.is_staff = True
        usuario.save(update_fields=["is_staff"])
        usuario.groups.add(grupo)

        depois = {
            "is_staff": True,
            "grupos": sorted(usuario.groups.values_list("name", flat=True)),
        }

        if antes == depois:
            # Idempotente: rodar de novo não inventa um registro de auditoria
            # dizendo que algo mudou. Trilha com evento falso é pior que trilha
            # curta — ela faz alguém procurar uma causa que não existiu.
            self.stdout.write(f"A conta #{usuario.pk} já tinha acesso de {papel}.")
            return

        RegistroAdministrativo.objects.create(
            ator=None,
            acao=(
                AcaoAdministrativa.PRIMEIRO_ADMIN
                if primeiro
                else AcaoAdministrativa.PROMOVEU_STAFF
            ),
            alvo=usuario,
            alvo_email=usuario.email,
            detalhe={
                "papel": papel,
                "origem": "comando promover_admin",
                "identificado_por": "email" if email else "id",
                "antes": antes,
                "depois": depois,
                "is_superuser": usuario.is_superuser,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"A conta #{usuario.pk} agora é staff e pertence a {papel}. "
                f"is_superuser continua {usuario.is_superuser}."
            )
        )
