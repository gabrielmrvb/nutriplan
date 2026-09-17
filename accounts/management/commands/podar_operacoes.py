# -*- coding: utf-8 -*-
"""Apaga as `SyncedOperation` vencidas — roda a cada deploy (`scripts/build.sh`).

A tabela cresce a cada marcação offline (água, suplemento, série), num banco
gratuito com limite de tamanho, e nunca foi podada: `SyncedOperation.podar`
existia desde a fila offline e ninguém o chamava (T2.4, 17/09/2026). A
validade (`VALIDADE_DIAS`, 30) fica bem acima dos 7 dias que um item da
fila ainda pode reenviar — a poda nunca apaga um `op_id` que um reenvio
traria de volta, senão "+500 ml" reenviado somaria de novo.
"""
from django.core.management.base import BaseCommand

from accounts.models import SyncedOperation


class Command(BaseCommand):
    help = "Apaga as operações sincronizadas mais velhas que SyncedOperation.VALIDADE_DIAS."

    def handle(self, *args, **options):
        removidas = SyncedOperation.podar()
        self.stdout.write(
            "%d operação(ões) sincronizada(s) com mais de %d dias removida(s)"
            % (removidas, SyncedOperation.VALIDADE_DIAS)
        )
