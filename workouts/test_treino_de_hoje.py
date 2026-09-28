# -*- coding: utf-8 -*-
"""O TREINO DE HOJE DIZ A VERDADE (28/09/2026, parte 2, onda 2).

Achados de 27/09 (`achados/qa-exploratorio-20260927.md` e
`achados/caca-bugs-20260927.md`) sobre a tela de Treino, a ficha e a
execução — todos do mesmo tipo: a tela afirmava uma coisa que o banco não
sustentava, ou deixava de oferecer o que a pessoa veio fazer.

- R4: no domingo não havia como treinar. A tela dizia "Dia de descanso", a
  execução "Hoje não tem treino", e nenhuma das duas tinha porta;
- R7: o `<summary>` "Fazer outro treino" media 25 px de altura;
- M3 (item 4): o herói dizia "14 % do treino" (1 de 7 EXERCÍCIOS) e a
  execução, no mesmo instante, "2/25 séries" — duas réguas para a mesma
  pergunta;
- BA22: depois de "Encerrar treino" o botão continuava "Continuar treino
  (4 de 7)";
- M19: a ficha de um programa anterior mostrava a opção que NÃO foi feita
  (a "próxima vez" de um plano que não terá próxima vez);
- BA18: quem não faz musculação lia "Suas corridas ficam logo abaixo." numa
  tela que não lista corrida nenhuma;
- o aviso CRN/CREF (§4 do Gate 1, aprovado pelo dono em 28/09) chega à ficha
  de treino, que tinha ficado de fora do primeiro lote.

As réguas medem o TEXTO VISÍVEL ou ancoram na classe/`<form>`: o seletor do
JavaScript e o marcador do HTML são a mesma string (CLAUDE.md).
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Musculacao, Profile, TrainingDay
from config import relogio
from config.test_linguagem import AVISO_CRN_CREF, texto_visivel
from plans.tests import create_complete_user
from workouts import services
from workouts.models import EscolhaDeTreino, ExerciseLog, TrainingPlan
from workouts.test_sequencia import QUINTA, SEGUNDA, _pessoa, fazer

TERCA = SEGUNDA + timedelta(days=1)
SABADO = SEGUNDA + timedelta(days=5)


def _main(resposta):
    html = resposta.content.decode()
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _bloco(html, marcador, fim="</section>"):
    """O trecho do HTML que começa no marcador (uma classe) e vai até `fim`."""
    assert marcador in html, "marcador ausente: %s" % marcador
    return html.split(marcador, 1)[1].split(fim, 1)[0]


def _cta_do_heroi(resposta):
    """O texto visível do botão principal do herói de hoje."""
    casou = re.search(r"<a[^>]*data-hoje-cta[^>]*>(.*?)</a>", _main(resposta), re.S)
    assert casou is not None, "o botão do herói sumiu"
    return texto_visivel(casou.group(1))


def _anotar(user, item, n, dia):
    ExerciseLog.objects.create(
        user=user, exercise=item.exercise, date=dia, set_number=n,
        weight_kg=Decimal("40"), reps=10,
    )


def _tira(resposta):
    """{dia: letra} dos dias de treino da tira ("·" no `pulado`)."""
    return {
        d["short"]: "·" if d["session"].projecao == "pulado" else d["session"].label
        for d in resposta.context["week"] if d["session"] is not None
    }


def _cartao_de_treino_da_home(client):
    """O texto visível do cartão "Treino" do painel do dia na Home."""
    html = _main(client.get(reverse("plans:today")))
    for bloco in html.split('<section class="painel__cartao')[1:]:
        corpo = bloco.split("</section>", 1)[0]
        if "Treino" in texto_visivel(corpo.split("</h3>", 1)[0]):
            return texto_visivel(corpo)
    raise AssertionError("o cartão de Treino sumiu da Home")


class _Base(TestCase):
    """A e B feitos na segunda e na terça, ABC de segunda a sexta."""

    dia = QUINTA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(self.dia).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("hoje-%s@exemplo.com" % self.__class__.__name__.lower())
        self.plano = services.create_routine(self.user)
        fazer(self.user, self.plano, "A", SEGUNDA)
        fazer(self.user, self.plano, "B", TERCA)
        self.client.force_login(self.user)

    def _linhas(self):
        return list(self.plano.sessions.prefetch_related("exercises__exercise"))


class NoDescansoDaParaTreinarMesmoAssimTests(_Base):
    """R4. Sábado: a ficha é de segunda a sexta. A última feita foi B (terça),
    então o recomendado — a seguinte à última FEITA — é C. Quem quer treinar
    no sábado toca "Treinar mesmo assim", que é a MESMA escolha de letra do
    "Fazer outro treino" (`EscolherLetraView`)."""

    dia = SABADO

    def test_controle_sabado_e_descanso_e_o_recomendado_e_c(self):
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertIsNone(resposta.context["hoje"])
        self.assertIn("Dia de descanso", texto_visivel(_main(resposta)))
        self.assertEqual(services.sequencia_do_treino(self.user, self.plano).recomendada(), "C")

    def test_o_descanso_oferece_treinar_mesmo_assim_na_letra_recomendada(self):
        cartao = _bloco(_main(self.client.get(reverse("workouts:routine"))), 'class="card hoje hoje--descanso"')
        self.assertIn('action="%s"' % reverse("workouts:escolher_letra"), cartao)
        self.assertIn('name="letra" value="C"', cartao)
        self.assertIn("Treinar mesmo assim", texto_visivel(cartao))

    def test_a_execucao_no_descanso_oferece_o_mesmo(self):
        resposta = self.client.get(reverse("workouts:now"))
        self.assertFalse(resposta.context["estado"].tem_treino, "controle: não é descanso")
        corpo = _main(resposta)
        self.assertIn("Hoje não tem treino", texto_visivel(corpo))
        self.assertIn('action="%s"' % reverse("workouts:escolher_letra"), corpo)
        self.assertIn('name="letra" value="C"', corpo)
        self.assertIn("Treinar mesmo assim", texto_visivel(corpo))

    def test_treinar_mesmo_assim_abre_o_treino_a_execucao_e_grava_a_serie(self):
        linha_c = next(s for s in self._linhas() if s.label == "C")
        self.assertIn("Descanso", _cartao_de_treino_da_home(self.client), "controle: a Home não dizia descanso")
        resposta = self.client.post(reverse("workouts:escolher_letra"), {"letra": "C"})
        self.assertEqual(resposta["Location"], reverse("workouts:routine"))

        # A HOME CONCORDA (fix round 1, MINOR 5): ela lê `estado_do_treino`,
        # que passa pela mesma `sessao_do_dia`; o cartão deixa de ser
        # "Descanso" e oferece o treino escolhido.
        home = _cartao_de_treino_da_home(self.client)
        self.assertNotIn("Descanso", home)
        self.assertIn("C — %s" % linha_c.name, home)
        self.assertIn("Começar", home)

        painel = self.client.get(reverse("workouts:routine"))
        self.assertIsNotNone(painel.context["hoje"], "a letra escolhida no descanso não virou o treino de hoje")
        self.assertEqual(painel.context["hoje"].label, "C")
        self.assertNotIn("Dia de descanso", texto_visivel(_main(painel)))
        self.assertIn("Começar treino", _cta_do_heroi(painel))
        ficha = self.client.get(reverse("workouts:ficha", args=[painel.context["hoje"].pk]))
        self.assertTrue(ficha.context["ficha"]["executavel"], "a ficha da letra escolhida não executa")

        execucao = self.client.get(reverse("workouts:now"))
        estado = execucao.context["estado"]
        self.assertTrue(estado.tem_treino)
        self.assertEqual(estado.sessao.label, "C")

        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": estado.atual.exercise_id, "weight_kg": "40", "reps": "10",
            "op_id": "sabado-1", "sessao": estado.sessao.pk,
        })
        self.assertEqual(ExerciseLog.objects.filter(user=self.user, date=SABADO).count(), 1)
        self.assertEqual(self.client.get(reverse("workouts:now")).context["estado"].series_feitas, 1)

    def test_treinar_no_descanso_nao_muda_a_regra_da_sequencia(self):
        """GUARDA (não nasce vermelho): a regra continua "a seguinte à última
        FEITA". Escolher sem série não conta; com série, C passa a ser a
        última feita e a segunda seguinte recomenda A."""
        segunda_que_vem = SEGUNDA + timedelta(days=7)

        def recomendada():
            return services.sequencia_do_treino(self.user, self.plano, ate=segunda_que_vem).recomendada()

        self.assertEqual(recomendada(), "C")
        self.client.post(reverse("workouts:escolher_letra"), {"letra": "C"})
        self.assertEqual(recomendada(), "C", "escolher sem série virou presença")
        linha_c = next(s for s in self._linhas() if s.label == "C")
        _anotar(self.user, linha_c.exercises.all()[0], 1, SABADO)
        self.assertEqual(recomendada(), "A")

    def test_depois_de_treinar_mesmo_assim_a_tira_segue_da_letra_escolhida(self):
        """IMPORTANT 1 da revisão (fix round 1). Sábado, C escolhido: a tira
        (a semana que vem) começava por C — a recomendada de antes, que foi a
        oferecida — e o cartão de C dizia "Segunda-feira". O próximo dia
        segue da letra de HOJE, como num dia de treino: segunda é A."""
        antes = self.client.get(reverse("workouts:routine"))
        self.assertEqual(_tira(antes)["Seg"], "C", "controle: sem escolha, a segunda é a recomendada")

        self.client.post(reverse("workouts:escolher_letra"), {"letra": "C"})
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertEqual(resposta.context["hoje"].label, "C", "controle")
        self.assertEqual(_tira(resposta)["Seg"], "A")
        cartao_c = next(c for c in resposta.context["letras"] if c["label"] == "C")
        self.assertNotIn("Segunda-feira", cartao_c["dias"])

    def test_a_serie_no_descanso_sem_escolha_nao_consulta_a_escolha_de_novo(self):
        """MINOR 4 da revisão (fix round 1). A guarda do descanso em
        `sessao_do_dia` lê a escolha do dia quando não a recebe. Quem já leu
        e sabe que não há (`garantir_escolha`, `series_de_hoje`,
        `prescricao_de_hoje`) passa `escolha=None`. MEDIDO no POST de uma
        série no sábado sem escolha: 2 leituras de `EscolhaDeTreino` (a de
        `garantir_escolha` e a de `series_de_hoje`); com a consulta repetida
        eram 4."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        linha_c = next(s for s in self._linhas() if s.label == "C")
        with CaptureQueriesContext(connection) as ctx:
            self.client.post(reverse("workouts:record_set"), {
                "exercise_id": linha_c.exercises.all()[0].exercise_id, "weight_kg": "40",
                "reps": "10", "op_id": "sabado-sem-escolha",
            })
        self.assertEqual(ExerciseLog.objects.filter(user=self.user, date=SABADO).count(), 1, "controle")
        self.assertFalse(EscolhaDeTreino.objects.filter(user=self.user, date=SABADO).exists(), "controle")
        leituras = [
            q["sql"] for q in ctx.captured_queries
            if q["sql"].lstrip().startswith("SELECT") and 'FROM "workouts_escolhadetreino"' in q["sql"]
        ]
        self.assertLessEqual(len(leituras), 2, "\n".join(leituras))


