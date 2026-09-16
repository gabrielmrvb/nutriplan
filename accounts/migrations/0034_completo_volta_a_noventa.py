# Completo volta a 90 minutos (17/09/2026): com o catálogo de 63 ativos e as
# faixas do TREINO.md a sessão passa de 65, e o rótulo diz o teto de verdade.
# Só os rótulos mudam — nenhum valor gravado é tocado.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0033_rotulos_de_duracao_honestos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='duracao_treino',
            field=models.CharField(choices=[('rapido', 'Rápido — até 30 minutos'), ('padrao', 'Padrão — até 60 minutos'), ('completo', 'Completo — a ficha inteira, até 90 minutos'), ('livre', 'Sem limite rígido — o mesmo que Completo, até 90 minutos')], default='padrao', max_length=10, verbose_name='duração do treino'),
        ),
    ]
