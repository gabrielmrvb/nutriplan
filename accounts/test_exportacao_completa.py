"""A exportação leva TUDO que o app guarda sobre a pessoa, ou justifica por
que não leva (LGPD art. 18, V) — o gap medido no Gate 1 da missão LGPD.

`reunir_dados` tinha nove chaves à mão e o resto ficava de fora sem ninguém
decidir isso. A varredura abaixo não lê uma lista escrita à mão: ela lê
`get_user_model()._meta.related_objects`, a verdade do banco, e reprova se um
model novo (o de amanhã incluído) não estiver em `exportacao.EXPORTADOS` nem
justificado em `exportacao.NAO_EXPORTA`.
"""
import time
from decimal import Decimal

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, tag
from django.utils import timezone

from accounts import exportacao
from accounts.models import Consentimento
from analytics.models import Event as AnalyticsEvent
from avisos.models import EmailEnviado, Preferencia, TipoDeEmail
from catalog.models import Food
from plans.models import GoleDeAgua, ItemAvulsoDaLista, ItemDaListaMarcado
from plans.tests import CatalogFixture, create_complete_user
from push.models import DispositivoNativo, NotificationLog, PushSubscription
from workouts.models import (
    Corrida,
    EscolhaDeTreino,
    EventoDeProduto,
    Exercise,
    PlanoDeCorrida,
    Split,
    TrainingPlan,
    TrainingSession,
    TrocaDeExercicio,
    VersaoDoTreino,
)


class NenhumModelDaPessoaFicaDeForaTests(TestCase):
    """A varredura: todo model com FK/O2O para o usuário está coberto."""

    def test_todo_model_com_fk_para_o_usuario_e_exportado_ou_justificado(self):
        rel = {
            r.related_model._meta.label
            for r in get_user_model()._meta.related_objects
        }
        faltando = rel - exportacao.EXPORTADOS - set(exportacao.NAO_EXPORTA)
        self.assertEqual(faltando, set())

    def test_a_varredura_enxerga_um_model_novo(self):
        """Controle positivo: se este teste um dia falhar, a varredura parou
        de ver o banco de verdade e passou a olhar para uma lista congelada."""
        rel = {
            r.related_model._meta.label
            for r in get_user_model()._meta.related_objects
        }
        self.assertIn("workouts.Corrida", rel)

    def test_nao_exporta_so_tem_razao_escrita(self):
        for label, razao in exportacao.NAO_EXPORTA.items():
            self.assertTrue(razao and razao.strip(), label)


