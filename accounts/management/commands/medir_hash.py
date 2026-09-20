# -*- coding: utf-8 -*-
"""`manage.py medir_hash` — quanto custa UMA senha em cada hasher configurado,
nesta máquina. Só leitura; não toca no banco. PROTÓTIPO (auditoria 20/09/2026)."""
import time

from django.contrib.auth.hashers import get_hashers
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mede o tempo de um hash de senha por hasher configurado."

    def handle(self, *args, **options):
        for hasher in get_hashers():
            nome = hasher.algorithm
            t0 = time.perf_counter()
            try:
                # `encode` no PRÓPRIO hasher: `make_password(hasher=nome)` pega o
                # primeiro com aquele `algorithm`, e os dois PBKDF2 têm o mesmo.
                hasher.encode("medir-hash-nutriplan", hasher.salt())
            except Exception as erro:  # noqa: BLE001
                self.stdout.write("%-18s indisponível (%s)" % (nome, erro))
                continue
            dt = time.perf_counter() - t0
            extra = " (%s iterações)" % getattr(hasher, "iterations", "") if getattr(hasher, "iterations", None) else ""
            self.stdout.write("%-18s %-40s %.3f s%s" % (nome, type(hasher).__name__, dt, extra))
        self.stdout.write("O primeiro da lista é o que grava senha nova; os outros só conferem as antigas.")
