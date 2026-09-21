"""Cada regra do `docs/briefs/treino/TREINO.md` tem um teste que LÊ o
documento do disco e cobra o gerador — como `config/test_design_system.py`
cobra o `DESIGN.md` (17/09/2026).

Duas metades. A primeira prova que `workouts/doutrina.py` devolve o que
está escrito (o leitor não inventa). A segunda prova que a ficha gerada
obedece: exercícios por grupo, séries por exercício, séries diretas por
sessão, teto semanal por frequência, descanso, ordem e duração — sobre o
perfil de referência do brief (intermediário, 5 dias, abc2) com Completo,
onde nada é cortado pelo relógio, e sobre os outros níveis onde a regra
não depende do corte.
"""
import re
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import WorkoutTemplate

RAIZ = Path(__file__).resolve().parent.parent
DOC = RAIZ / "docs" / "briefs" / "treino" / "TREINO.md"


def _linhas_da_tabela(texto, cabecalho):
    """As linhas de uma tabela do documento, por um segundo parser — regex
    e não o de `doutrina` — para o teste não confiar no que ele testa."""
    bloco = re.search(re.escape(cabecalho) + r"\n\|[-|: ]+\|\n((?:\|.*\|\n?)+)", texto)
    assert bloco, "tabela não encontrada: %s" % cabecalho
    return [
        [c.strip() for c in linha.strip().strip("|").split("|")]
        for linha in bloco.group(1).strip().splitlines()
    ]


def _faixa(texto):
    partes = [int(p) for p in re.split(r"\s*[–\-]\s*", texto.strip())]
    return (partes[0], partes[-1])


class OLeitorDevolveOQueEstaEscritoTests(SimpleTestCase):
    def setUp(self):
        self.texto = DOC.read_text(encoding="utf-8")

    def test_tabela_a_por_sessao(self):
        linhas = _linhas_da_tabela(
            self.texto,
            "| nivel | tipo_de_dia | exercicios_grande | exercicios_pequeno | series_por_exercicio | series_diretas | duracao_min |",
        )
        self.assertEqual(len(linhas), 18)
        for nivel, tipo, grande, pequeno, por_exercicio, diretas, duracao in linhas:
            with self.subTest(nivel=nivel, tipo=tipo):
                self.assertEqual(doutrina.exercicios_por_grupo(nivel, tipo), (int(grande), int(pequeno)))
                self.assertEqual(doutrina.faixa_de_series(nivel, tipo), _faixa(diretas))
                self.assertEqual(doutrina.duracao_esperada(nivel, tipo), _faixa(duracao))
        self.assertEqual({l[0] for l in linhas}, set(doutrina.NIVEIS))
        self.assertEqual({l[1] for l in linhas}, set(doutrina.TIPOS_DE_DIA))

    def test_tabela_b_por_semana(self):
        linhas = _linhas_da_tabela(self.texto, "| nivel | ocorrencias | series_diretas_semana | teto_efetivo |")
        self.assertEqual(len(linhas), 9)
        for nivel, ocorrencias, diretas, teto in linhas:
            with self.subTest(nivel=nivel, ocorrencias=ocorrencias):
                self.assertEqual(doutrina.faixa_semanal_direta(nivel, int(ocorrencias)), _faixa(diretas))
                self.assertEqual(doutrina.teto_semanal(nivel, int(ocorrencias)), int(teto))
        # O teto cresce com a frequência, em todo nível — é a tese do documento.
        for nivel in doutrina.NIVEIS:
            self.assertLess(doutrina.teto_semanal(nivel, 1), doutrina.teto_semanal(nivel, 2))
            self.assertLess(doutrina.teto_semanal(nivel, 2), doutrina.teto_semanal(nivel, 3))

    def test_tabela_c_descanso(self):
        linhas = _linhas_da_tabela(self.texto, "| tipo | descanso_s |")
        self.assertEqual({l[0]: int(l[1]) for l in linhas}, {"composto": doutrina.descanso(True), "isolador": doutrina.descanso(False)})

    def test_quem_nao_respondeu_treina_como_intermediario(self):
        self.assertEqual(doutrina.faixa_de_series("", doutrina.DOIS_GRUPOS), doutrina.faixa_de_series("intermediario", doutrina.DOIS_GRUPOS))
        self.assertEqual(doutrina.teto_semanal(None, 1), doutrina.teto_semanal("intermediario", 1))

    def test_mapa_de_equipamento(self):
        """O mapa dos quatro perfis está escrito no documento, nas chaves de
        `Exercise.equipment`, e é o que `doutrina.equipamentos_de` devolve."""
        from workouts.models import Equipment

        linhas = _linhas_da_tabela(self.texto, "| perfil | equipamentos |")
        mapa = {perfil: {e.strip() for e in equipamentos.split(",")} for perfil, equipamentos in linhas}
        self.assertEqual(set(mapa), set(doutrina.PERFIS_DE_EQUIPAMENTO))
        for perfil, equipamentos in mapa.items():
            with self.subTest(perfil=perfil):
                self.assertTrue(equipamentos <= set(Equipment.values), equipamentos)
                self.assertEqual(doutrina.equipamentos_de(perfil), frozenset(equipamentos))
        self.assertEqual(mapa["completa"], set(Equipment.values))
        self.assertEqual(mapa["peso_corporal"], {"bodyweight"})

    def test_o_documento_cita_as_fontes(self):
        for fonte in ("Schoenfeld", "Israetel", "Helms"):
            self.assertIn(fonte, self.texto)


