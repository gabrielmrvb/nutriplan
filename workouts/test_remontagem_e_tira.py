# -*- coding: utf-8 -*-
"""A REMONTAGEM NÃO ZERA A SEQUÊNCIA; A TIRA NÃO INVENTA FALTA (28/09/2026).

Caça-bugs de 27/09 (`achados/caca-bugs-20260927.md`), duas personas, o
mesmo defeito: B4 — remontar a ficha ("regenerar", trocar o equipamento,
mudar os dias) fazia o app esquecer o que a pessoa tinha feito. Persona 2
fez A no domingo e B na terça; depois da remontagem o Treino recomendou A
na sexta, A de novo no sábado, e C (pernas) só apareceu no 10º dia. A tira
marcou como `pulado` ("·") os dias que ela TREINOU, no mesmo instante em
que o Progresso dizia "4 de 4" e as Conquistas "Semana completa". A causa:
`sequencia_do_treino` lia só as escolhas do plano ATUAL.

A regra da sequência por presença não muda (CLAUDE.md, 24/09/2026): o
recomendado é a letra SEGUINTE à última FEITA. O que muda é de quem é a
presença — da PESSOA, não da ficha. A ficha é retrato; o que a pessoa fez
continua feito depois que o retrato é trocado.

Junto, três achados vizinhos:

- item 8 (auditoria visual): a tira marcava `pulado` os dias de treino de
  ANTES de a conta existir — falta inventada, e o chip apagado a 2,86:1;
- M1: aceitar "regenerar" com série hoje (o pedido fica para amanhã) não
  tirava a pergunta da Home até a aba Treino ser aberta;
- BA4: o mapa dia↔letra depois da primeira volta do ciclo.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import expectedFailure

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, TrainingDay
from config import relogio
from plans.tests import create_complete_user
from workouts import services
from workouts.models import EscolhaDeTreino, TrainingPlan
from workouts.test_planos_ativos import _mudar_a_prescricao
from workouts.test_sequencia import fazer

SEGUNDA = date(2026, 9, 14)  # uma segunda-feira
QUARTA = SEGUNDA + timedelta(days=2)
QUINTA = SEGUNDA + timedelta(days=3)


def _pessoa(email, dias=(0, 1, 2, 3, 4)):
    """ABC em cinco dias (A B C A B nas linhas), conta antiga (o fixture)."""
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in dias:
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


def _tira(resposta):
    """{dia: (letra, estado)} — o que a tira de /treino/ desenha ("·" no pulado)."""
    return {
        d["short"]: (
            "·" if d["session"].projecao == "pulado" else d["session"].label,
            d["session"].projecao,
        )
        for d in resposta.context["week"] if d["session"] is not None
    }


def _plano_ativo(user):
    return TrainingPlan.objects.get(user=user, is_active=True)


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)


class ARemontagemNaoZeraASequenciaTests(_Base):
    """B4. A na segunda e B na terça sob a ficha 1; a quarta passou sem
    treino; na terça à noite a pessoa pediu "regenerar" (ou trocou o
    equipamento) e, como já tinha treinado, o pedido ficou para depois. Na
    quinta ela abre o Treino: a ficha 2 nasce ali, no GET — e o treino de
    hoje tem de ser C, a seguinte à última feita, como seria sem remontagem."""

    def setUp(self):
        super().setUp()
        self.user = _pessoa("remonta@exemplo.com")
        self.antiga = services.create_routine(self.user)
        fazer(self.user, self.antiga, "A", SEGUNDA)
        fazer(self.user, self.antiga, "B", SEGUNDA + timedelta(days=1))
        self.client.force_login(self.user)

    def _remontar_no_get(self):
        """A remontagem de verdade: o pedido adiado é cumprido pela visita ao
        Treino (`sync_active_routine`), a mesma porta de P2/P4."""
        TrainingPlan.objects.filter(pk=self.antiga.pk).update(regenerar_pedido_em=timezone.now())
        resposta = self.client.get(reverse("workouts:routine"))
        nova = _plano_ativo(self.user)
        self.assertNotEqual(nova.pk, self.antiga.pk, "controle: a ficha não foi remontada")
        return resposta, nova

    def test_depois_de_remontar_o_treino_de_hoje_segue_da_ultima_letra_feita(self):
        resposta, nova = self._remontar_no_get()
        self.assertEqual(resposta.context["hoje"].label, "C")
        self.assertEqual(services.sequencia_do_treino(self.user, nova).recomendada(), "C")

    def test_depois_de_remontar_a_tira_mostra_os_dias_feitos(self):
        """Os dias treinados sob a ficha antiga são `feito` com a letra
        feita; só a quarta, que ninguém treinou, é `pulado`."""
        resposta, _ = self._remontar_no_get()
        self.assertEqual(
            _tira(resposta),
            {
                "Seg": ("A", "feito"),
                "Ter": ("B", "feito"),
                "Qua": ("·", "pulado"),
                "Qui": ("C", "hoje"),
                "Sex": ("A", "futuro"),
            },
        )
        # No HTML, ancorado na classe do chip: um pulado só (a quarta).
        self.assertEqual(resposta.content.decode().count("day-chip--pulado"), 1)

    def test_remontar_pela_troca_de_equipamento_tambem_nao_zera(self):
        """A outra porta de P2 (d6) e P4 (02/10): a entrada mudou, a ficha
        ficou inválida e é remontada — e a sequência atravessa do mesmo jeito."""
        self.user.profile.equipamento = "basica"
        self.user.profile.save(update_fields=["equipamento"])
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertNotEqual(_plano_ativo(self.user).pk, self.antiga.pk, "controle: não remontou")
        self.assertEqual(resposta.context["hoje"].label, "C")

    def test_a_opcao_da_ficha_legada_nao_muda_com_historico_de_ficha_anterior(self):
        """A OPÇÃO da letra (1/2) só existe na ficha legada de duas opções
        (15–27/09) e sai da contagem da letra NESTA ficha. Contar o feito nas
        fichas anteriores trocaria, no deploy, a opção de hoje de quem tem
        ficha legada e histórico antes dela — sem ninguém ter feito nada. A
        sequência (a letra) atravessa as fichas; a opção, não. Lido pela
        porta que a ficha e a execução usam (`variacao_do_dia`/`opcao_do_dia`)."""
        from workouts.test_opcoes import ficha_legada

        nova = services.create_routine(self.user)  # A seg e B ter ficaram na antiga
        ficha_legada(nova, "A")
        linhas = list(nova.sessions.prefetch_related("exercises__exercise"))
        linha_a = next(s for s in sorted(linhas, key=lambda s: s.order) if s.label == "A")
        self.assertEqual(len(linha_a.opcoes), 2, "controle: a letra A não é legada")

        antes = services.variacao_do_dia(nova, QUINTA, linha_a, linhas, user=self.user)
        self.assertEqual(antes, linha_a.opcoes[0], "nada feito NESTA ficha: a 1ª opção")
        fazer(self.user, self.antiga, "A", QUARTA)  # mais um A, na ficha ANTERIOR
        self.assertEqual(services.variacao_do_dia(nova, QUINTA, linha_a, linhas, user=self.user), antes)
        self.assertEqual(services.opcao_do_dia(self.user, linha_a, QUINTA, linhas), antes)

    def _c_por_ultimo_e_dois_dias(self):
        """C na segunda como a ÚLTIMA feita (sai a terça do setUp) e os dias
        passam a seg+qui: a ficha nova, montada no GET, é AB — sem C."""
        fazer(self.user, self.antiga, "C", SEGUNDA)
        EscolhaDeTreino.objects.filter(user=self.user, date=SEGUNDA + timedelta(days=1)).delete()
        TrainingDay.objects.filter(user=self.user).exclude(weekday__in=(0, 3)).delete()
        resposta = self.client.get(reverse("workouts:routine"))
        nova = _plano_ativo(self.user)
        self.assertEqual(services.letras_do_ciclo(list(nova.sessions.all())), ["A", "B"], "controle")
        self.assertEqual(services.sequencia_do_treino(self.user, nova).ultima_letra(), "C", "controle")
        return resposta, nova

    def test_letra_feita_que_a_ficha_nova_nao_tem_aparece_como_foi_feita(self):
        """A tira não pode dizer que a segunda foi "A": mostra C, feito."""
        resposta, _ = self._c_por_ultimo_e_dois_dias()
        self.assertEqual(_tira(resposta)["Seg"], ("C", "feito"))

    def test_ultima_letra_fora_do_ciclo_novo_recomenda_a_primeira(self):
        """A última feita (C) não existe na ficha nova (AB): o recomendado é
        a primeira letra do ciclo novo. Antes de 28/09 esse caminho não
        existia (a sequência só via as letras do próprio plano); sem a guarda
        `ultima not in self.letras`, `letras.index("C")` é ValueError — 500
        no Treino e na Home (revisão da Task C, achado 2)."""
        resposta, _ = self._c_por_ultimo_e_dois_dias()
        self.assertEqual(resposta.context["hoje"].label, "A")

    def test_a_ficha_de_hoje_nao_herda_a_letra_da_copia_fora_do_ciclo(self):
        """A cópia que mostra C na tira levava o `pk` da linha de segunda —
        que na ficha nova é a letra A. A ficha de hoje (A) procura as irmãs
        por `pk` e se chamava "Treino C: Superior" (revisão da Task C, achado
        1). A cópia leva o pk da sessão FEITA, o C da ficha antiga — e essa
        ficha abre como programa anterior, sem 404."""
        resposta, _ = self._c_por_ultimo_e_dois_dias()
        hoje = resposta.context["hoje"]
        self.assertEqual(hoje.label, "A", "controle")
        ficha = self.client.get(reverse("workouts:ficha", args=[hoje.pk]))
        self.assertEqual(ficha.context["sessao"].rotulo, "A")
        self.assertContains(ficha, "<h1>Treino A:")
        c_feito = EscolhaDeTreino.objects.get(user=self.user, date=SEGUNDA).session_id
        self.assertEqual(self.client.get(reverse("workouts:ficha", args=[c_feito])).status_code, 200)

    def _cortar_para_dois_dias(self):
        TrainingDay.objects.filter(user=self.user).exclude(weekday__in=(0, 3)).delete()
        nova = services.create_routine(self.user)
        self.assertEqual(services.letras_do_ciclo(list(nova.sessions.all())), ["A", "B"], "controle")
        return nova

    def test_o_aviso_de_repeticao_le_os_grupos_da_sessao_feita(self):
        """Ontem, B da ficha antiga: "Costas e bíceps". Hoje a ficha é AB, e o
        B dela é "Inferior". Escolher B hoje NÃO repete grupo nenhum — o aviso
        pela letra (a linha B da ficha nova) dizia "Quadríceps foi treinado
        ontem", o que é falso (revisão da Task C, achado 4)."""
        fazer(self.user, self.antiga, "B", QUARTA)
        nova = self._cortar_para_dois_dias()
        self.assertIsNone(services.aviso_de_treino_repetido(self.user, nova, "B", QUINTA))

    def test_o_aviso_de_repeticao_ve_a_letra_que_a_ficha_nova_nao_tem(self):
        """Controle positivo do anterior: ontem, C da ficha antiga ("Pernas e
        ombros"). Hoje, AB — sem C. Escolher B ("Inferior") repete pernas, e
        o aviso tem de aparecer; pela letra, C não existia na ficha nova e o
        aviso sumia."""
        fazer(self.user, self.antiga, "C", QUARTA)
        nova = self._cortar_para_dois_dias()
        aviso = services.aviso_de_treino_repetido(self.user, nova, "B", QUINTA)
        self.assertIsNotNone(aviso)
        self.assertIn("ontem", aviso)


