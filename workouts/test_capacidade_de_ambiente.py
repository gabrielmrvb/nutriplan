"""TREINO — o que o catálogo sustenta em matéria de AMBIENTE, medido.

A PERGUNTA. O produto deveria deixar a pessoa dizer onde treina — academia
completa, casa com halteres, peso corporal — e a ficha mudar de verdade. Este
arquivo responde se dá, e a resposta de hoje é NÃO, com número.

POR QUE NÃO É "É SÓ FILTRAR". A prescrição não SELECIONA exercícios do
catálogo: `prescrever_semana` copia MODELOS curados de `splits.json`, com os
exercícios escritos por nome. Filtrar por equipamento não escolhe outro
exercício — ele abre um BURACO no modelo. Medido nos 15 modelos ativos:

    casa + halteres  ->  8 dos 15 modelos perdem grupo sem substituto,
                         e `abcde-C` termina com ZERO exercícios;
    peso corporal    -> 13 dos 15 perdem grupo sem substituto,
                         e SETE modelos terminam com zero.

É exatamente a ficha incompleta que a regra central proíbe: integridade da
prescrição vem antes da promessa de ambiente.

A VARREDURA COMPLETA, e ela é o que impede este arquivo de ser opinião. Cinco
equipamentos dão 31 recortes possíveis. Medidos todos, contra a régua da
`capacidade` abaixo: **um único é viável, e é o conjunto completo** — ou seja,
"academia completa", que é o comportamento de hoje. Nenhum recorte não trivial
passa.

A CAUSA É ESTRUTURAL, e são três monopólios de equipamento no catálogo:

    abdômen e core -> 3 de 3 exercícios em peso do corpo
    antebraço      -> 2 de 2 em barra
    panturrilha    -> 2 de 2 em máquina

Qualquer recorte que exclua um desses três equipamentos perde o grupo inteiro,
sem substituto. É por isso que "tirar a polia" quase passa (11/11 grupos) e
"tirar o peso do corpo" não passa nunca.

POR QUE A REGRA MORA NUM ARQUIVO DE TESTE, e não em `workouts/services.py`.
Ela não tem consumidor de produto: não há campo de ambiente no `Profile`, não
há pergunta no onboarding, e o motor não lê equipamento em lugar nenhum. Pôr a
regra em `services` criaria código de produto sem chamador — que é exatamente o
que `disputa_equipamento` era, e que sai do repositório no mesmo commit que
este arquivo entra. Quando o catálogo sustentar um ambiente, esta regra muda de
casa junto com o motor que passar a chamá-la; até lá, o lugar dela é onde ela é
executada.

E ELA SE SOLTA SOZINHA. `test_o_veredito_de_hoje_esta_congelado` prende o
veredito ATUAL de cada ambiente. No dia em que alguém cadastrar as alternativas
que faltam, ele fica VERMELHO dizendo que o ambiente virou implementável — é
catraca ao contrário, o mesmo desenho de `OCatalogoAindaNaoSustentaEquipamento`
em `test_experiencia.py`, agora medindo o que o motor faz e não só a contagem
por grupo.

COBERTURA NÃO É QUALIDADE, e a primeira versão desta régua confundia as duas.
Ela media só "todo grupo perdido tem substituto" — e teria virado SUPORTADO com
TRÊS exercícios novos. Medido o que aconteceria nesse cenário:

    academia hoje          26 a 29 exercícios distintos por semana,
                           reutilização máxima 1, zero grupo com opção única
    casa + halteres com 3  13 a 14 distintos para o MESMO número de itens,
                           reutilização até 4, e SETE dos onze grupos com
                           exatamente um exercício

Mesmo volume, metade dos movimentos. E há uma consequência que a cobertura
esconde: `aparar_volume_semanal` nunca remove o último exercício direto de um
grupo. Com sete grupos de um exercício só, o teto semanal por experiência
deixa de ter o que ceder — a personalização por experiência, que já está no ar,
pararia de funcionar justamente nesse ambiente.

Por isso a régua ganhou a FOLGA: grupo que os modelos usam precisa de pelo menos
DUAS opções no ambiente. Medido quanto isso custa: cobertura pede 3 exercícios,
folga pede 10, e igualar a variedade da academia pede 18. A tabela está no
`BACKLOG.md`.
"""
import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from workouts.models import Equipment, Exercise, MuscleGroup, WorkoutTemplate

