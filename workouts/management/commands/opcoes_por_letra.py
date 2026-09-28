"""Quantas opções cada letra de ficha nova recebe com o catálogo ATIVO — o relatório do gate.

    python manage.py opcoes_por_letra

Rode antes e depois de mudar o catálogo ou o motor: desde 27/09/2026 o
deploy só sobe se NENHUMA letra de ficha nova sair com duas opções
(`workouts/opcoes_em_producao.py`).
"""
from django.core.management.base import BaseCommand

from workouts.opcoes_em_producao import letras_a_mais, letras_com_opcoes, opcoes_por_letra


class Command(BaseCommand):
    help = "Tabela split × letra → opções da ficha nova, com o catálogo ativo; nenhuma pode ter duas."

    def handle(self, *args, **options):
        por_letra = opcoes_por_letra()
        self.stdout.write("%-7s %-5s %s" % ("split", "letra", "opções"))
        for (split, letra), n in sorted(por_letra.items()):
            self.stdout.write("%-7s %-5s %d" % (split, letra, n))
        self.stdout.write("letras com 2 opções: %d (tem de ser 0)" % len(letras_com_opcoes(por_letra)))
        a_mais = letras_a_mais(por_letra)
        if a_mais:
            self.stdout.write(self.style.ERROR(
                "SEGUNDA OPÇÃO: " + ", ".join("%s %s" % p for p in a_mais) + " — este estado não pode subir."
            ))
