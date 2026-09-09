"""TREINO — a experiência muda a prescrição, e não só o formulário.

"Campo que só aparece no formulário e não altera comportamento não conta como
personalização implementada." Este arquivo é a prova do caminho inteiro:
entrada → persistência → motor → apresentação → edição.

O QUE A EXPERIÊNCIA MOVE, e por que só isso. Ela ajusta o TETO SEMANAL POR
GRUPO — o número que `aparar_volume_semanal` usa para decidir quantas séries
efetivas cada músculo recebe na semana. Não mexe em QUAIS exercícios entram:
rebaixar o agachamento por ser "complexo demais para iniciante" seria o app
decidir sozinho tirar o movimento que mais interessa a quem está começando.

NÃO HÁ PADRÃO: o campo nasce vazio, e vazio é "ainda não respondeu". O motor
lê o vazio como 20 — o número que o app já praticava —, então quem nunca
respondeu não tem a ficha reescrita, e a tela também não afirma um nível que
ninguém declarou. É a doutrina da `0024` e a de `prioridade == ""`.

O QUE FICOU DE FORA, e a medição está aqui para ninguém achar que foi esquecimento:
local e equipamento. Dos onze grupos do catálogo, "casa com halteres" deixa
posterior de coxa, panturrilha e antebraço com ZERO exercícios; "peso corporal"
esvazia oito dos onze. Um filtro por equipamento entregaria ficha sem grupo
inteiro — o oposto do que as travas de `aparar_volume_semanal` protegem. O
teste `test_o_catalogo_ainda_nao_sustenta_filtro_por_equipamento` congela essa
medição: no dia em que o catálogo crescer, ele avisa.
"""
from collections import defaultdict

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import (
    TETO_POR_EXPERIENCIA,
    Experiencia,
    ONBOARDING_DONE,
    Profile,
    TrainingDay,
)

from . import services
from .models import Equipment, Exercise, TrainingPlan
from .tests import create_user


def com_experiencia(email, nivel, dias=4):
    user = create_user(email=email, weekdays=tuple(range(dias)))
    Profile.objects.filter(user=user).update(experiencia=nivel)
    user.refresh_from_db()
    services.create_routine(user)
    return user


def volume_efetivo_por_grupo(user):
    plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
    volume = defaultdict(float)
    for sessao in plano.sessions.all():
        for item in sessao.exercises.select_related("exercise"):
            volume[item.exercise.muscle_group] += item.sets
            for secundario in item.exercise.secondary_muscles or []:
                volume[secundario] += item.sets * 0.5
    return volume


class AExperienciaMudaOVolumeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_numero_do_nivel_chega_ao_aparo_e_o_aparo_vai_ate_o_fim(self):
        """A prova direta de que a resposta atravessa até o motor.

        Duas afirmações numa medição só, e as duas precisam ser verdade:

        1. o teto que `aparar_volume_semanal` recebe é o do nível — não o 20
           fixo de antes, e não um número derivado de outra coisa;
        2. o aparo PAROU porque não havia mais o que ceder, e não no meio do
           caminho. A conferência é rodar a função de novo sobre o que
           sobreviveu: se ela ainda tirar alguma coisa, o primeiro laço
           desistiu cedo.

        O que este teste NÃO afirma, e a distinção é a mesma que
        `aparar_volume_semanal` documenta: o teto não é promessa. Quando o
        excesso de um grupo é secundário de composto principal — meio ponto por
        série de supino somando no ombro —, tirá-lo exigiria derrubar o supino,
        e a trava existe para impedir isso. Ver
        `OTetoDeAparoNaoEPromessaDeTetoTests`, logo abaixo, com a medição.
        """
        for nivel, teto in TETO_POR_EXPERIENCIA.items():
            with self.subTest(nivel=nivel):
                visto = {}
                original = services.aparar_volume_semanal

                def espiao(candidatos, teto=None, _orig=original, _visto=visto):
                    ficam = _orig(candidatos, teto=teto)
                    _visto["candidatos"] = list(candidatos)
                    _visto["teto"] = teto
                    _visto["ficam"] = set(ficam)
                    return ficam

                services.aparar_volume_semanal = espiao
                try:
                    com_experiencia("t-%s@exemplo.com" % nivel, nivel)
                finally:
                    services.aparar_volume_semanal = original

                self.assertEqual(visto["teto"], teto)
                sobreviventes = [
                    c for c in visto["candidatos"] if c[0] in visto["ficam"]
                ]
                self.assertEqual(
                    original(sobreviventes, teto=teto), visto["ficam"],
                    "o aparo parou antes de esgotar o que podia ceder",
                )

    def test_iniciante_recebe_menos_volume_que_avancado(self):
        """A personalização precisa APARECER na ficha, não só no perfil."""
        iniciante = com_experiencia("i@exemplo.com", Experiencia.INICIANTE)
        avancado = com_experiencia("a@exemplo.com", Experiencia.AVANCADO)

        def total(user):
            plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
            return sum(s.total_sets for s in plano.sessions.all())

        self.assertLess(total(iniciante), total(avancado))

    def test_o_volume_cresce_com_o_nivel_sem_inverter(self):
        """Monotonicidade: pega corte com sinal trocado, que isolado parece ok."""
        volumes = []
        for nivel in (Experiencia.INICIANTE, Experiencia.INTERMEDIARIO,
                      Experiencia.AVANCADO):
            user = com_experiencia("m-%s@exemplo.com" % nivel, nivel)
            plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
            volumes.append(sum(s.total_sets for s in plano.sessions.all()))

        self.assertEqual(volumes, sorted(volumes), volumes)

    def test_quem_nunca_respondeu_fica_no_comportamento_de_antes(self):
        """Vazio é um estado de verdade, e ele vale o número de antes.

        As duas metades importam. A primeira: o campo NÃO nasce
        `intermediario` — gravar isso seria o app declarar por quem não
        declarou. A segunda: mesmo assim a ficha não muda, porque o motor lê o
        vazio como `TETO_SEMANAL_POR_GRUPO`.
        """
        user = create_user(email="padrao@exemplo.com")

        self.assertEqual(user.profile.experiencia, "")
        self.assertEqual(services.teto_semanal_de(user),
                         services.TETO_SEMANAL_POR_GRUPO)
        self.assertEqual(services.teto_semanal_de(user), 20)

    def test_o_vazio_produz_a_mesma_ficha_do_intermediario(self):
        """A retrocompatibilidade dita na migration `0028`, medida na ficha.

        Se o vazio montasse ficha diferente, a pergunta nova teria reescrito o
        treino de todo mundo que já usa o app — e a `0028` não converte
        ninguém, então não haveria como voltar atrás.
        """
        antes = create_user(email="vazio@exemplo.com", weekdays=(0, 1, 2, 3))
        depois = com_experiencia(
            "intermediario@exemplo.com", Experiencia.INTERMEDIARIO
        )
        services.create_routine(antes)

        def receita(user):
            plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
            return sorted(
                (s.label, i.exercise_id, i.sets)
                for s in plano.sessions.all()
                for i in s.exercises.all()
            )

        self.assertEqual(receita(antes), receita(depois))

    def test_nenhum_nivel_apaga_um_grupo_inteiro(self):
        """Menos volume não pode virar músculo sem treino nenhum.

        É a mesma trava de `aparar_volume_semanal`: grupo com um exercício só
        não tem gordura para cortar.
        """
        for nivel in TETO_POR_EXPERIENCIA:
            with self.subTest(nivel=nivel):
                user = com_experiencia("g-%s@exemplo.com" % nivel, nivel)

                grupos = {
                    g for g, v in volume_efetivo_por_grupo(user).items() if v > 0
                }

                self.assertGreaterEqual(len(grupos), 8)

    def test_trocar_a_experiencia_remonta_a_ficha(self):
        """Editar o campo tem de chegar na ficha — senão a edição é decorativa.

        E a ficha antiga não é EDITADA: plano é retrato. O que se prova aqui é
        que `routine_is_current` reprova o retrato antigo e nasce um plano novo,
        com menos volume.
        """
        user = com_experiencia("remonta@exemplo.com", Experiencia.AVANCADO)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
        antes = sum(s.total_sets for s in plano.sessions.all())

        Profile.objects.filter(user=user).update(experiencia=Experiencia.INICIANTE)
        user = type(user).objects.get(pk=user.pk)

        self.assertFalse(services.routine_is_current(plano, user))
        nova, mudou = services.sync_active_routine(user)
        self.assertTrue(mudou)
        self.assertNotEqual(nova.pk, plano.pk)
        self.assertLess(sum(s.total_sets for s in nova.sessions.all()), antes)


