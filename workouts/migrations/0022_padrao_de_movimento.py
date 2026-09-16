"""`Exercise.padrao`: o padrão de movimento, preenchido para quem já existe.

Aditiva. A coluna entra com `default=""`, o `RunPython` escreve o padrão
dos 36 exercícios pelo NOME (a mesma identidade que a aposentadoria usa —
nunca posição), e só então as duas `CheckConstraint` entram: nenhum
exercício sem padrão, nenhum sem equipamento. Linha que não esteja no mapa
— um banco com exercício cadastrado à mão — derruba a migration em vez de
passar em branco, porque a constraint recusaria em seguida e a mensagem
seria pior.
"""
from django.db import migrations, models

PADRAO_POR_NOME = {
    'Supino reto com barra': 'pressao_de_peito',
    'Flexão de braço': 'pressao_de_peito',
    'Supino inclinado com halteres': 'pressao_de_peito',
    'Crucifixo na máquina (voador)': 'crucifixo',
    'Puxada frente na polia': 'puxada_vertical',
    'Barra fixa assistida': 'puxada_vertical',
    'Remada baixa na polia': 'remada_horizontal',
    'Remada unilateral com halter': 'remada_horizontal',
    'Remada curvada com barra': 'remada_horizontal',
    'Desenvolvimento com halteres': 'pressao_vertical',
    'Elevação lateral com halteres': 'elevacao',
    'Elevação frontal com halteres': 'elevacao',
    'Crucifixo inverso na máquina': 'deltoide_posterior',
    'Agachamento livre': 'agachamento',
    'Leg press 45°': 'agachamento',
    'Afundo com halteres': 'agachamento',
    'Cadeira extensora': 'extensao_de_joelho',
    'Stiff com barra': 'extensao_de_quadril',
    'Elevação pélvica': 'extensao_de_quadril',
    'Mesa flexora': 'flexao_de_joelho',
    'Cadeira flexora': 'flexao_de_joelho',
    'Panturrilha em pé': 'flexao_plantar',
    'Panturrilha sentado': 'flexao_plantar',
    'Rosca direta com barra': 'rosca',
    'Rosca alternada com halteres': 'rosca',
    'Rosca martelo': 'rosca',
    'Tríceps na polia com corda': 'extensao_de_cotovelo',
    'Tríceps testa com barra': 'extensao_de_cotovelo',
    'Mergulho no banco': 'pressao_fechada',
    'Prancha abdominal': 'anti_extensao',
    'Abdominal supra no solo': 'flexao_de_tronco',
    'Elevação de pernas': 'flexao_de_quadril',
    'Encolhimento com halteres': 'elevacao_escapular',
    'Remada alta com barra': 'remada_alta',
    'Rosca de punho com barra': 'flexao_de_punho',
    'Rosca inversa com barra': 'extensao_de_punho',
}


def preencher(apps, schema_editor):
    Exercise = apps.get_model("workouts", "Exercise")
    sem_padrao = []
    for exercicio in Exercise.objects.all():
        padrao = PADRAO_POR_NOME.get(exercicio.name)
        if padrao is None:
            # A linha LEGADA `Remada curvada` (sem "com barra") existe em
            # bancos anteriores à `0017`, aposentada: recebe o padrão da
            # sucessora, porque é o mesmo movimento.
            if exercicio.name == "Remada curvada":
                padrao = "remada_horizontal"
            else:
                sem_padrao.append(exercicio.name)
                continue
        Exercise.objects.filter(pk=exercicio.pk).update(padrao=padrao)
    if sem_padrao:
        raise RuntimeError(
            "Exercício sem padrão no mapa desta migration: %s. Acrescente-o "
            "a PADRAO_POR_NOME antes de migrar." % ", ".join(sem_padrao)
        )


def esvaziar(apps, schema_editor):
    apps.get_model("workouts", "Exercise").objects.update(padrao="")


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0021_opcoes_por_letra"),
    ]

    operations = [
        migrations.AddField(
            model_name="exercise",
            name="padrao",
            field=models.CharField(
                choices=[
                    ("pressao_de_peito", "pressão de peito"),
                    ("crucifixo", "crucifixo"),
                    ("puxada_vertical", "puxada vertical"),
                    ("remada_horizontal", "remada horizontal"),
                    ("pressao_vertical", "pressão vertical"),
                    ("elevacao", "elevação de ombro"),
                    ("deltoide_posterior", "deltoide posterior"),
                    ("agachamento", "agachamento"),
                    ("extensao_de_joelho", "extensão de joelho"),
                    ("extensao_de_quadril", "extensão de quadril"),
                    ("flexao_de_joelho", "flexão de joelho"),
                    ("flexao_plantar", "flexão plantar"),
                    ("rosca", "rosca"),
                    ("extensao_de_cotovelo", "extensão de cotovelo"),
                    ("pressao_fechada", "pressão fechada"),
                    ("anti_extensao", "anti-extensão"),
                    ("flexao_de_tronco", "flexão de tronco"),
                    ("flexao_de_quadril", "flexão de quadril"),
                    ("elevacao_escapular", "elevação escapular"),
                    ("remada_alta", "remada alta"),
                    ("flexao_de_punho", "flexão de punho"),
                    ("extensao_de_punho", "extensão de punho"),
                ],
                default="",
                max_length=24,
                verbose_name="padrão de movimento",
            ),
        ),
        migrations.RunPython(preencher, esvaziar),
        migrations.AddConstraint(
            model_name="exercise",
            constraint=models.CheckConstraint(
                condition=models.Q(("padrao", ""), _negated=True), name="padrao_nao_vazio",
            ),
        ),
        migrations.AddConstraint(
            model_name="exercise",
            constraint=models.CheckConstraint(
                condition=models.Q(("equipment", ""), _negated=True), name="equipment_nao_vazio",
            ),
        ),
    ]
