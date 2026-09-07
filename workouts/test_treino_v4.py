# -*- coding: utf-8 -*-
"""TREINO V4, fase A: o exercício sabe o que trabalha e onde a execução começa.

Três capacidades novas, e cada uma tem um jeito próprio de dar errado:

**O recorte do vídeo.** A demonstração quase nunca começa no zero — há
apresentação, conversa e posicionamento antes de alguém levantar o peso.
`video_start_seconds` leva o player direto ao movimento. O risco é a URL: um
parâmetro a mais, um `None` impresso, um `end` sem `start`, e o embed quebra
para os 36 exercícios de uma vez.

**Os músculos auxiliares.** O principal continua em `muscle_group`, de onde
`muscle_volume` tira a conta. O risco é semântico: acrescentar auxiliares e,
sem querer, começar a somar volume para eles — o que mudaria em silêncio todo
número que a tela de treino mostra.

**O seletor de mídia.** Ele troca o que se vê e nada mais. O risco é o estado:
uma troca que reinicie série, cronômetro ou progresso transformaria uma
curiosidade ("o que isso trabalha?") em perda de treino.
"""
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from workouts.models import Exercise, MuscleGroup


def exercicio(**extras):
    """Um exercício mínimo, com só o que os campos novos precisam."""
    dados = {
        "name": extras.pop("name", "Teste V4"),
        "muscle_group": extras.pop("muscle_group", MuscleGroup.CHEST),
        "equipment": "machine",
    }
    dados.update(extras)
    return Exercise(**dados)


class ORecorteDoVideoTests(TestCase):
    """`video_start_seconds` existe por UX, não por técnica: quem abre "ver
    execução" no meio da série quer o movimento, não a introdução."""

    VIDEO = "https://www.youtube.com/watch?v=abc123XYZ_1"

    def test_sem_timestamp_a_url_e_a_de_antes_do_campo_existir(self):
        """A compatibilidade dos 36 já cadastrados, dita byte a byte.

        Este é o teste que permite acrescentar o campo sem tocar em nenhum
        exercício: sem valor conferido, nada muda.
        """
        sem = exercicio(video_url=self.VIDEO).video_embed_url

        self.assertIn("/embed/abc123XYZ_1", sem)
        self.assertNotIn("start=", sem)
        self.assertNotIn("end=", sem)
        self.assertNotIn("None", sem)

    def test_so_o_inicio_entra_quando_so_ele_existe(self):
        url = exercicio(video_url=self.VIDEO, video_start_seconds=27).video_embed_url

        self.assertIn("&start=27", url)
        self.assertNotIn("end=", url)

    def test_inicio_e_fim_entram_juntos(self):
        url = exercicio(
            video_url=self.VIDEO, video_start_seconds=27, video_end_seconds=49
        ).video_embed_url

        self.assertIn("&start=27", url)
        self.assertIn("&end=49", url)

    def test_o_recorte_nao_atropela_os_parametros_que_ja_existiam(self):
        """O pedido era ESTENDER, não substituir. Privacidade, autoplay, mudo,
        loop e `playsinline` são decisões anteriores, cada uma com motivo
        escrito no modelo, e o recorte não pode custar nenhuma delas."""
        url = exercicio(
            video_url=self.VIDEO, video_start_seconds=27, video_end_seconds=49
        ).video_embed_url

        for pedaco in (
            "youtube-nocookie.com",
            "autoplay=1",
            "mute=1",
            "loop=1",
            "playlist=abc123XYZ_1",
            "playsinline=1",
            "rel=0",
        ):
            with self.subTest(parametro=pedaco):
                self.assertIn(pedaco, url)

    def test_a_query_tem_uma_interrogacao_so(self):
        """Concatenar errado produz `?a=1?start=2`, que o YouTube ignora
        inteiro — e a tela abriria no zero sem ninguém notar."""
        url = exercicio(
            video_url=self.VIDEO, video_start_seconds=27, video_end_seconds=49
        ).video_embed_url

        self.assertEqual(url.count("?"), 1)
        self.assertEqual(url.count("start="), 1)
        self.assertEqual(url.count("end="), 1)

    def test_zero_e_um_valor_conferido_e_nao_ausencia(self):
        """`0` significa "assisti, e começa no início"; `None` significa
        "ninguém conferiu". A diferença importa para saber o que falta
        curar — e um `if not inicio` colapsaria as duas."""
        url = exercicio(video_url=self.VIDEO, video_start_seconds=0).video_embed_url

        self.assertIn("&start=0", url)

    def test_sem_video_nao_ha_embed_nem_com_timestamp(self):
        vazio = exercicio(video_url="", video_start_seconds=27)

        self.assertEqual(vazio.video_embed_url, "")


