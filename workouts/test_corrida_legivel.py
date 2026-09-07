# -*- coding: utf-8 -*-
"""O histórico de corridas fala a mesma língua do painel ao vivo.

O painel diz "0,00 km", "00:00 em movimento" e "min/km". O histórico, na mesma
página, escrevia "5230 m" e "1523 s em movimento" — e o pace, que
`Corrida.pace_s_km` já calculava e documentava, não aparecia em template
nenhum.
"""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from workouts.models import Corrida
from workouts.templatetags.corrida import km, pace, relogio


class OsFiltrosDaCorridaTests(SimpleTestCase):
    def test_o_relogio_usa_minutos_e_segundos(self):
        self.assertEqual(relogio(1523), "25:23")
        self.assertEqual(relogio(0), "00:00")
        self.assertEqual(relogio(59), "00:59")

    def test_acima_de_uma_hora_aparece_a_hora(self):
        """A maratona vira "2:01:39" e não "121:39" — a forma só-minutos fica
        ilegível exatamente na corrida longa."""
        self.assertEqual(relogio(7299), "2:01:39")

    def test_valor_impossivel_vira_travessao_em_vez_de_estourar(self):
        self.assertEqual(relogio(None), "—")
        self.assertEqual(relogio("qualquer coisa"), "—")
        self.assertEqual(relogio(-5), "—")

    def test_a_distancia_sai_em_km_com_virgula(self):
        """O app é pt-BR: "5,23", não "5.23"."""
        self.assertEqual(km(5230), "5,23")
        self.assertEqual(km(1000), "1,00")
        self.assertEqual(km(400), "0,40")


class OPaceApareceNoHistoricoTests(TestCase):
    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="corre@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)

    def _corrida(self, **campos):
        agora = timezone.now()
        padrao = dict(user=self.pessoa, op_id="uma", comecou_em=agora - timedelta(hours=1),
                      terminou_em=agora, distancia_m=5230, duracao_s=1523)
        padrao.update(campos)
        return Corrida.objects.create(**padrao)

    def test_a_tela_mostra_km_relogio_e_pace(self):
        self._corrida()

        html = self.client.get(reverse("workouts:corridas")).content.decode()

        self.assertIn("5,23", html)
        self.assertIn("25:23", html)
        self.assertIn("04:51", html)   # 1523 s / 5,23 km

    def test_a_tela_nao_escreve_mais_o_valor_cru(self):
        """Ancorado no texto VISÍVEL e não no número solto: "5230" aparecia
        como "5230 m", e é essa forma que não pode voltar."""
        self._corrida()

        html = self.client.get(reverse("workouts:corridas")).content.decode()

        self.assertNotIn("5230 m", html)
        self.assertNotIn("1523 s", html)

    def test_corrida_sem_distancia_mostra_travessao_e_nao_quebra(self):
        """`pace_s_km` devolve `None` quando não há o que dividir. O filtro
        precisa aguentar isso — a tela não pode dar 500 por causa de um
        registro antigo."""
        self._corrida(distancia_m=0, op_id="vazia")

        resposta = self.client.get(reverse("workouts:corridas"))

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("—", resposta.content.decode())

    def test_o_filtro_de_pace_le_a_propriedade_do_modelo(self):
        """Não refaz a divisão: a propriedade é que sabe quando devolver
        `None`, e uma segunda conta aqui seria a terceira cópia do mesmo fato."""
        corrida = self._corrida(op_id="prop")

        self.assertEqual(pace(corrida), relogio(round(corrida.pace_s_km)))


class CorridaComLacunaNaoRecebePaceTests(TestCase):
    """A tela apagada para o GPS e não para o relógio.

    `corrida.js` marca `teveLacuna` no `visibilitychange` porque o app SABE
    que aquele trecho não foi medido. O tempo fica inteiro, a distância fica
    curta, e o pace derivado dos dois é rápido demais — errado por construção,
    não por imprecisão.
    """

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="lacuna@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)
        agora = timezone.now()
        self.base = dict(user=self.pessoa, comecou_em=agora - timedelta(hours=1),
                         terminou_em=agora, distancia_m=5230, duracao_s=1523)

    def test_com_lacuna_o_pace_vira_travessao(self):
        corrida = Corrida.objects.create(op_id="furada", teve_lacuna=True, **self.base)

        self.assertEqual(pace(corrida), "—")

    def test_sem_lacuna_o_pace_continua_aparecendo(self):
        """CONTROLE POSITIVO: sem ele, um filtro que devolvesse sempre "—"
        passaria no teste acima."""
        corrida = Corrida.objects.create(op_id="inteira", teve_lacuna=False, **self.base)

        self.assertEqual(pace(corrida), "04:51")

    def test_a_distancia_e_o_tempo_continuam_na_tela_mesmo_com_lacuna(self):
        """Os dois são medição real, ainda que incompleta. Esconder tudo
        apagaria os cinco quilômetros que a pessoa de fato correu."""
        Corrida.objects.create(op_id="furada", teve_lacuna=True, **self.base)

        html = self.client.get(reverse("workouts:corridas")).content.decode()

        self.assertIn("5,23", html)
        self.assertIn("25:23", html)
        self.assertIn("trecho não registrado", html)
