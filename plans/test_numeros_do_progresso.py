# -*- coding: utf-8 -*-
"""O Progresso diz o mesmo número toda vez — e a ofensiva é UMA conta só.

Três coisas nesta missão, e as três são a mesma doença: um número da tela
que não corresponde ao que o app guarda.

1. **A caixa do consolidado misturava dois denominadores.** Desde 22/09/2026
   `adherence_pct` é dos DIAS FECHADOS ("hoje ainda está acontecendo"), e
   `avg_kcal` continuou sendo de TODOS os dias — hoje incluído. A média de
   "kcal/dia" caía a cada manhã, subia durante o dia e era comparada com a
   meta de um dia inteiro ao lado. Quem lia a tela três vezes no mesmo dia
   via três médias, sem ter mudado nada de propósito. Agora as duas leem o
   mesmo recorte, e no primeiro dia — quando não há dia fechado — a tela
   não inventa média nenhuma.

2. **A ofensiva tem de ser a mesma nas três telas.** Ela já foi diferente:
   as Conquistas chamavam `streaks.calcular` sem a meta de água, a água
   "fechava" todo dia, e a tela dizia "3 dias" (ou "401 / 3") enquanto a
   Home dizia 0 (achado #4 das personas). A correção de 22/09 foi passar a
   meta nos dois lugares — o que deixava a régua dependendo de cada chamador
   lembrar. `streaks.para_a_tela` é a porta única: ela deriva a meta do
   plano ativo, e nenhuma tela escolhe a sua.

3. **O que faltou ONTEM é dito com NÚMERO.** "Ontem faltou dieta ou água"
   era dito a quem registrou 3 refeições de 5 e bebeu 1,5 L de 3 — a pessoa
   registrou as duas coisas; o que faltou foi CHEGAR na meta. Medido no
   navegador em 24/09/2026.

DUAS MUDANÇAS DO MESMO DIA SE ENCONTRARAM AQUI, e este arquivo é onde elas
foram reconciliadas:

- o Progresso foi REDESENHADO (#137): as caixas de "aderência" e "média de
  kcal" que o item 1 media não existem mais. A régua sobreviveu no tile de
  Cardápio (`evolucao.tile_de_dieta` recorta pelos dias fechados, com a
  mesma frase de `tracking.adherence`), e é ele que os testes de tela leem
  agora. A correção de DADO continua inteira em `plans/tracking.py`, e os
  dois primeiros testes desta classe a medem direto, sem passar por tela;
- a MENSAGEM da ofensiva em zero deixou de citar ontem ("A sequência em
  zero convida em vez de cobrar", 24/09). O NÚMERO do item 3 continua
  calculado e continua sendo lido — em `Ofensiva.falta_ontem` —, e é lá que
  ele é medido. As duas decisões não se contradizem: uma diz que a frase
  não cobra, a outra diz que, quando o app for dizer o que faltou, diga com
  número em vez de rótulo.
"""
import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay
from plans import services, streaks, tracking
from plans.models import HydrationLog, MealLog, MealStatus
from plans.tests import create_complete_user
from workouts import services as treino_services

TILE = re.compile(
    r'class="tile tile--tendencia tile--(?P<chave>[a-z]+)[^"]*"[^>]*>'
    r"(?P<corpo>.*?)</div>",
    re.S,
)
VALOR = re.compile(r'class="tile__value"[^>]*>(?P<texto>.*?)</strong>', re.S)
FRASE = re.compile(r'class="tile__meta"[^>]*>(?P<texto>.*?)</span>', re.S)


