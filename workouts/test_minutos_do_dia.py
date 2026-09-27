# -*- coding: utf-8 -*-
"""O painel e a ficha contam o MESMO treino de hoje.

Observado em produção em 18/09/2026 e medido em 24/09: o cartão de hoje do
painel dizia "~57 min" e a ficha do mesmo dia dizia "~60". Não eram duas
contas de duração — a conta é uma só desde 13/09 (`segundos_da_sessao`) —,
eram duas OPÇÕES: `total_sets` e `estimated_minutes` são da opção 1, a
referência da semana, e a ficha mostra a opção DO DIA (a pinada pela
primeira série, senão a variação do ciclo). Num dia de variação 2 os dois
números discordam por construção; medido no `abc2` do intermediário de
cinco dias, a letra B fecha em 57 min na opção 1 e 60 na 2, e a C em 25
séries contra 27.

A opção 1 continua sendo a referência do PROGRAMA — é o que os cartões das
outras letras mostram, e as duas opções são equivalentes por construção
(diferença ≤ 1 série por grupo, ≤ 5 min). O que não pode é o cartão de
HOJE, que fala do treino que a pessoa vai fazer agora, anunciar o número de
outro.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, TrainingDay
from config import relogio
from plans.tests import create_complete_user
from workouts import services
from workouts.tests import sem_scripts


def _pessoa(email, dias=5):
    user = create_complete_user(
        email=email,
        experiencia="intermediario",
        split_preference="two",
        split_preference_confirmada=True,
        duracao_treino=DuracaoTreino.PADRAO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class OPainelEAFichaContamOMesmoTreinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = _pessoa("minutos@exemplo.com")
        self.plano = services.create_routine(self.user)
        self.linhas = list(self.plano.sessions.prefetch_related("exercises__exercise"))
        self.client.force_login(self.user)

    def _dia_de_variacao(self, opcao, com_numeros_diferentes=True):
        """Um dia da semana em que a letra cai na `opcao` pedida — e, se
        pedido, em que as duas opções dão números DIFERENTES (senão o teste
        passaria sem medir nada)."""
        hoje = timezone.localdate()
        for n in range(0, 21):
            dia = hoje + timedelta(days=n)
            sessao = services.sessao_do_dia(self.plano, dia, self.linhas)
            if sessao is None or len(sessao.opcoes) < 2:
                continue
            if services.variacao_do_dia(self.plano, dia, sessao, self.linhas) != opcao:
                continue
            numeros = {
                k: (sessao.series_da_opcao(k), sessao.minutos_da_opcao(k)) for k in sessao.opcoes
            }
            if not com_numeros_diferentes or len(set(numeros.values())) > 1:
                return dia, sessao, numeros
        self.skipTest("o catálogo de hoje não tem letra com opções de números diferentes")

    def _painel(self):
        html = sem_scripts(self.client.get(reverse("workouts:routine")).content.decode())
        bloco = html.split('class="hoje__meta', 1)[1].split("</ul>", 1)[0]
        return bloco

    def test_o_cartao_de_hoje_anuncia_os_numeros_da_opcao_do_dia(self):
        """O caso real: num dia de variação 2, o painel dizia os números da
        opção 1. A régua é a IGUALDADE com a ficha do mesmo dia — não um
        número escrito à mão, que envelhece com o catálogo."""
        dia, sessao, numeros = self._dia_de_variacao(2)
        with relogio.congelado_em(dia):
            bloco = self._painel()
            ficha = sem_scripts(
                self.client.get(reverse("workouts:ficha", args=[sessao.pk])).content.decode()
            )
        series, minutos = numeros[2]
        self.assertIn(">%d</b> séries" % series, bloco)
        self.assertIn(">%d</b> min" % minutos, bloco)
        # E a ficha do mesmo dia diz o mesmo — é o par que estava divergindo.
        cabeca = ficha.split('<p class="lead">', 1)[1].split("</p>", 1)[0]
        self.assertIn("%d séries" % series, cabeca)
        self.assertIn("~%d min" % minutos, cabeca)
        self.assertNotEqual(numeros[1], numeros[2], "o dia escolhido precisa distinguir as opções")

    def test_no_dia_de_variacao_1_nada_muda(self):
        """Controle: onde a opção do dia É a referência, o cartão continua
        dizendo o mesmo de sempre — a correção não move o caso comum."""
        dia, sessao, numeros = self._dia_de_variacao(1)
        with relogio.congelado_em(dia):
            bloco = self._painel()
        series, minutos = numeros[1]
        self.assertIn(">%d</b> séries" % series, bloco)
        self.assertIn(">%d</b> min" % minutos, bloco)

    def test_a_escolha_pinada_vence_a_variacao_tambem_no_cartao(self):
        """Quem pinou a outra opção (a primeira série grava a escolha) vê no
        cartão os números do treino que está fazendo, não os do ciclo."""
        dia, sessao, numeros = self._dia_de_variacao(1)
        with relogio.congelado_em(dia):
            services.registrar_escolha(self.user, sessao, 2)
            bloco = self._painel()
        series, minutos = numeros[2]
        self.assertIn(">%d</b> séries" % series, bloco)
        self.assertIn(">%d</b> min" % minutos, bloco)

    def test_o_programa_continua_falando_da_referencia(self):
        """`total_sets` e `estimated_minutes` NÃO mudam de significado: eles
        são o retrato da letra para a semana (a opção 1), e é o que os
        cartões das outras letras mostram. Mudar isso faria o programa
        oscilar conforme o dia em que a tela é aberta.

        Com CONTROLE POSITIVO: a primeira versão deste teste media só a
        letra A, cujas duas opções dão 59 min e 25 séries — trocar a
        referência para a outra opção não mexia em número nenhum e a
        sabotagem passava verde. A régua só vale sobre uma letra em que as
        opções DIFEREM.
        """
        distinguem = 0
        for sessao in self.linhas:
            with self.subTest(letra=sessao.label):
                self.assertEqual(sessao.total_sets, sessao.series_da_opcao(sessao.opcoes[0]))
                self.assertEqual(sessao.estimated_minutes, sessao.minutos_da_opcao(sessao.opcoes[0]))
                numeros = {
                    (sessao.series_da_opcao(k), sessao.minutos_da_opcao(k)) for k in sessao.opcoes
                }
                distinguem += len(numeros) > 1
        self.assertGreater(distinguem, 0, "nenhuma letra distingue as opções: o teste não mede nada")
