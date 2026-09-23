"""Progresso: a meta da época, e o que a tela pode afirmar sobre evolução."""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    Goal,
    Profile,
    Sex,
)
from plans import tracking
from plans.models import MealLog, MealStatus, NutritionPlan

User = get_user_model()


class MetaDaEpocaTests(TestCase):
    """A barra do dia a dia compara com a meta que valia NAQUELE dia.

    O defeito que isto corrige: a tela comparava todo dia com a meta atual.
    Como a meta muda justamente quando o peso muda, o dia da recalibragem era
    o dia em que a comparação passava a mentir para trás — quem cortou 200
    kcal na terça via a segunda inteira parecendo excesso.

    O dado sempre esteve no banco: `NutritionPlan` é retrato e os antigos
    ficam. Faltava ir buscar.
    """

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="progresso@exemplo.com", password="senha-bem-forte-123"
        )
        # A CONTA NASCE ANTES DOS DADOS que o teste escreve (23/09/2026).
        #
        # Desde o redesenho, a tela não desenha nada anterior ao cadastro — é
        # a regra do item 6, e ela está certa: em produção ninguém tem
        # registro de antes de ter conta. Em TESTE, criar a pessoa agora e
        # escrever histórico para trás produz um estado que a vida não
        # produz, e a tela responde com uma janela de um dia. Nascer antes é
        # o que faz o fixture descrever gente possível — a mesma correção que
        # `plans.tests.create_complete_user` levou no lote 2.
        self.pessoa.date_joined = timezone.now() - timedelta(days=120)
        self.pessoa.save(update_fields=["date_joined"])
        Profile.objects.create(
            user=self.pessoa,
            sex=Sex.MALE,
            birth_date=date(1995, 4, 12),
            height_cm=178,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        self.hoje = timezone.localdate()

    def _plano(self, alvo, dias_atras, ativo=False):
        plano = NutritionPlan.objects.create(
            user=self.pessoa,
            weight_kg=Decimal("80"), height_cm=178, age_years=30,
            sex=Sex.MALE, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            bmr_kcal=1700, tdee_kcal=2300, target_kcal=alvo,
            protein_g=160, carb_g=300, fat_g=70,
            is_active=ativo,
        )
        # `auto_now_add` ignora o valor passado; a data se ajusta depois.
        NutritionPlan.objects.filter(pk=plano.pk).update(
            created_at=timezone.now() - timedelta(days=dias_atras)
        )
        return plano

    def test_cada_dia_usa_a_meta_que_valia_nele(self):
        self._plano(2600, dias_atras=20)
        self._plano(2400, dias_atras=5, ativo=True)

        dias = [self.hoje - timedelta(days=n) for n in (10, 1)]
        metas = tracking.metas_por_dia(self.pessoa, dias)

        self.assertEqual(metas[self.hoje - timedelta(days=10)], 2600)
        self.assertEqual(metas[self.hoje - timedelta(days=1)], 2400)

    def test_o_dia_da_troca_ja_usa_a_meta_nova(self):
        """O plano vale para o dia em que nasceu: quem recalibrou de manhã
        passou o dia inteiro com a meta nova."""
        self._plano(2600, dias_atras=20)
        self._plano(2400, dias_atras=3, ativo=True)

        dia_da_troca = self.hoje - timedelta(days=3)
        metas = tracking.metas_por_dia(self.pessoa, [dia_da_troca])

        self.assertEqual(metas[dia_da_troca], 2400)

    def test_dia_anterior_ao_primeiro_plano_usa_o_primeiro(self):
        """Comparar o que a pessoa comeu antes de existir plano com uma meta
        que ainda não existia seria inventar a régua. Usar a primeira é a
        aproximação menos errada, e não afeta o caso comum: quase ninguém tem
        registro anterior ao próprio plano."""
        self._plano(2600, dias_atras=5, ativo=True)

        antigo = self.hoje - timedelta(days=30)
        metas = tracking.metas_por_dia(self.pessoa, [antigo])

        self.assertEqual(metas[antigo], 2600)

    def test_sem_plano_nenhum_nao_quebra(self):
        self.assertEqual(tracking.metas_por_dia(self.pessoa, [self.hoje]), {})

    def test_a_tela_usa_a_meta_da_epoca_na_barra(self):
        """Prova de ponta a ponta: o mesmo consumo em dois dias com metas
        diferentes tem que render barras diferentes. Comparado com a meta de
        hoje, os dois dariam a mesma."""
        self._plano(2000, dias_atras=20)
        self._plano(4000, dias_atras=2, ativo=True)
        for atras in (10, 1):
            MealLog.objects.create(
                user=self.pessoa,
                date=self.hoje - timedelta(days=atras),
                status=MealStatus.DONE,
                kcal=1000,
                slot_name="almoço",
            )
        self.client.force_login(self.pessoa)

        linhas = self.client.get("/historico/").context["rows"]

        por_dia = {linha["date"]: linha for linha in linhas}
        antigo = por_dia[self.hoje - timedelta(days=10)]
        recente = por_dia[self.hoje - timedelta(days=1)]
        self.assertEqual(antigo["meta"], 2000)
        self.assertEqual(recente["meta"], 4000)
        self.assertEqual(antigo["pct"], 50)
        self.assertEqual(recente["pct"], 25)

    def test_a_meta_da_epoca_nao_custa_uma_consulta_por_dia(self):
        """Trinta dias na tela não podem virar trinta consultas."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._plano(2600, dias_atras=20)
        self._plano(2400, dias_atras=5, ativo=True)

        poucos = [self.hoje - timedelta(days=n) for n in range(3)]
        with CaptureQueriesContext(connection) as a:
            tracking.metas_por_dia(self.pessoa, poucos)

        muitos = [self.hoje - timedelta(days=n) for n in range(30)]
        with CaptureQueriesContext(connection) as b:
            tracking.metas_por_dia(self.pessoa, muitos)

        self.assertEqual(len(a.captured_queries), len(b.captured_queries))


class AguaPorSemanaTests(TestCase):
    """Média sobre os dias com registro, e o número de dias junto."""

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="agua@exemplo.com", password="senha-bem-forte-123"
        )
        self.hoje = date(2026, 9, 2)  # quarta

    def _agua(self, dia, ml):
        from plans.models import HydrationLog

        return HydrationLog.objects.create(user=self.pessoa, date=dia, ml=ml)

    def test_a_media_e_sobre_os_dias_com_registro(self):
        """Dividir por sete transformaria "3 litros em dois dias" em "média de
        850 ml", que descreve um comportamento que não aconteceu. Quem esqueceu
        de anotar não bebeu zero — o app só não sabe."""
        self._agua(self.hoje, 3000)
        self._agua(self.hoje - timedelta(days=1), 3000)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 2)
        self.assertEqual(semanas[-1]["media_ml"], 3000)

    def test_o_numero_de_dias_acompanha_a_media(self):
        """A média sozinha esconde quantos dias a sustentam."""
        self._agua(self.hoje, 4000)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 1)
        self.assertEqual(semanas[-1]["media_ml"], 4000)

    def test_linha_zerada_nao_conta_como_dia(self):
        """A linha nasce por `get_or_create` quando a tela do dia abre.
        Existir não é ter bebido."""
        self._agua(self.hoje, 0)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(semanas[-1]["dias"], 0)
        self.assertEqual(semanas[-1]["media_ml"], 0)

    def test_semana_sem_registro_aparece_zerada(self):
        self._agua(self.hoje, 2000)

        semanas = tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(semanas), 8)
        self.assertEqual([s["dias"] for s in semanas[:-1]], [0] * 7)

    def test_o_custo_nao_cresce_com_os_registros(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for n in range(5):
            self._agua(self.hoje - timedelta(days=n), 2000)
        with CaptureQueriesContext(connection) as poucos:
            tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        for n in range(5, 50):
            self._agua(self.hoje - timedelta(days=n), 2000)
        with CaptureQueriesContext(connection) as muitos:
            tracking.agua_por_semana(self.pessoa, hoje=self.hoje)

        self.assertEqual(len(poucos.captured_queries), len(muitos.captured_queries))


class TelaDeProgressoTests(TestCase):
    """A tela mostra o treino, e diz o que cada número significa."""

    def setUp(self):
        from workouts.models import Exercise, ExerciseLog

        self.pessoa = User.objects.create_user(
            email="tela@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.pessoa, sex=Sex.MALE, birth_date=date(1995, 4, 12),
            height_cm=178, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            wake_time=time(7, 0), sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        self.hoje = timezone.localdate()
        self.supino = Exercise.objects.create(
            name="Supino reto com barra", muscle_group="peito", padrao="pressao_de_peito",
        )
        for atras, carga in ((14, "60"), (0, "70")):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.supino,
                date=self.hoje - timedelta(days=atras),
                set_number=1, weight_kg=Decimal(carga), reps=10,
            )
        # Uma refeição marcada: sem ela `totals.days` é zero e a tela mostra o
        # estado vazio inteiro, sem o cartão do dia a dia. O teste da régua
        # mediria a ausência do cartão em vez do texto dele.
        MealLog.objects.create(
            user=self.pessoa, date=self.hoje, status=MealStatus.DONE,
            kcal=800, slot_name="almoço",
        )
        self.client.force_login(self.pessoa)

    def _html(self):
        return self.client.get("/historico/").content.decode()

    def test_a_carga_de_dois_e_meio_nao_vira_um_numero_que_nao_existe(self):
        """`floatformat:0` arredondava 62,5 para 63 e 12,5 para 13 — e a barra
        não tem 63 kg. Medido em 13/09/2026: "60 → 63 kg +3" para quem foi de
        60 a 62,5. `-2` mostra "62,5" e continua mostrando "60" sem casa."""
        from workouts.models import ExerciseLog

        ExerciseLog.objects.filter(user=self.pessoa, exercise=self.supino).delete()
        for atras, carga in ((14, "60"), (0, "62.5")):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.supino,
                date=self.hoje - timedelta(days=atras),
                set_number=1, weight_kg=Decimal(carga), reps=10,
            )
        html = self._html()
        # A LISTA DE PROGRESSÃO (60 → 62,50 kg) saiu no redesenho de
        # 23/09/2026, e "Seus recordes" ficou no lugar. O que este teste
        # protegia continua protegido — o meio quilo não pode virar um número
        # que não existe —, agora no recorde: 62,5 é carga real de anilha, e
        # 63 não é.
        linha = html.split("Supino reto com barra", 1)[1].split("</li>", 1)[0]
        linha = " ".join(linha.split())
        self.assertIn("62,50 kg", linha)
        self.assertNotIn("63", linha)

    def test_o_treino_aparece_na_tela(self):
        """O buraco que a V2 fechou: cada série estava no banco e nenhuma
        aparecia numa tela chamada Métricas. Desde 23/09/2026 quem mostra é
        "Seus recordes" (carga máxima por exercício, com data) no lugar da
        lista de progressão de 14 dias — a mudança está registrada no
        relatório da missão."""
        html = self._html()

        self.assertIn("Supino reto com barra", html)
        self.assertIn("Seus recordes", html)

    def test_a_tela_nao_chama_frequencia_de_aderencia(self):
        """`TrainingDay` é o que a pessoa DECLAROU; `ExerciseLog` é o que ela
        fez. Uma razão entre os dois fingiria medir compromisso."""
        html = self._html().lower()

        pedaco = html[html.index("treino") : html.index("treino") + 3000]
        for palavra in ("aderência ao treino", "% dos treinos", "compromisso"):
            with self.subTest(palavra=palavra):
                self.assertNotIn(palavra, pedaco)

    def test_a_dica_explica_a_regua_de_cada_dia(self):
        """A barra passou a usar a meta da época. Se a tela continuasse dizendo
        "sua meta atual", o texto contradiria o número."""
        html = self._html()

        self.assertIn("que valia NAQUELE dia", html)
        self.assertNotIn("compara o dia com a sua meta atual", html)

    def test_o_custo_da_tela_nao_cresce_com_os_registros(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from workouts.models import ExerciseLog

        self.client.get("/historico/")
        with CaptureQueriesContext(connection) as poucos:
            self.client.get("/historico/")

        for n in range(2, 40):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.supino,
                date=self.hoje - timedelta(days=n % 40),
                set_number=n, weight_kg=Decimal("65"), reps=10,
            )
        # A PRIMEIRA visita depois de 38 dias de treino DESBLOQUEIA o que
        # chegou a 100 % (5, 10 e 25 treinos — `achievements.resumo`,
        # 16/09/2026, B35): custo de UMA vez, limitado pelo CATÁLOGO de
        # regras e não pelos registros. A régua de N+1 é a visita seguinte.
        from achievements.regras import CATALOGO
        with CaptureQueriesContext(connection) as desbloqueio:
            self.client.get("/historico/")
        self.assertLessEqual(
            len(desbloqueio.captured_queries) - len(poucos.captured_queries),
            5 * len(CATALOGO),
        )
        with CaptureQueriesContext(connection) as muitos:
            self.client.get("/historico/")

        self.assertEqual(len(poucos.captured_queries), len(muitos.captured_queries))

    def test_sem_treino_nenhum_a_tela_convida_em_vez_de_cobrar(self):
        from workouts.models import ExerciseLog

        ExerciseLog.objects.filter(user=self.pessoa).delete()

        html = self._html()

        self.assertIn("Nenhuma série anotada ainda", html)
        # A PORTA, e não só a frase: a frase sozinha continuava verde com o
        # vazio frio ("assim que você salvar… aparece aqui", sem link).
        vazio = html.split("Nenhuma série anotada ainda", 1)[1].split("</div>", 1)[0]
        self.assertIn(reverse("workouts:routine"), vazio)
        self.assertIn("btn", vazio)

    def test_sem_refeicao_marcada_o_vazio_usa_o_mesmo_botao_dos_outros(self):
        """Os três vazios da tela falam a mesma língua (§39): a ação primária
        do Progresso é a pesagem, e o convite da alimentação era um segundo
        botão cheio acima da dobra."""
        from plans.models import MealLog

        MealLog.objects.filter(user=self.pessoa).delete()

        html = self._html()

        self.assertIn("Nenhuma refeição registrada", html)
        vazio = html.split("Nenhuma refeição registrada", 1)[1].split("</div>", 1)[0]
        self.assertIn(reverse("plans:today"), vazio)
        self.assertIn("btn--ghost", vazio)
        self.assertNotIn("btn--primary", vazio)

    def test_sem_agua_nenhuma_o_vazio_da_a_porta_da_agua(self):
        """O mesmo contrato para a seção de água (§39): benefício + ação."""
        from plans.models import HydrationLog

        HydrationLog.objects.filter(user=self.pessoa).delete()

        html = self._html()

        self.assertIn("Nenhum registro de água ainda", html)
        vazio = html.split("Nenhum registro de água ainda", 1)[1].split("</div>", 1)[0]
        self.assertIn(reverse("plans:hydration"), vazio)


class MesmaGramaticaTests(TestCase):
    """Treino e água respondem a mesma pergunta e são lidos do mesmo jeito.

    Eu tinha desenhado uma como barras e a outra como lista, na MESMA tela.
    Duas soluções para o mesmo problema é dívida de UX nascendo: quem lê passa
    a decodificar dois formatos para comparar duas séries do próprio hábito.

    Este teste é sobre CONSISTÊNCIA e não sobre estilo — ele não afirma como a
    série deve parecer, afirma que as duas parecem a mesma coisa.
    """

    def setUp(self):
        from plans.models import HydrationLog
        from workouts.models import Exercise, ExerciseLog

        self.pessoa = User.objects.create_user(
            email="gramatica@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.pessoa, sex=Sex.MALE, birth_date=date(1995, 4, 12),
            height_cm=178, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            wake_time=time(7, 0), sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        hoje = timezone.localdate()
        exercicio = Exercise.objects.create(name="Supino", muscle_group="peito", padrao="pressao_de_peito")
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=exercicio, date=hoje,
            set_number=1, weight_kg=Decimal("60"), reps=10,
        )
        HydrationLog.objects.create(user=self.pessoa, date=hoje, ml=2500)
        MealLog.objects.create(
            user=self.pessoa, date=hoje, status=MealStatus.DONE,
            kcal=700, slot_name="almoço",
        )
        self.client.force_login(self.pessoa)

    def test_as_duas_series_usam_a_mesma_estrutura(self):
        """A régua continua sendo "uma gramática só", e ficou mais forte.
        O REDESENHO DE 23/09/2026 trocou a lista de oito semanas pelo mapa
        do dia mais as colunas da semana — um sistema de gráfico só para as
        quatro áreas. O que este teste prendia (as duas séries com a MESMA
        gramática) continua valendo e ficou mais forte: agora é literalmente
        a mesma parcial (`plans/_progresso_area.html`) para as quatro.
        """
        html = self.client.get("/historico/").content.decode()

        self.assertIn('area-evolucao--treino', html)
        self.assertIn('area-evolucao--agua', html)
        # A MESMA classe de mapa nas duas: é a mesma parcial, e não duas
        # soluções parecidas que divergem na primeira mudança.
        for area in ("treino", "agua"):
            bloco = html.split('area-evolucao--%s' % area, 1)[1].split("</section>", 1)[0]
            with self.subTest(area=area):
                self.assertIn("mapa-dias__dia", bloco)

    def test_o_recorte_e_o_da_JANELA_e_nao_oito_semanas_fixas(self):
        """O defeito que o redesenho corrigiu: as séries tinham horizonte fixo
        de oito semanas, e numa conta de três dias sete delas eram anteriores
        ao cadastro. Agora quem manda é `plans.evolucao.janela`."""
        from plans import evolucao

        painel = self.client.get("/historico/").context["painel"]
        janela = painel["janela"]
        nascimento = timezone.localtime(self.pessoa.date_joined).date()

        self.assertGreaterEqual(janela.inicio, nascimento)
        for area in painel["areas"]:
            with self.subTest(area=area.chave):
                self.assertEqual(len(area.mapa), len(evolucao.dias_da_janela(janela)))

    def test_a_media_de_agua_vem_com_os_dias_que_a_sustentam(self):
        """A média sozinha mente nos dois sentidos, e a régua é a mesma de
        antes: o que a barra da semana mostra é a média dos dias COM
        registro (`evolucao.barras(..., media=True)`), e o tile diz quantos
        dias a sustentam."""
        painel = self.client.get("/historico/").context["painel"]
        agua = [t for t in painel["tiles"] if t.chave == "agua"][0]

        self.assertEqual(agua.valor, "2.500")
        self.assertIn("dia com registro", agua.frase)
