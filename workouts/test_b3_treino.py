"""B3 — TREINO: o que a tela fala, o que ela desfaz e onde ficam as portas.

Tres defeitos medidos no navegador, com a conta de cada um:

1. O relogio do descanso vivia dentro de uma regiao viva e trocava de texto uma
   vez por segundo. Medido com `MutationObserver`: cinco mutacoes em 5,2 s, nas
   DUAS telas de treino. Cada mutacao faz o leitor de tela reler a regiao
   inteira — "Descanso 54s pular", "Descanso 53s pular" — e sao oitenta
   anuncios por descanso, cerca de dois mil num treino de 29 series. Uma fila
   de fala desse tamanho nao informa: ela impede ouvir o resto da tela.

2. "desfazer ultima serie" sumia no instante em que o exercicio fechava. A
   ultima serie da puxada e justamente a que passa a vez para a remada, e
   entao `atual.feitas` e zero e o botao nao existe mais. Nove vezes por
   treino, sempre logo depois da serie mais provavel de ter sido registrada por
   engano.

3. A unica porta para a Corrida era o ultimo bloco do documento — medido a
   375px, o cabecalho em y=5476 de uma pagina de 5755.

4. E, achado ao consertar o segundo: `ultimo_log` saia de um `max` por
   `created_at`, e no empate devolvia a primeira linha da iteracao — a do
   exercicio ANTERIOR. Enquanto isso so alimentava o cronometro, escolher
   errado custava segundos de descanso; com o desfazer pendurado nisso,
   apagaria a serie errada.

O que estes testes NAO fazem: julgar se o cronometro esta bonito. Eles
verificam onde a informacao mora, quem fala e o que o botao apaga.
"""
import re
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user


def dentro_de_regiao_viva(html, marcador):
    """O marcador esta dentro de algum elemento com `aria-live`?

    Anda de tras para frente a partir do marcador contando `<div>` abertas e
    fechadas; se encontrar `aria-live` numa `<div>` que ainda estava aberta
    quando o marcador apareceu, o marcador esta dentro dela.

    Simplificacao deliberada — os dois blocos medidos usam `<div>`. Um teste
    que arrastasse um parser de HTML esconderia o que ele mede.
    """
    trecho = html[: html.index(marcador)]
    profundidade = 0
    for tag in reversed(list(re.finditer(r"<(/?)div\b([^>]*)>", trecho))):
        if tag.group(1) == "/":
            profundidade += 1
        elif profundidade:
            profundidade -= 1
        elif "aria-live" in tag.group(2):
            return True
    return False


