# -*- coding: utf-8 -*-
"""Mudar a restrição alimentar tem de invalidar o cardápio NO MESMO POST.

O defeito, ponta a ponta: a pessoa marca "sem peixe" no Perfil, a tela diz
"Alterações salvas." — e o cardápio continua oferecendo sardinha. Não só
naquela tela: na visita seguinte à Home também, porque `plan_is_current`
NUNCA olhou para as restrições. `NutritionPlan` guardava peso, altura,
idade, sexo, atividade, objetivo e dias de treino; o que escolhe as
RECEITAS — as restrições e o estilo de cardápio — ficava de fora do
retrato, então o motor comparava o plano velho com as entradas de hoje,
não via diferença nenhuma, e devolvia "está atual".

"Plano é retrato" é a doutrina, e o retrato estava incompleto: ele
fotografava o que calcula a META e não o que escolhe a COMIDA.

E há um segundo tempo no mesmo POST: `dietary_tags` é ManyToMany, e um
`ModelForm` só grava M2M em `save_m2m()`, depois do `save()` da linha.
Quem remontar o cardápio antes disso lê as restrições VELHAS e remonta o
mesmo cardápio — o defeito de volta, agora com uma consulta a mais.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import DietaryTag, MealCategory, MealTemplate, TagKind
from plans import services
from plans.models import MealOption, NutritionPlan
from accounts.test_equipamento_pela_tela import campos_do_formulario
from plans.tests import CatalogFixture, create_complete_user, make_template


def _receitas(plan):
    return set(
        MealOption.objects.filter(slot__plan=plan).values_list(
            "template__name", flat=True
        )
    )


class CatalogoComRestricao(CatalogFixture):
    """O catálogo mínimo mais DUAS restrições de verdade.

    "sem-peixe" está em todas as receitas MENOS uma (a sardinha), que é o que
    faz marcar a restrição mudar o cardápio de verdade; "vegetariana" está em
    duas, para o teste de ordem ter duas tags para embaralhar. A tag descreve
    o que a refeição É, e o filtro exige TODAS as do perfil.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sardinha = make_template(
            "Sardinha com arroz", MealCategory.MAIN,
            [(cls.rice, 150, True)],
        )
        for modelo in MealTemplate.objects.exclude(pk=cls.sardinha.pk):
            modelo.tags.add(
                DietaryTag.objects.get_or_create(
                    slug="sem-peixe",
                    defaults={"name": "Sem peixe", "kind": TagKind.RESTRICTION},
                )[0]
            )
        vegetariana = DietaryTag.objects.get_or_create(
            slug="vegetariana",
            defaults={"name": "Vegetariana", "kind": TagKind.RESTRICTION},
        )[0]
        for modelo in MealTemplate.objects.filter(name__startswith="Arroz"):
            modelo.tags.add(vegetariana)


class ARestricaoEntraNoRetratoDoPlanoTests(CatalogoComRestricao):
    def setUp(self):
        self.user = create_complete_user(email="restricao@exemplo.com")
        self.perfil = self.user.profile
        self.plano = services.sync_active_plan(self.user)[0]
        self.tag = DietaryTag.objects.get(slug="sem-peixe")

    def test_o_plano_guarda_as_restricoes_de_quando_nasceu(self):
        self.perfil.dietary_tags.add(self.tag)
        novo = services.create_plan(self.user)
        self.assertEqual(novo.restricoes, self.tag.slug)

    def test_marcar_uma_restricao_desatualiza_o_plano(self):
        """A régua: `plan_is_current` tem de dizer NÃO. Antes dizia SIM — as
        restrições não estavam em `_INPUT_FIELDS`."""
        entradas = services.build_inputs(self.user)
        self.assertTrue(services.plan_is_current(self.plano, entradas))
        self.perfil.dietary_tags.add(self.tag)
        self.assertFalse(
            services.plan_is_current(self.plano, services.build_inputs(self.user)),
            "o plano continuou 'atual' com uma restrição nova",
        )

    def test_desmarcar_a_restricao_tambem_desatualiza(self):
        self.perfil.dietary_tags.add(self.tag)
        plano = services.create_plan(self.user)
        self.perfil.dietary_tags.clear()
        self.assertFalse(
            services.plan_is_current(plano, services.build_inputs(self.user))
        )

    def test_trocar_o_estilo_de_cardapio_desatualiza(self):
        """MESMO defeito, MESMO formulário: `meal_style` escolhe receita e
        também estava fora do retrato. Corrigir metade seria deixar a pessoa
        trocar para "econômica" e continuar vendo salmão."""
        from accounts.models import MealStyle

        outro = next(
            valor for valor, _ in MealStyle.choices if valor != self.perfil.meal_style
        )
        self.perfil.meal_style = outro
        self.perfil.save(update_fields=["meal_style"])
        self.assertFalse(
            services.plan_is_current(self.plano, services.build_inputs(self.user))
        )

    def test_a_ordem_das_restricoes_nao_inventa_diferenca(self):
        """O retrato é ORDENADO: com duas tags, a ordem do `values_list` varia
        e o plano nasceria "desatualizado" na consulta seguinte — regenerando
        o cardápio em toda visita à Home, para sempre."""
        self.perfil.dietary_tags.set(
            DietaryTag.objects.filter(slug__in=("sem-peixe", "vegetariana"))
        )
        plano = services.create_plan(self.user)
        for _ in range(3):
            self.assertTrue(
                services.plan_is_current(plano, services.build_inputs(self.user))
            )

    def test_plano_antigo_sem_retrato_de_restricao_nao_e_invalidado_a_toa(self):
        """Migration `default=""`: quem já tinha plano e NENHUMA restrição
        continua com ele. Invalidar todo mundo no deploy seria trocar o
        cardápio de quem não pediu nada."""
        NutritionPlan.objects.filter(pk=self.plano.pk).update(restricoes="", meal_style="")
        self.plano.refresh_from_db()
        self.assertTrue(
            services.plan_is_current(self.plano, services.build_inputs(self.user))
        )


