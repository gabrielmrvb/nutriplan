# O ciclo da divisão roda CONTÍNUO (17/09/2026): a semana seguinte continua
# de onde a anterior parou — A B C A B → C A B C A → B C A B C —, em vez de
# recomeçar em A toda segunda-feira. `inicio_do_ciclo` é o primeiro dia de
# treino do plano, a posição zero; a letra de qualquer data sai da posição
# dela na sequência de dias de treino. Os planos que já existem ficam com o
# campo em branco e continuam presos ao dia da semana, como sempre foram —
# a política da Fase 5: plano ativo não é remontado por mudança de regra, a
# Home pergunta.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workouts', '0023_aviso_de_regenerar'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingplan',
            name='inicio_do_ciclo',
            field=models.DateField(blank=True, null=True, verbose_name='início do ciclo'),
        ),
    ]
