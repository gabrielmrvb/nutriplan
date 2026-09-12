# -*- coding: utf-8 -*-
"""A primeira passagem pelo cadastro não abre com resposta marcada.

Medido no navegador em 12/09/2026, a 390px, com uma conta nova: o passo 2
abria com "Manter o peso" e "Pouco ativo" já escolhidos, o passo 4 com
"3 grupos por dia" e o passo 5 com "Variada e elaborada" — os padrões de
fábrica do `Profile`, que existem para a migração não reescrever o plano de
quem nunca viu a pergunta. Na TELA eles viram outra coisa: quem toca
"Continuar" sem ler declara um objetivo que não escolheu, e o cartão de
"2 grupos por dia" dizia "Mais popular" ao lado de um "3 grupos" já marcado —
a tela recomendava um e entregava outro.

É a regra que `experiencia` já segue (`workouts/test_experiencia.py`): opção
pré-marcada é o padrão silencioso, na entrada. Vale só na primeira passagem;
quem já respondeu volta e encontra a resposta dele.

Toda asserção de "nenhum marcado" vem com a contagem dos rádios ao lado: um
seletor errado acharia zero marcados porque acharia zero rádios, e passaria.
"""
import re

from django.test import TestCase
from django.urls import reverse

from accounts.models import ONBOARDING_DONE, Profile, User

STEP1 = {"sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82.4"}
STEP2 = {"goal": "cut", "activity_level": "light"}
STEP3_QUATRO_DIAS = {
    "weekdays": ["0", "1", "3", "5"],
    "wake_time": "07:00",
    "sleep_time": "23:30",
}
STEP4 = {"split_preference": "three"}
STEP5 = {"meal_style": "quick"}


def passo(n):
    return reverse("accounts:onboarding_step", kwargs={"step": n})


class _Cadastro(TestCase):
    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="nova@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)

    def radios(self, n, campo):
        """(quantos rádios do campo há na tela, quais valores estão marcados)."""
        html = self.client.get(passo(n)).content.decode()
        tags = re.findall(r'<input[^>]*name="%s"[^>]*>' % campo, html)
        marcados = [
            re.search(r'value="([^"]*)"', t).group(1) for t in tags if "checked" in t
        ]
        return len(tags), marcados


class OPasso2AbreEmBrancoTests(_Cadastro):
    def setUp(self):
        super().setUp()
        self.client.post(passo(1), STEP1)

    def test_objetivo_e_rotina_abrem_sem_marcacao_na_primeira_vez(self):
        total, marcados = self.radios(2, "goal")
        self.assertEqual(total, 4)
        self.assertEqual(marcados, [])
        total, marcados = self.radios(2, "activity_level")
        self.assertEqual(total, 3)
        self.assertEqual(marcados, [])

    def test_o_padrao_de_fabrica_continua_no_banco_e_so_a_tela_o_esconde(self):
        """Controle: o perfil TEM `maintain` e `sedentary` gravados pelo passo
        1 — é exatamente isso que a tela não pode apresentar como escolha."""
        perfil = Profile.objects.get(user=self.pessoa)
        self.assertEqual(perfil.goal, "maintain")
        self.assertEqual(perfil.activity_level, "sedentary")

    def test_enviar_sem_escolher_e_recusado_e_o_passo_nao_avanca(self):
        resposta = self.client.post(passo(2), {})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'class="field__errors"')
        self.assertEqual(Profile.objects.get(user=self.pessoa).onboarding_step, 2)

    def test_quem_respondeu_volta_e_encontra_a_resposta(self):
        self.client.post(passo(2), STEP2)
        self.assertEqual(self.radios(2, "goal"), (4, ["cut"]))
        self.assertEqual(self.radios(2, "activity_level"), (3, ["light"]))


class OPasso4AbreEmBrancoTests(_Cadastro):
    def setUp(self):
        super().setUp()
        self.client.post(passo(1), STEP1)
        self.client.post(passo(2), STEP2)
        self.client.post(passo(3), STEP3_QUATRO_DIAS)

    def test_a_divisao_abre_sem_marcacao_e_o_selo_de_mais_popular_esta_la(self):
        total, marcados = self.radios(4, "split_preference")
        self.assertEqual(total, 3)
        self.assertEqual(marcados, [])
        self.assertContains(self.client.get(passo(4)), "Mais popular")

    def test_escolher_tres_de_proposito_volta_marcado(self):
        """TRES é o padrão de fábrica E uma resposta válida; a diferença é a
        confirmação, e é ela que faz o rádio voltar marcado."""
        self.client.post(passo(4), STEP4)
        self.assertEqual(self.radios(4, "split_preference"), (3, ["three"]))

    def test_quem_terminou_o_cadastro_sem_responder_ainda_abre_em_branco(self):
        """Quem treinava três dias pulou o passo 4. Ao marcar o quarto dia, o
        app manda de volta para cá — e a pergunta continua sem resposta."""
        Profile.objects.filter(user=self.pessoa).update(
            onboarding_step=ONBOARDING_DONE, split_preference_confirmada=False
        )
        self.assertEqual(self.radios(4, "split_preference"), (3, []))


class OPasso5AbreEmBrancoTests(_Cadastro):
    def setUp(self):
        super().setUp()
        self.client.post(passo(1), STEP1)
        self.client.post(passo(2), STEP2)
        self.client.post(passo(3), STEP3_QUATRO_DIAS)
        self.client.post(passo(4), STEP4)

    def test_o_cardapio_abre_sem_marcacao_e_o_recomendado_esta_la(self):
        total, marcados = self.radios(5, "meal_style")
        self.assertEqual(total, 2)
        self.assertEqual(marcados, [])
        self.assertContains(self.client.get(passo(5)), "Recomendado")

    def test_quem_respondeu_volta_e_encontra_a_resposta(self):
        self.client.post(passo(5), STEP5)
        self.assertEqual(self.radios(5, "meal_style"), (2, ["quick"]))

    def test_quem_terminou_o_cadastro_edita_com_a_resposta_gravada(self):
        """Edição pelo Perfil: o valor do banco é a resposta, e aparece."""
        self.client.post(passo(5), {"meal_style": "varied"})
        Profile.objects.filter(user=self.pessoa).update(onboarding_step=ONBOARDING_DONE)
        self.assertEqual(self.radios(5, "meal_style"), (2, ["varied"]))
