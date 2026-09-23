# -*- coding: utf-8 -*-
"""A FOLHA DE TROCA E OS ACABAMENTOS DA EXECUÇÃO (22/09/2026).

O resto da missão do Treino, depois da ficha e do fecho:

- **"trocar" abre uma folha sobre a ficha** em vez de trocar de tela. Ele é
  um LINK para a leitura do exercício (funciona sem JavaScript, no
  histórico, ao compartilhar) e `pwa.js` o promove a `<dialog>` — a exceção
  que a doutrina de sobreposição prevê, porque aqui o foco precisa ficar
  preso e há formulários dentro;
- **a última carga aparece ACIMA do campo**, que é onde se escolhe a
  anilha (o fato existia, mas depois do formulário);
- **setas ‹ › entre exercícios**, links de verdade, sem voltar à ficha;
- **foto que não carrega não deixa buraco**: as imagens vêm de uma CDN, e
  na academia elas falham — o `<img>` quebrado sai da linha;
- **a alternativa sem foto não reserva um retângulo cinza** (Parte 3).
"""
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.tests import create_user, escolher_opcao_de_hoje

RAIZ = Path(__file__).resolve().parents[1]
PWA = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
LEITURA = (RAIZ / "templates" / "workouts" / "exercicio.html").read_text(encoding="utf-8")


class AFolhaDeTrocaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(
            email="folha@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(self.user)
        escolher_opcao_de_hoje(self.user)
        self.client.force_login(self.user)
        self.sessao = services.sessao_do_dia(
            services.get_active_routine(self.user), timezone.localdate()
        )

    def _ficha(self):
        return self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode()

    def test_a_ficha_traz_a_folha_vazia_e_o_link_que_a_abre(self):
        html = self._ficha()
        self.assertIn("data-folha-troca", html)
        self.assertIn("data-trocar=", html)
        self.assertIn("folha-troca__corpo", html)

    def test_sem_javascript_trocar_continua_sendo_um_link_para_a_leitura(self):
        """A folha é melhoria progressiva: sem JS, a porta é a de sempre —
        a leitura do exercício, ancorada nas alternativas."""
        import re

        html = self._ficha()
        link = re.search(r'<a class="ficha-item__trocar"\s+href="([^"]+)"', html)
        self.assertIsNotNone(link, "nenhum exercício desta ficha oferece troca")
        self.assertIn("/treino/exercicio/", link.group(1))
        self.assertTrue(link.group(1).endswith("#outras-formas"))

    def test_o_javascript_recorta_a_secao_e_usa_dialog(self):
        bloco = PWA[PWA.index("TROCAR NA FICHA"):]
        self.assertIn('querySelector("#outras-formas")', bloco)
        self.assertIn("showModal()", bloco)
        # Falhou a rede ou o HTML: cai na navegação de sempre.
        self.assertIn("location.href = link.href", bloco)

    def test_a_folha_fecha_pelo_fundo_e_pelo_botao(self):
        bloco = PWA[PWA.index("TROCAR NA FICHA"):]
        self.assertIn("evento.target === folha", bloco)
        self.assertIn("data-folha-fechar", bloco)

    def test_a_troca_feita_na_folha_recarrega_a_ficha(self):
        """O card precisa mostrar o exercício novo — e é a ficha que a
        pessoa está olhando, não a leitura para onde a view redireciona."""
        bloco = PWA[PWA.index("TROCAR NA FICHA"):]
        self.assertIn("location.reload()", bloco)


class OsAcabamentosDaExecucaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(
            email="acabamento@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(self.user)
        escolher_opcao_de_hoje(self.user)
        self.client.force_login(self.user)
        self.itens = services.estado_do_treino(self.user).itens

    def test_a_ultima_carga_aparece_acima_do_campo(self):
        from datetime import timedelta
        from decimal import Decimal

        item = self.itens[0]
        services.record_load(
            self.user, item.exercise, Decimal("42.5"), set_number=1, reps=6,
            day=timezone.localdate() - timedelta(days=7),
        )
        html = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        ).content.decode()
        self.assertIn("registro__ultima", html)
        # ACIMA: a marca da última vez vem antes do campo no documento.
        self.assertLess(html.index("registro__ultima"), html.index('name="weight_kg"'))
        self.assertIn("42,5", html)

    def test_as_setas_levam_ao_vizinho_na_ordem_da_ficha(self):
        segundo = self.itens[1]
        html = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), segundo.exercise_id)
        ).content.decode()
        self.assertIn("agora__seta", html)
        self.assertIn("?exercicio=%d" % self.itens[0].exercise_id, html)
        self.assertIn("?exercicio=%d" % self.itens[2].exercise_id, html)

    def test_no_primeiro_exercicio_nao_ha_seta_para_tras(self):
        estado = services.estado_do_treino(self.user, escolhido=self.itens[0].exercise_id)
        self.assertIsNone(estado.item_anterior)
        self.assertIsNotNone(estado.item_seguinte)

    def test_foto_quebrada_sai_da_linha_em_vez_de_deixar_buraco(self):
        bloco = PWA[PWA.index("FOTO DE EXERCÍCIO QUE NÃO CARREGA"):]
        self.assertIn('document.addEventListener("error"', bloco)
        self.assertIn("true", bloco, "o evento `error` não borbulha: o ouvinte é de captura")
        self.assertIn("alvo.remove()", bloco)
        for classe in ("ficha-item__foto", "demo__foto", "forma__foto"):
            self.assertIn(classe, bloco)

    def test_a_alternativa_sem_foto_nao_reserva_retangulo_cinza(self):
        """Parte 3: "Barra fixa negativa" e "Barra fixa pronada" apareciam
        com um buraco de 96px ao lado do nome."""
        self.assertNotIn("forma__foto--vazia", LEITURA)
        self.assertNotIn("forma__foto--vazia", CSS)
