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

A VARREDURA (28/09/2026 — gap medido no Gate 1 da missão LGPD)

`reunir_dados` tinha nove chaves escritas à mão, e o resto de tudo que o app
guarda com FK/O2O para o usuário ficava de fora sem ninguém decidir isso —
corrida, consentimento, gole de água, lista de compras, assinatura push, o
que a pessoa pediu de e-mail, o rastro de analytics dela. `EXPORTADOS` e
`NAO_EXPORTA` existem para que essa lista nunca mais fique desatualizada em
silêncio: `test_todo_model_com_fk_para_o_usuario_e_exportado_ou_justificado`
lê `get_user_model()._meta.related_objects` — a verdade do banco, não uma
lista escrita à mão — e reprova se um model novo não estiver em nenhum dos
dois. Os de sempre continuam com a seção escrita à mão (os testes antigos
leem essas chaves, e alguns merecem o nome resolvido — exercício, alimento —
que o helper genérico não traz); o resto passa por `_linhas`, um helper que
lê os campos escalares do model e pula relação e segredo.

A VARREDURA SÓ ENXERGA RELAÇÃO DIRETA COM O USUÁRIO (achado I3 da revisão,
28/09/2026). `TracoDaCorrida` (o percurso GPS) é O2O para `Corrida`, não
para `User` — `get_user_model()._meta.related_objects` não o vê, e o dado
de localização, o mais sensível que o app guarda depois de saúde, ficava
fora do arquivo em silêncio. Por isso `Corrida` SAIU do registro genérico e
virou seção à mão (como `trocas_de_exercicio`), com `select_related("traco")`
trazendo os pontos junto de cada corrida — o mesmo padrão de "resolver a
relação que o genérico descartaria".

