# -*- coding: utf-8 -*-
"""A demonstração vem ANTES da série, como poster — e o player nasce no toque.

O vídeo era o sexto bloco do cartão de execução: topo, pastilhas, descanso,
formulário, desfazer, mídia. Medido em 13/09/2026: 0 px de vídeo visíveis a
320×568, 63 a 375×667. "Vê a série, não vê o vídeo" era literal. Subir o
iframe inteiro foi refutado com conta (391 px, o CTA saía da dobra em todas
as larguras); o que sobe é uma faixa de ~96 px — foto do exercício e "toque
para ver o vídeo" — e o toque monta o player no lugar. Decisão do dono em
13/09/2026, revendo a de 30/08 ("mídia abaixo do botão") com a medição a favor.

O HTML servido tem ZERO iframe; a escada de mídia é do servidor e mora nos
`data-` do parcial `_demonstracao.html`, que a rota de leitura reaproveita.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.tests import create_user, dias_incluindo_hoje, sem_scripts


class OPosterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="poster@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        hoje = timezone.localdate().weekday()
        sessao = next(s for s in plano.sessions.all() if s.weekday == hoje)
        self.item = sessao.exercises.select_related("exercise").first()
        self.html = sem_scripts(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode())

    def test_o_poster_vem_antes_das_series_e_leva_a_dica_do_movimento(self):
        poster = self.html.index('class="demo')
        cue = self.html.index('class="demo__cue"')
        series = self.html.index('class="series"')
        formulario = self.html.index('class="registro registro--agora"')
        self.assertLess(poster, cue)
        self.assertLess(cue, series)
        self.assertLess(series, formulario)
        self.assertIn(self.item.exercise.cue, self.html.split('class="demo__cue"', 1)[1].split("</p>", 1)[0])

    def test_o_html_servido_nao_tem_player_e_o_poster_carrega_o_video(self):
        self.assertEqual(self.html.count("<iframe"), 0)
        self.assertNotIn('class="agora__media', self.html)
        identificador = self.item.exercise.video_embed_url.split("/embed/")[1].split("?")[0]
        demo = self.html.split("data-demo", 1)[1].split("</div>", 1)[0]
        self.assertIn(identificador, demo)
        self.assertIn('data-tipo="youtube"', demo)

    def test_o_poster_tem_a_foto_e_diz_o_que_o_toque_faz(self):
        demo = self.html.split("data-demo", 1)[1].split("</div>", 1)[0]
        self.assertIn('class="demo__foto"', demo)
        self.assertIn(self.item.exercise.frames[0], demo)
        self.assertIn("ver vídeo", demo)
        self.assertIn('aria-label="Ver o vídeo de %s"' % self.item.exercise.name, demo)
        # Sem script, ainda há caminho até o vídeo.
        self.assertIn("<noscript>", demo)
        self.assertIn(self.item.exercise.video_url, demo)

    def test_o_poster_e_um_parcial_partilhado(self):
        """Uma cópia: a rota de leitura usa o mesmo arquivo."""
        from pathlib import Path

        from django.conf import settings

        agora = (Path(settings.BASE_DIR) / "templates" / "workouts" / "agora.html").read_text(encoding="utf-8")
        self.assertIn('include "workouts/_demonstracao.html"', agora)
