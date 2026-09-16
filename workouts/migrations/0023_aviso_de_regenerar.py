# Plano ativo antigo NÃO é remontado por mudança de catálogo (17/09/2026): a
# Home pergunta uma vez ("Seu treino pode ficar mais completo — regenerar?")
# e a dispensa fica no plano. E o plano passa a ser retrato também das
# ENTRADAS — catálogo, nível, faixa de duração — para distinguir "a pessoa
# mudou a própria entrada" (remonta) de "o catálogo mudou embaixo dela"
# (pergunta). Os planos que já existem ficam com os três em branco:
# desconhecido, que não invalida nada.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workouts', '0022_padrao_de_movimento'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingplan',
            name='aviso_dispensado_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='aviso de regenerar dispensado em'),
        ),
        migrations.AddField(
            model_name='trainingplan',
            name='catalogo',
            field=models.CharField(blank=True, default='', max_length=64, verbose_name='catálogo de origem'),
        ),
        migrations.AddField(
            model_name='trainingplan',
            name='nivel',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='nível de origem'),
        ),
        migrations.AddField(
            model_name='trainingplan',
            name='duracao',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='faixa de duração de origem'),
        ),
    ]
