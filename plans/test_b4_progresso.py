"""B4 — METRICAS: o aviso que nao sumia, as barras que nao comparavam.

Quatro defeitos medidos no navegador contra a stack local:

1. O convite a recalibrar a dieta NAO sumia depois de respondido.
   `Profile.recalibrated_at` era gravado pelas duas respostas e nao era lido
   por ninguem — `grep` nao achava uma leitura sequer, e `sugerir_recalibragem`
   saia so do peso, que nao se mexe em dois minutos. Medido: dois toques em
   "Cortar 150 kcal" no mesmo minuto levaram `kcal_adjustment` para −300 e a
   meta para 1773 kcal, com o cartao ainda na tela oferecendo o terceiro. O
   proprio texto do botao promete "De duas semanas antes de julgar o
   resultado", e a docstring da view ja dizia que o app registra a escolha
   "para nao repetir a pergunta na semana seguinte" — dizia, e nao fazia.

2. Os cartoes de Treino e Agua desenham a MESMA escala de 0 a 7 e tinham
   trilhos de larguras diferentes. Medido a 375px: 192px no treino e 129px na
   agua, porque a barra e `1fr` e a coluna de valor da agua reserva mais
   espaco. Cinco dias de agua (91px) desenhavam quase igual a tres dias de
   treino (83px) — exatamente a comparacao que unificar as duas listas existia
   para permitir.

3. Os vaos entre cartoes saiam 16, 32, 32, 16: a tela partia cinco cartoes em
   tres containers de um `.split` que e coluna unica em toda largura. Dentro de
   um container o `gap` do flex soma com a margem do `.stack`; entre containers
   so o `gap` conta. O agrupamento saia invertido — Peso, Treino e Agua, que
   sao a mesma gramatica, mais afastados entre si do que da fronteira.

4. O `<title>` dizia "Historico" numa tela cuja aba e cujo `<h1>` dizem
   "Metricas".
"""
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry

from . import weight_trend
from .models import MealLog, MealStatus
from .tests import create_complete_user

CSS = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"


def parado(user, semanas=4):
    """Media semanal que nao se mexe — o estado que gera o convite."""
    user.weight_entries.all().delete()
    hoje = timezone.localdate()
    segunda = hoje - timedelta(days=hoje.weekday())
    for semana in range(semanas, -1, -1):
        inicio = segunda - timedelta(weeks=semana)
        for dia in (0, 2, 4):
            quando = inicio + timedelta(days=dia)
            if quando > hoje:
                continue
            WeightEntry.objects.create(
                user=user, date=quando,
                weight_kg=Decimal("81.0") + Decimal(dia) / 100,
            )