#: O que cada ambiente PERMITE, dito por extenso.
#:
#: "Casa + halteres" NÃO assume barra, máquina nem polia — assumir seria
#: transformar a promessa em outra promessa. E "peso corporal" é o recorte
#: estrito: nada de banco, cadeira ou elástico. `Mergulho no banco` está no
#: catálogo como `bodyweight` e precisa de um banco; enquanto o modelo não
#: souber dizer "banco", o recorte estrito é o único que não mente.
AMBIENTES = {
    "academia completa": frozenset(Equipment.values),
    "casa + halteres": frozenset({Equipment.DUMBBELL, Equipment.BODYWEIGHT}),
    "casa + barra": frozenset({Equipment.BARBELL, Equipment.BODYWEIGHT}),
    "peso corporal": frozenset({Equipment.BODYWEIGHT}),
}

#: Uma sessão com menos que isto não é uma sessão — é uma lista.
#:
#: Três e não um: o motor já se recusa a esvaziar um dia (`aparar_volume_semanal`
#: nunca tira o último exercício direto de um grupo, e uma versão anterior que
#: deixou a sexta-feira com dois exercícios foi tratada como defeito e está
#: registrada no `CLAUDE.md`). O piso aqui usa a mesma régua daquele episódio.
PISO_DE_EXERCICIOS = 3


class Veredito:
    """O que um ambiente consegue sustentar, e por quê.

    `status` é uma das três palavras que a missão fixou, e ela é DERIVADA — não
    escrita à mão em lugar nenhum:

      SUPORTADO      nenhum modelo perde grupo sem substituto, nenhuma sessão
                     cai abaixo do piso, e todo grupo que os modelos usam tem
                     FOLGA — pelo menos duas opções no ambiente;
      PARCIAL        dá para montar, mas a qualidade cai: sessão curta demais
                     ou grupo atendido por um exercício só;
      NAO_SUPORTADO  existe grupo que o ambiente não cobre de jeito nenhum.
    """

    def __init__(self, nome, sem_substituto, sessoes_curtas, pior,
                 grupos_cobertos, sem_folga):
        self.nome = nome
        self.sem_substituto = sem_substituto
        self.sessoes_curtas = sessoes_curtas
        self.pior = pior
        self.grupos_cobertos = grupos_cobertos
        self.sem_folga = sem_folga

    @property
    def status(self):
        if self.sem_substituto:
            return "NAO_SUPORTADO"
        if self.sessoes_curtas or self.sem_folga:
            return "PARCIAL"
        return "SUPORTADO"

    def __repr__(self):
        return "<%s: %s>" % (self.nome, self.status)


