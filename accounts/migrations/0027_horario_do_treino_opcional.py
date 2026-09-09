"""O horário do treino passa a ser opcional.

NÃO-DESTRUTIVA: `AlterField` para nulo preserva todos os horários gravados.
Ninguém perde o que informou, e o campo continua aceitando horário — ele só
deixou de ser exigido.

SOBRE A VOLTA. Reverter esta migration devolve `NOT NULL`, e isso falha se
alguma linha tiver nulo — que é exatamente o que passa a acontecer depois que
alguém concluir o passo 3 sem horário. É o comportamento correto para um
`AlterField` de nulabilidade, e está dito aqui para ninguém descobrir no meio
de um rollback: para voltar, preencha os nulos primeiro com uma decisão
explícita de produto. Este arquivo não escolhe um horário por ninguém.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0026_duracao_do_treino_em_faixa'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trainingday',
            name='start_time',
            field=models.TimeField(blank=True, null=True, verbose_name='horário de início'),
        ),
    ]
