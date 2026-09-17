"""O TESTE DOURADO (17/09/2026): a sessão entregue parece uma ficha de academia.

Intermediário, 5 dias, `abc2`, duração Padrão → a letra A ("Peito e
tríceps") tem ≥ 6 exercícios (≥ 4 de peito, ≥ 2 de tríceps), 21–28 séries
diretas e 55–65 minutos NAS DUAS OPÇÕES; com Completo, 60–80 minutos. O
mesmo para 4 dias em ABC e 3 dias. Iniciante e avançado com os valores do
`docs/briefs/treino/TREINO.md`.

Este arquivo é IMUTÁVEL por decisão do dono: se não passar com o catálogo,
ajusta-se o motor ou pede-se mais catálogo — nunca se afrouxa o teste. Os
números vêm da ficha padrão de academia (4 de peito + 3 de tríceps, 3–4
séries, 60–75 minutos) e da literatura citada no TREINO.md.

E VALE POR PERFIL DE EQUIPAMENTO desde 17/09/2026 (`FichaDeVerdadePorEquipamentoTests`):
"completa", "básica" (sem barra livre) e "casa com halteres" têm de fechar
com os MESMOS números; "só peso do corpo" é medido e fica como
`expectedFailure` nomeado — com o déficit escrito e a lista do que falta ao
catálogo no `BACKLOG.md` — até o catálogo fechar. Nunca afrouxado.

ANTES desta missão (medido em 16/09/2026): 4 exercícios, 13 séries, ~36
minutos por opção — metade de uma ficha.
"""
from unittest import expectedFailure

from django.core.management import call_command
from django.test import TestCase

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import MuscleGroup

#: (nome, dias, preferência, tipo de dia da letra A) — as três frequências
#: do brief. "Peito, tríceps e ombro" (ABC) é `tres_grupos`; "Peito e
#: tríceps" (abc2) é `dois_grupos`.
PERFIS = (
    ("3d-abc", 3, "three", doutrina.TRES_GRUPOS),
    ("4d-abc", 4, "three", doutrina.TRES_GRUPOS),
    ("5d-abc2", 5, "two", doutrina.DOIS_GRUPOS),
)

#: O que o INTERMEDIÁRIO recebe na letra A, POR OPÇÃO — os números do dono,
#: literais, iguais nos três perfis.
#: exercícios: (mínimo total, mínimo de peito, mínimo de tríceps)
#: séries diretas: (mínimo, máximo)
#: minutos com Padrão (teto 60) e com Completo (teto 90).
INTERMEDIARIO = {"exercicios": (6, 4, 2), "series": (21, 28), "padrao": (55, 60), "completo": (60, 80)}

TETO_PADRAO_MIN = 60


def esperado(nivel, tipo):
    """Iniciante e avançado com os valores do TREINO.md para o tipo de dia
    da letra A; o intermediário com os do dono."""
    if nivel == "intermediario":
        return INTERMEDIARIO
    grande, pequeno = doutrina.exercicios_por_grupo(nivel, tipo)
    piso_min, teto_min = doutrina.duracao_esperada(nivel, tipo)
    return {
        "exercicios": (grande + pequeno, grande, pequeno),
        "series": doutrina.faixa_de_series(nivel, tipo),
        "padrao": (min(piso_min, TETO_PADRAO_MIN), min(teto_min, TETO_PADRAO_MIN)),
        "completo": (piso_min, teto_min),
    }


