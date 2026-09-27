"""Recorde é o que SUPEROU uma data anterior — nas duas telas (24/09/2026).

A varredura de 24/09 mediu uma conta com UMA série (agachamento livre,
40 kg × 6) e achou duas telas dizendo coisas opostas sobre o mesmo dado:

- Progresso: "Seus recordes · Agachamento livre 40 kg × 6 · 24/09";
- Conquistas: "0 recordes".

As duas estavam certas dentro da própria definição — o Progresso listava a
carga MÁXIMA por exercício, e `achievements` só chama de recorde o que
passou de uma data anterior (`achievements/services.py`: "estreia não é
recorde") — e é por isso que a tela mentia: a palavra era a mesma e a régua
não.

Decisão do dono: a PRIMEIRA série não é recorde em lugar nenhum. A lista do
Progresso passa a se chamar "Melhores cargas" (título honesto: é a maior
carga de cada exercício, de sempre), e a palavra "recorde" só aparece na
linha que bateu uma data anterior — a mesma régua de `achievements`.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ONBOARDING_DONE, ActivityLevel, Goal, Profile, Sex
from plans import evolucao
from workouts.models import Exercise, ExerciseLog, MuscleGroup

User = get_user_model()


class RecordeEUmaMarcaTests(TestCase):
    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="melhores@exemplo.com", password="senha-bem-forte-123"
        )
        # A conta nasce antes dos dados: a tela não desenha nada anterior ao
        # cadastro, e histórico escrito para trás de uma conta de hoje é um
        # estado que a vida não produz.
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
        self.agacho = Exercise.objects.create(
            name="Agachamento livre",
            muscle_group=MuscleGroup.QUADS,
            is_compound=True,
            padrao="agachamento",
            equipment="barra",
        )
        self.hoje = timezone.localdate()

    def _serie(self, quando, carga, reps=6, exercicio=None):
        return ExerciseLog.objects.create(
            user=self.pessoa,
            exercise=exercicio or self.agacho,
            date=quando,
            set_number=1,
            weight_kg=Decimal(carga),
            reps=reps,
        )

    def _html(self):
        self.client.force_login(self.pessoa)
        return self.client.get(reverse("plans:history")).content.decode()

    # ------------------------------------------------- a primeira série
    def test_a_primeira_serie_nao_e_recorde_em_lugar_nenhum(self):
        """O achado, do jeito que ele apareceu: uma série, e as duas telas
        discordando. Depois desta correção nenhuma das duas escreve
        "recorde" — o Progresso mostra a melhor carga, que é verdade, e as
        Conquistas continuam em zero, que também é."""
        self._serie(self.hoje, "40")

        melhores = evolucao.recordes(self.pessoa)
        self.assertEqual(len(melhores), 1)
        self.assertEqual(melhores[0]["weight_kg"], Decimal("40"))
        self.assertFalse(
            melhores[0]["e_recorde"],
            "estreia não é recorde — a régua é a de achievements",
        )

        html = self._html()
        self.assertIn("Melhores cargas", html)
        self.assertIn("Agachamento livre", html)
        self.assertNotIn("Seus recordes", html)
        # A palavra só pode aparecer onde há marca de verdade.
        self.assertNotIn("recorde", html.split("Melhores cargas", 1)[1][:1200])

    # ------------------------------------------------- superou a data anterior
    def test_a_carga_que_passou_uma_data_anterior_e_recorde(self):
        """Segundo dia mais pesado: aí sim é marca. A linha ganha a palavra,
        e é a MESMA régua que `achievements` usa para desbloquear."""
        self._serie(self.hoje - timedelta(days=7), "40")
        self._serie(self.hoje, "45")

        melhores = evolucao.recordes(self.pessoa)
        self.assertEqual(melhores[0]["weight_kg"], Decimal("45"))
        self.assertTrue(melhores[0]["e_recorde"])

        html = self._html()
        linha = html.split("Agachamento livre", 1)[1].split("</li>", 1)[0]
        self.assertIn("recorde", linha)

    def test_repetir_a_mesma_carga_nao_vira_recorde(self):
        """Empatar não é superar. Sem isto, quem treina com a mesma anilha
        toda semana ganharia uma marca nova por semana."""
        self._serie(self.hoje - timedelta(days=7), "40")
        self._serie(self.hoje, "40")

        self.assertFalse(evolucao.recordes(self.pessoa)[0]["e_recorde"])

    def test_duas_series_no_mesmo_dia_nao_viram_recorde(self):
        """A régua é DATA anterior, não série anterior: subir a carga entre a
        primeira e a segunda série do mesmo treino é aquecimento, não marca —
        e `achievements` já lia assim (`date__lt`)."""
        self._serie(self.hoje, "40")
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.agacho, date=self.hoje,
            set_number=2, weight_kg=Decimal("45"), reps=6,
        )

        melhores = evolucao.recordes(self.pessoa)
        self.assertEqual(melhores[0]["weight_kg"], Decimal("45"))
        self.assertFalse(melhores[0]["e_recorde"])

    # ------------------------------------------------- as duas telas juntas
    def test_as_duas_telas_contam_a_mesma_historia(self):
        """O cruzamento que o achado pede: o que o Progresso chama de recorde
        é o que as Conquistas contam. Com uma série, zero dos dois lados."""
        self._serie(self.hoje, "40")

        marcas_no_progresso = sum(
            1 for linha in evolucao.recordes(self.pessoa) if linha["e_recorde"]
        )
        self.client.force_login(self.pessoa)
        conquistas = self.client.get(reverse("achievements:list"))
        self.assertEqual(marcas_no_progresso, 0)
        self.assertEqual(conquistas.context["recordes"], 0)

    # ------------------------------------------------- o custo não muda
    def test_a_lista_continua_custando_uma_consulta(self):
        """`DISTINCT ON` com um `Exists` anotado continua sendo UMA consulta —
        a marca viaja na mesma linha. Duas consultas aqui apareceriam no teto
        de `plans:history`, que é medido."""
        self._serie(self.hoje - timedelta(days=7), "40")
        self._serie(self.hoje, "45")

        with self.assertNumQueries(1):
            list(evolucao.recordes(self.pessoa))


class OTileDeTreinoDizPrevistosTests(TestCase):
    """"2 dias combinados no período" — "combinado" é palavra de contrato, e
    a pessoa não combinou nada com ninguém: ela DECLAROU os dias no cadastro.
    Achado 7b da varredura de 24/09/2026."""

    def test_o_tile_fala_de_dias_previstos(self):
        mapa = [
            evolucao.DiaDoMapa(data=date(2026, 9, 21), estado=evolucao.FEITO),
            evolucao.DiaDoMapa(data=date(2026, 9, 23), estado=evolucao.FALTOU),
        ]
        tile = evolucao.tile_de_treino(mapa, {0, 2})

        self.assertIn("previstos", tile.frase)
        self.assertNotIn("combinado", tile.frase)

    def test_sem_dia_previsto_a_frase_tambem_muda(self):
        tile = evolucao.tile_de_treino([], set())

        self.assertIn("previsto", tile.frase)
        self.assertNotIn("combinado", tile.frase)
