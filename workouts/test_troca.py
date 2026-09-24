""""OUTRAS FORMAS" (17/09/2026): a troca por exercício é a interação principal
da ficha — a pessoa não escolhe mais entre opção 1 e 2; escolhe COMO fazer
cada movimento.

`TrocaDeExercicio(user, original, substituto)` é customização POR EXERCÍCIO:
vale em toda letra, toda semana e toda opção em que o original apareça, e
NÃO toca em `SessionExercise` nem em `customized_at` — a ficha continua
retrato, a rotação continua, a conferência do catálogo não a enxerga. A
aplicação é em memória (`services.aplicar_trocas`), com a MESMA dose:
trocar não altera séries nem volume. O registro vai para o exercício FEITO;
a leitura mostra "no lugar de <original>" com o histórico do original.
"""
from datetime import date, timedelta
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import DuracaoTreino, Equipamento, TrainingDay
from plans.tests import create_complete_user
from workouts import services
from workouts.models import Equipment, Exercise, ExerciseLog, SessionExercise, TrocaDeExercicio
from workouts.test_recorde_na_hora import CONSULTAS_DO_POST_SEM_RECORDE
from workouts.tests import sem_scripts

SEGUNDA = date(2026, 9, 14)


def _congelar(dia):
    patcher = mock.patch("django.utils.timezone.localdate", return_value=dia)
    patcher.start()
    return patcher


