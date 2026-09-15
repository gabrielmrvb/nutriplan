# -*- coding: utf-8 -*-
"""A instrução de esforço volta à execução — por série e por nível.

`PrescriptionFields.intensidade` sempre soube dizer quão perto da falha levar
cada série ("1 a 2 na reserva" no composto, "até a falha" no isolador). Era
renderizada no cartão do exercício e SAIU da tela no redesenho de 12/09/2026
(`128aa1b`) sem constar na lista do que "mudou de lugar" — a pesquisa de
13/09 achou zero ocorrências em `templates/`. É a pergunta que o CLAUDE.md
manda fazer a toda tela encolhida — "para onde vai o que estou tirando?" —
sem resposta.

Volta com duas coisas que o texto antigo não tinha, e as duas vêm da
literatura de proximidade da falha (Refalo 2023/2024, Helms 2016):

- o ISOLADOR só vai à falha na ÚLTIMA série; nas anteriores fica com 1 a 2 na
  reserva — falhar em toda série custa fadiga sem estímulo a mais;
- o INICIANTE nunca lê "até a falha" em movimento composto, e para com 2
  sobrando: em quem está aprendendo o movimento, técnica vale mais que a
  última repetição.

`experiencia == ""` é "ainda não respondeu" e recebe o texto do
intermediário — o mesmo critério de `teto_semanal_de`. A tela nunca afirma um
nível que a pessoa não declarou.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Experiencia, Profile
from workouts import services
from workouts.models import Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


class _Item:
    """Só o que `instrucao_de_esforco` lê de um `SessionExercise`."""

    def __init__(self, composto, sets=3, measure=Measure.REPS):
        self.sets = sets
        self.measure = measure

        class _Ex:
            is_compound = composto

        self.exercise = _Ex()


class AInstrucaoDeEsforcoTests(TestCase):
    def test_composto_para_o_intermediario_pede_um_a_dois_na_reserva(self):
        texto = services.instrucao_de_esforco(_Item(True), 1, Experiencia.INTERMEDIARIO)
        self.assertIn("1 a 2 repetições na reserva", texto)

    def test_composto_para_o_iniciante_pede_duas_sobrando_e_nunca_a_falha(self):
        texto = services.instrucao_de_esforco(_Item(True), 1, Experiencia.INICIANTE)
        self.assertIn("2 sobrando", texto)
        self.assertNotIn("falha", texto)

    def test_isolador_so_vai_a_falha_na_ultima_serie(self):
        primeira = services.instrucao_de_esforco(_Item(False, sets=3), 1, Experiencia.INTERMEDIARIO)
        ultima = services.instrucao_de_esforco(_Item(False, sets=3), 3, Experiencia.INTERMEDIARIO)
        self.assertIn("reserva", primeira)
        self.assertIn("última série", primeira)
        self.assertIn("até a falha", ultima)

    def test_segundos_falam_de_tecnica_e_nao_de_repeticao(self):
        texto = services.instrucao_de_esforco(
            _Item(False, measure=Measure.SECONDS), 2, Experiencia.INTERMEDIARIO
        )
        self.assertIn("técnica", texto)
        self.assertNotIn("falha", texto)
        self.assertNotIn("reserva", texto)

    def test_quem_nao_respondeu_a_experiencia_le_o_texto_do_intermediario(self):
        """A tela não afirma nível não declarado — nem para mais, nem para menos."""
        self.assertEqual(
            services.instrucao_de_esforco(_Item(True), 1, ""),
            services.instrucao_de_esforco(_Item(True), 1, Experiencia.INTERMEDIARIO),
        )

    def test_a_property_antiga_continua_respondendo_sem_serie(self):
        """`intensidade` segue existindo para quem a lê sem contexto de série."""
        from workouts.models import Exercise, SessionExercise

        item = SessionExercise(
            sets=3, rep_min=6, rep_max=10,
            exercise=Exercise(name="Supino", muscle_group="chest", is_compound=True),
        )
        self.assertIn("reserva", item.intensidade)
        self.assertNotIn("Última", item.intensidade)


class AInstrucaoApareceNaExecucaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(
            email="esforco@exemplo.com", weekdays=dias_incluindo_hoje(5)
        )
        Profile.objects.filter(user=self.pessoa).update(
            experiencia=Experiencia.INICIANTE
        )
        # RECARREGADA DO BANCO: `Profile` fica em cache no objeto, e a ficha
        # montada com o perfil velho seria remontada na primeira visita —
        # levando junto a escolha do dia, que aponta para a sessão antiga.
        self.pessoa = type(self.pessoa).objects.get(pk=self.pessoa.pk)
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        # A execução abre a opção ESCOLHIDA de hoje (15/09/2026).
        escolher_opcao_de_hoje(self.pessoa)

    def _execucao(self, item):
        url = "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        return sem_scripts(self.client.get(url).content.decode())

    def _sessao_de_hoje(self):
        plano = services.get_active_routine(self.pessoa)
        hoje = timezone.localdate().weekday()
        return next(s for s in plano.sessions.all() if s.weekday == hoje)

    def test_a_execucao_mostra_a_instrucao_da_serie_da_vez(self):
        """Ancorado na classe com aspas: a frase muda com a série, e o teste
        precisa achar o bloco, não a palavra."""
        # Da opção ESCOLHIDA (a 1): a execução recusa exercício que só está
        # na outra versão da letra.
        composto = next(
            i for i in self._sessao_de_hoje().da_opcao(1)
            if i.exercise.is_compound
        )
        html = self._execucao(composto)
        self.assertIn('class="series__esforco"', html)
        bloco = html.split('class="series__esforco"', 1)[1].split("</p>", 1)[0]
        # Iniciante em composto: duas sobrando, nunca "falha".
        self.assertIn("2 sobrando", bloco)
        self.assertNotIn("falha", bloco)

    def test_toda_instrucao_cabe_numa_linha_a_320px(self):
        """Medido no navegador em 13/09/2026: a 320px cabem ~44 caracteres
        de 12,8px na coluna. Cada linha a mais empurra "Concluir série" para
        baixo — e a 320×568 o botão já nasce atrás da barra. A régua é o
        comprimento, que o teste consegue medir; a altura foi conferida à mão."""
        from workouts.models import Measure

        casos = [
            (_Item(True), 1, Experiencia.INICIANTE),
            (_Item(True), 1, Experiencia.INTERMEDIARIO),
            (_Item(False, sets=3), 1, Experiencia.AVANCADO),
            (_Item(False, sets=3), 3, Experiencia.AVANCADO),
            (_Item(False, measure=Measure.SECONDS), 1, ""),
        ]
        for item, serie, nivel in casos:
            with self.subTest(serie=serie, nivel=nivel):
                self.assertLessEqual(len(services.instrucao_de_esforco(item, serie, nivel)), 44)