class AValidacaoDoRecorteTests(TestCase):
    """As regras moram em `clean()`, e não só no formulário: seed, admin e
    `shell` escrevem direto no modelo."""

    def test_fim_menor_que_inicio_e_recusado(self):
        alvo = exercicio(video_start_seconds=40, video_end_seconds=20)

        with self.assertRaises(ValidationError) as caso:
            alvo.full_clean()

        self.assertIn("video_end_seconds", caso.exception.error_dict)

    def test_fim_igual_ao_inicio_e_recusado(self):
        """Recorte de duração zero não é recorte."""
        alvo = exercicio(video_start_seconds=30, video_end_seconds=30)

        with self.assertRaises(ValidationError):
            alvo.full_clean()

    def test_fim_sem_inicio_e_recusado(self):
        """Recorte pela metade: abriria no zero e pararia no meio, que é pior
        que não recortar."""
        alvo = exercicio(video_end_seconds=49)

        with self.assertRaises(ValidationError) as caso:
            alvo.full_clean()

        self.assertIn("video_end_seconds", caso.exception.error_dict)

    def test_o_par_valido_passa(self):
        """Controle positivo: sem ele, um `clean()` que recusasse tudo
        deixaria os três testes acima verdes."""
        exercicio(video_start_seconds=27, video_end_seconds=49).full_clean()

    def test_negativo_nao_cabe_no_campo(self):
        """`PositiveSmallIntegerField` já recusa; o teste prende a escolha do
        tipo, que é o que impede `&start=-5` de existir."""
        alvo = exercicio(video_start_seconds=-5)

        with self.assertRaises(ValidationError):
            alvo.full_clean()


class OsMusculosAuxiliaresTests(TestCase):
    def test_zero_auxiliares_e_o_padrao(self):
        """Isolador não tem auxiliar, e o campo nasce vazio — nenhum dos 36
        exercícios já cadastrados precisou ser tocado pela migration."""
        alvo = exercicio()

        self.assertEqual(alvo.secondary_muscles, [])
        self.assertEqual(alvo.secondary_muscle_labels, [])

    def test_um_auxiliar(self):
        alvo = exercicio(
            muscle_group=MuscleGroup.BICEPS, secondary_muscles=["forearms"]
        )
        alvo.full_clean()

        self.assertEqual(alvo.secondary_muscle_labels, ["Antebraço"])

    def test_varios_auxiliares_saem_na_ordem_da_taxonomia(self):
        """Ordem da taxonomia, e não a de digitação: duas pessoas cadastrando
        o mesmo exercício em ordens diferentes produziriam duas telas
        diferentes para o mesmo fato."""
        alvo = exercicio(secondary_muscles=["triceps", "shoulders"])
        alvo.full_clean()
        outro = exercicio(secondary_muscles=["shoulders", "triceps"])

        self.assertEqual(
            alvo.secondary_muscle_labels, outro.secondary_muscle_labels
        )
        self.assertEqual(alvo.secondary_muscle_labels, ["Ombros", "Tríceps"])

    def test_repetir_o_principal_e_recusado(self):
        """Um músculo é principal OU auxiliar. Repetido, apareceria duas vezes
        na tela e sugeriria estímulo duplo."""
        alvo = exercicio(
            muscle_group=MuscleGroup.CHEST, secondary_muscles=["chest", "triceps"]
        )

        with self.assertRaises(ValidationError) as caso:
            alvo.full_clean()

        self.assertIn("secondary_muscles", caso.exception.error_dict)

    def test_valor_fora_da_taxonomia_e_recusado(self):
        """É o que faz disto relação estruturada e não texto livre."""
        alvo = exercicio(secondary_muscles=["peitoral", "gluteos"])

        with self.assertRaises(ValidationError) as caso:
            alvo.full_clean()

        self.assertIn("secondary_muscles", caso.exception.error_dict)

    def test_auxiliar_repetido_na_propria_lista_e_recusado(self):
        alvo = exercicio(secondary_muscles=["triceps", "triceps"])

        with self.assertRaises(ValidationError):
            alvo.full_clean()

    def test_texto_solto_no_lugar_da_lista_e_recusado(self):
        """O caso que o pedido nomeia: `"triceps, ombro, peito"`."""
        alvo = exercicio(secondary_muscles="triceps, ombro")

        with self.assertRaises(ValidationError):
            alvo.full_clean()


