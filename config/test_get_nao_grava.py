"""Abrir uma tela não grava nada.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, R6).
Para achar escrita escondida atrás de leitura, a varredura comparou os
contadores do Postgres antes e depois de uma passada só de GET. A única
tabela que mudou fora do analytics (que chega por POST) foi
`avisos_preferencia`: `GET /avisos/` chamava `Preferencia.de`, um
`get_or_create`, e criava a linha na primeira visita. O efeito é inofensivo,
porque a linha nasce com os padrões, mas "ver" não pode ser "gravar". Uma
leitura que escreve concorre com a escrita de verdade, suja o `atualizado_em`
e é justamente o tipo de efeito colateral que ninguém procura quando o dado
aparece errado.

A régua abaixo abre as telas logadas de quem já tem os dois planos montados
e exige ZERO `INSERT`/`UPDATE`/`DELETE`. Rota nova que grave num GET deixa
de gravar ou entra aqui com a razão escrita. (A renovação da sessão,
`config/sessao.py`, só escreve depois de metade da vida da sessão e não
aparece numa sessão recém-criada.)
"""
import re

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from plans import services
from plans.tests import create_complete_user
from workouts import services as treino

ROTAS = [
    "plans:today", "plans:alimentacao", "plans:history", "plans:hydration",
    "plans:shopping", "workouts:routine", "workouts:now", "workouts:corridas",
    "achievements:list", "accounts:profile", "avisos:preferencias",
    "ajuda:index", "ajuda:mudancas",
]

ESCRITA = re.compile(r'^\s*(INSERT INTO|UPDATE|DELETE FROM)\s+"?([a-z_]+)"?', re.I)


def escritas(consultas):
    achadas = []
    for consulta in consultas:
        casou = ESCRITA.match(consulta["sql"])
        if casou:
            achadas.append("%s %s" % (casou.group(1).upper(), casou.group(2)))
    return achadas


class NenhumGetGravaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="so-leio@exemplo.com")
        services.sync_active_plan(self.user)
        treino.sync_active_routine(self.user)
        self.client.force_login(self.user)

    def test_abrir_cada_tela_nao_grava(self):
        for nome in ROTAS:
            with self.subTest(rota=nome):
                with CaptureQueriesContext(connection) as consultas:
                    resposta = self.client.get(reverse(nome))
                self.assertIn(resposta.status_code, (200, 302))
                self.assertEqual(escritas(consultas.captured_queries), [], nome)

    def test_a_regua_enxerga_uma_escrita(self):
        """Controle positivo: uma escrita de verdade é pega pela régua."""
        with CaptureQueriesContext(connection) as consultas:
            self.client.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertTrue(any("plans_hydrationlog" in e for e in escritas(consultas.captured_queries)))