def _texto(html):
    """O texto visível de um trecho — sem as tags e sem espaço dobrado."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _caixa(html):
    """A caixa do consolidado do Progresso: por tile, o número e a frase.

    Ancorada em `tile--<chave>` DENTRO do `<main>`, e não num recorte por
    `class="tiles"`: o Progresso de 23/09 trocou aquela classe por
    `tiles tiles--tendencia` num `<div>`, e o recorte antigo estourava. Um
    helper que se cala quando a tela muda seria pior que o erro — cinco
    leituras vazias são cinco leituras iguais —, e é por isso que quem
    chama confere o conjunto de tiles com `_conferir`.
    """
    corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
    caixa = {}
    for tile in TILE.finditer(corpo):
        dentro = tile.group("corpo")
        valor = VALOR.search(dentro)
        frase = FRASE.search(dentro)
        caixa[tile.group("chave")] = {
            "valor": _texto(valor.group("texto")) if valor else None,
            "frase": _texto(frase.group("texto")) if frase else "",
        }
    return caixa


class LeAsTelasMixin:
    #: peso, treino, cardápio e água — `evolucao.reunir` monta sempre os quatro.
    TILES = {"peso", "treino", "dieta", "agua"}

    def _conferir(self, caixa):
        self.assertEqual(set(caixa), self.TILES, caixa)
        return caixa

    def _numeros(self, resposta=None, sem=()):
        """Os números da caixa, prontos para comparar entre duas leituras.

        `sem` deixa de fora o tile que a ação sob teste PODE mover — é o
        caso do peso quando o que se mede é o efeito de registrar um peso.
        """
        resposta = resposta or self.client.get(reverse("plans:history"))
        self.assertEqual(resposta.status_code, 200)
        caixa = self._conferir(_caixa(resposta.content.decode()))
        return tuple(sorted(
            (chave, dados["valor"]) for chave, dados in caixa.items()
            if chave not in sem
        ))


class ACaixaDoConsolidadoLeUmRecorteSoTests(LeAsTelasMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="tiles@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        hoje = timezone.localdate()
        self.user.date_joined = timezone.now() - timedelta(days=3)
        self.user.save(update_fields=["date_joined"])
        services.sync_active_plan(self.user)
        plano = services.get_active_plan(self.user)
        self.horarios = list(plano.slots.all().order_by("time"))
        # Dois dias FECHADOS com 2 000 kcal cada, e hoje com 400 — o café.
        for atras, kcal in ((2, Decimal("1000")), (1, Decimal("1000"))):
            dia = hoje - timedelta(days=atras)
            for slot in self.horarios[:2]:
                MealLog.objects.update_or_create(
                    user=self.user, slot=slot, date=dia,
                    defaults={"status": MealStatus.DONE, "kcal": kcal},
                )
        MealLog.objects.update_or_create(
            user=self.user, slot=self.horarios[0], date=hoje,
            defaults={"status": MealStatus.DONE, "kcal": Decimal("400")},
        )

    def test_a_media_de_kcal_e_dos_dias_fechados_como_a_aderencia(self):
        """Os dois números da mesma caixa não podem ter denominadores
        diferentes: 2 000 é a média dos dois dias fechados; incluir hoje,
        que tem 400, dava 1 466."""
        linhas = tracking.history(self.user)
        self.assertEqual(tracking.adherence(linhas)["avg_kcal"], 2000)

    def test_a_media_nao_muda_com_a_hora_do_dia(self):
        """A prova da determinação: as mesmas linhas, lidas às 7h e às 23h,
        dão o mesmo consolidado. Era aqui que a tela discordava de si mesma —
        a média incluía um dia em andamento."""
        medidos = set()
        real = timezone.localtime
        for hora in (7, 13, 20, 23):
            with mock.patch.object(
                tracking.timezone, "localtime",
                lambda *a, **k: real(*a, **k).replace(hour=hora, minute=0),
            ):
                consolidado = tracking.adherence(tracking.history(self.user))
                medidos.add((consolidado["avg_kcal"], consolidado["adherence_pct"]))
        self.assertEqual(len(medidos), 1, medidos)

    def test_o_tile_do_cardapio_conta_so_os_dias_fechados(self):
        """A régua do item 1 na tela de hoje: as 4 refeições marcadas são as
        dos DOIS dias fechados. O café de hoje não entra — nem no numerador
        nem no denominador —, que é o que impede o número de cair de manhã e
        subir à noite."""
        caixa = self._conferir(_caixa(
            self.client.get(reverse("plans:history")).content.decode()
        ))
        self.assertIn("nos dias fechados", caixa["dieta"]["frase"])
        feitas, previstas = re.search(
            r"(\d+) de (\d+) refeições", caixa["dieta"]["frase"]
        ).groups()
        self.assertEqual(int(feitas), 4)
        self.assertEqual(
            caixa["dieta"]["valor"],
            "%d %%" % round(int(feitas) * 100 / int(previstas)),
        )

    def test_cinco_leituras_seguidas_da_tela_dao_os_mesmos_numeros(self):
        vistos = {self._numeros() for _ in range(5)}
        self.assertEqual(len(vistos), 1, vistos)

    def test_a_leitura_depois_do_post_do_peso_da_os_mesmos_numeros(self):
        """O caminho do relato: registrar o peso e cair no Progresso pelo
        redirect. O peso não muda refeição nenhuma, então cardápio, treino e
        água também não podem mudar — o tile do PESO muda, e é por isso que
        ele fica de fora da comparação."""
        antes = self._numeros(sem=("peso",))
        resposta = self.client.post(
            reverse("accounts:log_weight"), {"weight_kg": "83,5", "origem": "metricas"}
        )
        self.assertEqual(resposta.status_code, 302)
        depois = self._numeros(self.client.get(resposta["Location"]), sem=("peso",))
        self.assertEqual(antes, depois)

    def test_sabotagem_uma_refeicao_a_mais_num_dia_fechado_move_a_media(self):
        """Controle positivo: a caixa continua LENDO o banco — ela só parou
        de ler o dia em andamento."""
        antes = self._numeros()
        MealLog.objects.update_or_create(
            user=self.user, slot=self.horarios[2],
            date=timezone.localdate() - timedelta(days=1),
            defaults={"status": MealStatus.DONE, "kcal": Decimal("1000")},
        )
        self.assertNotEqual(antes, self._numeros())

    def test_sabotagem_uma_refeicao_a_mais_hoje_nao_move_a_media(self):
        """O outro lado do mesmo controle, e o defeito original: marcar uma
        refeição HOJE não pode mexer no número dos dias fechados."""
        antes = self._numeros()
        MealLog.objects.update_or_create(
            user=self.user, slot=self.horarios[1], date=timezone.localdate(),
            defaults={"status": MealStatus.DONE, "kcal": Decimal("900")},
        )
        self.assertEqual(antes, self._numeros())


class OPrimeiroDiaNaoTemMediaTests(LeAsTelasMixin, TestCase):
    """Conta nascida hoje: nenhum dia fechado, e nenhuma média a mostrar."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="dia1@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        self.user.date_joined = timezone.now()
        self.user.save(update_fields=["date_joined"])
        services.sync_active_plan(self.user)
        plano = services.get_active_plan(self.user)
        MealLog.objects.update_or_create(
            user=self.user, slot=plano.slots.all().order_by("time").first(),
            date=timezone.localdate(),
            defaults={"status": MealStatus.DONE, "kcal": Decimal("400")},
        )

    def test_o_consolidado_nao_tem_porcentagem_nem_media(self):
        consolidado = tracking.adherence(tracking.history(self.user))
        self.assertIsNone(consolidado["adherence_pct"])
        self.assertIsNone(consolidado["avg_kcal"])

    def test_a_tela_nao_inventa_uma_porcentagem_no_primeiro_dia(self):
        """Sem dia fechado não há nota: o tile diz "—" e convida. Um "0 %"
        ali seria uma reprovação inventada no primeiro dia de uso, e uma
        média que muda de hora em hora é o defeito que esta missão fechou."""
        caixa = self._conferir(_caixa(
            self.client.get(reverse("plans:history")).content.decode()
        ))
        self.assertEqual(caixa["dieta"]["valor"], "—")
        self.assertIn("Marque uma refeição", caixa["dieta"]["frase"])


