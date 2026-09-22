# -*- coding: utf-8 -*-
"""`manage.py sincronizar_brevo` — copia do Brevo quem bloqueou e quem abriu
(`avisos.brevo`). Roda no build (`scripts/build.sh`) e a cada 12 h dentro
da rodada de e-mails; sem `BREVO_API_KEY` diz isso e sai com 0 — o deploy
não pode cair por uma chave que ainda não foi gravada no painel."""
from django.core.management.base import BaseCommand

from avisos import brevo


class Command(BaseCommand):
    help = "Sincroniza e-mails bloqueados e abertos a partir do Brevo (só leitura na API)."

    def handle(self, *args, **options):
        resultado = brevo.sincronizar()
        self.stdout.write("brevo: %s" % ", ".join("%s=%s" % kv for kv in resultado.items()))
