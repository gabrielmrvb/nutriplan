"""A leitura do exercício volta para onde a pessoa veio; a linha da ficha inteira é a porta.

UX NOVO-03 (14/09/2026): quem abria a leitura a partir da ficha A1 lia
"← Treino" e voltava ao painel — dois toques para estar de novo onde
estava. `?de=` diz de onde veio, em LISTA FECHADA (`ficha`, `agora`,
`painel`), como `?exercicio=`: valor desconhecido é 404, e o `href` da
volta nunca é montado a partir do pedido — é `reverse()` da tela nomeada.
`sessao=` acompanha `ficha` e tem de ser uma sessão em que o exercício
está; senão, 404.

CA-03 / NOVO-06: na ficha, o número da linha ficava fora do link — a
única parte da linha que não abria nada. Ele entra no link "ver", e a
área tocável da linha (ver + fazer) passa de 90 %.
"""

from django.test import TestCase
from django.urls import reverse

from . import services
from .test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje


class DeOndeVeioTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("de-onde@exemplo.com")
        self.sessao = tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.item = self.sessao.exercises.first()
        self.url = reverse("workouts:exercicio", args=[self.item.exercise_id])

    def _volta(self, sufixo=""):
        resposta = self.client.get(self.url + sufixo)
        self.assertEqual(resposta.status_code, 200, sufixo)
        html = resposta.content.decode()
        inicio = html.index('<div class="page-head">')
        return html[inicio: html.index("</div>", inicio)]

    def test_sem_parametro_volta_ao_painel(self):
        volta = self._volta()
        self.assertIn('href="%s"' % reverse("workouts:routine"), volta)
        self.assertIn("← Treino", volta)

    def test_da_ficha_volta_para_a_ficha_com_o_rotulo_dela(self):
        volta = self._volta("?de=ficha&sessao=%d" % self.sessao.pk)
        self.assertIn('href="%s"' % reverse("workouts:ficha", args=[self.sessao.pk]), volta)
        self.assertIn("← Ficha A1", volta)

    def test_da_execucao_volta_para_a_execucao_deste_exercicio(self):
        volta = self._volta("?de=agora")
        self.assertIn(
            'href="%s?exercicio=%d"' % (reverse("workouts:now"), self.item.exercise_id), volta
        )
        self.assertIn("← Execução", volta)

    def test_valor_desconhecido_e_404_e_nunca_vira_href(self):
        for sufixo in ("?de=qualquer", "?de=//evil.example", "?de=ficha&de=agora", "?de="):
            with self.subTest(sufixo=sufixo):
                self.assertEqual(self.client.get(self.url + sufixo).status_code, 404)

    def test_sessao_que_nao_tem_o_exercicio_e_404(self):
        plano = services.get_active_routine(self.user)
        outra = plano.sessions.exclude(pk=self.sessao.pk).exclude(
            exercises__exercise_id=self.item.exercise_id
        ).first()
        self.assertEqual(
            self.client.get(self.url + "?de=ficha&sessao=%d" % outra.pk).status_code, 404
        )
        self.assertEqual(self.client.get(self.url + "?de=ficha&sessao=x").status_code, 404)

    def test_a_ficha_manda_de_onde_veio_e_o_numero_esta_dentro_do_link(self):
        html = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode()
        self.assertIn(
            'href="%s?de=ficha&amp;sessao=%d"' % (self.url, self.sessao.pk), html
        )
        # O número da linha fica DENTRO de `.ficha-item__ver`.
        inicio = html.index('class="ficha-item__ver"')
        trecho = html[inicio: html.index("</a>", inicio)]
        self.assertIn('class="ficha-item__ordem', trecho)

    def test_a_execucao_manda_de_onde_veio(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn('class="agora__nome-link" href="%s?de=agora"' % self.url, html)
