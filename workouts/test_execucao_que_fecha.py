# -*- coding: utf-8 -*-
"""A EXECUÇÃO DO TREINO GANHA UM FECHO, UM CRONÔMETRO E FOCO (22/09/2026).

Quatro defeitos observados pelo dono, logado, no meio de um treino:

1. **não havia como terminar.** "Concluído" só existia com toda série
   prescrita registrada; quem parava no sexto de nove exercícios ficava em
   "Exercício 6/9" para sempre e nunca via resumo nenhum. Agora há
   "Encerrar treino" — com menos da metade das séries ele PERGUNTA antes —,
   o placar abre, diz "Treino parcial · N de M séries", nomeia o que ficou
   sem registro, e "Retomar treino" desfaz sem apagar nada;
2. **o descanso mudava de formato sozinho** ("79s" → "1:13") e era uma
   faixa fina que rolava para fora da tela. Agora é `m:ss` do primeiro ao
   último segundo, gruda no topo, e tem "+30 s" e som opcional;
3. **a barra de abas e o rodapé legal ficavam na tela** durante o treino —
   quatro portas de saída numa tarefa que se faz de pé;
4. **o campo de carga empurrava o botão.** `.teclado-aberto .container`
   devolvia o espaço reservado para a barra de abas ao focar um campo de
   texto; na execução, que não tem barra, a página encolhia ~100 px
   (MEDIDO no navegador: `scrollHeight` 1026 → 923) e o "Concluir série"
   escapava do dedo. Sem barra não há espaço a devolver, e a regra passou a
   exigir `.tem-tabbar`.
"""
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import EscolhaDeTreino, ExerciseLog
from workouts.tests import create_user, escolher_opcao_de_hoje

RAIZ = Path(__file__).resolve().parents[1]
PWA = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")


