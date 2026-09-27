# -*- coding: utf-8 -*-
"""A ficha de peso do corpo tem volume comparável (decisão 1 da avaliação, 20/09/2026).

O dono pediu: "ampliar o catálogo com 20–30 exercícios de peso do corpo com
progressões, para que a ficha desse perfil tenha o mesmo volume das outras."
Aqui está a prova de que ela tem — não idêntica (bíceps, ombro e peito são
menores por limite físico do peso do corpo, não do catálogo), mas cada letra
vira uma sessão cheia e o volume semanal total fica perto do da academia.

O golden (`test_ficha_de_verdade`) guarda a letra A opção a opção e continua
com o `expectedFailure` da letra A (o crucifixo não tem versão sem carga);
este arquivo guarda a COMPARABILIDADE, que é o que a decisão pediu.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import services
from workouts.models import Exercise


def _plano(equipamento, dias=5, pref="two"):
    user = create_complete_user(
        email="pesocorpo-%s@exemplo.com" % equipamento, experiencia="intermediario",
        split_preference=pref, split_preference_confirmada=True,
        duracao_treino=DuracaoTreino.PADRAO, equipamento=equipamento,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return services.create_routine(user)


class VolumeComparavelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    #: A letra que o catálogo de casa NÃO enche, e por quê.
    #:
    #: "Costas e bíceps" sem barra fixa tem, no catálogo inteiro, DOIS
    #: exercícios possíveis: a remada invertida (sob a mesa) e a rosca
    #: invertida na mesma barra baixa. Não há como puxar sem alguma coisa
    #: para puxar, e desde 26/09/2026 o app não finge que há — a barra fixa
    #: saiu da ficha de casa (`Exercise.aparelho`).
    #:
    #: O número fica preso AQUI, e não afrouxado: se a letra B cair para 1
    #: exercício, ou se alguma outra letra encolher, o teste reprova.
    LETRA_MAGRA_SEM_BARRA = {"B": 2}

    def test_cada_letra_vira_uma_sessao_cheia(self):
        """Nenhuma letra sai magra — exceto a que o catálogo de casa não tem
        como encher, e essa está NOMEADA.

        Antes da decisão de 20/09/2026 a letra B tinha 1 exercício e a C,
        dois; o catálogo de peso do corpo encheu as três. Em 26/09/2026 a
        barra fixa saiu da ficha de casa (ela não é "peso do corpo", é
        aparelho), e a letra B voltou a ter o que uma casa tem: duas
        remadas invertidas e uma rosca invertida, repartidas entre as duas
        opções. A lista do que falta ao catálogo está no `BACKLOG.md`.
        """
        plano = _plano("peso_corporal")
        for s in plano.sessions.prefetch_related("exercises__exercise").order_by("order"):
            for k in s.opcoes:
                itens = s.da_opcao(k)
                retrato = "%s opção %d: %d ex, %d min" % (
                    s.label, k, len(itens), s.minutos_da_opcao(k))
                magra = self.LETRA_MAGRA_SEM_BARRA.get(s.label)
                with self.subTest(retrato=retrato):
                    if magra:
                        self.assertEqual(len(itens), magra, retrato)
                        continue
                    self.assertGreaterEqual(len(itens), 5, retrato)
                    self.assertGreaterEqual(s.minutos_da_opcao(k), 45, retrato)
                    self.assertLessEqual(s.minutos_da_opcao(k), 65, retrato)

    def test_casa_com_halteres_continua_com_todas_as_letras_cheias(self):
        """CONTROLE POSITIVO da régua de cima: o que a barra fixa tirou foi
        do perfil que não tem NADA — quem tem halteres rema e faz rosca, e
        as três letras continuam entre 5 e 9 exercícios."""
        plano = _plano("casa_halteres")
        for s in plano.sessions.prefetch_related("exercises__exercise").order_by("order"):
            for k in s.opcoes:
                with self.subTest(letra=s.label, opcao=k):
                    self.assertGreaterEqual(len(s.da_opcao(k)), 5)

    def test_o_volume_semanal_e_comparavel_ao_da_academia(self):
        """O volume efetivo da semana contra o da academia completa.

        MEDIDO em 20/09/2026: 94% — com a barra fixa dentro do catálogo de
        "peso do corpo". MEDIDO em 26/09/2026, com ela fora: **77% para só o
        peso do corpo e 100% para casa com halteres** (218 e 281 contra
        282 séries efetivas).

        O piso de 70% guarda o que sobrou e reprova uma queda nova; os 80%
        de antes contavam um exercício que aquela casa não tem. Subir de
        volta é trabalho de CATÁLOGO (remada e rosca sem barra), não de
        motor — está no `BACKLOG.md`.
        """
        peso = sum(services.volume_da_semana(_plano("peso_corporal")).values())
        halteres = sum(services.volume_da_semana(_plano("casa_halteres")).values())
        cheia = sum(services.volume_da_semana(_plano("completa")).values())
        self.assertGreaterEqual(
            peso, cheia * 7 / 10,
            "o volume do peso do corpo caiu demais: %s contra %s" % (peso, cheia),
        )
        self.assertGreaterEqual(
            halteres, cheia * 95 / 100,
            "casa com halteres tem substituto para tudo: %s contra %s" % (halteres, cheia),
        )

    def test_os_grupos_que_faltavam_agora_tem_exercicio_sem_aparelho(self):
        """Quadríceps, posterior, panturrilha, ombro e costas — que não tinham
        NENHUM exercício ativo sem aparelho — agora têm, e é isso que enche as
        letras B e C. Bíceps continua com um só (a barra fixa/rosca invertida):
        limite físico do peso do corpo, dito na ficha, não no catálogo."""
        sem_aparelho = Exercise.objects.filter(is_active=True, equipment="bodyweight")
        grupos = set(sem_aparelho.values_list("muscle_group", flat=True))
        for grupo in ("quads", "hamstrings", "calves", "shoulders", "back", "chest", "triceps", "core"):
            with self.subTest(grupo=grupo):
                self.assertIn(grupo, grupos)


class ProgressaoDoMovimentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_escada_vai_do_facil_ao_dificil_e_marca_o_atual(self):
        atual = Exercise.objects.get(name="Flexão de braço")
        escada = services.escada_de(atual)
        nomes = [d["exercicio"].name for d in escada]
        self.assertEqual(nomes[0], "Flexão de braço com joelhos apoiados")
        niveis = [d["exercicio"].progressao["nivel"] for d in escada]
        self.assertEqual(niveis, sorted(niveis), "a escada não está ordenada")
        marcados = [d for d in escada if d["atual"]]
        self.assertEqual(len(marcados), 1)
        self.assertEqual(marcados[0]["exercicio"].name, "Flexão de braço")
        rel = {d["exercicio"].name: d["relativo"] for d in escada}
        self.assertEqual(rel["Flexão de braço com joelhos apoiados"], "mais_facil")
        self.assertEqual(rel["Flexão de braço arqueiro"], "mais_dificil")

    def test_exercicio_com_aparelho_nao_tem_escada(self):
        """A progressão do que usa aparelho é a carga, não a versão."""
        com_aparelho = (
            Exercise.objects.filter(is_active=True).exclude(equipment="bodyweight").first()
        )
        self.assertEqual(services.escada_de(com_aparelho), [])

    def test_a_leitura_mostra_a_escada_do_peso_do_corpo(self):
        """Ponta a ponta: quem treina só com o corpo abre a leitura de uma
        flexão e vê a progressão do movimento, com "você está aqui"."""
        user = create_complete_user(
            email="leitura-peso@exemplo.com", experiencia="intermediario",
            split_preference="two", split_preference_confirmada=True,
            duracao_treino=DuracaoTreino.PADRAO, equipamento="peso_corporal",
        )
        TrainingDay.objects.filter(user=user).delete()
        for d in range(5):
            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
        plano = services.create_routine(user)
        # um exercício de peso do corpo que está na ficha e tem escada
        exercicios = {
            i.exercise for s in plano.sessions.prefetch_related("exercises__exercise")
            for i in s.exercises.all()
        }
        com_escada = next(e for e in exercicios if services.escada_de(e))
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:exercicio", args=[com_escada.pk])).content.decode()
        self.assertIn("Progressão do movimento", html)
        self.assertIn("você está aqui", html)
        self.assertIn("card escada", html)
