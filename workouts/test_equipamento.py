"""EQUIPAMENTO NO PERFIL (17/09/2026): a segunda dimensão de personalização
do treino, e a primeira que mexe em QUAIS exercícios entram.

Quatro respostas (`accounts.models.Equipamento`), um mapa no `TREINO.md`
lido por `doutrina.equipamentos_de`, e o motor filtrando o catálogo ANTES de
prescrever — por SUBSTITUIÇÃO (mesmo padrão, mesmo grupo, mesma dose), e
não por filtro, que abriria buraco nos modelos curados (a medição de 10/09
em `test_capacidade_de_ambiente.py`). O plano guarda o perfil com que
nasceu; mudar no perfil remonta; quem já tinha conta ficou em "completa" e
não remonta.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.forms import TrainingForm
from accounts.models import Equipamento, Profile, TrainingDay
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import Equipment, Exercise, Padrao, TrainingPlan, WorkoutTemplate


def _plano(email, **perfil):
    user = create_complete_user(email=email, split_preference="two", split_preference_confirmada=True, **perfil)
    TrainingDay.objects.filter(user=user).delete()
    for d in range(5):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user, services.create_routine(user)


def _exercicios(plano):
    return {
        i.exercise
        for s in plano.sessions.prefetch_related("exercises__exercise")
        for i in s.exercises.all()
    }


class OMapaDeEquipamentoTests(TestCase):
    """O mapa mora no TREINO.md e o motor só lê."""

    def test_os_quatro_perfis_do_mapa_sao_os_do_enum(self):
        self.assertEqual(set(doutrina.PERFIS_DE_EQUIPAMENTO), set(Equipamento.values))

    def test_o_mapa_do_documento(self):
        self.assertEqual(doutrina.equipamentos_de(doutrina.COMPLETA), frozenset(Equipment.values))
        self.assertEqual(
            doutrina.equipamentos_de(doutrina.BASICA),
            frozenset({Equipment.DUMBBELL, Equipment.MACHINE, Equipment.CABLE, Equipment.BODYWEIGHT}),
        )
        self.assertEqual(
            doutrina.equipamentos_de(doutrina.CASA_HALTERES),
            frozenset({Equipment.DUMBBELL, Equipment.BODYWEIGHT}),
        )
        self.assertEqual(doutrina.equipamentos_de(doutrina.PESO_CORPORAL), frozenset({Equipment.BODYWEIGHT}))

    def test_perfil_desconhecido_ou_vazio_e_completa(self):
        """Quem monta ficha sem perfil (e o plano antigo) usa o catálogo inteiro."""
        self.assertEqual(doutrina.equipamentos_de(""), frozenset(Equipment.values))
        self.assertEqual(doutrina.equipamentos_de("garagem"), frozenset(Equipment.values))


class ASubstituicaoTests(TestCase):
    """O item fora do perfil é trocado pelo mesmo padrão e grupo, com a
    mesma dose; sem substituto, sai."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.modelos = {
            (t.split, t.label): t
            for t in WorkoutTemplate.objects.filter(is_active=True).prefetch_related("items__exercise")
        }
        self.a = self._itens("abc2", "A")
        self.c = self._itens("abc2", "C")

    def _itens(self, split, label):
        return [i for i in self.modelos[(split, label)].items.all() if i.exercise.is_active]

    def test_completa_devolve_os_mesmos_itens_sem_consulta(self):
        with self.assertNumQueries(0):
            resultado = services.substituir_por_equipamento(self.a, doutrina.equipamentos_de("completa"))
        self.assertEqual([id(i) for i in resultado], [id(i) for i in self.a])
        with self.assertNumQueries(0):
            self.assertEqual(services.substituir_por_equipamento(self.a, None), self.a)

    def test_o_agachamento_livre_vira_o_mesmo_padrao_com_halteres_e_a_mesma_dose(self):
        """Medido em 17/09/2026 no `abc2 C` em "casa com halteres": agachamento
        livre (barra) → afundo com halteres, leg press → goblet, stiff com
        barra → stiff com halteres — mesmo `padrao`, mesmo grupo, a dose do
        item trocado. O teste casa por PADRÃO, não por nome."""
        permitidos = doutrina.equipamentos_de("casa_halteres")
        original = next(i for i in self.c if i.exercise.equipment == Equipment.BARBELL and i.exercise.padrao == Padrao.AGACHAMENTO)
        with self.assertNumQueries(1):
            resultado = services.substituir_por_equipamento(self.c, permitidos)
        trocado = next(
            (i for i in resultado if i.order == original.order and i.exercise_id != original.exercise_id), None,
        )
        self.assertIsNotNone(trocado, "o agachamento livre saiu sem substituto do mesmo padrão")
        self.assertIn(trocado.exercise.equipment, permitidos)
        self.assertEqual(trocado.exercise.padrao, original.exercise.padrao)
        self.assertEqual(trocado.exercise.muscle_group, original.exercise.muscle_group)
        self.assertEqual(
            (trocado.sets, trocado.rep_min, trocado.rep_max, trocado.rest_seconds, trocado.measure),
            (original.sets, original.rep_min, original.rep_max, original.rest_seconds, original.measure),
        )
        self.assertIsNone(trocado.pk, "a cópia não pode se passar pelo item gravado do catálogo")
        self.assertTrue(all(i.exercise.equipment in permitidos for i in resultado))
        ids = [i.exercise_id for i in resultado]
        self.assertEqual(len(ids), len(set(ids)))
        # E os itens que já estavam dentro do perfil são os MESMOS objetos.
        dentro = {id(i) for i in self.c if i.exercise.equipment in permitidos}
        self.assertTrue(dentro <= {id(i) for i in resultado})

    def test_na_academia_basica_a_letra_a_troca_os_tres_de_barra_pelos_cinco_novos(self):
        """`abc2 A` lista 8 peitos e 6 tríceps, e TODAS as pressões de peito
        sem barra do catálogo de 17/09 (manhã) já estavam nele: sem barra, os
        três itens de barra saíam sem substituto e a letra fechava em 6
        exercícios e 50–52 min (dourado vermelho). Os cinco de peito e
        tríceps sem barra da tarde ficam FORA do modelo, de propósito, para
        serem exatamente esse substituto: supino reto com barra → declinado
        com halteres; tríceps testa → coice; supino fechado → flexão fechada.
        "Completa" não vê nada disso e a ficha dela continua idêntica."""
        permitidos = doutrina.equipamentos_de("basica")
        resultado = services.substituir_por_equipamento(self.a, permitidos)
        de_barra = [i for i in self.a if i.exercise.equipment == Equipment.BARBELL]
        self.assertEqual(len(de_barra), 3)
        self.assertEqual(len(resultado), len(self.a))
        nomes = {i.exercise.name for i in resultado}
        self.assertTrue({"Supino declinado com halteres", "Tríceps coice com halter", "Flexão de braço fechada (diamante)"} <= nomes, nomes)
        self.assertTrue(all(i.exercise.equipment in permitidos for i in resultado))
        self.assertEqual(len({i.exercise_id for i in resultado}), len(resultado))
        # E nenhum dos cinco novos está em modelo algum: eles só entram por substituição.
        from workouts.models import WorkoutTemplateItem

        self.assertFalse(WorkoutTemplateItem.objects.filter(exercise__name__in=[
            "Supino declinado com halteres", "Crucifixo inclinado com halteres", "Flexão de braço com pés elevados",
            "Flexão de braço fechada (diamante)", "Tríceps coice com halter",
        ]).exists())

    def test_o_substituto_nunca_e_um_exercicio_que_ja_esta_no_modelo(self):
        """Trocar o supino reto por um supino inclinado que o modelo já lista
        seria o mesmo exercício duas vezes na mesma sessão."""
        for chave, modelo in self.modelos.items():
            for perfil in doutrina.PERFIS_DE_EQUIPAMENTO:
                resultado = services.substituir_por_equipamento(self._itens(*chave), doutrina.equipamentos_de(perfil))
                ids = [i.exercise_id for i in resultado]
                self.assertEqual(len(ids), len(set(ids)), (chave, perfil))

    def test_sem_substituto_o_item_sai(self):
        """Peso do corpo: o que não tem versão sem aparelho no mesmo padrão
        e grupo desaparece — e o teste só vale se isso acontecer de verdade."""
        permitidos = doutrina.equipamentos_de("peso_corporal")
        resultado = services.substituir_por_equipamento(self.a, permitidos)
        self.assertLess(len(resultado), len(self.a))
        self.assertTrue(all(i.exercise.equipment == Equipment.BODYWEIGHT for i in resultado))

    def test_o_substituto_e_o_equipamento_mais_proximo_e_nao_o_primeiro_nome(self):
        """Supino reto com barra, sozinho num modelo, em "casa com halteres":
        há duas pressões de peito livres no perfil — a flexão com pés
        elevados (peso do corpo, primeira por nome) e o supino declinado com
        halteres. Barra vira halteres antes de virar flexão
        (`PROXIMIDADE_DE_EQUIPAMENTO`)."""
        from workouts.models import WorkoutTemplateItem

        supino = Exercise.objects.get(name="Supino reto com barra")
        item = WorkoutTemplateItem(exercise=supino, sets=4, rep_min=6, rep_max=10, rest_seconds=80, order=1)
        (trocado,) = services.substituir_por_equipamento([item], doutrina.equipamentos_de("casa_halteres"))
        self.assertEqual(trocado.exercise.name, "Supino declinado com halteres")
        # E o que o perfil PERMITE não é trocado: "básica" tem máquina, o
        # voador fica — o mesmo objeto, sem cópia.
        voador = Exercise.objects.get(name="Crucifixo na máquina (voador)")
        item = WorkoutTemplateItem(exercise=voador, sets=3, rep_min=10, rep_max=12, rest_seconds=60, order=2)
        (mesmo,) = services.substituir_por_equipamento([item], doutrina.equipamentos_de("basica"))
        self.assertIs(mesmo, item)

    def test_o_substituto_e_do_mesmo_padrao_e_nao_o_primeiro_do_grupo(self):
        """Modelo sintético com UM item — supino reto com barra — em "casa
        com halteres". Por nome, o primeiro peito do perfil é o crucifixo
        com halteres (padrão `crucifixo`); o certo é uma PRESSÃO de peito.
        Sabotagem medida: ignorar `padrao` na escolha devolve o crucifixo e
        este teste fica vermelho — nos modelos reais o primeiro candidato do
        grupo coincidia com o do padrão."""
        from workouts.models import WorkoutTemplateItem

        supino = Exercise.objects.get(name="Supino reto com barra")
        item = WorkoutTemplateItem(exercise=supino, sets=4, rep_min=6, rep_max=10, rest_seconds=80, order=1)
        permitidos = doutrina.equipamentos_de("casa_halteres")
        (trocado,) = services.substituir_por_equipamento([item], permitidos)
        self.assertEqual(trocado.exercise.padrao, Padrao.PRESSAO_DE_PEITO)
        primeiro_do_grupo = Exercise.objects.filter(
            is_active=True, muscle_group=supino.muscle_group, equipment__in=list(permitidos),
        ).order_by("name").first()
        self.assertNotEqual(primeiro_do_grupo.padrao, Padrao.PRESSAO_DE_PEITO, "o controle do teste precisa de um primeiro-por-nome de outro padrão")
        self.assertNotEqual(trocado.exercise_id, primeiro_do_grupo.id)

    def test_a_escolha_e_deterministica(self):
        """A conferência refaz a conta do gerador; duas respostas diferentes
        para a mesma pergunta remontariam a ficha em laço."""
        permitidos = doutrina.equipamentos_de("casa_halteres")
        a = [i.exercise_id for i in services.substituir_por_equipamento(self.c, permitidos)]
        b = [i.exercise_id for i in services.substituir_por_equipamento(self.c, permitidos)]
        self.assertEqual(a, b)


