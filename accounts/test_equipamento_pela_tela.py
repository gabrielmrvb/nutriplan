"""O equipamento escolhido NA TELA chega ao banco e volta para a tela.

Item 1 da missão de UX (22/09/2026): "o equipamento do cadastro não é
salvo — sempre reverte para Academia completa". Não reproduzido no código
atual, nem pelo navegador (`scratchpad/ux/r1_equipamento.py`: "só o peso
do corpo" chega ao banco na etapa 2, aparece na etapa 3, no Perfil, e a
edição para "casa com halteres" remonta a ficha). O que existia era o
achado #1 das personas — com menos de três dias de treino o CONTINUAR
sumia, e quem apertava Enter num campo podia sair da etapa sem ver o que
foi enviado. Este teste prende o caminho pela TELA, e não só pela view:
envia o formulário RENDERIZADO (nome de campo trocado no template derruba
o teste), com o token da própria página, e confere a volta.
"""
import re

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Equipamento, Profile, User
from accounts.test_tres_etapas import ETAPA1, etapa


def campos_do_formulario(html):
    """Os pares (name, value) que um navegador enviaria do formulário
    principal, marcando o que o teste quer marcar depois."""
    form = html.split("<main", 1)[1]
    form = form[form.index("<form"):]
    form = form[: form.index("</form>")]
    dados = {}
    for tag in re.findall(r"<input[^>]*>", form):
        nome = re.search(r'name="([^"]+)"', tag)
        if not nome:
            continue
        valor = re.search(r'value="([^"]*)"', tag)
        tipo = (re.search(r'type="([^"]+)"', tag) or [None, "text"])[1]
        if tipo in ("radio", "checkbox"):
            if "checked" in tag:
                dados.setdefault(nome.group(1), []).append(valor.group(1) if valor else "on")
        elif tipo != "submit":
            dados[nome.group(1)] = valor.group(1) if valor else ""
    return dados


class EquipamentoPelaTelaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(email="tela@exemplo.com", password="senha-bem-forte-123")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        html = self.client.get(etapa(1)).content.decode()
        dados = campos_do_formulario(html)
        dados.update({"sex": "F", "birth_date": "1997-04-12", "height_cm": "165", "weight_kg": "78", "termos": "on", "saude": "on", "transferencia": "on"})
        self.client.post(etapa(1), dados)

    def test_so_o_peso_do_corpo_com_dois_dias_chega_ao_banco_e_volta_a_tela(self):
        html = self.client.get(etapa(2)).content.decode()
        self.assertIn('name="equipamento" value="peso_corporal"', html)
        dados = campos_do_formulario(html)
        dados.update({"goal": "cut", "activity_level": "light", "musculacao": "sim", "experiencia": "iniciante",
                      "equipamento": "peso_corporal", "weekdays": ["0", "2"]})
        resposta = self.client.post(etapa(2), dados)
        self.assertRedirects(resposta, etapa(3), fetch_redirect_response=False)
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.equipamento, Equipamento.PESO_CORPORAL)
        # a etapa 3 resume, o Perfil mostra, e a etapa 2 reabre marcada
        self.assertIn("Só o peso do corpo", self.client.get(etapa(3)).content.decode())
        reaberta = self.client.get(etapa(2)).content.decode()
        self.assertRegex(reaberta, r'name="equipamento" value="peso_corporal"[^>]*checked')
        self.assertNotRegex(reaberta, r'name="equipamento" value="completa"[^>]*checked')

    def test_a_edicao_pelo_perfil_troca_e_nao_reverte(self):
        html = self.client.get(etapa(2)).content.decode()
        dados = campos_do_formulario(html)
        dados.update({"goal": "cut", "activity_level": "light", "musculacao": "sim", "experiencia": "iniciante",
                      "equipamento": "peso_corporal", "weekdays": ["0", "2", "4"], "split_preference": "three"})
        self.client.post(etapa(2), dados)
        self.client.post(etapa(3), {"meal_style": "quick", "interesses": ["treino"], "prioridade": "treino"}, follow=True)
        editar = etapa(2) + "?origem=perfil"
        html = self.client.get(editar).content.decode()
        dados = campos_do_formulario(html)
        self.assertEqual(dados.get("equipamento"), ["peso_corporal"])
        dados["equipamento"] = "casa_halteres"
        self.client.post(editar, dados)
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.equipamento, Equipamento.CASA_HALTERES)
        perfil_html = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn("Em casa, com halteres", perfil_html)
        self.assertNotIn("Academia completa", perfil_html.split("<h2>Treinos</h2>", 1)[1].split("</section>", 1)[0])
