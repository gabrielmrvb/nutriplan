# -*- coding: utf-8 -*-
"""A duração do treino se escolhe NA ÁREA DE TREINO, e a ficha é remontada.

Avaliação de 16/09/2026 (D4): a pergunta saiu do cadastro em 10/09 — certo,
ninguém calibra "rápido, padrão ou completo" antes de ver uma ficha — e o
CLAUDE.md passou a dizer que "Completo/Rápido é escolha da área de Treino".
Só que a área de Treino não tinha onde escolher: a ficha oferecia "Versão
rápida" (a opção do dia passando por `escolher_para_o_tempo`), "Dados do
cálculo" dizia "até 60 min" fixo, e o Completo de 90 minutos — a ficha
inteira — não tinha porta nenhuma.

O painel ganha a escolha em "Seu programa": Rápido · Padrão · Completo, com
o teto de cada um, e "Aplicar" grava `Profile.duracao_treino`, deriva
`TrainingDay.duration_min` (o contrato do cardápio, como `TrainingForm.save`
já fazia) e deixa `sync_active_routine` fazer o que a doutrina de 17/09 já
prevê — faixa diferente da que a ficha guarda é entrada da pessoa, e
remonta. As mesmas travas de sempre continuam: com série registrada hoje a
ficha muda amanhã; ficha ajustada à mão não é remontada. A tela diz qual.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, MINUTOS_POR_DURACAO
from workouts import services
from workouts.models import Measure, TrainingPlan
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


#: "Duração: até <span class="num">60</span> min por sessão" — o número leva
#: a classe de tabular; a régua lê através dela.
_ATE = r'Duração: até\s*(?:<span class="num">)?%d(?:</span>)?\s*min'


class EscolherADuracaoNoTreinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="duracao@exemplo.com", weekdays=dias_incluindo_hoje(5))
        self.perfil = self.pessoa.profile
        self.perfil.duracao_treino = DuracaoTreino.PADRAO
        self.perfil.save(update_fields=["duracao_treino"])
        self.plano = services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _aplicar(self, faixa):
        return self.client.post(reverse("workouts:duracao"), {"duracao_treino": faixa})

    def _plano_ativo(self):
        return TrainingPlan.objects.get(user=self.pessoa, is_active=True)

    def test_o_painel_oferece_as_tres_faixas_com_a_atual_marcada(self):
        html = sem_scripts(self.client.get(reverse("workouts:routine")).content.decode())
        self.assertIn('action="%s"' % reverse("workouts:duracao"), html)
        for faixa in DuracaoTreino.escolhas_visiveis():
            self.assertIn('value="%s"' % faixa.value, html)
        self.assertRegex(html, r'value="padrao"[^>]*\bchecked\b')
        self.assertNotRegex(html, r'value="completo"[^>]*\bchecked\b')
        self.assertNotIn('value="livre"', html)
        # O que a pessoa está usando, dito em minutos, antes de abrir a escolha.
        self.assertRegex(html, _ATE % 60)

    def test_aplicar_completo_grava_o_perfil_e_remonta_a_ficha(self):
        resposta = self._aplicar("completo")
        self.assertRedirects(resposta, reverse("workouts:routine"), fetch_redirect_response=False)
        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.duracao_treino, DuracaoTreino.COMPLETO)
        self.assertEqual(
            set(self.pessoa.training_days.values_list("duration_min", flat=True)),
            {MINUTOS_POR_DURACAO[DuracaoTreino.COMPLETO]},
        )
        novo = self._plano_ativo()
        self.assertNotEqual(novo.pk, self.plano.pk, "a ficha não foi remontada")
        self.assertEqual(novo.duracao, DuracaoTreino.COMPLETO)
        html = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertRegex(html, _ATE % 90)

    def test_a_ficha_remontada_fica_dentro_do_teto_escolhido(self):
        """Controle positivo: Rápido produz sessões de até 30 minutos —
        senão a escolha seria só um rótulo."""
        self._aplicar("rapido")
        novo = self._plano_ativo()
        for sessao in novo.sessions.all():
            self.assertLessEqual(sessao.estimated_minutes, 30, sessao.name)

    def test_com_serie_registrada_hoje_a_ficha_espera_o_dia_virar(self):
        sessao = escolher_opcao_de_hoje(self.pessoa)
        item = next(i for i in sessao.da_opcao(1) if i.measure == Measure.REPS)
        services.append_set(self.pessoa, item.exercise, 40, reps=10, op_id="")
        resposta = self._aplicar("completo", )
        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.duracao_treino, DuracaoTreino.COMPLETO)
        self.assertEqual(self._plano_ativo().pk, self.plano.pk)
        mensagens = [str(m) for m in resposta.wsgi_request._messages]
        self.assertTrue(any("amanhã" in m for m in mensagens), mensagens)

    def test_ficha_ajustada_a_mao_nao_e_remontada_e_a_tela_diz(self):
        self.plano.customized_at = timezone.now()
        self.plano.save(update_fields=["customized_at"])
        resposta = self._aplicar("rapido")
        self.assertEqual(self._plano_ativo().pk, self.plano.pk)
        mensagens = [str(m) for m in resposta.wsgi_request._messages]
        self.assertTrue(any("ajust" in m for m in mensagens), mensagens)

    def test_valor_fora_da_lista_nao_grava_nada(self):
        for estranho in ("livre", "xyz", ""):
            resposta = self._aplicar(estranho)
            self.assertEqual(resposta.status_code, 302, estranho)
            self.perfil.refresh_from_db()
            self.assertEqual(self.perfil.duracao_treino, DuracaoTreino.PADRAO, estranho)
            self.assertEqual(self._plano_ativo().pk, self.plano.pk, estranho)

    def test_repetir_a_faixa_atual_nao_remonta(self):
        self._aplicar("padrao")
        self.assertEqual(self._plano_ativo().pk, self.plano.pk)

    def test_o_get_leva_ao_painel(self):
        resposta = self.client.get(reverse("workouts:duracao"))
        self.assertRedirects(resposta, reverse("workouts:routine"), fetch_redirect_response=False)
