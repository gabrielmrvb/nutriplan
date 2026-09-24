"""A ofensiva começa no dia em que a conta nasceu — nunca antes.

Achado #4 das personas (21/09/2026): "3 dias de ofensiva" desbloqueada no
PRIMEIRO dia para quem treina, e "401 / 3" para quem não tem dia de
treino. Dois defeitos na mesma conta:

- a ofensiva percorria 400 dias para trás e um dia sem treino previsto e
  sem meta de água (`meta_agua_ml=None` → `agua=True`) FECHAVA sozinho —
  então os 400 dias anteriores ao cadastro contavam como cumpridos;
- `achievements` chamava `streaks.calcular` SEM a meta de água, enquanto a
  Home passava a meta: duas telas, dois números ("0 dias" na Home, "3 dias"
  nas Conquistas).

A régua nova: nenhum dia anterior a `user.date_joined` conta — nem na
sequência, nem no recorde —, e as Conquistas passam a mesma meta de água
que a Home. Quem nasce hoje tem zero, e é isso que é verdade.
"""
from datetime import datetime, timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from achievements import services as conquistas
from accounts.models import User
from plans import services, streaks, weight_trend
from plans.models import HydrationLog
from plans.tests import CatalogFixture, create_complete_user


class OfensivaComecaNaContaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def _nascida_hoje(self, email="hoje@exemplo.com", **kw):
        user = create_complete_user(email=email, **kw)
        user.date_joined = timezone.now()
        user.save(update_fields=["date_joined"])
        return user

    def test_quem_so_corre_nao_ganha_quatrocentos_dias(self):
        """Sem dia de treino, todo dia antigo "fechava" — com a meta de água
        (a Home sempre a passa) o de hoje ainda não fechou, e os de antes da
        conta não existem."""
        user = self._nascida_hoje()
        user.training_days.all().delete()
        plano = services.create_plan(user)
        meta = weight_trend.hidratacao_ml(plano.weight_kg)
        hoje = timezone.localdate()
        ofensiva = streaks.calcular(user, hoje=hoje, meta_agua_ml=meta)
        self.assertEqual(ofensiva.dias, 0)
        self.assertEqual(ofensiva.recorde, 0)
        self.assertEqual(conquistas.reunir(user, hoje=hoje).ofensiva, 0)

    def test_quem_treina_nao_nasce_com_tres_dias(self):
        """Segunda de manhã: sábado e domingo eram "descanso cumprido" antes
        de a conta existir, e a Home dizia 0 enquanto as Conquistas diziam 3."""
        user = self._nascida_hoje("treina@exemplo.com")
        plano = services.create_plan(user)
        meta = weight_trend.hidratacao_ml(plano.weight_kg)
        hoje = timezone.localdate()
        self.assertEqual(streaks.calcular(user, hoje=hoje, meta_agua_ml=meta).dias, 0)
        self.assertEqual(conquistas.reunir(user, hoje=hoje).ofensiva, 0)

    def test_sem_meta_de_agua_os_dias_de_antes_da_conta_continuam_fora(self):
        """O caso cru da persona: sem dia de treino e sem meta, o dia anterior à
        conta fechava sozinho. Hoje pode fechar (não há o que cobrar); ontem não
        existe."""
        user = self._nascida_hoje("cru@exemplo.com")
        user.training_days.all().delete()
        ofensiva = streaks.calcular(user, hoje=timezone.localdate())
        # e um dia sem NADA a cumprir (sem treino previsto, sem cardápio, sem
        # meta) não fecha — não há o que ter cumprido
        self.assertEqual(ofensiva.dias, 0)
        self.assertEqual(ofensiva.recorde, 0)

    def test_as_conquistas_usam_a_mesma_meta_de_agua_que_a_home(self):
        """A mesma conta, o mesmo número, nas duas telas — com a água pesando."""
        user = create_complete_user(email="agua@exemplo.com")
        user.date_joined = timezone.now() - timedelta(days=10)
        user.save(update_fields=["date_joined"])
        user.training_days.all().delete()  # todo dia é descanso: fecha com dieta OU água
        plano = services.create_plan(user)
        meta = weight_trend.hidratacao_ml(plano.weight_kg)
        hoje = timezone.localdate()
        # ontem e anteontem: só meia meta de água, nenhuma refeição
        for atras in (1, 2):
            HydrationLog.objects.create(user=user, date=hoje - timedelta(days=atras), ml=meta // 2)
        da_home = streaks.calcular(user, hoje=hoje, meta_agua_ml=meta).dias
        das_conquistas = conquistas.reunir(user, hoje=hoje).ofensiva
        self.assertEqual(da_home, 0)
        self.assertEqual(das_conquistas, da_home)

    def test_no_primeiro_dia_a_mensagem_e_comece_hoje_e_depois_diz_o_que_faltou_ontem(self):
        """Persona 1 no dia 2: treinou, comeu 2 de 5 e bebeu 1 L de 2,25 — e a
        Home dizia "0 dias — Comece hoje". Hoje ela diz o que faltou ontem."""
        nova = self._nascida_hoje("mensagem@exemplo.com")
        plano = services.create_plan(nova)
        meta = weight_trend.hidratacao_ml(plano.weight_kg)
        hoje = timezone.localdate()
        # "COMECE", e não "recomeça": no primeiro dia não há o que recomeçar
        # (`falta_ontem is None` é exatamente "ontem não era da conta"). E a
        # frase diz O QUE FAZER, não o que faltou — rodada 2, 24/09/2026.
        self.assertEqual(
            streaks.calcular(nova, hoje=hoje, meta_agua_ml=meta).mensagem,
            "Comece hoje: registre uma refeição ou um copo d'água.",
        )

        antiga = create_complete_user(email="ontem@exemplo.com")
        antiga.date_joined = timezone.now() - timedelta(days=5)
        antiga.save(update_fields=["date_joined"])
        antiga.training_days.all().delete()  # ontem foi descanso: falta dieta ou água
        plano = services.create_plan(antiga)
        meta = weight_trend.hidratacao_ml(plano.weight_kg)
        HydrationLog.objects.create(user=antiga, date=hoje - timedelta(days=1), ml=meta // 2)
        ofensiva = streaks.calcular(antiga, hoje=hoje, meta_agua_ml=meta)
        self.assertEqual(ofensiva.dias, 0)
        # O NÚMERO de ontem continua verdadeiro e calculado — quem o lê são
        # outras telas. O que saiu da FRASE foi a palavra "faltou": desde
        # 22/09/2026 ela já não ABRIA por aí ("Ontem faltou X. Hoje
        # recomeça: …"), e na rodada 2 de experiência (24/09) ela deixou de
        # terminar nela também. Zero convida; cobrar duas vezes pela mesma
        # coisa era o que fazia a primeira aparição do treino na Home ser
        # uma bronca num cartão de zero dias.
        self.assertEqual(ofensiva.falta_ontem, ["dieta ou água"])
        self.assertNotIn("faltou", ofensiva.mensagem)
        # E aqui o verbo é RECOMEÇA: a conta existia ontem.
        self.assertEqual(
            ofensiva.mensagem,
            "Recomeça hoje: registre uma refeição ou um copo d'água.",
        )

    def test_o_dia_da_entrada_conta_e_o_anterior_nao(self):
        user = create_complete_user(email="entrada@exemplo.com")
        hoje = timezone.localdate()
        user.date_joined = timezone.make_aware(datetime.combine(hoje - timedelta(days=3), datetime.min.time()))
        user.save(update_fields=["date_joined"])
        user.training_days.all().delete()
        plano = services.create_plan(user)
        meta = weight_trend.hidratacao_ml(plano.weight_kg)
        for atras in range(1, 10):
            HydrationLog.objects.create(user=user, date=hoje - timedelta(days=atras), ml=meta)
        ofensiva = streaks.calcular(user, hoje=hoje, meta_agua_ml=meta)
        # ontem, anteontem e o dia da entrada: três; o quarto dia atrás não existia
        self.assertEqual(ofensiva.dias, 3)
        self.assertEqual(ofensiva.recorde, 3)
