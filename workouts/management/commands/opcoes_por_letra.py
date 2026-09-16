"""Quantas opções cada letra recebe com o catálogo ATIVO — o relatório do gate.

    python manage.py opcoes_por_letra

Rode antes e depois de mudar o catálogo ou o motor: o deploy só sobe se o
número de letras com duas opções não cair (`workouts/opcoes_em_producao.py`).
"""
from django.core.management.base import BaseCommand

from workouts.opcoes_em_producao import (
    LETRAS_COM_OPCOES_EM_PRODUCAO,
    letras_com_opcoes,
    opcoes_por_letra,
)


class Command(BaseCommand):
    help = "Tabela split × letra → opções, com o catálogo ativo; e o total contra o de produção."

    def handle(self, *args, **options):
        por_letra = opcoes_por_letra()
        com_duas = letras_com_opcoes(por_letra)
        self.stdout.write("%-7s %-5s %s" % ("split", "letra", "opções"))
        for (split, letra), n in sorted(por_letra.items()):
            self.stdout.write("%-7s %-5s %d" % (split, letra, n))
        self.stdout.write(
            "letras com 2 opções: %d (produção: %d)" % (len(com_duas), LETRAS_COM_OPCOES_EM_PRODUCAO)
        )
        if len(com_duas) < LETRAS_COM_OPCOES_EM_PRODUCAO:
            self.stdout.write(self.style.ERROR("ABAIXO de produção: este estado não pode subir."))