class ORelogioNaoFalaACadaSegundoTests(TestCase):
    """A contagem fica na tela; a fala fica para os dois instantes que decidem.

    O relogio continua legivel — quem navegar ate ele ouve o numero. O que sai
    e o empurrao: nao existe mais nada que force a leitura a cada tique.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _com_descanso_correndo(self, email):
        user = create_user(
            email=email, weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(user)
        item = services.estado_do_treino(user).itens[0]
        services.record_load(user, item.exercise, Decimal("50"), set_number=1, reps=8)
        self.client.force_login(user)
        return user

    # ---------------------------------------------- modo treino

    def test_o_relogio_do_modo_treino_nao_esta_numa_regiao_viva(self):
        self._com_descanso_correndo("fala1@exemplo.com")

        html = self.client.get(reverse("workouts:now")).content.decode()

        self.assertIn("data-descanso-relogio", html)
        self.assertFalse(
            dentro_de_regiao_viva(html, "data-descanso-relogio"),
            "o relogio voltou para dentro de uma regiao viva",
        )

    def test_o_modo_treino_tem_um_aviso_proprio_para_o_leitor_de_tela(self):
        """A outra metade. Tirar a regiao viva sem por nada no lugar deixaria
        quem ouve a tela sem saber que o descanso comecou ou acabou."""
        self._com_descanso_correndo("fala2@exemplo.com")

        html = self.client.get(reverse("workouts:now")).content.decode()

        aviso = re.search(r"<p[^>]*data-descanso-aviso[^>]*>", html)
        self.assertIsNotNone(aviso, "o aviso do descanso sumiu")
        self.assertIn('aria-live="polite"', aviso.group(0))
        self.assertIn('role="status"', aviso.group(0))
        self.assertIn("vis-oculto", aviso.group(0))

    def test_o_javascript_do_modo_treino_fala_no_comeco_e_no_fim(self):
        """As duas falas, e so as duas.

        Uma chamada dentro do ramo que apenas decrementa devolveria o defeito
        inteiro sem mudar uma linha do HTML — por isso o teste le o corpo do
        tique, e nao apenas a existencia da funcao.
        """
        self._com_descanso_correndo("fala3@exemplo.com")

        html = self.client.get(reverse("workouts:now")).content.decode()

        self.assertIn('falar("Descanso de "', html)
        self.assertIn('falar("Descanso terminado, pode ir.")', html)
        tique = html[html.index("var tique = setInterval"):]
        tique = tique[: tique.index("}, 1000);")]
        # O ramo que ZERA, e so ele: de `if (restante <= 0) {` ate o `return;`
        # que o fecha. A primeira versao deste teste cortava a partir do
        # `restante <= 0` e seguia ate o fim do tique — ou seja, o "ramo do fim"
        # continha tambem o caminho que apenas decrementa, e a sabotagem que
        # punha `falar()` ali passou verde.
        inicio = tique.index("if (restante <= 0) {")
        ramo_do_fim = tique[inicio: tique.index("return;", inicio)]
        self.assertEqual(
            tique.count("falar("),
            ramo_do_fim.count("falar("),
            "voltou a falar no caminho que so decrementa o relogio",
        )

    # ---------------------------------------------- ficha

    def test_o_cronometro_da_ficha_nao_esta_numa_regiao_viva(self):
        self.client.force_login(create_user(email="fala4@exemplo.com"))

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn("data-timer-valor", html)
        self.assertFalse(
            dentro_de_regiao_viva(html, "data-timer-valor"),
            "o cronometro voltou para dentro de uma regiao viva",
        )

    def test_a_ficha_tem_um_aviso_proprio_para_o_leitor_de_tela(self):
        self.client.force_login(create_user(email="fala5@exemplo.com"))

        html = self.client.get(reverse("workouts:routine")).content.decode()

        aviso = re.search(r"<p[^>]*data-timer-aviso[^>]*>", html)
        self.assertIsNotNone(aviso)
        self.assertIn('aria-live="polite"', aviso.group(0))
        self.assertIn("vis-oculto", aviso.group(0))

    def test_o_cronometro_da_ficha_fala_ao_iniciar_e_ao_terminar(self):
        self.client.force_login(create_user(email="fala6@exemplo.com"))

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('falar("Descanso de " + porExtenso(total)', html)
        self.assertIn('falar("Descanso terminado, pode ir.")', html)


class ODesfazerSegueAUltimaSerieTests(TestCase):
    """O botao desfaz a serie que a pessoa acabou de anotar — de qualquer
    exercicio.

    Ele estava preso ao exercicio da TELA, e a tela anda sozinha: fechada a
    ultima serie de um exercicio, a vez ja passou e o botao sumia junto.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _pronto(self, email):
        user = create_user(email=email, weekdays=(timezone.localdate().weekday(),))
        services.sync_active_routine(user)
        self.client.force_login(user)
        return user, services.estado_do_treino(user)

    def _fechar(self, user, item):
        for numero in range(1, item.sets + 1):
            services.record_load(
                user, item.exercise, Decimal("50"), set_number=numero, reps=8
            )

    def _tela(self):
        return self.client.get(reverse("workouts:now")).content.decode()

    def _formulario(self, html):
        trecho = html[html.index('class="agora__desfazer"'):]
        return trecho[: trecho.index("</form>")]

    def test_com_o_exercicio_fechado_o_desfazer_continua_na_tela(self):
        user, estado = self._pronto("desf1@exemplo.com")
        primeiro = estado.itens[0]
        self._fechar(user, primeiro)

        html = self._tela()

        # A tela ja e a do exercicio SEGUINTE...
        self.assertNotEqual(services.estado_do_treino(user).atual, primeiro)
        # ...e o desfazer aponta para o que acabou de receber a serie.
        self.assertIn(
            'value="%d"' % primeiro.exercise_id, self._formulario(html)
        )

    def test_o_rotulo_diz_de_qual_exercicio_e_a_serie(self):
        """Desfazer as cegas uma serie de um exercicio que nem esta na tela
        seria pior do que nao ter botao."""
        user, estado = self._pronto("desf2@exemplo.com")
        primeiro = estado.itens[0]
        self._fechar(user, primeiro)

        botao = self._formulario(self._tela())

        self.assertIn("desfazer última série", botao)
        self.assertIn("de %s" % primeiro.exercise.name, botao)

    def test_no_meio_do_exercicio_o_rotulo_nao_repete_o_nome(self):
        """O controle do teste acima.

        Um rotulo que nomeasse o exercicio SEMPRE passaria la e encheria de
        ruido o caso comum, que e desfazer a serie do exercicio da tela.
        """
        user, estado = self._pronto("desf3@exemplo.com")
        primeiro = estado.itens[0]
        services.record_load(
            user, primeiro.exercise, Decimal("50"), set_number=1, reps=8
        )

        botao = self._formulario(self._tela())

        self.assertIn("desfazer última série", botao)
        self.assertNotIn("de %s" % primeiro.exercise.name, botao)

    def test_sem_nenhuma_serie_hoje_nao_ha_o_que_desfazer(self):
        """O controle negativo. Um botao que aparecesse sempre desfaria a
        serie de ontem no primeiro toque do dia."""
        self._pronto("desf4@exemplo.com")

        self.assertNotIn("agora__desfazer", self._tela())

    def test_carimbos_iguais_desempatam_pela_ordem_de_gravacao(self):
        """`auto_now_add` chama `timezone.now()` no Python, e no Windows o
        relogio tem granularidade de milissegundos: duas series gravadas na
        mesma janela recebem o MESMO `created_at`.

        Pego ao semear estado de QA — a quarta serie da puxada e a primeira da
        remada saíram com o microssegundo identico, e `max` devolvia a primeira
        da iteracao, que era a do exercicio ANTERIOR. Com o desfazer pendurado
        nisso, um empate apagaria a serie errada.
        """
        user, estado = self._pronto("empate@exemplo.com")
        primeiro, segundo = estado.itens[0], estado.itens[1]
        self._fechar(user, primeiro)
        services.record_load(
            user, segundo.exercise, Decimal("50"), set_number=1, reps=8
        )
        # Todo mundo com o mesmo carimbo, que e o caso que quebrava.
        instante = ExerciseLog.objects.filter(
            user=user, date=timezone.localdate()
        ).first().created_at
        ExerciseLog.objects.filter(user=user, date=timezone.localdate()).update(
            created_at=instante
        )

        ultimo = services.estado_do_treino(user).ultimo_log

        self.assertEqual(ultimo.exercise_id, segundo.exercise_id)
        self.assertEqual(ultimo.set_number, 1)

    def test_o_desfazer_do_exercicio_fechado_apaga_de_verdade(self):
        """Nao basta o botao existir e apontar certo: o POST precisa remover a
        serie e devolver a vez ao exercicio de onde ela saiu."""
        user, estado = self._pronto("desf5@exemplo.com")
        primeiro = estado.itens[0]
        self._fechar(user, primeiro)

        self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": primeiro.exercise_id, "acao": "desfazer"},
        )

        restantes = ExerciseLog.objects.filter(
            user=user, exercise=primeiro.exercise, date=timezone.localdate()
        ).count()
        self.assertEqual(restantes, primeiro.sets - 1)
        self.assertEqual(services.estado_do_treino(user).atual, primeiro)


