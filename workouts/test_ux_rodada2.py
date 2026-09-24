# -*- coding: utf-8 -*-
"""Os atritos do treino que a rodada 2 de experiência deixou (24/09/2026).

Dois itens, e os dois são sobre o app dizer a verdade do que aconteceu:

**Um clique para treinar.** O CTA do painel abria a FICHA — decisão de
22/09/2026, escrita no template: "o fluxo pulava a etapa em que a pessoa
decide". A rodada 2 mediu o outro lado: quem já decidiu paga dois toques
toda vez, e o segundo é numa tela que ela não vai ler. O dono reverteu: o
botão leva à EXECUÇÃO, e "Ver ficha" — que já existia logo abaixo — continua
sendo a porta de quem quer conferir antes. O texto diz em qual dos dois
mundos a pessoa está: "Começar treino" sem série hoje, "Continuar treino
(3/8)" com o treino em andamento.

**O placar diz o treino, não os registros.** "1 min entre o primeiro e o
último registro" descrevia o banco, não a academia — e quem encerrou o
treino às 19h40 depois de anotar a última série às 19h05 via 35 minutos a
menos do que passou lá. Com "Encerrar treino" existe um fim de verdade
(`EscolhaDeTreino.encerrado_em`), e a duração passa a ser dele até a
primeira série. E o placar conta: "5 de 8 exercícios feitos", com os
pendentes na ordem da ficha — a lista já estava na ordem certa, o que
faltava era o número que a torna legível.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import EscolhaDeTreino, ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class UmCliqueParaTreinarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="clique@exemplo.com", weekdays=dias_incluindo_hoje(4))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        self.sessao = services.sessao_do_dia(plano, timezone.localdate())

    def _cta(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        casou = re.search(
            r'<a[^>]*data-hoje-cta[^>]*>(.*?)</a>', corpo, re.S
        )
        self.assertIsNotNone(casou, "o CTA de hoje sumiu do painel")
        tag = corpo[casou.start():casou.end()]
        href = re.search(r'href="([^"]+)"', tag).group(1)
        # O TEXTO VISÍVEL: o rótulo embrulha os números em `.num`
        # (`tabular-nums`, a régua do CLAUDE.md), e comparar o HTML cru
        # mediria a marcação em vez da frase.
        return href, " ".join(re.sub(r"<[^>]+>", " ", casou.group(1)).split())

    def test_sem_serie_hoje_o_botao_leva_a_execucao_e_diz_comecar(self):
        href, texto = self._cta()
        self.assertEqual(href, reverse("workouts:now"))
        self.assertEqual(texto, "Começar treino")

    def test_com_treino_em_andamento_o_botao_diz_continuar_com_a_conta(self):
        item = self.sessao.exercises.first()
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=item.exercise, date=timezone.localdate(),
            set_number=1, weight_kg=Decimal("40.00"), reps=10,
        )
        href, texto = self._cta()
        self.assertEqual(href, reverse("workouts:now"))
        self.assertRegex(texto, r"^Continuar treino \( ?1 de \d+ ?\)$")

    def test_a_ficha_continua_tendo_porta_propria(self):
        """"Ver ficha" é a tela de preparação, e não some: o que mudou foi
        qual dos dois é o botão principal."""
        html = self.client.get(reverse("workouts:routine")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertIn(reverse("workouts:ficha", args=[self.sessao.pk]), corpo)
        self.assertIn("Ver ficha", corpo)

    def test_sabotagem_o_botao_nao_aponta_mais_para_a_ficha(self):
        """A prova de que a mudança está no lugar certo: o `href` do CTA não
        pode ser a ficha — era exatamente o que ele era."""
        href, _ = self._cta()
        self.assertNotEqual(href, reverse("workouts:ficha", args=[self.sessao.pk]))


class OPlacarDizODiaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="placar@exemplo.com", weekdays=dias_incluindo_hoje(4))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        self.sessao = services.sessao_do_dia(plano, timezone.localdate())
        self.hoje = timezone.localdate()
        # A OPÇÃO DO DIA, e não `exercises.all()`: a letra tem até duas
        # opções e a execução só conhece a escolhida. Somar as duas fazia o
        # teste comparar 16 com os 8 que a tela mostra.
        opcao = services.opcao_do_dia(self.pessoa, self.sessao, self.hoje)
        self.itens = list(self.sessao.da_opcao(opcao))

    def _registrar(self, quantos, *, atras_min=40):
        agora = timezone.now()
        for n, item in enumerate(self.itens[:quantos]):
            log = ExerciseLog.objects.create(
                user=self.pessoa, exercise=item.exercise, date=self.hoje,
                set_number=1, weight_kg=Decimal("40.00"), reps=10,
            )
            ExerciseLog.objects.filter(pk=log.pk).update(
                created_at=agora - timedelta(minutes=atras_min - n)
            )

    def _estado(self):
        return services.estado_do_treino(self.pessoa)

    def test_a_duracao_vai_da_primeira_serie_ao_encerrar(self):
        """O fim é o "Encerrar treino", e não a última anotação: quem anota a
        última série e ainda faz o alongamento passou aquele tempo lá."""
        self._registrar(2, atras_min=50)
        escolha = EscolhaDeTreino.objects.get(user=self.pessoa, date=self.hoje)
        escolha.encerrado_em = timezone.now()
        escolha.save(update_fields=["encerrado_em"])
        estado = self._estado()
        self.assertGreaterEqual(estado.minutos_do_treino, 49)
        self.assertLessEqual(estado.minutos_do_treino, 51)

    def test_sem_encerrar_a_duracao_continua_sendo_entre_registros(self):
        """Quem não tocou "Encerrar" não tem fim medido, e o app não inventa
        um: a conta volta a ser o intervalo entre a primeira e a última
        anotação, que é o que o banco sabe."""
        self._registrar(3, atras_min=20)
        estado = self._estado()
        self.assertEqual(estado.minutos_do_treino, estado.minutos_entre_registros)
        self.assertGreater(estado.minutos_do_treino, 0)

    def test_o_placar_conta_quantos_exercicios_foram_feitos(self):
        self._registrar(2)
        estado = self._estado()
        self.assertEqual(estado.exercicios_feitos, 2)
        self.assertEqual(estado.exercicios_do_dia, len(self.itens))

    def test_os_pendentes_saem_na_ordem_da_ficha(self):
        self._registrar(2)
        estado = self._estado()
        self.assertEqual(
            [i.exercise_id for i in estado.pulados],
            [i.exercise_id for i in self.itens[2:]],
        )

    def test_a_tela_do_placar_escreve_a_conta_e_a_duracao(self):
        self._registrar(2, atras_min=50)
        escolha = EscolhaDeTreino.objects.get(user=self.pessoa, date=self.hoje)
        escolha.encerrado_em = timezone.now()
        escolha.save(update_fields=["encerrado_em"])
        html = self.client.get(reverse("workouts:now")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        texto = " ".join(re.sub(r"<[^>]+>", " ", corpo).split())
        self.assertIn("2 de %d exercícios" % len(self.itens), texto)
        self.assertIn("de treino", texto)
        self.assertNotIn("entre o primeiro e o último registro", texto)

    def test_sabotagem_mudar_o_encerrado_muda_a_duracao(self):
        self._registrar(2, atras_min=50)
        escolha = EscolhaDeTreino.objects.get(user=self.pessoa, date=self.hoje)
        escolha.encerrado_em = timezone.now()
        escolha.save(update_fields=["encerrado_em"])
        antes = self._estado().minutos_do_treino
        escolha.encerrado_em = timezone.now() + timedelta(minutes=20)
        escolha.save(update_fields=["encerrado_em"])
        self.assertEqual(self._estado().minutos_do_treino, antes + 20)
