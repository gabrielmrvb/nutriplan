"""Conquistas viraram um bloco do Progresso, e a página continua existindo.

A página isolada tinha pouco para justificar uma ferramenta própria no cartão de
Áreas: as ganhas, as próximas e três números. A pergunta que ela responde —
"como estou evoluindo" — é a do Progresso.

O que este arquivo guarda:

  - o bloco aparece no Progresso, nos estados que importam (nenhuma, uma,
    várias) e mostra a próxima com progresso REAL;
  - `Conquistas` saiu do cartão de Áreas, e as outras ferramentas ficaram;
  - `/conquistas/` NÃO quebrou — continua respondendo, e a porta para ela está
    no próprio bloco;
  - a regra do que entra em "próxima" mora num lugar só: `services.a_caminho`.
    A tela completa e o bloco compacto leem a MESMA lista, e é isso que impede
    as duas de divergirem na primeira mudança de catálogo.
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import (
    ActivityLevel,
    Goal,
    ONBOARDING_DONE,
    Profile,
    Sex,
    TrainingDay,
    WeightEntry,
)
from achievements import services
from achievements.models import UserAchievement
from workouts.models import Exercise, ExerciseLog

User = get_user_model()


def pessoa(email="conquista@exemplo.com"):
    user = User.objects.create_user(email=email, password="x8Kd2Lm9Qp4z")
    Profile.objects.create(
        user=user,
        sex=Sex.MALE,
        birth_date=date(1995, 4, 12),
        height_cm=178,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.BULK,
        wake_time=time(7, 0),
        sleep_time=time(23, 0),
        onboarding_step=ONBOARDING_DONE,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal("82.4"))
    TrainingDay.objects.create(
        user=user, weekday=0, start_time=time(19, 0), duration_min=60
    )
    return user


class OBlocoDeConquistasNoProgressoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = pessoa()
        self.client.force_login(self.user)
        self.exercicio = Exercise.objects.filter(is_active=True).first()

    def progresso(self):
        return self.client.get(reverse("plans:history")).content.decode()

    def _treinar(self, dias):
        """Séries em dias distintos — é assim que as conquistas de treino contam."""
        from django.utils import timezone

        hoje = timezone.localdate()
        for i in range(dias):
            ExerciseLog.objects.create(
                user=self.user,
                exercise=self.exercicio,
                date=hoje - timezone.timedelta(days=i),
                set_number=1,
                weight_kg=Decimal("40"),
                reps=10,
            )

    def test_com_zero_conquistas_o_bloco_mostra_o_que_falta_para_a_primeira(self):
        """Não sumir é a decisão: para quem não tem nenhuma, a única coisa útil
        de dizer é o que está mais perto de acontecer."""
        html = self.progresso()

        self.assertIn("<h2>Conquistas</h2>", html)
        self.assertIn("Desbloqueadas", html)

    def test_com_UMA_conquista_o_bloco_conta_uma(self):
        """`avaliar` explícito, e a chamada é o próprio contrato.

        `resumo` NÃO desbloqueia: quem faz isso é a página de conquistas, e a
        decisão está medida — chamar `avaliar` no Progresso levava a tela de 15
        para 50 consultas, com o número crescendo junto com o histórico. O
        bloco LÊ o que já está gravado.
        """
        self._treinar(1)
        services.avaliar(self.user)

        html = self.progresso()

        self.assertIn("<h2>Conquistas</h2>", html)
        total, recente, _proxima = services.resumo(self.user)
        self.assertGreaterEqual(total, 1)
        self.assertIsNotNone(recente)

    def test_com_VARIAS_o_total_acompanha(self):
        self._treinar(6)
        services.avaliar(self.user)

        total, _recente, _proxima = services.resumo(self.user)

        self.assertGreaterEqual(
            total, 2, "seis dias de treino deveriam ter fechado mais de uma"
        )

    def test_a_proxima_tem_progresso_REAL_e_nunca_uma_caixa_vazia(self):
        """A decisão que impede a parede de medalhas cinzentas: só entra o que
        dá para medir. Uma conquista sem `alvo` não vira "0 de 1"."""
        self._treinar(2)

        _total, _recente, proxima = services.resumo(self.user)

        self.assertIsNotNone(proxima)
        self.assertGreater(proxima["alvo"], 0)
        # `atual` PODE passar do alvo, e isso não é defeito: a ofensiva mede
        # dias corridos e uma conquista pode continuar trancada por outra
        # condição. O que o bloco não pode mostrar é uma barra sem escala —
        # por isso a régua é o `pct`, que já vem limitado a 100.
        self.assertGreaterEqual(proxima["pct"], 0)
        self.assertLessEqual(proxima["pct"], 100)

    def test_o_bloco_leva_para_a_pagina_completa(self):
        html = self.progresso()

        self.assertIn(reverse("achievements:list"), html)

    def test_a_regra_da_proxima_e_a_MESMA_nas_duas_telas(self):
        """Sem isto, o bloco e a página poderiam discordar sobre o que está a
        caminho — e discordar sobre conquista é o app dizendo duas coisas."""
        self._treinar(3)
        # `avaliar` ANTES de ler os conquistados: `resumo` chama por conta
        # própria, e comparar as duas listas sem isso compara estados
        # diferentes do banco — foi o que este teste acusou na primeira versão.
        services.avaliar(self.user)
        dados = services.reunir(self.user)
        conquistados = set(
            UserAchievement.objects.filter(user=self.user).values_list(
                "slug", flat=True
            )
        )

        lista = services.a_caminho(dados, conquistados)
        _total, _recente, proxima = services.resumo(self.user)

        self.assertTrue(lista)
        self.assertEqual(proxima["regra"].slug, lista[0]["regra"].slug)


class AConquistasSaiuDeAreasSemQuebrarNadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = pessoa(email="areas-conquista@exemplo.com")
        self.client.force_login(self.user)

    def test_o_cartao_de_conquistas_saiu_de_areas(self):
        html = self.client.get(reverse("areas")).content.decode()

        self.assertNotIn('modulo__nome">Conquistas', html)

    def test_as_outras_ferramentas_continuam_em_areas(self):
        """Controle positivo: tirar Conquistas não pode ter esvaziado a seção."""
        html = self.client.get(reverse("areas")).content.decode()

        self.assertIn('modulo__nome">Lista de compras', html)
        self.assertIn('modulo__nome">Perfil', html)

    def test_a_rota_antiga_continua_respondendo(self):
        """"A rota `/conquistas/` não deve quebrar." Ela segue como detalhe
        secundário, alcançada pelo bloco do Progresso."""
        resposta = self.client.get(reverse("achievements:list"))

        self.assertEqual(resposta.status_code, 200)

    def test_areas_continua_com_os_pilares_e_as_ferramentas(self):
        """Corrida, Hidratação, Lista de compras e Perfil continuam lá — é o
        que a campanha exige de Áreas."""
        html = self.client.get(reverse("areas")).content.decode()

        for destino in ("/treino/corridas/", "/hidratacao/", "/conta/perfil/"):
            with self.subTest(destino=destino):
                self.assertIn(destino, html)
