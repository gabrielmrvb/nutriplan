# -*- coding: utf-8 -*-
"""A API v1 saiu (decisão do dono, 20/09/2026), e com ela a credencial de
cliente que não é navegador. A tabela `accounts_tokendeapp` só era escrita
por `POST /api/v1/token/`; o backup `nutriplan-20260920-183736.dump`
(restaurado e verificado num PostgreSQL 18 local) guarda o que havia.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0035_equipamento"),
    ]

    operations = [
        migrations.DeleteModel(name="TokenDeApp"),
    ]
