# -*- coding: utf-8 -*-
"""O equipamento deixa de nascer respondido.

Só o DEFAULT do campo muda: nenhuma linha é tocada, e quem já tem
"completa" gravado continua com ela — aquela era a verdade de quem tinha
ficha antes de a pergunta existir. O que o default decidia errado era pela
pessoa que responde AGORA: a etapa 2 abria com "academia completa" marcada,
e passar batido virava uma declaração que ninguém fez.

Vazio é "ainda não respondeu", como em `experiencia`. `services.
equipamento_de` traduz para "completa" na hora de montar a ficha, e o
Perfil mostra o padrão dizendo que é padrão.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0039_musculacao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='equipamento',
            field=models.CharField(blank=True, choices=[('completa', 'Academia completa — barra, halteres, máquinas e polias'), ('basica', 'Academia básica — halteres, máquinas e polias, sem barra livre'), ('casa_halteres', 'Em casa, com halteres'), ('peso_corporal', 'Só o peso do corpo')], default='', max_length=15, verbose_name='equipamento disponível'),
        ),
    ]
