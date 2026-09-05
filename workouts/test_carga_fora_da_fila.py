# -*- coding: utf-8 -*-
"""A carga de treino saiu da fila offline, e este arquivo diz por quê.

O corpo que o formulário da ficha envia carrega `series_feitas` — um contador
DERIVADO, com a contagem já persistida. Quem o incrementa é o `fetch` da tela,
e ele incrementa numa CÓPIA: `templates/workouts/routine.html` faz
`dados.set("series_feitas", feitas + 1)` e só reescreve o campo real dentro do
`.then` de sucesso.

Offline o sucesso nunca vem. Então a fila capturava o contador ANTIGO — sempre
defasado por exatamente um, por construção, não por corrida.

E o replay desse corpo não é uma escrita inofensiva: `RecordLoadView` grava as
séries 1..N com a carga NOVA e roda `DELETE ... set_number__gt=N`. O primeiro
teste desta classe mede o estrago, e ele é de duas naturezas ao mesmo tempo —
apaga a série que a pessoa acabou de registrar e reescreve o peso das
anteriores.

A decisão foi tirar a rota da fila enquanto não existir uma solução que
preserve o histórico. Perder o toque offline é ruim; reescrever o treino de
quem confiou no app é pior. `CAMPANHA — CARGA OFFLINE V2` está no BACKLOG.
"""
import re
from datetime import timedelta
from pathlib import Path
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts.models import Exercise, ExerciseLog
from push.test_cache_privado import sem_comentarios
from push.test_replay import corpo_da_funcao
from workouts.tests import create_user


