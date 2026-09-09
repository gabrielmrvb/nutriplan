"""TREINO — o tempo prometido é o tempo entregue.

O DEFEITO, medido em produção e reproduzido aqui: quem informava 30 minutos
recebia sessão estimada em 32; 45 recebia 48; 60 recebia 61. A ajuda do campo
dizia "o treino é montado para caber nesse tempo".

A CAUSA não era o corte estar quebrado — era a tolerância. `_teto_em_segundos`
somava 10% do orçamento, no máximo 5 minutos, e a razão estava medida e escrita:
o corte é discreto (sai um exercício inteiro, de 3 a 7 minutos), e sem folga
uma sessão de 30,5 minutos perdia um exercício para economizar meio minuto —
quatro a seis séries semanais a menos.

A SAÍDA não foi escolher entre volume e honestidade: foi mudar a PERGUNTA. O
campo virou faixa (`DuracaoTreino`), o piso é o alvo e o topo é o teto. "Padrão
— 45 a 60" entrega ao motor os mesmos 60 minutos que a folga dava a quem
digitava 45, e agora ele pode prometer.

Este arquivo prova as duas metades: o teto nunca é ultrapassado, e o volume não
desabou por causa disso.
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import (
    TETO_POR_DURACAO,
    ActivityLevel,
    DuracaoTreino,
    Goal,
    ONBOARDING_DONE,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    WeightEntry,
    duracao_de_minutos,
)

from . import services
from .models import TrainingPlan

User = get_user_model()

#: A matriz auditada em produção, transcrita. Cada linha é uma pessoa real que
#: recebeu um treino maior do que o app prometeu.
MATRIZ = [
    ("mulher-22", Sex.FEMALE, date(2004, 3, 1), 162, "55.0", 2, SplitPreference.UM),
    ("homem-45", Sex.MALE, date(1981, 5, 9), 180, "95.0", 3, SplitPreference.DOIS),
    ("mulher-31", Sex.FEMALE, date(1995, 2, 14), 168, "72.0", 4, SplitPreference.TRES),
    ("homem-56", Sex.MALE, date(1970, 7, 21), 178, "110.0", 5, SplitPreference.UM),
    ("homem-25", Sex.MALE, date(2001, 6, 3), 174, "68.0", 6, SplitPreference.DOIS),
]


def pessoa(nome, sexo, nascimento, altura, peso, dias, preferencia, faixa):
    user = User.objects.create_user(
        email="%s-%s@exemplo.com" % (nome, faixa), password="senha-bem-forte-123"
    )
    Profile.objects.create(
        user=user, sex=sexo, birth_date=nascimento, height_cm=altura,
        activity_level=ActivityLevel.LIGHT, goal=Goal.MAINTAIN,
        wake_time=time(7, 0), sleep_time=time(23, 0),
        onboarding_step=ONBOARDING_DONE,
        split_preference=preferencia, split_preference_confirmada=True,
        duracao_treino=faixa,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal(peso))
    for weekday in range(dias):
        TrainingDay.objects.create(
            user=user, weekday=weekday, start_time=time(19, 0), duration_min=60
        )
    services.sync_active_routine(user)
    return user


def sessoes_de(user):
    plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
    return list(plano.sessions.prefetch_related("exercises__exercise"))


class OTetoDaFaixaNuncaEUltrapassadoTests(TestCase):
    """A promessa da tela, medida em todos os cruzamentos da matriz."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_nenhuma_sessao_passa_do_teto_da_faixa(self):
        for faixa in (DuracaoTreino.RAPIDO, DuracaoTreino.PADRAO,
                      DuracaoTreino.COMPLETO):
            teto = TETO_POR_DURACAO[faixa]
            for nome, sexo, nasc, alt, peso, dias, pref in MATRIZ:
                with self.subTest(faixa=faixa, perfil=nome):
                    user = pessoa(nome, sexo, nasc, alt, peso, dias, pref, faixa)

                    minutos = [s.estimated_minutes for s in sessoes_de(user)]

                    self.assertTrue(minutos, "a pessoa ficou sem sessão")
                    self.assertLessEqual(
                        max(minutos), teto,
                        "%s com %s recebeu %s, e o teto é %d"
                        % (nome, faixa, minutos, teto),
                    )

    def test_os_casos_exatos_da_auditoria(self):
        """30 não pode dar 32; 60 não pode dar 61. Eram os números da queixa."""
        casos = [
            ("mulher-22", DuracaoTreino.RAPIDO, 30),
            ("mulher-31", DuracaoTreino.PADRAO, 60),
        ]
        por_nome = {linha[0]: linha for linha in MATRIZ}
        for nome, faixa, teto in casos:
            with self.subTest(perfil=nome):
                _, sexo, nasc, alt, peso, dias, pref = por_nome[nome]
                user = pessoa(nome, sexo, nasc, alt, peso, dias, pref, faixa)

                for sessao in sessoes_de(user):
                    self.assertLessEqual(sessao.estimated_minutes, teto)

    def test_sem_limite_rigido_nao_corta_por_tempo(self):
        """LIVRE é "priorizar a ficha completa", e tem de entregar mais volume.

        Sem esta comparação, `LIVRE` poderia estar cortando igual e o teste do
        teto acima passaria — ele só olha para cima.
        """
        _, sexo, nasc, alt, peso, dias, pref = MATRIZ[2]
        curto = pessoa("comparar", sexo, nasc, alt, peso, dias, pref,
                       DuracaoTreino.RAPIDO)
        livre = pessoa("comparar", sexo, nasc, alt, peso, dias, pref,
                       DuracaoTreino.LIVRE)

        series_curto = sum(s.total_sets for s in sessoes_de(curto))
        series_livre = sum(s.total_sets for s in sessoes_de(livre))

        self.assertGreater(series_livre, series_curto)

    def test_a_faixa_maior_nunca_entrega_menos_volume_que_a_menor(self):
        """Monotonicidade: mais tempo não pode produzir ficha menor.

        É a propriedade que pega um corte com sinal invertido — o tipo de erro
        que passa despercebido porque cada faixa, isolada, parece plausível.
        """
        _, sexo, nasc, alt, peso, dias, pref = MATRIZ[4]
        volumes = []
        for faixa in (DuracaoTreino.RAPIDO, DuracaoTreino.PADRAO,
                      DuracaoTreino.COMPLETO, DuracaoTreino.LIVRE):
            user = pessoa("mono", sexo, nasc, alt, peso, dias, pref, faixa)
            volumes.append(sum(s.total_sets for s in sessoes_de(user)))

        self.assertEqual(volumes, sorted(volumes),
                         "o volume não cresce com a faixa: %s" % volumes)


