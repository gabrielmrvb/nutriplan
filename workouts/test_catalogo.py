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
from django.test import SimpleTestCase, TestCase, TransactionTestCase
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


class PadraoDeMovimentoTests(TestCase):
    """Todo exercício declara o PADRÃO de movimento, e o banco não aceita
    exercício sem ele nem sem equipamento.

    A taxonomia tem 22 valores e um nível só (16/09/2026): ângulo e pegada
    ficam no nome — reto e inclinado são a mesma pressão de peito; lateral e
    frontal a mesma elevação. É o que a régua de equivalência das opções lê:
    duas opções de "Peito e tríceps" precisam das MESMAS pressões, e podem
    diferir nos isoladores.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_taxonomia_tem_vinte_e_dois_padroes_e_oito_compostos(self):
        from workouts.models import PADROES_COMPOSTOS, Padrao

        self.assertEqual(len(Padrao), 22)
        self.assertEqual(
            set(PADROES_COMPOSTOS),
            {
                Padrao.PRESSAO_DE_PEITO, Padrao.PUXADA_VERTICAL, Padrao.REMADA_HORIZONTAL,
                Padrao.PRESSAO_VERTICAL, Padrao.AGACHAMENTO, Padrao.EXTENSAO_DE_QUADRIL,
                Padrao.PRESSAO_FECHADA, Padrao.REMADA_ALTA,
            },
        )

    def test_todo_exercicio_semeado_tem_padrao_da_taxonomia(self):
        from workouts.models import Exercise, Padrao

        validos = {p.value for p in Padrao}
        sem = [e.name for e in Exercise.objects.all() if e.padrao not in validos]
        self.assertEqual(sem, [])
        self.assertGreaterEqual(Exercise.objects.count(), 36)

    def test_composto_e_o_padrao_concordam(self):
        """`is_compound` continua decidindo série e descanso; o padrão decide
        a equivalência. Os dois dizem a mesma coisa sobre cada exercício, e
        este teste é o que impede um "supino isolador" por digitação."""
        from workouts.models import PADROES_COMPOSTOS, Exercise

        discordam = [
            e.name for e in Exercise.objects.all()
            if e.is_compound != (e.padrao in PADROES_COMPOSTOS)
        ]
        self.assertEqual(discordam, [])

    def test_o_banco_recusa_exercicio_sem_padrao(self):
        from django.db import IntegrityError, transaction

        from workouts.models import Equipment, Exercise, MuscleGroup

        with self.assertRaises(IntegrityError), transaction.atomic():
            Exercise.objects.create(
                name="Sem padrão", muscle_group=MuscleGroup.CHEST,
                equipment=Equipment.MACHINE, padrao="",
            )

    def test_o_banco_recusa_exercicio_sem_equipamento(self):
        from django.db import IntegrityError, transaction

        from workouts.models import Exercise, MuscleGroup, Padrao

        with self.assertRaises(IntegrityError), transaction.atomic():
            Exercise.objects.create(
                name="Sem equipamento", muscle_group=MuscleGroup.CHEST,
                equipment="", padrao=Padrao.CRUCIFIXO,
            )

    def test_o_json_do_catalogo_declara_padrao_e_equipamento_em_todos(self):
        """O seed lê `row["padrao"]` sem `.get`: linha sem padrão derruba o
        build, que é onde um catálogo pela metade tem de parar."""
        import json

        from workouts.models import Equipment, Padrao

        catalogo = json.loads(
            (RAIZ / "workouts" / "data" / "exercises.json").read_text(encoding="utf-8")
        )
        padroes = {p.value for p in Padrao}
        equipamentos = {e.value for e in Equipment}
        for linha in catalogo:
            with self.subTest(exercicio=linha["name"]):
                self.assertIn(linha.get("padrao"), padroes)
                self.assertIn(linha.get("equipment"), equipamentos)

    def test_o_seed_depois_da_migration_mantem_o_padrao(self):
        """A migration preenche quem já existe; o seed, que roda em todo
        deploy, precisa gravar o mesmo valor — senão o próximo build zera o
        campo e o `CheckConstraint` derruba a publicação."""
        from workouts.models import Exercise

        antes = dict(Exercise.objects.values_list("name", "padrao"))
        call_command("seed_workouts", verbosity=0)
        self.assertEqual(dict(Exercise.objects.values_list("name", "padrao")), antes)


class AMigrationDoPadraoTests(TransactionTestCase):
    """A `0022` preenche o padrão de quem JÁ existe pelo nome, e recusa
    exercício que ela não conhece — em vez de deixá-lo em branco para a
    constraint derrubar o deploy com uma mensagem pior."""

    ANTES = ("workouts", "0021_opcoes_por_letra")
    DEPOIS = ("workouts", "0022_padrao_de_movimento")

    def _migrar(self, alvo):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([alvo])
        return executor.loader.project_state([alvo]).apps

    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_quem_ja_existe_recebe_o_padrao_pelo_nome(self):
        velho = self._migrar(self.ANTES)
        Exercicio = velho.get_model("workouts", "Exercise")
        Exercicio.objects.create(name="Supino reto com barra", muscle_group="chest", equipment="barbell")
        Exercicio.objects.create(name="Remada curvada", muscle_group="back", equipment="barbell", is_active=False)

        novo = self._migrar(self.DEPOIS)

        Exercicio = novo.get_model("workouts", "Exercise")
        self.assertEqual(Exercicio.objects.get(name="Supino reto com barra").padrao, "pressao_de_peito")
        # A linha legada, anterior à `0017`, é o mesmo movimento da sucessora.
        self.assertEqual(Exercicio.objects.get(name="Remada curvada").padrao, "remada_horizontal")

    def test_exercicio_desconhecido_derruba_a_migration(self):
        velho = self._migrar(self.ANTES)
        Exercicio = velho.get_model("workouts", "Exercise")
        Exercicio.objects.create(name="Cadastrado à mão", muscle_group="chest", equipment="barbell")

        with self.assertRaisesRegex(RuntimeError, "Cadastrado à mão"):
            self._migrar(self.DEPOIS)
        Exercicio.objects.all().delete()


class GateDeOpcoesPorLetraTests(TestCase):
    """Nenhum deploy reduz o número de letras com duas opções (16/09/2026).

    O número é o que o MOTOR entrega com o catálogo ATIVO, passando pela
    mesma `create_routine` de produção — não uma conta sobre o JSON. Fica
    VERMELHO enquanto o código local entregar menos do que produção tem, e
    é para ficar: a régua de padrões compostos derruba a segunda opção das
    letras que só a tinham por acidente, e o que a devolve é ativar, com
    mídia conferida, o exercício que cada uma pede.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_nenhum_deploy_reduz_as_letras_com_duas_opcoes(self):
        from workouts import opcoes_em_producao as gate

        por_letra = gate.opcoes_por_letra()
        com_duas = gate.letras_com_opcoes(por_letra)
        tabela = "\n".join("  %s %s: %d" % (s, l, n) for (s, l), n in sorted(por_letra.items()))
        self.assertGreaterEqual(
            len(com_duas), gate.LETRAS_COM_OPCOES_EM_PRODUCAO,
            "\n%d letras com duas opções contra %d em produção:\n%s"
            % (len(com_duas), gate.LETRAS_COM_OPCOES_EM_PRODUCAO, tabela),
        )

    def test_a_conta_do_gate_nao_deixa_rastro(self):
        from accounts.models import User
        from workouts import opcoes_em_producao as gate
        from workouts.models import TrainingPlan

        antes = (User.objects.count(), TrainingPlan.objects.count())
        por_letra = gate.opcoes_por_letra()
        self.assertEqual((User.objects.count(), TrainingPlan.objects.count()), antes)
        self.assertEqual({s for s, _ in por_letra}, {"full", "ab", "abc", "abc2", "abcd", "abcde"})