class OReplayDaCargaEDestrutivoTests(TestCase):
    """A reprodução do risco. Estes testes descrevem o que ACONTECERIA se a
    carga voltasse para a fila — e é por isso que ela não pode voltar sem uma
    campanha própria."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.exercise = Exercise.objects.get(name="Supino reto com barra")
        self.client.force_login(self.user)
        self.hoje = timezone.localdate()

    def series(self):
        return {
            log.set_number: log.weight_kg
            for log in ExerciseLog.objects.filter(
                user=self.user, exercise=self.exercise, date=self.hoje
            )
        }

    def registrar(self, *, peso, feitas):
        """O corpo que o formulário da ficha envia."""
        return self.client.post(
            reverse("workouts:record_load", args=[self.exercise.pk]),
            {"weight_kg": str(peso), "series_feitas": str(feitas)},
        )

    def test_um_corpo_com_contador_defasado_apaga_serie_e_reescreve_peso(self):
        """Três séries a 40 kg. A quarta, a 50, chega com o contador ANTIGO.

        É exatamente o que a fila capturaria offline. O resultado não é "a
        quarta série não foi registrada": é três séries a 50 kg — a quarta
        sumiu E o peso das três anteriores foi reescrito.
        """
        self.registrar(peso=40, feitas=3)
        self.assertEqual(self.series(), {1: Decimal("40"), 2: Decimal("40"), 3: Decimal("40")})

        # O replay do corpo defasado: a pessoa tocou a QUARTA série a 50 kg, e
        # o campo escondido ainda dizia 3.
        self.registrar(peso=50, feitas=3)

        depois = self.series()
        self.assertEqual(
            len(depois), 3,
            "o replay do corpo defasado deveria ter deixado tres series",
        )
        self.assertEqual(
            set(depois.values()), {Decimal("50")},
            "o peso das series anteriores foi reescrito",
        )

    def test_com_o_contador_em_zero_o_dia_inteiro_daquele_exercicio_some(self):
        """O pior caso, e ele não é exótico: primeira série do dia.

        Com `series_feitas = 0` o laço `range(1, 1)` é vazio e o DELETE remove
        TUDO daquele exercício no dia. Nada é gravado no lugar.
        """
        self.registrar(peso=40, feitas=3)
        self.assertEqual(len(self.series()), 3)

        self.registrar(peso=50, feitas=0)

        self.assertEqual(self.series(), {}, "o DELETE levou o dia inteiro")

    def test_o_controle_positivo_o_contador_CERTO_faz_a_coisa_certa(self):
        """Sem este, os dois testes acima poderiam estar medindo uma view
        quebrada em vez de um corpo defasado. Com `feitas = 4`, a quarta série
        nasce e as anteriores ficam onde estavam."""
        self.registrar(peso=40, feitas=3)

        self.registrar(peso=40, feitas=4)

        depois = self.series()
        self.assertEqual(len(depois), 4)
        self.assertEqual(set(depois.values()), {Decimal("40")})

    def test_a_carga_de_ONTEM_nao_e_alcancada(self):
        """O DELETE é do dia de hoje. Um replay não reescreve o histórico
        inteiro — o que ele destrói é o dia, e isso já basta."""
        ontem = self.hoje - timedelta(days=1)
        ExerciseLog.objects.create(
            user=self.user, exercise=self.exercise, date=ontem,
            set_number=1, weight_kg=Decimal("35"),
        )

        self.registrar(peso=50, feitas=0)

        self.assertTrue(
            ExerciseLog.objects.filter(
                user=self.user, exercise=self.exercise, date=ontem
            ).exists()
        )


class ACargaSaiuDaFilaOfflineTests(TestCase):
    """As duas metades da mitigação: não enfileirar, e não reproduzir.

    A segunda não é teórica — a versão publicada enfileirava carga, então há
    aparelho por aí com item desses guardado agora. Tirar da lista impede os
    novos; o descarte na drenagem é o que desarma os que já existem. E é o
    replay que destrói, não o enfileiramento.

    Estas asserções são ESTRUTURAIS, sobre os dois arquivos JavaScript, e estão
    declaradas como tais: não existe Node neste ambiente. O comportamento de
    `permitida` foi medido no navegador contra os arquivos servidos — `/agua/`
    e `/refeicao/7/marcar/` verdadeiros, `/treino/exercicio/12/carga/` falso —
    e o ciclo offline inteiro foi percorrido na ficha real.
    """

    @classmethod
    def setUpTestData(cls):
        from django.conf import settings

        cls.raiz = Path(settings.BASE_DIR)

    def setUp(self):
        self.pagina = sem_comentarios(
            (self.raiz / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        )
        self.worker = sem_comentarios(self.client.get("/sw.js").content.decode())

    def _rotas(self, texto):
        """A lista literal, fechada pelo `];` e não pelo primeiro `]`.

        Fatiar até o primeiro colchete quebra na primeira regex que use classe
        de caracteres — `[0-9]` fecharia a janela cedo, e o `assertNotIn` de
        "carga" passaria verde por truncamento, não por ausência.
        """
        trecho = texto[texto.index("ROTAS = [") :]
        return trecho[: trecho.index("];") + 2]

    def test_a_carga_nao_esta_na_lista_de_nenhum_dos_dois(self):
        for nome, texto in (("fila.js", self.pagina), ("sw.js", self.worker)):
            with self.subTest(arquivo=nome):
                self.assertNotIn("carga", self._rotas(texto))

    def test_agua_e_refeicao_CONTINUAM_na_lista(self):
        """Controle positivo: retirar a carga não pode desligar a fila inteira.

        Sem este teste, apagar `ROTAS` por completo passaria como "a carga saiu"
        — e levaria junto a água e a refeição, que são a razão de a fila
        existir.
        """
        for nome, texto in (("fila.js", self.pagina), ("sw.js", self.worker)):
            with self.subTest(arquivo=nome):
                rotas = self._rotas(texto)
                self.assertIn("agua", rotas)
                self.assertIn("marcar", rotas)

    def test_os_dois_lados_declaram_a_MESMA_lista(self):
        """O worker drena sem nenhuma aba aberta. Se a lista dele divergir, ele
        reproduz exatamente o que a página passou a recusar."""
        self.assertEqual(
            re.sub(r"\s+", " ", self._rotas(self.pagina)),
            re.sub(r"\s+", " ", self._rotas(self.worker)),
        )

    def test_os_dois_lados_DESCARTAM_o_que_nao_esta_na_lista(self):
        """Tirar da lista sozinho não desarma o item já gravado no aparelho."""
        for nome, bloco in (
            ("fila.js", self._bloco_do_descarte(
                corpo_da_funcao(self.pagina, "function emSerieAtePreservar(itens, i) {"))),
            ("sw.js", self._bloco_do_descarte(
                corpo_da_funcao(self.worker, "async function drenarFila() {"))),
        ):
            with self.subTest(arquivo=nome):
                self.assertIn("remover", bloco, "a guarda existe e nao descarta")

    def _bloco_do_descarte(self, corpo):
        """O corpo do `if (!permitida(...))`, contando chaves.

        A versão anterior deste teste procurava `remover(item.op_id)` na FUNÇÃO
        INTEIRA — e o caminho de sucesso contém a mesma string. Medido por
        revisão adversarial: trocar o descarte por um PULO (mantendo a guarda,
        tirando a remoção) passava verde nos dois lados. A guarda estava
        protegida; o descarte não estava, e ele é metade do que esta classe
        promete — sem ele o item de carga fica na fila para sempre, inflando a
        contagem de pendências, que é outra forma de a tela mentir.
        """
        inicio = corpo.index("if (!permitida(item.url)) {")
        profundidade = 0
        for fim in range(inicio, len(corpo)):
            if corpo[fim] == "{":
                profundidade += 1
            elif corpo[fim] == "}":
                profundidade -= 1
                if profundidade == 0:
                    return corpo[inicio : fim + 1]
        raise AssertionError("chave nao fechada no bloco do descarte")

    def test_o_recorte_do_descarte_nao_pega_o_caminho_de_sucesso(self):
        """Controle do recorte: se ele escorregasse para a função inteira, o
        teste acima voltaria a ser satisfeito pelo caminho de sucesso."""
        bloco = self._bloco_do_descarte(
            corpo_da_funcao(self.pagina, "function emSerieAtePreservar(itens, i) {")
        )

        self.assertIn("permitida", bloco)
        self.assertNotIn("veredito", bloco)
        self.assertNotIn("enviar(item)", bloco)

    def test_a_guarda_existe_nos_dois_lados(self):
        drenar = corpo_da_funcao(self.pagina, "function emSerieAtePreservar(itens, i) {")
        worker = corpo_da_funcao(self.worker, "async function drenarFila() {")

        self.assertIn("if (!permitida(item.url)) {", drenar)
        self.assertIn("if (!permitida(item.url)) {", worker)

    def test_o_produtor_so_enfileira_o_que_a_lista_permite(self):
        """A guarda do enfileiramento é a mesma função, e não uma segunda
        cópia da regra — duas cópias divergiriam na primeira mudança."""
        # Do `addEventListener` até o `guardar({`, e não até o fim do arquivo:
        # sem limite superior, a asserção não prova que a guarda está DENTRO do
        # handler — provaria só que a string existe em algum lugar depois dele.
        inicio = self.pagina.index('addEventListener("submit"')
        captura = self.pagina[inicio : self.pagina.index("guardar({", inicio)]

        self.assertIn("!permitida(form.action)", captura)

    def test_o_recorte_do_produtor_termina_no_enfileiramento(self):
        """Controle do recorte acima."""
        inicio = self.pagina.index('addEventListener("submit"')
        captura = self.pagina[inicio : self.pagina.index("guardar({", inicio)]

        self.assertIn("evento.preventDefault()", captura)
        self.assertNotIn("function drenar()", captura)


class OAvisoOfflineNaoMenteTests(TestCase):
    """Sem rede a série não é salva, e a tela precisa dizer isso.

    Um toque que não produz nada visível é indistinguível de um botão quebrado,
    e a pessoa toca de novo. O aviso reusa `role="status"`/`aria-live` — o mesmo
    padrão do aviso do cronômetro, nesta mesma ficha — em vez de um toast novo.
    """

    @classmethod
    def setUpTestData(cls):
        from django.conf import settings

        cls.raiz = Path(settings.BASE_DIR)

    def setUp(self):
        # SEM COMENTÁRIOS: `assertNotIn("atualiza(", ...)` sobre o texto cru
        # ficaria VERMELHO no dia em que alguém escrevesse "não chama
        # `atualiza(`" dentro do próprio `.catch` — falso vermelho, mesma
        # família da armadilha que já custou caro aqui na direção oposta.
        self.ficha = sem_comentarios(
            (self.raiz / "templates" / "workouts" / "routine.html").read_text(
                encoding="utf-8"
            )
        )
        self.cartao = (
            self.raiz / "templates" / "workouts" / "_exercicio.html"
        ).read_text(encoding="utf-8")

    def _catch_do_registro(self):
        """O `.catch` do envio da série, recortado do resto da ficha."""
        envio = self.ficha.index("envia(form, feitas + 1)")
        inicio = self.ficha.index(".catch(function () {", envio)
        return self.ficha[inicio : self.ficha.index(".then(function ()", inicio)]

    def test_o_recorte_pega_mesmo_o_catch_do_registro(self):
        """Controle do recorte: o arquivo tem outros `.catch`, e o primeiro
        deles é do wake-lock. Se o recorte escorregasse, as duas asserções
        abaixo estariam falando de um bloco que não é este."""
        catch = self._catch_do_registro()

        self.assertIn("data-registro-aviso", catch)
        self.assertNotIn("release()", catch)

    def test_o_formulario_tem_onde_avisar(self):
        self.assertIn("data-registro-aviso", self.cartao)
        self.assertIn('role="status"', self.cartao)
        self.assertIn('aria-live="polite"', self.cartao)

    def test_o_fallback_nativo_NAO_EXISTE_MAIS(self):
        """`form.submit()` no erro era destrutivo, e não offline.

        Ele mandava o campo REAL do formulário — e quem escreve esse campo é
        `atualiza()`, que só roda no `.then` de sucesso. Ou seja: o fallback
        postava o contador VELHO, e a view apaga toda série acima dele. Com
        `series_feitas = 0`, que é o primeiro toque do dia, o
        `DELETE ... set_number__gt=0` leva o exercício inteiro — está medido em
        `test_com_o_contador_em_zero_o_dia_inteiro_daquele_exercicio_some`.

        E disparava COM REDE VIVA: qualquer falha do `fetch` — 5xx, requisição
        abortada, o cold start de 50 s do plano gratuito. Não era o caminho
        offline; era o caminho online.

        Sem o fallback, a única gravação é o `fetch`, que manda o contador
        certo. Falhou, não salvou, e a tela diz isso.
        """
        catch = self._catch_do_registro()

        self.assertNotIn("form.submit()", catch)

    def test_o_erro_avisa_com_rede_e_sem_rede(self):
        """As duas frases existem, e são diferentes: "não consegui" e "sem
        rede" descrevem situações distintas para quem está de pé na academia."""
        catch = self._catch_do_registro()

        self.assertIn("navigator.onLine", catch)
        self.assertIn("Sem rede", catch)
        self.assertIn("Nao consegui salvar", catch)
        self.assertIn("aviso.hidden = false;", catch)

    def test_sem_rede_a_ficha_NAO_navega_para_fora(self):
        """`form.submit()` offline leva a pessoa para a página de offline e
        tira a ficha da frente dela no meio do treino — e agora não há nem fila
        para recolher o toque."""
        # Ancorado no ENVIO da série, e não no primeiro `.catch` do arquivo —
        # esse é o do wake-lock, centenas de linhas acima, e a asserção falhava
        # medindo o bloco errado.
        catch = self._catch_do_registro()

        # A asserção era `assertIn("form.submit();")` — ela travava a NAVEGAÇÃO
        # no ramo online como se fosse desejável. Era o oposto: aquele POST
        # nativo mandava o contador defasado e apagava o dia. Hoje o teste
        # irmão exige a AUSÊNCIA dele, e este cuida do que sobrou: a tela não
        # sai do lugar e avisa.
        self.assertNotIn("form.submit()", catch)
        self.assertIn("aviso.hidden = false;", catch)

    def test_o_aviso_e_limpo_a_cada_tentativa(self):
        """Aviso que sobrevive ao registro seguinte mente na direção oposta."""
        self.assertIn("avisoAnterior.hidden = true;", self.ficha)

    def test_a_ficha_nao_marca_a_serie_no_caminho_de_erro(self):
        """Controle do "não finja que salvou": `atualiza()` só existe dentro do
        `.then` de sucesso. Se aparecesse no `.catch`, o contador subiria sem
        nada ter sido gravado."""
        catch = self._catch_do_registro()

        self.assertNotIn("atualiza(", catch)
