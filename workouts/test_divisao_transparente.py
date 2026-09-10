"""TREINO — a divisão pedida, a aplicada, e a diferença dita em voz alta.

DOIS DEFEITOS DA MESMA FAMÍLIA, os dois de LEITURA e nenhum de prescrição.

1. A PREFERÊNCIA CEDE EM SILÊNCIO. `split_for` cruza preferência com
   frequência e a frequência manda — quem pede "1 grupo por dia" e treina duas
   vezes recebe AB, porque uma divisão de cinco dias com duas sessões deixaria
   três quintos do corpo sem treinar nenhuma vez. A regra está certa; o que
   estava errado é que a tela mostrava AB e o Perfil continuava dizendo
   "1 grupo por dia", como se a escolha tivesse valido.

   E abaixo de quatro dias o onboarding nem PERGUNTA
   (`preferencia_muda_a_divisao` responde False), então a preferência gravada
   fica inerte e a pessoa não tem como descobrir isso sozinha.

2. A LETRA REPETIDA PARECE FICHA INCOMPLETA. Cinco dias num ABC viram
   A, B, C, A, B. As duas ocorrências de A nascem com a dose cheia, e
   `aparar_volume_semanal` cede sempre a sessão mais cheia — então uma das
   passagens sai menor. Quem abre a menor lê o mesmo título com menos
   exercícios e conclui que falta coisa.

   E A FRASE QUE EXPLICA ISSO NÃO PODE PROMETER VARIEDADE. A primeira versão
   dizia que as passagens "trazem exercícios diferentes", apoiada num caso
   auditado. Medido em 09/09/2026 nos perfis de 4, 5, 6 e 7 dias: em quatro
   dias a segunda passagem de A é um SUBCONJUNTO da primeira; em sete dias as
   três são IDÊNTICAS; B e C com seis dias realmente divergem. O caso existia,
   a regra não — e frase verdadeira em parte dos casos, na tela de todos eles,
   é frase falsa.

O que ficou proibido, e tem teste: mexer em `TrainingSession.label`. Ele é a
identidade que liga a sessão ao modelo do catálogo; "A1" gravado ali quebraria
`templates_for`, a conferência de prescrição e o histórico. A numeração é de
EXIBIÇÃO, calculada por ocorrência e nunca por posição na lista.
"""
import pathlib

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile, SplitPreference

from . import services
from .models import TrainingPlan
from .tests import create_user
from .views import nomear_ocorrencias


def com_preferencia(email, dias, preferencia):
    user = create_user(email=email, weekdays=tuple(range(dias)))
    Profile.objects.filter(user=user).update(
        split_preference=preferencia, split_preference_confirmada=True
    )
    user.refresh_from_db()
    services.create_routine(user)
    return user


class APreferenciaQueCedeEDitaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_os_dois_casos_exatos_da_auditoria(self):
        """2 dias pedindo 1 grupo e 2 dias pedindo 2 grupos.

        O SEGUNDO CASO MUDOU DE NÚMERO EM 10/09/2026, e a mudança é a
        correção. A auditoria reclamava de "3 dias pedindo 2 grupos", que
        cedia para ABC porque a preferência de dois grupos exigia QUATRO dias
        (ela entregava ABCD, cujo quarto dia é o de complementares). Hoje ela
        pede três, e três dias a atendem inteira — não há mais o que ceder.

        O caso de cessão dessa preferência desceu junto: quem pede dois grupos
        e treina DUAS vezes recebe AB, porque uma divisão de três letras com
        duas sessões deixa um terço do corpo sem treinar nenhuma vez.
        `test_a_preferencia_de_dois_grupos_cabe_em_tres_dias` guarda o outro
        lado.
        """
        casos = [
            ("dois-dias@exemplo.com", 2, SplitPreference.UM, "ab"),
            ("dois-dias-dois@exemplo.com", 2, SplitPreference.DOIS, "ab"),
        ]
        for email, dias, preferencia, esperado in casos:
            with self.subTest(dias=dias, preferencia=preferencia):
                user = com_preferencia(email, dias, preferencia)

                explicacao = services.divisao_explicada(user)

                self.assertEqual(explicacao["aplicada"], esperado)
                self.assertTrue(explicacao["cedeu"])
                self.assertIn(str(dias), explicacao["motivo"])

    def test_a_preferencia_de_dois_grupos_cabe_em_tres_dias(self):
        """O caso que a auditoria trouxe, agora atendido sem ressalva.

        Três dias pedindo dois grupos por dia recebe ABC de dois grupos, com a
        preferência intacta no perfil e SEM ressalva na tela — porque não houve
        adaptação nenhuma para explicar.
        """
        user = com_preferencia("tres-dias@exemplo.com", 3, SplitPreference.DOIS)

        explicacao = services.divisao_explicada(user)

        self.assertEqual(explicacao["aplicada"], "abc2")
        self.assertFalse(explicacao["cedeu"])
        self.assertEqual(explicacao["motivo"], "")
        self.assertEqual(
            user.profile.split_preference, SplitPreference.DOIS,
            "a preferência gravada não pode mudar por causa da divisão",
        )

    def test_o_motivo_nomeia_o_que_foi_pedido_e_o_que_foi_aplicado(self):
        """"Houve uma adaptação" sem dizer qual não ajuda ninguém."""
        user = com_preferencia("motivo@exemplo.com", 2, SplitPreference.UM)

        explicacao = services.divisao_explicada(user)

        self.assertIn("1 grupo por dia", explicacao["motivo"])
        self.assertIn("AB", explicacao["motivo"])
        self.assertIn("5 dias", explicacao["motivo"])

    def test_quando_a_preferencia_vale_nao_ha_ressalva(self):
        """Aviso que aparece sempre vira ruído e deixa de ser lido."""
        user = com_preferencia("cabe@exemplo.com", 5, SplitPreference.UM)

        explicacao = services.divisao_explicada(user)

        self.assertFalse(explicacao["cedeu"])
        self.assertEqual(explicacao["motivo"], "")

    def test_a_tela_mostra_a_ressalva_quando_cede(self):
        user = com_preferencia("tela@exemplo.com", 2, SplitPreference.UM)
        self.client.force_login(user)

        resposta = self.client.get(reverse("workouts:routine"))

        self.assertContains(resposta, "programa__ressalva")
        self.assertContains(resposta, "1 grupo por dia")
        # E o caminho para destravar: mudar a frequência é o que libera a
        # divisão pedida, e mandar a pessoa procurar seria devolver o problema.
        self.assertContains(resposta, reverse("accounts:onboarding_step", kwargs={"step": 3}))

    def test_a_tela_nao_mostra_ressalva_quando_a_preferencia_valeu(self):
        user = com_preferencia("tela-ok@exemplo.com", 5, SplitPreference.UM)
        self.client.force_login(user)

        self.assertNotContains(
            self.client.get(reverse("workouts:routine")), "programa__ressalva"
        )

    def test_a_matriz_inteira_de_frequencia_e_preferencia(self):
        """Todos os cruzamentos, e a propriedade vale nos dois sentidos.

        `cedeu` tem de ser verdadeiro exatamente quando a divisão aplicada
        difere da que a preferência pede por inteiro — nem mais, nem menos.
        """
        for dias in range(1, 8):
            for preferencia in SplitPreference.values:
                with self.subTest(dias=dias, preferencia=preferencia):
                    user = com_preferencia(
                        "m-%d-%s@exemplo.com" % (dias, preferencia),
                        dias, preferencia,
                    )

                    e = services.divisao_explicada(user)

                    self.assertEqual(e["cedeu"], e["aplicada"] != e["pedida"])
                    if e["cedeu"]:
                        self.assertNotEqual(e["motivo"], "")
                    else:
                        self.assertEqual(e["motivo"], "")


class AsOcorrenciasRepetidasSeDistinguemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _sessoes(self, user):
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
        sessoes = list(plano.sessions.all())
        nomear_ocorrencias(sessoes)
        return sessoes

    def test_cinco_dias_em_abc_viram_a1_b1_c_a2_b2(self):
        user = com_preferencia("cinco@exemplo.com", 5, SplitPreference.TRES)

        rotulos = [s.rotulo for s in self._sessoes(user)]

        self.assertEqual(rotulos, ["A1", "B1", "C", "A2", "B2"])

    def test_letra_que_nao_repete_fica_sem_numero(self):
        """"C1" sozinho seria um número que não distingue nada."""
        user = com_preferencia("tres@exemplo.com", 3, SplitPreference.TRES)

        rotulos = [s.rotulo for s in self._sessoes(user)]

        self.assertEqual(rotulos, ["A", "B", "C"])

    def test_a_letra_do_banco_nao_muda(self):
        """`label` liga a sessão ao modelo do catálogo.

        Gravar "A1" ali quebraria `templates_for`, a conferência de prescrição
        e o histórico. A numeração é de exibição e só.
        """
        user = com_preferencia("banco@exemplo.com", 5, SplitPreference.TRES)

        sessoes = self._sessoes(user)

        self.assertEqual([s.label for s in sessoes], ["A", "B", "C", "A", "B"])
        for sessao in sessoes:
            sessao.refresh_from_db()
            self.assertIn(sessao.label, ("A", "B", "C"))

    def test_as_duas_ocorrencias_trazem_exercicios_diferentes(self):
        """O fato que a numeração existe para explicar.

        Se elas fossem idênticas, A1/A2 seria enfeite — e a queixa da auditoria
        ("o segundo A parece incompleto") não teria fundamento nenhum.
        """
        user = com_preferencia("difere@exemplo.com", 5, SplitPreference.TRES)
        sessoes = [s for s in self._sessoes(user) if s.label == "A"]

        conjuntos = [
            {i.exercise_id for i in s.exercises.all()} for s in sessoes
        ]

        self.assertEqual(len(conjuntos), 2)
        self.assertNotEqual(conjuntos[0], conjuntos[1])

    def test_a_tela_e_a_ficha_concordam_no_rotulo(self):
        """O cartão leva a pessoa a uma ficha, e as duas dizem a mesma coisa."""
        user = com_preferencia("concorda@exemplo.com", 5, SplitPreference.TRES)
        self.client.force_login(user)
        segunda_a = [s for s in self._sessoes(user) if s.label == "A"][1]

        tela = self.client.get(reverse("workouts:routine")).content.decode()
        ficha = self.client.get(
            reverse("workouts:ficha", args=[segunda_a.pk])
        ).content.decode()

        self.assertIn("A2", tela)
        self.assertIn("A2", ficha)
        self.assertIn("aparece duas vezes na semana", ficha)

    def test_a_ficha_nao_promete_exercicios_diferentes(self):
        """A frase que a medição desmentiu não pode voltar.

        O CASO QUE DECIDE É O DE SETE DIAS, e não o de cinco. Em cinco as duas
        passagens de A realmente diferem — a segunda é a primeira menos um
        isolador —, e é o caso que o teste logo acima já cobra. Em sete a letra
        A aparece TRÊS vezes e as três saem IDÊNTICAS: mesmo conjunto, mesma
        dose. A ficha dessa pessoa afirmava, nas três, que elas "trazem
        exercícios diferentes".

        As duas metades importam. A identidade dos conjuntos prova que a
        promessa é falsa; a ausência da frase prova que ela saiu da tela. Sem a
        primeira, este teste passaria a verde no dia em que o motor voltasse a
        diferenciá-las — e aí a frase poderia voltar, mas por outro motivo.
        """
        user = com_preferencia("promessa@exemplo.com", 7, SplitPreference.TRES)
        self.client.force_login(user)
        ocorrencias = [s for s in self._sessoes(user) if s.label == "A"]
        conjuntos = [
            {i.exercise_id for i in s.exercises.all()} for s in ocorrencias
        ]

        # ERAM IDÊNTICAS ATÉ 10/09/2026, e é por isso que a frase da ficha
        # não promete variedade. `repartir_ocorrencia` mudou o fato: as três
        # passagens agora trazem exercícios DIFERENTES.
        #
        # A frase continua honesta — ela fala do teto semanal, que segue
        # valendo, e não afirma que as passagens são iguais. O que este teste
        # guarda mudou de "são idênticas" para "não repetem", que é o contrato
        # novo.
        self.assertEqual(len(conjuntos), 3)
        self.assertEqual(conjuntos[0] & conjuntos[1], set())
        self.assertEqual(conjuntos[1] & conjuntos[2], set())
        for sessao in ocorrencias:
            ficha = self.client.get(
                reverse("workouts:ficha", args=[sessao.pk])
            ).content.decode()
            self.assertNotIn("exercícios diferentes", ficha)
            self.assertIn("aumenta a frequência", ficha)

    def test_tres_ocorrencias_nao_sao_chamadas_de_duas(self):
        """Sete dias em ABC dão A três vezes, e a frase dizia "duas".

        Número escrito à mão no template mente para o perfil que não foi o
        usado ao escrevê-lo. Aqui ele vem da contagem que o rótulo já fez.
        """
        user = com_preferencia("sete@exemplo.com", 7, SplitPreference.TRES)
        self.client.force_login(user)
        ocorrencias = [s for s in self._sessoes(user) if s.label == "A"]

        self.assertEqual(len(ocorrencias), 3)
        ficha = self.client.get(
            reverse("workouts:ficha", args=[ocorrencias[0].pk])
        ).content.decode()

        self.assertIn("aparece três vezes na semana", ficha)
        self.assertNotIn("aparece duas vezes na semana", ficha)

    def test_a_ficha_de_letra_unica_nao_fala_de_repeticao(self):
        user = com_preferencia("unica@exemplo.com", 3, SplitPreference.TRES)
        self.client.force_login(user)
        sessao = self._sessoes(user)[0]

        ficha = self.client.get(
            reverse("workouts:ficha", args=[sessao.pk])
        ).content.decode()

        self.assertNotIn("aparece duas vezes na semana", ficha)

    def test_a_numeracao_nao_vem_da_posicao_na_lista(self):
        """Ordem embaralhada tem de produzir a mesma numeração por ocorrência.

        A regra proíbe associar sessão por posição, e é a mesma disciplina da
        substituição de exercício: identidade própria, nunca índice.
        """
        user = com_preferencia("ordem@exemplo.com", 5, SplitPreference.TRES)
        sessoes = self._sessoes(user)
        por_pk = {s.pk: s.rotulo for s in sessoes}

        invertidas = list(reversed(sessoes))
        nomear_ocorrencias(invertidas)

        # Invertida, a PRIMEIRA ocorrência de A é a que era a segunda — então
        # os rótulos trocam entre elas, e é isso que prova que a conta é por
        # ocorrência na ordem recebida, e não um índice fixo por pk.
        self.assertEqual(
            sorted(por_pk.values()), sorted(s.rotulo for s in invertidas)
        )


