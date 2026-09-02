"""Reconcilia os grupos administrativos com o que `accounts/papeis.py` declara.

Existe por uma lacuna que só apareceu quando alguém foi conferir em produção.
`PAPEIS` é a declaração de quem pode o quê, mas quem escreve isso no banco é
`sincronizar_papeis()` — e a única coisa que a chamava era `promover_admin`,
que saiu do build depois de cumprir o bootstrap. Resultado: tirar `add_user` da
declaração não tirava `add_user` de ninguém. O código dizia uma coisa e o
grupo em produção continuava com a permissão da última vez que alguém promoveu
um administrador.

Rodar isto em todo deploy é o que transforma `PAPEIS` de documentação em
configuração. É seguro repetir: `sincronizar_papeis()` usa `set()`, então o
resultado de rodar duas vezes é igual ao de rodar uma — e permissão retirada
da declaração é retirada de quem já estava no grupo.
"""
from django.core.management.base import BaseCommand

from accounts.papeis import sincronizar_papeis


class Command(BaseCommand):
    help = "Ajusta os grupos administrativos ao que o código declara."

    def handle(self, *args, **options):
        resumo = sincronizar_papeis()
        for papel, quantas in sorted(resumo.items()):
            self.stdout.write(f"{papel}: {quantas} permissões")
