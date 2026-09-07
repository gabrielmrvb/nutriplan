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

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActivityLevel, Goal, Sex, WeightEntry

from . import weight_trend
from .calculations import ABSOLUTE_MIN_KCAL
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


class OCorteManualNaoFuraOPisoClinicoTests(TestCase):
    """`kcal_adjustment` acumula, e a trava só olhava para a taxa basal.

    O módulo declara DOIS pisos: a taxa metabólica basal e
    `ABSOLUTE_MIN_KCAL` — 1.500 para homem, 1.200 para mulher, "a recomendação
    clássica de piso para dietas sem acompanhamento clínico". O docstring de
    `kcal_adjustment` promete que "um corte manual não pode furá-las", no
    plural. Só o primeiro estava sendo aplicado depois do ajuste.

    Quando a taxa basal é MENOR que o mínimo absoluto, o corte passava por
    baixo do piso clínico: mulher de 45 kg, 150 cm e 60 anos tem TMB 927, e
    dois toques em "Cortar 150 kcal" levavam a meta para 927 — 273 abaixo do
    que o próprio app diz respeitar. E a tela oferece esse corte a cada duas
    semanas, sem teto.
    """

    def _meta(self, sex, idade, altura, peso, ajuste, *,
               atividade=ActivityLevel.SEDENTARY, objetivo=Goal.CUT,
               sessoes=()):
        from plans import calculations

        entradas = calculations.PlanInputs(
            sex=sex, age_years=idade, height_cm=altura, weight_kg=Decimal(peso),
            activity_level=atividade, goal=objetivo,
            session_minutes=sessoes, kcal_adjustment=ajuste,
        )
        return calculations.calculate(entradas)

    def test_a_mulher_pequena_nao_desce_abaixo_de_1200(self):
        for ajuste in (0, -150, -300, -900):
            with self.subTest(ajuste=ajuste):
                plano = self._meta(Sex.FEMALE, 60, 150, "45", ajuste)
                self.assertGreaterEqual(
                    plano.target_kcal, ABSOLUTE_MIN_KCAL[Sex.FEMALE],
                    "corte de %d furou o piso clínico" % ajuste,
                )

    def test_o_homem_com_gasto_baixo_nao_desce_abaixo_de_1500(self):
        for ajuste in (0, -150, -450, -900):
            with self.subTest(ajuste=ajuste):
                plano = self._meta(Sex.MALE, 60, 165, "60", ajuste)
                self.assertGreaterEqual(
                    plano.target_kcal, ABSOLUTE_MIN_KCAL[Sex.MALE],
                    "corte de %d furou o piso clínico" % ajuste,
                )

    def test_o_corte_continua_valendo_quando_cabe_acima_do_piso(self):
        """CONTROLE POSITIVO: sem ele, um piso que ignorasse o ajuste por
        completo passaria nos dois testes acima e quebraria a função.

        O perfil tem de ter FOLGA até o piso, e a primeira versão deste teste
        não tinha: homem sedentário em corte já para na própria taxa basal por
        `target_kcal`, então o corte manual não tinha para onde descer e o
        controle reprovava um código correto. Aqui ele treina cinco vezes e
        quer manter — sobra caminho.
        """
        perfil = dict(atividade=ActivityLevel.ACTIVE, objetivo=Goal.MAINTAIN,
                      sessoes=(60, 60, 60, 60, 60))
        cheio = self._meta(Sex.MALE, 30, 178, "80", 0, **perfil).target_kcal
        cortado = self._meta(Sex.MALE, 30, 178, "80", -150, **perfil).target_kcal

        self.assertEqual(cortado, cheio - 150)
        self.assertGreater(cortado, ABSOLUTE_MIN_KCAL[Sex.MALE])


class OPisoDeSegurancaNaoViraSuperavitRecomendadoTests(TestCase):
    """A tela dizia as duas coisas ao mesmo tempo, com treze linhas de distância.

    Em gente pequena o piso de segurança eleva a meta ACIMA do gasto: mulher de
    45 kg, 150 cm e 60 anos, sedentária, tem gasto 1.158 e meta 1.200. O
    classificador lia só o sinal da subtração e devolvia "Superávit diário
    recomendado" — para quem escolheu Emagrecer —, enquanto a nota do plano,
    logo abaixo, explicava que "o emagrecimento fica mais lento, e mais
    seguro".

    Quem sabe que houve piso é `target_kcal`. A classificação passa a
    considerar o objetivo em vez de recalcular por fora com outra régua.
    """

    def _balanco(self, sex, idade, altura, peso, objetivo):
        from decimal import Decimal

        from accounts.models import ActivityLevel
        from plans import calculations, views

        entradas = calculations.PlanInputs(
            sex=sex, age_years=idade, height_cm=altura, weight_kg=Decimal(peso),
            activity_level=ActivityLevel.SEDENTARY, goal=objetivo,
            session_minutes=(),
        )
        r = calculations.calculate(entradas)

        class Fake:
            target_kcal = r.target_kcal
            tdee_kcal = r.tdee_kcal
            goal = objetivo

        return views.energy_balance(Fake())

    def test_meta_acima_do_gasto_em_quem_quer_emagrecer_nao_e_superavit(self):
        b = self._balanco(Sex.FEMALE, 60, 150, "45", Goal.CUT)

        self.assertGreater(b["delta_kcal"], 0, "o caso de borda mudou; reveja")
        self.assertEqual(b["kind"], "piso")
        self.assertNotIn("uperávit", b["label"])

    def test_quem_quer_ganhar_massa_continua_vendo_superavit(self):
        """CONTROLE POSITIVO: sem ele, marcar tudo que é positivo como piso
        apagaria o rótulo certo de quem está em ganho."""
        b = self._balanco(Sex.MALE, 30, 178, "80", Goal.BULK)

        self.assertGreater(b["delta_kcal"], 0)
        self.assertEqual(b["kind"], "surplus")

    def test_quem_emagrece_com_folga_continua_vendo_deficit(self):
        b = self._balanco(Sex.MALE, 30, 178, "110", Goal.CUT)

        self.assertLess(b["delta_kcal"], 0)
        self.assertEqual(b["kind"], "deficit")


