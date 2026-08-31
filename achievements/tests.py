"""Testes das conquistas.

TODA data aqui é escolhida pelo teste, nunca lida do relógio. Três testes de
`workouts` acabaram de ser corrigidos por dependerem do dia da semana em que a
suíte rodava, e este arquivo nasce depois disso: `avaliar(user, hoje=...)`
recebe a data, e as séries são criadas com `date=` explícito. Um teste de
conquista que passa no sábado e quebra na terça seria a mesma cicatriz de novo,
num app cuja regra central é "dias seguidos".
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import TrainingDay
from workouts import services as treino_services
from workouts.models import Exercise, ExerciseLog
from workouts.tests import create_user

from . import services
from .models import UserAchievement
from .regras import POR_SLUG

#: Uma segunda-feira. Todas as contas deste arquivo partem dela.
SEGUNDA = date(2026, 8, 31)


class BaseDeConquistas(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="conquista@exemplo.com", weekdays=(0, 2, 4)):
        """Pessoa COM ficha ativa, e a ficha nao e detalhe de cenario.

        Sem `TrainingPlan` ativo, `plans/streaks.py` nao encontra dia previsto
        nenhum, todo dia conta como descanso cumprido e a ofensiva cresce
        sozinha ate o teto do historico. Quem termina o onboarding ganha ficha,
        entao um teste sem ela mede um estado que o produto nao produz.
        """
        user = create_user(email=email, weekdays=weekdays)
        treino_services.create_routine(user)
        return user

    def treinar(self, user, dia, exercicio=None, carga="60"):
        """Uma série num dia. É o que o projeto inteiro chama de "treinou":
        existe `ExerciseLog` naquela data."""
        exercicio = exercicio or Exercise.objects.filter(is_active=True).first()
        return ExerciseLog.objects.create(
            user=user, exercise=exercicio, date=dia,
            set_number=1, weight_kg=Decimal(carga), reps=10,
        )

    def slugs(self, user):
        return sorted(
            UserAchievement.objects.filter(user=user).values_list("slug", flat=True)
        )


class PrimeiroTreinoTests(BaseDeConquistas):
    def test_sem_treino_nenhum_nao_ha_conquista(self):
        """Conta nova não ganha nada — a tela de conquistas de quem chegou
        agora precisa estar honestamente vazia."""
        user = self.pessoa()

        services.avaliar(user, hoje=SEGUNDA)

        self.assertEqual(self.slugs(user), [])

    def test_a_primeira_serie_desbloqueia_o_primeiro_treino(self):
        user = self.pessoa()
        self.treinar(user, SEGUNDA)

        novas = services.avaliar(user, hoje=SEGUNDA)

        self.assertIn("primeiro-treino", [c.slug for c in novas])

    def test_avaliar_de_novo_nao_desbloqueia_de_novo(self):
        """Idempotência: registrar mais uma série no mesmo dia não pode fazer a
        conquista nascer duas vezes. É o caso que a fila offline produz sozinha
        quando reenvia um POST."""
        user = self.pessoa()
        self.treinar(user, SEGUNDA)
        services.avaliar(user, hoje=SEGUNDA)

        novas = services.avaliar(user, hoje=SEGUNDA)

        self.assertEqual(novas, [])
        self.assertEqual(
            UserAchievement.objects.filter(user=user, slug="primeiro-treino").count(), 1
        )


class LimiaresDeTreinoTests(BaseDeConquistas):
    def test_cinco_dias_distintos_desbloqueiam_cinco_treinos(self):
        user = self.pessoa()
        for n in range(5):
            self.treinar(user, SEGUNDA + timedelta(days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=4))

        self.assertIn("treinos-5", self.slugs(user))

    def test_varias_series_no_mesmo_dia_contam_um_dia_so(self):
        """Senão bastaria anotar oito séries numa terça para "treinar" oito
        dias — e o número da conquista discordaria da ofensiva, que conta dias
        distintos."""
        user = self.pessoa()
        exercicio = Exercise.objects.filter(is_active=True).first()
        for serie in range(1, 9):
            ExerciseLog.objects.create(
                user=user, exercise=exercicio, date=SEGUNDA,
                set_number=serie, weight_kg=Decimal("50"), reps=10,
            )

        services.avaliar(user, hoje=SEGUNDA)

        self.assertNotIn("treinos-5", self.slugs(user))

    def test_o_limiar_maior_nao_vem_antes_do_menor(self):
        user = self.pessoa()
        for n in range(10):
            self.treinar(user, SEGUNDA + timedelta(days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=9))
        ganhos = self.slugs(user)

        self.assertIn("treinos-10", ganhos)
        self.assertIn("treinos-5", ganhos)
        self.assertNotIn("treinos-25", ganhos)


class OfensivaTests(BaseDeConquistas):
    def test_tres_dias_seguidos_desbloqueiam_a_ofensiva_de_tres(self):
        """Dia sem treino previsto não quebra a sequência — é a regra que
        `plans/streaks.py` já aplicava, e aqui ela é reusada e não reescrita."""
        user = self.pessoa(weekdays=(0, 1, 2))
        for n in range(3):
            self.treinar(user, SEGUNDA + timedelta(days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=2))

        self.assertIn("ofensiva-3", self.slugs(user))

    def test_faltar_um_dia_previsto_zera_a_sequencia(self):
        """O que quebra a ofensiva e um dia PREVISTO sem treino.

        Nao e "poucos dias treinados": descanso conta como cumprido, entao uma
        pessoa que treina na segunda com previstos (0, 1, 2) chega ao domingo
        seguinte com sequencia longa sem treinar de novo. Isso e a definicao do
        produto, e a conquista segue ela em vez de inventar outra.
        """
        user = self.pessoa(weekdays=(0, 1, 2))
        self.treinar(user, SEGUNDA)

        # Quarta e dia previsto e ficou sem treino; terca tambem. A sequencia
        # morre na terca, antes de chegar aos tres.
        services.avaliar(user, hoje=SEGUNDA + timedelta(days=2))

        self.assertNotIn("ofensiva-3", self.slugs(user))

    def test_descanso_conta_e_isso_e_declarado(self):
        """Trava o comportamento que surpreende, para ele ser escolha e nao
        acidente: com previstos (0, 1, 2), treinar so na segunda ja da
        sequencia — quinta a domingo sao descanso cumprido."""
        user = self.pessoa(weekdays=(0, 1, 2))
        self.treinar(user, SEGUNDA)

        services.avaliar(user, hoje=SEGUNDA)

        self.assertIn("ofensiva-3", self.slugs(user))


class SemanaCompletaTests(BaseDeConquistas):
    def test_cumprir_todos_os_dias_previstos_desbloqueia_a_semana(self):
        user = self.pessoa(weekdays=(0, 2, 4))
        for n in (0, 2, 4):
            self.treinar(user, SEGUNDA + timedelta(days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=4))

        self.assertIn("semana-completa", self.slugs(user))

    def test_faltar_um_dia_previsto_nao_completa(self):
        user = self.pessoa(weekdays=(0, 2, 4))
        for n in (0, 2):
            self.treinar(user, SEGUNDA + timedelta(days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=4))

        self.assertNotIn("semana-completa", self.slugs(user))

    def test_dia_previsto_que_ainda_nao_chegou_nao_reprova(self):
        """Na quarta, a sexta ainda não aconteceu. A semana não está perdida —
        ela só ainda não fechou, e cobrar isso seria o contador punindo por
        alguém abrir o app no meio da semana."""
        user = self.pessoa(weekdays=(0, 2, 4))
        for n in (0, 2):
            self.treinar(user, SEGUNDA + timedelta(days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=2))

        self.assertNotIn("semana-completa", self.slugs(user))

    def test_duas_semanas_cumpridas_sao_duas_conquistas(self):
        """Repetível: a `chave` é a segunda-feira, então cada semana é uma
        ocorrência própria e a constraint não as confunde."""
        user = self.pessoa(weekdays=(0, 2))
        for semana in range(2):
            for n in (0, 2):
                self.treinar(user, SEGUNDA + timedelta(weeks=semana, days=n))

        services.avaliar(user, hoje=SEGUNDA + timedelta(weeks=1, days=2))

        self.assertEqual(
            UserAchievement.objects.filter(user=user, slug="semana-completa").count(), 2
        )


class RecordeTests(BaseDeConquistas):
    """O contrato do recorde, travado em teste: MAIOR CARGA REGISTRADA."""

    def test_a_estreia_num_exercicio_nao_e_recorde(self):
        """A primeira carga também é, tecnicamente, a maior. Chamar isso de
        recorde transformaria a conquista em confete de estreia."""
        user = self.pessoa()
        self.treinar(user, SEGUNDA, carga="60")

        services.avaliar(user, hoje=SEGUNDA)

        self.assertNotIn("novo-recorde", self.slugs(user))

    def test_superar_a_carga_anterior_e_recorde(self):
        user = self.pessoa()
        exercicio = Exercise.objects.filter(is_active=True).first()
        self.treinar(user, SEGUNDA, exercicio, carga="60")
        services.avaliar(user, hoje=SEGUNDA)
        self.treinar(user, SEGUNDA + timedelta(days=1), exercicio, carga="65")

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=1))

        self.assertIn("novo-recorde", self.slugs(user))

    def test_repetir_a_mesma_carga_nao_e_recorde(self):
        user = self.pessoa()
        exercicio = Exercise.objects.filter(is_active=True).first()
        self.treinar(user, SEGUNDA, exercicio, carga="60")
        self.treinar(user, SEGUNDA + timedelta(days=1), exercicio, carga="60")

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=1))

        self.assertNotIn("novo-recorde", self.slugs(user))

    def test_a_carga_nao_e_persistida_no_contexto(self):
        """Decisão de privacidade, e é o que permite o card sair sem número.

        A chave é `exercício:data`, e não `exercício:carga`, exatamente para o
        peso levantado não precisar existir aqui — o contexto pode acabar
        dentro de uma imagem que a pessoa manda para um grupo.
        """
        user = self.pessoa()
        exercicio = Exercise.objects.filter(is_active=True).first()
        self.treinar(user, SEGUNDA, exercicio, carga="60")
        self.treinar(user, SEGUNDA + timedelta(days=1), exercicio, carga="97.5")

        services.avaliar(user, hoje=SEGUNDA + timedelta(days=1))

        conquista = UserAchievement.objects.get(user=user, slug="novo-recorde")
        guardado = "%s %s" % (conquista.chave, conquista.contexto)
        self.assertNotIn("97", guardado)
        self.assertNotIn("60", guardado)
        self.assertEqual(set(conquista.contexto), {"exercicio"})


class UnicidadeTests(BaseDeConquistas):
    def test_a_trava_esta_no_banco_e_nao_so_no_codigo(self):
        """`get_or_create` sozinho não resolve corrida: dois pedidos passam
        pelo SELECT antes de qualquer INSERT. A constraint é o que decide."""
        user = self.pessoa()
        UserAchievement.objects.create(user=user, slug="primeiro-treino", chave="")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserAchievement.objects.create(
                    user=user, slug="primeiro-treino", chave=""
                )

    def test_a_mesma_conquista_de_pessoas_diferentes_convive(self):
        um = self.pessoa(email="um@exemplo.com")
        dois = self.pessoa(email="dois@exemplo.com")

        UserAchievement.objects.create(user=um, slug="primeiro-treino", chave="")
        UserAchievement.objects.create(user=dois, slug="primeiro-treino", chave="")

        self.assertEqual(UserAchievement.objects.count(), 2)

    def test_conquista_de_um_nao_aparece_para_o_outro(self):
        um = self.pessoa(email="um@exemplo.com")
        dois = self.pessoa(email="dois@exemplo.com")
        self.treinar(um, SEGUNDA)

        services.avaliar(um, hoje=SEGUNDA)

        self.assertEqual(self.slugs(dois), [])
        self.assertEqual(services.nao_vistas(dois), [])


class CatalogoTests(TestCase):
    """O catálogo é código, então o que se trava aqui é a coerência dele."""

    def test_todo_slug_e_unico(self):
        slugs = [regra.slug for regra in POR_SLUG.values()]

        self.assertEqual(len(slugs), len(set(slugs)))

    def test_toda_regra_tem_texto_para_a_tela(self):
        for slug, regra in POR_SLUG.items():
            with self.subTest(slug=slug):
                self.assertTrue(regra.titulo)
                self.assertTrue(regra.frase)
                self.assertTrue(regra.emoji)

    def test_nao_ha_conquista_de_dado_que_o_app_nao_tem(self):
        """Corrida, passos, medida corporal, sono e desafio não existem no
        NutriPlan. Uma conquista sobre eles seria uma promessa quebrada."""
        familias = {regra.familia for regra in POR_SLUG.values()}

        self.assertEqual(familias, {"treino", "ofensiva", "meta", "recorde"})


class AcessoTests(BaseDeConquistas):
    """Ninguém vê conquista de ninguém."""

    def test_anonimo_e_mandado_para_o_login(self):
        resposta = self.client.get(reverse("achievements:list"))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/entrar/", resposta["Location"])

    def test_a_tela_nao_aceita_id_de_usuario_por_parametro(self):
        """Não há IDOR possível porque não há identificador na rota: a tela
        lê `request.user` e nada mais. Este teste trava o desenho — se alguém
        acrescentar `?user=`, ele continua ignorando."""
        um = self.pessoa(email="um@exemplo.com")
        dois = self.pessoa(email="dois@exemplo.com")
        self.treinar(dois, SEGUNDA)
        services.avaliar(dois, hoje=SEGUNDA)

        self.client.force_login(um)
        html = self.client.get(
            reverse("achievements:list"), {"user": dois.pk, "user_id": dois.pk}
        ).content.decode()

        self.assertIn("Nenhuma ainda", html)

    def test_marcar_vistas_nao_alcanca_conquista_de_outro(self):
        um = self.pessoa(email="um@exemplo.com")
        dois = self.pessoa(email="dois@exemplo.com")
        self.treinar(dois, SEGUNDA)
        (conquista,) = [
            c for c in services.avaliar(dois, hoje=SEGUNDA) if c.slug == "primeiro-treino"
        ]

        self.client.force_login(um)
        self.client.post(reverse("achievements:marcar_vistas"), {"id": conquista.pk})

        conquista.refresh_from_db()
        self.assertIsNone(conquista.seen_at)

    def test_marcar_vistas_recusa_get(self):
        """Muda estado; GET não pode."""
        user = self.pessoa()
        self.client.force_login(user)

        resposta = self.client.get(reverse("achievements:marcar_vistas"))

        self.assertEqual(resposta.status_code, 405)


class AvisoTests(BaseDeConquistas):
    """O aviso aparece uma vez, e não volta no refresh."""

    def test_o_aviso_aparece_depois_de_registrar_serie(self):
        user = self.pessoa(weekdays=(0, 2, 4))
        self.client.force_login(user)
        exercicio = Exercise.objects.filter(is_active=True).first()

        self.client.post(
            reverse("workouts:record_load", args=[exercicio.pk]),
            {"weight_kg": "60", "set_number": 1, "reps": 10},
        )
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('class="conquista"', html)
        self.assertIn("Conquista desbloqueada", html)

    def test_depois_de_continuar_o_aviso_nao_volta(self):
        user = self.pessoa(weekdays=(0, 2, 4))
        self.client.force_login(user)
        exercicio = Exercise.objects.filter(is_active=True).first()
        self.client.post(
            reverse("workouts:record_load", args=[exercicio.pk]),
            {"weight_kg": "60", "set_number": 1, "reps": 10},
        )
        ids = list(
            UserAchievement.objects.filter(user=user).values_list("pk", flat=True)
        )

        self.client.post(reverse("achievements:marcar_vistas"), {"id": ids})
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertNotIn('class="conquista"', html)

    def test_sem_nada_pendente_o_aviso_nao_custa_consulta(self):
        """O processador de contexto roda em TODO request autenticado. Ele só
        toca no banco quando a sessão diz que há algo — senão seria um imposto
        cobrado o dia inteiro por um evento semanal."""
        user = self.pessoa()
        self.client.force_login(user)
        # Aquece sessão e plano para a contagem medir só o painel.
        self.client.get(reverse("workouts:routine"))

        from achievements.context_processors import conquistas_pendentes

        class PedidoFalso:
            pass

        pedido = PedidoFalso()
        pedido.user = user
        pedido.session = {}
        with self.assertNumQueries(0):
            self.assertEqual(conquistas_pendentes(pedido), {})


class PrivacidadeDoCardTests(BaseDeConquistas):
    """Nada pessoal entra num card que a pessoa manda para um grupo.

    O card é desenhado no navegador a partir de atributos `data-` escritos pelo
    servidor. Então o teste mira exatamente esses atributos: se um dado sensível
    não está lá, ele não tem como ser desenhado.
    """

    def _atributos_de_card(self, html):
        trechos = []
        for pedaco in html.split("data-conquista-share")[1:]:
            trechos.append(pedaco.split(">", 1)[0])
        return " ".join(trechos)

    def test_o_card_nao_carrega_email_nem_nome(self):
        user = self.pessoa(email="segredo.pessoal@exemplo.com")
        self.treinar(user, SEGUNDA)
        services.avaliar(user, hoje=SEGUNDA)
        self.client.force_login(user)

        html = self.client.get(reverse("achievements:list")).content.decode()
        atributos = self._atributos_de_card(html)

        self.assertTrue(atributos, "a tela deveria oferecer compartilhamento")
        self.assertNotIn("segredo.pessoal", atributos)
        self.assertNotIn("@exemplo.com", atributos)

    def test_o_card_nao_carrega_peso_corporal_nem_nascimento(self):
        """`Profile` guarda data de nascimento e `WeightEntry` guarda peso. Os
        dois alimentam o cálculo e nenhum dos dois tem o que fazer numa imagem
        pública."""
        user = self.pessoa()
        self.treinar(user, SEGUNDA)
        services.avaliar(user, hoje=SEGUNDA)
        self.client.force_login(user)

        html = self.client.get(reverse("achievements:list")).content.decode()
        atributos = self._atributos_de_card(html)

        self.assertNotIn("82.4", atributos)   # o peso de `create_user`
        self.assertNotIn("82,4", atributos)
        self.assertNotIn("1995", atributos)   # o ano de nascimento

    def test_o_card_de_recorde_nao_carrega_a_carga(self):
        user = self.pessoa()
        exercicio = Exercise.objects.filter(is_active=True).first()
        self.treinar(user, SEGUNDA, exercicio, carga="60")
        self.treinar(user, SEGUNDA + timedelta(days=1), exercicio, carga="97.5")
        services.avaliar(user, hoje=SEGUNDA + timedelta(days=1))
        self.client.force_login(user)

        html = self.client.get(reverse("achievements:list")).content.decode()
        atributos = self._atributos_de_card(html)

        self.assertIn(exercicio.name, atributos)
        self.assertNotIn("97", atributos)
        self.assertNotIn("60", atributos)
