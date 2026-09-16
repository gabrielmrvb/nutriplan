"""TREINO — o fluxo é painel, ficha, exercício, Short. Nessa ordem.

O QUE ESTAVA ERRADO, e é uma coisa só com três consequências: "Começar treino"
abria DIRETO o primeiro exercício pendente, com o vídeo dele já tocando. A
pessoa tocava num botão para começar e caía dentro de um movimento sem ter
visto o treino — sem saber quantos exercícios eram, o que vinha depois, nem
poder escolher outro para abrir.

O fluxo agora é:

    Treino -> card de hoje -> Começar treino
           -> FICHA completa (preparação e seleção)
           -> a pessoa escolhe o exercício
           -> execução -> Short

E cada tela responde uma pergunta: o painel diz "o que tem hoje", a ficha diz
"o que tem nesse treino", a execução diz "como eu faço isto agora".
"""
from datetime import time, timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, Profile, SplitPreference, TrainingDay

from . import services
from .models import ExerciseLog, TrainingPlan, TrainingSession
from .tests import create_user


def pessoa(email, weekdays=(0, 1, 2, 3, 4, 5, 6)):
    """Treina TODO dia, para a sessão de hoje existir seja qual for o dia.

    Um fixture com seg/qua/sex faria metade dos testes deste arquivo passar por
    acidente às terças — a tela de descanso não tem CTA, não tem lista e não
    abre exercício nenhum, então tudo o que se afirma sobre elas seria
    vacuamente verdadeiro.
    """
    user = create_user(email=email, weekdays=weekdays)
    Profile.objects.filter(user=user).update(
        split_preference=SplitPreference.DOIS,
        split_preference_confirmada=True,
        duracao_treino=DuracaoTreino.PADRAO,
    )
    user.refresh_from_db()
    services.create_routine(user)
    return user