def _plano(nivel, dias, preferencia, duracao):
    user = create_complete_user(
        email="treino-md-%s-%s-%s-%s@exemplo.com" % (nivel, dias, preferencia, duracao),
        experiencia=nivel, split_preference=preferencia, split_preference_confirmada=True,
        duracao_treino=duracao,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return services.create_routine(user)


#: Panturrilha e core são complementares em todo tipo de dia (TREINO.md,
#: "Tipos de dia"): a cota de pequeno não vale para eles — no máximo dois.
COMPLEMENTARES_SEMPRE = ("calves", "core")


def _cotas(main_groups, tipo):
    """`([(grupos que somam a cota do grande)], [(grupos que somam uma cota
    de pequeno)])`, pelas regras do documento: em `dois_grupos` quadríceps e
    posterior dividem a cota do grande; em `tres_grupos` antebraço e trapézio
    dividem a cota do segundo pequeno; em "Braços" o tríceps faz de grande."""
    anunciados = list(main_groups)
    pernas = [g for g in anunciados if g in ("quads", "hamstrings", "glutes")]
    if "quads" in pernas and "hamstrings" in pernas:
        # Quadríceps, posterior e glúteo dividem a cota do grande, em
        # qualquer tipo (o glúteo desde 21/09/2026: um exercício anunciado
        # que a elevação pélvica já ocupava como "posterior").
        grandes = [tuple(pernas)]
        pequenos = [(g,) for g in anunciados if g not in pernas]
        return grandes, pequenos
    grandes_soltos = [g for g in anunciados if g in ("chest", "back", "quads", "hamstrings", "shoulders")]
    if not grandes_soltos:
        # "Braços": bíceps e tríceps são os dois pequenos (TREINO.md).
        return [], [(g,) for g in anunciados]
    grande = grandes_soltos[0]
    # Posterior e glúteo dividem a cota do grande quando o quadríceps não
    # está ("Complementares" do ABCD): a elevação pélvica sempre foi contada
    # ali como posterior.
    cota_do_grande = (grande, "glutes") if grande == "hamstrings" and "glutes" in anunciados else (grande,)
    pequenos = [(g,) for g in anunciados if g not in cota_do_grande and g not in ("forearms", "traps")]
    if "forearms" in anunciados and "traps" in anunciados:
        pequenos.append(("forearms", "traps"))
    elif "forearms" in anunciados or "traps" in anunciados:
        pequenos.append(tuple(g for g in ("forearms", "traps") if g in anunciados))
    return [cota_do_grande], pequenos


class OGeradorObedeceAoDocumentoTests(TestCase):
    """Perfil de referência do brief com Completo (teto 90): nada é cortado
    pelo relógio, então cada número da tabela A é cobrado literalmente."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        cls.plano = _plano("intermediario", 5, "two", DuracaoTreino.COMPLETO)
        cls.letras = {}
        for sessao in cls.plano.sessions.prefetch_related("exercises__exercise").order_by("order"):
            cls.letras.setdefault(sessao.label, sessao)

    def _tipo(self, sessao):
        return doutrina.tipo_de_dia(self.plano.split, sessao.label)

    def test_exercicios_por_grupo_anunciado(self):
        for letra, sessao in self.letras.items():
            tipo = self._tipo(sessao)
            grande_min, pequeno_min = doutrina.exercicios_por_grupo("intermediario", tipo)
            grandes, pequenos = _cotas(sessao.main_groups, tipo)
            for k in sessao.opcoes:
                itens = sessao.da_opcao(k)
                por_grupo = {}
                for item in itens:
                    por_grupo[item.exercise.muscle_group] = por_grupo.get(item.exercise.muscle_group, 0) + 1
                with self.subTest(letra=letra, opcao=k, por_grupo=por_grupo):
                    for cota in grandes:
                        self.assertGreaterEqual(sum(por_grupo.get(g, 0) for g in cota), grande_min, cota)
                    for cota in pequenos:
                        minimo = min(pequeno_min, 2) if set(cota) <= set(COMPLEMENTARES_SEMPRE) else pequeno_min
                        self.assertGreaterEqual(sum(por_grupo.get(g, 0) for g in cota), minimo, cota)

    def test_series_por_exercicio(self):
        """Todo exercício dentro da faixa do nível — com UMA exceção dita no
        documento: o isolador de um grupo que bateu no teto semanal pode
        ficar em 2, o piso do aparo. É o ombro de "Pernas e ombros" a 2×
        com o secundário de todos os supinos e remadas; abaixo de 3 sem o
        grupo estar no teto seria defeito."""
        piso, teto = doutrina.series_por_exercicio("intermediario")
        efetivo = services.volume_da_semana(self.plano)
        tetos = services.tetos_da_semana(self.plano)
        for letra, sessao in self.letras.items():
            for k in sessao.opcoes:
                for item in sessao.da_opcao(k):
                    grupo = item.exercise.muscle_group
                    with self.subTest(letra=letra, opcao=k, exercicio=item.exercise.name, series=item.sets):
                        self.assertLessEqual(item.sets, teto)
                        if item.sets < piso:
                            self.assertFalse(item.exercise.is_compound, "composto abaixo do piso")
                            self.assertGreaterEqual(item.sets, 2, "abaixo do piso do aparo")
                            self.assertGreaterEqual(
                                efetivo[grupo], tetos[grupo] - 1,
                                "isolador em 2 sem o grupo estar no teto semanal",
                            )

    def test_series_diretas_por_sessao(self):
        """Dos grupos ANUNCIADOS (`main_groups`) — o complementar não
        anunciado fica fora da soma, como no teste dourado; a panturrilha
        conta onde o nome a promete ("Pernas completo")."""
        for letra, sessao in self.letras.items():
            piso, teto = doutrina.faixa_de_series("intermediario", self._tipo(sessao))
            anunciados = set(sessao.main_groups)
            for k in sessao.opcoes:
                series = sum(i.sets for i in sessao.da_opcao(k) if i.exercise.muscle_group in anunciados)
                with self.subTest(letra=letra, opcao=k, series=series):
                    self.assertGreaterEqual(series, piso)
                    self.assertLessEqual(series, teto)

    def test_duracao_esperada(self):
        for letra, sessao in self.letras.items():
            piso, teto = doutrina.duracao_esperada("intermediario", self._tipo(sessao))
            for k in sessao.opcoes:
                minutos = sessao.minutos_da_opcao(k)
                with self.subTest(letra=letra, opcao=k, minutos=minutos):
                    self.assertGreaterEqual(minutos, piso)
                    self.assertLessEqual(minutos, teto)

    def test_teto_semanal_por_frequencia(self):
        """Tabela B: o pior caso da semana (cada ocorrência na opção mais
        pesada) cabe no teto efetivo da FREQUÊNCIA do grupo."""
        from workouts.tests import excesso_e_irredutivel

        efetivo = services.volume_da_semana(self.plano)
        tetos = services.tetos_da_semana(self.plano)
        for grupo, volume in efetivo.items():
            with self.subTest(grupo=grupo, volume=volume, teto=tetos.get(grupo)):
                if volume <= tetos[grupo]:
                    continue
                irredutivel, evidencia = excesso_e_irredutivel(self.plano, grupo)
                self.assertTrue(irredutivel, "%s em %s (teto %s) tendo o que ceder: %s" % (grupo, volume, tetos[grupo], evidencia))

    def test_composto_principal_primeiro(self):
        for letra, sessao in self.letras.items():
            for k in sessao.opcoes:
                primeiro = sessao.da_opcao(k)[0]
                with self.subTest(letra=letra, opcao=k):
                    self.assertTrue(primeiro.exercise.is_compound, primeiro.exercise.name)


class ADoseDoNivelValeEmTodoNivelTests(TestCase):
    """Tabela A, coluna `series_por_exercicio`, nos TRÊS níveis: o iniciante
    faz 2 a 3 — o supino de quatro do catálogo vira três para ele —, e o
    avançado 3 a 4. Cobrado nos anunciados de toda letra com Completo, onde
    o relógio não interfere. Sem este teste, tirar o teto por exercício do
    nível de `preencher_ate_a_faixa` passava pelo teste dourado (a descida
    até o topo da faixa compensava nas séries dos isoladores)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_series_por_exercicio_por_nivel(self):
        for nivel in doutrina.NIVEIS:
            piso, teto = doutrina.series_por_exercicio(nivel)
            plano = _plano(nivel, 5, "two", DuracaoTreino.COMPLETO)
            efetivo = services.volume_da_semana(plano)
            tetos = services.tetos_da_semana(plano)
            for sessao in plano.sessions.prefetch_related("exercises__exercise"):
                anunciados = set(sessao.main_groups)
                for k in sessao.opcoes:
                    for item in sessao.da_opcao(k):
                        grupo = item.exercise.muscle_group
                        if grupo not in anunciados:
                            continue
                        with self.subTest(nivel=nivel, letra=sessao.label, opcao=k, exercicio=item.exercise.name, series=item.sets):
                            self.assertLessEqual(item.sets, teto)
                            if item.sets < piso:
                                # A exceção do aparo (ver `test_series_por_exercicio`).
                                self.assertFalse(item.exercise.is_compound)
                                self.assertGreaterEqual(item.sets, 2)
                                self.assertGreaterEqual(efetivo[grupo], tetos[grupo] - 1)
        # Controle positivo: os níveis pedem coisas diferentes.
        self.assertNotEqual(doutrina.series_por_exercicio("iniciante"), doutrina.series_por_exercicio("avancado"))


class OCatalogoObedeceAoDescansoTests(TestCase):
    """Tabela C: composto descansa 80 s, isolador 60 s — em todo modelo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_descanso_por_tipo_em_todos_os_modelos(self):
        for modelo in WorkoutTemplate.objects.filter(is_active=True):
            for item in modelo.items.select_related("exercise"):
                with self.subTest(modelo=str(modelo), exercicio=item.exercise.name):
                    self.assertEqual(item.rest_seconds, doutrina.descanso(item.exercise.is_compound))
