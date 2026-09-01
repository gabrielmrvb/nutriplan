"""Exportar meus dados — a portabilidade que a LGPD garante (Art. 18, V).

O que este módulo NÃO faz, e cada ausência é deliberada:

  Não exporta o hash da senha. Ele é dado sobre a conta, não dado da pessoa, e
  colocá-lo num arquivo que ela vai guardar no Downloads transforma um segredo
  bem guardado em algo que anda pelo mundo.

  Não exporta sessão, token de OAuth nem a tabela de limite de recuperação. A
  primeira é credencial viva; a segunda o app nem guarda; a terceira só tem
  HMAC, e exportar um HMAC não informa nada a ninguém.

  Não exporta o catálogo. Alimento e exercício são conteúdo do app, iguais para
  todo mundo — mandar 103 alimentos junto faria o arquivo parecer maior e ser
  menos útil. O que sai é o que a pessoa produziu: o histórico dela.

A montagem é toda a partir de `user`, e nunca de um identificador vindo do
pedido. Não existe parâmetro para escolher de quem é a exportação, então não
existe superfície para exportar a conta de outra pessoa — a proteção é a
ausência do parâmetro, e não uma verificação que alguém pode esquecer.
"""
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
from django.views import View


def _data(valor):
    return valor.isoformat() if valor is not None else None


def _numero(valor):
    """Decimal vira string, e não float.

    Float de ponto flutuante transforma 82,40 em 82.40000000000001 no arquivo
    que a pessoa abre. String preserva exatamente o que está no banco.
    """
    return str(valor) if valor is not None else None


def reunir_dados(user) -> dict:
    """Tudo o que o NutriPlan guarda sobre uma pessoa, menos o que é segredo."""
    from accounts.models import Profile, TrainingDay, WeightEntry
    from achievements.models import UserAchievement
    from plans.models import HydrationLog, MealLog, NutritionPlan
    from workouts.models import ExerciseLog, TrainingPlan

    perfil = Profile.objects.filter(user=user).first()

    dados = {
        "exportado_em": timezone.now().isoformat(),
        "aviso": (
            "Este arquivo contém dados de saúde. Guarde-o com o mesmo cuidado "
            "que você teria com um exame."
        ),
        "conta": {
            "nome": user.first_name,
            "email": user.email,
            "criada_em": _data(user.date_joined),
            "ultimo_acesso": _data(user.last_login),
            "entra_com_google": user.socialaccount_set.exists()
            if hasattr(user, "socialaccount_set")
            else False,
        },
    }

    if perfil is not None:
        dados["perfil"] = {
            "sexo": perfil.get_sex_display(),
            "data_de_nascimento": _data(perfil.birth_date),
            "altura_cm": perfil.height_cm,
            "nivel_de_atividade": perfil.get_activity_level_display(),
            "objetivo": perfil.get_goal_display(),
            "restricoes_alimentares": sorted(
                perfil.dietary_tags.values_list("name", flat=True)
            ),
            "acorda": _data(perfil.wake_time),
            "dorme": _data(perfil.sleep_time),
            "fuso_horario": perfil.timezone,
            "ajuste_de_calorias": perfil.kcal_adjustment,
        }

    dados["pesagens"] = [
        {"data": _data(p.date), "peso_kg": _numero(p.weight_kg)}
        for p in WeightEntry.objects.filter(user=user).order_by("date")
    ]

    dados["dias_de_treino"] = [
        {
            "dia_da_semana": d.get_weekday_display(),
            "horario": _data(d.start_time),
            "duracao_min": d.duration_min,
        }
        for d in TrainingDay.objects.filter(user=user).order_by("weekday")
    ]

    dados["metas_calculadas"] = [
        {
            "criada_em": _data(p.created_at),
            "ativa": p.is_active,
            "peso_kg": _numero(p.weight_kg),
            "calorias": p.target_kcal,
            "proteina_g": p.protein_g,
            "carboidrato_g": p.carb_g,
            "gordura_g": p.fat_g,
        }
        for p in NutritionPlan.objects.filter(user=user).order_by("created_at")
    ]

    dados["refeicoes_marcadas"] = [
        {
            "data": _data(m.date),
            "refeicao": m.slot_name,
            "situacao": m.get_status_display(),
            "o_que_comeu": m.recipe_name or None,
            "calorias": _numero(m.kcal),
            "proteina_g": _numero(m.protein_g),
            "observacao": m.notes or None,
        }
        for m in MealLog.objects.filter(user=user).order_by("date", "scheduled_time")
    ]

    dados["agua"] = [
        {"data": _data(h.date), "ml": h.ml}
        for h in HydrationLog.objects.filter(user=user).order_by("date")
    ]

    dados["treinos"] = [
        {
            "criado_em": _data(t.created_at),
            "ativo": t.is_active,
            "divisao": t.get_split_display(),
            "dias_por_semana": t.days_per_week,
        }
        for t in TrainingPlan.objects.filter(user=user).order_by("created_at")
    ]

    dados["series_registradas"] = [
        {
            "data": _data(e.date),
            "exercicio": e.exercise.name,
            "serie": e.set_number,
            "carga_kg": _numero(e.weight_kg),
            "repeticoes": e.reps,
        }
        for e in ExerciseLog.objects.filter(user=user)
        .select_related("exercise")
        .order_by("date", "exercise__name", "set_number")
    ]

    dados["conquistas"] = [
        {"conquista": c.titulo, "data": _data(c.unlocked_at)}
        for c in UserAchievement.objects.filter(user=user).order_by("unlocked_at")
    ]

    return dados


class ExportarDadosView(LoginRequiredMixin, View):
    """Baixa um JSON com o histórico de quem está logado.

    Só POST. Uma exportação é um evento — ela gera um arquivo com dado de saúde
    e sai do controle do app no instante em que o navegador o salva. Com GET,
    bastaria um link numa página de terceiro para o navegador de quem está
    logado disparar o download sozinho.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        dados = reunir_dados(request.user)
        corpo = json.dumps(dados, ensure_ascii=False, indent=2)

        resposta = HttpResponse(corpo, content_type="application/json; charset=utf-8")
        nome = "nutriplan-%s.json" % timezone.localdate().isoformat()
        resposta["Content-Disposition"] = 'attachment; filename="%s"' % nome
        # O arquivo tem dado de saúde: nenhum intermediário deve guardá-lo.
        resposta["Cache-Control"] = "no-store"
        return resposta
