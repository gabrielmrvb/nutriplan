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
    TracoDaCorrida,
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
    corrida = Corrida.objects.create(
        user=user,
        op_id="op-teste-1",
        comecou_em=timezone.now(),
        terminou_em=timezone.now(),
        distancia_m=3000,
        duracao_s=1200,
    )
    # O traçado é filho da CORRIDA, não do usuário — é o achado I3 da
    # revisão: sem ele aqui, o teste de conteúdo não provaria que a seção à
    # mão de `corridas` de fato lê `traco`.
    TracoDaCorrida.objects.create(
        corrida=corrida,
        # `lat` distinta por `user.pk` — como os outros valores deste
        # helper —, para o teste de isolamento medir um traço de A contra
        # um de B de verdade, e não dois pontos idênticos por coincidência.
        pontos=[{"lat": -23.5 - user.pk, "lon": -46.6, "t": 0.0, "acumulado_m": 0.0}],
        descartadas=2,
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

    def test_o_traco_gps_viaja_dentro_da_corrida(self):
        """I3 da revisão: `TracoDaCorrida` é filho de `Corrida`, não do
        usuário — a varredura não o vê, e sem a seção à mão o traçado (dado
        de localização) sumia do arquivo em silêncio."""
        dados = exportacao.reunir_dados(self.user)

        corrida = dados["corridas"][0]
        self.assertIsNotNone(corrida["traco"])
        self.assertEqual(corrida["traco"]["pontos"][0]["lat"], -23.5 - self.user.pk)
        self.assertEqual(corrida["traco"]["leituras_descartadas"], 2)

    def test_nenhum_segredo_atravessa_o_generico(self):
        """`PushSubscription`, `DispositivoNativo`, `avisos.Preferencia` e
        `Corrida` têm campo de credencial no model — o helper genérico
        precisa filtrar pelo NOME REAL do campo, não por um rótulo
        genérico.

        `json.dumps` SEM `default=str` (M1 da revisão): é exatamente a
        chamada que `ExportarDadosView.post` faz. Com `default=str` o teste
        mediria um arquivo que a pessoa nunca recebe — um campo que
        `_valor_json` não sabe converter passaria aqui e daria 500 no botão
        de verdade."""
        import json

        corpo = json.dumps(exportacao.reunir_dados(self.user), ensure_ascii=False)
        for proibido in (
            "push.exemplo.invalid", "chave-p256dh", "chave-auth",
            "token-fcm-teste", "op-teste-1",
        ):
            self.assertNotIn(proibido, corpo, proibido)


class IsolamentoDaExportacaoTests(TestCase):
    """O JSON de uma pessoa não contém e-mail nem dado de linha de OUTRA."""

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def test_a_exportacao_de_a_nao_contem_nada_de_b(self):
        a = create_complete_user()
        b = create_complete_user(email="outra.pessoa@exemplo.invalid")

        _criar_uma_linha_por_model(a)
        _criar_uma_linha_por_model(b)

        import json

        dados_a = exportacao.reunir_dados(a)
        corpo_a = json.dumps(dados_a, ensure_ascii=False)

        self.assertNotIn(b.email, corpo_a)
        # Valores que só existem na conta de B — distintos por `b.pk`, e não
        # um número cru: um `assertNotIn(str(b.pk), ...)` falharia por
        # acidente contra qualquer data ou contagem que contenha o mesmo
        # dígito, sem nada vazar de verdade.
        self.assertNotIn("Item de teste %s" % b.pk, corpo_a)
        self.assertNotIn("uid-teste-%s" % b.pk, corpo_a)
        self.assertNotIn("token-fcm-teste-%s" % b.pk, corpo_a)
        self.assertNotIn("push.exemplo.invalid/%s" % b.pk, corpo_a)

        # M2 da revisão: comparar PKS no banco é tautológico (são sempre
        # disjuntos, com ou sem vazamento — `id` nem sai no arquivo). A
        # prova real é a CONTAGEM: se `_linhas` trocasse `filter(user=user)`
        # por `.all()`, a lista de A passaria a ter as linhas de A E de B.
        for _label, chave, model, _ordenar in exportacao._registro_generico():
            self.assertEqual(
                len(dados_a[chave]), model.objects.filter(user=a).count(), chave
            )

        self.assertEqual(len(dados_a["corridas"]), Corrida.objects.filter(user=a).count())

    def test_o_traco_de_b_nao_aparece_na_exportacao_de_a(self):
        """I3 da revisão: a seção à mão de `corridas` é nova, e o padrão de
        vazamento de A/B vale para ela como vale para o resto."""
        a = create_complete_user()
        b = create_complete_user(email="outra.pessoa@exemplo.invalid")
        _criar_uma_linha_por_model(a)
        _criar_uma_linha_por_model(b)

        traco_de_b = Corrida.objects.get(user=b).traco.pontos

        import json

        corpo_a = json.dumps(exportacao.reunir_dados(a), ensure_ascii=False)
        self.assertNotIn(json.dumps(traco_de_b), corpo_a)


class RedacaoDaRotaDeDescadastroTests(TestCase):
    """I1 da revisão: a chave de descadastro (`avisos.Preferencia.chave`)
    anda na própria URL, e essa URL pode ter sido gravada em
    `analytics.Event.route`/`referrer` — quem clica o link do rodapé do
    e-mail com o navegador logado grava um evento comum."""

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user()
        self.chave = Preferencia.de(self.user).chave

    def test_a_chave_de_descadastro_nao_sai_no_arquivo(self):
        AnalyticsEvent.objects.create(
            user=self.user,
            name="tela.vista",
            route="/avisos/sair/%s/" % self.chave,
            referrer="https://nutriplan.invalid/avisos/sair/%s/" % self.chave,
        )

        import json

        corpo = json.dumps(exportacao.reunir_dados(self.user), ensure_ascii=False)
        self.assertNotIn(self.chave, corpo)

        evento = [
            e for e in exportacao.reunir_dados(self.user)["eventos_analytics"]
            if e["name"] == "tela.vista"
        ][0]
        self.assertIn("[REDIGIDO]", evento["route"])
        self.assertIn("[REDIGIDO]", evento["referrer"])

    def test_evento_sem_rota_nao_quebra(self):
        AnalyticsEvent.objects.create(user=self.user, name="app.aberto")
        dados = exportacao.reunir_dados(self.user)
        self.assertEqual(dados["eventos_analytics"][0]["route"], "")


class VarreduraDeNomesDeSegredoTests(TestCase):
    """I2 da revisão: `SEGREDOS` é uma lista fechada de nomes conferidos
    HOJE contra os models de HOJE. Esta varredura é o que pega o campo que
    alguém acrescentar AMANHÃ com cara de segredo e esquecer de filtrar."""

    def test_todo_campo_com_cara_de_segredo_esta_em_segredos_ou_na_allowlist(self):
        faltando = []
        for label, _chave, model, _ordenar in exportacao._registro_generico():
            permitidos = exportacao.CAMPO_NAO_E_SEGREDO.get(label, {})
            for campo in model._meta.concrete_fields:
                if not exportacao.PADRAO_NOME_DE_SEGREDO.search(campo.name):
                    continue
                if campo.name in exportacao.SEGREDOS or campo.name in permitidos:
                    continue
                faltando.append("%s.%s" % (label, campo.name))

        self.assertEqual(faltando, [])

    def test_a_varredura_enxerga_um_campo_de_verdade(self):
        """Controle positivo: `p256dh_key` bate no padrão — se um dia não
        batesse mais, o teste acima passaria vazio sem estar provando nada."""
        self.assertTrue(exportacao.PADRAO_NOME_DE_SEGREDO.search("p256dh_key"))
        self.assertIn("p256dh_key", exportacao.SEGREDOS)


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