class ATiraNaoInventaFaltaAntesDaContaTests(_Base):
    """Item 8. A conta nasceu na TERÇA às 23h30 de Brasília — já quarta
    (02h30) em UTC —; hoje é quinta. A segunda é dia de treino da ficha, mas
    a pessoa ainda não usava o app: não é falta. Terça e quarta são — a conta
    já existia no dia LOCAL — e continuam `pulado` (controle positivo). A
    hora perto da meia-noite prende o fuso: ler `date_joined.date()` em UTC
    esconderia a terça (revisão da Task C, achado 3)."""

    def setUp(self):
        super().setUp()
        self.user = _pessoa("nova@exemplo.com")
        self.user.date_joined = timezone.make_aware(datetime(2026, 9, 15, 23, 30))
        self.user.save(update_fields=["date_joined"])
        self.assertEqual(self.user.date_joined.astimezone(dt_timezone.utc).day, 16, "controle: UTC já é quarta")
        services.create_routine(self.user)
        self.client.force_login(self.user)

    def test_dia_de_antes_da_conta_nao_e_pulado(self):
        resposta = self.client.get(reverse("workouts:routine"))
        tira = _tira(resposta)
        self.assertNotIn("Seg", tira, "segunda (antes da conta) virou dia de treino na tira")
        self.assertEqual(tira.get("Ter"), ("·", "pulado"), "a terça local (conta já existia) sumiu")
        self.assertEqual(tira["Qua"], ("·", "pulado"))
        self.assertEqual(tira["Qui"], ("A", "hoje"))
        self.assertEqual(resposta.content.decode().count("day-chip--pulado"), 2)


