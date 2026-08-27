"""Os três valores antigos da preferência de divisão viram a contagem nova.

`focused` / `upper_lower` / `full_body` existiram por um commit. Eram
vocabulário de quem já sabe a resposta, e a tela foi refeita para perguntar o
que se pergunta na academia: quantos grupos por dia.

Todos caem em `three`, e a escolha do destino é deliberada: `three` produz o
ABC, que é o que o motor escolhia sozinho antes de a pergunta existir. Ninguém
acorda com uma ficha diferente por causa desta migração.

O que se perde: quem tivesse escolhido `upper_lower` ou `full_body` nesse
intervalo perde a escolha. As duas opções deixaram de existir na tela — não há
para onde mapeá-las que não seja inventar uma intenção que a pessoa não teve.
O caminho de volta devolve todo mundo para `focused`, pelo mesmo motivo: era o
padrão de lá.
"""
from django.db import migrations

DE_PARA = {"focused": "three", "upper_lower": "three", "full_body": "three"}


def para_contagem(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    for antigo, novo in DE_PARA.items():
        Profile.objects.filter(split_preference=antigo).update(split_preference=novo)


def voltar(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(split_preference__in=["one", "two", "three"]).update(
        split_preference="focused"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_preferencia_por_grupos"),
    ]

    operations = [
        migrations.RunPython(para_contagem, voltar),
    ]