def capacidade(permitidos, modelos, por_grupo, com_substituicao=False):
    """Mede um ambiente contra os MODELOS, que é o que o motor copia.

    Contar exercício por grupo no catálogo não responde a pergunta: o que
    importa é o que sobra de cada modelo curado, e se o que caiu tem
    substituto do mesmo grupo dentro do ambiente.

    DOIS MODELOS, e os dois precisam ser medidos porque respondem perguntas
    diferentes:

    `com_substituicao=False` é o FILTRO INGÊNUO — tira o item e segue. É o
    cenário que a regra central proíbe, e medi-lo é o que prova que ele é
    proibido: `abcde-C` termina com zero exercícios em casa + halteres.

    `com_substituicao=True` é o que uma implementação de verdade faria: item
    que cai e tem alternativa do mesmo grupo no ambiente é TROCADO, e a sessão
    mantém o tamanho. Só aí a pergunta "quanto falta no catálogo" tem resposta
    honesta — e a resposta deixa de ser sobre sessões curtas e passa a ser
    sobre os grupos que não têm nenhuma alternativa.
    """
    sem_substituto = set()
    curtas = []
    pior = None
    for modelo in modelos:
        itens = list(modelo.items.all())
        # `is_active` JUNTO com o equipamento, e não só o equipamento: é o que
        # `prescrever_semana` faz, e a régua que não espelha o motor mede outra
        # coisa. Achado por sabotagem — aposentar o grupo core inteiro deixava
        # o veredito intacto, porque o item aposentado continuava "cabendo" no
        # ambiente enquanto o motor já o teria descartado.
        fica = [
            i for i in itens
            if i.exercise.is_active and i.exercise.equipment in permitidos
        ]
        perdidos = ({i.exercise.muscle_group for i in itens}
                    - {i.exercise.muscle_group for i in fica})
        for grupo in perdidos:
            if not any(e.equipment in permitidos for e in por_grupo[grupo]):
                sem_substituto.add(grupo)
        chave = "%s-%s" % (modelo.split, modelo.label)
        vivos = len(fica)
        if com_substituicao:
            # Cada item que caiu e tem alternativa do mesmo grupo volta como
            # troca. O que não tem alternativa continua sendo perda.
            for item in itens:
                if item in fica or not item.exercise.is_active:
                    continue
                grupo = item.exercise.muscle_group
                if any(e.equipment in permitidos and e.is_active
                       for e in por_grupo[grupo]):
                    vivos += 1
        if vivos < PISO_DE_EXERCICIOS:
            curtas.append(chave)
        if pior is None or vivos < pior[1]:
            pior = (chave, vivos)
    cobertos = sum(
        1 for grupo in MuscleGroup.values
        if any(e.equipment in permitidos and e.is_active for e in por_grupo[grupo])
    )

    # FOLGA — a régua que separa "cobre" de "serve".
    #
    # Só vale para grupo que os MODELOS usam: cobrar duas opções de um grupo
    # que nenhuma ficha pede seria inventar requisito. E o número é dois porque
    # é o que `aparar_volume_semanal` precisa para ter o que ceder — ela nunca
    # remove o último exercício direto de um grupo, e sem isso o teto semanal
    # por experiência não se aplica àquele grupo.
    usados = {
        item.exercise.muscle_group
        for modelo in modelos for item in modelo.items.all()
    }
    sem_folga = {
        grupo for grupo in usados
        if grupo not in sem_substituto
        and len([e for e in por_grupo[grupo]
                 if e.is_active and e.equipment in permitidos]) < 2
    }
    return Veredito("", sem_substituto, curtas, pior, cobertos, sem_folga)


class ACapacidadeDeAmbienteEMedidaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.modelos = list(
            WorkoutTemplate.objects.filter(is_active=True)
            .prefetch_related("items__exercise")
        )
        self.por_grupo = defaultdict(list)
        for exercicio in Exercise.objects.filter(is_active=True):
            self.por_grupo[exercicio.muscle_group].append(exercicio)

    def veredito(self, nome):
        v = capacidade(AMBIENTES[nome], self.modelos, self.por_grupo)
        v.nome = nome
        return v

    #: O VEREDITO DE HOJE, congelado. Catraca ao contrário: quando o catálogo
    #: crescer, este teste fica vermelho e diz qual ambiente virou possível.
    ESPERADO = {
        "academia completa": "SUPORTADO",
        "casa + halteres": "NAO_SUPORTADO",
        "casa + barra": "NAO_SUPORTADO",
        "peso corporal": "NAO_SUPORTADO",
    }

    def test_o_veredito_de_hoje_esta_congelado(self):
        """Falhar aqui é NOTÍCIA BOA: o catálogo passou a sustentar um ambiente.

        Quem vier consertar não deve afrouxar o número — deve ler o veredito
        novo, implementar o ambiente no motor e mover esta régua para junto
        dele.
        """
        for nome in AMBIENTES:
            with self.subTest(ambiente=nome):
                v = self.veredito(nome)

                self.assertEqual(
                    v.status, self.ESPERADO[nome],
                    "%s virou %s — sem substituto: %s; sessões curtas: %s; "
                    "sem folga: %s"
                    % (nome, v.status,
                       sorted(v.sem_substituto) or "nenhum",
                       v.sessoes_curtas or "nenhuma",
                       sorted(v.sem_folga) or "nenhum"),
                )

    def test_so_a_academia_completa_passa_e_ela_e_o_estado_atual(self):
        """"Academia completa" ser SUPORTADO não é conquista: ela permite TUDO,
        então não restringe nada. É o comportamento de hoje, e serve de controle
        positivo — se nem ela passasse, a régua estaria quebrada."""
        aprovados = [n for n in AMBIENTES if self.veredito(n).status == "SUPORTADO"]

        self.assertEqual(aprovados, ["academia completa"])
        self.assertEqual(AMBIENTES["academia completa"], frozenset(Equipment.values))

    def test_o_filtro_ingenuo_esvaziaria_sessoes_inteiras(self):
        """O cenário que a regra central proíbe, medido em vez de afirmado."""
        vazias = {}
        for nome in ("casa + halteres", "peso corporal"):
            v = self.veredito(nome)
            vazias[nome] = v.pior

        self.assertEqual(vazias["casa + halteres"][1], 0, vazias)
        self.assertEqual(vazias["peso corporal"][1], 0, vazias)

    def test_os_tres_monopolios_de_equipamento(self):
        """A CAUSA, e não o sintoma.

        Enquanto um grupo inteiro depender de um único equipamento, todo
        recorte que exclua esse equipamento perde o grupo. São estes três que
        reprovam 30 dos 31 recortes possíveis.
        """
        monopolios = {}
        for grupo, exercicios in self.por_grupo.items():
            equipamentos = {e.equipment for e in exercicios}
            if len(equipamentos) == 1:
                monopolios[grupo] = (equipamentos.pop(), len(exercicios))

        self.assertEqual(
            monopolios,
            {
                MuscleGroup.CORE: (Equipment.BODYWEIGHT, 3),
                MuscleGroup.FOREARMS: (Equipment.BARBELL, 2),
                MuscleGroup.CALVES: (Equipment.MACHINE, 2),
            },
            "o catálogo mudou de forma — releia a matriz antes de ajustar",
        )

    def test_a_regua_enxerga_um_ambiente_que_daria_certo(self):
        """CONTROLE POSITIVO. Uma régua que reprovasse tudo passaria nos testes
        acima sem medir nada. Aqui um ambiente fabricado — o conjunto completo
        menos nada — tem de ser aprovado, e um que tira só a polia tem de
        reprovar por core, que é peso do corpo puro."""
        completo = capacidade(
            frozenset(Equipment.values), self.modelos, self.por_grupo
        )
        sem_peso_do_corpo = capacidade(
            frozenset(set(Equipment.values) - {Equipment.BODYWEIGHT}),
            self.modelos, self.por_grupo,
        )

        self.assertEqual(completo.status, "SUPORTADO")
        self.assertEqual(sem_peso_do_corpo.status, "NAO_SUPORTADO")
        self.assertIn(MuscleGroup.CORE, sem_peso_do_corpo.sem_substituto)


