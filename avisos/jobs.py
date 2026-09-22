# -*- coding: utf-8 -*-
"""Os dois e-mails que o RELÓGIO manda: inatividade e resumo da semana.

Nenhum relógio próprio: `push.tarefas.rodar()` chama `rodar(now)` no fim de
cada rodada que não está pausada (UptimeRobot a cada 5 min; o Neon dorme
entre rodadas). Cada job responde três perguntas com UMA consulta para a
lista e uma por e-mail que sai:

- quem: conta ativa, onboarding feito, ficha ativa (sem ficha não há treino
  a cobrar nem semana a resumir), preferência ligada (linha ausente = ligada);
- quando: a partir de `hora_email` da pessoa, no dia certo (o resumo, na
  segunda);
- de novo?: nunca — a referência do `EmailEnviado` fecha a porta.
"""
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Max, Q, Sum
from django.utils import timezone

from accounts.models import ONBOARDING_DONE, User, WeightEntry
from plans.models import HydrationLog
from workouts.models import ExerciseLog

from .models import Preferencia, TipoDeEmail
from .brevo import sincronizar_se_vencido
from .services import TLD_QUE_NAO_ENTREGA, enviar

#: Dias sem série para o e-mail de inatividade sair.
DIAS_SEM_TREINO = 5

#: Teto de e-mails por rodada, por tipo. A rodada volta em 5 minutos, então
#: o teto não atrasa ninguém de verdade — ele impede a RAJADA: a primeira
#: rodada de produção (21/09/2026) mandou dezenas de uma vez, e um dia com
#: 46,6 % de hard bounce é o que suspende conta no Brevo. Uma data de
#: ativação errada num ambiente novo também esbarra aqui.
TETO_POR_RODADA = 20


def inatividade_desde():
    """`settings.NUTRIPLAN_AVISOS_INATIVIDADE_DESDE` como data; ilegível ou
    vazia vale HOJE (nada de antes conta), nunca "tudo"."""
    texto = getattr(settings, "NUTRIPLAN_AVISOS_INATIVIDADE_DESDE", "") or ""
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return timezone.localdate()



def _candidatos(campo_ligado):
    """Quem pode receber: ativo, onboarding feito, ficha ativa, com a
    preferência ligada — ou sem linha, que vale ligado. A hora do dia é
    conferida em Python (`_hora_passou`): a lista é pequena e a linha ausente
    tem hora padrão, o que o SQL não expressa sem um COALESCE por dialeto."""
    return (
        User.objects.filter(
            is_active=True,
            profile__onboarding_step__gte=ONBOARDING_DONE,
            training_plans__is_active=True,
        )
        # `.invalid` nem entra na lista (o demo tem ficha ativa e onboarding
        # feito); `enviar()` é a segunda trava, para os três tipos.
        .exclude(email__iendswith=TLD_QUE_NAO_ENTREGA)
        .filter(
            Q(preferencia_de_aviso__isnull=True)
            | Q(**{f"preferencia_de_aviso__{campo_ligado}": True})
        )
        .distinct()
    )


def _hora_passou(user, now):
    """Sem linha de preferência vale a hora padrão (08:00)."""
    pref = getattr(user, "preferencia_de_aviso", None)
    hora = pref.hora_email if pref is not None else Preferencia._meta.get_field("hora_email").default
    return now.time() >= hora


def rodar_inatividade(now=None):
    """Um e-mail por PAUSA: a referência é a data da última série (ou do
    cadastro, para quem nunca treinou). Cinco dias depois dela, sai; no dia
    seguinte a chave é a mesma e nada sai; treinou de novo, a chave muda.

    Duas guardas de PRIMEIRA RODADA: a pausa tem de ter COMEÇADO a partir de
    `inatividade_desde()` — quem parou antes de o aviso existir não é
    cobrado por um aviso que não existia —, e no máximo `TETO_POR_RODADA`
    saem por rodada (o resto sai nas próximas, de 5 em 5 min)."""
    now = now or timezone.localtime()
    hoje = now.date()
    desde = inatividade_desde()
    enviados = pulados = falhados = adiados = 0
    usuarios = (
        _candidatos("email_inatividade")
        .select_related("preferencia_de_aviso")
        .annotate(ultima_serie=Max("exercise_logs__date"))
    )
    for user in usuarios:
        if not _hora_passou(user, now):
            continue
        base = user.ultima_serie or timezone.localtime(user.date_joined).date()
        if base < desde:
            continue
        dias = (hoje - base).days
        if dias < DIAS_SEM_TREINO:
            continue
        if enviados >= TETO_POR_RODADA:
            adiados += 1
            continue
        referencia = ("nunca-" if user.ultima_serie is None else "") + base.isoformat()
        resultado = enviar(
            user, TipoDeEmail.INATIVIDADE, referencia,
            {"dias": dias, "ultima": user.ultima_serie, "nunca": user.ultima_serie is None},
            descadastro_de="inatividade",
        )
        if resultado == "enviado":
            enviados += 1
        elif resultado == "pulado":
            pulados += 1
        else:
            falhados += 1
    return {"enviados": enviados, "pulados": pulados, "falhados": falhados, "adiados": adiados}