class OConviteEsperaDepoisDeRespondidoTests(TestCase):
    """Responder ao aviso tem de fazer o aviso ir embora.

    A supressao e do CONVITE, e nao do fato: a media continua parada e a tela
    pode continuar dizendo isso. O que espera duas semanas e a oferta de mexer
    na dieta outra vez.
    """

    def setUp(self):
        self.pessoa = create_complete_user(email="b4recal@exemplo.com")
        parado(self.pessoa)
        self.client.force_login(self.pessoa)

    def _perfil(self):
        self.pessoa.profile.refresh_from_db()
        return self.pessoa.profile

    def test_sem_nunca_ter_respondido_o_convite_aparece(self):
        """O controle positivo. Sem ele, uma supressao larga demais passaria
        despercebida: o teste seguinte ficaria verde com o convite morto."""
        self.assertTrue(weight_trend.analisar(self.pessoa).sugerir_recalibragem)
        self.assertContains(
            self.client.get(reverse("plans:history")), "Sua média estabilizou"
        )

    def test_depois_de_cortar_o_convite_some_da_tela(self):
        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})

        self.assertNotContains(
            self.client.get(reverse("plans:history")), "Sua média estabilizou"
        )

    def test_depois_de_recusar_o_convite_some_da_tela(self):
        self.client.post(reverse("plans:recalibrate"), {"acao": "dispensar"})

        self.assertNotContains(
            self.client.get(reverse("plans:history")), "Sua média estabilizou"
        )

    def test_passada_a_espera_o_convite_volta(self):
        """A outra metade. Suprimir para sempre trocaria um defeito por outro:
        a pessoa que cortou e continuou parada precisa ser perguntada de novo.
        """
        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})
        perfil = self._perfil()
        perfil.recalibrated_at = timezone.now() - (
            weight_trend.ESPERA_APOS_RECALIBRAR + timedelta(days=1)
        )
        perfil.save(update_fields=["recalibrated_at"])

        self.assertContains(
            self.client.get(reverse("plans:history")), "Sua média estabilizou"
        )

    def test_a_media_parada_continua_sendo_relatada(self):
        """O que some e o convite, nao o fato.

        Se `semanas_paradas` zerasse junto, o app passaria a esconder que a
        media empacou — que e informacao verdadeira e util.
        """
        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})
        # Um usuario NOVO, lido do banco. `analisar` chega ao perfil por
        # `user.profile`, e o Django guarda essa relacao na INSTANCIA: o objeto
        # que o teste tem em mao continua com o `recalibrated_at` de antes do
        # POST, e o teste mediria o estado velho.
        pessoa = type(self.pessoa).objects.get(pk=self.pessoa.pk)

        tendencia = weight_trend.analisar(pessoa)

        self.assertFalse(tendencia.sugerir_recalibragem)
        self.assertGreaterEqual(
            tendencia.semanas_paradas, weight_trend.SEMANAS_PARA_RECALIBRAR
        )

    def test_o_segundo_corte_nao_e_aplicado(self):
        """A aba velha.

        A tela deixou de oferecer o botao, mas quem tinha a pagina aberta antes
        de responder continua com o formulario valido. Sem esta guarda, o corte
        seria aplicado de novo por quem so voltou numa aba que ficou aberta —
        e foi assim, com dois envios, que −300 kcal apareceram no navegador.
        """
        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})
        primeiro = self._perfil().kcal_adjustment

        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})

        self.assertEqual(primeiro, -weight_trend.AJUSTE_KCAL)
        self.assertEqual(self._perfil().kcal_adjustment, primeiro)

    def test_o_segundo_envio_explica_por_que_nao_fez_nada(self):
        """Recusar em silencio e pior que aplicar: a pessoa toca, nada muda, e
        ela toca de novo."""
        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})

        resposta = self.client.post(
            reverse("plans:recalibrate"), {"acao": "cortar"}, follow=True
        )

        self.assertContains(resposta, "Você já respondeu a esse aviso")


class OsDoisCartoesSemanaisSaoComparaveisTests(TestCase):
    """Treino e Agua desenham a mesma escala e precisam do mesmo trilho.

    `MesmaGramaticaTests` ja cobra que as duas listas usem a MESMA ESTRUTURA.
    Isto cobra a outra metade, que a estrutura igual nao garantia: que a barra
    tenha o mesmo comprimento nos dois cartoes.
    """

    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")

    def _regra(self, seletor):
        m = re.search(
            r"(?m)^%s\s*\{(.*?)\}" % re.escape(seletor), self.css, re.S
        )
        return m.group(1) if m else None

    def test_a_coluna_de_valor_reserva_largura(self):
        corpo = self._regra(".semana__valor")

        self.assertIsNotNone(corpo, "a regra .semana__valor sumiu")
        largura = re.search(r"min-width:\s*([\d.]+)rem", corpo)
        self.assertIsNotNone(
            largura,
            "sem largura reservada a barra volta a sobrar no treino e faltar "
            "na agua",
        )
        self.assertGreaterEqual(float(largura.group(1)), 4.0)

    def test_nao_existe_mais_uma_largura_so_para_a_agua(self):
        """A classe `--largo` era o que criava a diferenca. Enquanto ela
        existir, alguem pode reaplica-la e os trilhos divergem de novo."""
        self.assertNotIn("semana__valor--largo", self.css)

    def test_nenhum_template_usa_a_classe_que_deixou_de_existir(self):
        raiz = Path(__file__).resolve().parent.parent / "templates"
        usos = [
            caminho.name
            for caminho in raiz.rglob("*.html")
            if "semana__valor--largo" in caminho.read_text(encoding="utf-8")
        ]

        self.assertEqual(usos, [])