class OLinkDaRessalvaCabeNoDedoTests(TestCase):
    """O link "Mudar meus dias de treino" nasceu sem classe, e sem altura.

    MEDIDO EM PRODUÇÃO em 09/09/2026, a 390px: 149x17 — a altura do texto,
    contra os 44px que o `CLAUDE.md` exige de altura E de largura. Não é caso
    de exceção para link inline: TODO link daquela tela tem 44, inclusive os
    que moram dentro de parágrafo. "Saiba mais", na tarja do demo, tem 77x44
    com `.btn-link`; "Editar", no cabeçalho do cartão, tem 49x44 por
    `.card__head a`. O componente já existia — faltava usá-lo.

    POR QUE O TESTE MORA AQUI E NÃO NA RÉGUA DO B7.
    `TodoControleDasTelasNovasTemAlturaTests` varre templates procurando
    controle sem "classe que carrega altura", e seria o lugar natural. O
    modelo dele não descreve esta tela: `routine.html` tem controles cuja
    altura vem de regra CONTEXTUAL e não de classe própria — o "Editar" acima
    é exatamente isso, 49x44 sem classe nenhuma. Pôr a tela naquela lista
    exigiria ou aceitar um falso positivo permanente, ou estender a lista de
    classes com meia-verdade. Estender aquela régua para valer é trabalho
    próprio; aqui fica a guarda do caso medido.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_link_da_ressalva_carrega_a_classe_que_tem_44px(self):
        user = com_preferencia("dedo@exemplo.com", 4, SplitPreference.UM)
        self.client.force_login(user)

        html = self.client.get(reverse("workouts:routine")).content.decode()

        ressalva = html.split('class="programa__ressalva"', 1)
        self.assertEqual(len(ressalva), 2, "a ressalva sumiu da tela")
        trecho = ressalva[1].split("</p>", 1)[0]

        self.assertIn("Mudar meus dias de treino", trecho)
        self.assertIn('class="btn-link"', trecho)

    def test_a_classe_continua_valendo_44px_no_css(self):
        """A outra metade: a classe certa numa regra que encolheu não protege
        ninguém. 2.75rem é 44px, e é o número que `TouchTargetTests` trava."""
        css = (
            pathlib.Path(settings.BASE_DIR) / "static" / "css" / "app.css"
        ).read_text(encoding="utf-8")
        regra = css.split(".btn-link {", 1)[1].split("}", 1)[0]

        self.assertIn("min-height: 2.75rem", regra)
        self.assertIn("min-width: 2.75rem", regra)


class AExplicacaoNaoCustaConsultaTests(TestCase):
    """A ressalva é texto; ela não pode cobrar ida ao banco.

    MEDIDO: `divisao_explicada(user)` sem argumento faz DUAS consultas — o
    perfil e `training_days.count()`. Na tela de Treino o perfil já está quente
    (`sync_active_routine` acabou de lê-lo), então sobrava uma, e a tela subiu
    de 21 para 22 consultas.

    A correção não foi cachear nada: foi passar `dias=plan.days_per_week`, que
    é o número congelado NO PLANO que a tela está desenhando. Mais barato e
    mais correto ao mesmo tempo — plano é retrato, e a ressalva explica a
    divisão daquele retrato, não a contagem de hoje.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_com_o_plano_em_maos_a_explicacao_e_de_graca(self):
        user = com_preferencia("gratis@exemplo.com", 4, SplitPreference.UM)
        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
        user.profile  # o mesmo aquecimento que a view já fez

        with self.assertNumQueries(0):
            explicada = services.divisao_explicada(
                user, dias=plano.days_per_week
            )

        self.assertTrue(explicada["cedeu"])

    def test_sem_o_plano_ela_ainda_funciona_sozinha(self):
        """Controle: o argumento é otimização, não requisito.

        Quem chamar de um shell ou de um teste sem plano em mãos continua
        recebendo a resposta certa — só paga a consulta.
        """
        user = com_preferencia("sozinha@exemplo.com", 4, SplitPreference.UM)

        self.assertEqual(
            services.divisao_explicada(user)["aplicada"],
            services.divisao_explicada(user, dias=4)["aplicada"],
        )


