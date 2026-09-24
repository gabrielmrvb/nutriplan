# -*- coding: utf-8 -*-
"""O Progresso diz o mesmo número toda vez — e a ofensiva é UMA conta só.

Três coisas nesta missão, e as três são a mesma doença: um número da tela
que não corresponde ao que o app guarda.

1. **A caixa do consolidado misturava dois denominadores.** Desde 22/09/2026
   `adherence_pct` é dos DIAS FECHADOS ("hoje ainda está acontecendo"), e
   `avg_kcal` continuou sendo de TODOS os dias — hoje incluído. A média de
   "kcal/dia" caía a cada manhã, subia durante o dia e era comparada com a
   meta de um dia inteiro ao lado. Quem lia a tela três vezes no mesmo dia
   via três médias, sem ter mudado nada de propósito. Agora as duas leem o
   mesmo recorte, e no primeiro dia — quando não há dia fechado — a caixa
   mostra o de HOJE em vez de uma média que não existe.

2. **A ofensiva tem de ser a mesma nas três telas.** Ela já foi diferente:
   as Conquistas chamavam `streaks.calcular` sem a meta de água, a água
   "fechava" todo dia, e a tela dizia "3 dias" (ou "401 / 3") enquanto a
   Home dizia 0 (achado #4 das personas). A correção de 22/09 foi passar a
   meta nos dois lugares — o que deixava a régua dependendo de cada chamador
   lembrar. `streaks.para_a_tela` é a porta única: ela deriva a meta do
   plano ativo, e nenhuma tela escolhe a sua.

3. **A frase de ontem diz o NÚMERO.** "Ontem faltou dieta ou água" era dita
   a quem registrou 3 refeições de 5 e bebeu 1,5 L de 3 — a pessoa
   registrou as duas coisas; o que faltou foi CHEGAR na meta. Medido no
   navegador em 24/09/2026.
"""
import re
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay, WeightEntry
from plans import services, streaks, tracking
from plans.models import HydrationLog, MealLog, MealStatus
from plans.tests import create_complete_user
from workouts import services as treino_services


def _numeros(html):
    """Os números que a caixa do consolidado imprime, na ordem."""
    corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
    caixa = corpo.split('class="tiles"', 1)[1].split("</section>", 1)[0]
    return re.findall(r'class="tile__value[^"]*"[^>]*>([^<]+)<', caixa)