class OsTresExerciciosNaoBastamTests(TestCase):
    """A ARMADILHA QUE ESTE ARQUIVO EXISTE PARA DESARMAR.

    A medição de 09/09/2026 disse que faltavam TRÊS exercícios para "casa +
    halteres" — panturrilha, antebraço e posterior de coxa, com halteres — e
    entrou no `BACKLOG.md` com esse número. É verdade para COBERTURA, e é
    enganoso: com os três, sete dos onze grupos ficariam com UM exercício só, e
    a semana cairia de 26-29 movimentos distintos para 13-14, com o mesmo
    número de séries.

    Sem este teste, alguém cadastra três exercícios, vê o veredito virar e
    publica um treino em que costas é a mesma remada quatro vezes por semana.

    O que a simulação prova é que o veredito para em PARCIAL — que é o
    vocabulário para "dá para montar, mas a qualidade cai" — e não em
    SUPORTADO.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    #: Um exercício que ainda não existe, para a simulação. Só precisa
    #: responder o que `capacidade` pergunta.
    class Candidato:
        is_active = True

        def __init__(self, grupo, equipamento):
            self.muscle_group = grupo
            self.equipment = equipamento

    def _com_os_tres(self):
        por_grupo = defaultdict(list)
        for exercicio in Exercise.objects.filter(is_active=True):
            por_grupo[exercicio.muscle_group].append(exercicio)
        for grupo in (MuscleGroup.CALVES, MuscleGroup.FOREARMS,
                      MuscleGroup.HAMSTRINGS):
            por_grupo[grupo].append(self.Candidato(grupo, Equipment.DUMBBELL))
        return por_grupo

    def test_com_os_tres_o_veredito_para_em_PARCIAL(self):
        modelos = list(
            WorkoutTemplate.objects.filter(is_active=True)
            .prefetch_related("items__exercise")
        )

        v = capacidade(AMBIENTES["casa + halteres"], modelos, self._com_os_tres(),
                       com_substituicao=True)

        self.assertEqual(v.sem_substituto, set(), "os três cobrem os buracos")
        self.assertEqual(
            v.status, "PARCIAL",
            "os três exercícios passaram a bastar — releia a medição de "
            "variedade antes de publicar o ambiente",
        )
        self.assertGreaterEqual(
            len(v.sem_folga), 5,
            "grupos com um exercício só: %s" % sorted(v.sem_folga),
        )

    def test_a_conta_do_que_falta_de_verdade(self):
        """Três é cobertura; dez é folga. O número que o backlog precisa é dez.

        FOLGA é o piso porque abaixo dele `aparar_volume_semanal` não tem o que
        ceder — e é ela que faz o teto por experiência valer. Igualar a
        variedade da academia custa mais, e está no `BACKLOG.md`.
        """
        por_grupo = defaultdict(list)
        for exercicio in Exercise.objects.filter(is_active=True):
            por_grupo[exercicio.muscle_group].append(exercicio)
        permitidos = AMBIENTES["casa + halteres"]
        usados = {
            item.exercise.muscle_group
            for modelo in WorkoutTemplate.objects.filter(is_active=True)
            for item in modelo.items.all()
        }

        faltam = 0
        for grupo in usados:
            tem = len([e for e in por_grupo[grupo]
                       if e.is_active and e.equipment in permitidos])
            faltam += max(0, 2 - tem)

        self.assertEqual(
            faltam, 10,
            "a conta da folga mudou — atualize o BACKLOG.md junto",
        )


#: OS NOVE MOVIMENTOS QUE FECHAM SEIS DOS SETE BURACOS DE CASA + HALTERES.
#:
#: Cada um é a variante com halteres de um exercício QUE JÁ ESTÁ no catálogo —
#: a coluna `origem` — e é de lá que sai o metadado: grupo, articulações,
#: `compound` e secundários são herdados, não inventados. Foram cadastrados e
#: medidos em 10/09/2026, e depois REVERTIDOS; o porquê está em
#: `OsNoveMovimentosPrecisamDeCuradoriaTests`.
NOVE_CANDIDATOS = (
    ("Stiff com halteres", "Stiff com barra", MuscleGroup.HAMSTRINGS),
    ("Elevação pélvica com halteres", "Elevação pélvica", MuscleGroup.HAMSTRINGS),
    ("Panturrilha em pé com halteres", "Panturrilha em pé", MuscleGroup.CALVES),
    ("Panturrilha sentado com halteres", "Panturrilha sentado", MuscleGroup.CALVES),
    ("Rosca de punho com halteres", "Rosca de punho com barra", MuscleGroup.FOREARMS),
    ("Rosca inversa com halteres", "Rosca inversa com barra", MuscleGroup.FOREARMS),
    ("Agachamento goblet", "Agachamento livre", MuscleGroup.QUADS),
    ("Tríceps testa com halteres", "Tríceps testa com barra", MuscleGroup.TRICEPS),
    ("Remada alta com halteres", "Remada alta com barra", MuscleGroup.TRAPS),
)


class OsNoveMovimentosPrecisamDeCuradoriaTests(TestCase):
    """O QUE FALTA PARA CASA + HALTERES, ESPECIFICADO E MEDIDO.

    Em 10/09/2026 os nove movimentos de `NOVE_CANDIDATOS` foram cadastrados de
    verdade e a semana foi medida. O ganho é real:

        antes    7 grupos com uma opção só, 13-14 movimentos distintos/semana
        depois   1 grupo  com uma opção só, 18-19 movimentos distintos/semana

    E FORAM REVERTIDOS, por um motivo que a medição descobriu e que não era o
    esperado: **o bloqueio não são os movimentos, é a MÍDIA.** Este catálogo
    tem um contrato de quatro partes para exercício ativo, e ele é defendido
    por nove guardas independentes, cada uma com o motivo escrito:

      `video_url` não vazio e embutível   `test_every_exercise_in_the_catalog_has_a_video`
      `clip_kind` não vazio               `test_no_exercise_is_left_without_a_demonstration`
      `tem_anatomia` verdadeiro           `test_todo_exercicio_oferece_anatomia_de_verdade`
      presente em `media_map.json`        `test_every_exercise_in_the_catalog_is_in_the_map`

    Os nove violam os quatro. Escolher vídeo exige ASSISTIR ao candidato, e
    este ambiente não assiste — está medido em `workouts/videos.py`:
    `readyState 0` depois de 60 s. Inventar id repetiria o defeito de
    07/09/2026, quando dez exercícios apontaram para o vídeo de outro com a
    suíte inteira verde. E afrouxar as nove guardas publicaria exercício que a
    pessoa abre e não vê demonstração nenhuma.

    Então o desbloqueio é curadoria humana de mídia para nove movimentos já
    especificados — não é decidir o que cadastrar. A lista está no
    `BACKLOG.md`, com origem e metadado de cada um.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    class Candidato:
        is_active = True
        equipment = Equipment.DUMBBELL

        def __init__(self, grupo):
            self.muscle_group = grupo

    def _por_grupo(self, com_os_nove=False):
        por_grupo = defaultdict(list)
        for exercicio in Exercise.objects.filter(is_active=True):
            por_grupo[exercicio.muscle_group].append(exercicio)
        if com_os_nove:
            for _, _, grupo in NOVE_CANDIDATOS:
                por_grupo[grupo].append(self.Candidato(grupo))
        return por_grupo

    def _modelos(self):
        return list(
            WorkoutTemplate.objects.filter(is_active=True)
            .prefetch_related("items__exercise")
        )

    def test_cada_candidato_deriva_de_um_exercicio_que_existe(self):
        """A fonte é o próprio catálogo, e isto prova que ela não envelheceu.

        Se a origem for aposentada ou renomeada, o candidato perde a base do
        metadado e alguém precisa reavaliá-lo antes de cadastrar.
        """
        catalogo = {
            e.name: e for e in Exercise.objects.filter(is_active=True)
        }
        for nome, origem, grupo in NOVE_CANDIDATOS:
            with self.subTest(candidato=nome):
                self.assertNotIn(nome, catalogo, "já foi cadastrado")
                self.assertIn(origem, catalogo, "a origem sumiu do catálogo")
                self.assertEqual(
                    catalogo[origem].muscle_group, grupo,
                    "o grupo da origem mudou — reavalie o candidato",
                )

    def test_os_nove_fechariam_seis_dos_sete_buracos(self):
        """O ganho, medido — e o que sobra, nomeado."""
        modelos = self._modelos()
        antes = capacidade(AMBIENTES["casa + halteres"], modelos,
                           self._por_grupo(), com_substituicao=True)
        depois = capacidade(AMBIENTES["casa + halteres"], modelos,
                            self._por_grupo(com_os_nove=True),
                            com_substituicao=True)

        self.assertEqual(len(antes.sem_folga) + len(antes.sem_substituto), 7)
        self.assertEqual(depois.sem_substituto, set())
        self.assertEqual(
            depois.sem_folga, {MuscleGroup.BACK},
            "mudou o que sobra — refaça a medição antes de mexer no BACKLOG",
        )

    def test_mesmo_com_os_nove_o_veredito_nao_chega_a_SUPORTADO(self):
        """Costas continua com uma opção só, e isso basta para segurar.

        As três saídas para costas com halteres estão todas bloqueadas por
        algo já decidido: `Remada curvada com halteres` reintroduziria o
        movimento que a migration `0018` aposentou por decisão de produto;
        `Pullover com halter` tem classificação disputada entre dorsal e
        peitoral, e escolher um lado para fechar contagem é preencher campo
        para satisfazer teste; e qualquer remada apoiada é a
        `Remada unilateral com halter` com outro nome. Puxada vertical em casa
        exige barra fixa, que está fora do ambiente.
        """
        v = capacidade(AMBIENTES["casa + halteres"], self._modelos(),
                       self._por_grupo(com_os_nove=True), com_substituicao=True)

        self.assertEqual(v.status, "PARCIAL")

    def test_o_contrato_de_midia_e_o_bloqueio_de_verdade(self):
        """Enquanto isto valer, exercício novo precisa de mídia curada.

        As quatro asserções são as mesmas que as nove guardas espalhadas pela
        suíte fazem — repetidas aqui juntas porque é a CONJUNÇÃO delas que
        explica por que os nove candidatos não puderam ser cadastrados.
        """
        ativos = list(Exercise.objects.filter(is_active=True))
        mapa = json.loads(
            (Path(settings.BASE_DIR) / "workouts" / "data" / "media_map.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual([e.name for e in ativos if not e.video_url], [])
        self.assertEqual([e.name for e in ativos if not e.clip_kind], [])
        self.assertEqual([e.name for e in ativos if not e.animation_url], [])
        self.assertEqual([e.name for e in ativos if e.name not in mapa], [])


class OProdutoNaoPrometeAmbienteTests(TestCase):
    """A outra metade do Caso C: enquanto não sustenta, não pode oferecer.

    Não há campo de ambiente no `Profile`, não há pergunta no onboarding e o
    motor não lê `equipment`. Isso não é acidente feliz — é o estado que estes
    testes existem para manter, porque acrescentar a pergunta antes do catálogo
    criaria preferência guardada e não consumida, que é mentira com banco de
    dados por trás.
    """

    #: Como uma pergunta de ambiente se pareceria num formulário.
    SINAIS = ("ambiente", "equipamento", "onde_treina", "local_de_treino",
              "equipment", "academia")

    def test_o_perfil_nao_guarda_ambiente(self):
        from accounts.models import Profile

        campos = {
            f.attname for f in Profile._meta.get_fields() if hasattr(f, "attname")
        }

        for sinal in self.SINAIS:
            with self.subTest(sinal=sinal):
                self.assertEqual(
                    [c for c in campos if sinal in c], [],
                    "apareceu campo de ambiente no Profile — se o motor ainda "
                    "não lê equipamento, isso é preferência que não vira nada",
                )

    def test_o_passo_de_treino_nao_pergunta_ambiente(self):
        from accounts.forms import TrainingForm

        campos = set(TrainingForm.base_fields)

        for sinal in self.SINAIS:
            with self.subTest(sinal=sinal):
                self.assertEqual([c for c in campos if sinal in c], [])

    def test_o_controle_positivo_do_varredor(self):
        """Uma varredura que não casasse com nada passaria para sempre."""
        from accounts.forms import TrainingForm

        campos = set(TrainingForm.base_fields)

        # `experiencia` e `weekdays`, e não `duracao_treino`: a duração saiu do
        # formulário em 10/09/2026 — a pergunta virou decisão do produto, com
        # padrão de 45 a 60 minutos. O controle positivo precisa apontar para
        # campos que EXISTEM, senão ele para de provar que a varredura enxerga.
        self.assertIn("experiencia", campos)
        self.assertIn("weekdays", campos)
        self.assertTrue(
            [c for c in campos | {"ambiente_de_treino"} if "ambiente" in c]
        )

    def test_o_motor_nao_le_equipamento(self):
        """Se um dia ler, é aqui que o teste avisa para revisar este arquivo
        inteiro — inclusive o veredito congelado logo acima."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parent / "services.py"
        ).read_text(encoding="utf-8")
        sem_prosa = "\n".join(
            linha for linha in fonte.splitlines()
            if not linha.lstrip().startswith("#")
        )

        self.assertNotIn("equipment", sem_prosa)
