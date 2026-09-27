# -*- coding: utf-8 -*-
"""A corrida passa a existir para o cálculo.

Três colunas, todas com default e nenhuma escrita: conta que já existe
continua em branco, que é "não perguntado" — e em branco não muda meta
nenhuma. Quem responder "sim" e disser quantas vezes por semana entra em
`calculations.activity_factor` pela mesma porta da musculação: SESSÕES por
semana.

Sem backfill de propósito: inferir "ela corre" de `TracoDaCorrida` seria
transformar USO em intenção declarada, que é o erro que a `0024` evitou com
a prioridade de pilar.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0040_equipamento_sem_padrao'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='corrida',
            field=models.CharField(blank=True, choices=[('sim', 'Sim, corro (ou pedalo, ou nado)'), ('nao', 'Não')], default='', max_length=3, verbose_name='corre, pedala ou nada'),
        ),
        migrations.AddField(
            model_name='profile',
            name='corrida_dias',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='corridas por semana'),
        ),
        migrations.AddField(
            model_name='profile',
            name='corrida_minutos',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='minutos por corrida'),
        ),
    ]