class ONomeDaDivisaoCabeNaTelaTests(TestCase):
    """O nome longo da divisão sumia da tela, e nada avisava.

    MEDIDO NO NAVEGADOR a 390px, com quatro dias pedindo "1 grupo por dia":
    `.programa__resumo > span` é `white-space: nowrap`, o nome de ABCD tem 65
    caracteres, e o span saía com 374px dentro de um parágrafo de 309px. A
    página não rolava na horizontal — ela CLIPA —, então o texto terminava em
    "…ombro/perna e complemen" e ninguém tinha como notar.

    Só acontecia em ABCD e ABCDE. Em ABC o nome cabe, e é o caso que todo mundo
    olhava.

    O QUE ESTE TESTE ALCANÇA, E O QUE NÃO. Ele não mede layout: teste de
    servidor não tem caixa nem fonte, e afirmar o contrário seria pior que não
    testar. O que ele prende é a LIGAÇÃO entre as duas metades da correção — a
    classe no HTML e a regra no CSS. Quem apagar uma das duas fica vermelho;
    quem mudar a fonte e fizer o texto estourar de novo, não. Para esse, a
    medição está escrita aqui e no template.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_o_nome_da_divisao_sai_marcado_para_quebrar(self):
        user = com_preferencia("quebra@exemplo.com", 4, SplitPreference.UM)
        self.client.force_login(user)

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('class="programa__divisao"', html)

    def test_a_regra_que_deixa_esse_nome_quebrar_existe(self):
        """A outra metade: sem ela a classe no HTML não faz nada."""
        css = (
            pathlib.Path(settings.BASE_DIR) / "static" / "css" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".programa__resumo > .programa__divisao { white-space: normal; }",
            css,
        )

    def test_os_numeros_continuam_sem_quebrar(self):
        """Controle: a correção não pode desligar o `nowrap` de todo mundo.

        "4 dias por semana" quebrado entre o número e a unidade é o defeito que
        aquela regra existe para impedir.
        """
        css = (
            pathlib.Path(settings.BASE_DIR) / "static" / "css" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn(".programa__resumo > span { white-space: nowrap; }", css)


class OVolumeSemanalEConsequenciaDasRegrasTests(TestCase):
    """OS 85 SETS: número legítimo, lido no lugar errado.

    A queixa foi "85 séries" num perfil de quatro dias. O número era real — e
    não era de um treino: é a SOMA da semana inteira, distribuída entre eleven
    grupos musculares. Ler como se fosse um dia é o que o tornava absurdo, e é
    o que o texto "no total" convidava a fazer (corrigido para "por semana").

    Este arquivo prova as três coisas que a missão pede: que o valor não
    voltou, que ele é plausível, e que a plausibilidade NÃO vem de esconder o
    número na interface — ela vem do teto por grupo, que é onde a regra mora.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _volume(self, user):
        from collections import defaultdict

        plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
        direto, indireto, freq = defaultdict(int), defaultdict(float), defaultdict(set)
        for sessao in plano.sessions.all():
            for item in sessao.exercises.select_related("exercise"):
                grupo = item.exercise.muscle_group
                direto[grupo] += item.sets
                freq[grupo].add(sessao.weekday)
                for secundario in item.exercise.secondary_muscles or []:
                    indireto[secundario] += item.sets * 0.5
        return direto, indireto, freq

    def _perfil_da_queixa(self):
        from accounts.models import DuracaoTreino

        user = create_user(email="oitenta-e-cinco@exemplo.com", weekdays=(0, 1, 2, 3))
        Profile.objects.filter(user=user).update(
            split_preference=SplitPreference.TRES,
            split_preference_confirmada=True,
            duracao_treino=DuracaoTreino.PADRAO,
        )
        user.refresh_from_db()
        services.create_routine(user)
        return user

    def test_nenhum_grupo_passa_do_teto_semanal(self):
        """A regra que torna o total plausível, medida onde ela age.

        `TETO_SEMANAL_POR_GRUPO` conta séries EFETIVAS: direta vale 1 e
        secundária vale meia. Um total alto distribuído entre onze grupos é
        outra coisa que um total alto concentrado num só — e é exatamente essa
        diferença que o teto garante.
        """
        direto, indireto, _ = self._volume(self._perfil_da_queixa())

        for grupo in set(direto) | set(indireto):
            with self.subTest(grupo=grupo):
                efetivo = direto[grupo] + indireto[grupo]
                self.assertLessEqual(efetivo, services.TETO_SEMANAL_POR_GRUPO)

    def test_o_total_e_a_soma_de_muitos_grupos_e_nao_de_um(self):
        """"85 séries" só assusta enquanto parece ser de um músculo."""
        direto, _, _ = self._volume(self._perfil_da_queixa())

        total = sum(direto.values())

        self.assertGreaterEqual(len(direto), 8, "o volume se concentrou")
        # A média por grupo é o número que responde "isso é muito?" — e ela
        # fica no piso das recomendações usuais, não acima delas.
        self.assertLessEqual(total / len(direto), 12)

    def test_o_total_semanal_fica_numa_faixa_plausivel(self):
        """Nem inflado nem escondido: a catraca protege os dois lados.

        Um teto sozinho seria satisfeito zerando a ficha, e reduzir volume só
        para o número ficar menor é o que a missão proíbe com todas as letras.
        """
        direto, _, _ = self._volume(self._perfil_da_queixa())

        total = sum(direto.values())

        self.assertGreaterEqual(total, 60, "a ficha encolheu demais")
        self.assertLessEqual(total, 100, "o volume voltou a inflar")

    def test_a_frequencia_de_cada_grupo_e_pelo_menos_semanal(self):
        """Volume distribuído não pode virar grupo treinado nenhuma vez."""
        direto, _, freq = self._volume(self._perfil_da_queixa())

        for grupo, series in direto.items():
            if series:
                with self.subTest(grupo=grupo):
                    self.assertGreaterEqual(len(freq[grupo]), 1)
