"""TREINO — a nota da ficha só afirma o que aconteceu de verdade.

O DEFEITO, achado no navegador em 09/09/2026 com a conta de QA. A pessoa
respondeu "sem limite rígido" — não informou tempo nenhum — e a tela dizia,
dentro de "Detalhes do programa":

    A ficha foi ajustada para caber no tempo que você informou.

Nenhuma parte daquela frase era verdadeira. `escolher_para_o_tempo` não cortou
nada, porque sem faixa de tempo não há teto. Quem cortou foi
`aparar_volume_semanal`, que tira isolador redundante para o teto semanal do
grupo — e `aviso_de_tempo` media o corte contra o MODELO do catálogo, então
somava os dois cortes e creditava tudo ao relógio.

A régua nova é `prescrever_semana` com `teto=None`: a mesma prescrição, com o
volume já aparado e o relógio ainda não aplicado. A diferença entre ela e a
prescrição final é, por construção, exatamente o que o tempo tirou.

E O CORTE DE VOLUME CONTINUA SEM FRASE. Não é omissão: tirar o terceiro
isolador de peito da segunda passagem do dia A é o programa funcionando como
foi desenhado, e não uma limitação imposta à pessoa. Aviso que aparece para
todo mundo vira ruído e deixa de ser lido — é a mesma razão pela qual
`test_quando_nada_e_cortado_a_nota_nao_fala_de_tempo` já existia.
"""
from django.core.management import call_command
from django.test import TestCase

from accounts.models import DuracaoTreino, Profile

from . import services
from .tests import create_user


def com_faixa(email, faixa, dias=4):
    """Cria a pessoa com a faixa de duração e devolve o plano ativo.

    Recarrega o usuário do banco de propósito: `Profile` é `OneToOne` e fica em
    cache no objeto: sem isto o motor leria a faixa velha e o teste passaria
    medindo a ficha errada.
    """
    user = create_user(email=email, weekdays=tuple(range(dias)))
    Profile.objects.filter(user=user).update(duracao_treino=faixa)
    user = type(user).objects.get(pk=user.pk)
    return user, services.create_routine(user)


class ANotaNaoInventaUmCorteDeTempoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_sem_faixa_de_tempo_a_nota_nao_fala_de_tempo(self):
        """O defeito, na forma exata em que apareceu na tela."""
        _, plano = com_faixa("livre@exemplo.com", DuracaoTreino.LIVRE)

        self.assertNotIn("tempo que você informou", plano.notes)
        self.assertNotIn("Aumentar o tempo", plano.notes)

    def test_e_ainda_assim_o_volume_foi_aparado(self):
        """Controle do teste acima: sem ele, "nunca corta" passaria.

        O perfil de quatro dias PRECISA ter perdido exercício para o aparo —
        é o que torna o teste anterior uma prova. Se um dia o catálogo mudar e
        o aparo parar de cortar aqui, este teste avisa em vez de deixar o
        outro passar por vacuidade.
        """
        user, plano = com_faixa("livre-2@exemplo.com", DuracaoTreino.LIVRE)

        modelos = {t.label: t for t in services.templates_for(plano.split)}
        do_catalogo = sum(
            len(modelos[s.label].items.all()) for s in plano.sessions.all()
        )
        na_ficha = sum(s.exercises.count() for s in plano.sessions.all())

        self.assertLess(na_ficha, do_catalogo)

    def test_a_nota_de_tempo_aparece_quando_o_relogio_corta(self):
        """Controle positivo: a frase não virou letra morta."""
        _, plano = com_faixa("rapido@exemplo.com", DuracaoTreino.RAPIDO)

        self.assertIn("tempo que você informou", plano.notes)

    def test_nenhuma_faixa_sem_teto_produz_frase_de_tempo(self):
        """A propriedade, varrendo as quatro faixas.

        Só quem tem teto de minutos pode receber frase sobre tempo. `LIVRE` é
        a única sem teto hoje, e escrever a varredura em vez do caso isolado é
        o que pega uma quinta faixa criada amanhã sem teto.
        """
        for faixa in DuracaoTreino.values:
            with self.subTest(faixa=faixa):
                user, plano = com_faixa("faixa-%s@exemplo.com" % faixa, faixa)

                fala_de_tempo = "tempo que você informou" in plano.notes
                if services.teto_de_minutos(user) is None:
                    self.assertFalse(fala_de_tempo, plano.notes)

    def test_a_perda_de_grupo_tambem_e_medida_contra_o_relogio(self):
        """A frase pesada tem a mesma régua da leve, e por que isso importa.

        "Não cabem todos os grupos" promete que aumentar o tempo traz os
        outros de volta. Se a régua fosse o modelo, um grupo removido pelo
        aparo de volume dispararia a promessa — e aumentar o tempo não traria
        nada, porque não foi o tempo que tirou.
        """
        for faixa in (DuracaoTreino.LIVRE, DuracaoTreino.COMPLETO):
            with self.subTest(faixa=faixa):
                _, plano = com_faixa("grupo-%s@exemplo.com" % faixa, faixa)

                self.assertNotIn("não cabem todos os grupos", plano.notes)


