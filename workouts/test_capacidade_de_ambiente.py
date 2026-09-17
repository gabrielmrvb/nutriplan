"""TREINO — o que o catálogo sustenta em matéria de AMBIENTE, medido.

A PERGUNTA. O produto deveria deixar a pessoa dizer onde treina — academia
completa, casa com halteres, peso corporal — e a ficha mudar de verdade. Este
arquivo responde se dá, e a resposta de hoje é NÃO, com número — e o número
mudou em 17/09/2026, quando 28 exercícios com foto conferida entraram ativos
(63 ativos): "casa_halteres" passou de NAO_SUPORTADO a PARCIAL. Continua
sem consumidor no motor; o que este arquivo diz é o que o catálogo SUSTENTA.

POR QUE NÃO É "É SÓ FILTRAR". A prescrição não SELECIONA exercícios do
catálogo: `prescrever_semana` copia MODELOS curados de `splits.json`, com os
exercícios escritos por nome. Filtrar por equipamento não escolhe outro
exercício — ele abre um BURACO no modelo. Medido nos 15 modelos ativos:

    casa + halteres  ->  8 dos 15 modelos perdem grupo sem substituto,
                         e `abcde-C` termina com ZERO exercícios;
    peso corporal    -> 13 dos 15 perdem grupo sem substituto,
                         e SETE modelos terminam com zero.

É exatamente a ficha incompleta que a regra central proíbe: integridade da
prescrição vem antes da promessa de ambiente. (Os números acima são os de
10/09/2026, com 35 ativos; com os 63 de 17/09 "casa_halteres" não perde
grupo sem substituto e nenhuma sessão fica abaixo do piso — o que falta é
FOLGA, ver o fim deste texto.)

A VARREDURA COMPLETA, e ela é o que impede este arquivo de ser opinião. Cinco
equipamentos dão 31 recortes possíveis. Medidos todos, contra a régua da
`capacidade` abaixo: **um único é viável, e é o conjunto completo** — ou seja,
"completa", que é o comportamento de hoje. Nenhum recorte não trivial
passa.

A CAUSA ERA ESTRUTURAL, e eram três monopólios de equipamento no catálogo:

    abdômen e core -> 3 de 3 exercícios em peso do corpo
    antebraço      -> 2 de 2 em barra
    panturrilha    -> 2 de 2 em máquina

Qualquer recorte que exclua um desses três equipamentos perdia o grupo inteiro,
sem substituto. Desde 17/09/2026 sobrou UM: core continua 3 de 3 em peso do
corpo — antebraço ganhou a rosca de punho com halteres e panturrilha a em pé
com halteres. É por isso que "tirar o peso do corpo" continua não passando.

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
DUAS opções no ambiente. Medido quanto isso custava em 10/09: cobertura pedia 3
exercícios, folga pedia 10, e igualar a variedade da academia pedia 18. Em
17/09/2026 quatro dos nove candidatos com halteres entraram de verdade, com
foto conferida — stiff, panturrilha em pé, rosca de punho e agachamento
goblet —, e a conta da folga caiu de 10 para 3: panturrilha, posterior e
trapézio ainda têm UMA opção em casa + halteres. A tabela está no `BACKLOG.md`.
"""
import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from workouts import doutrina
from workouts.models import Equipment, Exercise, MuscleGroup, WorkoutTemplate