class OVolumeNaoMudouTests(TestCase):
    """A regressão que mais importa nesta fase.

    Acrescentar auxiliares NÃO significa distribuir volume para eles. A conta
    de `muscle_volume` continua somando por `muscle_group`, e mudá-la seria
    decisão de produto com consequência matemática em toda tela de treino —
    fora do escopo desta fase, e por isso trancado aqui.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_volume_soma_pelo_principal_e_ignora_os_auxiliares(self):
        from workouts import views
        from workouts.models import WorkoutTemplate

        modelo = WorkoutTemplate.objects.filter(is_active=True).first()
        itens = list(modelo.items.select_related("exercise").all())
        self.assertTrue(itens, "o seed não trouxe itens")

        class SessaoFalsa:
            def __init__(self, itens):
                self._itens = itens

            @property
            def exercises(self):
                sessao = self

                class Gerente:
                    def all(self_):
                        return sessao._itens

                return Gerente()

        linhas = views.muscle_volume([SessaoFalsa(itens)])
        por_grupo = {linha["slug"]: linha["sets"] for linha in linhas}

        esperado = {}
        for item in itens:
            grupo = item.exercise.muscle_group
            esperado[grupo] = esperado.get(grupo, 0) + item.sets

        self.assertEqual(por_grupo, esperado)

    def test_ha_auxiliar_cadastrado_no_catalogo(self):
        """Controle positivo do teste acima: sem nenhum auxiliar no banco, ele
        provaria que ignorar lista vazia não muda nada — o que é trivial."""
        com_auxiliar = Exercise.objects.exclude(secondary_muscles=[]).count()

        self.assertGreater(com_auxiliar, 10, "o seed não cadastrou auxiliares")


class OCatalogoSemeadoEValidoTests(TestCase):
    """O arquivo de dados passa pela MESMA validação da tela.

    Um erro de digitação em `exercises.json` — "gluteos" em vez de
    "hamstrings" — apareceria como músculo faltando no drawer, e só quando
    alguém abrisse aquele exercício. Aqui ele aparece no teste.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_todo_exercicio_do_catalogo_passa_no_full_clean(self):
        for alvo in Exercise.objects.all():
            with self.subTest(exercicio=alvo.name):
                alvo.full_clean()

    def test_os_exemplos_do_pedido_estao_cadastrados(self):
        """Os casos que o dono citou, mapeados à taxonomia REAL do projeto.

        Onde a granularidade difere, o mapa está escrito: não existe `glutes`
        (o glúteo mora em `hamstrings`, cujo rótulo é "Posterior de coxa e
        glúteo"), nem `lats` (é `back`), nem `anterior_deltoid` (é
        `shoulders`). Inventar esses grupos criaria a segunda taxonomia que o
        pedido proíbe e quebraria `muscle_volume`.
        """
        esperado = {
            "Supino reto com barra": ("chest", {"triceps", "shoulders"}),
            "Puxada frente na polia": ("back", {"biceps", "forearms"}),
            "Rosca direta com barra": ("biceps", {"forearms"}),
            "Tríceps na polia com corda": ("triceps", set()),
            "Agachamento livre": ("quads", {"hamstrings", "core"}),
            "Stiff com barra": ("hamstrings", {"back", "core"}),
            "Panturrilha em pé": ("calves", set()),
        }
        for nome, (principal, auxiliares) in esperado.items():
            with self.subTest(exercicio=nome):
                alvo = Exercise.objects.get(name=nome)
                self.assertEqual(alvo.muscle_group, principal)
                self.assertEqual(set(alvo.secondary_muscles), auxiliares)

    def test_nenhum_timestamp_foi_inventado(self):
        """O pedido é explícito: timestamp é dado de produção, e chute não
        vira dado. Nenhum vídeo foi assistido para conferir onde a execução
        começa, então nenhum exercício do catálogo tem `start` — e o campo
        vazio é a verdade, não um buraco."""
        com_chute = Exercise.objects.exclude(video_start_seconds=None).count()

        self.assertEqual(com_chute, 0)


