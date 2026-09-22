"""O iniciante que treina só com o peso do corpo começa pelo degrau mais
fácil da escada — nunca pelas paralelas.

Achado #5 das personas (21/09/2026): a iniciante de 78 kg, "só o peso do
corpo", recebeu na letra A quatro variações de flexão mais MERGULHO NAS
PARALELAS (degrau 4 de 4, e não há paralelas em casa); a leitura já
mostrava a escada com "você está aqui", mas a ficha a punha no topo dela.
A doutrina do `TREINO.md` continua: o iniciante faz os MESMOS movimentos —
a flexão continua flexão —, só que no degrau em que consegue fazer.

A régua (`services.ajustar_degrau_do_iniciante`): só para `iniciante` e só
quando o perfil é `peso_corporal`; cada item com `progressao` acima do
degrau 2 é trocado pelo degrau mais baixo do MESMO movimento e grupo que
ainda não esteja na lista, com a dose do item trocado. Sem degrau livre
mais baixo, o item fica — quatro flexões numa letra viram duas fáceis e
duas normais, e é assim que a escada existe. O gerador e a conferência
(`_prescricao_bate`) aplicam a mesma régua: a ficha nova não nasce
"desatualizada".
"""
from django.core.management import call_command
from django.test import TestCase

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import services
from workouts.models import Exercise, SessionExercise


def _plano(experiencia, equipamento="peso_corporal", dias=5):
    """O perfil da persona: 5 dias, dois grupos por dia (abc2)."""
    user = create_complete_user(
        email="degrau-%s-%s@exemplo.com" % (experiencia, equipamento), experiencia=experiencia,
        split_preference="two", split_preference_confirmada=True,
        duracao_treino=DuracaoTreino.PADRAO, equipamento=equipamento,
    )
    user.training_days.all().delete()
    for weekday in range(dias):
        TrainingDay.objects.create(user=user, weekday=weekday, duration_min=60)
    return services.create_routine(user), user


class DegrauDoInicianteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _nomes(self, plano):
        return [i.exercise.name for i in SessionExercise.objects.filter(session__plan=plano).select_related("exercise")]

    def test_a_iniciante_de_peso_do_corpo_nao_recebe_as_paralelas(self):
        plano, user = _plano("iniciante")
        nomes = self._nomes(plano)
        self.assertNotIn("Mergulho nas paralelas", nomes)
        self.assertIn("Mergulho no banco", nomes)
        self.assertTrue(any("joelhos apoiados" in n for n in nomes), nomes)
        # e a ficha que acabou de nascer é a que o motor produziria hoje
        self.assertFalse(services.rotina_desatualizada(plano, user))

    def test_o_intermediario_continua_no_degrau_do_modelo(self):
        plano, _ = _plano("intermediario")
        self.assertIn("Mergulho nas paralelas", self._nomes(plano))

    def test_na_academia_completa_o_iniciante_nao_e_mexido(self):
        plano, _ = _plano("iniciante", equipamento="completa")
        nomes = self._nomes(plano)
        self.assertFalse(any("joelhos apoiados" in n for n in nomes), nomes)

    def test_a_troca_mantem_a_dose(self):
        dips = Exercise.objects.get(name="Mergulho nas paralelas")
        banco = Exercise.objects.get(name="Mergulho no banco")
        item = SessionExercise(exercise=dips, sets=3, rep_min=6, rep_max=10, rest_seconds=60, order=1)
        catalogo = services.catalogo_permitido({"bodyweight"})
        [trocado] = services.ajustar_degrau_do_iniciante([item], "iniciante", {"bodyweight"}, catalogo)
        self.assertEqual(trocado.exercise, banco)
        self.assertEqual((trocado.sets, trocado.rep_min, trocado.rep_max, trocado.rest_seconds), (3, 6, 10, 60))
