# -*- coding: utf-8 -*-
"""Quem diz que faz musculação responde nível e equipamento (24/09/2026).

Os dois campos eram `required=False` com a razão escrita: "sem resposta o
motor usa 20, que é o que o app já praticava — a ficha não muda, e a tela
não inventa a frase". A régua está certa e continua valendo: o app NÃO
declara nível por ninguém. O que a rodada 2 mediu é o outro lado dela — a
pessoa saía do cadastro sem responder e o Perfil dizia **"não informada"**,
que é o app admitindo que a ficha dela foi montada com um palpite.

A saída não é inventar a resposta: é PERGUNTAR. As duas perguntas só
existem para quem disse que faz musculação (`musculacao == "sim"`), e é
exatamente aí que elas passam a ser obrigatórias. Quem respondeu "não faço"
não vê o bloco e não é cobrado por ele — o `clean` já zerava os dois.

O erro nasce junto do campo (`aria-invalid` + `field__errors`, a régua do
lote 1 de 22/09) e o `pwa.js` rola até ele. E o Perfil de quem já tem conta
sem resposta deixou de dizer "não informada": ele diz o que o motor USA e
que foi padrão — um estado de verdade, não um buraco.
"""
import re

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Equipamento, Experiencia, Musculacao, Profile, User
from accounts.test_equipamento_pela_tela import campos_do_formulario
from accounts.test_tres_etapas import etapa


class NivelEEquipamentoSaoObrigatoriosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="obrigatorio@exemplo.com", password="senha-bem-forte-123"
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        html = self.client.get(etapa(1)).content.decode()
        dados = campos_do_formulario(html)
        dados.update({
            "sex": "M", "birth_date": "1995-04-12", "height_cm": "178",
            "weight_kg": "82", "termos": "on", "saude": "on", "transferencia": "on",
        })
        self.client.post(etapa(1), dados)

    def _postar(self, **extra):
        html = self.client.get(etapa(2)).content.decode()
        dados = campos_do_formulario(html)
        dados.update({
            "goal": "cut", "activity_level": "light", "musculacao": "sim",
            "weekdays": ["0", "2", "4"], "split_preference": "two",
        })
        dados.pop("experiencia", None)
        dados.pop("equipamento", None)
        dados.update(extra)
        return self.client.post(etapa(2), dados)

    def test_sem_experiencia_a_etapa_recusa(self):
        resposta = self._postar(equipamento=Equipamento.COMPLETA)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("experiencia", resposta.context["forms"]["rotina"].errors)

    def test_sem_equipamento_a_etapa_recusa(self):
        resposta = self._postar(experiencia=Experiencia.INICIANTE)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("equipamento", resposta.context["forms"]["rotina"].errors)

    def test_o_erro_nasce_junto_do_campo_e_a_tela_vai_ate_ele(self):
        """A régua do lote 1: `aria-invalid` no campo é o que `pwa.js` procura
        para rolar e focar. Um erro só no topo da página deixa a pessoa
        procurando qual dos dez campos recusou."""
        html = self._postar().content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertIn('aria-invalid="true"', corpo)
        self.assertIn("field__errors", corpo)

    def test_com_as_duas_respostas_a_etapa_passa(self):
        resposta = self._postar(
            experiencia=Experiencia.INICIANTE, equipamento=Equipamento.CASA_HALTERES
        )
        self.assertEqual(resposta.status_code, 302)
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.experiencia, Experiencia.INICIANTE)
        self.assertEqual(perfil.equipamento, Equipamento.CASA_HALTERES)

    def test_quem_nao_faz_musculacao_nao_e_cobrado(self):
        """A pergunta-porta decide: sem musculação o bloco não existe na tela,
        e exigir o que não foi perguntado seria um beco sem saída."""
        html = self.client.get(etapa(2)).content.decode()
        dados = campos_do_formulario(html)
        dados.update({"goal": "cut", "activity_level": "light", "musculacao": "nao"})
        dados.pop("experiencia", None)
        dados.pop("equipamento", None)
        dados.pop("weekdays", None)
        resposta = self.client.post(etapa(2), dados)
        self.assertEqual(resposta.status_code, 302)
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.musculacao, Musculacao.NAO)
        self.assertEqual(perfil.experiencia, "")


class OPerfilNuncaDizNaoInformadaTests(TestCase):
    """Conta ANTERIOR à obrigatoriedade: a resposta não existe, e o Perfil
    diz o que o motor usa em vez de admitir um buraco."""

    def setUp(self):
        from plans.tests import create_complete_user

        self.user = create_complete_user(email="legado@exemplo.com")
        perfil = self.user.profile
        perfil.musculacao = Musculacao.SIM
        perfil.experiencia = ""
        perfil.save(update_fields=["musculacao", "experiencia"])
        self.client.force_login(self.user)

    def test_o_perfil_nao_escreve_nao_informada(self):
        html = self.client.get(reverse("accounts:profile")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        texto = " ".join(re.sub(r"<[^>]+>", " ", corpo).split())
        self.assertNotIn("não informada", texto)

    def test_o_perfil_diz_o_que_o_motor_usa_e_que_e_padrao(self):
        html = self.client.get(reverse("accounts:profile")).content.decode()
        texto = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        self.assertIn("Intermediário", texto)
        self.assertIn("padrão", texto)