class ACaixaDoConsolidadoLeUmRecorteSoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="tiles@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        hoje = timezone.localdate()
        self.user.date_joined = timezone.now() - timedelta(days=3)
        self.user.save(update_fields=["date_joined"])
        services.sync_active_plan(self.user)
        plano = services.get_active_plan(self.user)
        self.horarios = list(plano.slots.all().order_by("time"))
        # Dois dias FECHADOS com 2 000 kcal cada, e hoje com 400 — o café.
        for atras, kcal in ((2, Decimal("1000")), (1, Decimal("1000"))):
            dia = hoje - timedelta(days=atras)
            for slot in self.horarios[:2]:
                MealLog.objects.update_or_create(
                    user=self.user, slot=slot, date=dia,
                    defaults={"status": MealStatus.DONE, "kcal": kcal},
                )
        MealLog.objects.update_or_create(
            user=self.user, slot=self.horarios[0], date=hoje,
            defaults={"status": MealStatus.DONE, "kcal": Decimal("400")},
        )

    def test_a_media_de_kcal_e_dos_dias_fechados_como_a_aderencia(self):
        """Os dois números da mesma caixa não podem ter denominadores
        diferentes: 2 000 é a média dos dois dias fechados; incluir hoje,
        que tem 400, dava 1 466."""
        linhas = tracking.history(self.user)
        self.assertEqual(tracking.adherence(linhas)["avg_kcal"], 2000)

    def test_a_media_nao_muda_com_a_hora_do_dia(self):
        """A prova da determinação: as mesmas linhas, lidas às 7h e às 23h,
        dão o mesmo consolidado. Era aqui que a tela discordava de si mesma —
        a média incluía um dia em andamento."""
        medidos = set()
        real = timezone.localtime
        for hora in (7, 13, 20, 23):
            with mock.patch.object(
                tracking.timezone, "localtime",
                lambda *a, **k: real(*a, **k).replace(hour=hora, minute=0),
            ):
                consolidado = tracking.adherence(tracking.history(self.user))
                medidos.add((consolidado["avg_kcal"], consolidado["adherence_pct"]))
        self.assertEqual(len(medidos), 1, medidos)

    def test_cinco_leituras_seguidas_da_tela_dao_os_mesmos_numeros(self):
        vistos = {tuple(_numeros(self.client.get(reverse("plans:history")).content.decode()))
                  for _ in range(5)}
        self.assertEqual(len(vistos), 1, vistos)

    def test_a_leitura_depois_do_post_do_peso_da_os_mesmos_numeros(self):
        """O caminho do relato: registrar o peso e cair no Progresso pelo
        redirect. O peso não muda refeição nenhuma, então a caixa também não
        pode mudar."""
        antes = _numeros(self.client.get(reverse("plans:history")).content.decode())
        resposta = self.client.post(
            reverse("accounts:log_weight"), {"weight_kg": "83,5", "origem": "metricas"}
        )
        self.assertEqual(resposta.status_code, 302)
        depois = _numeros(self.client.get(resposta["Location"]).content.decode())
        self.assertEqual(antes, depois)

    def test_sabotagem_uma_refeicao_a_mais_num_dia_fechado_move_a_media(self):
        """Controle positivo: a caixa continua LENDO o banco — ela só parou
        de ler o dia em andamento."""
        antes = _numeros(self.client.get(reverse("plans:history")).content.decode())
        MealLog.objects.update_or_create(
            user=self.user, slot=self.horarios[2],
            date=timezone.localdate() - timedelta(days=1),
            defaults={"status": MealStatus.DONE, "kcal": Decimal("1000")},
        )
        depois = _numeros(self.client.get(reverse("plans:history")).content.decode())
        self.assertNotEqual(antes, depois)


class OPrimeiroDiaNaoTemMediaTests(TestCase):
    """Conta nascida hoje: nenhum dia fechado, e nenhuma média a mostrar."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="dia1@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        self.user.date_joined = timezone.now()
        self.user.save(update_fields=["date_joined"])
        services.sync_active_plan(self.user)
        plano = services.get_active_plan(self.user)
        MealLog.objects.update_or_create(
            user=self.user, slot=plano.slots.all().order_by("time").first(),
            date=timezone.localdate(),
            defaults={"status": MealStatus.DONE, "kcal": Decimal("400")},
        )

    def test_o_consolidado_nao_tem_porcentagem_nem_media(self):
        consolidado = tracking.adherence(tracking.history(self.user))
        self.assertIsNone(consolidado["adherence_pct"])
        self.assertIsNone(consolidado["avg_kcal"])

    def test_a_tela_diz_que_e_o_primeiro_dia_em_vez_de_inventar_uma_media(self):
        html = self.client.get(reverse("plans:history")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        caixa = corpo.split('class="tiles"', 1)[1].split("</section>", 1)[0]
        self.assertIn("hoje, até agora", caixa)
        self.assertNotIn("%", caixa)
        self.assertIn("400", caixa, "o que ela comeu HOJE continua na tela")


class AOfensivaEUmaContaSoNasTresTelasTests(TestCase):
    """Home, Progresso e Conquistas contam a MESMA ofensiva.

    Elas já contaram diferente: as Conquistas chamavam `calcular` sem a meta
    de água e diziam "3 dias" (ou "401 / 3") enquanto a Home dizia 0.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="ofensiva@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        self.user.date_joined = timezone.now() - timedelta(days=10)
        self.user.save(update_fields=["date_joined"])

    def _espiar(self, rota):
        """O que cada tela pediu à ofensiva, e o que recebeu."""
        chamadas = []
        real = streaks.calcular

        def espia(*args, **kwargs):
            resultado = real(*args, **kwargs)
            chamadas.append((kwargs.get("meta_agua_ml"), resultado.dias))
            return resultado

        with mock.patch.object(streaks, "calcular", side_effect=espia):
            resposta = self.client.get(rota)
        self.assertEqual(resposta.status_code, 200, rota)
        self.assertTrue(chamadas, "%s não contou ofensiva nenhuma" % rota)
        return chamadas

    def test_as_tres_telas_pedem_a_mesma_meta_de_agua_e_recebem_o_mesmo_numero(self):
        medidos = set()
        for rota in (reverse("plans:today"), reverse("plans:history"),
                     reverse("achievements:list")):
            medidos.update(self._espiar(rota))
        self.assertEqual(len(medidos), 1, medidos)

    def test_nenhuma_tela_conta_ofensiva_sem_meta_de_agua(self):
        """Sem meta, `agua=True` em todo dia e a régua "treino e (dieta ou
        água)" fecha sozinha — era a origem do "401 / 3"."""
        for rota in (reverse("plans:today"), reverse("plans:history"),
                     reverse("achievements:list")):
            for meta, _ in self._espiar(rota):
                self.assertTrue(meta, "%s contou sem meta de água" % rota)