class AOfensivaEUmaContaSoNasTresTelasTests(TestCase):
    """Home, Progresso e Conquistas contam a MESMA ofensiva.

    Elas já contaram diferente: as Conquistas chamavam `calcular` sem a meta
    de água e diziam "3 dias" (ou "401 / 3") enquanto a Home dizia 0.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="ofensiva@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        self.user.date_joined = timezone.now() - timedelta(days=10)
        self.user.save(update_fields=["date_joined"])

    def _espiar(self, rota):
        """O que cada tela pediu à ofensiva, e o que recebeu."""
        chamadas = []
        real = streaks.calcular

        def espia(*args, **kwargs):
            resultado = real(*args, **kwargs)
            chamadas.append((kwargs.get("meta_agua_ml"), resultado.dias))
            return resultado

        with mock.patch.object(streaks, "calcular", side_effect=espia):
            resposta = self.client.get(rota)
        self.assertEqual(resposta.status_code, 200, rota)
        self.assertTrue(chamadas, "%s não contou ofensiva nenhuma" % rota)
        return chamadas

    def test_as_tres_telas_pedem_a_mesma_meta_de_agua_e_recebem_o_mesmo_numero(self):
        medidos = set()
        for rota in (reverse("plans:today"), reverse("plans:history"),
                     reverse("achievements:list")):
            medidos.update(self._espiar(rota))
        self.assertEqual(len(medidos), 1, medidos)

    def test_nenhuma_tela_conta_ofensiva_sem_meta_de_agua(self):
        """Sem meta, `agua=True` em todo dia e a régua "treino e (dieta ou
        água)" fecha sozinha — era a origem do "401 / 3"."""
        for rota in (reverse("plans:today"), reverse("plans:history"),
                     reverse("achievements:list")):
            for meta, _ in self._espiar(rota):
                self.assertTrue(meta, "%s contou sem meta de água" % rota)


