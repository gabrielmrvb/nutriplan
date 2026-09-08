"""A carga volta à fila offline como EVENTO, e não como estado.

A mitigação de 05/09/2026 tirou a carga da fila porque o corpo enfileirado
carregava `series_feitas`, um contador derivado: três séries a 40 kg mais uma
quarta a 50 com o contador defasado terminavam em três séries a 50 — a quarta
sumia e o peso das anteriores era reescrito. Com o contador em zero, o dia
inteiro daquele exercício era apagado. `test_carga_fora_da_fila.py` guarda essa
reprodução, e ela continua valendo para a rota da FICHA.

O que muda aqui é a natureza do pedido. "Fiz mais uma série" é um evento; "tenho
N séries" é um estado, e estado enviado com atraso reescreve o presente. O
número da série passa a ser do SERVIDOR, decidido na hora de aplicar, e o
cliente não manda contador nenhum.

Este arquivo prova as propriedades que a campanha listou como não-opcionais:
identidade estável, contador que não envelhece, append, idempotência,
concorrência com retry, rollback (desfazer), o DIA em que o toque aconteceu, e
equivalência entre a sequência online e a offline.

E prova nos dois níveis, de propósito. O serviço responde pelo contrato; as
classes de TELA (`ATelaMandaOpIdEmVezDeContador`, `OEventoCarregaODiaDoToque`)
respondem pelo formulário que a pessoa recebe — porque o defeito mais provável
desta mudança é o serviço certo com o HTML ainda mandando `set_number`, e teste
de serviço não enxerga isso.
"""
import re
import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SyncedOperation
from workouts import services
from workouts.models import Exercise, ExerciseLog
from workouts.tests import create_user

User = get_user_model()


def _pessoa(email="serie@exemplo.com"):
    return User.objects.create_user(email=email, password="x8Kd2Lm9Qp4z")


def _exercicio(nome="Supino de teste"):
    """Um exercício próprio, e não o do catálogo semeado.

    Buscar `Exercise.objects.get(name=...)` amarraria este arquivo ao conteúdo
    do seed: renomear um exercício do catálogo quebraria testes que não falam
    de catálogo nenhum.
    """
    return Exercise.objects.create(name=nome, muscle_group="chest")


class OContadorNaoVemMaisDoClienteTests(TestCase):
    """A propriedade que derrubou a versão anterior, medida do outro lado."""

    def setUp(self):
        self.pessoa = _pessoa()
        self.exercicio = _exercicio()

    def test_tres_eventos_iguais_viram_TRES_series(self):
        """O caso exato da academia sem sinal.

        Três toques em "Concluir série" sem rede enfileiram três pedidos, e os
        três nasceram na MESMA página — com o mesmo número de série escrito no
        HTML, porque a página não recarregou entre eles. Se o número viesse do
        corpo, os três gravariam a mesma linha e a pessoa terminaria o treino
        com uma série registrada de três que fez.
        """
        for i in range(3):
            log, criada = services.append_set(
                self.pessoa, self.exercicio, "40", reps=10, op_id=f"toque-{i}"
            )
            self.assertTrue(criada)

        series = list(
            ExerciseLog.objects.filter(user=self.pessoa, exercise=self.exercicio)
            .order_by("set_number")
            .values_list("set_number", flat=True)
        )
        self.assertEqual(series, [1, 2, 3])

    def test_o_peso_de_cada_serie_e_o_daquele_toque(self):
        """Série pesada e série leve no mesmo exercício — o motivo de o
        registro ser por série desde 24/08/2026. Um evento não pode reescrever
        o peso dos anteriores, que é o que o corpo com estado fazia."""
        services.append_set(self.pessoa, self.exercicio, "40", op_id="a")
        services.append_set(self.pessoa, self.exercicio, "40", op_id="b")
        services.append_set(self.pessoa, self.exercicio, "50", op_id="c")

        pesos = list(
            ExerciseLog.objects.filter(user=self.pessoa, exercise=self.exercicio)
            .order_by("set_number")
            .values_list("weight_kg", flat=True)
        )
        self.assertEqual(pesos, [Decimal("40"), Decimal("40"), Decimal("50")])

    def test_nada_e_apagado(self):
        """`append` não remove. A rota da ficha apagava o que passasse do
        contador — é dali que vinha o dia inteiro sumindo."""
        antiga = services.record_load(
            self.pessoa, self.exercicio, "60", set_number=1, reps=8
        )

        services.append_set(self.pessoa, self.exercicio, "40", op_id="nova")

        self.assertTrue(ExerciseLog.objects.filter(pk=antiga.pk).exists())
        self.assertEqual(
            ExerciseLog.objects.filter(
                user=self.pessoa, exercise=self.exercicio
            ).count(),
            2,
        )

    def test_o_dia_de_ONTEM_nao_e_alcancado(self):
        """A contagem é por dia. Um evento que drena hoje não pode continuar a
        numeração de ontem nem tocar no que ficou lá."""
        ontem = timezone.localdate() - timezone.timedelta(days=1)
        services.record_load(
            self.pessoa, self.exercicio, "80", set_number=1, day=ontem
        )
        services.record_load(
            self.pessoa, self.exercicio, "80", set_number=2, day=ontem
        )

        log, _ = services.append_set(self.pessoa, self.exercicio, "40", op_id="hoje")

        self.assertEqual(log.set_number, 1)
        self.assertEqual(
            ExerciseLog.objects.filter(
                user=self.pessoa, exercise=self.exercicio, date=ontem
            ).count(),
            2,
        )


