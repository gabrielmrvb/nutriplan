""""Você faz musculação?" — a pergunta que corredores e nadadores não tinham.

Item 5 da missão de UX (22/09/2026) e achado #9 das personas: a etapa 2
obrigava quem só corre a inventar respostas de academia (experiência,
equipamento, dias) e a aba Treino cobrava "Cadastrar meus dias de treino"
para sempre. Hoje `Profile.musculacao` guarda a resposta (`sim` / `nao`; em
branco é "não perguntado", o estado de toda conta anterior à pergunta —
uso não é intenção declarada): com "não", experiência, equipamento, dias e
divisão não são pedidos nem gravados, a ficha não nasce, e a aba Treino
diz o que a pessoa disse em vez de cobrar.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Musculacao, Profile, User
from accounts.test_tres_etapas import ETAPA1, ETAPA2, ETAPA3, etapa
from workouts.models import TrainingPlan

SO_CORRO = {"goal": "cut", "activity_level": "light", "musculacao": "nao", "wake_time": "07:00", "sleep_time": "23:30"}


def sem_scripts(html):
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S)


class PerguntaDaMusculacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(email="corredora@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)

    def test_a_etapa_2_pergunta_antes_da_experiencia_e_do_equipamento(self):
        html = sem_scripts(self.client.get(etapa(2)).content.decode())
        self.assertIn('name="musculacao" value="sim"', html)
        self.assertIn('name="musculacao" value="nao"', html)
        self.assertLess(html.index('name="musculacao"'), html.index('name="experiencia"'))
        # o bloco que só faz sentido com musculação é UM contêiner, que o
        # JavaScript esconde com "não"
        bloco = html.split("data-so-musculacao", 1)[1]
        for campo in ("experiencia", "equipamento", "weekdays", "split_preference"):
            self.assertIn('name="%s"' % campo, bloco, campo)
        # e a janela do dia NÃO está dentro dele: refeição não depende de treino
        self.assertLess(html.index('name="wake_time"'), html.index("data-so-musculacao")) if html.index('name="wake_time"') < html.index("data-so-musculacao") else self.assertNotIn('name="wake_time"', bloco.split("</div>\n        </div>", 1)[0])

    def test_sem_resposta_a_etapa_2_nao_avanca(self):
        resposta = self.client.post(etapa(2), {k: v for k, v in ETAPA2.items() if k != "musculacao"})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("musculacao", resposta.context["forms"]["rotina"].errors)

    def test_quem_so_corre_avanca_sem_dias_experiencia_nem_equipamento(self):
        resposta = self.client.post(etapa(2), SO_CORRO)
        self.assertRedirects(resposta, etapa(3), fetch_redirect_response=False)
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.musculacao, Musculacao.NAO)
        self.assertEqual(self.user.training_days.count(), 0)

    def test_com_nao_os_dias_enviados_sao_ignorados(self):
        """Sem JavaScript o bloco continua na tela; o servidor é quem decide."""
        self.client.post(etapa(2), {**SO_CORRO, "weekdays": ["0", "2", "4"], "experiencia": "avancado", "split_preference": "three"})
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.musculacao, Musculacao.NAO)
        self.assertEqual(self.user.training_days.count(), 0)
        self.assertEqual(perfil.experiencia, "")

    def test_com_sim_tudo_continua_como_antes(self):
        self.client.post(etapa(2), {**ETAPA2, "musculacao": "sim"})
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.musculacao, Musculacao.SIM)
        self.assertEqual(self.user.training_days.count(), 3)

    def test_o_resumo_da_etapa_3_diz_que_nao_faz_e_nao_lista_o_resto(self):
        self.client.post(etapa(2), SO_CORRO)
        html = self.client.get(etapa(3)).content.decode()
        resumo = html.split('class="data-list resumo-etapas"', 1)[1].split("</dl>", 1)[0]
        self.assertIn("Musculação", resumo)
        self.assertIn("Não faço", resumo)
        for rotulo in ("Dias de treino", "Experiência", "Equipamento", "Divisão"):
            self.assertNotIn(rotulo, resumo, rotulo)

    def test_calcular_a_estimativa_nao_monta_ficha_e_a_aba_treino_nao_cobra_dias(self):
        self.client.post(etapa(2), SO_CORRO)
        self.client.post(etapa(3), ETAPA3, follow=True)
        self.assertFalse(TrainingPlan.objects.filter(user=self.user, is_active=True).exists())
        html = sem_scripts(self.client.get(reverse("workouts:routine")).content.decode())
        self.assertNotIn("Cadastrar meus dias de treino", html)
        self.assertNotIn("Falta dizer em quais dias", html)
        self.assertIn("não faz musculação", html)
        self.assertIn(reverse("workouts:corridas"), html)
        self.assertIn("origem=treino", html)  # a porta para mudar de ideia

    def test_o_perfil_mostra_a_resposta(self):
        self.client.post(etapa(2), SO_CORRO)
        self.client.post(etapa(3), ETAPA3, follow=True)
        html = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn("Musculação", html)
        self.assertIn("Não faço", html)

    def test_quem_ja_tinha_conta_abre_a_etapa_2_com_sim_marcado_se_tem_dias(self):
        """Conta anterior à pergunta (`musculacao == ""`) com dias de treino:
        a resposta implícita é sim, e a tela abre com ela — sem obrigar quem
        vai trocar o equipamento a responder de novo."""
        self.client.post(etapa(2), {**ETAPA2, "musculacao": "sim"})
        Profile.objects.filter(user=self.user).update(musculacao="")
        html = sem_scripts(self.client.get(etapa(2)).content.decode())
        self.assertRegex(html, r'name="musculacao" value="sim"[^>]*checked')

    def test_o_pwa_esconde_o_bloco_com_nao(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        self.assertIn("data-so-musculacao", js)
        self.assertIn('name="musculacao"', js.replace("'", '"'))