class OTituloDizEmQueEstadoATelaEstaTests(TestCase):
    """O titulo e o nome da pagina na aba, na lista de apps da PWA e no anuncio
    do leitor de tela ao carregar. Fixo em "Treinando", ele afirmava que a
    pessoa estava treinando na tela que diz que o treino acabou.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _titulo(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        return re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()

    def test_em_treino_o_titulo_diz_treinando(self):
        user = create_user(
            email="tit1@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(user)
        self.client.force_login(user)

        self.assertEqual(self._titulo(), "Treinando · NutriPlan")

    def test_com_tudo_registrado_o_titulo_diz_concluido(self):
        user = create_user(
            email="tit2@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(user)
        for item in services.estado_do_treino(user).itens:
            for numero in range(1, item.sets + 1):
                services.record_load(
                    user, item.exercise, Decimal("50"), set_number=numero, reps=8
                )
        self.client.force_login(user)

        self.assertEqual(self._titulo(), "Treino concluído · NutriPlan")

    def test_no_dia_de_descanso_o_titulo_nao_diz_treinando(self):
        amanha = (timezone.localdate().weekday() + 1) % 7
        user = create_user(email="tit3@exemplo.com", weekdays=(amanha,))
        services.sync_active_routine(user)
        self.client.force_login(user)

        self.assertEqual(self._titulo(), "Modo treino · NutriPlan")


class APortaDaCorridaTests(TestCase):
    """A corrida continua dentro do treino, e deixou de ser o rodape dele.

    `ACorridaTemPortaTests` ja cobra que a porta EXISTA — e foi ela que pegou a
    primeira versao desta mudanca, que moveu o cartao para a coluna lateral e
    apagou a porta de quem ainda nao cadastrou dias de treino. Estes testes
    cobram a outra metade: onde ela fica, e que ela fique nos dois estados.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_porta_vem_antes_das_secoes_de_consulta(self):
        self.client.force_login(create_user(email="corrida1@exemplo.com"))

        html = self.client.get(reverse("workouts:routine")).content.decode()

        porta = html.index('href="/treino/corridas/"')
        for secao in ("Séries por músculo", "Como executar", "Dias de treino"):
            with self.subTest(secao=secao):
                self.assertLess(
                    porta,
                    html.index(secao),
                    "a porta da corrida voltou para baixo de '%s'" % secao,
                )

    def test_quem_ainda_nao_tem_rotina_tambem_alcanca_a_corrida(self):
        """O ramo que a primeira versao quebrou.

        Sem dias de treino nao ha ficha nem coluna lateral — e a corrida nao
        depende de ficha nenhuma para acontecer.
        """
        self.client.force_login(create_user(email="corrida2@exemplo.com", weekdays=()))

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertNotIn("split__aside", html)
        self.assertIn('href="/treino/corridas/"', html)

    def test_a_porta_e_uma_so(self):
        """Duas portas para a mesma tela e o comeco de duas que divergem."""
        self.client.force_login(create_user(email="corrida3@exemplo.com"))

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertEqual(html.count('href="/treino/corridas/"'), 1)