class ATrocaDeFaixaNaoCustouVolumeTests(TestCase):
    """A correção não podia ser obtida encolhendo a ficha de todo mundo.

    Antes, quem digitava 45 recebia até 50 (45 + folga). Agora essa pessoa cai
    em "Padrão — 45 a 60", cujo teto é 60. O volume tinha de subir ou ficar
    igual, nunca cair — e é isso que se mede aqui.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_padrao_entrega_pelo_menos_o_que_a_folga_antiga_entregava(self):
        _, sexo, nasc, alt, peso, dias, pref = MATRIZ[1]
        user = pessoa("padrao", sexo, nasc, alt, peso, dias, pref,
                      DuracaoTreino.PADRAO)

        sessoes = sessoes_de(user)

        # A auditoria mediu 48, 48 e 44 minutos para este perfil com teto 45.
        # Com a faixa Padrão o teto é 60, então a ficha cabe inteira — nenhuma
        # sessão precisa perder exercício por tempo.
        self.assertTrue(all(s.estimated_minutes <= 60 for s in sessoes))
        self.assertGreaterEqual(sum(s.total_sets for s in sessoes), 55)


class MudarAFaixaRemontaAFichaTests(TestCase):
    """Trocar a faixa tem de invalidar a ficha — senão o campo é decorativo.

    O PERCURSO ATÉ ESTA VERSÃO, porque ele evitou dívida.

    A suspeita era de defeito: `routine_is_current` compara (dia, horário,
    `duration_min`), e a faixa não mexe em `duration_min` nenhum. Parecia que
    trocar "Completo" por "Rápido" deixaria a ficha de 90 minutos na tela com a
    interface prometendo 30.

    A correção escrita foi guardar o teto no retrato do plano — uma coluna e uma
    migration. E a SABOTAGEM reprovou a correção: com a comparação nova
    desligada, estes testes continuaram verdes. O motivo é que
    `_prescricao_confere` já chama `prescrever_semana`, que passou a ler a
    faixa — a prescrição muda, e a conferência de prescrição pega. A coluna era
    redundante e foi removida junto com a migration.

    O que ficou é este arquivo: a propriedade continua exigida, e a sabotagem
    de `_prescricao_confere` mostra que ela é guardada de verdade.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _pessoa(self, faixa):
        _, sexo, nasc, alt, peso, dias, pref = MATRIZ[3]
        return pessoa("remonta", sexo, nasc, alt, peso, dias, pref, faixa)

    @staticmethod
    def _trocar_faixa(user, faixa):
        """Troca a faixa e devolve uma instância NOVA da pessoa.

        `user.profile` é um `OneToOne` com cache na instância: gravar no banco
        e continuar usando o mesmo objeto faz `teto_de_minutos` ler o valor
        antigo, e o teste mede o estado anterior achando que mede o novo. Foi
        o que aconteceu na primeira versão deste arquivo — a asserção falhou
        sem nenhum defeito no produto.
        """
        Profile.objects.filter(user=user).update(duracao_treino=faixa)
        return type(user).objects.get(pk=user.pk)

    def test_a_ficha_fica_obsoleta_quando_a_faixa_encolhe(self):
        user = self._pessoa(DuracaoTreino.LIVRE)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()

        user = self._trocar_faixa(user, DuracaoTreino.RAPIDO)

        self.assertFalse(services.routine_is_current(plano, user))

    def test_a_ficha_remontada_obedece_a_faixa_nova(self):
        """Ficar obsoleta não basta: a próxima tem de caber."""
        user = self._pessoa(DuracaoTreino.LIVRE)

        user = self._trocar_faixa(user, DuracaoTreino.RAPIDO)
        nova, mudou = services.sync_active_routine(user)

        self.assertTrue(mudou)
        for sessao in nova.sessions.all():
            self.assertLessEqual(sessao.estimated_minutes, 30)

    def test_sem_mexer_na_faixa_a_ficha_continua_valendo(self):
        """Controle: sem isto, "sempre obsoleta" passaria nos dois acima.

        Uma ficha julgada obsoleta em toda visita faria o gerador rodar em laço
        — o defeito que o comentário de `routine_is_current` já registra.
        """
        user = self._pessoa(DuracaoTreino.PADRAO)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()

        self.assertTrue(services.routine_is_current(plano, user))

    def test_a_prescricao_e_quem_denuncia_a_troca(self):
        """O mecanismo, nomeado — para a próxima pessoa não recriar a coluna.

        Não há teto guardado no plano: quem percebe a mudança é a conferência
        de prescrição, porque `prescrever_semana` lê a faixa e devolve outra
        ficha. Este teste falha se alguém tornar a conferência indiferente à
        faixa.
        """
        user = self._pessoa(DuracaoTreino.LIVRE)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
        antes = services.prescrever_semana(
            list(plano.sessions.all()),
            {t.label: t for t in services.templates_for(plano.split)},
        )

        user = self._trocar_faixa(user, DuracaoTreino.RAPIDO)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
        depois = services.prescrever_semana(
            list(plano.sessions.all()),
            {t.label: t for t in services.templates_for(plano.split)},
        )

        self.assertNotEqual(set(antes), set(depois))