class OReenvioNaoCriaSerieAMaisTests(TestCase):
    def setUp(self):
        self.pessoa = _pessoa()
        self.exercicio = _exercicio()

    def test_o_mesmo_op_id_grava_uma_vez_so(self):
        """A fila reenvia: é o que ela faz quando a resposta se perde no meio.
        Sem idempotência, "mais uma série" reenviada vira uma série que ninguém
        fez — o mesmo defeito que a água tem com "+500 ml"."""
        primeiro, criada1 = services.append_set(
            self.pessoa, self.exercicio, "40", op_id="mesmo"
        )
        segundo, criada2 = services.append_set(
            self.pessoa, self.exercicio, "40", op_id="mesmo"
        )

        self.assertTrue(criada1)
        self.assertFalse(criada2)
        self.assertIsNone(segundo)
        self.assertEqual(
            ExerciseLog.objects.filter(user=self.pessoa).count(), 1
        )
        self.assertEqual(primeiro.set_number, 1)

    def test_op_ids_diferentes_sao_series_diferentes(self):
        """Controle positivo do teste acima: sem ele, um `append_set` que nunca
        gravasse passaria como "idempotente"."""
        services.append_set(self.pessoa, self.exercicio, "40", op_id="um")
        services.append_set(self.pessoa, self.exercicio, "40", op_id="dois")

        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 2)

    def test_sem_op_id_nao_ha_deduplicacao(self):
        """Corpo SEM identificador continua gravando, e isso não é o caminho
        da tela.

        A tela passou a mandar `op_id` em 08/09/2026 — esta frase dizia que ela
        não mandava, e ficou falsa no mesmo commit. O que o teste guarda é o
        contrato de `ja_aplicada`: vazio não é repetição. Tratar o vazio como
        "já aplicada" travaria toda escrita que chegasse sem identificador, e
        um formulário que perdesse o campo pararia de gravar em silêncio em vez
        de duplicar — falha pior, porque não deixa rastro."""
        services.append_set(self.pessoa, self.exercicio, "40", op_id="")
        services.append_set(self.pessoa, self.exercicio, "40", op_id="")

        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 2)

    def test_o_op_id_de_OUTRA_pessoa_nao_bloqueia(self):
        """O identificador nasce no navegador e dois aparelhos podem sortear o
        mesmo. A chave é por pessoa, e este teste é o que prova."""
        outra = _pessoa("outra@exemplo.com")
        services.append_set(self.pessoa, self.exercicio, "40", op_id="colisao")

        log, criada = services.append_set(
            outra, self.exercicio, "40", op_id="colisao"
        )

        self.assertTrue(criada)
        self.assertEqual(log.set_number, 1)


class AIdempotenciaCaiJuntoComOEfeitoTests(TestCase):
    """O `op_id` não pode ser registrado se a série não foi gravada.

    Este projeto não liga `ATOMIC_REQUESTS`. Registrar fora da transação faria
    uma falha no meio queimar o identificador sem gravar nada: o reenvio seria
    respondido com "já aplicada", a fila apagaria o item, e a série sumiria em
    silêncio. Foi exatamente o defeito que `LogHydrationView` pagou para
    aprender.
    """

    def test_falha_na_escrita_nao_deixa_o_op_id_gravado(self):
        pessoa = _pessoa()
        exercicio = _exercicio()

        # 20 é o teto do modelo; a 21ª levanta antes de escrever.
        for numero in range(1, 21):
            services.record_load(pessoa, exercicio, "40", set_number=numero)

        with self.assertRaises(ValueError):
            services.append_set(pessoa, exercicio, "40", op_id="queimado")

        self.assertFalse(
            SyncedOperation.objects.filter(user=pessoa, op_id="queimado").exists(),
            "o identificador ficou registrado sem a série existir: o reenvio "
            "seria descartado e a carga se perderia",
        )