def semana_anterior(hoje):
    """`(segunda, domingo, "AAAA-Www")` da semana ISO que acabou ontem."""
    segunda = hoje - timedelta(days=hoje.weekday() + 7)
    domingo = segunda + timedelta(days=6)
    ano, semana, _ = segunda.isocalendar()
    return segunda, domingo, f"{ano}-W{semana:02d}"


def resumo_de(user, segunda, domingo):
    logs = ExerciseLog.objects.filter(user=user, date__range=(segunda, domingo))
    treinos = logs.values("date").distinct().count()
    series = logs.count()
    agua = HydrationLog.objects.filter(user=user, date__range=(segunda, domingo)).aggregate(total=Sum("ml"))["total"] or 0
    peso = WeightEntry.objects.filter(user=user, date__lte=domingo).order_by("-date", "-pk").first()
    anterior = None
    if peso is not None:
        anterior = (
            WeightEntry.objects.filter(user=user, date__lt=segunda).order_by("-date", "-pk").first()
        )
    delta = None
    if peso is not None and anterior is not None:
        delta = peso.weight_kg - anterior.weight_kg
    return {
        "treinos": treinos, "series": series, "agua_ml": agua,
        "agua_fmt": _milhar(agua),
        "agua_media_fmt": _milhar(round(agua / 7) if agua else 0),
        "peso": peso.weight_kg if peso else None,
        "peso_fmt": _decimal(peso.weight_kg) if peso else "",
        "peso_delta": delta,
        "peso_delta_fmt": ("+" if delta >= 0 else "") + _decimal(delta) if delta is not None else "",
        "segunda": segunda, "domingo": domingo,
        "periodo": f"{segunda:%d/%m} a {domingo:%d/%m}",
    }


def _milhar(n):
    """`3500` → `"3.500"`: o app é pt-BR e o e-mail não passa pelo
    `intcomma` da tela."""
    return f"{int(n):,}".replace(",", ".")


def _decimal(valor):
    """`Decimal("82.20")` → `"82,2"`, uma casa, vírgula."""
    return f"{valor:.1f}".replace(".", ",")


def rodar_resumo_semanal(now=None):
    """Na segunda-feira, a partir da hora da pessoa, o resumo de segunda a
    domingo da semana que acabou. Semana vazia também sai (quem tem ficha
    ativa recebe o zero como convite, não como silêncio)."""
    now = now or timezone.localtime()
    hoje = now.date()
    if hoje.weekday() != 0:
        return {"enviados": 0, "pulados": 0, "falhados": 0, "dia": "não é segunda"}
    segunda, domingo, referencia = semana_anterior(hoje)
    enviados = pulados = falhados = adiados = 0
    usuarios = _candidatos("email_resumo_semanal").select_related("preferencia_de_aviso")
    for user in usuarios:
        if not _hora_passou(user, now):
            continue
        if enviados >= TETO_POR_RODADA:
            adiados += 1
            continue
        dados = resumo_de(user, segunda, domingo)
        resultado = enviar(user, TipoDeEmail.RESUMO_SEMANAL, referencia, dados, descadastro_de="resumo")
        if resultado == "enviado":
            enviados += 1
        elif resultado == "pulado":
            pulados += 1
        else:
            falhados += 1
    return {"enviados": enviados, "pulados": pulados, "falhados": falhados, "adiados": adiados, "semana": referencia}


def rodar(now=None):
    now = now or timezone.localtime()
    # A cópia do Brevo (bloqueados e abertos) antes de decidir quem recebe —
    # a cada 12 h por processo; sem chave, nada muda.
    brevo = sincronizar_se_vencido(now)
    return {
        "brevo": brevo,
        "inatividade": rodar_inatividade(now),
        "resumo_semanal": rodar_resumo_semanal(now),
    }