def _pessoa(email, dias=5, **perfil):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO, **perfil,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class _ComFicha(TestCase):
    """Intermediário, 5 dias, abc2, "completa", segunda 14/09 (A, opção 1)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.stop)
        self.user = _pessoa("troca-%s@exemplo.com" % self._testMethodName[:30])
        self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)
        self.hoje = services.sessao_do_dia(self.plan, SEGUNDA)
        self.opcao = services.opcao_do_dia(self.user, self.hoje, SEGUNDA)
        self.itens = self.hoje.da_opcao(self.opcao)
        self.supino = Exercise.objects.get(name="Supino reto com barra")
        self.declinado = Exercise.objects.get(name="Supino declinado com halteres")
        self.assertIn(self.supino.pk, {i.exercise_id for i in self.itens}, "o dourado põe o supino reto na A de segunda")

    def _trocar(self, original=None, substituto=None):
        return services.registrar_troca(self.user, original or self.supino, substituto or self.declinado)

    def _ficha(self):
        return sem_scripts(self.client.get(reverse("workouts:ficha", args=[self.hoje.pk])).content.decode())

    def _serie(self, exercicio, op_id, peso="40"):
        return self.client.post(reverse("workouts:record_set"), {
            "exercise_id": exercicio.pk, "weight_kg": peso, "reps": "8", "op_id": op_id,
            "dia": SEGUNDA.isoformat(), "sessao": self.hoje.pk, "opcao": self.opcao, "versao": "completo",
        })


class AAplicacaoDaTrocaTests(_ComFicha):
    def test_a_troca_veste_a_ficha_a_execucao_e_a_leitura_com_a_mesma_dose(self):
        """A linha do original passa a apontar para o substituto — na ficha,
        na execução e na leitura —, com séries, faixa e descanso IGUAIS:
        trocar não altera o volume da sessão (diferença 0, dentro do ±1)."""
        linha = next(i for i in self.itens if i.exercise_id == self.supino.pk)
        dose = (linha.sets, linha.rep_min, linha.rep_max, linha.rest_seconds)
        volume_antes = sum(i.sets for i in self.itens)
        self._trocar()
        html = self._ficha()
        self.assertIn(self.declinado.name, html)
        self.assertNotIn(self.supino.name, html)
        estado = services.estado_do_treino(self.user)
        item = next(i for i in estado.itens if i.exercise_id == self.declinado.pk)
        self.assertEqual((item.sets, item.rep_min, item.rep_max, item.rest_seconds), dose)
        self.assertEqual(item.original, self.supino)
        self.assertEqual(sum(i.sets for i in estado.itens), volume_antes)
        self.assertFalse(any(i.exercise_id == self.supino.pk for i in estado.itens))
        agora = sem_scripts(self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.declinado.pk).content.decode())
        self.assertIn(self.declinado.name, agora)
        leitura = self.client.get(reverse("workouts:exercicio", args=[self.declinado.pk]))
        self.assertEqual(leitura.status_code, 200)
        self.assertContains(leitura, "No lugar de %s" % self.supino.name)
        # O link velho para o original na execução é 404, como todo link velho.
        self.assertEqual(self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.supino.pk).status_code, 404)

    def test_a_troca_vale_em_toda_letra_e_semana_em_que_o_original_cai(self):
        """Customização POR EXERCÍCIO: a mesma troca veste a linha de B onde
        o original também estivesse, e a ficha de A duas semanas depois
        (quarta 30/09, posição 12, opção 1 de novo) continua trocada."""
        linha_b = next(s for s in self.plan.sessions.all() if s.label == "B")
        SessionExercise.objects.create(
            session=linha_b, exercise=self.supino, sets=3, rep_min=8, rep_max=12, rest_seconds=80, order=99, opcao=1,
        )
        self._trocar()
        linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))
        with self.assertNumQueries(1):
            services.aplicar_trocas(self.user, linhas)
        trocadas = [i for s in linhas for i in s.exercises.all() if getattr(i, "original", None) is not None]
        self.assertEqual({i.session.label for i in trocadas}, {"A", "B"})
        self.assertTrue(all(i.exercise_id == self.declinado.pk for i in trocadas))
        self.relogio.stop()
        self.relogio = _congelar(SEGUNDA + timedelta(days=16))
        self.addCleanup(self.relogio.stop)
        sessao = services.sessao_do_dia(self.plan, SEGUNDA + timedelta(days=16))
        self.assertEqual(sessao.label, "A")
        html = sem_scripts(self.client.get(reverse("workouts:ficha", args=[sessao.pk])).content.decode())
        self.assertIn(self.declinado.name, html)
        self.assertNotIn(self.supino.name, html)

    def test_a_serie_vai_para_o_substituto_e_conta_na_ficha_no_painel_e_na_execucao(self):
        """`ExerciseLog` é do exercício FEITO. A linha do original responde
        pelo substituto na prescrição de hoje (mesma consulta), então a
        ficha diz 1/4, o painel conta o exercício e a execução continua nele."""
        self._trocar()
        resposta = self._serie(self.declinado, "op-1")
        self.assertEqual(resposta.status_code, 302, resposta.content[:200])
        self.assertEqual(ExerciseLog.objects.filter(user=self.user, exercise=self.declinado).count(), 1)
        self.assertFalse(ExerciseLog.objects.filter(user=self.user, exercise=self.supino).exists())
        self.assertEqual(services.series_de_hoje(self.user, self.declinado)[0], 1)
        self.assertEqual(services.prescricao_de_hoje(self.user, self.declinado.pk), 4)
        self.assertTrue(services.serie_pendente(self.user, self.declinado.pk))
        html = self._ficha()
        self.assertIn("1/4", html)
        painel = self.client.get(reverse("workouts:routine"))
        self.assertEqual(painel.context["hoje"].feitos_hoje, 1, "o painel conta o exercício feito no substituto")
        # O CTA do painel LÊ esse contador (rodada 2, 24/09/2026): com uma
        # série no substituto ele diz "Continuar treino (1 de N)" e leva à
        # execução. A asserção antiga era o texto do link da ficha, que não
        # dependia do que este teste mede.
        self.assertContains(painel, "Continuar treino")

    def test_o_post_da_serie_nao_paga_uma_consulta_a_mais_pela_troca(self):
        """O orçamento do POST é 20; a linha do original responde pelo
        substituto por JOIN, na consulta que já existia."""
        self._trocar()
        self._serie(self.declinado, "op-a", "60")
        with CaptureQueriesContext(connection) as consultas:
            self._serie(self.declinado, "op-b", "60")
        self.assertLessEqual(len(consultas), CONSULTAS_DO_POST_SEM_RECORDE, "\n".join(c["sql"][:90] for c in consultas))

    def test_desfazer_volta_ao_original_e_o_historico_do_substituto_fica(self):
        self._trocar()
        self._serie(self.declinado, "op-1")
        self.assertTrue(services.desfazer_troca(self.user, self.supino))
        self.assertFalse(services.desfazer_troca(self.user, self.supino), "desfazer o que não existe é nada")
        html = self._ficha()
        self.assertIn(self.supino.name, html)
        self.assertNotIn(self.declinado.name, html)
        self.assertEqual(ExerciseLog.objects.filter(user=self.user, exercise=self.declinado).count(), 1)
        leitura = self.client.get(reverse("workouts:exercicio", args=[self.supino.pk]))
        self.assertNotContains(leitura, "No lugar de")

    def test_a_leitura_do_substituto_mostra_o_historico_do_original(self):
        """Trocar não apaga o que foi feito: as séries do original ficam
        visíveis na leitura do substituto, e o formulário troca a partir do
        ORIGINAL (estado absoluto), nunca em cadeia."""
        ExerciseLog.objects.create(user=self.user, exercise=self.supino, date=SEGUNDA - timedelta(days=7), set_number=1, weight_kg=70, reps=8)
        self._trocar()
        leitura = self.client.get(reverse("workouts:exercicio", args=[self.declinado.pk]) + "?de=ficha&sessao=%d" % self.hoje.pk)
        self.assertContains(leitura, "No lugar de %s" % self.supino.name)
        self.assertContains(leitura, "07/09")
        self.assertContains(leitura, 'name="original" value="%d"' % self.supino.pk)
        self.assertContains(leitura, 'name="desfazer" value="1"')
        self.assertContains(leitura, "← Ficha")

    def test_a_leitura_diz_no_lugar_de_mesmo_quando_o_substituto_e_linha_crua_da_outra_opcao(self):
        """Ensaio da prova em produção (17/09): trocar uma pressão de peito
        da opção 2 por uma que já é linha CRUA da opção 1 da mesma letra —
        a leitura pegava a linha crua (que vem antes) e perdia o "No lugar
        de". Sabotagem medida: olhar só a primeira linha por sessão deixa
        este teste vermelho."""
        outra = next(k for k in self.hoje.opcoes if k != self.opcao)
        de_hoje = {i.exercise_id for i in self.itens}
        original = next(
            i.exercise for i in self.hoje.da_opcao(outra)
            if i.exercise.padrao == self.supino.padrao and i.exercise.muscle_group == self.supino.muscle_group
            and i.exercise_id not in de_hoje
        )
        substituto = next(
            i.exercise for i in self.itens
            if i.exercise.padrao == original.padrao and i.exercise.muscle_group == original.muscle_group
            and i.exercise_id not in {x.exercise_id for x in self.hoje.da_opcao(outra)}
        )
        services.registrar_troca(self.user, original, substituto)
        leitura = self.client.get(reverse("workouts:exercicio", args=[substituto.pk]))
        self.assertContains(leitura, "No lugar de %s" % original.name)
        self.assertContains(leitura, 'name="original" value="%d"' % original.pk)

    def test_a_troca_nao_remonta_nem_marca_a_ficha_como_ajustada(self):
        gravadas = list(SessionExercise.objects.filter(session__plan=self.plan).order_by("pk").values_list("exercise_id", "sets"))
        self._trocar()
        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.customized_at)
        self.assertFalse(services.rotina_invalida(self.plan, self.user))
        self.assertFalse(services.rotina_desatualizada(self.plan, self.user))
        self.assertEqual(list(SessionExercise.objects.filter(session__plan=self.plan).order_by("pk").values_list("exercise_id", "sets")), gravadas)

    def test_o_banco_garante_uma_troca_por_original_e_recusa_trocar_por_si_mesmo(self):
        self._trocar()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TrocaDeExercicio.objects.create(user=self.user, original=self.supino, substituto=self.declinado)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TrocaDeExercicio.objects.create(user=self.user, original=self.declinado, substituto=self.declinado)
        # Trocar de novo a partir do original ATUALIZA a mesma linha.
        outra = Exercise.objects.get(name="Flexão de braço com pés elevados")
        self._trocar(substituto=outra)
        self.assertEqual(list(TrocaDeExercicio.objects.filter(user=self.user).values_list("substituto__name", flat=True)), [outra.name])


class AsAlternativasTests(_ComFicha):
    def test_as_alternativas_sao_do_mesmo_padrao_e_grupo_no_equipamento_e_fora_da_sessao(self):
        """Para o supino reto com barra em "completa": as pressões de peito
        ativas que NÃO estão na sessão A — os dois de 17/09 (declinado com
        halteres, flexão com pés elevados), o mais próximo em equipamento
        primeiro. Nada de outro padrão ou grupo, nada do que já está lá."""
        na_sessao = {i.exercise_id for i in self.itens}
        alternativas = services.alternativas_de(self.user, self.supino, na_sessao)
        nomes = [e.name for e in alternativas]
        # Fora da MESMA lista (a opção de hoje): a pressão de peito da outra
        # opção também é forma válida — não é duplicata no mesmo treino.
        self.assertIn("Supino declinado com halteres", nomes)
        self.assertIn("Flexão de braço com pés elevados", nomes)
        self.assertEqual(alternativas[0].equipment, Equipment.DUMBBELL, "barra troca por halteres antes de peso do corpo")
        self.assertEqual(nomes.index("Supino declinado com halteres") < nomes.index("Flexão de braço com pés elevados"), True)
        self.assertTrue(all(e.padrao == self.supino.padrao and e.muscle_group == self.supino.muscle_group for e in alternativas))
        self.assertFalse({e.pk for e in alternativas} & na_sessao)
        self.assertNotIn(self.supino.pk, {e.pk for e in alternativas})

    def test_fora_do_equipamento_nao_aparece_e_o_post_recusa(self):
        """Quem treina na academia básica não recebe barra como alternativa,
        e o POST com uma barra é recusado sem gravar nada."""
        self.user.profile.equipamento = Equipamento.BASICA
        self.user.profile.save(update_fields=["equipamento"])
        self.user = type(self.user).objects.get(pk=self.user.pk)
        plano, _ = services.sync_active_routine(self.user)
        self.client.force_login(self.user)
        inclinado = Exercise.objects.get(name="Supino inclinado com halteres")
        self.assertTrue(SessionExercise.objects.filter(session__plan=plano, exercise=inclinado).exists())
        alternativas = services.alternativas_de(self.user, inclinado)
        self.assertFalse(any(e.equipment == Equipment.BARBELL for e in alternativas))
        resposta = self.client.post(reverse("workouts:trocar"), {"original": inclinado.pk, "substituto": self.supino.pk})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(TrocaDeExercicio.objects.filter(user=self.user).exists())

    def test_o_post_recusa_substituto_de_outro_movimento_e_original_fora_da_ficha(self):
        rosca = Exercise.objects.get(name="Rosca direta com barra")
        self.client.post(reverse("workouts:trocar"), {"original": self.supino.pk, "substituto": rosca.pk})
        self.assertFalse(TrocaDeExercicio.objects.exists())
        with self.assertRaises(services.TrocaInvalida):
            services.registrar_troca(self.user, self.declinado, self.supino)  # o declinado não está na ficha
        self.assertEqual(self.client.post(reverse("workouts:trocar"), {"original": "x", "substituto": self.declinado.pk}).status_code, 404)
        self.assertEqual(self.client.get(reverse("workouts:trocar")).status_code, 302)

    def test_a_leitura_lista_as_alternativas_com_foto_e_trocar_e_a_ficha_anuncia(self):
        leitura = self.client.get(reverse("workouts:exercicio", args=[self.supino.pk]) + "?de=ficha&sessao=%d" % self.hoje.pk)
        self.assertContains(leitura, "Outras formas")
        self.assertContains(leitura, self.declinado.name)
        self.assertContains(leitura, 'class="forma__foto"')
        self.assertContains(leitura, 'action="%s"' % reverse("workouts:trocar"))
        self.assertContains(leitura, 'name="substituto" value="%d"' % self.declinado.pk)
        self.assertContains(leitura, 'name="original" value="%d"' % self.supino.pk)
        html = self._ficha()
        self.assertIn("outras formas", html)
        # Um movimento sem outra forma no equipamento não anuncia a porta.
        # "Abdominal supra no solo" é o único (padrao, grupo) com um exercício
        # ativo só no catálogo — a prancha deixou de servir de exemplo em
        # 20/09/2026, quando a prancha lateral entrou (decisão 1 da avaliação).
        sozinho = Exercise.objects.get(name="Abdominal supra no solo")
        itens = [type("I", (), {"exercise": sozinho, "exercise_id": sozinho.pk})()]
        services.contar_outras_formas(self.user, itens)
        self.assertEqual(itens[0].outras_formas, 0)

    def test_trocar_pela_tela_grava_e_volta_a_leitura_do_substituto_com_a_mesma_volta(self):
        resposta = self.client.post(reverse("workouts:trocar"), {
            "original": self.supino.pk, "substituto": self.declinado.pk, "de": "ficha", "sessao": self.hoje.pk,
        })
        self.assertRedirects(resposta, reverse("workouts:exercicio", args=[self.declinado.pk]) + "?de=ficha&sessao=%d" % self.hoje.pk)
        self.assertEqual(TrocaDeExercicio.objects.get(user=self.user, original=self.supino).substituto, self.declinado)
        # Repetir é idempotente; desfazer pela tela volta à leitura do original.
        self.client.post(reverse("workouts:trocar"), {"original": self.supino.pk, "substituto": self.declinado.pk})
        self.assertEqual(TrocaDeExercicio.objects.count(), 1)
        resposta = self.client.post(reverse("workouts:trocar"), {"original": self.supino.pk, "desfazer": "1", "de": "painel"})
        self.assertRedirects(resposta, reverse("workouts:exercicio", args=[self.supino.pk]) + "?de=painel")
        self.assertFalse(TrocaDeExercicio.objects.exists())

    def test_a_ficha_e_a_leitura_concordam_sobre_quem_tem_outras_formas(self):
        """Achado do QA de 17/09: a linha anunciava "outras formas" e a
        leitura não listava nenhuma — a ficha excluía só a MESMA lista e a
        leitura excluía a sessão inteira (as duas opções). A régua é a da
        lista, nos dois lados e no POST."""
        services.contar_outras_formas(self.user, self.itens)
        for item in self.itens:
            leitura = self.client.get(reverse("workouts:exercicio", args=[item.exercise_id]))
            with self.subTest(exercicio=item.exercise.name):
                self.assertEqual(len(leitura.context["alternativas"]), item.outras_formas)
                if item.outras_formas:
                    services.registrar_troca(self.user, item.exercise, leitura.context["alternativas"][0])
                    services.desfazer_troca(self.user, item.exercise)

    def test_a_troca_de_outra_pessoa_nao_veste_a_minha_ficha(self):
        outra = _pessoa("outra-troca@exemplo.com")
        services.create_routine(outra)
        services.registrar_troca(outra, self.supino, self.declinado)
        html = self._ficha()
        self.assertIn(self.supino.name, html)
        self.assertNotIn(self.declinado.name, html)
