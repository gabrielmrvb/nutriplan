# -*- coding: utf-8 -*-
"""Reabrir uma etapa e salvar sem mexer em nada não pode mudar resposta nenhuma.

Três casos da avaliação de 16/09/2026 (B2, B3, B4), e os três têm a mesma
forma: o formulário de edição abre com um campo VAZIO (ou grava um dado que
ninguém mediu) e o `save()` transforma o vazio em resposta. Quem só veio
corrigir a altura, ou trocar o cardápio, sai com a experiência apagada, a
prioridade promovida ou uma pesagem de hoje que não aconteceu.

A régua é uma só: reabrir + salvar = nada muda.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.forms import BodyDataForm, InteressesForm, TrainingForm
from accounts.models import Experiencia, Pilar, Profile, WeightEntry
from plans.tests import create_complete_user


def _dados_iniciais(form):
    """O que a tela renderizada devolveria se a pessoa tocasse em Salvar sem
    mexer em nada: o `initial` de cada campo, no formato que o POST traz."""
    dados = {}
    for nome, campo in form.fields.items():
        valor = form.get_initial_for_field(campo, nome)
        if valor is None or valor == "":
            continue
        if isinstance(valor, (list, tuple)):
            dados[nome] = [str(v) for v in valor]
        elif hasattr(valor, "strftime"):
            dados[nome] = valor.strftime("%H:%M") if hasattr(valor, "hour") and not hasattr(valor, "year") else valor.isoformat()
        else:
            dados[nome] = str(valor)
    return dados


class ExperienciaSobreviveAReedicaoSemDiasTests(TestCase):
    """B2 — `TrainingForm` só preenchia `experiencia` dentro de `if existing`
    (dias de treino). Quem respondeu "há quanto tempo treina" com ZERO dias
    ("Se não treina ainda, pode deixar em branco") reabria a etapa com o rádio
    vazio, e salvar gravava "". Reproduzido em produção: a etapa 3 mostrava
    "Experiência: Intermediário", reabri a 2, salvei, a linha sumiu."""

    def setUp(self):
        # `musculacao="sim"`: desde 22/09/2026 a etapa 2 pergunta "você faz
        # musculação?" e a resposta é obrigatória; sem dias gravados não há
        # "sim" implícito, então quem reabre precisa ter respondido.
        self.user = create_complete_user(experiencia=Experiencia.AVANCADO, musculacao="sim")
        self.user.training_days.all().delete()

    def test_o_formulario_abre_com_a_experiencia_gravada_mesmo_sem_dias(self):
        form = TrainingForm(user=self.user)
        self.assertEqual(
            form.get_initial_for_field(form.fields["experiencia"], "experiencia"),
            Experiencia.AVANCADO,
        )

    def test_reabrir_e_salvar_sem_mexer_mantem_a_experiencia(self):
        aberto = TrainingForm(user=self.user)
        enviado = TrainingForm(_dados_iniciais(aberto), user=self.user)
        self.assertTrue(enviado.is_valid(), enviado.errors)
        enviado.save()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.experiencia, Experiencia.AVANCADO)

    def test_quem_nunca_respondeu_e_PERGUNTADO_em_vez_de_gravar_em_branco(self):
        """A REGRA VIROU MAIS FORTE em 24/09/2026, e o princípio é o mesmo.

        Até aqui: "enviar em branco não grava declaração" — o `or ""` impedia
        o app de inventar um nível. O princípio continua de pé (o app NÃO
        declara nível por ninguém); o que mudou é que enviar em branco com
        `musculacao=sim` deixou de ser aceito em silêncio e passou a ser
        RECUSADO, com o erro no campo. O outro lado da régua antiga era o
        Perfil dizendo "não informada", que é admitir que a ficha foi montada
        com um palpite.

        Quem já tinha conta em branco continua intocado: a recusa é do
        FORMULÁRIO, e nada reescreve o perfil de quem não abriu a tela.
        """
        self.user.profile.experiencia = ""
        self.user.profile.save(update_fields=["experiencia"])
        aberto = TrainingForm(user=self.user)
        self.assertFalse(aberto.get_initial_for_field(aberto.fields["experiencia"], "experiencia"))
        enviado = TrainingForm(_dados_iniciais(aberto), user=self.user)
        self.assertFalse(enviado.is_valid())
        self.assertIn("experiencia", enviado.errors)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.experiencia, "")


class NaoQueroPriorizarSobreviveAReedicaoTests(TestCase):
    """B3 — "Não quero priorizar agora" é gravado como `prioridade = ""`, e o
    formulário reabria com NENHUM rádio marcado. Salvar de novo (para trocar
    o cardápio, por exemplo) com UMA área marcada promovia a área a principal
    em silêncio; com duas, recusava com "Escolha qual vem primeiro" — cobrando
    de novo uma resposta já dada."""

    def _perfil(self, **campos):
        user = create_complete_user(**campos)
        return Profile.objects.get(user=user)

    def test_com_uma_area_e_sem_prioridade_o_neutro_abre_marcado(self):
        perfil = self._perfil(interesse_corrida=True, prioridade="")
        form = InteressesForm(instance=perfil)
        self.assertEqual(
            form.get_initial_for_field(form.fields["prioridade"], "prioridade"),
            InteressesForm.SEM_PRIORIDADE,
        )

    def test_reabrir_e_salvar_com_uma_area_nao_promove_a_area(self):
        perfil = self._perfil(interesse_corrida=True, prioridade="")
        aberto = InteressesForm(instance=perfil)
        enviado = InteressesForm(_dados_iniciais(aberto), instance=perfil)
        self.assertTrue(enviado.is_valid(), enviado.errors)
        enviado.save()
        perfil.refresh_from_db()
        self.assertEqual(perfil.prioridade, "")
        self.assertEqual([str(p) for p in perfil.interesses], [str(Pilar.CORRIDA)])

    def test_reabrir_e_salvar_com_duas_areas_nao_cobra_a_escolha_de_novo(self):
        perfil = self._perfil(interesse_corrida=True, interesse_hidratacao=True, prioridade="")
        aberto = InteressesForm(instance=perfil)
        enviado = InteressesForm(_dados_iniciais(aberto), instance=perfil)
        self.assertTrue(enviado.is_valid(), enviado.errors)
        enviado.save()
        perfil.refresh_from_db()
        self.assertEqual(perfil.prioridade, "")

    def test_quem_tem_prioridade_continua_abrindo_com_ela(self):
        perfil = self._perfil(interesse_treino=True, prioridade=Pilar.TREINO)
        form = InteressesForm(instance=perfil)
        self.assertEqual(
            form.get_initial_for_field(form.fields["prioridade"], "prioridade"),
            Pilar.TREINO,
        )

    def test_a_primeira_passagem_continua_sem_radio_marcado(self):
        """Onboarding no meio, nada marcado ainda: não há resposta a preservar,
        e pré-marcar "não quero priorizar" seria declarar pela pessoa."""
        perfil = self._perfil(onboarding_step=3, prioridade="")
        form = InteressesForm(instance=perfil)
        self.assertFalse(form.get_initial_for_field(form.fields["prioridade"], "prioridade"))


class EditarAlturaNaoFabricaPesagemTests(TestCase):
    """B4 — `BodyDataForm.save()` fazia `WeightEntry.update_or_create(date=hoje)`
    sempre, com o peso que o campo trazia pré-preenchido: quem abria "Dados
    corporais → Editar" para corrigir a altura gravava uma pesagem datada de
    hoje com o número de dez dias atrás, e `convidar_a_pesar` parava de
    convidar porque "hoje já tem pesagem"."""

    def setUp(self):
        self.user = create_complete_user()
        antiga = WeightEntry.objects.get(user=self.user)
        WeightEntry.objects.filter(pk=antiga.pk).update(
            date=timezone.localdate() - timedelta(days=10)
        )
        self.perfil = Profile.objects.get(user=self.user)

    def _dados(self, **troca):
        aberto = BodyDataForm(instance=self.perfil)
        dados = _dados_iniciais(aberto)
        dados.update(troca)
        return dados

    def test_corrigir_so_a_altura_nao_cria_pesagem_de_hoje(self):
        form = BodyDataForm(self._dados(height_cm="181"), instance=self.perfil)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)
        self.assertFalse(
            WeightEntry.objects.filter(user=self.user, date=timezone.localdate()).exists()
        )
        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.height_cm, 181)

    def test_mudar_o_peso_grava_a_pesagem_de_hoje(self):
        form = BodyDataForm(self._dados(weight_kg="80,0"), instance=self.perfil)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        hoje = WeightEntry.objects.get(user=self.user, date=timezone.localdate())
        self.assertEqual(hoje.weight_kg, Decimal("80.0"))

    def test_a_primeira_passagem_grava_o_primeiro_peso(self):
        WeightEntry.objects.filter(user=self.user).delete()
        form = BodyDataForm(self._dados(weight_kg="82,4"), instance=self.perfil)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(
            WeightEntry.objects.filter(user=self.user, date=timezone.localdate()).exists()
        )