class OPerfilRemontaOCardapioNoMesmoPostTests(CatalogoComRestricao):
    """O caminho da pessoa: Perfil › restrições › Salvar."""

    def setUp(self):
        self.user = create_complete_user(email="perfil-restricao@exemplo.com")
        self.perfil = self.user.profile
        self.plano = services.sync_active_plan(self.user)[0]
        self.client.force_login(self.user)
        self.tag = DietaryTag.objects.get(slug="sem-peixe")
        self.url = reverse("accounts:onboarding_step", kwargs={"step": 3})

    def _salvar(self, tags):
        """O formulário RENDERIZADO, como um navegador o enviaria.

        Um `post` de dicionário prova a VIEW e não a TELA: nome de campo
        trocado no template passaria verde. É a régua que
        `accounts/test_equipamento_pela_tela.py` já aplica.
        """
        html = self.client.get(self.url + "?origem=perfil").content.decode()
        dados = campos_do_formulario(html)
        dados["dietary_tags"] = [str(t.pk) for t in tags]
        return self.client.post(self.url + "?origem=perfil", dados)

    def test_salvar_a_restricao_ja_deixa_outro_cardapio(self):
        antes = _receitas(self.plano)
        resposta = self._salvar([self.tag])
        self.assertEqual(resposta.status_code, 302)
        plano = services.get_active_plan(self.user)
        self.assertNotEqual(
            plano.pk, self.plano.pk, "o cardápio não foi remontado no mesmo POST"
        )
        self.assertEqual(plano.restricoes, self.tag.slug)
        # A sardinha é a ÚNICA receita sem a tag: com "sem peixe" marcado,
        # ela não pode mais aparecer.
        self.assertNotIn("Sardinha com arroz", _receitas(plano))
        self.assertTrue(antes, "o fixture precisa de cardápio antes")

    def test_a_mensagem_diz_o_que_valeu(self):
        resposta = self._salvar([self.tag])
        mensagens = [str(m) for m in resposta.wsgi_request._messages]
        self.assertTrue(
            any("cardápio" in m.lower() for m in mensagens),
            "a tela disse 'Alterações salvas.' sem dizer que o cardápio mudou: %s"
            % mensagens,
        )

    def test_salvar_sem_mudar_nada_nao_remonta(self):
        """Idempotência: reabrir e salvar igual não pode trocar o cardápio de
        quem não pediu — é a mesma régua de `sync_active_plan`."""
        self._salvar([])
        self.assertEqual(services.get_active_plan(self.user).pk, self.plano.pk)

    def test_sabotagem_o_m2m_do_post_e_o_que_o_motor_le(self):
        """Se o cardápio for remontado ANTES do `save_m2m()`, o motor lê as
        restrições velhas e remonta o mesmo cardápio. Esta é a prova de que a
        remontagem acontece DEPOIS: o plano novo tem a tag do POST."""
        self._salvar([self.tag])
        self.assertEqual(
            services.get_active_plan(self.user).restricoes, self.tag.slug
        )
