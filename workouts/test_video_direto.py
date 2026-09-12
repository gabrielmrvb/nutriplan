# -*- coding: utf-8 -*-
"""A tela do exercício mostra o VÍDEO REAL, e mostra o vídeo que o dono escolheu.

POR QUE ESTE ARQUIVO EXISTE.

Duas tentativas de responder "o que este exercício trabalha" com desenho saíram
do produto. A primeira foi um Short de terceiro em `animation_url` — metade se
chamava "<exercício> — Músculos Trabalhados", um deles trazia banner de personal
concorrente, e o supino levava onze segundos de diagrama antes de alguém deitar
no banco. A segunda foi o mapa muscular em SVG, com Frente/Costas e um seletor
"Vídeo real | Anatomia". O dono avaliou as duas e decidiu: a tela do exercício é
o vídeo da execução, direto, sem escolha no meio.

A informação anatômica NÃO se perdeu — ela virou texto, "Principal" e "Também
trabalha", que saem de `muscle_group` e `secondary_muscles`. Há teste aqui para
isso, porque "remover o desenho" e "remover o dado" são coisas diferentes e a
segunda seria uma perda de produto.

E OS 36 VÍDEOS SÃO CURADORIA HUMANA. O dono escolheu um por um, à mão. A tabela
`OFICIAIS` abaixo é essa escolha, e é a razão principal deste arquivo existir:
qualquer coisa que troque um vídeo — um seed remendado, um `update` no banco,
um merge malfeito — fica vermelha aqui, com o nome do exercício e os dois IDs.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from workouts.models import Exercise, MuscleGroup
from workouts.videos import MOVIMENTO_ESPERADO, titulo_confere

RAIZ = Path(settings.BASE_DIR)
# `_drawer.html` e `_exercicio.html` saíram do repositório em 10/09/2026: sem
# `{% include %}` em template nenhum, eram 1.050 linhas que ninguém emitia. A
# tela do exercício é `agora.html`, e `ATelaDaExecucaoEODoVideoTests` a lê.

#: O exercício legado. Ele não está no seed, não tem vídeo e não aparece em
#: ficha nenhuma — e `migrations/0017` o DESATIVA em vez de apagar porque
#: `ExerciseLog.exercise` é **CASCADE** (`models.py:843`), não `PROTECT`:
#: apagar a linha levaria o histórico de carga junto, sem aviso. As duas
#: relações que SÃO `PROTECT` são `WorkoutTemplateItem` e `TrainingSession`.
LEGADO = "Remada curvada"

#: OS 36 VÍDEOS OFICIAIS, escolhidos à mão pelo dono do produto.
#:
#: Chave = nome exibido; valor = ID do YouTube. O ID e não a URL inteira porque
#: é o ID que chega ao `<iframe>`: `video_embed_url` monta
#: `youtube-nocookie.com/embed/<id>`, e é a comparação de ID que impede um
#: exercício de servir o vídeo de outro.
OFICIAIS = {
    "Abdominal supra no solo": "vRDR_MmFHcI",
    "Afundo com halteres": "a5zYhGUSp-8",
    "Agachamento livre": "4PbHkCEUI6I",
    "Barra fixa assistida": "lRCROSJkTKM",
    "Cadeira extensora": "PzIfB9MiiX8",
    "Cadeira flexora": "T46yKiz8laY",
    "Crucifixo inverso na máquina": "wUT3hmnzq3c",
    "Crucifixo na máquina (voador)": "zEcIgGm7fxU",
    "Desenvolvimento com halteres": "5I7ogOjvdnc",
    "Elevação de pernas": "In0EzoOAILw",
    "Elevação frontal com halteres": "GqZRmCow0rw",
    "Elevação lateral com halteres": "ot9nwSC1JnA",
    "Elevação pélvica": "cOvGedlKlD4",
    "Encolhimento com halteres": "x9Im5d1H-Xw",
    "Flexão de braço": "qqECekG4jMo",
    "Leg press 45°": "NY5fw4Zaofg",
    "Mergulho no banco": "Q07t33qOow0",
    "Mesa flexora": "IXg1PQ_5gmw",
    "Panturrilha em pé": "fVGkOlkOrnA",
    "Panturrilha sentado": "9fIw0ue8iQE",
    "Prancha abdominal": "yZaYCfWS3mQ",
    "Puxada frente na polia": "_2MfZAj98tk",
    "Remada alta com barra": "emPow6X_a_E",
    "Remada baixa na polia": "7lc8Ow4vIwA",
    "Remada curvada com barra": "e53vSzibkO0",
    "Remada unilateral com halter": "OhQTM6Mkq-E",
    "Rosca alternada com halteres": "WUrn8iFf1js",
    "Rosca de punho com barra": "kJtnD6Orr5A",
    "Rosca direta com barra": "dc330H9yN3Y",
    "Rosca inversa com barra": "mcUpjlWlGZY",
    "Rosca martelo": "0rRpv6o140o",
    "Stiff com barra": "6ZbS3jXheMw",
    "Supino inclinado com halteres": "ZaNyRjpoki8",
    "Supino reto com barra": "UHa9U-O09_U",
    "Tríceps na polia com corda": "-QGC1cL6ETE",
    "Tríceps testa com barra": "40Cx-IfJhA0",
}


class OsTrintaESeisVideosOficiaisTests(TestCase):
    """A curadoria manual do dono, travada exercício por exercício."""

    @classmethod
    def setUpTestData(cls):
        # O banco de teste nasce vazio; o catálogo vem do seed, que é a MESMA
        # fonte que o build do Render usa. Testar contra o banco de
        # desenvolvimento provaria que alguém rodou o seed lá, e não que o
        # arquivo versionado está certo.
        call_command("seed_workouts", verbosity=0)

    #: Exercícios do catálogo que saíram do uso ATIVO, por decisão de produto.
    #:
    #: Nomeados um a um de propósito. Derivar a lista do próprio JSON deixaria
    #: o teste concordar com qualquer aposentadoria, inclusive a acidental —
    #: aposentar passa a exigir uma edição aqui, que é onde alguém pergunta
    #: "por quê".
    APOSENTADOS = {"Remada curvada com barra"}

    def test_o_catalogo_ativo_tem_exatamente_os_nomes_oficiais_vivos(self):
        """Nem um a mais, nem um a menos.

        Um exercício novo que entrasse no seed sem vídeo curado passaria
        despercebido por qualquer teste que só varresse os conhecidos: ele
        não estaria na lista, então ninguém perguntaria por ele. A igualdade de
        CONJUNTOS é o que fecha os dois lados.

        Em 08/09/2026 o conjunto ativo deixou de ser "todos os oficiais": a
        `Remada curvada com barra` foi aposentada por decisão de produto e
        continua no catálogo, com o vídeo, para o histórico de quem treinou com
        ela poder ser lido.
        """
        ativos = set(
            Exercise.objects.filter(is_active=True).values_list("name", flat=True)
        )
        self.assertEqual(ativos, set(OFICIAIS) - self.APOSENTADOS)

    def test_o_aposentado_continua_no_catalogo_com_o_video(self):
        """Controle do teste acima, e a razão de aposentar em vez de apagar.

        `ExerciseLog.exercise` é CASCADE: um `delete()` levaria junto o
        histórico de carga. Se alguém "limpar" o catálogo apagando o
        aposentado, este teste cai antes de o dado sumir.
        """
        for nome in self.APOSENTADOS:
            with self.subTest(exercicio=nome):
                velho = Exercise.objects.filter(name=nome).first()
                self.assertIsNotNone(velho, "o aposentado foi APAGADO")
                self.assertFalse(velho.is_active)
                self.assertTrue(velho.video_url, "o vídeo do aposentado sumiu")

    def test_cada_exercicio_serve_o_video_que_o_dono_escolheu(self):
        """ID a ID — e o ID, não a URL.

        Comparar URL deixaria passar `youtu.be/<id>` contra
        `youtube.com/shorts/<id>`: endereços diferentes, mesmo vídeo. E
        comparar só "tem vídeo" deixaria passar o defeito que este teste existe
        para pegar, que é um exercício servir o clipe de outro.
        """
        for nome, esperado in sorted(OFICIAIS.items()):
            with self.subTest(exercicio=nome):
                servido = Exercise.objects.get(name=nome).video_id
                self.assertEqual(servido, esperado)

    def test_nenhum_video_e_usado_por_dois_exercicios(self):
        """Repetir um ID é o sintoma mais provável de erro de digitação na
        curadoria — e ele não aparece comparando um exercício de cada vez."""
        ids = [e.video_id for e in Exercise.objects.filter(is_active=True)]
        self.assertEqual(len(ids), len(set(ids)), "há ID repetido no catálogo")

    def test_o_embed_de_todos_e_montavel_e_sem_cookie(self):
        """`clip_kind` vazio faz a tela cair no plano B. Com os 36 curados,
        nenhum pode cair — e o embed é `youtube-nocookie`, que é o que impede
        o YouTube de plantar cookie de rastreio em quem só abriu a ficha."""
        for exercicio in Exercise.objects.filter(is_active=True).order_by("name"):
            with self.subTest(exercicio=exercicio.name):
                self.assertEqual(exercicio.clip_kind, "youtube")
                self.assertIn(
                    "youtube-nocookie.com/embed/" + OFICIAIS[exercicio.name],
                    exercicio.video_embed_url,
                )

    def test_o_seed_e_a_fonte_e_o_banco_concorda_com_ele(self):
        """O SEED RODA EM TODO BUILD e faz upsert.

        Trocar o vídeo só no banco é uma correção que o próximo deploy desfaz,
        em silêncio, e o defeito reaparece semanas depois sem ninguém ligar uma
        coisa à outra. Este teste roda o seed DE NOVO sobre o banco de teste e
        exige que nada mude: se `exercises.json` e o catálogo divergirem, a
        segunda passada devolve o valor do arquivo e a comparação quebra.
        """
        call_command("seed_workouts", verbosity=0)
        for nome, esperado in sorted(OFICIAIS.items()):
            with self.subTest(exercicio=nome):
                self.assertEqual(Exercise.objects.get(name=nome).video_id, esperado)

    def test_o_json_do_seed_nao_guarda_token_de_compartilhamento(self):
        """Os links chegaram com `?is=...`, que é token de compartilhamento do
        aplicativo do YouTube. Ele não muda o vídeo — o parser lê o caminho —,
        mas este repositório é PÚBLICO, e token de conta de alguém não entra em
        arquivo versionado por descuido."""
        bruto = (RAIZ / "workouts" / "data" / "exercises.json").read_text(
            encoding="utf-8"
        )
        for chave in ("?is=", "&is=", "?si=", "&si="):
            with self.subTest(chave=chave):
                self.assertNotIn(chave, bruto)



class AIdentidadeDoVideoTests(TestCase):
    """O par exercício -> vídeo é conferido pelo CONTEÚDO, não só pela URL.

    A CLASSE NASCEU DE UM DEFEITO QUE PASSOU POR TODOS OS OUTROS TESTES.

    Em 07/09/2026 dez exercícios abriam o vídeo de outro exercício: o supino
    reto mostrava tríceps na polia, a rosca martelo mostrava supino, o stiff
    mostrava rosca inversa. A suíte estava verde — porque cada teste comparava
    a URL cadastrada com a URL esperada, e as duas eram a MESMA URL errada. Um
    teste que só sabe qual URL deveria estar lá não consegue perceber que a
    URL certa aponta para o vídeo errado.

    A âncora nova é o TÍTULO do vídeo, capturado do oEmbed público do YouTube
    no dia da curadoria e gravado em `exercises.json` como `video_titulo`. Ele
    é dado do conteúdo, não da nossa expectativa — e é isso que faz esta
    classe morder onde as outras não mordiam.

    O LIMITE ESTÁ DITO: título não é imagem. Um vídeo bem intitulado que mostre
    outra coisa atravessa daqui. Conferir o quadro exige assistir, e este
    ambiente não assiste vídeo do YouTube.
    """

    def setUp(self):
        self.catalogo = json.loads(
            (RAIZ / "workouts" / "data" / "exercises.json").read_text(
                encoding="utf-8")
        )

    def test_todo_exercicio_com_video_declara_o_titulo_dele(self):
        """Sem o título gravado não há o que conferir, e o guarda vira enfeite."""
        sem = [x["name"] for x in self.catalogo
               if x.get("video") and not x.get("video_titulo")]
        self.assertEqual(sem, [], "exercício com vídeo e sem `video_titulo`")

    def test_o_titulo_gravado_menciona_o_movimento_do_exercicio(self):
        """ESTE é o teste que teria pego a troca.

        Com o par embaralhado, "Supino reto com barra" carregava o título
        "Tríceps pulley corda" — e nenhuma palavra de supino aparece ali.
        """
        for linha in self.catalogo:
            if not linha.get("video"):
                continue
            with self.subTest(exercicio=linha["name"]):
                self.assertTrue(
                    titulo_confere(linha["name"], linha["video_titulo"]),
                    "%r aponta para um vídeo intitulado %r, que não menciona "
                    "o movimento" % (linha["name"], linha["video_titulo"]),
                )

    #: Exercícios cujo vídeo ANUNCIA peso corporal, e que a prescrição carrega
    #: em quilos. É dívida de CURADORIA, não de código: trocar exige escolher
    #: outro vídeo e conferir o que ele mostra, e este ambiente não assiste
    #: vídeo. Inventar um id seria repetir o defeito de 07/09/2026 — dez
    #: exercícios apontando para o vídeo de outro, com a suíte verde.
    #:
    #: A lista é uma CATRACA: ela não pode crescer. Enquanto o vídeo do
    #: agachamento não for trocado por uma demonstração com barra, ele fica
    #: aqui, nomeado, e nenhum exercício novo entra sem alguém decidir.
    VIDEO_SEM_CARGA_CONHECIDO = {"Agachamento livre"}

    def test_video_de_peso_corporal_nao_se_espalha(self):
        """A ficha prescreve carga em quilos; o vídeo não pode ensinar sem ela.

        Auditado em produção: "Agachamento livre" abre "Agachamento Livre Peso
        Corporal | Bodyweight Free Squat". O movimento é o mesmo, a execução
        que a ficha manda fazer não é — quem segue o vídeo faz agachamento sem
        barra e anota 80 kg no histórico.

        O guarda não conserta a curadoria; ele impede que ela piore, e nomeia o
        caso que falta. É a mesma catraca de `TETO_*` no sistema visual.
        """
        import re as _re

        sem_carga = _re.compile(r"peso corporal|bodyweight|sem peso|calistenia",
                                _re.I)
        achados = {
            linha["name"]
            for linha in self.catalogo
            if linha.get("video_titulo") and sem_carga.search(linha["video_titulo"])
        }

        novos = achados - self.VIDEO_SEM_CARGA_CONHECIDO
        self.assertEqual(
            novos, set(),
            "exercício com carga apontando para vídeo de peso corporal: %s"
            % sorted(novos),
        )

    def test_a_catraca_do_video_sem_carga_nao_esta_folgada(self):
        """O teto É a dívida, e não um número com folga.

        Sem isto, alguém consertaria o agachamento, deixaria o nome na lista, e
        a catraca aceitaria um exercício novo com o mesmo defeito sem reclamar.
        """
        import re as _re

        sem_carga = _re.compile(r"peso corporal|bodyweight|sem peso|calistenia",
                                _re.I)
        achados = {
            linha["name"]
            for linha in self.catalogo
            if linha.get("video_titulo") and sem_carga.search(linha["video_titulo"])
        }

        self.assertEqual(achados, self.VIDEO_SEM_CARGA_CONHECIDO)

    def test_a_tabela_de_movimentos_cobre_o_catalogo_inteiro(self):
        """`titulo_confere` devolve True para exercício que não está na tabela
        — é o que impede um exercício novo de derrubar o build. O preço é que
        a ausência silencia o guarda, então a ausência é o que se testa aqui."""
        self.assertEqual(
            {x["name"] for x in self.catalogo}, set(MOVIMENTO_ESPERADO)
        )

    def test_dois_exercicios_nunca_dividem_o_mesmo_video(self):
        """Movimento diferente, vídeo diferente. Vídeo repetido é o sintoma
        mais barato de detectar de uma curadoria que escorregou de linha."""
        ids = [x["video"].rsplit("/", 1)[-1] for x in self.catalogo
               if x.get("video")]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(repetidos, [], "vídeo usado por mais de um exercício")

    def test_o_seed_casa_por_NOME_e_nunca_por_posicao(self):
        """A CAUSA QUE NÃO ERA. Quando a troca apareceu, a primeira hipótese
        foi associação posicional — `videos[i] -> exercicios[i]` —, e a
        investigação mostrou que não existe: o seed usa `name` como chave. Este
        teste congela isso, porque o dia em que alguém introduzir um `zip()`
        entre duas listas aqui, o embaralhamento volta em silêncio.
        """
        fonte = (RAIZ / "workouts" / "management" / "commands"
                 / "seed_workouts.py").read_text(encoding="utf-8")
        sem_comentario = re.sub(r"#.*$", "", fonte, flags=re.M)

        # SÓ A FUNÇÃO QUE GRAVA O VÍDEO. A primeira versão varria o arquivo
        # inteiro e reprovou por causa de um `enumerate()` de `_seed_splits`,
        # que numera a ORDEM dos exercícios dentro do treino e não tem nada a
        # ver com mídia. Guarda que reprova código correto é guarda que alguém
        # desliga.
        inicio = sem_comentario.index("def _seed_exercises(self)")
        fim = sem_comentario.index("def _seed_splits(self", inicio)
        trecho = sem_comentario[inicio:fim]

        self.assertIn('name=row["name"]', trecho)
        self.assertIn('row.get("video", "")', trecho)
        for posicional in ("zip(", "videos[", "VIDEOS[", "enumerate(", "[i]"):
            with self.subTest(posicional=posicional):
                self.assertNotIn(posicional, trecho)


class OLegadoFicaDesativadoTests(TestCase):
    """Desativar preserva o histórico; apagar o levaria junto.

    O legado NÃO existe no banco de teste — ele não está no seed, e é por isso
    que a migração `0017` o procura em vez de criá-lo. Então o que se testa
    aqui é a FUNÇÃO da migração, com a linha montada à mão do jeito que ela
    está em produção: `is_active=True` e `muscle_group="costas"`, valor de
    quando a taxonomia era em português.

    Testar contra o banco de desenvolvimento provaria que a migração já rodou
    aqui, e não que ela FAZ o que diz — que é o que precisa valer no dia em
    que ela rodar em produção.
    """

    @staticmethod
    def _rodar_a_migracao():
        import importlib

        from django.apps import apps as registro

        modulo = importlib.import_module(
            "workouts.migrations.0017_desativa_remada_curvada_legada"
        )
        modulo.desativar(registro, None)

    def test_a_migracao_desativa_o_legado_e_preserva_a_linha(self):
        Exercise.objects.create(
            name=LEGADO, muscle_group="costas", equipment="machine", is_active=True
        )

        self._rodar_a_migracao()

        legado = Exercise.objects.filter(name=LEGADO).first()
        self.assertIsNotNone(legado, "a migração APAGOU a linha — o histórico ia junto")
        self.assertFalse(legado.is_active)

    def test_a_migracao_conserta_o_grupo_muscular_invalido(self):
        """Desativar não tira o exercício do histórico, e a tela de histórico
        chama `get_muscle_group_display()` — que devolve `"costas"` cru quando
        o valor está fora de `MuscleGroup`."""
        Exercise.objects.create(
            name=LEGADO, muscle_group="costas", equipment="machine", is_active=True
        )

        self._rodar_a_migracao()

        self.assertIn(Exercise.objects.get(name=LEGADO).muscle_group, MuscleGroup.values)

    def test_a_migracao_nao_reclama_quando_o_legado_nao_existe(self):
        """Em banco novo — o de teste, o de um colaborador — a linha não
        existe. `filter().update()` devolve zero e segue; um `get()` teria
        derrubado a migração e, com ela, o build."""
        self._rodar_a_migracao()
        self.assertFalse(Exercise.objects.filter(name=LEGADO).exists())

    def test_o_legado_nao_esta_no_seed(self):
        """Se ele voltasse ao `exercises.json`, o seed o reativaria no próximo
        build: `is_active` sai de `row.get("active", True)`."""
        catalogo = json.loads(
            (RAIZ / "workouts" / "data" / "exercises.json").read_text(encoding="utf-8")
        )
        self.assertNotIn(LEGADO, {linha["name"] for linha in catalogo})







class ATelaDaExecucaoEODoVideoTests(TestCase):
    """A demonstração é do exercício aberto, e é uma só.

    CONSOLIDA NOVE TESTES DE DUAS CLASSES que liam `_drawer.html` e
    `_exercicio.html`. Os dois parciais saíram do repositório nesta missão:
    zero `{% include %}` em template nenhum, 1.050 linhas que ninguém emitia.

    O que eles guardavam não era a gaveta — era o que a gaveta fazia certo, e
    isso continua valendo na tela que ficou no lugar dela:

        `id="drawer-media"` único        -> um `<iframe>` por tela
        `media.innerHTML = ""` antes     -> nada de player vivo escondido
        `montarClipe` antes de `Quadros` -> a escada de mídia
        `media.hidden = !montou`         -> sem mídia, sem caixa preta
        sem seletor de mídia             -> a execução não pode virar anatomia

    A DIFERENÇA É QUE AGORA A MAIOR PARTE É DO SERVIDOR. A escada virou um
    `{% if %}` sobre `execucao_tipo`, e "limpar ao fechar" deixou de existir
    como problema: a página inteira é o exercício, e trocar de exercício é
    trocar de página. Um `setInterval` esquecido não sobrevive a uma navegação.
    """

    @classmethod
    def setUpTestData(cls):
        cls.agora = (
            RAIZ / "templates" / "workouts" / "agora.html"
        ).read_text(encoding="utf-8")
        cls.limpo = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", cls.agora,
            flags=re.S,
        )

    def test_a_execucao_monta_UM_player_e_o_recorte_enxerga(self):
        """Controle positivo junto: um `_sem_comentarios` que apagasse o
        arquivo inteiro deixaria toda asserção de ausência verde para sempre.
        """
        self.assertIn("agora__media", self.limpo)
        self.assertEqual(self.limpo.count("<iframe"), 1)

    def test_a_escada_de_midia_e_do_SERVIDOR_e_tem_uma_ordem(self):
        """Clipe, vídeo, gif, fotos — e a busca quando não há nada.

        Era `montarClipe` antes de `montarQuadros` dentro de `montarMidia`; a
        ordem é a mesma, escrita em `{% if %}`. Ancorado nas POSIÇÕES, porque o
        defeito de agosto foi de ordem e não de ausência: quem tocava "Ver
        vídeo de execução" recebia o diagrama de músculos, com o banner de um
        personal concorrente por cima.
        """
        posicoes = [
            self.limpo.index("execucao_tipo == 'youtube'"),
            self.limpo.index("execucao_tipo == 'video'"),
            self.limpo.index("execucao_tipo == 'gif'"),
            self.limpo.index("execucao_tipo == 'fotos'"),
        ]
        self.assertEqual(posicoes, sorted(posicoes))

    def test_sem_midia_a_tela_diz_isso_em_vez_de_ficar_preta(self):
        """§16 da decisão: sem vídeo, nada de player vazio nem caixa preta.

        Medido no navegador na versão do drawer: um exercício sem vídeo e sem
        foto abria com um retângulo chapado de 228×405 no topo. Aqui o `{% else %}`
        entrega texto e a busca no YouTube — os 36 ativos têm vídeo, então este
        ramo não é alcançável hoje, e é exatamente por isso que ele precisa de
        teste: ninguém vai encontrar o defeito usando o app.
        """
        ramo = self.limpo.split("execucao_tipo == 'fotos'", 1)[1]
        ramo = ramo.split("</div>", 1)[0]
        self.assertIn("agora__sem-media", ramo)
        self.assertIn("Sem demonstração cadastrada", ramo)
        self.assertIn("video_search_url", ramo)

    def test_a_execucao_nao_tem_seletor_de_midia_nenhum(self):
        """O INVARIANTE FICOU MAIS FORTE, e por isso mudou de forma.

        Havia um ternário escolhendo a mídia inicial, e um teste medindo que
        `execucao` vinha antes de `anatomia` nele. A trava passou a ser a
        AUSÊNCIA do seletor, que é mais forte que a ordem dentro dele — e
        atravessou a troca de tela intacta.
        """
        for morto in ("data-drawer-midias", "data-drawer-midia=",
                      "drawer.dataset.midia", "drawer--duas-midias",
                      "montarAnimacao", "mapa_muscular", "corpo__vista"):
            with self.subTest(morto=morto):
                self.assertNotIn(morto, self.limpo)

    def test_a_anatomia_continua_secundaria_e_calada(self):
        """O DADO ANATÔMICO FICA; o que saiu foi o desenho e a prioridade.

        `animation_url` guarda conteúdo anatômico — metade dos vídeos de lá se
        chama "<exercício> - Músculos Trabalhados", e o supino levava onze
        segundos de diagrama antes de alguém deitar no banco. Ele continua no
        app, embaixo, atrás de um `<details>`, e o embed só nasce quando alguém
        abre: iframe dentro de `<details>` fechado é baixado e TOCADO pelo
        navegador, e esses vídeos trazem publicidade de terceiro.
        """
        self.assertIn("data-anatomia-area", self.limpo)
        self.assertIn("tem_anatomia", self.limpo)

        # O `src` mora num atributo, e vira elemento só no `toggle`.
        self.assertIn('data-anatomia="{{ atual.exercise.anatomia_src }}"', self.limpo)
        corpo = self.limpo.split('detalhe.addEventListener("toggle"', 1)[1]
        corpo = corpo.split("});", 1)[0]
        self.assertIn("if (!detalhe.open)", corpo)
        self.assertIn('corpo.innerHTML = ""', corpo)

    def test_o_video_da_execucao_e_o_do_exercicio_aberto(self):
        """A ponta a ponta: o `src` sai do exercício da vez, e de mais ninguém.

        É o que `id="drawer-media"` único protegia por outro caminho — uma
        caixa só, para a limpeza alcançar. Aqui a caixa é a página.
        """
        self.assertIn('src="{{ atual.exercise.execucao_src }}"', self.limpo)
        self.assertIn('title="Execução de {{ atual.exercise.name }}"', self.limpo)
