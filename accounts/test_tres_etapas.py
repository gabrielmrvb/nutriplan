"""O onboarding tem TRÊS etapas reais — nem seis, nem seis maquiadas de três.

Decisão C-ONB (14/09/2026) e ordem do dono (15/09/2026): a produção ainda
mostrava "Passo 1/6 · 16%" em `/conta/onboarding/1/`, seis rotas e CTA
"Salvar". Aqui: três rotas (1, 2, 3), "Etapa N de 3", CTAs "Continuar" /
"Continuar" / "Criar meu plano", voltar sem perder dado, atualizar sem
corromper, e a conclusão montando cardápio E ficha.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ONBOARDING_DONE, Profile, TrainingDay, User
from plans.models import NutritionPlan
from workouts.models import TrainingPlan

ETAPA1 = {"sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82,4"}
#: Três dias já pedem a divisão (`preferencia_muda_a_divisao(3)` é True: ABC
#: e ABC2 divergem a partir daí), então o payload de três dias a inclui.
ETAPA2 = {
    "goal": "cut", "activity_level": "light", "experiencia": "intermediario",
    "weekdays": ["0", "2", "4"], "wake_time": "07:00", "sleep_time": "23:30",
    "split_preference": "two",
}
#: Dois dias: a divisão não muda nada e não é pedida.
ETAPA2_DOIS_DIAS = {**ETAPA2, "weekdays": ["0", "3"]}
ETAPA2_DOIS_DIAS.pop("split_preference")
ETAPA3 = {"meal_style": "quick", "interesses": ["treino"], "prioridade": "treino"}


def etapa(n):
    return reverse("accounts:onboarding_step", kwargs={"step": n})


class TresEtapasReaisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(email="tres@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)

    def test_so_existem_tres_rotas(self):
        self.assertEqual(self.client.get(etapa(1)).status_code, 200)
        for n in (4, 5, 6, 0, 7):
            with self.subTest(n=n):
                self.assertEqual(self.client.get(etapa(n)).status_code, 404)

    def test_a_etapa_2_avisa_o_que_muda_no_peso_do_corpo(self):
        """Decisão 1 da avaliação de UX (20/09/2026): desde o catálogo de peso
        do corpo a ficha desse perfil é CHEIA e comparável às outras — o aviso
        deixou de dizer "ficha mais curta" (era verdade só até o catálogo
        cobrir) e passou a dizer o que de fato muda: peito, ombro e bíceps
        ficam mais leves, por limite físico do próprio corpo, e dá para trocar
        o equipamento depois. O onboarding continua não fingindo paridade
        total, mas sem alarmar quem escolhe "em casa, sem nada"."""
        self.client.post(etapa(1), ETAPA1)  # o onboarding só libera a etapa 2 depois da 1
        html = self.client.get(etapa(2)).content.decode()
        self.assertIn("field__nota-equipamento", html)
        self.assertIn("<strong>Só o peso do corpo</strong>", html)
        self.assertIn("mais leves", html)

    def test_a_etapa_1_diz_1_de_3_e_continuar(self):
        html = self.client.get(etapa(1)).content.decode()
        self.assertIn("Etapa 1 de 3", html)
        self.assertIn("Sobre você", html)
        self.assertIn(">Continuar<", html.replace("\n", "").replace("  ", ""))
        self.assertNotIn("Passo 1/6", html)
        self.assertNotIn("/6", html.split("<main", 1)[1])
        self.assertNotIn("%", re.search(r'class="wizard__label[^"]*"[^>]*>([^<]*)<', html).group(1))

    def test_ida_e_volta_nao_perde_dados(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        resposta = self.client.get(etapa(1))
        volta = resposta.content.decode()
        self.assertIn('value="178"', volta)
        # O peso volta do banco (o widget ainda escreve ponto — T2b.4 da onda 2b).
        self.assertEqual(resposta.context["form"].fields["weight_kg"].initial, Decimal("82.40"))
        de_novo = self.client.get(etapa(2)).content.decode()
        self.assertIn('value="0"', de_novo)  # segunda-feira continua marcada
        self.assertIn("checked", de_novo)
        self.assertEqual(Profile.objects.get(user=self.user).goal, "cut")

    def test_atualizar_a_pagina_nao_corrompe_o_andamento(self):
        self.client.post(etapa(1), ETAPA1)
        for _ in range(3):
            self.assertEqual(self.client.get(etapa(2)).status_code, 200)
        self.assertEqual(Profile.objects.get(user=self.user).onboarding_step, 2)
        # Pular para a 3 antes da 2 devolve para a 2.
        self.assertRedirects(self.client.get(etapa(3)), etapa(2))

    def test_criar_meu_plano_conclui_e_monta_cardapio_e_ficha(self):
        hoje = timezone.localdate().weekday()
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), {**ETAPA2, "weekdays": [str(hoje), str((hoje + 2) % 7), str((hoje + 4) % 7)]})
        html = self.client.get(etapa(3)).content.decode()
        self.assertIn("Etapa 3 de 3", html)
        self.assertIn("Criar meu plano", html)
        resposta = self.client.post(etapa(3), ETAPA3)
        self.assertRedirects(resposta, reverse("plans:today"))
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.onboarding_step, ONBOARDING_DONE)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user, is_active=True).count(), 1)
        self.assertEqual(TrainingPlan.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_concluir_duas_vezes_nao_duplica_planos(self):
        """Concluir é idempotente: o duplo toque em "Criar meu plano" (ou o
        reenvio da tela de montagem) não cria um segundo cardápio nem uma
        segunda ficha.

        Conta TODOS os planos, e não só os ativos: `create_plan` desliga o
        anterior ao criar, então contar ativos deixaria a duplicação passar
        com um plano "morto" a cada toque. O terceiro POST rearma a etapa 3
        para representar o segundo pedido de um duplo clique, que ainda
        enxerga o cadastro por concluir.
        """
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        self.client.post(etapa(3), ETAPA3)  # já concluído: edição
        Profile.objects.filter(user=self.user).update(onboarding_step=3)
        self.client.post(etapa(3), ETAPA3)  # o segundo toque do duplo clique
        self.assertEqual(NutritionPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(TrainingPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user, is_active=True).count(), 1)
        self.assertEqual(TrainingPlan.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_zero_dias_conclui_sem_ficha_e_sem_500(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), {**ETAPA2, "weekdays": []})
        resposta = self.client.post(etapa(3), ETAPA3)
        self.assertRedirects(resposta, reverse("plans:today"))
        self.assertFalse(TrainingPlan.objects.filter(user=self.user).exists())
        self.assertTrue(NutritionPlan.objects.filter(user=self.user, is_active=True).exists())

    def test_treino_sem_horario_e_o_padrao_e_nao_quebra_nada(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        self.assertTrue(all(d.start_time is None for d in TrainingDay.objects.filter(user=self.user)))
        self.client.post(etapa(3), ETAPA3)
        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)

    def test_a_divisao_e_exigida_quando_os_dias_pedem(self):
        """A régua é a do motor (`preferencia_muda_a_divisao`): hoje, três dias."""
        self.client.post(etapa(1), ETAPA1)
        sem_divisao = {k: v for k, v in ETAPA2.items() if k != "split_preference"}
        resposta = self.client.post(etapa(2), sem_divisao)
        self.assertEqual(resposta.status_code, 200)  # reprovou: falta a divisão
        self.assertContains(resposta, "divisão")
        self.assertEqual(Profile.objects.get(user=self.user).onboarding_step, 2)
        resposta = self.client.post(etapa(2), ETAPA2)
        self.assertRedirects(resposta, etapa(3))
        perfil = Profile.objects.get(user=self.user)
        self.assertTrue(perfil.split_preference_confirmada)
        self.assertEqual(perfil.split_preference, "two")

    def test_com_dois_dias_a_divisao_nao_e_pedida_nem_confirmada(self):
        self.client.post(etapa(1), ETAPA1)
        self.assertRedirects(self.client.post(etapa(2), ETAPA2_DOIS_DIAS), etapa(3))
        self.assertFalse(Profile.objects.get(user=self.user).split_preference_confirmada)

    def test_a_etapa_3_resume_as_escolhas(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        html = self.client.get(etapa(3)).content.decode()
        for trecho in ("Emagrecer", "Seg", "Qua", "Sex", "178 cm", "82,4"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, html)


class QuemJaConcluiuTests(TestCase):
    """Compatibilidade: quem passou pelo fluxo antigo continua concluído e edita sem refazer."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user
        self.user = create_complete_user(email="antigo@exemplo.com")
        self.client.force_login(self.user)

    def test_a_home_abre_e_nao_manda_para_o_onboarding(self):
        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("accounts:onboarding")), reverse("plans:today"))

    def test_editar_uma_etapa_salva_e_volta_ao_perfil(self):
        html = self.client.get(etapa(2)).content.decode()
        self.assertIn(">Salvar<", html.replace("\n", "").replace("  ", ""))
        self.assertNotIn("Criar meu plano", html)
        resposta = self.client.post(etapa(2), {**ETAPA2, "goal": "bulk"})
        self.assertRedirects(resposta, reverse("accounts:profile"))
        self.assertEqual(Profile.objects.get(user=self.user).goal, "bulk")
        self.assertEqual(Profile.objects.get(user=self.user).onboarding_step, ONBOARDING_DONE)

    def test_editar_a_personalizacao_nao_mostra_o_resumo_do_cadastro(self):
        """O resumo é a conferência antes de "Criar meu plano"; quem veio do
        Perfil trocar o cardápio não tem esse botão nem edita altura ali."""
        html = self.client.get(etapa(3)).content.decode()
        self.assertNotIn('class="data-list resumo-etapas"', html)
        self.assertIn(">Salvar<", html.replace(chr(10), "").replace("  ", ""))

    def test_editar_os_dias_pelo_treino_volta_ao_treino(self):
        resposta = self.client.post(etapa(2) + "?origem=treino", ETAPA2)
        self.assertRedirects(resposta, reverse("workouts:routine"), fetch_redirect_response=False)


