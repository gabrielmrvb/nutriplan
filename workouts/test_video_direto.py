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
FICHA = RAIZ / "templates" / "workouts" / "routine.html"
GATILHO = RAIZ / "templates" / "workouts" / "_exercicio.html"

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

    def test_o_catalogo_ativo_tem_exatamente_os_36_nomes(self):
        """Nem um a mais, nem um a menos.

        Um exercício novo que entrasse no seed sem vídeo curado passaria
        despercebido por qualquer teste que só varresse os 36 conhecidos: ele
        não estaria na lista, então ninguém perguntaria por ele. A igualdade de
        CONJUNTOS é o que fecha os dois lados.
        """
        ativos = set(
            Exercise.objects.filter(is_active=True).values_list("name", flat=True)
        )
        self.assertEqual(ativos, set(OFICIAIS))

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



class ATelaDoExercicioEODoVideoTests(TestCase):
    """A Anatomia saiu da interface, e o vídeo abre sem toque intermediário."""

    def setUp(self):
        self.ficha = FICHA.read_text(encoding="utf-8")
        self.gatilho = GATILHO.read_text(encoding="utf-8")
        # Este projeto comenta muito, e os comentários CITAM o nome do que
        # saiu — é a armadilha que o CLAUDE.md registra. Sem tirá-los, um
        # `assertNotIn("Anatomia")` reprova por causa da própria explicação.
        self.ficha_limpa = self._sem_comentarios(self.ficha)
        self.gatilho_limpo = self._sem_comentarios(self.gatilho)

    @staticmethod
    def _sem_comentarios(fonte):
        fonte = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", fonte, flags=re.S
        )
        fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
        return re.sub(r"^\s*//.*$", "", fonte, flags=re.M)

    def test_a_ficha_nao_oferece_anatomia_em_lugar_nenhum(self):
        """O controle positivo está nas duas primeiras asserções: sem ele, um
        `_sem_comentarios` que apagasse o arquivo inteiro deixaria este teste
        verde para sempre."""
        self.assertIn("data-drawer-media", self.ficha_limpa)
        self.assertIn("data-drawer-musculo", self.ficha_limpa)

        for morto in ("Anatomia", "data-drawer-anatomia", "data-drawer-midia",
                      "corpo__vista", "mapa_muscular", "Frente", "Costas",
                      "pintarCorpo", "mostrarVista", "temAnatomia"):
            with self.subTest(morto=morto):
                self.assertNotIn(morto, self.ficha_limpa)

    def test_o_gatilho_nao_carrega_mais_dado_de_anatomia(self):
        """`data-destaques` e `data-vista` viajavam em CADA gatilho da ficha da
        semana. Sem leitor, são bytes multiplicados por exercício."""
        for morto in ("data-destaques", "data-vista", "data-animacao"):
            with self.subTest(morto=morto):
                self.assertNotIn(morto, self.gatilho_limpo)

    def test_o_gatilho_continua_publicando_principal_e_auxiliares(self):
        """O DADO ANATÔMICO FICA. O que saiu foi o desenho."""
        self.assertIn("data-musculo=", self.gatilho_limpo)
        self.assertIn("data-auxiliares=", self.gatilho_limpo)

    def test_abrir_o_drawer_monta_a_midia_sem_escolha_no_meio(self):
        """`preencher` chama `montarMidia` direto, sem consultar seletor.

        Ancorado na CHAMADA e não na definição: `assertIn("montarMidia")`
        casaria com `function montarMidia(...)` e passaria mesmo se ninguém a
        chamasse — é o falso positivo que este repositório já pagou duas vezes.
        """
        corpo = self.ficha.split("function preencher(dados) {", 1)[1]
        corpo = corpo.split("\n        }", 1)[0]
        self.assertIn("montarMidia(media, dados);", corpo)

    def test_sem_midia_a_caixa_some_em_vez_de_ficar_preta(self):
        """§16 da decisão: sem vídeo, nada de player vazio nem caixa preta.

        `--vertical` sai de `data-vertical`, que é do CADASTRO: ela dimensiona
        a caixa mesmo quando nenhum construtor montou nada. Medido no
        navegador, um exercício sem vídeo e sem foto abria o drawer com um
        retângulo chapado de 228×405 no topo.

        Os 36 ativos têm vídeo, então este ramo não é alcançável hoje — e é
        exatamente por isso que ele precisa de teste: ninguém vai encontrar o
        defeito usando o app.
        """
        corpo = self.ficha.split("function montarMidia(media, dados) {", 1)[1]
        corpo = corpo.split("\n        }", 1)[0]
        self.assertIn("media.hidden = !montou;", corpo)
        self.assertLess(
            corpo.index("montarClipe"), corpo.index("media.hidden = !montou;"),
            "a caixa some antes de alguém tentar montar a mídia",
        )

    def test_a_regra_de_16_por_9_do_seletor_saiu_junto(self):
        """`.drawer--duas-midias .drawer__media--vertical` prendia o Short em
        16:9 para trocar de mídia não fazer a caixa pular de tamanho. Sem
        seletor ela é letra morta, e mantê-la roubaria metade da área útil do
        vídeo: os 36 são verticais, e `--vertical` sozinha dá 9:16."""
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        # SEM OS COMENTÁRIOS — a armadilha do CLAUDE.md, e ela mordeu aqui na
        # primeira execução: o comentário que EXPLICA a remoção cita o nome do
        # seletor removido, e o teste reprovou por causa da própria explicação.
        regras = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotIn("drawer--duas-midias", regras)
        self.assertIn(".drawer__media--vertical {", regras)


class UmIframeVivoPorVezTests(TestCase):
    """Vídeo escondido tocando atrás é bateria e dado do bolso alheio."""

    def setUp(self):
        self.ficha = FICHA.read_text(encoding="utf-8")

    def test_montar_a_midia_esvazia_a_caixa_antes_de_encher(self):
        """Tirar o `<iframe>` do documento é o que ENCERRA o vídeo. A ordem
        importa: esvaziar depois de anexar deixaria o novo de fora."""
        corpo = self.ficha.split("function montarMidia(media, dados) {", 1)[1]
        corpo = corpo.split("\n        }", 1)[0]
        self.assertIn('media.innerHTML = "";', corpo)
        self.assertLess(
            corpo.index('media.innerHTML = "";'), corpo.index("montarClipe")
        )

    def test_fechar_o_drawer_limpa_a_midia_pelos_tres_caminhos(self):
        """Botão, Esc e clique no fundo. `<dialog>` avisa por `cancel` e por
        `close`; sem os dois, sair pelo teclado deixava o clipe tocando."""
        self.assertIn('drawer.addEventListener("cancel", limparMidia)', self.ficha)
        self.assertIn('drawer.addEventListener("close", limparMidia)', self.ficha)
        self.assertIn("function fecharDrawer() {", self.ficha)

    def test_existe_uma_caixa_de_midia_so_no_documento(self):
        """Duas caixas seriam dois iframes vivos, e a limpeza só alcança a que
        ela conhece.

        Ancorado no `id`, que é único por definição, e não na contagem de
        `data-drawer-media`: essa string aparece também nos `querySelector` do
        JavaScript, então o número esperado mudaria a cada função nova que
        procurasse a caixa — um teste que quebra quando nada quebrou.
        """
        self.assertEqual(self.ficha.count('id="drawer-media"'), 1)
        self.assertEqual(self.ficha.count('class="drawer__media"'), 1)