class CatalogoDimensionadoTests(TestCase):
    """Objetivo 3 (16/09/2026): o catálogo cresce até sustentar DUAS opções
    cheias por letra — e cresce INATIVO, porque exercício ativo tem
    demonstração conferida por alguém que assistiu, e este ambiente não
    assiste. Os 28 novos entram com padrão, equipamento, dica, chave
    conferida na free-exercise-db e candidatos de mídia achados por busca;
    ativar é curadoria da manhã, não deploy.

    A fórmula: para um grupo com `k` exercícios ATIVOS no modelo da letra,
    duas opções com metade própria pedem `2·ceil(k/2) + floor(k/2)`; duas
    opções CHEIAS pedem `2k`. E a régua dos compostos pede dois exercícios
    por padrão composto do grupo no modelo.
    """

    NOVOS = 28

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _catalogo(self):
        import json

        return json.loads((RAIZ / "workouts" / "data" / "exercises.json").read_text(encoding="utf-8"))

    def test_os_novos_entram_inativos_e_completos(self):
        import json

        from workouts.models import Exercise

        mapa = json.loads((RAIZ / "workouts" / "data" / "media_map.json").read_text(encoding="utf-8"))
        novos = [x for x in self._catalogo() if not x.get("active", True) and x["name"] != "Remada curvada com barra"]
        self.assertEqual(len(novos), self.NOVOS)
        for linha in novos:
            with self.subTest(exercicio=linha["name"]):
                self.assertFalse(Exercise.objects.get(name=linha["name"]).is_active)
                self.assertTrue(linha["padrao"] and linha["equipment"] and linha["cue"])
                self.assertIn(linha["name"], mapa, "sem chave na free-exercise-db")
                self.assertTrue(linha["candidatos"]["execucao"], "sem candidato de execução")
                self.assertTrue(linha["candidatos"]["anatomia"], "sem candidato de anatomia")
                # Candidato NÃO é vídeo: `video` só entra com `video_titulo`,
                # depois de alguém assistir.
                self.assertNotIn("video", linha)

    def test_os_ativos_continuam_os_mesmos_trinta_e_cinco(self):
        """O deploy sobe o catálogo pronto, não a variedade: nenhum novo
        ativo por acidente."""
        from workouts.models import Exercise

        self.assertEqual(Exercise.objects.filter(is_active=True).count(), 35)
        self.assertEqual(Exercise.objects.count(), 36 + self.NOVOS)

    def test_todo_padrao_composto_anunciado_tem_dois_exercicios_no_modelo(self):
        """A condição estrutural para duas opções depois da ativação: em cada
        letra, cada padrão composto de um grupo anunciado tem pelo menos dois
        exercícios no modelo (contando os inativos)."""
        from workouts.models import PADROES_COMPOSTOS, WorkoutTemplate

        for modelo in WorkoutTemplate.objects.filter(is_active=True):
            itens = list(modelo.items.select_related("exercise"))
            for grupo in modelo.main_groups or []:
                por_padrao = {}
                for item in itens:
                    if item.exercise.muscle_group == grupo and item.exercise.padrao in PADROES_COMPOSTOS:
                        por_padrao[item.exercise.padrao] = por_padrao.get(item.exercise.padrao, 0) + 1
                for padrao, n in por_padrao.items():
                    with self.subTest(modelo="%s %s" % (modelo.split, modelo.label), grupo=grupo, padrao=padrao):
                        self.assertGreaterEqual(n, 2)

    #: A tabela "hoje" de 16/09/2026: quantos exercícios ATIVOS cada grupo
    #: anunciado tinha no modelo da letra ANTES da expansão — é o `k` da
    #: fórmula, a dose de uma sessão. Congelada porque o modelo cresceu e
    #: recalcular `k` do modelo novo faria a régua correr atrás dela mesma.
    K_HOJE = {
        ("full", "A", "quads"): 1, ("full", "A", "chest"): 1, ("full", "A", "back"): 1,
        ("full", "A", "hamstrings"): 1, ("full", "A", "shoulders"): 1, ("full", "A", "biceps"): 1,
        ("full", "A", "triceps"): 1,
        ("ab", "A", "chest"): 1, ("ab", "A", "back"): 2, ("ab", "A", "shoulders"): 1,
        ("ab", "A", "biceps"): 1, ("ab", "A", "triceps"): 1,
        ("ab", "B", "quads"): 2, ("ab", "B", "hamstrings"): 2,
        ("abc", "A", "chest"): 4, ("abc", "A", "triceps"): 3, ("abc", "A", "shoulders"): 2,
        ("abc", "B", "back"): 4, ("abc", "B", "biceps"): 3, ("abc", "B", "forearms"): 1, ("abc", "B", "traps"): 1,
        ("abc", "C", "quads"): 3, ("abc", "C", "hamstrings"): 3, ("abc", "C", "calves"): 2,
        ("abcd", "A", "chest"): 4, ("abcd", "A", "triceps"): 3,
        ("abcd", "B", "back"): 4, ("abcd", "B", "biceps"): 3,
        ("abcd", "C", "quads"): 3, ("abcd", "C", "hamstrings"): 2, ("abcd", "C", "shoulders"): 2,
        ("abcd", "D", "hamstrings"): 1, ("abcd", "D", "traps"): 2, ("abcd", "D", "calves"): 2,
        ("abcd", "D", "forearms"): 2, ("abcd", "D", "core"): 1,
        ("abcde", "A", "chest"): 4, ("abcde", "B", "back"): 4,
        ("abcde", "C", "quads"): 3, ("abcde", "C", "hamstrings"): 3, ("abcde", "C", "calves"): 2,
        ("abcde", "D", "shoulders"): 4, ("abcde", "D", "traps"): 2,
        ("abcde", "E", "biceps"): 3, ("abcde", "E", "triceps"): 3,
        ("abc2", "A", "chest"): 4, ("abc2", "A", "triceps"): 3,
        ("abc2", "B", "back"): 4, ("abc2", "B", "biceps"): 3,
        ("abc2", "C", "quads"): 3, ("abc2", "C", "hamstrings"): 3, ("abc2", "C", "shoulders"): 2,
    }

    def test_o_modelo_tem_o_minimo_da_formula_para_duas_opcoes(self):
        """Cada grupo anunciado de cada letra lista (contando os inativos)
        pelo menos `2·ceil(k/2) + floor(k/2)` exercícios — o mínimo
        matemático para duas opções com metade própria — sobre o `k` de
        hoje; e nas letras de referência do brief (peito e tríceps de
        `abc2`, `abcd`) o recomendado `2k`: peito 8, tríceps 6."""
        import math

        from workouts.models import WorkoutTemplate

        modelos = {(m.split, m.label): m for m in WorkoutTemplate.objects.filter(is_active=True)}
        for (split, letra, grupo), k in self.K_HOJE.items():
            itens = [i for i in modelos[(split, letra)].items.select_related("exercise")
                     if i.exercise.muscle_group == grupo]
            minimo = 2 * math.ceil(k / 2) + math.floor(k / 2)
            with self.subTest(modelo="%s %s" % (split, letra), grupo=grupo):
                self.assertGreaterEqual(len(itens), minimo)
        for split in ("abc2", "abcd"):
            a = modelos[(split, "A")]
            por_grupo = {}
            for item in a.items.select_related("exercise"):
                por_grupo[item.exercise.muscle_group] = por_grupo.get(item.exercise.muscle_group, 0) + 1
            self.assertEqual(por_grupo["chest"], 8, split)
            self.assertEqual(por_grupo["triceps"], 6, split)

    def test_o_seed_e_idempotente_com_os_novos(self):
        from workouts.models import Exercise, WorkoutTemplateItem

        antes = (
            dict(Exercise.objects.values_list("name", "is_active")),
            WorkoutTemplateItem.objects.count(),
        )
        call_command("seed_workouts", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        self.assertEqual(
            (dict(Exercise.objects.values_list("name", "is_active")), WorkoutTemplateItem.objects.count()),
            antes,
        )


class VolumeSemanalPorPropriedadeTests(TestCase):
    """Objetivo 4 (16/09/2026): a propriedade que vale para QUALQUER perfil.

    Sem `hypothesis` no ambiente, o domínio é percorrido INTEIRO — 3 níveis
    × 3 preferências × 6 frequências (2–7 dias) = 54 perfis, que é o espaço
    todo que `split_for` e `teto_semanal_de` distinguem. Um gerador aleatório
    cobriria menos que isso.

    A propriedade: escolher esta ou aquela opção NÃO muda o volume direto da
    semana em mais de uma série por grupo em cada sessão com opções. Para
    cada sessão e cada grupo, a opção mais pesada e a mais leve diferem em
    no máximo uma série direta; logo a semana toda, feita sempre com a mais
    pesada ou sempre com a mais leve, difere da projeção (opção 1 em toda
    sessão, `prescrever_semana`) em no máximo o número de sessões com opções.
    E todo grupo anunciado aparece em toda opção.
    """

    NIVEIS = ("iniciante", "intermediario", "avancado")
    PREFERENCIAS = ("one", "two", "three")
    DIAS = range(2, 8)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _plano(self, nivel, preferencia, dias):
        from django.utils import timezone

        user = create_complete_user(
            email="prop-%s-%s-%d@exemplo.com" % (nivel, preferencia, dias),
            experiencia=nivel, split_preference=preferencia, split_preference_confirmada=True,
            duracao_treino=DuracaoTreino.PADRAO,
        )
        TrainingDay.objects.filter(user=user).delete()
        for d in range(dias):
            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
        return services.create_routine(user)

    def _direto(self, itens):
        volume = {}
        for item in itens:
            volume[item.exercise.muscle_group] = volume.get(item.exercise.muscle_group, 0) + item.sets
        return volume

    def test_a_escolha_da_opcao_move_o_volume_direto_em_no_maximo_uma_serie_por_grupo(self):
        for nivel in self.NIVEIS:
            for preferencia in self.PREFERENCIAS:
                for dias in self.DIAS:
                    plano = self._plano(nivel, preferencia, dias)
                    sessoes = list(plano.sessions.prefetch_related("exercises__exercise"))
                    projecao, pesada, leve = {}, {}, {}
                    com_opcoes = 0
                    for sessao in sessoes:
                        volumes = [self._direto(sessao.da_opcao(k)) for k in sessao.opcoes]
                        anunciados = set(sessao.main_groups or [])
                        grupos = set().union(*(v.keys() for v in volumes))
                        if len(volumes) > 1:
                            com_opcoes += 1
                        for grupo in grupos:
                            valores = [v.get(grupo, 0) for v in volumes]
                            with self.subTest(perfil=(nivel, preferencia, dias), sessao=sessao.label, grupo=grupo):
                                self.assertLessEqual(max(valores) - min(valores), 1)
                                if grupo in anunciados:
                                    self.assertTrue(all(valores), "grupo anunciado ausente numa opção")
                            projecao[grupo] = projecao.get(grupo, 0) + valores[0]
                            pesada[grupo] = pesada.get(grupo, 0) + max(valores)
                            leve[grupo] = leve.get(grupo, 0) + min(valores)
                    for grupo in projecao:
                        with self.subTest(perfil=(nivel, preferencia, dias), grupo=grupo, semana=True):
                            self.assertLessEqual(pesada[grupo] - projecao[grupo], com_opcoes)
                            self.assertLessEqual(projecao[grupo] - leve[grupo], com_opcoes)