class AFraseDeOntemDizONumeroTests(TestCase):
    """"Ontem faltou dieta ou água" para quem registrou as duas coisas.

    Medido no navegador em 24/09/2026: 3 refeições de 5 e 1 500 ml de uma
    meta de 3 000. A pessoa registrou; o que faltou foi CHEGAR na meta, e a
    frase não dizia isso.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="ontem@exemplo.com")

    def setUp(self):
        self.user.date_joined = timezone.now() - timedelta(days=10)
        self.user.save(update_fields=["date_joined"])
        self.hoje = timezone.localdate()
        self.ontem = self.hoje - timedelta(days=1)
        TrainingDay.objects.filter(user=self.user).delete()
        services.sync_active_plan(self.user)
        plano = services.get_active_plan(self.user)
        self.horarios = list(plano.slots.all().order_by("time"))
        for slot in self.horarios[:3]:
            MealLog.objects.update_or_create(
                user=self.user, slot=slot, date=self.ontem,
                defaults={"status": MealStatus.DONE, "kcal": Decimal("500")},
            )
        HydrationLog.objects.update_or_create(
            user=self.user, date=self.ontem, defaults={"ml": 1500}
        )

    def _ontem(self):
        return streaks.para_a_tela(self.user, hoje=self.hoje)

    def test_a_frase_traz_os_dois_numeros_da_dieta_e_da_agua(self):
        ofensiva = self._ontem()
        self.assertEqual(ofensiva.dias, 0)
        frase = ofensiva.mensagem
        self.assertIn("3 de 5 refeições", frase)
        self.assertIn("1,5", frase)
        self.assertIn("3 L", frase)

    def test_a_frase_nao_diz_o_rotulo_solto_de_antes(self):
        self.assertNotIn("faltou dieta ou água.", self._ontem().mensagem)

    def test_sem_serie_num_dia_de_treino_a_frase_diz_isso(self):
        """Os dias previstos saem da FICHA (`plan.sessions`), e não de
        `TrainingDay` — criar só a linha do dia deixaria `previstos` vazio e
        o teste passaria verde medindo outra coisa."""
        call_command("seed_workouts", verbosity=0)
        TrainingDay.objects.create(
            user=self.user, weekday=self.ontem.weekday(), duration_min=60
        )
        treino_services.create_routine(self.user)
        frase = self._ontem().mensagem
        self.assertIn("nenhuma série", frase)

    def test_sabotagem_mudar_a_agua_de_ontem_muda_a_frase(self):
        antes = self._ontem().mensagem
        HydrationLog.objects.filter(user=self.user, date=self.ontem).update(ml=800)
        self.assertNotEqual(antes, self._ontem().mensagem)
        self.assertIn("0,8", self._ontem().mensagem)

    def test_a_frase_de_hoje_continua_com_o_rotulo_curto(self):
        """O que FECHA o dia, sem número: é a decisão de 22/09/2026 e ela
        não muda aqui — a frase medida era a de ONTEM."""
        ofensiva = streaks.para_a_tela(self.user, hoje=self.hoje)
        self.assertEqual(ofensiva.falta_hoje, ["dieta ou água"])