def _criar_uma_linha_por_model(user):
    """Uma linha em CADA model exportado, pelo ORM — o suficiente para provar
    que `reunir_dados` de fato lê cada tabela e não só declara a chave."""
    from accounts.models import Profile, TrainingDay, WeightEntry
    from achievements.models import UserAchievement
    from plans import services
    from plans.models import HydrationLog, MealLog, MealStatus

    from datetime import timedelta

    Profile.objects.filter(user=user).update(sex="f")
    # `create_complete_user` já grava peso de hoje e treino em seg/qua/sex —
    # este helper usa outro dia para não colidir com o fixture de base.
    WeightEntry.objects.get_or_create(
        user=user,
        date=timezone.localdate() - timedelta(days=1),
        defaults={"weight_kg": Decimal("70.0")},
    )
    TrainingDay.objects.get_or_create(user=user, weekday=5, defaults={"duration_min": 45})
    services.get_active_plan(user) or services.create_plan(user)
    HydrationLog.objects.create(user=user, date=timezone.localdate(), ml=1000)
    MealLog.objects.create(
        user=user,
        date=timezone.localdate(),
        slot_name="Almoço",
        scheduled_time=timezone.now().time(),
        status=MealStatus.DONE,
    )

    food, _ = Food.objects.get_or_create(
        name="Item de teste %s" % user.pk,
        defaults=dict(kcal=Decimal(100), protein_g=Decimal(10), carb_g=Decimal(10), fat_g=Decimal(1)),
    )
    ItemDaListaMarcado.objects.create(
        user=user, food=food, opcao="A", semana=timezone.localdate()
    )

    call_command("seed_workouts", verbosity=0)
    exercicio1 = Exercise.objects.filter(is_active=True).first()
    exercicio2 = (
        Exercise.objects.filter(is_active=True).exclude(pk=exercicio1.pk).first()
    )
    # Se o teste já tem uma rotina ativa (o timing de `OrcamentoDaExportacaoTests`
    # roda `create_routine` antes), usa ela — o índice único de plano ativo por
    # pessoa não deixa duas coexistirem.
    plano_treino = TrainingPlan.objects.filter(user=user, is_active=True).first()
    if plano_treino is None:
        plano_treino = TrainingPlan.objects.create(
            user=user, split=Split.FULL, days_per_week=1, is_active=True
        )
    sessao, _ = TrainingSession.objects.get_or_create(
        plan=plano_treino, weekday=6, defaults={"label": "A", "name": "Corpo inteiro"}
    )
    from workouts.models import ExerciseLog, SessionExercise

    SessionExercise.objects.create(session=sessao, exercise=exercicio1, order=1)
    ExerciseLog.objects.create(
        user=user,
        exercise=exercicio1,
        date=timezone.localdate(),
        set_number=1,
        weight_kg=Decimal("20.0"),
        reps=10,
    )
    UserAchievement.objects.create(user=user, slug="primeiro_treino")

    Consentimento.objects.create(user=user, tipo=Consentimento.Tipo.SAUDE, versao="2026-09-28")
    GoleDeAgua.objects.create(user=user, dia=timezone.localdate(), ml=250)
    ItemAvulsoDaLista.objects.create(user=user, nome="Café", semana=timezone.localdate())
    EventoDeProduto.objects.create(user=user, nome="versao_rapida", date=timezone.localdate())
    TrocaDeExercicio.objects.create(user=user, original=exercicio1, substituto=exercicio2)
    EscolhaDeTreino.objects.create(
        user=user, date=timezone.localdate(), session=sessao, versao=VersaoDoTreino.COMPLETO
    )
    Corrida.objects.create(
        user=user,
        op_id="op-teste-1",
        comecou_em=timezone.now(),
        terminou_em=timezone.now(),
        distancia_m=3000,
        duracao_s=1200,
    )
    PlanoDeCorrida.objects.create(
        user=user,
        plano=PlanoDeCorrida.Plano.CINCO_K,
        nivel=PlanoDeCorrida.Nivel.INICIANTE,
        comecou_em=timezone.localdate(),
    )
    PushSubscription.objects.create(
        user=user,
        endpoint="https://push.exemplo.invalid/%s" % user.pk,
        p256dh_key="chave-p256dh",
        auth_key="chave-auth",
    )
    NotificationLog.objects.create(user=user, date=timezone.localdate())
    DispositivoNativo.objects.create(
        user=user, token="token-fcm-teste-%s" % user.pk, plataforma="android"
    )
    Preferencia.de(user)
    EmailEnviado.objects.create(user=user, tipo=TipoDeEmail.BOAS_VINDAS, referencia="conta")
    AnalyticsEvent.objects.create(user=user, name="teste.evento")
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    SocialAccount.objects.create(user=user, provider="google", uid="uid-teste-%s" % user.pk)


class ConteudoDaExportacaoTests(TestCase):
    """Cada chave nova do JSON tem pelo menos um item — a varredura prova
    presença, este teste prova que o dado É lido, não só declarado."""

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user()
        _criar_uma_linha_por_model(self.user)

    def test_cada_chave_exportada_tem_pelo_menos_um_item(self):
        dados = exportacao.reunir_dados(self.user)

        chaves_de_lista = [
            "pesagens", "dias_de_treino", "metas_calculadas", "refeicoes_marcadas",
            "agua", "treinos", "series_registradas", "conquistas",
            "itens_marcados_da_lista", "trocas_de_exercicio",
            "consentimentos", "goles_de_agua", "itens_avulsos_da_lista",
            "eventos_de_produto", "escolhas_de_treino", "corridas",
            "planos_de_corrida", "assinaturas_push", "notificacoes_enviadas",
            "dispositivos_nativos", "emails_enviados", "eventos_analytics",
            "enderecos_de_email", "contas_sociais",
        ]
        for chave in chaves_de_lista:
            self.assertGreaterEqual(len(dados[chave]), 1, chave)

        # `avisos.Preferencia` é O2O: uma linha, não uma lista.
        self.assertIsNotNone(dados["preferencia_de_avisos"])

    def test_conteudo_tem_o_nome_resolvido_e_nao_so_a_relacao(self):
        dados = exportacao.reunir_dados(self.user)

        self.assertEqual(
            dados["itens_marcados_da_lista"][0]["alimento"], "Item de teste %s" % self.user.pk
        )
        troca = dados["trocas_de_exercicio"][0]
        self.assertTrue(troca["original"])
        self.assertTrue(troca["substituto"])
        self.assertNotEqual(troca["original"], troca["substituto"])

    def test_nenhum_segredo_atravessa_o_generico(self):
        """`PushSubscription`, `DispositivoNativo`, `avisos.Preferencia` e
        `Corrida` têm campo de credencial no model — o helper genérico
        precisa filtrar pelo NOME REAL do campo, não por um rótulo
        genérico."""
        import json

        corpo = json.dumps(exportacao.reunir_dados(self.user), ensure_ascii=False, default=str)
        for proibido in (
            "push.exemplo.invalid", "chave-p256dh", "chave-auth",
            "token-fcm-teste", "op-teste-1",
        ):
            self.assertNotIn(proibido, corpo, proibido)


