# -*- coding: utf-8 -*-
"""O glúteo é grupo próprio (21/09/2026), e ninguém perdeu exercício por isso.

Quatro coisas que importam provar, e o motivo de cada uma:

- a migration `0032` reclassifica POR NOME as quatro linhas e devolve tudo no
  `--reverse`; o seed grava o mesmo valor (senão o próximo deploy desfaz);
- a ficha montada ANTES do grupo existir continua com as MESMAS linhas
  depois — e não é julgada desatualizada: o `SessionExercise` aponta para o
  exercício pela chave, e o grupo não entra na conferência da prescrição.
  É a régua da missão: nenhuma ficha existente perde exercício;
- para as OPÇÕES, o relógio e o principal da sessão, posterior e glúteo são
  uma FAMÍLIA: stiff e elevação pélvica são o mesmo padrão composto, um em
  cada versão da letra. Sem isso a letra C do abc2 em Padrão caía para UMA
  opção de 20 séries (medido). O teste prende a letra do teste dourado;
- "outras formas" e a substituição por equipamento respeitam o grupo: a
  elevação pélvica troca por elevação pélvica, o stiff por stiff — e a
  família só responde quando o grupo esgotou.
"""
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase

from accounts.models import DuracaoTreino, Equipamento, TrainingDay
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import (
    FAMILIA_DE_OPCOES, Exercise, MuscleGroup, SessionExercise, WorkoutTemplate, familia_de_opcoes,
)

GLUTEO = ("Elevação pélvica", "Elevação pélvica no banco", "Ponte de glúteo", "Ponte de glúteo unilateral")