class OQueFaltouOntemDizONumeroTests(TestCase):
    """"Ontem faltou dieta ou água" para quem registrou as duas coisas.

    Medido no navegador em 24/09/2026: 3 refeições de 5 e 1 500 ml de uma
    meta de 3 000. A pessoa registrou; o que faltou foi CHEGAR na meta.

    A medição é em `Ofensiva.falta_ontem`, e não na frase: a MENSAGEM da
    ofensiva em zero deixou de citar ontem no mesmo dia ("Zero convida, e
    não cobra"). As duas decisões se completam — uma tira a cobrança da
    frase, a outra garante que o número, onde ele for dito, seja número.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="ontem@exemplo.com")

    def setUp(self):
        self.user.date_joined = timezone.now() - timedelta(days=10)
        self.user.save(update_fields=["date_joined"])
        self.hoje = timezone.localdate()
        self.ontem = self.hoje - timedelta(days=1)
        TrainingDay.objects.filter(user=self.user).delete()
        services.sync_active_plan(self.user)
        plano = services.get_active_plan(self.user)
        self.horarios = list(plano.slots.all().order_by("time"))
        for slot in self.horarios[:3]:
            MealLog.objects.update_or_create(
                user=self.user, slot=slot, date=self.ontem,
                defaults={"status": MealStatus.DONE, "kcal": Decimal("500")},
            )
        HydrationLog.objects.update_or_create(
            user=self.user, date=self.ontem, defaults={"ml": 1500}
        )

    def _ontem(self):
        return streaks.para_a_tela(self.user, hoje=self.hoje)

    def _falta_ontem(self):
        return " · ".join(self._ontem().falta_ontem)

    def test_o_numero_de_ontem_traz_a_dieta_e_a_agua(self):
        ofensiva = self._ontem()
        self.assertEqual(ofensiva.dias, 0)
        medido = " · ".join(ofensiva.falta_ontem)
        self.assertIn("3 de 5 refeições", medido)
        self.assertIn("1,5", medido)
        self.assertIn("3 L", medido)

    def test_ontem_nao_e_dito_com_o_rotulo_solto_de_antes(self):
        """Nem no número, nem na frase: `falta_ontem` traz a medida, e a
        mensagem da ofensiva em zero não cobra ontem nenhuma."""
        self.assertNotIn("dieta ou água", self._falta_ontem())
        self.assertNotIn("faltou", self._ontem().mensagem)

    def test_sem_serie_num_dia_de_treino_o_numero_diz_isso(self):
        """Os dias previstos saem da FICHA (`plan.sessions`), e não de
        `TrainingDay` — criar só a linha do dia deixaria `previstos` vazio e
        o teste passaria verde medindo outra coisa."""
        call_command("seed_workouts", verbosity=0)
        TrainingDay.objects.create(
            user=self.user, weekday=self.ontem.weekday(), duration_min=60
        )
        treino_services.create_routine(self.user)
        self.assertIn("nenhuma série", self._falta_ontem())

    def test_sabotagem_mudar_a_agua_de_ontem_muda_o_numero(self):
        antes = self._falta_ontem()
        HydrationLog.objects.filter(user=self.user, date=self.ontem).update(ml=800)
        self.assertNotEqual(antes, self._falta_ontem())
        self.assertIn("0,8", self._falta_ontem())

    def test_o_que_falta_hoje_continua_com_o_rotulo_curto(self):
        """O que FECHA o dia, sem número: é a decisão de 22/09/2026 e ela
        não muda aqui — o que ganhou número foi ONTEM, que já fechou."""
        self.assertEqual(self._ontem().falta_hoje, ["dieta ou água"])