class _ComTreinoHoje(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(
            email=self.__class__.__name__.lower() + "@exemplo.com",
            weekdays=(timezone.localdate().weekday(),),
        )
        services.sync_active_routine(self.user)
        escolher_opcao_de_hoje(self.user)
        self.client.force_login(self.user)
        self.estado = services.estado_do_treino(self.user)

    def _registrar(self, quantas):
        """`quantas` séries, do primeiro exercício em diante."""
        feitas = 0
        for item in self.estado.itens:
            for n in range(1, item.sets + 1):
                if feitas >= quantas:
                    return
                services.record_load(
                    self.user, item.exercise, Decimal("40"), set_number=n, reps=8
                )
                feitas += 1


class EncerrarTreinoTests(_ComTreinoHoje):
    def test_a_execucao_oferece_encerrar_o_treino(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn(reverse("workouts:encerrar"), html)
        self.assertIn("Encerrar treino", html)

    def test_encerrar_com_o_treino_quase_inteiro_fecha_na_hora(self):
        self._registrar(self.estado.total_series)
        resposta = self.client.post(reverse("workouts:encerrar"), follow=True)
        self.assertIsNotNone(
            EscolhaDeTreino.objects.get(user=self.user, date=timezone.localdate()).encerrado_em
        )
        self.assertContains(resposta, "Treino concluído")

    def test_encerrar_pela_metade_pergunta_antes_e_nao_fecha(self):
        """Fechar sem querer no terceiro exercício esconderia a ficha do
        resto do dia — e a confirmação é uma TELA, não um `confirm()`."""
        self._registrar(1)
        resposta = self.client.post(reverse("workouts:encerrar"), follow=True)
        self.assertIsNone(
            EscolhaDeTreino.objects.get(user=self.user, date=timezone.localdate()).encerrado_em
        )
        self.assertContains(resposta, "Registrar como treino parcial?")

    def test_confirmado_encerra_e_o_placar_diz_que_foi_parcial(self):
        self._registrar(1)
        resposta = self.client.post(
            reverse("workouts:encerrar"), {"confirmado": "1"}, follow=True
        )
        self.assertContains(resposta, "Treino parcial")
        # Nem no rótulo, nem no `<title>`: chamar de concluído um treino
        # pela metade é o app afirmando o que não aconteceu.
        self.assertNotContains(resposta, "Treino concluído")
        self.assertContains(resposta, "Treino encerrado · NutriPlan")

    def test_o_placar_parcial_nomeia_o_que_ficou_sem_registro(self):
        self._registrar(1)
        self.client.post(reverse("workouts:encerrar"), {"confirmado": "1"})
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn("Sem registro hoje:", html)
        ultimo = self.estado.itens[-1].exercise.name
        self.assertIn(ultimo, html)

    def test_encerrar_nao_apaga_serie_nenhuma(self):
        self._registrar(2)
        antes = ExerciseLog.objects.filter(user=self.user).count()
        self.client.post(reverse("workouts:encerrar"), {"confirmado": "1"})
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), antes)

    def test_retomar_devolve_o_treino_de_onde_parou(self):
        self._registrar(1)
        self.client.post(reverse("workouts:encerrar"), {"confirmado": "1"})
        resposta = self.client.post(reverse("workouts:retomar"), follow=True)
        self.assertIsNone(
            EscolhaDeTreino.objects.get(user=self.user, date=timezone.localdate()).encerrado_em
        )
        self.assertContains(resposta, "Concluir série")

    def test_o_placar_de_quem_fechou_a_ficha_inteira_nao_oferece_retomar(self):
        """Não há o que retomar num treino que acabou — e o botão ali
        convidaria a desfazer o que foi feito."""
        self._registrar(self.estado.total_series)
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn("Treino concluído", html)
        self.assertNotIn(reverse("workouts:retomar"), html)

    def test_o_get_de_encerrar_volta_para_a_execucao(self):
        """Nenhuma ação de tela responde 405 em branco (config/acoes.py)."""
        resposta = self.client.get(reverse("workouts:encerrar"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("workouts:now"), resposta["Location"])

    def test_pedido_de_encerramento_ilegivel_e_404(self):
        resposta = self.client.get(reverse("workouts:now") + "?encerrar=talvez")
        self.assertEqual(resposta.status_code, 404)


class OCronometroDeDescansoTests(_ComTreinoHoje):
    def _com_descanso(self):
        item = self.estado.itens[0]
        services.record_load(self.user, item.exercise, Decimal("50"), set_number=1, reps=8)
        return self.client.get(reverse("workouts:now")).content.decode()

    def test_o_primeiro_quadro_vem_do_servidor_em_m_ss(self):
        """A tela dizia "79s" e virava "1:13" no meio da contagem."""
        html = self._com_descanso()
        estado = services.estado_do_treino(self.user)
        self.assertRegex(estado.descanso_relogio, r"^\d+:\d\d$")
        self.assertIn(estado.descanso_relogio, html)
        self.assertNotIn("%ds" % estado.descanso_restante, html)

    def test_o_relogio_gruda_no_topo(self):
        """Ele rolava para fora da tela justo quando a pessoa esperava."""
        bloco = CSS[CSS.index(".descanso {"):]
        bloco = bloco[: bloco.index("}")]
        self.assertIn("position: sticky", bloco)
        self.assertIn("var(--appbar-h)", bloco)
        self.assertIn("z-index: var(--camada-flutuante)", bloco)

    def test_a_tela_oferece_mais_30_segundos_pular_e_som(self):
        html = self._com_descanso()
        for marcador in ("data-descanso-mais", "data-descanso-pular", "data-descanso-som"):
            self.assertIn(marcador, html)
        self.assertIn("+30 s", html)

    def test_o_som_nasce_desligado_e_e_lembrado_no_aparelho(self):
        """Quem treina ouvindo música não quer um bipe sem pedir."""
        html = self._com_descanso()
        self.assertIn('aria-pressed="false"', html)
        self.assertIn('nutriplan:descanso-som', PWA)
        self.assertIn('guardado("localStorage", CHAVE_SOM) === "1"', PWA)

    def test_o_cronometro_segura_a_tela_acesa_enquanto_corre(self):
        self.assertIn("navigator.wakeLock", PWA)
        self.assertIn('wakeLock.request("screen")', PWA)
        self.assertIn("bloqueio.release()", PWA, "o bloqueio esquecido drena bateria depois do treino")

    def test_a_vibracao_continua_e_o_bipe_e_opcional(self):
        fim = PWA[PWA.index("Descanso terminado, pode ir."):]
        fim = fim[: fim.index("return;")]
        self.assertIn("navigator.vibrate", fim)
        self.assertIn("bipar()", fim)


class ModoFocoDeVerdadeTests(_ComTreinoHoje):
    def test_a_barra_de_abas_nao_aparece_durante_o_treino(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertNotIn('class="tabbar"', html)
        self.assertNotIn("tem-tabbar", html)

    def test_o_rodape_legal_nao_aparece_durante_o_treino(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertNotIn("links-legais", html)

    def test_a_ficha_continua_com_barra_e_rodape(self):
        """Controle positivo: o foco é DESTA tela, não do app inteiro."""
        sessao = services.sessao_do_dia(
            services.get_active_routine(self.user), timezone.localdate()
        )
        html = self.client.get(reverse("workouts:ficha", args=[sessao.pk])).content.decode()
        self.assertIn('class="tabbar"', html)

    def test_as_duas_saidas_da_execucao_continuam_na_tela(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn("← Ficha", html)
        self.assertIn("Encerrar treino", html)

    def test_o_teclado_so_recolhe_espaco_onde_a_barra_existe(self):
        """O salto de layout do campo de carga: a página encolhia ~100 px ao
        focar, e o "Concluir série" escapava do dedo."""
        self.assertIn(".teclado-aberto.tem-tabbar .container", CSS)
        self.assertNotIn(".teclado-aberto .container {", CSS)