class EditarADivisaoRemontaAFichaNaHoraTests(TestCase):
    """A ficha remontada na edição lê a divisão que ACABOU de ser gravada.

    Achado da revisão adversarial (15/09/2026): `TrainingForm.__init__` lê
    `user.profile`, e o Django guarda essa reversa no próprio `user`. A
    divisão era gravada noutra instância (`self.profile`), e
    `acertar_rotina(user)` — no mesmo pedido — lia a preferência VELHA pelo
    cache: "só a divisão mudou" era visto como "nada mudou", e o Perfil
    dizia "2 grupos" com a Home mostrando a sessão do ABC. O wizard antigo
    não tinha o defeito porque o passo da divisão nunca tocava
    `user.profile` antes de remontar.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(email="divisao@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), {**ETAPA2, "weekdays": ["0", "1", "3", "4"], "split_preference": "three"})
        self.client.post(etapa(3), ETAPA3)

    def test_trocar_so_a_divisao_remonta_a_ficha_com_a_nova(self):
        from workouts.services import split_for

        antes = TrainingPlan.objects.get(user=self.user, is_active=True)
        self.assertEqual(antes.split, split_for(4, "three"))
        resposta = self.client.post(
            etapa(2), {**ETAPA2, "weekdays": ["0", "1", "3", "4"], "split_preference": "two"}
        )
        self.assertEqual(resposta.status_code, 302)
        depois = TrainingPlan.objects.get(user=self.user, is_active=True)
        self.assertEqual(Profile.objects.get(user=self.user).split_preference, "two")
        self.assertEqual(depois.split, split_for(4, "two"))
        self.assertNotEqual(depois.pk, antes.pk)


class NenhumTemplateDizSeisPassosTests(TestCase):
    def test_zero_ocorrencias_de_passo_n_de_6(self):
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR)
        for arquivo in list((base / "templates").rglob("*.html")) + [base / "accounts" / "views.py"]:
            texto = arquivo.read_text(encoding="utf-8")
            with self.subTest(arquivo=arquivo.name):
                self.assertNotRegex(texto, r"Passo \{\{|Passo \d/6|/6 ·|step=[456]\b")


class MigracaoParaTresEtapasTests(TransactionTestCase):
    """`0032` remapeia só quem parou no meio; concluído (7) não é tocado."""

    ANTES = ("accounts", "0031_plano_gratis_ou_pro")
    DEPOIS = ("accounts", "0032_onboarding_em_tres_etapas")

    def _apps_em(self, alvo):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([alvo])
        return executor.loader.project_state([alvo]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_de_para(self):
        apps = self._apps_em(self.ANTES)
        User = apps.get_model("accounts", "User")
        Profile = apps.get_model("accounts", "Profile")
        for passo in (1, 2, 3, 4, 5, 6, 7):
            user = User.objects.create(email="p%d@exemplo.com" % passo, password="x")
            Profile.objects.create(
                user=user, sex="M", birth_date=date(1995, 4, 12), height_cm=178,
                onboarding_step=passo,
            )
        apps = self._apps_em(self.DEPOIS)
        Profile = apps.get_model("accounts", "Profile")
        # O e-mail guarda o passo de origem ("p4@…" veio do 4).
        depois = {
            int(perfil.user.email[1]): perfil.onboarding_step
            for perfil in Profile.objects.select_related("user")
        }
        self.assertEqual(depois, {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3, 7: 7})

    def test_a_reversa_nao_inventa_passo_antigo(self):
        apps = self._apps_em(self.DEPOIS)
        User = apps.get_model("accounts", "User")
        Profile = apps.get_model("accounts", "Profile")
        user = User.objects.create(email="r@exemplo.com", password="x")
        Profile.objects.create(user=user, sex="M", birth_date=date(1995, 4, 12), height_cm=178, onboarding_step=3)
        apps = self._apps_em(self.ANTES)
        self.assertEqual(apps.get_model("accounts", "Profile").objects.get().onboarding_step, 3)


class CriarMeuPlanoPelaMontagemTests(TestCase):
    """A tela de montagem envia por `fetch`; o destino volta no corpo e a
    mensagem sobrevive até a navegação de verdade."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_xhr_recebe_o_destino_e_a_mensagem_chega_na_home(self):
        user = User.objects.create_user(email="xhr@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(user)
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        resposta = self.client.post(etapa(3), ETAPA3, headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"destino": reverse("plans:today")})
        home = self.client.get(reverse("plans:today"))
        self.assertContains(home, "Seu plano está pronto")


class ErrosJuntoAoCampoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="erros@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)

    def test_a_janela_curta_aparece_junto_dos_relogios(self):
        resposta = self.client.post(etapa(2), {**ETAPA2, "wake_time": "07:00", "sleep_time": "09:00"})
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        janela = html.split("A janela do seu dia", 1)[1].split("</div>\n        </div>", 1)[0]
        self.assertIn("muito curta", janela)

    def test_o_campo_obrigatorio_erra_no_proprio_campo_e_preserva_o_resto(self):
        resposta = self.client.post(etapa(2), {k: v for k, v in ETAPA2.items() if k != "goal"})
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        objetivo = html.split("Qual é o seu objetivo?", 1)[1].split("</ul>", 1)[0]
        self.assertIn("Este campo é obrigatório", html)
        self.assertIn('value="4"', html)  # o dia de sexta continua marcado
        self.assertIn('checked', html)