class DoisPedidosAoMesmoTempoTests(TransactionTestCase):
    """Duas abas, ou a fila drenando enquanto a pessoa toca na tela.

    `TransactionTestCase` porque `TestCase` envolve tudo numa transação e as
    threads não enxergariam o que a outra gravou — o teste passaria sem medir
    concorrência nenhuma, que é o modo de falhar mais comum deste tipo de
    prova.
    """

    def test_oito_series_simultaneas_gravam_OITO(self):
        """A primeira versão deste teste passou medindo nada.

        Ela afirmava `len(numeros) + len(erros) == 8`, que é verdade também
        quando as oito falham — e era exatamente o que acontecia: uma sonda
        direta contra o banco devolveu `gravadas: [1,2,3,4,5]` e três
        `IntegrityError`. TRÊS SÉRIES PERDIDAS, com o teste verde.

        A asserção certa não tem lugar para erro: as oito têm de existir, com
        os números de 1 a 8, porque foi isso que a pessoa fez.
        """
        pessoa = _pessoa()
        exercicio = _exercicio()
        erros = []

        # A BARREIRA É O QUE FAZ ESTE TESTE MEDIR ALGUMA COISA.
        #
        # Sem ela o teste passa MESMO SEM RETRY — sabotado, ficou verde. Cada
        # thread abre a própria conexão com o Postgres, e o custo disso as
        # escalona: quando a primeira grava, a oitava ainda está no handshake.
        # A corrida nunca acontecia, e o teste media o escalonamento do driver.
        #
        # `ensure_connection()` paga esse custo ANTES, e a barreira só solta
        # as oito quando todas já têm conexão viva. Foi assim que a sonda
        # contra o banco de desenvolvimento colidiu de verdade — lá as
        # conexões já estavam quentes.
        portao = threading.Barrier(8)

        def registrar(i):
            try:
                connections["default"].ensure_connection()
                portao.wait(timeout=10)
                services.append_set(pessoa, exercicio, "40", op_id=f"par-{i}")
            except Exception as erro:  # noqa: BLE001 — o teste quer ver qualquer uma
                erros.append(repr(erro))
            finally:
                connections.close_all()

        fios = [threading.Thread(target=registrar, args=(i,)) for i in range(8)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()

        numeros = sorted(
            ExerciseLog.objects.filter(user=pessoa, exercise=exercicio)
            .values_list("set_number", flat=True)
        )
        self.assertEqual(erros, [], f"alguma escrita foi recusada: {erros}")
        self.assertEqual(
            numeros, [1, 2, 3, 4, 5, 6, 7, 8],
            f"oito toques, {len(numeros)} séries: {numeros}",
        )


class ATelaMandaOpIdEmVezDeContadorTests(TestCase):
    """O outro lado da mesma regra, medido no HTML que a pessoa recebe.

    Testar so o servico deixaria passar o defeito mais provavel desta mudanca:
    o servico certo e o formulario ainda mandando `set_number`. `nutriplan-qa`
    chama isso de teste que prova a view e nao a tela.
    """

    url = reverse("workouts:now")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(
            email="agora@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        # A ficha precisa existir antes de alguem registrar serie nela. A tela
        # sincroniza sozinha ao ser carregada; os testes que POSTam direto
        # (que e o que a fila faz ao drenar) nunca passam por la.
        services.sync_active_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _registro(self, html):
        """So o formulario de registrar, recortado pela classe.

        Recortar importa: a pagina tem DOIS formularios para a mesma rota, e
        uma assercao sobre a pagina inteira nao distingue qual deles carrega o
        campo.
        """
        inicio = html.index('class="registro registro--agora"')
        return html[inicio : html.index("</form>", inicio)]

    def _op_do_registro(self, html):
        return re.search(r'name="op_id" value="(\w+)"', self._registro(html)).group(1)

    def test_o_formulario_NAO_manda_mais_o_numero_da_serie(self):
        """A regressao que reabriria o defeito inteiro: basta alguem devolver o
        campo escondido para os tres toques offline voltarem a colidir."""
        registro = self._registro(self.client.get(self.url).content.decode())

        self.assertNotIn('name="set_number"', registro)
        self.assertIn('name="op_id"', registro)

    def test_os_dois_formularios_da_tela_tem_identificadores_DIFERENTES(self):
        """Registrar e desfazer nao podem dividir identidade: desfazer logo
        depois de gravar seria recusado como repeticao do proprio registro."""
        # O formulario de desfazer so existe quando ha serie para desfazer.
        self._enviar(op_id="primeira")
        html = self.client.get(self.url).content.decode()

        todos = re.findall(r'name="op_id" value="(\w+)"', html)

        self.assertEqual(len(todos), 2, f"esperava dois formularios: {todos}")
        self.assertEqual(len(set(todos)), 2, "os dois formularios dividem o op_id")
        self.assertIn(self._op_do_registro(html), todos)

    def test_cada_carregamento_traz_um_identificador_NOVO(self):
        """Controle positivo do teste de reenvio: com um valor fixo no HTML, a
        segunda serie do treino seria recusada como repeticao da primeira e o
        app pararia de gravar depois do primeiro toque."""
        self._enviar(op_id="primeira")
        um = re.findall(r'name="op_id" value="(\w+)"',
                        self.client.get(self.url).content.decode())
        dois = re.findall(r'name="op_id" value="(\w+)"',
                          self.client.get(self.url).content.decode())

        self.assertEqual(set(um) & set(dois), set())

    def _enviar(self, **extra):
        exercicio = services.estado_do_treino(self.pessoa).atual.exercise
        corpo = {"exercise_id": exercicio.pk, "weight_kg": "40", "reps": "10"}
        corpo.update(extra)
        return self.client.post(reverse("workouts:record_set"), corpo)

    def test_o_MESMO_corpo_enviado_duas_vezes_grava_UMA_serie(self):
        """Toque duplo e botao voltar. Era o `update_or_create` no `set_number`
        que protegia isso; agora e o `op_id`, e sem esta prova a troca teria
        devolvido o defeito que ela veio consertar."""
        self._enviar(op_id="mesmo-toque")
        self._enviar(op_id="mesmo-toque")

        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 1)

    def test_identificadores_diferentes_gravam_DUAS(self):
        """Controle positivo: uma view que nunca gravasse passaria acima."""
        self._enviar(op_id="toque-1")
        self._enviar(op_id="toque-2")

        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 2)

    def _desfazer(self, exercicio, op_id):
        return self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": exercicio.pk, "acao": "desfazer", "op_id": op_id},
        )

    def test_desfazer_reenviado_apaga_UMA_serie_so(self):
        """Desfazer tambem entra na fila, e a fila reenvia. Sem idempotencia
        aqui, um toque reproduzido apagaria a serie que a pessoa desfez E a
        anterior, que ela queria manter."""
        self._enviar(op_id="a")
        self._enviar(op_id="b")
        exercicio = ExerciseLog.objects.filter(user=self.pessoa).first().exercise

        self._desfazer(exercicio, "undo")
        self._desfazer(exercicio, "undo")

        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 1)

    def test_dois_desfazer_DIFERENTES_apagam_dois(self):
        """Controle positivo do teste acima."""
        self._enviar(op_id="a")
        self._enviar(op_id="b")
        exercicio = ExerciseLog.objects.filter(user=self.pessoa).first().exercise

        self._desfazer(exercicio, "undo-1")
        self._desfazer(exercicio, "undo-2")

        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 0)

    def test_a_sequencia_OFFLINE_termina_igual_a_ONLINE(self):
        """A propriedade que a campanha pede por ultimo, e a unica que mede as
        duas juntas.

        Online: tres ciclos de carregar a pagina e enviar. Offline: tres
        pedidos drenados da fila, com identificadores proprios e SEM nenhum
        carregamento entre eles — e essa a diferenca que derrubava a versao
        antiga, porque o contador do HTML nao avancava.
        """
        for peso in ("40", "45", "50"):
            html = self.client.get(self.url).content.decode()
            self._enviar(op_id=self._op_do_registro(html), weight_kg=peso)

        online = list(
            ExerciseLog.objects.filter(user=self.pessoa)
            .order_by("set_number").values_list("set_number", "weight_kg")
        )

        outra = create_user(
            email="offline@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        self.client.force_login(outra)
        services.sync_active_routine(outra)
        exercicio = services.estado_do_treino(outra).atual.exercise
        for i, peso in enumerate(("40", "45", "50")):
            self.client.post(
                reverse("workouts:record_set"),
                {"exercise_id": exercicio.pk, "weight_kg": peso, "reps": "10",
                 "op_id": f"fila-{i}"},
            )

        offline = list(
            ExerciseLog.objects.filter(user=outra)
            .order_by("set_number").values_list("set_number", "weight_kg")
        )

        self.assertEqual(
            online,
            [(1, Decimal("40")), (2, Decimal("45")), (3, Decimal("50"))],
        )
        self.assertEqual(offline, online)

    def test_o_buraco_e_preenchido_como_a_tela_ONLINE_faria(self):
        """`append_set` procura o primeiro numero livre, e nao `maior + 1`.

        Quem anotou a serie 3 e deixou a 1 em branco ve "Concluir serie 1" na
        tela — `_primeira_serie_livre` decide isso desde antes desta campanha.
        Se a fila contasse `maior + 1`, o mesmo toque gravaria a serie 4 com
        rede e a 1 sem rede.
        """
        exercicio = services.estado_do_treino(self.pessoa).atual.exercise
        services.record_load(self.pessoa, exercicio, "40", set_number=3)

        log, _ = services.append_set(self.pessoa, exercicio, "42", op_id="buraco")

        self.assertEqual(log.set_number, 1)


class OEventoCarregaODiaDoToqueTests(TestCase):
    """A fila drena quando a rede volta, e isso pode ser noutro dia.

    Quem fecha a ultima serie as 23h50 e so recupera sinal ao sair da academia
    tinha o treino inteiro caindo no dia seguinte: sumia do dia certo e virava
    sessao fantasma no outro. `estado_do_treino`, a ofensiva e o historico leem
    por DATA, entao os tres passavam a mentir juntos.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(
            email="virada@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.exercicio = services.estado_do_treino(self.pessoa).atual.exercise
        self.hoje = timezone.localdate()

    def _post(self, **extra):
        corpo = {"exercise_id": self.exercicio.pk, "weight_kg": "40", "reps": "10"}
        corpo.update(extra)
        return self.client.post(reverse("workouts:record_set"), corpo)

    def _dias(self):
        return sorted(
            ExerciseLog.objects.filter(user=self.pessoa)
            .values_list("date", flat=True)
        )

    def test_a_serie_fica_no_dia_em_que_foi_TOCADA(self):
        ontem = self.hoje - timezone.timedelta(days=1)

        self._post(op_id="atrasada", dia=ontem.isoformat())

        self.assertEqual(self._dias(), [ontem])

    def test_sem_o_campo_a_serie_cai_em_HOJE(self):
        """Controle positivo, e tambem o caminho de quem nao passa pela tela:
        um corpo sem `dia` nao pode virar erro."""
        self._post(op_id="sem-dia")

        self.assertEqual(self._dias(), [self.hoje])

    def test_data_no_FUTURO_e_recusada(self):
        """Relogio de celular adiantado escreveria num dia que ainda nao
        existe, e aquele registro ficaria invisivel para toda tela que pergunta
        'e hoje?'."""
        amanha = self.hoje + timezone.timedelta(days=1)

        self._post(op_id="futuro", dia=amanha.isoformat())

        self.assertEqual(self._dias(), [self.hoje])

    def test_data_VELHA_demais_e_recusada(self):
        """Corpo antigo em aparelho esquecido. Escrever um treino de mes
        passado seria pior que descartar a data."""
        antiga = self.hoje - timezone.timedelta(days=30)

        self._post(op_id="antiga", dia=antiga.isoformat())

        self.assertEqual(self._dias(), [self.hoje])

    def test_data_ilegivel_nao_derruba_o_registro(self):
        """A serie e o que importa; a data e um detalhe do transporte. Um corpo
        corrompido nao pode custar o registro do treino."""
        self._post(op_id="lixo", dia="ontem de manha")

        self.assertEqual(self._dias(), [self.hoje])

    def test_desfazer_alcanca_o_dia_do_TOQUE(self):
        """Desfazer viaja na mesma fila e precisa da mesma data: sem ela,
        desfazer uma serie de ontem apagaria uma de hoje — ou nenhuma."""
        ontem = self.hoje - timezone.timedelta(days=1)
        self._post(op_id="a", dia=ontem.isoformat())
        self._post(op_id="b", dia=ontem.isoformat())

        self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.exercicio.pk, "acao": "desfazer",
             "op_id": "undo", "dia": ontem.isoformat()},
        )

        self.assertEqual(
            ExerciseLog.objects.filter(user=self.pessoa, date=ontem).count(), 1
        )

    def test_a_numeracao_e_por_DIA(self):
        """Duas series ontem e uma hoje: a de hoje e a serie 1, e nao a 3."""
        ontem = self.hoje - timezone.timedelta(days=1)
        self._post(op_id="o1", dia=ontem.isoformat())
        self._post(op_id="o2", dia=ontem.isoformat())

        self._post(op_id="h1")

        self.assertEqual(
            ExerciseLog.objects.get(user=self.pessoa, date=self.hoje).set_number, 1
        )