#: O que cada ambiente PERMITE, dito por extenso.
#:
#: "Casa + halteres" NÃO assume barra, máquina nem polia — assumir seria
#: transformar a promessa em outra promessa. E "peso_corporal" é o recorte
#: estrito: nada de banco, cadeira ou elástico. `Mergulho no banco` está no
#: catálogo como `bodyweight` e precisa de um banco; enquanto o modelo não
#: souber dizer "banco", o recorte estrito é o único que não mente.
#: Os QUATRO PERFIS do perfil (`accounts.models.Equipamento`), lidos do mapa
#: do `TREINO.md` — desde 17/09/2026 o produto pergunta, e o motor obedece
#: por substituição (`services.substituir_por_equipamento`). "casa + barra"
#: saiu: não é resposta que o perfil ofereça.
AMBIENTES = {perfil: doutrina.equipamentos_de(perfil) for perfil in doutrina.PERFIS_DE_EQUIPAMENTO}

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
        "completa": "SUPORTADO",
        "basica": "SUPORTADO",
        # PARCIAL desde 17/09/2026 (63 ativos): todo grupo coberto, nenhuma
        # sessão curta, três grupos sem folga — ver `OQueFaltaParaCasaComHalteresTests`.
        "casa_halteres": "PARCIAL",
        "peso_corporal": "NAO_SUPORTADO",
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

    def test_completa_e_basica_passam_e_completa_e_o_controle_positivo(self):
        """"Completa" ser SUPORTADO não é conquista: ela permite TUDO, então
        não restringe nada — serve de controle positivo (se nem ela passasse,
        a régua estaria quebrada). "Básica" (sem barra livre) passa por esta
        régua de folga; o que ela ainda perde é medido pelo teste dourado
        (`test_ficha_de_verdade.FichaDeVerdadePorEquipamentoTests`)."""
        aprovados = [n for n in AMBIENTES if self.veredito(n).status == "SUPORTADO"]

        self.assertEqual(aprovados, ["completa", "basica"])
        self.assertEqual(AMBIENTES["completa"], frozenset(Equipment.values))

    def test_o_filtro_ingenuo_esvaziaria_sessoes_inteiras(self):
        """O cenário que a regra central proíbe, medido em vez de afirmado.

        Em 10/09/2026 "casa_halteres" também zerava uma sessão
        (`abcde-C`); com os 63 ativos a pior sessão dela fica no piso, e é
        "peso_corporal" que continua esvaziando."""
        vazias = {}
        for nome in ("casa_halteres", "peso_corporal"):
            v = self.veredito(nome)
            vazias[nome] = v.pior

        self.assertGreaterEqual(vazias["casa_halteres"][1], PISO_DE_EXERCICIOS, vazias)
        self.assertEqual(vazias["peso_corporal"][1], 0, vazias)

    def test_os_tres_monopolios_de_equipamento(self):
        """A CAUSA, e não o sintoma.

        Enquanto um grupo inteiro depender de um único equipamento, todo
        recorte que exclua esse equipamento perde o grupo. Eram três em
        10/09/2026 (core, antebraço, panturrilha) e reprovavam 30 dos 31
        recortes; desde 17/09 sobrou o core, em peso do corpo.
        """
        monopolios = {}
        for grupo, exercicios in self.por_grupo.items():
            equipamentos = {e.equipment for e in exercicios}
            if len(equipamentos) == 1:
                monopolios[grupo] = (equipamentos.pop(), len(exercicios))

        self.assertEqual(
            monopolios,
            {MuscleGroup.CORE: (Equipment.BODYWEIGHT, 3)},
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


#: OS CINCO MOVIMENTOS QUE AINDA FALTAM DOS NOVE DE 10/09/2026.
#:
#: Os nove eram variantes com halteres de exercícios que já estavam no
#: catálogo, cadastrados, medidos e revertidos naquele dia porque não tinham
#: mídia. Em 17/09/2026 QUATRO entraram para valer, com foto conferida pelo
#: dono: `Stiff com halteres`, `Panturrilha em pé com halteres`,
#: `Rosca de punho com halteres` e `Agachamento goblet`. Estes cinco
#: continuam esperando mídia curada — e continuam a especificação: grupo,
#: `compound` e secundários vêm da origem, não são inventados.
CINCO_QUE_FALTAM = (
    ("Elevação pélvica com halteres", "Elevação pélvica", MuscleGroup.HAMSTRINGS),
    ("Panturrilha sentado com halteres", "Panturrilha sentado", MuscleGroup.CALVES),
    ("Rosca inversa com halteres", "Rosca inversa com barra", MuscleGroup.FOREARMS),
    ("Tríceps testa com halteres", "Tríceps testa com barra", MuscleGroup.TRICEPS),
    ("Remada alta com halteres", "Remada alta com barra", MuscleGroup.TRAPS),
)

#: Os quatro que entraram em 17/09/2026, e de onde cada um deriva.
QUATRO_QUE_ENTRARAM = (
    ("Stiff com halteres", "Stiff com barra", MuscleGroup.HAMSTRINGS),
    ("Panturrilha em pé com halteres", "Panturrilha em pé", MuscleGroup.CALVES),
    ("Rosca de punho com halteres", "Rosca de punho com barra", MuscleGroup.FOREARMS),
    ("Agachamento goblet", "Agachamento livre", MuscleGroup.QUADS),
)


class OQueFaltaParaCasaComHalteresTests(TestCase):
    """O QUE FALTA PARA CASA + HALTERES, MEDIDO COM O CATÁLOGO DE HOJE.

    Desde 17/09/2026 (tarde) o motor OBEDECE ao perfil "casa com halteres"
    por substituição (`services.substituir_por_equipamento`), e a letra A do
    dourado fecha nele; o que esta classe continua medindo é a FOLGA da
    semana inteira — os grupos com uma opção só —, que é a lista do
    `BACKLOG.md`.

    A ARMADILHA QUE ESTE ARQUIVO EXISTE PARA DESARMAR continua a mesma:
    COBERTURA não é QUALIDADE. Em 10/09/2026 a medição disse que três
    exercícios "resolviam" casa + halteres, e era verdade só para cobertura —
    com os três, sete dos onze grupos ficariam com UM exercício, e a semana
    cairia de 26-29 movimentos distintos para 13-14. Por isso a régua cobra
    FOLGA (duas opções por grupo usado), e por isso o veredito para em
    PARCIAL enquanto houver grupo sem folga.

    Hoje (17/09/2026, 63 ativos): nenhum grupo sem substituto, nenhuma sessão
    abaixo do piso, e TRÊS grupos sem folga — panturrilha, posterior e
    trapézio, cada um com uma opção só em halteres/peso do corpo. Três
    exercícios com mídia curada (a panturrilha sentado, a elevação pélvica e
    a remada alta com halteres, de `CINCO_QUE_FALTAM`) fecham a folga; o
    veredito só vira SUPORTADO com os três, e é este teste que fica vermelho
    nesse dia — notícia boa, e a hora de implementar o ambiente no motor.

    E O BLOQUEIO CONTINUA SENDO A MÍDIA. Exercício ativo tem contrato de
    quatro partes, defendido por nove guardas independentes; os cinco que
    faltam violam os quatro. Escolher vídeo exige assistir ao candidato, e
    este ambiente não assiste (`workouts/videos.py`). Os quatro que entraram
    entraram pela porta certa: foto conferida pelo dono, mosaico de veto,
    licença registrada (`curadoria` em `exercises.json`).
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    class Candidato:
        is_active = True
        equipment = Equipment.DUMBBELL

        def __init__(self, grupo):
            self.muscle_group = grupo

    def _por_grupo(self, com_os_cinco=False):
        por_grupo = defaultdict(list)
        for exercicio in Exercise.objects.filter(is_active=True):
            por_grupo[exercicio.muscle_group].append(exercicio)
        if com_os_cinco:
            for _, _, grupo in CINCO_QUE_FALTAM:
                por_grupo[grupo].append(self.Candidato(grupo))
        return por_grupo

    def _modelos(self):
        return list(
            WorkoutTemplate.objects.filter(is_active=True)
            .prefetch_related("items__exercise")
        )

    def test_os_quatro_entraram_e_os_cinco_ainda_nao(self):
        """A lista não envelhece em silêncio: o que entrou está ativo e
        deriva da origem certa; o que falta continua fora."""
        catalogo = {e.name: e for e in Exercise.objects.filter(is_active=True)}
        for nome, origem, grupo in QUATRO_QUE_ENTRARAM:
            with self.subTest(entrou=nome):
                self.assertIn(nome, catalogo, "saiu do catálogo ativo")
                self.assertEqual(catalogo[nome].equipment, Equipment.DUMBBELL)
                self.assertEqual(catalogo[nome].muscle_group, grupo)
                self.assertIn(origem, catalogo, "a origem sumiu do catálogo")
        for nome, origem, grupo in CINCO_QUE_FALTAM:
            with self.subTest(falta=nome):
                self.assertNotIn(nome, catalogo, "já foi cadastrado — releia este arquivo")
                self.assertIn(origem, catalogo, "a origem sumiu do catálogo")
                self.assertEqual(catalogo[origem].muscle_group, grupo)

    def test_casa_com_halteres_e_PARCIAL_por_tres_grupos_sem_folga(self):
        v = capacidade(AMBIENTES["casa_halteres"], self._modelos(),
                       self._por_grupo(), com_substituicao=True)

        self.assertEqual(v.status, "PARCIAL")
        self.assertEqual(v.sem_substituto, set())
        self.assertEqual(v.sessoes_curtas, [])
        self.assertEqual(
            v.sem_folga,
            {MuscleGroup.CALVES, MuscleGroup.HAMSTRINGS, MuscleGroup.TRAPS},
            "mudou o que falta — refaça a medição antes de mexer no BACKLOG",
        )

    def test_a_conta_do_que_falta_de_verdade(self):
        """Três exercícios com mídia fecham a folga. Era dez em 10/09/2026.

        FOLGA é o piso porque abaixo dele `aparar_volume_semanal` não tem o
        que ceder — e é ela que faz o teto por experiência valer.
        """
        por_grupo = self._por_grupo()
        permitidos = AMBIENTES["casa_halteres"]
        usados = {
            item.exercise.muscle_group
            for modelo in WorkoutTemplate.objects.filter(is_active=True)
            for item in modelo.items.all()
        }

        faltam = 0
        for grupo in usados:
            tem = len([e for e in por_grupo[grupo] if e.equipment in permitidos])
            faltam += max(0, 2 - tem)

        self.assertEqual(faltam, 3, "a conta da folga mudou — atualize o BACKLOG.md junto")

    def test_com_os_cinco_o_veredito_vira_SUPORTADO(self):
        """O controle positivo da régua: com os cinco cadastrados (três
        deles bastam), casa + halteres passa. É o dia de implementar o
        ambiente no motor — e de mover esta régua para junto dele."""
        v = capacidade(AMBIENTES["casa_halteres"], self._modelos(),
                       self._por_grupo(com_os_cinco=True), com_substituicao=True)

        self.assertEqual(v.status, "SUPORTADO")

    def test_o_contrato_de_midia_e_o_bloqueio_de_verdade(self):
        """Enquanto isto valer, exercício novo precisa de mídia curada.

        As quatro asserções são as mesmas que as nove guardas espalhadas pela
        suíte fazem — repetidas aqui juntas porque é a CONJUNÇÃO delas que
        explica por que os cinco candidatos não puderam ser cadastrados.
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


class OProdutoPrometeEquipamentoEOMotorObedeceTests(TestCase):
    """A outra metade, invertida em 17/09/2026: o perfil TEM a pergunta, o
    formulário a FAZ, e o motor LÊ `equipment`.

    Até 17/09 estes testes cobravam o contrário — sem campo no `Profile`, sem
    pergunta no onboarding, `equipment` sem leitor em `services.py` —, porque
    guardar preferência que o motor não obedece é mentira com banco de dados
    por trás. O motor passou a obedecer por SUBSTITUIÇÃO (mesmo padrão e
    grupo, `services.substituir_por_equipamento`), e a promessa que o perfil
    faz é exatamente a que a ficha cumpre: `workouts/test_equipamento.py`.
    """

    def test_o_perfil_guarda_o_equipamento_com_o_padrao_completa(self):
        from accounts.models import Equipamento, Profile

        campo = Profile._meta.get_field("equipamento")
        self.assertEqual(campo.default, Equipamento.COMPLETA)
        self.assertEqual({c for c, _ in campo.choices}, set(doutrina.PERFIS_DE_EQUIPAMENTO))

    def test_o_passo_de_treino_pergunta_o_equipamento(self):
        from accounts.forms import TrainingForm

        self.assertIn("equipamento", TrainingForm.base_fields)
        self.assertIn("experiencia", TrainingForm.base_fields)

    def test_o_motor_le_equipamento(self):
        """O leitor existe e é o único ponto de entrada: quem quiser saber o
        que o perfil pode usar passa por `permitidos_de` / `doutrina`."""
        from pathlib import Path

        fonte = (Path(__file__).resolve().parent / "services.py").read_text(encoding="utf-8")
        sem_prosa = "\n".join(
            linha for linha in fonte.splitlines() if not linha.lstrip().startswith("#")
        )
        self.assertIn("def substituir_por_equipamento(", sem_prosa)
        self.assertIn("item.exercise.equipment", sem_prosa)
        self.assertIn("permitidos=permitidos_de(user)", sem_prosa)