class BaseDoFluxo(TestCase):
    """Catálogo semeado uma vez por classe.

    `create_user` cria a PESSOA, não o catálogo — e sem `seed_workouts` a
    divisão `abc2` não existe, então `create_routine` levanta `NoTrainingDays`
    antes de qualquer asserção. `setUpTestData` roda uma vez por classe e o
    comando é idempotente.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)


def tornar_hoje(user, letra):
    """Coloca a primeira ocorrência de `letra` no dia de hoje. Devolve a sessão.

    POR QUE ISTO EXISTE, e é a correção de três `skipTest` que eu tinha escrito.
    Os testes de complementar, de peso corporal e de IDOR liam "a sessão de
    hoje" — e o que hoje é depende do dia em que a suíte roda. Numa quinta a
    sessão era `A2`, com dois exercícios, sem complementar e sem nada de peso
    corporal: os três testes pulavam. Numa quarta, `C1`, e os três rodavam.

    Cobertura que muda com o calendário é pior que cobertura ausente: ela passa
    verde no dia em que ninguém olha e some no dia em que o defeito entra. E o
    skip mentia sobre a causa — o catálogo TEM prancha e TEM complementar; o
    que faltava era a sessão certa cair hoje.

    A troca é de `weekday`, e precisa de três passos por causa de
    `unique_session_per_weekday`: o dia de hoje é liberado para um valor que
    ninguém usa antes de a sessão desejada assumi-lo.
    """
    hoje = timezone.localdate()
    plano = user.training_plans.get(is_active=True)
    linhas = list(plano.sessions.all())
    letras = services.letras_do_ciclo(linhas)
    assert letra in letras, "a divisão não tem a letra %s" % letra
    if services.ciclo_roda(plano):
        # COM A ROTAÇÃO A LETRA É DA POSIÇÃO, não do dia da semana: em vez de
        # trocar `weekday` entre linhas, move-se a posição zero do ciclo para
        # uma data em que hoje caia na letra pedida. A sessão devolvida é a
        # da letra vestindo hoje (`sessao_do_dia`).
        dias = services.dias_de_treino_de(linhas)
        assert hoje.weekday() in dias, "hoje precisa ser dia de treino"
        alvo = letras.index(letra)
        for atras in range(0, 8 * len(dias)):
            candidato = hoje - timedelta(days=atras)
            if candidato.weekday() not in dias:
                continue
            if services.posicao_no_ciclo(candidato, hoje, dias) % len(letras) == alvo:
                TrainingPlan.objects.filter(pk=plano.pk).update(inicio_do_ciclo=candidato)
                plano.inicio_do_ciclo = candidato
                return services.sessao_do_dia(plano, hoje)
        raise AssertionError("não achei posição zero para %s cair hoje" % letra)

    # Plano preso ao dia da semana: a troca de `weekday` de sempre, em três
    # passos por causa de `unique_session_per_weekday`.
    hoje = hoje.weekday()
    alvo = plano.sessions.filter(label=letra).order_by("weekday").first()
    if alvo.weekday == hoje:
        return alvo

    ocupante = plano.sessions.filter(weekday=hoje).first()
    livre = 99
    if ocupante is not None:
        TrainingSession.objects.filter(pk=ocupante.pk).update(weekday=livre)
    TrainingSession.objects.filter(pk=alvo.pk).update(weekday=hoje)
    if ocupante is not None:
        TrainingSession.objects.filter(pk=ocupante.pk).update(
            weekday=alvo.weekday
        )
    return plano.sessions.get(pk=alvo.pk)


def sessao_de_hoje(user):
    """A sessão de hoje como o app a resolve — pela LETRA da posição no
    ciclo (`sessao_do_dia`), não pelo dia da semana da linha."""
    plano = TrainingSession.objects.filter(plan__user=user, plan__is_active=True).first().plan
    sessao = services.sessao_do_dia(plano, timezone.localdate())
    assert sessao is not None, "hoje precisa ser dia de treino"
    return sessao


def escolher_a_opcao_1(user, sessao):
    """Grava a escolha de hoje — o que "Começar esta opção" faz na ficha.

    Desde 15/09/2026 a letra tem até duas versões, e `/treino/agora/` com
    duas opções e nenhuma escolha REDIRECIONA para a ficha: a execução não
    decide por ninguém. Todo teste que abre a execução direto passa por aqui
    primeiro, e mede a opção 1 — a que a ficha lista primeiro.
    """
    services.registrar_escolha(user, sessao, 1)
    return sessao.da_opcao(1)


class OPainelNaoDespejaAListaTests(BaseDoFluxo):
    """A tela de Treino é painel, e a lista mora na ficha."""

    def setUp(self):
        self.user = pessoa("painel@exemplo.com")
        self.client.force_login(self.user)

    def test_a_tela_principal_nao_renderiza_a_lista_de_exercicios(self):
        """Nem a de hoje, nem a da semana.

        Ela já desenhou o cartão completo de TODO exercício de TODA sessão —
        259 kB, 141 botões, 29 sanfonas no perfil de seis dias. O detalhe mudou
        de página em 09/09/2026, e este teste é a trava para ele não voltar:
        o que se conta é a estrutura da lista, não uma string do template.
        """
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertNotIn('class="exercise-list"', html)
        self.assertNotIn("exercise__head", html)
        # E nenhum nome de exercício da ficha de hoje aparece solto na tela.
        for item in sessao_de_hoje(self.user).exercises.select_related("exercise"):
            self.assertNotIn(item.exercise.name, html, item.exercise.name)

    def test_a_tela_principal_nao_traz_iframe_nem_gaveta_de_video(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertNotIn("<iframe", html)
        # Os marcadores, e não a palavra: `data-drawer` é o atributo que a
        # gaveta usa, e `data-clipe` é o do botão que a abre. Procurar a string
        # "iframe" sozinha encontraria o comentário dentro do `<script>` do
        # drawer — a armadilha que o `CLAUDE.md` registra.
        # O ATRIBUTO COM VALOR, e não o token solto: `[data-descanso]` também
        # aparece como SELETOR dentro do `<script>` desta página, e uma
        # asserção sobre a palavra encontraria o JavaScript em vez do elemento.
        # É a armadilha que o `CLAUDE.md` registra, e ela já reprovou este
        # teste uma vez.
        self.assertNotIn("data-clipe=", html)
        self.assertNotIn("data-drawer>", html)
        self.assertNotIn("data-descanso=", html)
        self.assertNotIn("<dialog", html)

    def test_o_horario_do_treino_nao_aparece_na_area_de_treino(self):
        """"19:00" repetido em todo cartão nunca ajudou a executar nada.

        O horário jamais participou da montagem da ficha — `create_routine`
        nunca leu `start_time` —, e na maioria das contas ele era o padrão de
        fábrica que ninguém escolheu. O VALOR continua no banco porque
        `plans/meal_planner.py` o usa; o que saiu é a exibição.
        """
        TrainingDay.objects.filter(user=self.user).update(start_time=time(19, 0))

        for rota in ("workouts:routine", "accounts:profile"):
            with self.subTest(rota=rota):
                html = self.client.get(reverse(rota)).content.decode()
                self.assertNotIn("19:00", html)

        # E o dado continua lá, intocado.
        self.assertTrue(
            all(d.start_time == time(19, 0) for d in self.user.training_days.all())
        )


class ComecarTreinoAbreAFichaTests(BaseDoFluxo):
    """O CTA da tela principal, e o que ele NÃO faz."""

    def setUp(self):
        self.user = pessoa("cta@exemplo.com")
        self.client.force_login(self.user)
        self.sessao = sessao_de_hoje(self.user)

    def test_o_cta_aponta_para_a_ficha_e_nao_para_a_execucao(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()
        ficha = reverse("workouts:ficha", args=[self.sessao.pk])

        self.assertIn('href="%s"' % ficha, html)
        # A âncora do CTA é a da ficha; a execução não é destino de botão nesta
        # tela. `agora` continua existindo — quem chega nela vem da ficha.
        inicio = html.index("data-hoje-cta")
        trecho = html[max(0, inicio - 400):inicio]
        self.assertIn(ficha, trecho)
        self.assertNotIn(reverse("workouts:now"), trecho)

    def test_abrir_a_ficha_nao_registra_progresso_nem_serie(self):
        """Ver não é fazer.

        A ficha é tela de preparação: ela lê `ExerciseLog` e não escreve nada.
        Um GET que criasse registro faria o progresso subir por navegação, e a
        pessoa veria "1 de 7 exercícios" sem ter levantado peso nenhum.
        """
        antes = ExerciseLog.objects.filter(user=self.user).count()

        self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))
        self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))

        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), antes)

    def test_abrir_um_exercicio_nao_registra_serie(self):
        """Entrar na execução também não escreve — quem escreve é o botão."""
        item = self.sessao.exercises.first()
        antes = ExerciseLog.objects.filter(user=self.user).count()

        self.client.get(
            reverse("workouts:now") + "?exercicio=%d" % item.exercise_id
        )

        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), antes)


class AFichaEAPreparacaoTests(BaseDoFluxo):
    """A ficha lista, numera e leva para o exercício."""

    def setUp(self):
        self.user = pessoa("ficha@exemplo.com")
        self.client.force_login(self.user)
        self.sessao = sessao_de_hoje(self.user)
        self.html = self.client.get(
            reverse("workouts:ficha", args=[self.sessao.pk])
        ).content.decode()

    def test_cada_exercicio_tem_porta_para_a_execucao(self):
        """Cada exercício da OPÇÃO ESCOLHIDA leva à execução; a outra opção se
        compara, não se executa.

        Desde 15/09/2026 a letra tem até duas versões e "Fazer" só existe na
        escolhida de hoje — sem escolha gravada a ficha não abre porta
        nenhuma, porque a execução ainda não sabe que treino é. O teste grava
        a escolha da opção 1, como o botão "Começar esta opção" faz.
        """
        services.registrar_escolha(self.user, self.sessao, 1)
        html = self.client.get(
            reverse("workouts:ficha", args=[self.sessao.pk])
        ).content.decode()
        escolhida = self.sessao.da_opcao(1)
        for item in escolhida:
            with self.subTest(exercicio=item.exercise.name):
                self.assertIn(
                    "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id),
                    html,
                )
        # O que só está na outra opção não tem porta: executar é da escolhida.
        so_na_outra = [
            item for opcao in self.sessao.opcoes[1:]
            for item in self.sessao.da_opcao(opcao)
            if item.exercise_id not in {i.exercise_id for i in escolhida}
        ]
        for item in so_na_outra:
            with self.subTest(exercicio=item.exercise.name, opcao="outra"):
                self.assertNotIn(
                    "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id),
                    html,
                )

    def test_a_ficha_e_LEVE_e_nao_carrega_o_que_e_da_execucao(self):
        """O contrato da tela de preparação, item por item.

        A ficha montava trinta e poucos `<details>` com botão de vídeo,
        formulário de carga, pastilhas de série, gatilho de descanso e
        comparação de peso — abertos ao mesmo tempo, para uma pessoa que ainda
        não escolheu o que vai fazer. Tudo isso é da EXECUÇÃO, e
        `ACargaContinuaNaExecucaoTests` e `ACargaAnteriorNaoViraRecomendacaoTests`
        provam que continua funcionando lá.

        Cada asserção aqui corresponde a uma coisa que saiu:

            iframe / data-clipe   -> vídeo, agora inline na execução
            data-drawer           -> a gaveta que aqueles botões abriam
            name="weight_kg"      -> registro de carga
            data-descanso         -> o cronômetro
            exercise__previous    -> a comparação com o último treino
        """
        self.assertNotIn("<iframe", self.html)
        self.assertNotIn("data-clipe", self.html)
        self.assertNotIn("data-drawer", self.html)
        self.assertNotIn('name="weight_kg"', self.html)
        self.assertNotIn("data-descanso", self.html)
        self.assertNotIn("exercise__previous", self.html)
        # E o que ficou é a lista.
        self.assertIn("ficha-item", self.html)

    def test_a_numeracao_continua_entre_principais_e_complementares(self):
        """O complementar é o oitavo do dia, não o primeiro de outra coisa."""
        # A LETRA C É A QUE TEM COMPLEMENTAR no `abc2` — panturrilha, glúteo e
        # abdômen moram no dia de pernas. Sem forçá-la para hoje, este teste
        # rodava só nos dias em que C calhava de ser o treino do dia.
        sessao = tornar_hoje(self.user, "C")
        html = self.client.get(
            reverse("workouts:ficha", args=[sessao.pk])
        ).content.decode()
        # POR OPÇÃO: a ficha desenha cada versão da letra como uma lista
        # própria, numerada do 1, e dentro de cada uma o complementar continua
        # a numeração dos principais.
        esperados = []
        for opcao in sessao.opcoes:
            principais = sessao.principais_da_opcao(opcao)
            complementares = sessao.complementares_da_opcao(opcao)
            self.assertTrue(
                complementares,
                "o dia de pernas deixou de trazer complementar na opção %d" % opcao,
            )
            esperados += list(range(1, len(principais) + len(complementares) + 1))
            # E o `<ol>` dos complementares COMEÇA onde o dos principais
            # parou: sem o `start`, o navegador recomeçaria do 1 e o oitavo
            # exercício do dia se apresentaria como primeiro de outra coisa.
            self.assertIn('start="%d"' % (len(principais) + 1), html)

        vistos = [
            int(t.split("</span>")[0])
            for t in html.split(
                '<span class="ficha-item__ordem num" aria-hidden="true">'
            )[1:]
        ]
        self.assertEqual(vistos, esperados)

    def test_a_linha_diz_nome_series_reps_e_musculo(self):
        """O que a ficha precisa apresentar, sem abrir nada."""
        for item in self.sessao.exercises.select_related("exercise"):
            with self.subTest(exercicio=item.exercise.name):
                self.assertIn(item.exercise.name, self.html)
                self.assertIn(item.rep_range, self.html)
                self.assertIn(item.exercise.get_muscle_group_display(), self.html)

    def test_o_movimento_principal_tem_marcador_discreto(self):
        # Toda sessão do `abc2` tem composto — A abre com supino, B com barra
        # fixa, C com agachamento —, então este `skipTest` era inalcançável
        # por construção e mesmo assim tinha a forma do defeito que este
        # arquivo já pagou três vezes: guarda que depende do calendário. Vira
        # asserção: se um dia a sessão de hoje não tiver composto, isso é um
        # fato sobre o catálogo que precisa aparecer, e não sumir num skip.
        compostos = [
            i for i in self.sessao.exercises.select_related("exercise")
            if i.exercise.is_compound
        ]
        self.assertTrue(compostos, "a sessão de hoje ficou sem movimento composto")

        self.assertIn("ficha-item__papel", self.html)
        self.assertIn(">Principal<", self.html)

    def test_o_selo_principal_e_um_por_grupo_anunciado_em_cada_opcao(self):
        """O PRIMEIRO composto de cada grupo anunciado, por opção — e só ele
        (17/09/2026). Com 63 ativos "Peito e tríceps" tem quatro pressões de
        peito por opção; marcando todo composto, "Principal" aparecia em
        cinco de sete linhas e deixava de dizer por onde começar."""
        from workouts import services

        esperados = 0
        for opcao in self.sessao.opcoes:
            itens = self.sessao.da_opcao(opcao)
            anunciados = set(self.sessao.main_groups)
            grupos_com_composto = {
                i.exercise.muscle_group for i in itens
                if i.exercise.is_compound and i.exercise.muscle_group in anunciados
            }
            esperados += len(grupos_com_composto)
            services.marcar_quem_abre_o_grupo(itens, self.sessao.main_groups)
            marcados = [i for i in itens if i.abre_o_grupo]
            # Um por grupo anunciado, e é o PRIMEIRO composto do grupo.
            self.assertEqual(len(marcados), len(grupos_com_composto))
            for grupo in grupos_com_composto:
                primeiro = next(i for i in itens if i.exercise.is_compound and i.exercise.muscle_group == grupo)
                self.assertTrue(primeiro.abre_o_grupo, primeiro.exercise.name)
            # Composto que NÃO abre o grupo fica sem selo, mesmo sendo composto.
            for i in itens:
                if i.exercise.is_compound and i not in marcados:
                    self.assertFalse(i.abre_o_grupo, i.exercise.name)
        self.assertGreater(esperados, 0)
        self.assertEqual(self.html.count(">Principal<"), esperados)
        compostos_na_tela = sum(
            1 for opcao in self.sessao.opcoes for i in self.sessao.da_opcao(opcao) if i.exercise.is_compound
        )
        # Controle positivo: há mais compostos que selos, senão o teste não
        # distingue "primeiro composto" de "todo composto".
        self.assertGreater(compostos_na_tela, esperados)


class AEscolhaDoExercicioEEstritaTests(BaseDoFluxo):
    """Pedido inválido REJEITA. Nunca "abre outro".

    O DEFEITO QUE ISTO FECHA nasceu com a própria escolha: a primeira versão
    fazia `pedido or atual`, e o silêncio era o problema. Um link velho, um id
    de outra sessão ou um id de outra conta abriam a tela do PRIMEIRO PENDENTE
    — com o vídeo dele tocando — como se nada tivesse acontecido. A pessoa via
    um exercício que não pediu e não tinha como saber; e um link quebrado que
    "funciona" nunca é consertado.
    """

    def setUp(self):
        self.user = pessoa("escolha@exemplo.com")
        self.client.force_login(self.user)
        self.sessao = sessao_de_hoje(self.user)
        # `meus` são TODOS os exercícios da sessão de hoje (as duas opções),
        # para excluir o que é de outra sessão; `escolhidos` são os da opção
        # que a execução vai abrir.
        self.meus = [i.exercise_id for i in self.sessao.exercises.all()]
        self.escolhidos = [i.exercise_id for i in escolher_a_opcao_1(self.user, self.sessao)]
        self.url = reverse("workouts:now")

    def _corpo(self, resposta):
        return resposta.content.decode("utf-8", "replace")

    def test_sem_parametro_continua_abrindo_o_proximo_pendente(self):
        """O caminho de "Continuar de onde parou" não mudou."""
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.sessao.da_opcao(1)[0].exercise.name)

    def test_com_id_valido_abre_exatamente_o_escolhido(self):
        escolhido = self.sessao.da_opcao(1)[-1]

        resposta = self.client.get(self.url + "?exercicio=%d" % escolhido.exercise_id)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, escolhido.exercise.name)
        # O poster do escolhido, e não um iframe: o player nasce no toque.
        corpo = self._corpo(resposta)
        self.assertEqual(corpo.count("<iframe"), 0)
        self.assertEqual(corpo.count("data-demo" + chr(10)), 1)
        self.assertIn('data-nome="%s"' % escolhido.exercise.name, corpo)

    def test_id_inexistente_devolve_404_sem_iframe(self):
        resposta = self.client.get(self.url + "?exercicio=999999")

        self.assertEqual(resposta.status_code, 404)
        self.assertNotIn("<iframe", self._corpo(resposta))

    def test_id_so_da_outra_opcao_devolve_404(self):
        """A opção não escolhida se compara, não se executa.

        Um exercício que só existe na outra versão da letra não é "do treino
        de hoje": abri-lo pela URL cairia no mesmo silêncio que este arquivo
        proíbe — a execução de um movimento que a pessoa não escolheu.
        """
        so_da_outra = [
            i.exercise_id
            for opcao in self.sessao.opcoes[1:]
            for i in self.sessao.da_opcao(opcao)
            if i.exercise_id not in self.escolhidos
        ]
        if not so_da_outra:
            self.skipTest("a letra de hoje não tem exercício exclusivo da outra opção")

        resposta = self.client.get(self.url + "?exercicio=%d" % so_da_outra[0])

        self.assertEqual(resposta.status_code, 404)

    def test_id_de_outra_sessao_devolve_404(self):
        """Exercício da terça não abre na quinta, mesmo sendo da própria pessoa."""
        outra = (
            TrainingSession.objects.filter(plan__user=self.user, plan__is_active=True)
            .exclude(pk=self.sessao.pk)
            .first()
        )
        de_fora = next(
            (
                i.exercise_id
                for i in outra.exercises.all()
                if i.exercise_id not in self.meus
            ),
            None,
        )
        if de_fora is None:
            self.skipTest("as sessões desta semana não têm exercício exclusivo")

        resposta = self.client.get(self.url + "?exercicio=%d" % de_fora)

        self.assertEqual(resposta.status_code, 404)

    def test_id_de_outra_pessoa_devolve_404(self):
        """O mesmo fechamento de IDOR que a ficha faz, e vem de graça.

        `estado_do_treino` só enxerga a sessão de hoje do PRÓPRIO usuário —
        então "não é seu" e "não existe" são a mesma resposta, e nenhuma delas
        vaza que o exercício existe na conta de outra pessoa.
        """
        # A OUTRA PESSOA TREINA OUTRA LETRA HOJE, e é isso que garante um
        # exercício exclusivo dela. Com as duas em `A2` — o que acontecia às
        # quintas — as fichas eram idênticas e o teste pulava: o IDOR ficava
        # sem guarda no dia em que as duas coincidiam. E "outra letra" é
        # RELATIVA à minha: fixar "C" repetia o defeito às quartas, quando a
        # minha sessão de hoje também é C (visto em 16/09/2026).
        alheia = pessoa("outra@exemplo.com")
        sessao_alheia = tornar_hoje(alheia, "C" if self.sessao.label != "C" else "A")
        alheios = [
            i.exercise_id
            for i in sessao_alheia.exercises.all()
            if i.exercise_id not in self.meus
        ]
        self.assertTrue(alheios, "as duas fichas ficaram idênticas")

        resposta = self.client.get(self.url + "?exercicio=%d" % alheios[0])

        self.assertEqual(resposta.status_code, 404)

    def test_parametro_adulterado_devolve_404(self):
        """Ilegível, vazio, negativo e REPETIDO — os quatro são o mesmo caso.

        O repetido é o que mais engana: `request.GET.get()` devolve o último
        valor sem reclamar, então `?exercicio=1&exercicio=2` abriria o segundo
        em silêncio. Pedido ambíguo não é pedido claro.
        """
        casos = [
            "?exercicio=abc",
            "?exercicio=",
            "?exercicio=-3",
            "?exercicio=%d&exercicio=%d" % (self.escolhidos[0], self.escolhidos[-1]),
        ]
        for consulta in casos:
            with self.subTest(consulta=consulta):
                resposta = self.client.get(self.url + consulta)

                self.assertEqual(resposta.status_code, 404)
                self.assertNotIn("<iframe", self._corpo(resposta))

    def test_pedido_invalido_nao_registra_nada(self):
        antes = ExerciseLog.objects.filter(user=self.user).count()

        self.client.get(self.url + "?exercicio=999999")

        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), antes)

    def test_num_dia_sem_treino_qualquer_escolha_e_404(self):
        """Sem sessão hoje não existe escolha válida.

        Este caminho passou despercebido na primeira versão: `estado_do_treino`
        retornava adiantado quando não havia sessão, e a validação da escolha
        ficava depois do `return`. Um link quebrado devolvia a tela de descanso
        com 200.
        """
        TrainingDay.objects.filter(
            user=self.user, weekday=timezone.localdate().weekday()
        ).delete()
        services.sync_active_routine(self.user)

        resposta = self.client.get(self.url + "?exercicio=%d" % self.escolhidos[0])

        self.assertEqual(resposta.status_code, 404)

    def test_exercicio_CONCLUIDO_abre_sem_corromper_a_contagem(self):
        """Conferir a carga que já fez é legítimo, e não mexe no progresso.

        O item em foco não pode contaminar os números da ficha:
        `exercicios_concluidos`, `concluido` e o "Depois" continuam saindo da
        ficha inteira. Abrir o último exercício já concluído não pode fazer a
        tela dizer que o treino acabou com séries faltando lá em cima.
        """
        # A OPÇÃO ESCOLHIDA é a ficha da execução; a outra não entra na conta.
        itens = self.sessao.da_opcao(1)
        if len(itens) < 2:
            self.skipTest("a sessão de hoje tem um exercício só")
        ultimo = itens[-1]
        for numero in range(1, ultimo.sets + 1):
            services.record_load(
                self.user, ultimo.exercise, weight_kg=40,
                set_number=numero, reps=10,
            )

        estado = services.estado_do_treino(
            self.user, escolhido=ultimo.exercise_id
        )

        self.assertEqual(estado.atual.exercise_id, ultimo.exercise_id)
        self.assertFalse(estado.concluido, "disse que o treino acabou")
        self.assertEqual(estado.exercicios_concluidos, 1)
        self.assertEqual(estado.posicao_atual, len(itens))
        # E o "Depois" aponta para o que ainda falta, e não para o vazio.
        self.assertIsNotNone(estado.proximo)
        self.assertFalse(estado.proximo.concluido)


class ACargaContinuaNaExecucaoTests(BaseDoFluxo):
    """O marcador saiu da ficha; o registro NÃO saiu de lugar nenhum."""

    def setUp(self):
        self.user = pessoa("carga@exemplo.com")
        self.client.force_login(self.user)
        self.sessao = sessao_de_hoje(self.user)
        self.item = escolher_a_opcao_1(self.user, self.sessao)[0]

    def test_a_execucao_tem_campo_de_carga(self):
        resposta = self.client.get(
            reverse("workouts:now") + "?exercicio=%d" % self.item.exercise_id
        )

        self.assertContains(resposta, 'name="weight_kg"')
        self.assertContains(resposta, 'name="reps"')

    def test_a_carga_registrada_fica_no_historico(self):
        """A regra: ficha mostra o plano, execução registra, histórico guarda."""
        services.record_load(
            self.user, self.item.exercise, weight_kg=60, set_number=1, reps=10
        )

        historico = services.load_history(self.user, [self.item.exercise])
        hoje = historico[self.item.exercise_id]["hoje"]

        self.assertEqual(hoje[1].weight_kg, 60)
        self.assertEqual(hoje[1].reps, 10)


class ADuracaoSaiDaTelaMasNaoDoMotorTests(BaseDoFluxo):
    """A pergunta saiu; o teto continua sendo o teto.

    A DECISÃO. "Rápido, padrão, completo ou sem limite?" pede uma calibração
    que ninguém consegue fazer antes de ver uma ficha — e a resposta mais comum
    era a de fábrica, "sem limite rígido", que na prática significava sessões de
    88 minutos para quem nunca abriu aquele rádio.

    O QUE NÃO PODE ACONTECER junto: o motor perder a capacidade de processar as
    quatro faixas. Elas continuam inteiras — o que sumiu é o controle, não a
    regra —, e este arquivo cobra as duas metades.
    """

    def setUp(self):
        self.user = pessoa("duracao@exemplo.com")
        self.client.force_login(self.user)

    def test_a_configuracao_nao_oferece_mais_a_escolha(self):
        # A etapa 2 é onde os dias de treino moram — e onde a faixa moraria.
        html = self.client.get(
            reverse("accounts:onboarding_step", kwargs={"step": 2})
        ).content.decode()

        self.assertNotIn('name="duracao_treino"', html)
        self.assertNotIn('name="start_time"', html)
        for rotulo in ("Rápido —", "Completo —", "Sem limite"):
            self.assertNotIn(rotulo, html, rotulo)

    def test_o_perfil_nao_exibe_um_valor_que_nao_da_para_editar(self):
        html = self.client.get(reverse("accounts:profile")).content.decode()

        for rotulo in ("Rápido —", "Padrão —", "Completo —", "Sem limite"):
            self.assertNotIn(rotulo, html, rotulo)

    def test_quem_nunca_respondeu_passa_a_valer_45_a_60(self):
        """O padrão mudou de "sem limite" para "Padrão", e isso é o pedido.

        `MINUTOS_POR_DURACAO` e `TETO_POR_DURACAO` continuam com as quatro
        faixas; o que mudou é para onde cai quem não respondeu.
        """
        from accounts.forms import TrainingForm

        Profile.objects.filter(user=self.user).update(duracao_treino="")
        self.user.refresh_from_db()

        form = TrainingForm(
            data={
                "weekdays": ["0", "2", "4"],
                "experiencia": "intermediario",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()

        self.assertEqual(self.user.profile.duracao_treino, DuracaoTreino.PADRAO)
        self.assertEqual(services.teto_de_minutos(self.user), 60)

    def test_quem_ja_respondeu_e_preservado(self):
        """Esconder o campo não pode reescrever a resposta de ninguém."""
        from accounts.forms import TrainingForm

        Profile.objects.filter(user=self.user).update(
            duracao_treino=DuracaoTreino.COMPLETO
        )
        self.user.refresh_from_db()

        form = TrainingForm(
            data={
                "weekdays": ["0", "2", "4"],
                "experiencia": "intermediario",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()

        self.assertEqual(self.user.profile.duracao_treino, DuracaoTreino.COMPLETO)
        # 65 em 16/09/2026 (o teto que o catálogo de 35 entregava); 90 desde
        # 17/09, com os 63 ativos e a doutrina do TREINO.md.
        self.assertEqual(services.teto_de_minutos(self.user), 90)

    def test_o_horario_existente_sobrevive_ao_salvamento(self):
        """O campo saiu da tela e o cardápio depende do valor.

        `update_or_create` com `start_time=None` nos defaults apagaria o horário
        de quem já tinha — mudando o cardápio dessa pessoa em silêncio, que é
        exatamente o que a decisão proíbe.
        """
        from accounts.forms import TrainingForm

        TrainingDay.objects.filter(user=self.user).update(start_time=time(19, 0))

        form = TrainingForm(
            data={
                "weekdays": [str(d) for d in range(7)],
                "experiencia": "intermediario",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        horarios = {d.start_time for d in self.user.training_days.all()}
        self.assertEqual(horarios, {time(19, 0)})

    def test_o_motor_continua_processando_as_QUATRO_faixas(self):
        """O controle saiu; a regra não.

        Um perfil gravado em "rápido" continua recebendo teto de 30, e um em
        "sem limite" continua sem teto. Perder isso transformaria a remoção de
        um campo numa amputação do motor.
        """
        esperado = {
            DuracaoTreino.RAPIDO: 30,
            DuracaoTreino.PADRAO: 60,
            # 65 em 16/09/2026 (com 90 o gerador entregava o mesmo treino);
            # 90 desde 17/09, quando a sessão passou a chegar lá.
            DuracaoTreino.COMPLETO: 90,
            DuracaoTreino.LIVRE: None,
        }
        for faixa, teto in esperado.items():
            with self.subTest(faixa=faixa):
                Profile.objects.filter(user=self.user).update(duracao_treino=faixa)
                self.user.refresh_from_db()

                self.assertEqual(services.teto_de_minutos(self.user), teto)


class ACargaAnteriorNaoViraRecomendacaoTests(BaseDoFluxo):
    """"Última carga" é fato; "manter" é o que o app faz; a seta é comparação.

    O DEFEITO QUE ISTO FECHA nasceu na migração do cartão para a execução. O
    cartão antigo mostrava "Último treino (03/09): 68 kg · +5 kg", e aquele
    delta era a diferença entre o mais pesado de HOJE e o da última vez —
    descrição do que a pessoa já tinha levantado. Renderizado ao lado de um
    campo de carga vazio, ele lia como conselho: "põe mais cinco".

    O app NÃO TINHA regra que autorizasse subir peso. Desde 13/09/2026 tem —
    a dupla progressão (`proxima_carga`, `test_dupla_progressao.py`) —, e
    ela só age com HISTÓRICO COMPLETO e com a razão escrita. Os casos daqui
    continuam valendo porque `_semana_passada` anota UMA série: sem a faixa
    fechada em todas, a sugestão é "manter", e nada é inventado.
    """

    def setUp(self):
        self.user = pessoa("progressao@exemplo.com")
        self.client.force_login(self.user)
        self.sessao = sessao_de_hoje(self.user)
        self.item = next(
            (
                i
                for i in escolher_a_opcao_1(self.user, self.sessao)
                if i.exercise.equipment != "bodyweight"
            ),
            None,
        )
        if self.item is None:
            self.skipTest("a sessão de hoje só tem exercício de peso corporal")

    def _tela(self):
        return self.client.get(
            reverse("workouts:now") + "?exercicio=%d" % self.item.exercise_id
        )

    def _semana_passada(self, item, peso):
        from datetime import timedelta

        services.record_load(
            self.user, item.exercise, weight_kg=peso, set_number=1, reps=10,
            day=timezone.localdate() - timedelta(days=7),
        )

    def test_sem_historico_nao_mostra_comparacao_nem_zero(self):
        """Nada inventado: sem carga anterior, a tela não afirma nada."""
        resposta = self._tela()

        self.assertNotContains(resposta, "Última carga")
        self.assertNotContains(resposta, "Sugestão: manter")
        self.assertNotContains(resposta, "0 kg")

    def test_com_historico_diz_o_fato_e_sugere_MANTER(self):
        self._semana_passada(self.item, 68)

        resposta = self._tela()

        self.assertContains(resposta, "Última carga")
        self.assertContains(resposta, "Sugestão: manter")
        self.assertContains(resposta, "68")
        # E não sugere subir: a comparação só existe depois de haver hoje.
        self.assertNotContains(resposta, "Hoje:")

    def test_carga_igual_hoje_e_dita_como_MESMA_e_nao_como_ganho(self):
        self._semana_passada(self.item, 68)
        services.record_load(
            self.user, self.item.exercise, weight_kg=68, set_number=1, reps=10
        )

        resposta = self._tela()

        self.assertContains(resposta, "mesma carga")

    def test_aumento_real_aparece_como_COMPARACAO_do_que_ja_foi_feito(self):
        self._semana_passada(self.item, 68)
        services.record_load(
            self.user, self.item.exercise, weight_kg=73, set_number=1, reps=10
        )

        resposta = self._tela()

        self.assertContains(resposta, "Hoje:")
        # A sugestão continua sendo MANTER a carga da última vez — o app não
        # promove o ganho de hoje a recomendação para a próxima série.
        self.assertContains(resposta, "Sugestão: manter")

    def test_exercicio_de_peso_corporal_nao_recebe_recomendacao(self):
        """Prancha não leva anilha, e "manter 0 kg" seria inventar um número."""
        # A letra A do `abc2` traz Flexão de braço e Mergulho no banco, os dois
        # de peso corporal. Forçá-la para hoje tira este teste do calendário.
        sessao = tornar_hoje(self.user, "A")
        # As duas opções repartem o modelo: a de peso corporal pode ser a 1
        # ou a 2. O teste escolhe a opção que o tem — é a escolha que a
        # pessoa faria na ficha.
        corporal = None
        for k in sessao.opcoes:
            candidato = next(
                (i for i in sessao.da_opcao(k) if i.exercise.equipment == "bodyweight"), None
            )
            if candidato is not None:
                services.registrar_escolha(self.user, sessao, k)
                corporal = candidato
                break
        self.assertIsNotNone(
            corporal, "o dia de peito deixou de ter exercício de peso corporal"
        )
        self._semana_passada(corporal, 0)

        resposta = self.client.get(
            reverse("workouts:now") + "?exercicio=%d" % corporal.exercise_id
        )

        self.assertNotContains(resposta, "Sugestão: manter")


class OFluxoResisteAoUsoRealTests(BaseDoFluxo):
    """Toque duplo, recarregar, voltar e reabrir — sem perder nem duplicar."""

    def setUp(self):
        self.user = pessoa("uso@exemplo.com")
        self.client.force_login(self.user)
        self.sessao = sessao_de_hoje(self.user)
        # Sem escolha gravada de propósito: a primeira série registrada É a
        # escolha (`ConcluirSerieView` grava a opção junto), e é esse caminho
        # que o uso real segue.
        self.item = self.sessao.da_opcao(1)[0]

    def _registrar(self, op_id):
        return self.client.post(
            reverse("workouts:record_set"),
            {
                "exercise_id": self.item.exercise_id,
                "weight_kg": "60",
                "reps": "10",
                "op_id": op_id,
                "dia": timezone.localdate().isoformat(),
            },
        )

    def test_toque_duplo_no_mesmo_op_id_grava_UMA_serie(self):
        """A identidade é da renderização, e é ela que protege o toque duplo.

        Sem `op_id` o segundo toque gravaria a série 2 — a pessoa terminaria o
        treino com uma série que não fez.
        """
        self._registrar("op-toque-duplo")
        self._registrar("op-toque-duplo")

        self.assertEqual(
            ExerciseLog.objects.filter(
                user=self.user, exercise=self.item.exercise,
                date=timezone.localdate(),
            ).count(),
            1,
        )

    def test_recarregar_a_execucao_nao_muda_o_progresso(self):
        self._registrar("op-uma")
        antes = ExerciseLog.objects.filter(user=self.user).count()

        for _ in range(3):
            self.client.get(
                reverse("workouts:now") + "?exercicio=%d" % self.item.exercise_id
            )

        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), antes)

    def test_voltar_para_a_ficha_preserva_o_andamento(self):
        self._registrar("op-antes-de-voltar")

        ficha = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))

        self.assertEqual(ficha.status_code, 200)
        # A ficha mostra o andamento no item que recebeu a série.
        self.assertContains(ficha, "1/%d" % self.item.sets)
        self.assertContains(ficha, "com série registrada hoje")

    def test_reabrir_exercicio_concluido_nao_conclui_nada_de_novo(self):
        for numero in range(1, self.item.sets + 1):
            self._registrar("op-serie-%d" % numero)
        antes = ExerciseLog.objects.filter(user=self.user).count()

        resposta = self.client.get(
            reverse("workouts:now") + "?exercicio=%d" % self.item.exercise_id
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), antes)

    def test_a_ficha_de_outra_pessoa_nao_abre_por_url(self):
        """IDOR na ficha: o id da sessão alheia não vira página.

        `FichaDaSessaoView` filtra por `plan__user`, e este teste é a trava —
        sem ele, trocar um número na barra de endereço abriria o treino de
        outra conta.
        """
        alheia = pessoa("alheia-ficha@exemplo.com")
        sessao_alheia = sessao_de_hoje(alheia)

        resposta = self.client.get(
            reverse("workouts:ficha", args=[sessao_alheia.pk])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_nao_da_para_executar_a_sessao_de_outro_dia(self):
        """Consultar sim; executar não.

        A ficha de outro dia é lista de leitura — sem link para a execução,
        porque a execução lê e grava `ExerciseLog` de HOJE. Prometer "fazer" a
        ficha de sexta numa terça registraria série num treino que não está
        acontecendo.
        """
        outra = (
            TrainingSession.objects.filter(
                plan__user=self.user, plan__is_active=True
            )
            .exclude(pk=self.sessao.pk)
            .first()
        )

        html = self.client.get(
            reverse("workouts:ficha", args=[outra.pk])
        ).content.decode()

        self.assertIn("ficha-item", html)
        self.assertNotIn('href="%s?exercicio=' % reverse("workouts:now"), html)