def _plano(nivel, dias, preferencia, duracao, sufixo, equipamento="completa"):
    user = create_complete_user(
        email="dourado-%s-%s-%s-%s-%s@exemplo.com" % (nivel, dias, preferencia, sufixo, equipamento),
        experiencia=nivel, split_preference=preferencia, split_preference_confirmada=True,
        duracao_treino=duracao, equipamento=equipamento,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return services.create_routine(user)


def _letra_a(plano):
    return next(s for s in plano.sessions.prefetch_related("exercises__exercise").order_by("order") if s.label == "A")


class ConfereAFicha:
    """A régua, uma só, para todo perfil de equipamento."""

    def _conferir(self, nivel, nome, dias, preferencia, tipo, duracao, chave_minutos, equipamento="completa"):
        plano = _plano(nivel, dias, preferencia, duracao, chave_minutos, equipamento)
        a = _letra_a(plano)
        alvo = esperado(nivel, tipo)
        minimo_total, minimo_peito, minimo_triceps = alvo["exercicios"]
        series_min, series_max = alvo["series"]
        minutos_min, minutos_max = alvo[chave_minutos]
        self.assertGreaterEqual(len(a.opcoes), 2, "%s %s: a letra A saiu com uma opção só" % (nivel, nome))
        for k in a.opcoes:
            itens = a.da_opcao(k)
            peito = [i for i in itens if i.exercise.muscle_group == MuscleGroup.CHEST]
            triceps = [i for i in itens if i.exercise.muscle_group == MuscleGroup.TRICEPS]
            series = sum(i.sets for i in itens)
            minutos = a.minutos_da_opcao(k)
            retrato = "%s %s %s %s opção %d: %d exercícios (%d peito, %d tríceps), %d séries, %d min — %s" % (
                equipamento, nivel, nome, chave_minutos, k, len(itens), len(peito), len(triceps), series, minutos,
                ", ".join("%s×%d" % (i.exercise.name, i.sets) for i in itens),
            )
            with self.subTest(retrato=retrato):
                self.assertGreaterEqual(len(itens), minimo_total, retrato)
                self.assertGreaterEqual(len(peito), minimo_peito, retrato)
                self.assertGreaterEqual(len(triceps), minimo_triceps, retrato)
                self.assertGreaterEqual(series, series_min, retrato)
                self.assertLessEqual(series, series_max, retrato)
                self.assertGreaterEqual(minutos, minutos_min, retrato)
                self.assertLessEqual(minutos, minutos_max, retrato)


class FichaDeVerdadeTests(ConfereAFicha, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_intermediario_recebe_uma_ficha_de_academia(self):
        for nome, dias, preferencia, tipo in PERFIS:
            self._conferir("intermediario", nome, dias, preferencia, tipo, DuracaoTreino.PADRAO, "padrao")
            self._conferir("intermediario", nome, dias, preferencia, tipo, DuracaoTreino.COMPLETO, "completo")

    def test_iniciante_recebe_a_ficha_do_nivel_dele(self):
        for nome, dias, preferencia, tipo in PERFIS:
            self._conferir("iniciante", nome, dias, preferencia, tipo, DuracaoTreino.PADRAO, "padrao")
            self._conferir("iniciante", nome, dias, preferencia, tipo, DuracaoTreino.COMPLETO, "completo")

    def test_avancado_recebe_a_ficha_do_nivel_dele(self):
        for nome, dias, preferencia, tipo in PERFIS:
            self._conferir("avancado", nome, dias, preferencia, tipo, DuracaoTreino.PADRAO, "padrao")
            self._conferir("avancado", nome, dias, preferencia, tipo, DuracaoTreino.COMPLETO, "completo")

    def test_os_perfis_sao_os_do_brief(self):
        """3 dias em ABC, 4 dias em ABC e 5 dias em abc2 — e a letra A de
        cada um é do tipo que o teste diz."""
        for nome, dias, preferencia, tipo in PERFIS:
            plano = _plano("intermediario", dias, preferencia, DuracaoTreino.PADRAO, "perfil")
            with self.subTest(nome=nome):
                self.assertEqual(plano.split, "abc2" if nome == "5d-abc2" else "abc")
                self.assertEqual(doutrina.tipo_de_dia(plano.split, "A"), tipo)


class FichaDeVerdadePorEquipamentoTests(ConfereAFicha, TestCase):
    """O dourado do intermediário, por perfil de equipamento (17/09/2026)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _intermediario(self, equipamento):
        for nome, dias, preferencia, tipo in PERFIS:
            self._conferir("intermediario", nome, dias, preferencia, tipo, DuracaoTreino.PADRAO, "padrao", equipamento)
            self._conferir("intermediario", nome, dias, preferencia, tipo, DuracaoTreino.COMPLETO, "completo", equipamento)

    def test_a_academia_basica_recebe_a_mesma_ficha_de_academia(self):
        """Sem barra livre, a letra A fecha com os mesmos números. O `abc2 A`
        perde três itens de barra sem substituto (o modelo já lista todas as
        pressões sem barra) — o catálogo precisou de peito e tríceps novos
        sem barra para as duas opções chegarem a sete exercícios."""
        self._intermediario("basica")

    def test_em_casa_com_halteres_a_letra_a_tambem_e_uma_ficha_de_academia(self):
        """Fechou em 17/09/2026 (tarde) com os cinco de peito e tríceps sem
        barra: de 4 exercícios por opção (2 peito), 14–15 séries e 34–39 min
        pela manhã para os números do dourado. O que entra é por
        substituição (supino reto → declinado com halteres, crucifixo na
        máquina → crucifixo inclinado com halteres, supino na máquina →
        flexão com pés elevados, tríceps testa → coice, supino fechado →
        flexão fechada); o que não tem substituto (crossover, corda) sai."""
        self._intermediario("casa_halteres")

    @expectedFailure
    def test_so_peso_do_corpo_ainda_nao_fecha_a_letra_a(self):
        """MEDIDO em 17/09/2026: sem aparelho nenhum a letra A tem 2–3
        exercícios (flexão de braço e mergulhos), uma opção só em ABC, 6–10
        séries, 20–30 min. Quadríceps, posterior, ombro, bíceps e panturrilha
        não têm exercício ativo sem aparelho (`test_experiencia`). A lista
        está no `BACKLOG.md`."""
        self._intermediario("peso_corporal")