class OAvisoDeRegenerarRespeitaOPedidoTests(_Base):
    """M1 (P2-06). A pessoa aceitou "Montar a ficha nova" com série hoje: o
    Treino respondeu "a ficha nova entra amanhã", e a Home continuou
    perguntando o resto do dia e na manhã seguinte, até a aba Treino ser
    aberta. Com o pedido gravado (`regenerar_pedido_em`), a pergunta já foi
    respondida."""

    def setUp(self):
        super().setUp()
        self.user = _pessoa("aviso@exemplo.com")
        self.plano = services.create_routine(self.user)
        _mudar_a_prescricao(self.plano)
        self.client.force_login(self.user)

    def test_aceito_e_adiado_o_aviso_some_da_home(self):
        self.assertTrue(services.aviso_de_regenerar(self.user, plan=self.plano), "controle: sem aviso")
        home = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('class="card aviso-regenerar"', home, "controle: a Home não perguntava")

        fazer(self.user, self.plano, "A", QUINTA)  # série hoje → o pedido fica para amanhã
        self.client.post(reverse("workouts:regenerar"))
        self.plano.refresh_from_db()
        self.assertIsNotNone(self.plano.regenerar_pedido_em, "controle: o pedido não foi adiado")

        self.assertFalse(services.aviso_de_regenerar(self.user, plan=self.plano))
        home = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn('class="card aviso-regenerar"', home)