class AConversaoDoNumeroAntigoEDeterministicaTests(TestCase):
    """Quem já usava o app não pode cair no padrão em silêncio."""

    def test_cada_numero_cai_na_faixa_certa(self):
        self.assertEqual(duracao_de_minutos(20), DuracaoTreino.RAPIDO)
        self.assertEqual(duracao_de_minutos(30), DuracaoTreino.RAPIDO)
        self.assertEqual(duracao_de_minutos(31), DuracaoTreino.PADRAO)
        self.assertEqual(duracao_de_minutos(60), DuracaoTreino.PADRAO)
        self.assertEqual(duracao_de_minutos(61), DuracaoTreino.COMPLETO)
        self.assertEqual(duracao_de_minutos(90), DuracaoTreino.COMPLETO)

    def test_acima_de_noventa_vira_livre_e_nao_completo(self):
        """Quem digitou 120 declarou que tempo não era a restrição dele.

        Enfiá-lo num teto de 90 apertaria a ficha de alguém que nunca pediu.
        """
        self.assertEqual(duracao_de_minutos(120), DuracaoTreino.LIVRE)
        self.assertEqual(duracao_de_minutos(300), DuracaoTreino.LIVRE)

    def test_ausencia_de_numero_e_livre(self):
        self.assertEqual(duracao_de_minutos(None), DuracaoTreino.LIVRE)
        self.assertEqual(duracao_de_minutos(0), DuracaoTreino.LIVRE)


class OContratoComOCardapioNaoFoiTocadoTests(TestCase):
    """`duration_min` continua existindo, e por um motivo de outra área.

    `plans/meal_planner.py` soma `start_time + duration_min` para não marcar
    refeição no meio do treino. Se esta campanha apagasse a coluna, o cardápio
    de todo mundo mudaria — e a missão proíbe mexer em Alimentação.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_dia_de_treino_continua_guardando_minutos(self):
        _, sexo, nasc, alt, peso, dias, pref = MATRIZ[0]
        user = pessoa("contrato", sexo, nasc, alt, peso, dias, pref,
                      DuracaoTreino.RAPIDO)

        for dia in TrainingDay.objects.filter(user=user):
            self.assertTrue(dia.duration_min)

    def test_o_motor_le_a_faixa_e_nao_o_inteiro_do_dia(self):
        """O inteiro do dia é 60 e a faixa é RAPIDO: quem manda é a faixa.

        Sem esta separação, a correção teria sido cosmética — o motor
        continuaria obedecendo ao número antigo.
        """
        _, sexo, nasc, alt, peso, dias, pref = MATRIZ[0]
        user = pessoa("faixa-manda", sexo, nasc, alt, peso, dias, pref,
                      DuracaoTreino.RAPIDO)

        self.assertEqual(services.teto_de_minutos(user), 30)
        for sessao in sessoes_de(user):
            self.assertEqual(sessao.duration_min, 60)
            self.assertLessEqual(sessao.estimated_minutes, 30)
