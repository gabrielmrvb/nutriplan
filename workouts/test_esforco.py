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

T2.2 (17/09/2026), do plano mestre: a ÚLTIMA série de composto com faixa
curta (`rep_max` até 12) diz "mesmo passando de N" — a faixa é alvo de
progressão, não teto (Helms 2016: quem chega em 10 com 1 a 2 sobrando faz
11) —, e quem tem 65 anos ou mais (`cauteloso`) nunca lê "falha", nem no
isolador (Fragala 2019, NSCA).
"""
from datetime import date

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Experiencia, Profile
from workouts import services
from workouts.models import IDADE_CAUTELOSA, REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


class _Item:
    """Só o que `instrucao_de_esforco` lê de um `SessionExercise`."""

    def __init__(self, composto, sets=3, measure=Measure.REPS, rep_max=12):
        self.sets = sets
        self.measure = measure
        self.rep_max = rep_max

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

    def test_a_ultima_serie_do_composto_com_faixa_curta_diz_que_a_faixa_nao_e_teto(self):
        """Faixa 6–10 na última série do supino: quem chega em 10 com 1 a 2
        sobrando NÃO para em 10 — o número é orientação, o RIR governa."""
        texto = services.instrucao_de_esforco(_Item(True, sets=3, rep_max=10), 3, Experiencia.INTERMEDIARIO)
        self.assertIn("mesmo passando de 10", texto)
        self.assertIn("1 a 2 sobrando", texto)
        self.assertNotIn("falha", texto)

    def test_a_serie_que_nao_e_a_ultima_nao_fala_de_passar_da_faixa(self):
        """Nas séries anteriores a faixa continua sendo a régua: passar dela
        na primeira série é carga leve, não progressão."""
        texto = services.instrucao_de_esforco(_Item(True, sets=3, rep_max=10), 1, Experiencia.INTERMEDIARIO)
        self.assertNotIn("mesmo passando", texto)
        self.assertIn("1 a 2 repetições na reserva", texto)

    def test_com_faixa_longa_o_aviso_de_passar_nao_entra(self):
        """A 15 ou 20 repetições a faixa já é longa: "mesmo passando de 15"
        seria ruído na linha que tem de caber a 320px."""
        for rep_max in (REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO + 1, 15, 20):
            with self.subTest(rep_max=rep_max):
                texto = services.instrucao_de_esforco(_Item(True, sets=3, rep_max=rep_max), 3, Experiencia.INTERMEDIARIO)
                self.assertNotIn("mesmo passando", texto)
                self.assertIn("1 a 2 repetições na reserva", texto)

    def test_o_iniciante_na_ultima_serie_para_com_duas_sobrando_mesmo_passando(self):
        """O iniciante continua com 2 sobrando — e continua sem "falha" —,
        mas também aprende que a faixa não é teto."""
        texto = services.instrucao_de_esforco(_Item(True, sets=3, rep_max=10), 3, Experiencia.INICIANTE)
        self.assertIn("2 sobrando", texto)
        self.assertIn("mesmo passando de 10", texto)
        self.assertNotIn("falha", texto)

    def test_quem_tem_65_ou_mais_nunca_le_falha_em_serie_nenhuma(self):
        """Com `cauteloso` o isolador também para antes da falha: a última
        série pede 1 na reserva e técnica limpa. Composto, isolador, toda
        série, todo nível — nenhuma frase traz "falha"."""
        for composto in (True, False):
            for serie in (1, 2, 3):
                for nivel in (Experiencia.INICIANTE, Experiencia.INTERMEDIARIO, Experiencia.AVANCADO, ""):
                    with self.subTest(composto=composto, serie=serie, nivel=nivel):
                        texto = services.instrucao_de_esforco(
                            _Item(composto, sets=3, rep_max=10), serie, nivel, cauteloso=True
                        )
                        self.assertNotIn("falha", texto)
        ultima = services.instrucao_de_esforco(_Item(False, sets=3), 3, Experiencia.AVANCADO, cauteloso=True)
        self.assertIn("1 na reserva", ultima)
        # Sem `cauteloso` a mesma série do isolador continua indo à falha:
        # a régua é a idade, não a série.
        self.assertIn("falha", services.instrucao_de_esforco(_Item(False, sets=3), 3, Experiencia.AVANCADO))

    def test_a_idade_cautelosa_e_sessenta_e_cinco(self):
        """A constante é lida pelo serviço; o número é o da posição da NSCA
        para idosos (Fragala 2019). Mudá-lo é decisão do dono, não deriva."""
        self.assertEqual(IDADE_CAUTELOSA, 65)
        self.assertEqual(REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO, 12)

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
        # Pela LETRA de hoje (rotação contínua), não pelo dia da semana da linha.
        plano = services.get_active_routine(self.pessoa)
        return services.sessao_do_dia(plano, timezone.localdate())

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

    def _bloco(self, item):
        html = self._execucao(item)
        self.assertIn('class="series__esforco"', html)
        return html.split('class="series__esforco"', 1)[1].split("</p>", 1)[0]

    def test_a_ultima_serie_do_composto_na_tela_diz_mesmo_passando_da_faixa(self):
        """A tela lê `rep_max` da linha da ficha: com as séries anteriores
        registradas, a série da vez é a última e a frase muda."""
        composto = next(
            i for i in self._sessao_de_hoje().da_opcao(1)
            if i.exercise.is_compound and i.rep_max <= REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO
        )
        for _ in range(composto.sets - 1):
            services.append_set(self.pessoa, composto.exercise, 40)
        bloco = self._bloco(composto)
        self.assertIn("mesmo passando de %d" % composto.rep_max, bloco)
        self.assertNotIn("falha", bloco)

    def test_quem_tem_65_ou_mais_nao_le_falha_na_execucao(self):
        """A idade sai do perfil já carregado (zero consulta a mais): com 65
        anos EXATOS — a fronteira de `IDADE_CAUTELOSA`, inclusiva — o
        isolador da primeira série já não anuncia falha na última."""
        hoje = timezone.localdate()
        Profile.objects.filter(user=self.pessoa).update(
            experiencia=Experiencia.INTERMEDIARIO,
            birth_date=date(hoje.year - IDADE_CAUTELOSA, hoje.month, min(hoje.day, 28)),
        )
        # O nível mudou: a ficha remonta na visita e a escolha do dia, que
        # apontava para a sessão antiga, deixa de valer — a execução cairia na
        # VARIAÇÃO do ciclo (opção 2 num bloco ímpar: sábado 19/09, posição
        # 3) e o isolador da opção 1 responderia 404. Remonta e pina a 1 de
        # novo, como a pessoa faria ao abrir a ficha.
        self.pessoa = type(self.pessoa).objects.get(pk=self.pessoa.pk)
        services.sync_active_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        isolador = next(
            i for i in self._sessao_de_hoje().da_opcao(1)
            if not i.exercise.is_compound and i.measure == Measure.REPS
        )
        bloco = self._bloco(isolador)
        self.assertNotIn("falha", bloco)
        self.assertIn("técnica limpa", bloco)
        # Controle: a mesma pessoa com 30 anos lê a frase com "falha".
        Profile.objects.filter(user=self.pessoa).update(
            birth_date=date(hoje.year - 30, hoje.month, min(hoje.day, 28))
        )
        self.assertIn("falha", self._bloco(isolador))

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
            # T2.2: a última série do composto com faixa 12 (37 caracteres;
            # a versão de 44 quebrava a 320px) e as frases do cauteloso.
            (_Item(True, sets=3, rep_max=REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO), 3, Experiencia.INTERMEDIARIO),
            (_Item(True, sets=3, rep_max=REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO), 3, Experiencia.INICIANTE),
        ]
        for item, serie, nivel in casos:
            with self.subTest(serie=serie, nivel=nivel):
                self.assertLessEqual(len(services.instrucao_de_esforco(item, serie, nivel)), 44)
            with self.subTest(serie=serie, nivel=nivel, cauteloso=True):
                self.assertLessEqual(
                    len(services.instrucao_de_esforco(item, serie, nivel, cauteloso=True)), 44
                )