class OFimNuncaViajaSozinhoTests(TestCase):
    """A propriedade se defende sozinha, e não só pela validação.

    `clean()` recusa `end` sem `start` — mas `video_embed_url` é uma
    propriedade, e propriedade é lida de objetos que nunca passaram por
    `full_clean()`: um `Exercise(...)` montado no shell, um `update()` em
    massa, uma fixture antiga. A primeira versão desta bateria não cobria isso,
    e a sabotagem que desindentava o bloco do `end` passou VERDE: a URL saía
    com `&end=` e sem `&start=`, que é o recorte pela metade.
    """

    VIDEO = "https://www.youtube.com/watch?v=abc123XYZ_1"

    def test_fim_sem_inicio_nao_chega_na_url_nem_sem_validacao(self):
        # De propósito SEM `full_clean()`: o estado é inválido, e a pergunta é
        # o que a propriedade faz com ele.
        url = exercicio(video_url=self.VIDEO, video_end_seconds=49).video_embed_url

        self.assertNotIn("end=", url)
        self.assertNotIn("start=", url)

    def test_o_fim_depende_do_inicio_e_nao_o_contrario(self):
        """Controle positivo: com o par completo, os dois entram."""
        url = exercicio(
            video_url=self.VIDEO, video_start_seconds=27, video_end_seconds=49
        ).video_embed_url

        self.assertIn("&start=27", url)
        self.assertIn("&end=49", url)


class OContratoDoDrawerTests(TestCase):
    """O que o servidor precisa emitir para o drawer funcionar.

    A troca de mídia é JavaScript, e JavaScript não roda aqui — o que roda é o
    CONTRATO entre os dois: o gatilho carrega os dados, o markup tem os
    lugares, e o JS lê. Se o servidor parar de emitir `data-auxiliares`, a
    linha "Também trabalha" some da tela e nenhum teste de modelo notaria.

    O comportamento em si — trocar sem perder estado, quatro combinações de
    mídia, alvo de 44px — foi medido no navegador e está no relatório.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def ficha(self):
        """A ficha renderizada. A pessoa é criada UMA vez por teste.

        Criar a cada chamada estourava a unicidade de e-mail no segundo
        `ficha()` do mesmo teste — e o erro vinha como `IntegrityError` no
        meio de uma asserção sobre `start=27`, que não tem nada a ver.
        """
        from plans.tests import create_complete_user

        if not getattr(self, "_pessoa", None):
            self._pessoa = create_complete_user(email="drawer-v4@exemplo.com")
            self.client.force_login(self._pessoa)
        return self.client.get("/treino/").content.decode()

    def test_o_gatilho_carrega_os_auxiliares(self):
        html = self.ficha()

        self.assertIn("data-auxiliares=", html)
        # O VALOR do atributo, e não a palavra solta.
        #
        # A primeira versão assertava `"Tríceps" in html` — e "Tríceps" chega
        # ao HTML por cinco caminhos que nada têm a ver com o campo novo: o
        # nome do exercício de tríceps (que está em TODOS os splits), o
        # `data-nome`, o `data-musculo`, a pílula do alvo e o `aria-label`.
        # Fazer `secondary_muscle_labels` devolver `[]` deixava o teste verde.
        # Uma revisão adversarial mediu os cinco.
        self.assertIn('data-auxiliares="Ombros · Tríceps"', html)

    def test_a_linha_dos_auxiliares_nasce_escondida(self):
        """Isolador não tem auxiliar, e "Também trabalha: nenhum" seria ruído
        numa tela aberta entre duas séries."""
        html = self.ficha()

        trecho = html.split("data-drawer-auxiliares", 1)[1].split(">", 1)[0]
        self.assertIn("hidden", trecho)

    def test_o_embed_do_gatilho_leva_o_recorte_quando_ele_existe(self):
        """A ponta a ponta do timestamp: do banco até o atributo que o
        JavaScript lê para montar o `<iframe>`."""
        # O exercício tem de estar NA FICHA desta pessoa: a rotina gerada usa
        # um subconjunto do catálogo, e marcar um que não aparece provaria que
        # o atributo não vaza — não que ele chega. Foi o que a primeira versão
        # deste teste fez, e ela reprovou por isso.
        html = self.ficha()
        na_ficha = [
            alvo
            for alvo in Exercise.objects.filter(video_url__icontains="youtu")
            if alvo.name in html
        ]
        self.assertTrue(na_ficha, "a ficha não trouxe exercício com vídeo")

        alvo = na_ficha[0]
        alvo.video_start_seconds = 27
        alvo.video_end_seconds = 49
        alvo.full_clean()
        alvo.save()

        html = self.ficha()

        self.assertIn("start=27", html)
        self.assertIn("end=49", html)
