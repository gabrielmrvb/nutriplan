"""O catálogo e a promessa de tempo (16/09/2026).

Medido em 16/09/2026 sobre o gerador (3 níveis × 3 preferências × 2–7 dias,
teto 60): a sessão entregue vai de 14 a 59 minutos — nenhuma combinação chega
a 60 —, e "Completo" (teto 90) e "Sem limite" (65) produzem o MESMO treino
em todas as 54 combinações, porque a faixa de séries do nível (≤ 20) e a
dose do catálogo limitam a sessão antes do relógio. A copy tinha de dizer
isso: nenhum rótulo promete um piso que o gerador não garante, "Completo"
usa por construção o teto que já entregava, "Sem limite" não é oferecido em
formulário nenhum, e a Home diz o teto de todo mundo.
"""
import re
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, Profile, TETO_POR_DURACAO, TrainingDay
from plans.tests import create_complete_user
from workouts import opcoes, services

RAIZ = Path(__file__).resolve().parent.parent


class CopyDeTempoTests(SimpleTestCase):
    def test_nenhum_rotulo_promete_um_piso_de_minutos(self):
        """"45 a 60" e "60 a 90" prometiam pisos que o gerador não garante
        (entrega 32–54 e nunca chega a 60). Rótulo diz só o teto."""
        for faixa in DuracaoTreino:
            with self.subTest(faixa=faixa):
                self.assertNotRegex(faixa.label, r"\d+ a \d+")
                self.assertIn("até", faixa.label)

    def test_completo_e_sem_limite_dizem_que_sao_a_mesma_coisa(self):
        self.assertEqual(DuracaoTreino.COMPLETO.label, "Completo — a sessão inteira, até 65 minutos")
        self.assertEqual(
            DuracaoTreino.LIVRE.label, "Sem limite rígido — o mesmo que Completo, até 65 minutos"
        )
        self.assertEqual(DuracaoTreino.RAPIDO.label, "Rápido — até 30 minutos")
        self.assertEqual(DuracaoTreino.PADRAO.label, "Padrão — até 60 minutos")

    def test_completo_usa_o_teto_que_entrega(self):
        """Medido: com 90 ou 65 o treino é idêntico nas 54 combinações. O teto
        passa a ser 65 por construção, para o rótulo ser verdade e não
        coincidência."""
        self.assertEqual(TETO_POR_DURACAO[DuracaoTreino.COMPLETO], opcoes.TETO_COMPLETO_MIN)
        self.assertIsNone(TETO_POR_DURACAO[DuracaoTreino.LIVRE])

    def test_sem_limite_nao_e_oferecido_em_formulario_nenhum(self):
        """Continua no `choices` e no banco (quem tem, mantém); some da UI."""
        self.assertEqual(
            [f for f in DuracaoTreino.escolhas_visiveis()],
            [DuracaoTreino.RAPIDO, DuracaoTreino.PADRAO, DuracaoTreino.COMPLETO],
        )
        for caminho in RAIZ.glob("templates/**/*.html"):
            with self.subTest(template=caminho.name):
                self.assertNotIn('name="duracao_treino"', caminho.read_text(encoding="utf-8"))

    def test_a_ficha_nao_promete_ate_40_min(self):
        html = (RAIZ / "templates" / "workouts" / "ficha.html").read_text(encoding="utf-8")
        self.assertNotIn("até 40 min", html)
        self.assertIn("rapida_minutos_min", html)
        self.assertIn("rapida_minutos_max", html)


class TetoNaHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def _home_de(self, faixa):
        user = create_complete_user(email="teto-%s@exemplo.com" % faixa, duracao_treino=faixa)
        self.client.force_login(user)
        return self.client.get(reverse("plans:today")).content.decode()

    def test_quem_e_sem_limite_tambem_le_o_teto(self):
        """"até {{ teto }} min" era só para quem tinha teto; sem limite lia
        nada — e desde 15/09/2026 essa pessoa tem a sessão de até 65."""
        self.assertIn("até 65 min", self._home_de(DuracaoTreino.LIVRE))
        self.assertIn("até 65 min", self._home_de(DuracaoTreino.COMPLETO))
        self.assertIn("até 60 min", self._home_de(DuracaoTreino.PADRAO))
        self.assertIn("até 30 min", self._home_de(DuracaoTreino.RAPIDO))


class SeletorDaRapidaTests(TestCase):
    """O seletor Completo/Rápido diz a faixa CALCULADA das opções."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_a_rapida_mostra_a_faixa_das_opcoes(self):
        from django.utils import timezone

        user = create_complete_user(
            email="rapida@exemplo.com", experiencia="intermediario",
            split_preference="two", split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
        )
        TrainingDay.objects.filter(user=user).delete()
        hoje = timezone.localdate().weekday()
        for d in {hoje, (hoje + 2) % 7, (hoje + 4) % 7}:
            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
        plan = services.create_routine(user)
        sessao = plan.sessions.get(weekday=hoje)
        self.client.force_login(user)
        resposta = self.client.get(reverse("workouts:ficha", args=[sessao.pk]))
        html = resposta.content.decode()
        self.assertIn("rapida_minutos_min", resposta.context)
        self.assertIn("rapida_minutos_max", resposta.context)
        if resposta.context["rapida_muda"]:
            minimo, maximo = resposta.context["rapida_minutos_min"], resposta.context["rapida_minutos_max"]
            self.assertLessEqual(minimo, maximo)
            self.assertLessEqual(maximo, opcoes.TETO_RAPIDO_MIN)
            self.assertIn("~%d–%d min" % (minimo, maximo) if minimo != maximo else "~%d min" % maximo, html)
        self.assertNotIn("até 40 min", html)