class OMapaDiaLetraSegueAProjecaoTests(_Base):
    """BA4 (P1-19, P4-09): "em que dias cai a letra" tem de ser UMA resposta
    na mesma tela e entre telas. A na segunda, B na terça, quarta sem
    treino: hoje (quinta) é C, e a tira mostra C só na quinta.

    REPRODUZ com a sequência por presença (28/09/2026), e o conserto NÃO
    mora em `services`: os três leitores tratam a entrada `pulado` de
    `sessoes_da_semana` (a LINHA do dia, com a letra e os exercícios dela)
    como se fosse a letra caindo naquele dia, e a página do exercício ainda
    pede a semana SEM a pessoa. Os `expectedFailure` abaixo são nomeados, com
    o lugar do conserto; quem consertar remove o decorador (o "sucesso
    inesperado" reprova a suíte)."""

    def setUp(self):
        super().setUp()
        self.user = _pessoa("mapa@exemplo.com")
        self.plano = services.create_routine(self.user)
        fazer(self.user, self.plano, "A", SEGUNDA)
        fazer(self.user, self.plano, "B", SEGUNDA + timedelta(days=1))
        self.client.force_login(self.user)
        self.linhas = list(self.plano.sessions.prefetch_related("exercises__exercise"))
        self.linha_c = next(s for s in sorted(self.linhas, key=lambda s: s.order) if s.label == "C")

    def test_controle_a_tira_mostra_c_so_na_quinta_e_a_so_seg_e_sex(self):
        """A régua dos três abaixo — e o controle de que o cenário existe."""
        tira = _tira(self.client.get(reverse("workouts:routine")))
        self.assertEqual([d for d, (letra, _) in tira.items() if letra == "C"], ["Qui"])
        self.assertEqual([d for d, (letra, _) in tira.items() if letra == "A"], ["Seg", "Sex"])
        self.assertEqual(tira["Qua"], ("·", "pulado"))

    @expectedFailure
    def test_a_ficha_da_letra_de_hoje_diz_os_dias_da_tira(self):
        """Hoje diz "Quarta-feira · Quinta-feira": a quarta PULADA entra
        porque a linha de quarta é a de C. Conserto: `FichaDaSessaoView`
        (`workouts/views.py`, `dias_texto` e `nomear_ocorrencias(irmas)`)
        ignora `projecao == "pulado"`."""
        ficha = self.client.get(reverse("workouts:ficha", args=[self.linha_c.pk]))
        self.assertEqual(ficha.context["sessao"].dias_texto, "Quinta-feira")

    @expectedFailure
    def test_o_cartao_da_letra_diz_os_dias_da_tira(self):
        """"Seu programa" diz "A · Segunda-feira · Quinta-feira": os dias das
        LINHAS (a estrutura de antes da rotação), não os da projeção.
        Conserto: `_cartao_da_letra` (`workouts/views.py`) lê os dias da
        tira, sem os pulados."""
        resposta = self.client.get(reverse("workouts:routine"))
        cartao_a = next(c for c in resposta.context["letras"] if c["label"] == "A")
        self.assertEqual(cartao_a["dias"], ["Segunda-feira", "Sexta-feira"])

    @expectedFailure
    def test_o_quando_do_exercicio_diz_os_dias_da_tira(self):
        """Hoje diz "Quarta-feira (C)": a semana vem de
        `telas.semana_do_plano`, que chama `sessoes_da_semana` SEM `user` —
        a projeção de quem nunca treinou (hoje seria A) — e lista a linha
        pulada. Conserto: `user=user` em `workouts/telas.py` e o laço de
        `ExercicioView` ignorando `pulado`."""
        de_outras = {
            i.exercise_id for s in self.linhas if s.label != "C" for i in s.exercises.all()
        }
        so_de_c = next(i.exercise for i in self.linha_c.exercises.all() if i.exercise_id not in de_outras)
        pagina = self.client.get(reverse("workouts:exercicio", args=[so_de_c.pk]))
        self.assertEqual(pagina.context["dias"], ["Quinta-feira (C)"])