class ZerarAAguaPedeConfirmacaoTests(TestCase):
    """Apagar o dia inteiro não pode ser um toque só, colado em "desfazer".

    As duas ações moravam lado a lado como links de um toque, e fazem coisas de
    tamanhos muito diferentes: "desfazer" tira o último gole, "zerar" apaga o
    total E a lista de goles do dia, sem volta. Um polegar errado entre séries
    custava o registro do dia.

    A confirmação é `<details>` e não `<dialog>` — é a ordem que o CLAUDE.md
    fixa — e funciona sem JavaScript, o que importa porque esta tela é postada
    por formulário puro.
    """

    CAMINHO = Path(settings.BASE_DIR) / "templates" / "plans" / "_agua.html"

    def setUp(self):
        self.fonte = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "",
            self.CAMINHO.read_text(encoding="utf-8"), flags=re.S,
        )

    def test_o_zerar_esta_atras_de_uma_confirmacao(self):
        self.assertIn("acao-perigosa", self.fonte)
        bloco = self.fonte.split('name="ml" value="0"', 1)[0]
        self.assertIn("<details", bloco[-400:],
                      "o campo que zera não está dentro de uma confirmação")

    def test_desfazer_continua_sendo_um_toque_so(self):
        """CONTROLE POSITIVO: confirmar TUDO treinaria a pessoa a confirmar sem
        ler, e desfazer um gole não merece cerimônia."""
        bloco = self.fonte.split('value="desfazer"', 1)[0]
        self.assertNotIn("<details", bloco[-300:])


class OPerfilMostraAMetaDeHojeTests(TestCase):
    """Duas telas, dois números, a mesma pessoa e o mesmo instante.

    As telas do app sincronizam o plano no GET (`PlanRequiredMixin`). O Perfil
    lia `plans.filter(is_active=True).first()` cru — então, depois de qualquer
    mudança de entrada, ele mostrava a meta ANTIGA até a pessoa passar por
    Hoje.

    MEDIDO no navegador: registrei 78,4 kg no lugar de 80 e o Perfil continuou
    dizendo 2.520 kcal enquanto o motor já respondia 2.497. E o número velho
    aparecia ao lado do botão que recalcula — o pior lugar possível, porque é
    exatamente ali que a pessoa decide se precisa recalcular.
    """

    def setUp(self):
        self.pessoa = create_complete_user("perfil-meta@exemplo.com")
        from plans.services import sync_active_plan
        sync_active_plan(self.pessoa)   # a tela precisa de um plano para mostrar
        self.client.force_login(self.pessoa)

    def _perfil(self):
        return self.client.get(reverse("accounts:profile"))

    def test_mudar_o_peso_faz_o_perfil_avisar_que_o_numero_envelheceu(self):
        antes = self._perfil()
        self.assertFalse(antes.context["plano_vencido"],
                         "nasceu vencido; o caso perdeu o sentido")

        # `update_or_create`, e não `create`: existe `unique_weight_per_day`
        # e `create_complete_user` já registrou o peso de hoje. O produto
        # funciona assim mesmo — pesar de novo no mesmo dia CORRIGE a pesagem,
        # não acrescenta uma segunda. Medido no navegador: depois de salvar
        # 78,4 sobre 80, o total de pesagens continuou 1.
        from django.utils import timezone as _tz
        WeightEntry.objects.update_or_create(
            user=self.pessoa, date=_tz.localdate(),
            defaults={"weight_kg": Decimal("62.0")},
        )
        depois = self._perfil()

        # A TELA NÃO RECALCULA SOZINHA — isso escreveria num GET e regeraria o
        # cardápio inteiro; medido, custava 19 consultas contra um teto de 15.
        # Ela AVISA, que é o que dá sentido ao botão logo abaixo.
        self.assertTrue(depois.context["plano_vencido"])
        self.assertContains(depois, "Recalcular metas")
        self.assertEqual(depois.context["plano"].target_kcal,
                         antes.context["plano"].target_kcal,
                         "o GET do perfil não pode ter reescrito o plano")

    def test_quem_nao_terminou_o_cadastro_nao_quebra_a_tela(self):
        """`sync_active_plan` precisa do perfil inteiro, e esta tela é só
        `LoginRequiredMixin` — alguém no meio do onboarding chega aqui."""
        from accounts.models import ONBOARDING_DONE

        perfil = self.pessoa.profile
        perfil.onboarding_step = ONBOARDING_DONE - 1
        perfil.save(update_fields=["onboarding_step"])

        resposta = self.client.get(reverse("accounts:profile"))

        self.assertEqual(resposta.status_code, 200)
