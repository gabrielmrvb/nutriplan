"""A política do convite de instalação, guardada nos dois lados.

O convite aparecia em toda página, e "Agora não" fazia a mesma coisa que o "×":
dispensava para sempre. Um "não agora" virava decisão definitiva que a pessoa
não tomou.

O QUE ESTE ARQUIVO GUARDA:

  - no SERVIDOR, quais telas se declaram críticas (`sem_convite`) e quais não —
    isso é testável de verdade, com requisição e HTML;
  - no CLIENTE, a forma da política em `static/js/pwa.js`. São asserções
    ESTRUTURAIS e estão declaradas como tais: não existe Node neste ambiente,
    então o comportamento do JavaScript não roda aqui. O que elas impedem é a
    regra sumir do arquivo sem ninguém notar.

Por que o marcador vem do servidor e não de uma lista de URLs no JavaScript: o
demo serve as MESMAS telas sob outro prefixo (`/demo/treino/agora/`), e uma
regex de caminho quebraria lá em silêncio. Quem sabe em que tela a pessoa está
é a view.
"""
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import (
    ActivityLevel,
    Goal,
    ONBOARDING_DONE,
    Profile,
    Sex,
    TrainingDay,
    WeightEntry,
)

User = get_user_model()
PWA_JS = Path(settings.BASE_DIR) / "static" / "js" / "pwa.js"


def pessoa(email="convite@exemplo.com"):
    user = User.objects.create_user(email=email, password="x8Kd2Lm9Qp4z")
    Profile.objects.create(
        user=user,
        sex=Sex.MALE,
        birth_date=date(1995, 4, 12),
        height_cm=178,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.BULK,
        wake_time=time(7, 0),
        sleep_time=time(23, 0),
        onboarding_step=ONBOARDING_DONE,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal("82.4"))
    from django.utils import timezone

    TrainingDay.objects.create(
        user=user,
        weekday=timezone.localdate().weekday(),
        start_time=time(19, 0),
        duration_min=60,
    )
    return user


class AsTelasCriticasSeDeclaramTests(TestCase):
    """Execução de treino e corrida não recebem convite."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.client.force_login(pessoa())

    def marcador(self, nome):
        html = self.client.get(reverse(nome)).content.decode()
        return "data-sem-convite" in html

    def test_a_execucao_do_treino_e_critica(self):
        """A pessoa está de pé, entre uma série e outra. Um cartão fixo
        cobrindo o rodapé atrapalha a tarefa que ela foi fazer."""
        self.assertTrue(self.marcador("workouts:now"))

    def test_a_corrida_e_critica(self):
        """Cronômetro na tela e aparelho no bolso."""
        self.assertTrue(self.marcador("workouts:corridas"))

    def test_as_telas_COMUNS_continuam_podendo_convidar(self):
        """Controle positivo, e ele é o que impede a correção de virar
        "nunca convide": se todas as telas fossem críticas, o convite estaria
        desligado e este arquivo passaria dizendo que a política funciona."""
        for nome in ("plans:today", "workouts:routine", "plans:history"):
            with self.subTest(tela=nome):
                self.assertFalse(
                    self.marcador(nome), "%s virou tela crítica sem motivo" % nome
                )


class AFormaDaPoliticaNoClienteTests(TestCase):
    """Asserções ESTRUTURAIS sobre `pwa.js`. Sem Node, não há execução aqui.

    O que elas guardam é a regra não sumir do arquivo. O comportamento foi
    verificado no navegador; isto impede a regressão silenciosa.
    """

    def setUp(self):
        self.js = PWA_JS.read_text(encoding="utf-8")

    def test_agora_nao_ADIA_e_o_x_dispensa(self):
        """Os dois usavam o mesmo gancho e faziam a mesma coisa."""
        self.assertIn("data-install-later", self.js)
        self.assertIn("data-install-close", self.js)
        self.assertIn("function adiar()", self.js)
        self.assertIn("function dispensar()", self.js)

    def test_o_adiamento_fica_entre_sete_e_trinta_dias(self):
        """A campanha define a faixa. Trinta é o teto dela, e perto do teto de
        propósito: a decisão anterior deste arquivo tornou a dispensa
        definitiva porque "um convite que reaparece é um convite que a pessoa
        já respondeu" — adiar pouco reintroduziria a insistência."""
        import re

        achado = re.search(r"DIAS_DE_ADIAMENTO\s*=\s*(\d+)", self.js)

        self.assertIsNotNone(achado, "sumiu a constante do adiamento")
        dias = int(achado.group(1))
        self.assertGreaterEqual(dias, 7)
        self.assertLessEqual(dias, 30)

    def test_o_convite_nao_aparece_em_tela_critica_nem_com_dialogo_aberto(self):
        self.assertIn("data-sem-convite", self.js)
        self.assertIn('dialog[open]', self.js)
        self.assertIn("horaRuim()", self.js)

    def test_mostrar_confere_TODAS_as_condicoes(self):
        """A guarda que impede alguém de acrescentar uma condição e esquecer de
        ligá-la: elas moram numa linha só, e o teste lê essa linha."""
        import re

        # Recorte até o `return;`, e não `[^)]*`: a linha tem `dispensado()`,
        # `adiado()` e `horaRuim()`, então parar no primeiro parêntese fechado
        # corta a condição no meio e o teste não acha nada.
        achado = re.search(r"if \(jaInstalado\(\)(.*?)\) return;", self.js, re.S)

        self.assertIsNotNone(achado, "a linha de condições de `mostrar` mudou de forma")
        condicoes = achado.group(1)
        for condicao in ("dispensado()", "adiado()", "horaRuim()"):
            with self.subTest(condicao=condicao):
                self.assertIn(condicao, condicoes)

    def test_o_botao_de_instalar_some_sem_evento(self):
        """`beforeinstallprompt` é de uso único: depois de `prompt()` o objeto
        deixa de valer. Um cartão reaparecendo nesse estado teria um botão que
        não faz nada — pior que não ter botão, porque parece app quebrado."""
        self.assertIn("instalar.hidden = !convite", self.js)

    def test_o_convite_continua_lendo_as_chaves_ANTIGAS(self):
        """Controle de regressão de uma correção anterior: trocar o nome da
        chave não pode ressuscitar o convite para quem já disse não."""
        self.assertIn("CHAVES_ANTIGAS", self.js)

    def test_quem_ja_instalou_nunca_ve_o_convite(self):
        self.assertIn("display-mode: standalone", self.js)
        self.assertIn("jaInstalado()", self.js)

    def test_o_adiamento_ignora_relogio_absurdo(self):
        """Relógio de aparelho anda para trás, e uma data absurdamente no
        futuro esconderia o convite para sempre. Errar mostrando é melhor que
        errar sumindo."""
        self.assertIn("ate <= teto", self.js)