class ComAnuncioPendenteNenhumGetGravaTests(TestCase):
    """A MESMA varredura, com um anúncio de conquista pendente na sessão.

    Decisão do dono (27/09/2026, revisão do PR #162). A varredura acima abre
    as telas SEM nada a anunciar — e era justamente com um anúncio pendente que
    `achievements.context_processors.conquistas_pendentes` escrevia: marcava a
    conquista como VISTA (`UPDATE seen_at`) e a tirava da sessão (`UPDATE
    django_session`). Um prefetch, uma pré-renderização ou um "abrir em nova
    aba" RENDERIZA sem a pessoa ver, e consumia o anúncio. Hoje o GET só lê, e
    o "visto" é um POST (`achievements:marcar_vistas`) que
    `static/js/conquista.js` manda com a página visível.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        from achievements.context_processors import CHAVE
        from achievements.models import UserAchievement

        self.chave = CHAVE
        self.user = create_complete_user(email="anuncio-pendente@exemplo.com")
        services.sync_active_plan(self.user)
        treino.sync_active_routine(self.user)
        self.client.force_login(self.user)
        self.conquista = UserAchievement.objects.create(user=self.user, slug="primeiro-treino")
        sessao = self.client.session
        sessao[CHAVE] = [self.conquista.pk]
        sessao.save()

    def test_a_pre_condicao_ha_anuncio_e_ele_e_desenhado(self):
        """Sem isto a varredura mediria telas sem nada a anunciar."""
        self.assertIsNone(self.conquista.seen_at)
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('class="conquista', html)

    def test_abrir_cada_tela_com_anuncio_pendente_nao_grava(self):
        for nome in ROTAS:
            with self.subTest(rota=nome):
                with CaptureQueriesContext(connection) as consultas:
                    resposta = self.client.get(reverse(nome))
                self.assertIn(resposta.status_code, (200, 302))
                self.assertEqual(escritas(consultas.captured_queries), [], nome)

    def test_o_anuncio_sobrevive_a_um_get_que_ninguem_viu(self):
        """O caso da decisão: o prefetch renderiza, e a pessoa, na aba dela,
        TEM de ver o anúncio depois."""
        self.client.get(reverse("plans:history"))
        self.assertEqual(self.client.session.get(self.chave), [self.conquista.pk])
        self.conquista.refresh_from_db()
        self.assertIsNone(self.conquista.seen_at)
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('class="conquista', html)

    def test_controle_positivo_o_post_do_visto_escreve(self):
        """O POST que `conquista.js` manda FAZ o `UPDATE` — a mesma régua que
        diz "zero" nas telas o enxerga —, limpa a sessão, e a tela seguinte já
        não traz o aviso."""
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.post(
                reverse("achievements:marcar_vistas"),
                {"id": self.conquista.pk},
                HTTP_X_REQUESTED_WITH="fetch",
            )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            "UPDATE achievements_userachievement", escritas(consultas.captured_queries)
        )
        self.conquista.refresh_from_db()
        self.assertIsNotNone(self.conquista.seen_at)
        self.assertNotIn(self.chave, self.client.session)
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn('class="conquista', html)

    def test_o_que_foi_visto_nao_volta_mesmo_com_a_sessao_velha(self):
        """A sessão pode ainda listar o id (outra aba, ou o POST que se
        perdeu), e a renderização filtra por `seen_at`."""
        from django.utils import timezone

        type(self.conquista).objects.filter(pk=self.conquista.pk).update(seen_at=timezone.now())
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn('class="conquista', html)


class OJavaScriptMarcaVistoSoQuandoAlguemVeTests(TestCase):
    """A terceira ponta: o POST do "visto" sai de `conquista.js`, e só com a
    página VISÍVEL e fora de pré-renderização — senão o JavaScript de uma
    página pré-renderizada consumiria o anúncio do mesmo jeito que o GET."""

    def _js(self):
        from pathlib import Path

        from django.conf import settings

        from config.estaticos import sem_comentarios

        return sem_comentarios(
            (Path(settings.BASE_DIR) / "static" / "js" / "conquista.js").read_text(encoding="utf-8")
        )

    def _corpo(self):
        js = self._js()
        self.assertIn("var marcarVista", js)
        return js, js.split("var marcarVista", 1)[1].split("};", 1)[0]

    def test_o_visto_e_um_post_ao_endereco_do_formulario(self):
        _js, corpo = self._corpo()
        self.assertIn("fetch(form.action", corpo)
        self.assertIn('method: "POST"', corpo)
        self.assertIn("keepalive: true", corpo)

    def test_so_com_a_pagina_visivel_e_fora_de_pre_renderizacao(self):
        js, corpo = self._corpo()
        self.assertIn('document.visibilityState !== "visible"', corpo)
        self.assertIn("document.prerendering", corpo)
        self.assertIn('addEventListener("visibilitychange", marcarVista)', js)
        self.assertIn('addEventListener("prerenderingchange", marcarVista)', js)
        # E a primeira chamada acontece ao carregar — sem ela o aviso só seria
        # dado por visto na próxima troca de aba.
        self.assertIn("marcarVista();", js)