class OTetoDeAparoNaoEPromessaDeTetoTests(TestCase):
    """A MEDIÇÃO QUE IMPEDE ALGUÉM DE "CONSERTAR" ISTO SEM SABER O PREÇO.

    A primeira versão desta implementação afirmava que nenhum grupo passa do
    teto do nível, e ela ficou VERMELHA: tríceps fechou em 13,0 com o teto do
    iniciante em 12. A leitura errada seria afrouxar o número até o vermelho
    sumir; a certa é que o teto nunca foi promessa, e `aparar_volume_semanal`
    diz isso na própria docstring — "se o excesso só puder ser resolvido
    cortando principal, o excesso fica".

    A medição, no perfil de quatro dias, variando SÓ o teto:

        teto  1 -> ombro 14,5 · tríceps 13,0 · peito 11,0 |  48 séries
        teto 12 -> ombro 14,5 · tríceps 13,0              |  65 séries
        teto 20 -> nenhum grupo acima do teto             |  88 séries

    O piso de 14,5 do ombro é secundário de supino e desenvolvimento: meio
    ponto por série de composto principal. Baixá-lo exigiria derrubar o supino,
    que é o que as travas existem para impedir — foi assim que uma versão
    anterior esvaziou uma sexta-feira inteira.

    E o que a personalização promete continua verdadeiro, porque é sobre o
    volume TOTAL: 48, 65 e 88 séries são três treinos diferentes.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_excesso_que_sobra_e_sempre_secundario_ou_unico(self):
        """Cada grupo acima do teto tem uma razão, e ela é uma das travas.

        Sem este teste, "o teto não é promessa" viraria licença para qualquer
        excesso. Aqui todo grupo que passa do teto do iniciante precisa provar
        que não havia o que ceder: ou o trabalho direto dele na semana é um
        exercício só, ou o que resta é tudo principal.
        """
        user = com_experiencia("excesso@exemplo.com", Experiencia.INICIANTE)
        teto = TETO_POR_EXPERIENCIA[Experiencia.INICIANTE]
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()

        diretos = defaultdict(list)
        for sessao in plano.sessions.all():
            itens = list(sessao.exercises.select_related("exercise"))
            for grau, item in zip(services.prioridades_da_sessao(itens), itens):
                diretos[item.exercise.muscle_group].append(grau)

        for grupo, series in volume_efetivo_por_grupo(user).items():
            if series <= teto:
                continue
            graus = diretos[grupo]
            self.assertTrue(
                len(graus) <= 1 or all(g == services.PRINCIPAL for g in graus),
                "%s ficou em %.1f com o teto em %d e ainda tinha o que ceder"
                % (grupo, series, teto),
            )

    def test_o_iniciante_treina_menos_apesar_do_excesso_irredutivel(self):
        """O que a personalização promete é o volume da SEMANA, e ele cai."""
        iniciante = com_experiencia("v-ini@exemplo.com", Experiencia.INICIANTE)
        intermediario = com_experiencia("v-int@exemplo.com",
                                        Experiencia.INTERMEDIARIO)

        def total(user):
            plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
            return sum(s.total_sets for s in plano.sessions.all())

        self.assertLess(total(iniciante), total(intermediario) * 0.85)


class AExperienciaAtravessaOFormularioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_passo_3_grava_a_experiencia(self):
        user = create_user(email="form@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {
                "weekdays": ["1", "3"],
                "start_time": "",
                "duracao_treino": "padrao",
                "experiencia": Experiencia.INICIANTE,
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
        )

        user.refresh_from_db()
        self.assertEqual(user.profile.experiencia, Experiencia.INICIANTE)

    def test_sem_resposta_o_passo_nao_declara_nada(self):
        """Passar batido pelo campo não pode gravar um nível."""
        user = create_user(email="form-vazio@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {
                "weekdays": ["1"],
                "start_time": "",
                "duracao_treino": "padrao",
                "experiencia": "",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
        )

        user.refresh_from_db()
        self.assertEqual(user.profile.experiencia, "")

    def test_o_perfil_mostra_a_experiencia(self):
        user = com_experiencia("perfil@exemplo.com", Experiencia.AVANCADO)
        self.client.force_login(user)

        self.assertContains(
            self.client.get(reverse("accounts:profile")), "Avançado"
        )

    def test_o_perfil_diz_que_a_experiencia_nao_foi_informada(self):
        """Linha pendurada sem valor não é honestidade, é descuido.

        E escrever "Intermediário" ali seria pior: a tela afirmaria a resposta
        que a pessoa não deu.
        """
        user = create_user(email="perfil-vazio@exemplo.com")
        self.client.force_login(user)

        resposta = self.client.get(reverse("accounts:profile"))

        self.assertContains(resposta, "não informada")
        self.assertNotContains(resposta, "Intermediário")

    def _marcados(self):
        """Os rádios de experiência que abrem já escolhidos.

        Ancorado em `checked`, que é o que faz o rádio nascer marcado — o
        `value` dos três aparece de qualquer jeito, porque as três opções são
        renderizadas sempre.
        """
        html = self.client.get(
            reverse("accounts:onboarding_step", kwargs={"step": 3})
        ).content.decode()
        return [
            trecho for trecho in html.split("<input")
            if 'name="experiencia"' in trecho and "checked" in trecho
        ]

    def test_o_formulario_nao_abre_com_um_nivel_marcado(self):
        """Opção pré-marcada é o mesmo padrão silencioso, na entrada.

        OS DOIS CAMINHOS, e a sabotagem é o motivo de existirem dois. O
        `initial` do campo só governa quem AINDA NÃO TEM dia de treino — a
        primeira passagem pelo passo 3 —, porque para quem já tem o `__init__`
        sobrescreve com o valor do perfil. Uma versão anterior deste teste só
        exercitava o segundo caminho: devolver `initial="intermediario"` ao
        campo passava VERDE, e a primeira pessoa a cadastrar treino no app
        continuava recebendo a opção marcada.
        """
        for tem_dias in (False, True):
            with self.subTest(tem_dias=tem_dias):
                user = create_user(email="form-abre-%s@exemplo.com" % tem_dias)
                if not tem_dias:
                    TrainingDay.objects.filter(user=user).delete()
                Profile.objects.filter(user=user).update(
                    onboarding_step=ONBOARDING_DONE
                )
                self.client.force_login(user)

                self.assertEqual(self._marcados(), [])

    def test_quem_ja_respondeu_reabre_o_passo_com_a_resposta(self):
        """Controle do teste acima: sem ele, "nunca marcar nada" passaria.

        E é comportamento exigido por si: reabrir o passo e enviar sem tocar no
        campo não pode apagar o nível que a pessoa escolheu.
        """
        user = com_experiencia("form-reabre@exemplo.com", Experiencia.AVANCADO)
        Profile.objects.filter(user=user).update(onboarding_step=ONBOARDING_DONE)
        self.client.force_login(user)

        marcados = self._marcados()

        self.assertEqual(len(marcados), 1)
        self.assertIn(Experiencia.AVANCADO, marcados[0])


class OCatalogoAindaNaoSustentaEquipamentoTests(TestCase):
    """A MEDIÇÃO QUE EXPLICA O QUE FICOU DE FORA — e que avisa quando mudar.

    A missão pede personalização por local/equipamento: academia completa, casa
    com halteres, peso corporal. O catálogo não comporta as duas últimas, e o
    número está aqui em vez de na minha palavra.

    Este teste é uma CATRACA ao contrário: ele falha no dia em que o catálogo
    crescer o bastante, e aí a personalização por equipamento passa a ser
    implementável sem entregar ficha sem grupo.

    A MATRIZ COMPLETA — 11 grupos x 5 equipamentos, com a contagem célula a
    célula — está no `BACKLOG.md`, em "Personalização de treino por LOCAL e
    EQUIPAMENTO". Ela não é repetida aqui de propósito: número copiado em dois
    lugares diverge no primeiro exercício novo, e o que este arquivo precisa
    guardar é a PROPRIEDADE, não a tabela.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    #: Grupos que um ambiente precisa cobrir para valer como opção.
    #: Trapézio e antebraço ficam de fora: têm um ou dois exercícios no
    #: catálogo inteiro e são distribuídos como complemento.
    ESSENCIAIS = {
        "chest", "back", "quads", "hamstrings", "shoulders",
        "biceps", "triceps", "calves", "core",
    }

    def _cobertura(self, equipamentos):
        grupos = set(
            Exercise.objects.filter(
                is_active=True, equipment__in=equipamentos
            ).values_list("muscle_group", flat=True)
        )
        return self.ESSENCIAIS - grupos

    def test_casa_com_halteres_ainda_deixa_grupos_sem_exercicio(self):
        faltam = self._cobertura([Equipment.DUMBBELL, Equipment.BODYWEIGHT])

        self.assertTrue(
            faltam,
            "o catálogo passou a cobrir casa com halteres — a personalização "
            "por equipamento virou implementável",
        )

    def test_peso_corporal_ainda_deixa_grupos_sem_exercicio(self):
        faltam = self._cobertura([Equipment.BODYWEIGHT])

        self.assertTrue(
            faltam,
            "o catálogo passou a cobrir peso corporal — a personalização por "
            "equipamento virou implementável",
        )

    def test_a_academia_completa_cobre_tudo(self):
        """Controle positivo: sem ele os dois testes acima passariam mesmo com
        um catálogo vazio, e a medição não mediria nada."""
        self.assertEqual(self._cobertura([e for e in Equipment.values]), set())
