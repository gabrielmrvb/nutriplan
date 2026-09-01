"""Separa "escolheu TRÊS" de "nunca respondeu nada".

`split_preference` nasce com `TRES`. A intenção estava certa — TRES é o ABC, o
que a frequência escolhia sozinha antes da pergunta existir — mas o efeito é que
o campo devolve uma RESPOSTA para todo mundo, inclusive para quem nunca viu a
tela. E ver a tela não é garantido: `preferencia_muda_a_divisao` não pergunta
nada até três dias de treino, então quem monta a ficha treinando três vezes
passa direto. Quando essa pessoa marca um quarto dia, o app lê TRES, entrega ABC
para quatro treinos e ninguém escolheu isso.

A correção NÃO é reescrever os TRES existentes. Não há como saber, olhando para
o banco hoje, quais vieram do padrão e quais alguém marcou de propósito — e
adivinhar erraria justamente contra quem respondeu.

Então entra um campo separado, `split_preference_confirmada`, que registra o
único fato que o banco realmente tem: esta pessoa passou pelo passo 4 e salvou.
Ele nasce False para todo mundo, inclusive para quem escolheu de verdade. Isso é
conservador na direção certa: o pior que acontece com quem já tinha respondido é
o app perguntar de novo quando a resposta voltar a importar. O contrário —
assumir uma escolha que ninguém fez — é o defeito que estamos fechando.

Nada muda de divisão por causa desta migração. `split_preference` continua com o
valor que está lá, e quem lê continua lendo o mesmo. O campo novo só passa a
existir para o app poder PERGUNTAR em vez de presumir.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_pedidoderecuperacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="split_preference_confirmada",
            field=models.BooleanField(
                default=False,
                verbose_name="divisão de treino confirmada pela pessoa",
            ),
        ),
    ]