Duas outras relações de segundo grau foram conferidas e ficam de fora, pela
MESMA razão que o catálogo fica de fora (acima): `plans.MealSlot` (filho de
`NutritionPlan`) é o horário e o ALVO calórico que o motor calcula — a
ESTRUTURA do cardápio, não o que a pessoa comeu (isso já está em
`refeicoes_marcadas`, via `MealLog`); `workouts.SessionExercise` (filho de
`TrainingSession`, filho de `TrainingPlan`) é a prescrição que o motor
montou — o que a pessoa FEZ de verdade já está em `series_registradas`, via
`ExerciseLog`. As duas são o cardápio/a ficha, geradas pelo motor a partir
das mesmas entradas que `metas_calculadas`/`treinos` já resumem; exportar a
estrutura inteira duplicaria o motor no arquivo sem acrescentar dado que a
pessoa produziu.
"""
import json
import re
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
from django.views import View

from config.observabilidade import redigir as _redigir_padroes_conhecidos


def _data(valor):
    return valor.isoformat() if valor is not None else None


def _numero(valor):
    """Decimal vira string, e não float.

    Float de ponto flutuante transforma 82,40 em 82.40000000000001 no arquivo
    que a pessoa abre. String preserva exatamente o que está no banco.
    """
    return str(valor) if valor is not None else None


def _valor_json(valor):
    """A mesma conversão de `_data`/`_numero`, para o helper genérico: data e
    hora viram ISO, `Decimal` vira string, o resto atravessa como está."""
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


#: A chave de descadastro de e-mail (`avisos.Preferencia.chave`) anda na
#: PRÓPRIA URL (`avisos/urls.py`: `sair/<str:chave>/`), e essa URL pode ter
#: sido gravada em `analytics.Event.route`/`referrer` — quem clica o link do
#: rodapé do e-mail com o navegador logado grava um evento comum, e
#: `static/js/analytics.js` manda `location.pathname` inteiro. `SEGREDOS`
#: filtra `chave` pelo NOME do campo; aqui o problema é outro — o valor de
#: um campo que não é segredo (`route`) carrega um que é. Achado I1 da
#: revisão, 28/09/2026.
_PADRAO_DESCADASTRO = re.compile(r"(/avisos/sair/)[^/?#]+")


def _sem_segredo_na_rota(texto):
    """Uma STRING de rota/URL, sem o que `config.observabilidade` já sabe
    redigir (token de senha, `?code=`/`?token=`...) e sem a chave de
    descadastro, que é específica deste app e não mora lá."""
    if not texto:
        return texto
    return _PADRAO_DESCADASTRO.sub(r"\1[REDIGIDO]", _redigir_padroes_conhecidos(texto))


def _sem_segredo(valor):
    """A mesma redação, RECURSIVA — para `analytics.Event.props`.

    `route`/`referrer` são colunas fixas; `props` é `JSONField` com forma
    livre por evento (a taxonomia declara os NOMES, não o formato). Round 2
    da revisão, 28/09/2026: `erro.js` leva `{"mensagem": ..., "rota":
    location.pathname}` — um erro de JavaScript na tela de descadastro
    grava a URL com a chave dentro de `props.rota`, e `mensagem` também pode
    carregar uma URL (a exceção do navegador costuma citar o arquivo/linha,
    às vezes a própria URL da página). Redigir só `rota` teria sido
    específico demais; aplicar a toda STRING dentro de `props` — em
    qualquer profundidade de dict/lista — não depende de saber o nome do
    campo de antemão."""
    if isinstance(valor, str):
        return _sem_segredo_na_rota(valor)
    if isinstance(valor, dict):
        return {k: _sem_segredo(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sem_segredo(v) for v in valor]
    return valor


#: Nomes de campo que NUNCA saem no arquivo, em model nenhum — credencial,
#: identificador técnico de reenvio ou chave de link. Os nomes são os REAIS
#: (lidos em `push/models.py`, `avisos/models.py` e `accounts/models.py`
#: antes de escrever esta lista), não um padrão genérico: `p256dh_key` e
#: `auth_key`, por exemplo, não `p256dh`/`auth`. `id` sai também — é
#: identificador interno de linha, sem valor de portabilidade, e nenhuma das
#: seções escritas à mão o inclui.
SEGREDOS = {
    "id",
    "password",
    "chave",  # avisos.Preferencia — a chave de descadastro sem login
    "endpoint",  # push.PushSubscription
    "p256dh_key",  # push.PushSubscription
    "auth_key",  # push.PushSubscription
    "token",  # push.DispositivoNativo — o token do FCM
    "op_id",  # workouts.Corrida — identificador da fila offline
}

#: Um NOME de campo que bate aqui e NÃO está em `SEGREDOS` reprova a
#: varredura de nomes (`accounts/test_exportacao_completa.py`,
#: `VarreduraDeNomesDeSegredoTests`) — a guarda contra o campo que alguém
#: acrescenta amanhã a um dos 15 models do registro genérico (um
#: `refresh_token`, `api_key`, `senha_hash`...) e que `SEGREDOS`, por ser uma
#: lista fechada de nomes de HOJE, não filtraria sozinha (achado I2 da
#: revisão, 28/09/2026).
PADRAO_NOME_DE_SEGREDO = re.compile(
    r"token|secret|segredo|senha|password|chave|key|endpoint|hash|op_id", re.I
)

#: Campo que BATE em `PADRAO_NOME_DE_SEGREDO` e não é segredo de verdade —
#: `{"model.Label": {"campo": "razão"}}`. Vazio hoje: nenhum dos 15 models
#: do registro genérico tem um campo assim fora de `SEGREDOS`. Existe para o
#: dia em que um bater por acidente (ex.: um campo chamado `chave_pix`) sem
#: precisar reabrir `SEGREDOS` para exceção.
CAMPO_NAO_E_SEGREDO = {}


def _linhas(model, user, ordenar_por=()):
    """Os campos escalares de `model` para quem tem `user=user`.

    Usado pelos models que não têm relação que valha a pena resolver, nem
    segredo além dos nomes já cobertos por `SEGREDOS`: filtra por `user`,
    tira relação (`is_relation`) e segredo, devolve o resto.
    """
    campos = [
        f.name
        for f in model._meta.concrete_fields
        if f.name not in SEGREDOS and f.name != "user" and not f.is_relation
    ]
    linhas = model.objects.filter(user=user).values(*campos)
    if ordenar_por:
        linhas = linhas.order_by(*ordenar_por)
    return [{k: _valor_json(v) for k, v in linha.items()} for linha in linhas]


def _registro_generico():
    """(label do model, chave no JSON, model, ordenação).

    Função e não uma tupla de módulo porque os imports moram AQUI DENTRO,
    como os de `reunir_dados` — a app registry pode não estar pronta ainda
    quando `accounts.exportacao` é importado (settings, checks). Isso não
    evita o custo: `EXPORTADOS`, logo abaixo, chama esta função na
    importação do módulo para derivar os labels, então os 15 models SÃO
    importados nesse momento de qualquer forma — só não import de `models.py`
    inteiro de cada app, e sim dos nomes usados aqui.

    `workouts.Corrida` NÃO está mais aqui (saiu em 28/09/2026, achado I3 da
    revisão): o traçado GPS (`TracoDaCorrida`) é filho DELA, não do usuário,
    e o helper genérico descarta relação — então `select_related("traco")`
    só é possível numa seção escrita à mão, como a de `reunir_dados` faz
    agora.
    """
    from accounts.models import Consentimento
    from allauth.account.models import EmailAddress
    from allauth.socialaccount.models import SocialAccount
    from analytics.models import Event as AnalyticsEvent
    from avisos.models import EmailEnviado, Preferencia
    from plans.models import GoleDeAgua, ItemAvulsoDaLista
    from push.models import DispositivoNativo, NotificationLog, PushSubscription
    from workouts.models import EscolhaDeTreino, EventoDeProduto, PlanoDeCorrida

    return (
        ("accounts.Consentimento", "consentimentos", Consentimento, ("dado_em",)),
        ("plans.GoleDeAgua", "goles_de_agua", GoleDeAgua, ("dia", "registrado_em")),
        (
            "plans.ItemAvulsoDaLista",
            "itens_avulsos_da_lista",
            ItemAvulsoDaLista,
            ("semana", "nome"),
        ),
        ("workouts.EventoDeProduto", "eventos_de_produto", EventoDeProduto, ("date",)),
        ("workouts.EscolhaDeTreino", "escolhas_de_treino", EscolhaDeTreino, ("date",)),
        ("workouts.PlanoDeCorrida", "planos_de_corrida", PlanoDeCorrida, ("criado_em",)),
        ("push.PushSubscription", "assinaturas_push", PushSubscription, ("created_at",)),
        ("push.NotificationLog", "notificacoes_enviadas", NotificationLog, ("sent_at",)),
        ("push.DispositivoNativo", "dispositivos_nativos", DispositivoNativo, ("criado_em",)),
        ("avisos.Preferencia", "preferencia_de_avisos", Preferencia, ()),
        ("avisos.EmailEnviado", "emails_enviados", EmailEnviado, ("enviado_em",)),
        ("analytics.Event", "eventos_analytics", AnalyticsEvent, ("ts",)),
        ("account.EmailAddress", "enderecos_de_email", EmailAddress, ("email",)),
        ("socialaccount.SocialAccount", "contas_sociais", SocialAccount, ("date_joined",)),
    )


#: Os nove exportados à mão (o formato antigo, com nome resolvido onde faz
#: diferença) mais os dois enriquecidos com relação (`ItemDaListaMarcado`,
#: `TrocaDeExercicio`) mais o registro genérico acima. Construído aqui, e não
#: escrito duas vezes, porque a lista de labels do registro genérico já
#: existe — divergir seria o mesmo defeito que a varredura existe para pegar.
EXPORTADOS = {
    "accounts.Profile",
    "accounts.WeightEntry",
    "accounts.TrainingDay",
    "plans.NutritionPlan",
    "plans.HydrationLog",
    "plans.MealLog",
    "plans.ItemDaListaMarcado",
    "workouts.TrainingPlan",
    "workouts.ExerciseLog",
    "workouts.TrocaDeExercicio",
    "workouts.Corrida",
    "achievements.UserAchievement",
} | {label for label, _, _, _ in _registro_generico()}


#: Model com FK/O2O para o usuário que a varredura vê e que, DE PROPÓSITO,
#: não entra no arquivo — com a razão, porque `NAO_EXPORTA` só existe com
#: razão escrita ao lado.
NAO_EXPORTA = {
    "accounts.SyncedOperation": "identificador técnico da fila offline",
    "accounts.RegistroAdministrativo": (
        "trilha de ações administrativas sobre OUTRAS contas — quando a pessoa "
        "é o alvo, o registro fala de uma decisão de um operador, não de algo "
        "que ela produziu; quando é o ator, `alvo_email` seria o e-mail de "
        "outra pessoa dentro do arquivo dela"
    ),
    "admin.LogEntry": (
        "trilha do painel administrativo do Django sobre OUTROS registros — "
        "`object_repr` pode conter dado de terceiros, e a linha descreve uma "
        "ação de operador, não o uso do produto pela própria pessoa"
    ),
}


def reunir_dados(user) -> dict:
    """Tudo o que o NutriPlan guarda sobre uma pessoa, menos o que é segredo
    ou fica justificado em `NAO_EXPORTA`."""
    from accounts.models import Profile, TrainingDay, WeightEntry
    from achievements.models import UserAchievement
    from plans.models import HydrationLog, ItemDaListaMarcado, MealLog, NutritionPlan
    from workouts.models import Corrida, ExerciseLog, TrainingPlan, TrocaDeExercicio

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

    # -- itens da lista de compras marcados: o nome do alimento é o que dá
    # sentido à linha — sem ele sobra só a opção e a semana.
    dados["itens_marcados_da_lista"] = [
        {
            "alimento": item.food.name,
            "opcao": item.opcao,
            "semana": _data(item.semana),
            "marcado_em": _data(item.created_at),
        }
        for item in ItemDaListaMarcado.objects.filter(user=user)
        .select_related("food")
        .order_by("semana", "food__name")
    ]

    # -- trocas de "outras formas": o nome dos dois exercícios é o que torna
    # a linha legível — o helper genérico descartaria as duas relações e
    # deixaria só a data.
    dados["trocas_de_exercicio"] = [
        {
            "original": troca.original.name,
            "substituto": troca.substituto.name,
            "trocado_em": _data(troca.created_at),
        }
        for troca in TrocaDeExercicio.objects.filter(user=user)
        .select_related("original", "substituto")
        .order_by("original__name")
    ]

    # -- corridas, com o traçado: `TracoDaCorrida` é O2O para `Corrida`, não
    # para o usuário, então a varredura não a vê e o genérico não a puxaria
    # — o `select_related` é o que traz o percurso junto sem consulta extra
    # por corrida (achado I3 da revisão, 28/09/2026).
    # `op_id` (SEGREDOS) fica de fora de propósito — é o identificador da
    # fila offline, não dado da corrida.
    dados["corridas"] = [
        {
            "comecou_em": _data(c.comecou_em),
            "terminou_em": _data(c.terminou_em),
            "distancia_m": c.distancia_m,
            "duracao_s": c.duracao_s,
            "teve_lacuna": c.teve_lacuna,
            "parciais": c.parciais,
            "criada_em": _data(c.criada_em),
            "origem": c.origem,
            "sensacao": c.sensacao,
            "traco": (
                {"pontos": c.traco.pontos, "leituras_descartadas": c.traco.descartadas}
                if hasattr(c, "traco")
                else None
            ),
        }
        for c in Corrida.objects.filter(user=user)
        .select_related("traco")
        .order_by("comecou_em")
    ]

    for _label, chave, model, ordenar_por in _registro_generico():
        dados[chave] = _linhas(model, user, ordenar_por)

    # -- redação: a chave de descadastro (e qualquer padrão que
    # `config.observabilidade` já conheça) não pode sobreviver dentro de uma
    # rota ou de um referrer gravados pelo analytics.
    for evento in dados["eventos_analytics"]:
        evento["route"] = _sem_segredo_na_rota(evento["route"])
        evento["referrer"] = _sem_segredo_na_rota(evento["referrer"])
        # `props` é forma livre (round 2 da revisão): `erro.js` grava a
        # rota E a mensagem do erro, e as duas podem carregar a chave.
        evento["props"] = _sem_segredo(evento["props"])

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