class ARegraDaNotaEUmaFuncaoPuraTests(TestCase):
    """A unidade, exercitada direto — sem passar pelo gerador inteiro.

    Serve para a regra ficar legível: a frase depende de DUAS prescrições, e a
    diferença entre elas é a única entrada que importa.
    """

    class _Sessao:
        def __init__(self, pk):
            self.pk = pk

    class _Exercicio:
        def __init__(self, grupo):
            self.muscle_group = grupo

    class _Item:
        def __init__(self, grupo):
            self.exercise = ARegraDaNotaEUmaFuncaoPuraTests._Exercicio(grupo)

    def _mapa(self, pares):
        return {
            (sessao, i): (3, self._Item(grupo))
            for i, (sessao, grupo) in enumerate(pares)
        }

    def test_prescricoes_iguais_nao_geram_frase(self):
        sessoes = [self._Sessao(1)]
        mapa = self._mapa([(1, "chest"), (1, "triceps")])

        self.assertEqual(services.aviso_de_tempo(sessoes, mapa, mapa), "")

    def test_perder_exercicio_sem_perder_grupo_avisa_leve(self):
        sessoes = [self._Sessao(1)]
        sem_relogio = self._mapa([(1, "chest"), (1, "chest")])
        final = {k: v for k, v in list(sem_relogio.items())[:1]}

        nota = services.aviso_de_tempo(sessoes, final, sem_relogio)

        self.assertIn("ajustada para caber", nota)
        self.assertNotIn("para outra sessão da semana", nota)
        self.assertNotIn("em nenhuma sessão desta semana", nota)

    def test_perder_um_grupo_da_SEMANA_avisa_com_o_nome_do_musculo(self):
        """A frase mais pesada das três, e ela nomeia.

        A NOTA PASSOU A TER TRÊS FRASES em 10/09/2026, e este teste conhecia
        duas. A antiga dizia "no tempo que você informou não cabem todos os
        grupos do dia" para os dois casos pesados — o grupo que sai de UMA
        sessão e volta na outra, e o que some da semana inteira. São fatos
        diferentes e a pessoa precisa distingui-los: no primeiro a panturrilha
        volta na quarta, no segundo ela não volta em dia nenhum.

        Aqui a semana tem UMA sessão, então perder o tríceps dela é perdê-lo
        da semana. A frase nomeia o músculo, que é o que permite à pessoa
        decidir se aumenta o tempo ou acrescenta um dia.
        """
        sessoes = [self._Sessao(1)]
        sem_relogio = self._mapa([(1, "chest"), (1, "triceps")])
        final = {
            k: v for k, v in sem_relogio.items()
            if v[1].exercise.muscle_group == "chest"
        }

        nota = services.aviso_de_tempo(sessoes, final, sem_relogio)

        self.assertIn("em nenhuma sessão desta semana", nota)
        self.assertIn("tríceps", nota)
        self.assertIn("Aumentar o tempo", nota)

    def test_perder_um_grupo_de_UMA_sessao_diz_que_ele_volta(self):
        """O caso do meio, que a versão anterior confundia com o de cima.

        Duas sessões; o tríceps sai da primeira e fica na segunda. A ficha de
        segunda-feira tem um grupo a menos, e isso merece frase — mas a frase
        NÃO pode ser a de perda semanal, porque o tríceps é treinado na
        semana. Quem lesse "não coube em nenhuma sessão" concluiria que o
        programa dele não tem tríceps, e concluiria errado.
        """
        sessoes = [self._Sessao(1), self._Sessao(2)]
        sem_relogio = self._mapa(
            [(1, "chest"), (1, "triceps"), (2, "triceps")]
        )
        final = {
            k: v for k, v in sem_relogio.items()
            if not (k[0] == 1 and v[1].exercise.muscle_group == "triceps")
        }

        nota = services.aviso_de_tempo(sessoes, final, sem_relogio)

        self.assertIn("para outra sessão da semana", nota)
        self.assertIn("tríceps", nota)
        self.assertNotIn("em nenhuma sessão desta semana", nota)