class OPlanoEORetratoDoEquipamentoTests(TestCase):
    """O plano guarda o perfil com que nasceu; mudar no perfil remonta; a
    conferência reconhece a própria ficha filtrada."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_o_padrao_e_completa_no_perfil_e_no_plano(self):
        user, plano = _plano("padrao@exemplo.com")
        self.assertEqual(user.profile.equipamento, Equipamento.COMPLETA)
        self.assertEqual(plano.equipamento, "completa")
        self.assertEqual(TrainingPlan._meta.get_field("equipamento").default, "completa")
        self.assertEqual(Profile._meta.get_field("equipamento").default, "completa")

    def test_a_conta_antiga_nao_e_remontada_pela_pergunta_nova(self):
        user, plano = _plano("antiga@exemplo.com")
        self.assertFalse(services.rotina_invalida(plano, user))
        self.assertFalse(services.rotina_desatualizada(plano, user))

    def test_mudar_o_equipamento_no_perfil_remonta_a_ficha(self):
        user, plano = _plano("muda@exemplo.com")
        user.profile.equipamento = Equipamento.BASICA
        user.profile.save(update_fields=["equipamento"])
        user = type(user).objects.get(pk=user.pk)
        self.assertTrue(services.rotina_invalida(plano, user))
        novo, remontou = services.sync_active_routine(user)
        self.assertTrue(remontou)
        self.assertNotEqual(novo.pk, plano.pk)
        self.assertEqual(novo.equipamento, "basica")
        self.assertFalse(any(e.equipment == Equipment.BARBELL for e in _exercicios(novo)))
        self.assertTrue(_exercicios(novo))

    def test_a_ficha_da_academia_basica_nao_tem_barra_e_a_conferencia_a_reconhece(self):
        """A conferência (`_prescricao_confere`) refaz a prescrição com o
        MESMO filtro — sem isso a ficha filtrada seria julgada desatualizada
        em toda visita, e a Home ofereceria "regenerar" para sempre."""
        user, plano = _plano("basica@exemplo.com", equipamento=Equipamento.BASICA)
        self.assertEqual(plano.equipamento, "basica")
        exercicios = _exercicios(plano)
        self.assertTrue(exercicios)
        self.assertFalse(any(e.equipment == Equipment.BARBELL for e in exercicios))
        self.assertFalse(services.rotina_invalida(plano, user))
        self.assertFalse(services.rotina_desatualizada(plano, user))

    def test_a_ficha_de_perfil_restrito_nascida_de_outro_catalogo_e_conferida_com_o_mesmo_filtro(self):
        """A impressão digital do catálogo poupa a conferência exata só
        quando é a de hoje; ficha de outro catálogo (deploy novo) passa por
        `_prescricao_bate`, que refaz a prescrição — COM o perfil de
        equipamento, inclusive na pré-conferência de reps e descanso, senão
        o afundo que substituiu o agachamento reprovava e a Home oferecia
        "regenerar" para sempre a quem treina em casa. Sabotagem medida:
        `permitidos` fora da conferência deixa os dois perfis vermelhos."""
        for perfil in (Equipamento.BASICA, Equipamento.CASA_HALTERES):
            with self.subTest(perfil=perfil):
                user, plano = _plano("outro-catalogo-%s@exemplo.com" % perfil, equipamento=perfil)
                TrainingPlan.objects.filter(pk=plano.pk).update(catalogo="catalogo-de-ontem")
                plano.refresh_from_db()
                self.assertFalse(services.rotina_desatualizada(plano, user))
                plano.refresh_from_db()
                self.assertEqual(plano.catalogo, services.versao_do_catalogo())

    def test_a_ficha_de_casa_so_tem_halteres_e_peso_do_corpo(self):
        user, plano = _plano("casa@exemplo.com", equipamento=Equipamento.CASA_HALTERES)
        permitidos = doutrina.equipamentos_de("casa_halteres")
        exercicios = _exercicios(plano)
        self.assertTrue(exercicios)
        self.assertTrue(all(e.equipment in permitidos for e in exercicios))
        self.assertFalse(services.rotina_desatualizada(plano, user))

    def test_completa_e_a_ficha_de_sempre(self):
        """Controle: o perfil "completa" não muda nada — o teste dourado
        continua valendo na mesma ficha."""
        _, com = _plano("controle-completa@exemplo.com", equipamento=Equipamento.COMPLETA)
        _, sem = _plano("controle-sem@exemplo.com")
        self.assertEqual(
            sorted(e.name for e in _exercicios(com)), sorted(e.name for e in _exercicios(sem)),
        )


class APerguntaTests(TestCase):
    """Etapa 2 do onboarding e Perfil: a pergunta existe, grava, e em branco
    não apaga."""

    def setUp(self):
        self.user = create_complete_user(email="pergunta@exemplo.com")
        self.client.force_login(self.user)

    def test_a_etapa_2_pergunta_e_abre_com_completa_marcada(self):
        html = self.client.get(reverse("accounts:onboarding_step", kwargs={"step": 2})).content.decode()
        self.assertIn("O que você tem para treinar?", html)
        self.assertIn('name="equipamento"', html)
        form = TrainingForm(user=self.user)
        self.assertEqual(form.get_initial_for_field(form.fields["equipamento"], "equipamento"), "completa")

    def test_o_formulario_grava_a_resposta(self):
        aberto = TrainingForm(user=self.user)
        dados = {"wake_time": "07:00", "sleep_time": "23:00", "weekdays": ["0", "2"], "equipamento": "casa_halteres"}
        enviado = TrainingForm(dados, user=self.user)
        self.assertTrue(enviado.is_valid(), enviado.errors)
        enviado.save()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.equipamento, Equipamento.CASA_HALTERES)
        del aberto

    def test_em_branco_nao_apaga_o_que_a_pessoa_tinha(self):
        self.user.profile.equipamento = Equipamento.BASICA
        self.user.profile.save(update_fields=["equipamento"])
        dados = {"wake_time": "07:00", "sleep_time": "23:00", "weekdays": ["0", "2"]}
        enviado = TrainingForm(dados, user=self.user)
        self.assertTrue(enviado.is_valid(), enviado.errors)
        enviado.save()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.equipamento, Equipamento.BASICA)

    def test_o_perfil_e_o_resumo_mostram_o_equipamento(self):
        from accounts.views import resumo_das_escolhas

        self.user.profile.equipamento = Equipamento.CASA_HALTERES
        self.user.profile.save(update_fields=["equipamento"])
        html = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn("Equipamento", html)
        self.assertIn("Em casa, com halteres", html)
        self.assertIn(("Equipamento", "Em casa, com halteres"), resumo_das_escolhas(self.user, self.user.profile))

    def test_todo_exercicio_ativo_tem_padrao_e_equipamento_para_a_troca_valer(self):
        """A substituição casa por `padrao` + grupo + `equipment`: um ativo
        sem qualquer um deles seria invisível para ela."""
        call_command("seed_workouts", verbosity=0)
        for e in Exercise.objects.filter(is_active=True):
            self.assertIn(e.padrao, Padrao.values, e.name)
            self.assertIn(e.equipment, Equipment.values, e.name)