def _pessoa(email, dias=5, preferencia="two", duracao=DuracaoTreino.PADRAO, equipamento=Equipamento.COMPLETA):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference=preferencia,
        split_preference_confirmada=True, duracao_treino=duracao, equipamento=equipamento,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class OGrupoExisteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_os_quatro_diretos_sao_gluteo_e_o_posterior_deixou_de_dizer_gluteo(self):
        for nome in GLUTEO:
            with self.subTest(nome=nome):
                self.assertEqual(Exercise.objects.get(name=nome).muscle_group, MuscleGroup.GLUTES)
        self.assertEqual(MuscleGroup.HAMSTRINGS.label, "Posterior de coxa")
        self.assertEqual(MuscleGroup.GLUTES.label, "Glúteo")
        self.assertEqual(services.NOME_CURTO_DO_GRUPO[MuscleGroup.GLUTES], "glúteo")

    def test_agachar_e_estender_o_quadril_trabalham_o_gluteo_como_secundario(self):
        """O que sempre foi verdade anatômica e não estava escrito: todo
        agachamento e toda extensão de quadril de quadríceps/posterior levam
        o glúteo nos secundários — é de onde vem o estímulo além do único
        exercício direto por letra."""
        for e in Exercise.objects.filter(is_active=True, padrao__in=("agachamento", "extensao_de_quadril"),
                                         muscle_group__in=(MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS)):
            with self.subTest(exercicio=e.name):
                self.assertIn("glutes", e.secondary_muscles)

    def test_o_gluteo_e_anunciado_em_toda_letra_que_tem_um_exercicio_dele(self):
        """Anunciado, e não complementar: complementar cede primeiro no
        tempo curto, e a elevação pélvica era protegida como posterior."""
        for modelo in WorkoutTemplate.objects.prefetch_related("items__exercise"):
            tem = any(i.exercise.muscle_group == MuscleGroup.GLUTES for i in modelo.items.all())
            with self.subTest(modelo="%s %s" % (modelo.split, modelo.label)):
                self.assertEqual(MuscleGroup.GLUTES in modelo.main_groups, tem)
                if tem:
                    self.assertIn(MuscleGroup.HAMSTRINGS, modelo.main_groups)

    def test_o_seed_grava_o_mesmo_grupo_que_a_migration(self):
        antes = dict(Exercise.objects.values_list("name", "muscle_group"))
        call_command("seed_workouts", verbosity=0)
        self.assertEqual(dict(Exercise.objects.values_list("name", "muscle_group")), antes)

    def test_o_titulo_chama_a_cadeia_de_posterior_e_pernas_continua_pernas(self):
        """UM título para as duas versões da letra: a com o stiff e a com a
        elevação pélvica têm a mesma cadeia, e o nome dela é "posterior" —
        o que o app dizia antes do grupo existir."""
        nomes = services._nomes_dos_grupos([MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES, MuscleGroup.SHOULDERS])
        self.assertEqual(nomes, ["pernas", "ombros"])
        nomes = services._nomes_dos_grupos([MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES, MuscleGroup.TRAPS])
        self.assertEqual(nomes, ["posterior", "glúteo", "trapézio"], "o aviso e o foco nomeiam o grupo de verdade")
        nomes = services._nomes_dos_grupos([MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES, MuscleGroup.TRAPS], por_familia=True)
        self.assertEqual(nomes, ["posterior", "trapézio"], "o título chama a cadeia de posterior")
        self.assertEqual(services._nomes_dos_grupos([MuscleGroup.QUADS, MuscleGroup.GLUTES], por_familia=True), ["pernas"])
        self.assertEqual(
            services.titulo_honesto("Pernas completo", ["quads", "hamstrings", "glutes", "calves"], ["quads", "glutes"]),
            "Pernas",
        )
        # Sem perna inteira, o título reescrito chama a cadeia de "posterior"
        # e NÃO nomeia "glúteo": a outra versão da letra pode ter só o stiff.
        self.assertEqual(
            services.titulo_honesto("Complementares", ["hamstrings", "glutes", "traps", "calves"], ["hamstrings", "glutes", "traps"]),
            "Posterior e trapézio",
        )
        self.assertEqual(
            services.titulo_honesto("Complementares", ["hamstrings", "glutes", "traps", "calves"], ["glutes", "traps"]),
            "Posterior e trapézio",
        )
        # A cadeia sobrevive por qualquer um dos dois: o nome do catálogo fica.
        self.assertEqual(
            services.titulo_honesto("Pernas e ombros", ["quads", "hamstrings", "glutes", "shoulders"], ["quads", "glutes", "shoulders"]),
            "Pernas e ombros",
        )
        self.assertEqual(
            services.titulo_honesto("Pernas e ombros", ["quads", "hamstrings", "glutes", "shoulders"], ["quads", "hamstrings"]),
            "Pernas",
        )

    def test_a_familia_e_so_gluteo_para_posterior(self):
        self.assertEqual(FAMILIA_DE_OPCOES, {"glutes": "hamstrings"})
        self.assertEqual(familia_de_opcoes("glutes"), "hamstrings")
        self.assertEqual(familia_de_opcoes("chest"), "chest")
        self.assertIn("glutes", __import__("workouts.adaptacao", fromlist=["GRUPOS_INFERIORES"]).GRUPOS_INFERIORES)