class IsolamentoDaExportacaoTests(TestCase):
    """O JSON de uma pessoa não contém e-mail nem id de linha de OUTRA."""

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def test_a_exportacao_de_a_nao_contem_nada_de_b(self):
        a = create_complete_user()
        b = create_complete_user(email="outra.pessoa@exemplo.invalid")

        _criar_uma_linha_por_model(a)
        _criar_uma_linha_por_model(b)

        import json

        corpo_a = json.dumps(exportacao.reunir_dados(a), ensure_ascii=False, default=str)

        self.assertNotIn(b.email, corpo_a)
        # Valores que só existem na conta de B — distintos por `b.pk`, e não
        # um número cru: um `assertNotIn(str(b.pk), ...)` falharia por
        # acidente contra qualquer data ou contagem que contenha o mesmo
        # dígito, sem nada vazar de verdade.
        self.assertNotIn("Item de teste %s" % b.pk, corpo_a)
        self.assertNotIn("uid-teste-%s" % b.pk, corpo_a)
        self.assertNotIn("token-fcm-teste-%s" % b.pk, corpo_a)
        self.assertNotIn("push.exemplo.invalid/%s" % b.pk, corpo_a)

        for label, chave, model, _ in exportacao._registro_generico():
            ids_de_b = set(model.objects.filter(user=b).values_list("pk", flat=True))
            ids_de_a = set(model.objects.filter(user=a).values_list("pk", flat=True))
            self.assertTrue(ids_de_b, label)
            self.assertFalse(ids_de_a & ids_de_b, label)


@tag("lento")
class OrcamentoDaExportacaoTests(TestCase):
    """A exportação fica SÍNCRONA (sem arquivo guardado, sem Actions) enquanto
    medir abaixo de 5 s numa conta cheia (decisão 4 do plano LGPD). Este
    teste é a guarda: se um dia passar de 5 s sem ninguém perceber, a decisão
    de servir na hora deixou de valer e ninguém vai saber olhando só a tela.

    `@tag("lento")` porque gera um ano de histórico — fica de fora da suíte
    rápida, como os outros orçamentos pesados do repositório."""

    TETO_SEGUNDOS = 5.0

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def test_reunir_dados_fica_abaixo_do_teto_numa_conta_cheia(self):
        user = create_complete_user()
        from plans import services
        from workouts.services import create_routine

        services.create_plan(user)
        create_routine(user)
        call_command("seed_stress", user.email, "--dias", "365", verbosity=0)
        _criar_uma_linha_por_model(user)  # cobre os models que o seed_stress não popula

        # 500 goles de água e 500 eventos de analytics: a mesma ordem de
        # grandeza que uma pessoa que usa o app todo dia por um ano e é
        # medida pelo próprio produto acumularia nos dois models mais
        # "quantitativos" que faltam no `seed_stress`.
        GoleDeAgua.objects.bulk_create(
            GoleDeAgua(user=user, dia=timezone.localdate(), ml=250) for _ in range(500)
        )
        AnalyticsEvent.objects.bulk_create(
            AnalyticsEvent(user=user, name="app.aberto") for _ in range(500)
        )

        inicio = time.perf_counter()
        dados = exportacao.reunir_dados(user)
        decorrido = time.perf_counter() - inicio
        print(f"\nreunir_dados na conta cheia (seed_stress 365 dias): {decorrido:.3f}s")

        self.assertLess(decorrido, self.TETO_SEGUNDOS, f"{decorrido:.2f}s")
        self.assertGreater(len(dados["pesagens"]), 150)
