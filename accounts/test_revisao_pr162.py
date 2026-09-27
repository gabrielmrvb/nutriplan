# -*- coding: utf-8 -*-
"""O que a revisão multi-agente do PR #162 achou, e a régua que impede a volta.

Três revisores independentes, somente leitura, sobre o diff da missão "quem
entra não desiste" contra `origin/main` (27/09/2026). Cada classe aqui é UM
achado consertado, com o cenário de falha que o revisor escreveu. O que era
decisão de produto ficou fora e está no relatório da missão.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Corrida, Musculacao, Profile, User
from accounts.test_tres_etapas import ETAPA1, ETAPA2, etapa
from plans.tests import create_complete_user


def sem_scripts(html):
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S)


class APerguntaDaCorridaTemOsProprioCartoesTests(TestCase):
    """BUG (revisor de UI): a pergunta "Você corre, pedala ou nada?" desenhava
    os DOIS cartões da musculação — "Sim, faço musculação · a ficha é sua" —,
    porque `Corrida` valia "sim"/"nao", as chaves que `Musculacao` já ocupa em
    `escolhas.DETALHES`, e o mapa é por valor cru, sem o nome do campo. Na
    etapa em que duas das três personas desistiam."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="cartoes-corrida@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)

    def test_os_valores_nao_colidem_com_os_da_musculacao(self):
        self.assertFalse(set(Corrida.values) & set(Musculacao.values))

    def test_a_etapa_2_nao_repete_os_cartoes_da_musculacao(self):
        html = sem_scripts(self.client.get(etapa(2)).content.decode())
        # "Sim, faço musculação" é o título do cartão da PRIMEIRA pergunta; se
        # aparecer duas vezes, a segunda é a pergunta da corrida vestindo a
        # roupa da outra.
        self.assertEqual(html.count("Sim, faço musculação"), 1)
        bloco = html.split('name="corrida"', 1)[1][:3000]
        self.assertIn("Sim, corro", bloco)
        # CONTROLE POSITIVO: o cartão da musculação continua lá.
        self.assertIn('name="musculacao" value="sim"', html)

    def test_responder_que_corre_revela_a_frequencia_sem_javascript(self):
        """O `hidden` do bloco da frequência comparava com "sim": com os valores
        novos, sem esta régua, o bloco ficaria escondido para sempre quando a
        tela volta com erro."""
        resposta = self.client.post(etapa(2), {**ETAPA2, "corrida": Corrida.SIM})
        html = sem_scripts(resposta.content.decode())
        self.assertEqual(
            resposta.status_code, 200, "o envio sem a frequência tem de voltar com erro"
        )
        bloco = html.split("data-so-corrida", 1)[1].split(">", 1)[0]
        self.assertNotIn("hidden", bloco)

    def test_o_javascript_compara_com_o_valor_novo(self):
        from config.estaticos import sem_comentarios

        js = sem_comentarios(
            (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        )
        trecho = js.split('input[name="corrida"]', 1)[1][:400]
        self.assertIn('"%s"' % Corrida.SIM, trecho)


class OResumoDaEtapa3MostraACorridaTests(TestCase):
    """OBSERVAÇÃO (revisor de UI): a corrida move a meta de calorias, e o resumo
    da etapa 3 — a conferência de tudo o que entra na conta, na tela anterior
    ao número — não a mostrava. Quem só corria lia "Atividade: Pouco ativo" e
    mais nada."""

    def test_quem_corre_ve_a_frequencia_no_resumo(self):
        from accounts.views import resumo_das_escolhas

        user = create_complete_user(email="resumo-corre@exemplo.com")
        Profile.objects.filter(user=user).update(
            corrida=Corrida.SIM, corrida_dias=3, corrida_minutos=40,
            musculacao=Musculacao.NAO,
        )
        user.refresh_from_db()
        itens = dict(resumo_das_escolhas(user, user.profile))
        self.assertEqual(itens.get("Corrida"), "3× por semana · 40 min")

    def test_quem_nao_corre_nao_ganha_linha_de_ruido(self):
        from accounts.views import resumo_das_escolhas

        user = create_complete_user(email="resumo-nao-corre@exemplo.com")
        Profile.objects.filter(user=user).update(corrida=Corrida.NAO)
        user.refresh_from_db()
        self.assertNotIn("Corrida", dict(resumo_das_escolhas(user, user.profile)))


class OEnvioParcialNaoApagaAFrequenciaTests(TestCase):
    """OBSERVAÇÃO (revisor de Django): `corrida` era preservada no envio sem o
    campo (`or perfil.corrida`), e `corrida_dias` era zerada (`or 0`). Um envio
    sem os dois deixava "corro" com "0× por semana" no Perfil."""

    def test_um_envio_sem_a_corrida_mantem_resposta_e_frequencia(self):
        from accounts.forms import TrainingForm

        user = create_complete_user(
            email="parcial@exemplo.com", musculacao="sim", equipamento="completa"
        )
        Profile.objects.filter(user=user).update(
            corrida=Corrida.SIM, corrida_dias=4, corrida_minutos=30
        )
        user.refresh_from_db()
        dados = {
            "weekdays": ["0", "2", "4"], "musculacao": "sim", "experiencia": "intermediario",
            "equipamento": "completa", "wake_time": "07:00", "sleep_time": "23:00",
        }
        form = TrainingForm(dados, user=user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        perfil = Profile.objects.get(user=user)
        self.assertEqual(
            (perfil.corrida, perfil.corrida_dias, perfil.corrida_minutos), (Corrida.SIM, 4, 30)
        )

    def test_com_a_resposta_nao_a_frequencia_zera(self):
        """CONTROLE POSITIVO: quando a resposta VEM, vale o que o `clean` decide."""
        from accounts.forms import TrainingForm

        user = create_complete_user(
            email="parcial-nao@exemplo.com", musculacao="sim", equipamento="completa"
        )
        Profile.objects.filter(user=user).update(corrida=Corrida.SIM, corrida_dias=4)
        user.refresh_from_db()
        dados = {
            "weekdays": ["0", "2", "4"], "musculacao": "sim", "experiencia": "intermediario",
            "equipamento": "completa", "wake_time": "07:00", "sleep_time": "23:00",
            "corrida": Corrida.NAO,
        }
        form = TrainingForm(dados, user=user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        perfil = Profile.objects.get(user=user)
        self.assertEqual((perfil.corrida, perfil.corrida_dias), (Corrida.NAO, 0))


class OFatorDoPerfilContaACorridaTests(TestCase):
    """OBSERVAÇÃO (revisor de Django): `Profile.activity_factor` não recebeu a
    corrida e divergia do fator que o plano grava — dois números para a mesma
    pergunta, esperando a próxima tela que lesse o do perfil."""

    def test_o_fator_do_perfil_e_o_do_calculo(self):
        from plans.calculations import activity_factor

        user = create_complete_user(email="fator-perfil@exemplo.com")
        Profile.objects.filter(user=user).update(corrida=Corrida.SIM, corrida_dias=3)
        user.refresh_from_db()
        perfil = user.profile
        esperado = activity_factor(perfil.activity_level, perfil.training_days_per_week, 3)
        self.assertEqual(perfil.activity_factor, esperado)
        # CONTROLE POSITIVO: sem a corrida, o número é outro — senão o teste
        # passaria com a corrida ignorada.
        self.assertNotEqual(
            esperado, activity_factor(perfil.activity_level, perfil.training_days_per_week, 0)
        )


class OConviteACorrerRespeitaARespostaTests(TestCase):
    """OBSERVAÇÃO (revisor de UI) + UX REAL da resolução do merge (revisor de
    Django): "Corri hoje" era incondicional — aparecia para quem respondeu que
    não corre — e, depois do merge com `main`, virou item solto da grade de
    duas colunas, empurrando o `<aside>` para baixo no desktop."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _html(self, corrida):
        from workouts import services as treino

        user = create_complete_user(email="convite-%s@exemplo.com" % (corrida or "branco"))
        Profile.objects.filter(user=user).update(corrida=corrida)
        user.refresh_from_db()
        treino.create_routine(user)
        self.client.force_login(user)
        return self.client.get(reverse("workouts:routine")).content.decode()

    def test_quem_disse_que_nao_corre_nao_e_convidado(self):
        self.assertNotIn("Corri hoje", self._html(Corrida.NAO))

    def test_quem_nao_respondeu_continua_convidado(self):
        self.assertIn("Corri hoje", self._html(""))

    def test_a_linha_mora_no_mesmo_item_de_grade_da_semana(self):
        """A linha e a lista de sessões são UM filho de `.stack--duas-colunas`:
        o `<p>` e o `<ul>` dentro do mesmo `<div>`, e o `<div>` fechado antes
        do `<aside>`."""
        html = self._html("")
        lista = html.index('class="programa__sessoes')
        linha = html.index("Corri hoje", lista)
        aside = html.index("<aside", linha)
        # Entre a lista e a linha não pode haver fechamento de `</div>` — se
        # houvesse, a linha teria saído do envoltório.
        self.assertNotIn("</div>", html[lista:linha])
        abre = html.rindex("<div", 0, lista)
        self.assertIn('class="stack"', html[abre:lista])
        self.assertIn("</div>", html[linha:aside])