class NenhumaFichaPerdeExercicioTests(TestCase):
    """A régua da missão, provada de dois jeitos: a ficha do teste dourado
    (intermediário, 5 dias, abc2, Padrão) continua com DUAS opções em toda
    letra e com a elevação pélvica numa versão e o stiff na outra; e uma
    ficha nascida com os quatro como "posterior" não é julgada desatualizada
    depois de eles virarem glúteo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_a_letra_de_pernas_do_teste_dourado_mantem_duas_opcoes_com_stiff_e_elevacao_pelvica_separados(self):
        user = _pessoa("dourado-gluteo@exemplo.com")
        plan = services.create_routine(user)
        pernas = plan.sessions.filter(label="C").first()
        self.assertIn(MuscleGroup.GLUTES, pernas.main_groups)
        por_opcao = {}
        for item in pernas.exercises.select_related("exercise"):
            por_opcao.setdefault(item.opcao, set()).add(item.exercise.name)
        self.assertEqual(len(por_opcao), 2, "a letra C tem duas opções")
        com_pelvica = [op for op, nomes in por_opcao.items() if "Elevação pélvica" in nomes]
        com_stiff = [op for op, nomes in por_opcao.items() if "Stiff com barra" in nomes]
        self.assertEqual(len(com_pelvica), 1)
        self.assertEqual(len(com_stiff), 1)
        self.assertNotEqual(com_pelvica, com_stiff, "um em cada versão da letra, como sempre")
        for op, nomes in por_opcao.items():
            with self.subTest(opcao=op):
                self.assertGreaterEqual(len(nomes), 8)

    def test_o_inferior_de_dois_dias_em_rapido_mantem_duas_opcoes(self):
        """Três principais de três séries são os 30 minutos inteiros: sem a
        família no PRINCIPAL da sessão (`prioridades_da_sessao`), a versão
        com a elevação pélvica ganhava o bom dia como segundo principal e a
        letra caía para uma opção (medido em 21/09/2026)."""
        user = _pessoa("rapido-gluteo@exemplo.com", dias=2, duracao=DuracaoTreino.RAPIDO)
        plan = services.create_routine(user)
        inferior = plan.sessions.filter(label="B").first()
        opcoes = {item.opcao for item in inferior.exercises.all()}
        self.assertEqual(opcoes, {1, 2})
        graus = services.prioridades_da_sessao(list(inferior.exercises.filter(opcao=1).select_related("exercise").order_by("order")))
        self.assertLessEqual(graus.count(services.PRINCIPAL), 2, "um principal por família, e o quadríceps")

    def test_toda_letra_com_duas_opcoes_em_producao_continua_com_duas(self):
        from workouts.opcoes_em_producao import LETRAS_COM_OPCOES_EM_PRODUCAO, opcoes_por_letra

        contagem = opcoes_por_letra()
        for letra in LETRAS_COM_OPCOES_EM_PRODUCAO:
            with self.subTest(letra=letra):
                self.assertGreaterEqual(contagem[letra], 2)

    def test_a_ficha_nascida_com_os_quatro_como_posterior_continua_igual_e_nao_e_desatualizada(self):
        """Simula a ficha de antes: monta a rotina com os quatro em
        `hamstrings` (o estado de produção até o deploy), devolve o grupo ao
        catálogo de hoje e confere que as linhas são as mesmas e que a Home
        não pede para regenerar."""
        Exercise.objects.filter(name__in=GLUTEO).update(muscle_group=MuscleGroup.HAMSTRINGS)
        for e in Exercise.objects.filter(muscle_group__in=(MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS)):
            e.secondary_muscles = [g for g in (e.secondary_muscles or []) if g != "glutes"]
            e.save(update_fields=["secondary_muscles"])
        user = _pessoa("antes-do-gluteo@exemplo.com")
        plan = services.create_routine(user)
        linhas_antes = sorted(
            SessionExercise.objects.filter(session__plan=plan).values_list("session__label", "opcao", "order", "exercise__name", "sets")
        )
        self.assertTrue(any(nome == "Elevação pélvica" for _, _, _, nome, _ in linhas_antes))

        call_command("seed_workouts", verbosity=0)  # o deploy: o catálogo de hoje volta
        self.assertEqual(Exercise.objects.get(name="Elevação pélvica").muscle_group, MuscleGroup.GLUTES)
        plan.refresh_from_db()
        linhas_depois = sorted(
            SessionExercise.objects.filter(session__plan=plan).values_list("session__label", "opcao", "order", "exercise__name", "sets")
        )
        self.assertEqual(linhas_antes, linhas_depois, "nenhuma linha da ficha mudou")
        self.assertFalse(services.rotina_invalida(plan, user))
        self.assertTrue(services._prescricao_bate(plan, user), "a Home não pede para regenerar")


class OutrasFormasESubstituicaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_outras_formas_da_elevacao_pelvica_sao_gluteo_e_as_do_stiff_sao_posterior(self):
        user = _pessoa("formas-gluteo@exemplo.com")
        pelvica = Exercise.objects.get(name="Elevação pélvica")
        formas = {e.name for e in services.alternativas_de(user, pelvica)}
        self.assertEqual(formas, {"Elevação pélvica no banco", "Ponte de glúteo", "Ponte de glúteo unilateral"})
        stiff = Exercise.objects.get(name="Stiff com barra")
        formas = {e.name for e in services.alternativas_de(user, stiff)}
        self.assertNotIn("Elevação pélvica", formas)
        self.assertIn("Stiff com halteres", formas)

    def test_sem_barra_a_elevacao_pelvica_troca_por_elevacao_pelvica_e_o_stiff_por_stiff(self):
        permitidos = doutrina.equipamentos_de(Equipamento.BASICA)
        modelo = WorkoutTemplate.objects.get(split="abc2", label="C")
        itens = services.substituir_por_equipamento(
            list(modelo.items.select_related("exercise")), permitidos,
        )
        nomes = [i.exercise.name for i in itens]
        self.assertIn("Elevação pélvica no banco", nomes)
        self.assertNotIn("Elevação pélvica", nomes)
        self.assertIn("Stiff com halteres", nomes)
        self.assertNotIn("Stiff com barra", nomes)
        self.assertEqual(len(nomes), modelo.items.count(), "nenhum item saiu sem substituto")

    def test_a_familia_so_responde_quando_o_grupo_esgotou(self):
        """"Inferior" só com o peso do corpo pede três stiffs e uma elevação
        pélvica; o catálogo tem UM stiff sem carga. O segundo e o terceiro
        viram ponte de glúteo — mesmo padrão, família — em vez de sumir."""
        permitidos = doutrina.equipamentos_de(Equipamento.PESO_CORPORAL)
        modelo = WorkoutTemplate.objects.get(split="ab", label="B")
        itens = services.substituir_por_equipamento(
            list(modelo.items.select_related("exercise")), permitidos,
        )
        extensoes = [i.exercise.name for i in itens if i.exercise.padrao == "extensao_de_quadril"]
        originais = [i.exercise.name for i in modelo.items.select_related("exercise") if i.exercise.padrao == "extensao_de_quadril"]
        self.assertEqual(len(extensoes), len(originais), "toda extensão de quadril do modelo tem substituto")
        self.assertIn("Stiff unilateral com peso do corpo", extensoes)
        self.assertTrue({"Ponte de glúteo", "Ponte de glúteo unilateral", "Elevação pélvica no banco"} & set(extensoes))


class AMigrationDoGluteoTests(TransactionTestCase):
    ANTES = ("workouts", "0031_merge_20260920_2352")
    DEPOIS = ("workouts", "0032_grupo_gluteo")

    def _migrar(self, alvo):
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([alvo])
        return executor.loader.project_state([alvo]).apps

    def tearDown(self):
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_reclassifica_pelo_nome_e_volta_no_reverse(self):
        velho = self._migrar(self.ANTES)
        Exercicio = velho.get_model("workouts", "Exercise")
        Exercicio.objects.create(name="Elevação pélvica", muscle_group="hamstrings", equipment="barbell",
                                 padrao="extensao_de_quadril", is_compound=True)
        Exercicio.objects.create(name="Stiff com barra", muscle_group="hamstrings", equipment="barbell",
                                 padrao="extensao_de_quadril", is_compound=True)

        novo = self._migrar(self.DEPOIS)
        Exercicio = novo.get_model("workouts", "Exercise")
        self.assertEqual(Exercicio.objects.get(name="Elevação pélvica").muscle_group, "glutes")
        self.assertEqual(Exercicio.objects.get(name="Stiff com barra").muscle_group, "hamstrings")

        velho = self._migrar(self.ANTES)
        Exercicio = velho.get_model("workouts", "Exercise")
        self.assertEqual(Exercicio.objects.get(name="Elevação pélvica").muscle_group, "hamstrings")
