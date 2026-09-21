"""A camada de consulta do painel — correção das perguntas difíceis (funil,
retenção) e a chave de PESSOA (uma pessoa conta uma vez)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from . import consultas
from .models import Event

User = get_user_model()


def ev(nome, quando, pessoa=None, anon="", **props):
    campos = {}
    if pessoa is not None:
        campos["user"] = pessoa
    return Event.objects.create(name=nome, ts=quando, anon_id=anon, props=props, **campos)


class PessoaTests(TestCase):
    def test_uma_pessoa_em_muitos_toques_conta_uma_vez(self):
        agora = timezone.now()
        for _ in range(5):
            ev("tela.vista", agora, anon="a")
        ev("tela.vista", agora, anon="b")
        self.assertEqual(consultas.ativos(1), 2)

    def test_logado_e_anonimo_sao_pessoas_diferentes(self):
        u = User.objects.create_user(email="p@b.com", password="senha-bem-forte-123")
        ev("tela.vista", timezone.now(), pessoa=u)
        ev("tela.vista", timezone.now(), anon="x")
        self.assertEqual(consultas.ativos(1), 2)


class FunilTests(TestCase):
    def test_conversao_respeita_a_ordem_do_tempo(self):
        """Quem fez o passo 2 ANTES do passo 1 não converteu."""
        base = timezone.now()
        # pessoa A: iniciou -> concluiu (converteu)
        ev("onboarding.iniciado", base, anon="A")
        ev("onboarding.concluido", base + timedelta(minutes=5), anon="A")
        # pessoa B: só iniciou
        ev("onboarding.iniciado", base, anon="B")
        # pessoa C: concluiu ANTES de iniciar (não conta)
        ev("onboarding.concluido", base, anon="C")
        ev("onboarding.iniciado", base + timedelta(minutes=1), anon="C")

        etapas = consultas.funil(["onboarding.iniciado", "onboarding.concluido"], 7)
        self.assertEqual(etapas[0]["pessoas"], 3)  # A, B, C iniciaram
        self.assertEqual(etapas[1]["pessoas"], 1)  # só A converteu na ordem
        self.assertEqual(etapas[1]["mediana_s"], 300)  # 5 min


class RetencaoTests(TestCase):
    def test_coorte_conta_quem_voltou_na_semana_seguinte(self):
        u1 = User.objects.create_user(email="u1@b.com", password="senha-bem-forte-123")
        u2 = User.objects.create_user(email="u2@b.com", password="senha-bem-forte-123")
        semana = timezone.now() - timedelta(weeks=3)
        ev("conta.criada", semana, pessoa=u1)
        ev("conta.criada", semana, pessoa=u2)
        # u1 volta na semana seguinte; u2 não
        ev("agua.registrada", semana + timedelta(weeks=1), pessoa=u1)

        linhas = consultas.retencao(semanas=4)
        self.assertEqual(len(linhas), 1)
        celulas = linhas[0]["celulas"]
        self.assertEqual(celulas[0]["n"], 2)  # semana 0: os dois
        self.assertEqual(celulas[1]["n"], 1)  # semana 1: só u1
        self.assertEqual(celulas[1]["pct"], 50)


class ExplorarETimelineTests(TestCase):
    def test_agrupar_por_propriedade(self):
        agora = timezone.now()
        ev("dieta.refeicao_registrada", agora, anon="a", opcao="almoço")
        ev("dieta.refeicao_registrada", agora, anon="a", opcao="almoço")
        ev("dieta.refeicao_registrada", agora, anon="b", opcao="janta")
        grupos = {g["valor"]: g for g in consultas.explorar(
            "dieta.refeicao_registrada", 7, agrupar="opcao")}
        self.assertEqual(grupos["almoço"]["n"], 2)
        self.assertEqual(grupos["almoço"]["pessoas"], 1)
        self.assertEqual(grupos["janta"]["n"], 1)

    def test_timeline_por_id_de_usuario_e_anon(self):
        u = User.objects.create_user(email="t@b.com", password="senha-bem-forte-123")
        ev("tela.vista", timezone.now(), pessoa=u)
        ev("agua.registrada", timezone.now(), anon="anon-1")
        self.assertEqual(len(consultas.linha_do_tempo(str(u.pk))), 1)
        self.assertEqual(len(consultas.linha_do_tempo("anon-1")), 1)