class ATelaNaoParteOsCartoesTests(TestCase):
    """Cinco cartoes, um container, um vao so.

    `.split` e coluna unica em toda largura — decisao registrada no CSS. Partir
    os cartoes entre `split__main` e `split__aside` nao produzia coluna
    nenhuma; produzia 16, 32, 32, 16 de vao, invertendo o agrupamento.
    """

    def setUp(self):
        # Uma refeicao marcada, senao `totals.days` e zero e a tela renderiza o
        # ramo VAZIO — que nao tem `.split` nenhum, e o teste mediria a
        # ausencia dos containers em vez de um container so.
        self.pessoa = create_complete_user(email="b4split@exemplo.com")
        MealLog.objects.create(
            user=self.pessoa, date=timezone.localdate(),
            status=MealStatus.DONE, kcal=800, slot_name="almoço",
        )
        self.client.force_login(self.pessoa)
        self.html = self.client.get(reverse("plans:history")).content.decode()

    def test_ha_um_unico_container_de_cartoes(self):
        containers = (
            self.html.count("split__main") + self.html.count("split__aside")
        )

        self.assertEqual(containers, 1, "a tela voltou a partir os cartões")

    def test_o_estado_vazio_usa_o_mesmo_container(self):
        """Estado vazio nao e outra tela.

        Solto no `.container`, quem espaca os cartoes e `.card + .card`, que
        vale 16px; dentro do `.split__main` o `gap` soma com a margem do
        `.stack` e vale 32. Medido: a MESMA tela mudava de ritmo conforme a
        pessoa ja tivesse marcado uma refeicao ou nao.
        """
        vazia = create_complete_user(email="b4vazio@exemplo.com")
        self.client.force_login(vazia)

        html = self.client.get(reverse("plans:history")).content.decode()

        self.assertIn("Ainda não há nada marcado", html)
        self.assertEqual(
            html.count("split__main") + html.count("split__aside"), 1
        )

    def test_a_ordem_e_resumo_peso_treino_agua_e_o_dia_a_dia(self):
        """A ordem que o contrato desta tela fixa, lida do documento.

        Vale como teste porque `.split` e coluna unica: aqui a ordem do HTML e
        a ordem da tela em qualquer largura.
        """
        marcos = ["Aderência", "<h2>Peso", "<h2>Treino", "<h2>Água", "Dia a dia"]
        posicoes = [self.html.index(m) for m in marcos]

        self.assertEqual(posicoes, sorted(posicoes), marcos)


class OTituloEONomeDaTelaTests(TestCase):
    """A aba do navegador e a lista de apps da PWA chamam a pagina pelo
    `<title>`; a tela e a barra de abas chamam de "Progresso".

    O B4 alinhou os três em "Métricas", que era o rótulo com que a barra tinha
    nascido. O B6 corrigiu o rótulo: o contrato de navegação escreve
    `Progresso` e nunca escreve `Métricas`. O que este teste protege não é a
    palavra — é a IGUALDADE entre o título e o nome que a tela mostra, que foi
    o defeito original.
    """

    def setUp(self):
        self.pessoa = create_complete_user(email="b4titulo@exemplo.com")
        self.client.force_login(self.pessoa)
        self.html = self.client.get(reverse("plans:history")).content.decode()

    def test_o_titulo_diz_metricas(self):
        titulo = re.search(r"<title>(.*?)</title>", self.html, re.S).group(1)

        self.assertEqual(titulo.strip(), "Progresso · NutriPlan")

    def test_a_tela_continua_se_chamando_metricas(self):
        """A premissa. Se o `<h1>` mudar de nome amanhã, o titulo acima
        passa a estar errado e o teste de cima nao perceberia sozinho."""
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", self.html, re.S).group(1)

        self.assertEqual(h1.strip(), "Progresso")

    def test_o_endereco_publicado_nao_mudou(self):
        """Rotulo se troca, endereco publicado nao."""
        self.assertEqual(reverse("plans:history"), "/historico/")
