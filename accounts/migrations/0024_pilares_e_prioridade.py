# -*- coding: utf-8 -*-
"""Os cinco pilares entram no perfil — e ninguém tem preferência inventada.

Duas coisas acontecem aqui, e elas são de naturezas diferentes.

**Os campos novos nascem vazios, e é deliberado.** Cinco booleanos em `False` e
`prioridade` em `""` são o estado "ainda não declarou". A tentação era olhar
para o banco e preencher — quem tem ficha vira "treino", quem registrou água
vira "hidratação". Isso seria fabricar intenção humana a partir de uso, e uso
não é consentimento nem declaração. O produto passa a perguntar; quem ainda não
respondeu continua sem resposta, e a experiência dessa pessoa não muda.

**O passo do onboarding sobe de 6 para 7, e esse SIM precisa de RunPython.**
O passo novo fez `ONBOARDING_DONE` ir de 6 para 7. Sem tocar em nada, todo
mundo que já tinha terminado — `onboarding_step == 6` — passaria a ser
"incompleto" e seria empurrado de volta para dentro do wizard, para responder
uma pergunta que ninguém combinou de fazer no meio do uso.

É exatamente o que a migration `0013_onboarding_ganhou_um_passo` já resolveu uma
vez, e a solução é a mesma: quem já estava em `ONBOARDING_DONE` sobe junto.

O que este `RunPython` NÃO faz: ele não escreve interesse nem prioridade. Ele só
preserva o estado de "terminei" de quem terminou. A pergunta nova chega para
essa pessoa por convite, não por bloqueio.
"""

from django.db import migrations, models


#: O valor de `ONBOARDING_DONE` ANTES desta migration.
#:
#: Escrito à mão, e não importado: importar leria o número de HOJE, e no dia em
#: que um sétimo passo entrar esta migration passaria a mexer em quem ela não
#: deveria alcançar. Migration que lê constante viva reescreve o passado.
DONE_ANTES = 6
DONE_DEPOIS = 7


def preservar_quem_ja_terminou(apps, schema_editor):
    """Quem estava em 6 vai para 7. Ninguém entra no wizard de novo.

    `>=` e não `==`: um perfil em 7 já está certo, e um em 8 nunca deveria
    existir — se existir, deixá-lo para trás seria pior que normalizá-lo.
    """
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(onboarding_step__gte=DONE_ANTES).update(
        onboarding_step=DONE_DEPOIS
    )


def desfazer(apps, schema_editor):
    """A volta é simétrica, e perde uma coisa — dita aqui em vez de descoberta.

    Quem responder o passo novo e depois voltar por esta migration cai em 6, ou
    seja, "terminou o onboarding antigo". A resposta de interesses some junto
    com as colunas, porque a reversão do `AddField` as apaga. Não há como
    guardá-la: o lugar dela deixa de existir.
    """
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(onboarding_step__gte=DONE_DEPOIS).update(
        onboarding_step=DONE_ANTES
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0023_tentativa_de_entrada'),
        ('catalog', '0005_food_is_premium'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='interesse_corrida',
            field=models.BooleanField(default=False, verbose_name='interesse em corrida'),
        ),
        migrations.AddField(
            model_name='profile',
            name='interesse_dieta',
            field=models.BooleanField(default=False, verbose_name='interesse em alimentação'),
        ),
        migrations.AddField(
            model_name='profile',
            name='interesse_hidratacao',
            field=models.BooleanField(default=False, verbose_name='interesse em hidratação'),
        ),
        migrations.AddField(
            model_name='profile',
            name='interesse_progresso',
            field=models.BooleanField(default=False, verbose_name='interesse em evolução'),
        ),
        migrations.AddField(
            model_name='profile',
            name='interesse_treino',
            field=models.BooleanField(default=False, verbose_name='interesse em musculação'),
        ),
        migrations.AddField(
            model_name='profile',
            name='prioridade',
            field=models.CharField(blank=True, choices=[('dieta', 'Alimentação'), ('treino', 'Musculação'), ('corrida', 'Corrida'), ('hidratacao', 'Hidratação'), ('progresso', 'Evolução')], default='', max_length=20, verbose_name='prioridade principal'),
        ),
        migrations.AddConstraint(
            model_name='profile',
            constraint=models.CheckConstraint(condition=models.Q(('prioridade', ''), models.Q(('interesse_dieta', True), ('prioridade', 'dieta')), models.Q(('interesse_treino', True), ('prioridade', 'treino')), models.Q(('interesse_corrida', True), ('prioridade', 'corrida')), models.Q(('interesse_hidratacao', True), ('prioridade', 'hidratacao')), models.Q(('interesse_progresso', True), ('prioridade', 'progresso')), _connector='OR'), name='prioridade_pertence_aos_interesses'),
        ),
        migrations.RunPython(preservar_quem_ja_terminou, desfazer),
    ]