class NoDescansoDoMeioDaSemanaATiraSegueDaEscolhaTests(TestCase):
    """IMPORTANT 1, o outro caminho: plano seg/qua/sex (ABC), A feito na
    segunda, terça é descanso. "Treinar mesmo assim" oferece B; escolhido,
    o herói diz B e a quarta da tira não pode ser B de novo — é C."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(TERCA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = create_complete_user(
            email="meio-da-semana@exemplo.com", experiencia="intermediario", split_preference="two",
            split_preference_confirmada=True,
        )
        TrainingDay.objects.filter(user=self.user).delete()
        for d in (0, 2, 4):
            TrainingDay.objects.create(user=self.user, weekday=d, duration_min=60)
        self.plano = services.create_routine(self.user)
        fazer(self.user, self.plano, "A", SEGUNDA)
        self.client.force_login(self.user)

    def test_escolhido_b_na_terca_a_quarta_e_c(self):
        antes = self.client.get(reverse("workouts:routine"))
        self.assertIsNone(antes.context["hoje"], "controle: terça não é descanso")
        self.assertEqual(services.letras_do_ciclo(list(self.plano.sessions.all())), ["A", "B", "C"], "controle")
        self.assertEqual(_tira(antes)["Qua"], "B", "controle: sem escolha, a quarta é a recomendada")

        self.client.post(reverse("workouts:escolher_letra"), {"letra": "B"})
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertEqual(resposta.context["hoje"].label, "B")
        self.assertEqual(_tira(resposta)["Qua"], "C")


class FazerOutroTreinoCabeNoDedoTests(_Base):
    """R7. O `<summary>` cru media 289×25 a 390 px. A classe do "Comi outra
    coisa" da Alimentação (`fora__abrir btn btn--ghost btn--block`) dá os
    44 px e apaga o marcador nativo — sem CSS novo."""

    def test_fazer_outro_treino_usa_o_botao_da_sanfona(self):
        html = _main(self.client.get(reverse("workouts:routine")))
        self.assertIn(
            '<summary class="fora__abrir btn btn--ghost btn--block">Fazer outro treino</summary>', html
        )


class OProgressoDeHojeEUmaContaSoTests(_Base):
    """Item 4 (M3). Quinta: hoje é C. Duas séries no primeiro exercício. O
    herói dizia "14 %" (1 de 7 exercícios) e a execução "2/25 séries": a
    régua passa a ser UMA — séries feitas de séries previstas —, e o herói,
    a ficha e a execução leem a mesma função no mesmo instante."""

    def _duas_series_hoje(self):
        estado = services.estado_do_treino(self.user)
        self.assertEqual(estado.sessao.label, "C", "controle")
        _anotar(self.user, estado.itens[0], 1, QUINTA)
        _anotar(self.user, estado.itens[0], 2, QUINTA)

    def _numero(self, padrao, html, oque):
        casou = re.search(padrao, html)
        self.assertIsNotNone(casou, "%s sumiu do HTML" % oque)
        return tuple(int(g) for g in casou.groups())

    def _comparar(self):
        """As três telas lidas pelo HTML DESENHADO, e não pelo contexto (fix
        round 1, MINOR 1): um template que passe a desenhar outro campo tem
        de reprovar aqui."""
        painel = _main(self.client.get(reverse("workouts:routine")))
        execucao = _main(self.client.get(reverse("workouts:now")))
        feitas, previstas = self._numero(
            r"· (\d+)/(\d+) séries", texto_visivel(_bloco(execucao, 'class="agora__passo num"', "</p>")),
            "o \"x/y séries\" da execução",
        )
        self.assertEqual(feitas, 2, "controle")
        (barra,) = self._numero(
            r'class="progress agora__progresso">\s*<span class="progress__fill" style="width: (\d+)%', execucao,
            "a barra da execução",
        )
        (anel,) = self._numero(r'class="ring__value num">(\d+)<', painel, "o número do anel")
        self.assertEqual(anel, barra, "o anel do herói e a barra da execução discordam")
        contagem = texto_visivel(_bloco(painel, 'class="hoje__contagem"', "</p>"))
        self.assertIn("%d de %d séries" % (feitas, previstas), contagem)
        hoje_pk = re.search(r'href="/treino/ficha/(\d+)/"', _bloco(painel, "hoje__ver-ficha", "</a>")).group(1)
        ficha = _main(self.client.get(reverse("workouts:ficha", args=[int(hoje_pk)])))
        (barra_da_ficha,) = self._numero(
            r'class="progress ficha__barra">\s*<span class="progress__fill" style="width: (\d+)%', ficha,
            "a barra da ficha",
        )
        self.assertEqual(barra_da_ficha, barra, "a barra da ficha discorda")

    def test_o_heroi_a_ficha_e_a_execucao_contam_series_do_mesmo_jeito(self):
        self._duas_series_hoje()
        self._comparar()

    def test_na_versao_rapida_a_base_e_a_mesma_da_execucao(self):
        """A rápida corta séries em memória na execução; o herói tem de contar
        contra o MESMO total, senão "2 de 25" num lado e "2/18" no outro."""
        completo = services.estado_do_treino(self.user).total_series
        self.client.post(reverse("workouts:rapida_hoje"))
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user, date=QUINTA).versao, "rapido", "controle")
        self.assertLess(services.estado_do_treino(self.user).total_series, completo, "controle: a rápida não corta")
        self._duas_series_hoje()
        self._comparar()


class TreinoEncerradoNaoDizContinuarTests(_Base):
    """BA22. Encerrar é a pessoa dizendo que acabou: o botão deixa de dizer
    "Continuar treino (n de N)" e leva ao resumo; a ficha não oferece
    encerrar de novo. "Retomar treino" desfaz, e o verbo volta."""

    def setUp(self):
        super().setUp()
        estado = services.estado_do_treino(self.user)
        _anotar(self.user, estado.itens[0], 1, QUINTA)
        self.hoje_pk = estado.sessao.pk

    def _ficha(self):
        corpo = _main(self.client.get(reverse("workouts:ficha", args=[self.hoje_pk])))
        return texto_visivel(_bloco(corpo, 'class="split__aside ficha__lado"', "</aside>"))

    def test_encerrado_o_heroi_leva_ao_resumo_e_a_ficha_nao_encerra_de_novo(self):
        self.assertTrue(_cta_do_heroi(self.client.get(reverse("workouts:routine"))).startswith("Continuar treino"), "controle")
        self.assertIn("Encerrar treino", self._ficha(), "controle")

        self.client.post(reverse("workouts:encerrar"), {"confirmado": "1"})

        self.assertEqual(_cta_do_heroi(self.client.get(reverse("workouts:routine"))), "Ver o resumo do treino")
        ficha = self._ficha()
        self.assertIn("Ver o resumo do treino", ficha)
        self.assertNotIn("Continuar treino", ficha)
        self.assertNotIn("Encerrar treino", ficha)

    def test_retomar_devolve_o_continuar(self):
        self.client.post(reverse("workouts:encerrar"), {"confirmado": "1"})
        self.client.post(reverse("workouts:retomar"))
        self.assertTrue(_cta_do_heroi(self.client.get(reverse("workouts:routine"))).startswith("Continuar treino"))


class AFichaAnteriorMostraOQueFoiFeitoTests(_Base):
    """M19. Ficha legada de duas opções (15–27/09): A foi feito na segunda
    com a opção 1. A ficha é remontada. A ficha do A ANTIGO abre como
    programa anterior e tem de mostrar a opção 1 — a feita —, e não a 2,
    que seria a "próxima vez" de um plano que não terá próxima vez."""

    def setUp(self):
        from workouts.test_opcoes import ficha_legada

        super().setUp()
        ficha_legada(self.plano, "A")
        self.linha_a = EscolhaDeTreino.objects.get(user=self.user, date=SEGUNDA).session
        self.assertEqual(len(self.linha_a.opcoes), 2, "controle: a letra A não é legada")

    def _ids(self, opcao):
        return [i.exercise_id for i in self.linha_a.da_opcao(opcao)]

    def _ficha_depois_de_remontar(self):
        self.assertNotEqual(self._ids(1), self._ids(2), "controle: as duas opções são iguais")
        TrainingPlan.objects.filter(pk=self.plano.pk).update(regenerar_pedido_em=timezone.now())
        self.client.get(reverse("workouts:routine"))
        self.assertFalse(TrainingPlan.objects.get(pk=self.plano.pk).is_active, "controle: não remontou")
        ficha = self.client.get(reverse("workouts:ficha", args=[self.linha_a.pk]))
        self.assertTrue(ficha.context["historico"], "controle: não é programa anterior")
        return [i.exercise_id for i in ficha.context["ficha"]["itens"]]

    def test_a_ficha_do_programa_anterior_mostra_a_opcao_feita(self):
        self.assertEqual(self._ficha_depois_de_remontar(), self._ids(1))

    def test_escolher_sem_registrar_serie_nao_e_fazer(self):
        """Visto na captura: "treinar mesmo assim" no sábado escolheu A na
        opção 2 e ninguém treinou. Feito é ter série (a régua da sequência
        por presença): a ficha anterior continua mostrando a opção 1."""
        EscolhaDeTreino.objects.create(user=self.user, date=QUINTA, session=self.linha_a, opcao=2)
        self.assertEqual(self._ficha_depois_de_remontar(), self._ids(1))

    def test_com_varias_feitas_vale_a_mais_recente(self):
        """Fix round 1 (MINOR 2): A feito na segunda (opção 1) e de novo na
        quarta (opção 2), as duas com série. A ficha anterior mostra a
        opção da ÚLTIMA vez feita — a 2."""
        quarta = SEGUNDA + timedelta(days=2)
        EscolhaDeTreino.objects.create(user=self.user, date=quarta, session=self.linha_a, opcao=2)
        _anotar(self.user, self.linha_a.da_opcao(2)[0], 1, quarta)
        self.assertEqual(self._ficha_depois_de_remontar(), self._ids(2))


class QuemNaoFazMusculacaoLeAVerdadeTests(TestCase):
    """BA18. A tela de quem não faz musculação dizia "Suas corridas ficam
    logo abaixo." e embaixo vinha só a porta da corrida — nenhuma corrida
    listada. A frase passa a dizer o que está lá."""

    def test_a_frase_diz_que_a_corrida_fica_abaixo(self):
        user = create_complete_user(email="so-corre-hoje@exemplo.com")
        TrainingDay.objects.filter(user=user).delete()
        Profile.objects.filter(user=user).update(musculacao=Musculacao.NAO)
        self.client.force_login(user)
        texto = texto_visivel(_main(self.client.get(reverse("workouts:routine"))))
        self.assertIn("não faz musculação", texto, "controle: não é o ramo de quem só corre")
        self.assertIn("A corrida fica logo abaixo.", texto)
        self.assertNotIn("Suas corridas", texto)


class AFichaDeTreinoTemOAvisoCrnCrefTests(_Base):
    """O aviso do §4 do Gate 1 (aprovado pelo dono em 28/09/2026) chega à
    ficha de treino — a MESMA frase de `config/test_linguagem.py`, num
    `<p class="hint">` no fim da lista, como na Alimentação."""

    def test_a_ficha_de_hoje_e_a_de_outra_letra_trazem_o_aviso(self):
        for linha in self._linhas()[:2]:
            with self.subTest(letra=linha.label):
                corpo = _main(self.client.get(reverse("workouts:ficha", args=[linha.pk])))
                self.assertIn(AVISO_CRN_CREF, texto_visivel(corpo))
                paragrafos = re.findall(r'<p class="hint">(.*?)</p>', corpo, re.S)
                self.assertTrue(any(AVISO_CRN_CREF in texto_visivel(p) for p in paragrafos))
