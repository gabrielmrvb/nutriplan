# -*- coding: utf-8 -*-
"""Corrida V1 — a corrida não se perde.

Auditado em 04/09/2026: o motor, o model, as views e a tela existem e são bons.
`static/js/corrida.js` não tinha uma linha de `localStorage`. A corrida inteira
vivia numa variável de JavaScript, e isso a perdia de dois jeitos:

  * recarregar a página, fechar a aba ou o navegador matar a página no meio
    apagava tudo, sem retomada;
  * se o `fetch` do fim falhasse — o caso comum, porque quem corre está na rua
    — a tela dizia "não consegui salvar", os botões voltavam ao início, e não
    existia "de novo".

E havia um defeito latente que só apareceria ao consertar o segundo: o `op_id`
era gerado DENTRO de `salvar()`. O model tem constraint de unicidade em
`(user, op_id)` justamente para o reenvio não duplicar — e o cliente inventava
uma chave nova a cada tentativa, desligando a proteção do lado de fora.

O servidor já está coberto por `test_corrida_registro.py` (reenvio não duplica,
CSRF, dono do dado, traçado não guardado). O que falta é o cliente, e é o que
está aqui.

A leitura é do ARQUIVO servido, e não de uma cópia: é ele que roda no
navegador de quem corre.
"""
import re

from django.test import SimpleTestCase

from config.settings import BASE_DIR

JS = (BASE_DIR / "static" / "js" / "corrida.js").read_text(encoding="utf-8")


def corpo_da_funcao(nome):
    """O corpo de uma função do arquivo, do `{` até a chave que o fecha.

    Contar chaves e não usar regex: o corpo tem `if`, `while` e objetos
    literais dentro, e um `.*?}` casaria a primeira chave interna — devolvendo
    um pedaço, e um teste sobre um pedaço não prova nada sobre o resto.
    """
    inicio = JS.index("function %s(" % nome)
    abre = JS.index("{", inicio)
    nivel = 0
    for i in range(abre, len(JS)):
        if JS[i] == "{":
            nivel += 1
        elif JS[i] == "}":
            nivel -= 1
            if nivel == 0:
                return JS[abre : i + 1]
    raise AssertionError("função %s não fecha" % nome)


def sem_comentarios(texto):
    """O corpo sem os comentários, para a asserção casar com CÓDIGO.

    Este arquivo comenta muito, e de propósito — mas comentário é texto, e uma
    asserção que procura `encerrar(true)` acha a menção dele numa frase que
    explica por que ele existe. Foi exatamente o que aconteceu: a sabotagem
    que REMOVE a chamada passou verde, porque o nome dela continuava escrito
    logo acima.

    É a armadilha que o `CLAUDE.md` deste projeto descreve, na versão
    JavaScript.
    """
    sem_bloco = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"^\s*//.*$", "", sem_bloco, flags=re.M)


class OIdentificadorNasceComACorridaTests(SimpleTestCase):
    """A chave precisa sobreviver a tudo o que a corrida sobreviver.

    Gerada no salvamento, cada tentativa inventaria uma chave nova — e a
    constraint de unicidade do model, que existe para o reenvio não duplicar,
    nunca seria acionada. A idempotência estaria no servidor e desligada pelo
    cliente.
    """

    def test_o_comecar_gera_o_identificador(self):
        self.assertIn("estado.opId = identificador()", corpo_da_funcao("comecar"))

    def test_o_salvar_usa_o_identificador_da_corrida_e_nao_um_novo(self):
        corpo = corpo_da_funcao("salvar")

        self.assertIn("op_id: estado.opId", corpo)
        self.assertNotIn("identificador()", corpo)

    def test_o_identificador_e_guardado_junto_com_a_corrida(self):
        """Sem ele no registro local, a retomada depois de um reload geraria
        chave nova — e o reenvio criaria uma segunda corrida."""
        self.assertIn("opId: estado.opId", corpo_da_funcao("guardar"))


class NenhumaCoordenadaEGuardadaNoAparelhoTests(SimpleTestCase):
    """A decisão do model vale igual no cliente.

    `Corrida` não guarda o traçado porque coordenada diz onde a pessoa mora, e
    não existe tela que use isso. Gravar as leituras no `localStorage` "para
    reprocessar depois" contrabandearia de volta exatamente esse dado — com o
    agravante de ficar no aparelho, legível por qualquer script da origem.

    `estado.ancora` É uma leitura do GPS: tem `lat` e `lon`. Um
    `JSON.stringify(estado)` levaria as duas.
    """

    #: O que não pode aparecer no que é gravado.
    PROIBIDOS = ("lat", "lon", "ancora", "accuracy", "coords")

    def test_o_que_e_gravado_e_uma_lista_branca(self):
        corpo = corpo_da_funcao("guardar")

        self.assertNotIn("JSON.stringify(estado)", corpo)
        for campo in self.PROIBIDOS:
            with self.subTest(campo=campo):
                self.assertNotRegex(corpo, r"\b%s\b" % campo)

    def test_o_que_e_lido_de_volta_tambem_nao_traz_coordenada(self):
        """De nada adiantaria não gravar e depois aceitar um registro
        adulterado com coordenadas dentro."""
        corpo = corpo_da_funcao("recuperar")

        for campo in ("lat", "lon", "ancora", "accuracy"):
            with self.subTest(campo=campo):
                self.assertNotRegex(corpo, r"\b%s\b" % campo)


class ORegistroLocalEDaPessoaCertaTests(SimpleTestCase):
    """`localStorage` é por ORIGEM, não por conta.

    Sem o id na chave, uma corrida interrompida seria oferecida a quem entrasse
    depois no mesmo navegador — e gravada na conta DELE, porque quem decide o
    dono é o `request.user` do servidor. Atribuir a corrida de alguém a outra
    pessoa é pior que perdê-la.
    """

    def test_a_chave_leva_o_id_de_quem_esta_logado(self):
        achado = re.search(r'var CHAVE = "nutriplan\.corrida\." \+ \(([^)]+)\)', JS)

        self.assertIsNotNone(achado, "a chave do localStorage mudou de forma")
        self.assertIn("dataset.usuario", achado.group(1))

    def test_o_template_publica_o_id_para_o_script_ler(self):
        """A chave depende de `data-usuario` no `<body>`. Se ele sumir do
        `base.html`, a chave vira a mesma para todo mundo — e o teste de cima
        continuaria passando sozinho."""
        base = (BASE_DIR / "templates" / "base.html").read_text(encoding="utf-8")

        self.assertIn('data-usuario="', base)


class OQueFicaGuardadoEOQueEApagadoTests(SimpleTestCase):
    """Apagar cedo demais troca "a corrida não subiu" por "a corrida não existe
    mais em lugar nenhum"."""

    def test_o_registro_so_e_apagado_depois_da_confirmacao(self):
        corpo = corpo_da_funcao("salvar")
        antes_da_resposta = corpo.split("then(function (r)", 1)[0]

        self.assertNotIn("esquecer()", antes_da_resposta)
        self.assertIn("esquecer()", corpo)

    def test_falha_de_rede_diz_que_a_corrida_esta_guardada(self):
        """"Não consegui salvar" e "está guardada e sobe quando o sinal voltar"
        são a diferença entre a pessoa achar que perdeu e saber que não."""
        corpo = corpo_da_funcao("salvar")

        self.assertIn("guardada", corpo)

    def test_encerrar_sem_distancia_nao_deixa_resto_no_aparelho(self):
        """Um resto de corrida antiga reapareceria como oferta de retomada
        semanas depois."""
        corpo = corpo_da_funcao("encerrar")

        self.assertIn("esquecer()", corpo)

    def test_quando_o_sinal_volta_a_corrida_pendente_sobe(self):
        self.assertIn('addEventListener("online"', JS)


class ACorridaInterrompidaVoltaTests(SimpleTestCase):
    """Retomar é escolha da pessoa, não automatismo.

    Entre a interrupção e ela reabrir a tela podem ter passado duas horas.
    Continuar contando o tempo sozinho inventaria duração — que é o mesmo
    pecado que o filtro de teleporte existe para evitar do outro lado.
    """

    def test_a_recuperacao_roda_quando_a_tela_abre(self):
        self.assertIn("recuperar();", JS)

    def test_uma_corrida_encerrada_e_nao_enviada_tenta_subir(self):
        corpo = corpo_da_funcao("recuperar")

        self.assertIn("salvo.encerrada", corpo)
        self.assertIn("salvar()", corpo)

    def test_uma_corrida_aberta_espera_a_pessoa_decidir(self):
        corpo = corpo_da_funcao("recuperar")

        self.assertIn("el.retomar.hidden = false", corpo)
        self.assertIn("el.encerrar.hidden = false", corpo)
        # E NÃO religa o GPS sozinha: quem faz isso é o botão.
        self.assertNotIn("ligarSensores()", corpo)

    def test_retomar_religa_os_sensores(self):
        """Depois de um reload não existe `watchPosition` nem relógio. Sem
        religá-los, "Retomar" mudaria os rótulos da tela sem voltar a contar
        nada — e a pessoa correria achando que estava sendo registrada."""
        self.assertIn("ligarSensores()", corpo_da_funcao("retomar"))


class UmRegistroQuebradoNaoPrendeATelaTests(SimpleTestCase):
    """Achado medindo, e não lendo.

    Um registro com `comecou` nulo e marcado como encerrado fazia `salvar()`
    estourar em `estado.comecou.toISOString()`. O erro não some sozinho: o
    registro continua no aparelho, e a tela quebra de novo TODA vez que alguém
    a abre — uma corrida presa que nunca sobe e nunca sai da frente.

    Ignorar em silêncio daria o mesmo resultado. Uma corrida sem início ou sem
    chave não é recuperável de jeito nenhum — o servidor recusaria as duas —,
    então perder o registro quebrado é melhor que deixar a tela inutilizável.
    """

    def test_registro_sem_inicio_ou_sem_chave_e_apagado(self):
        corpo = corpo_da_funcao("recuperar")

        self.assertIn("!salvo.opId || !salvo.comecou", corpo)
        self.assertIn("esquecer()", corpo)

    def test_a_guarda_vem_antes_de_qualquer_uso_do_registro(self):
        """Se ela viesse depois, o estouro já teria acontecido."""
        corpo = corpo_da_funcao("recuperar")
        guarda = corpo.index("!salvo.opId || !salvo.comecou")
        primeiro_uso = corpo.index("estado.opId = salvo.opId")

        self.assertLess(guarda, primeiro_uso)


class UmaSegundaCorridaNaMesmaPaginaTests(SimpleTestCase):
    """Três defeitos que só existem porque falhar de salvar deixou de ser fim
    de linha — e que a revisão independente encontrou.

    Antes, `comecar()` só rodava uma vez por carregamento: o salvamento
    bem-sucedido recarrega a tela. Agora a pessoa pode encerrar, o envio
    falhar, e ela tocar "Começar" de novo na mesma instância. Esse caminho
    novo revelou o que já estava frouxo.
    """

    def test_encerrar_zera_os_ids_dos_sensores(self):
        """`ligarSensores()` só religa quando eles estão nulos.

        Medido antes da correção: depois de um salvamento falho, tocar
        "Começar" de novo NÃO chamava `watchPosition`. A tela mostrava
        "Pausar" e "Encerrar", parecia estar contando, e nenhum metro era
        registrado — a pessoa correria acreditando estar sendo rastreada.

        Introduzido junto com a guarda de `ligarSensores()`, que existe para o
        botão "Retomar" não ligar dois sensores.
        """
        corpo = corpo_da_funcao("encerrar")

        self.assertIn("estado.vigia = null", corpo)
        self.assertIn("estado.relogio = null", corpo)

    def test_comecar_zera_os_acumuladores(self):
        """Sem isto, a corrida nova nasceria com a distância, o tempo e as
        parciais da anterior — uma corrida de 2 km reportada como 7 km, sem
        nada na tela sugerindo o erro."""
        corpo = corpo_da_funcao("comecar")

        for campo in ("distancia", "movimentoMs", "marcas", "proximoKm",
                      "ultimoAcumulado", "ultimoInstante", "teveLacuna", "ancora"):
            with self.subTest(campo=campo):
                self.assertRegex(corpo, r"estado\.%s = " % campo)

    def test_o_botao_comecar_fica_escondido_enquanto_o_envio_esta_em_voo(self):
        """Um toque ali começaria uma corrida NOVA por cima da que ainda está
        subindo — e o `reload()` do sucesso mataria a nova em silêncio."""
        encerrar = corpo_da_funcao("encerrar")

        # POSIÇÃO, e não presença. A primeira versão deste teste olhava só o
        # trecho DEPOIS do primeiro `return;`, e a sabotagem que reintroduz o
        # defeito insere a linha ANTES dele — então ela passava verde. Um teste
        # que examina a metade errada do corpo não prova nada sobre a outra.
        self.assertEqual(encerrar.count("el.comecar.hidden = false"), 1)
        guarda = encerrar.index("if (semSalvar")
        revelacao = encerrar.index("el.comecar.hidden = false")
        self.assertGreater(
            revelacao, guarda,
            "o botão reaparece antes de o script saber se vai salvar",
        )

        # E ele volta quando a tentativa termina, nos dois ramos de falha.
        salvar = corpo_da_funcao("salvar")
        self.assertEqual(salvar.count("el.comecar.hidden = false"), 2)

    def test_o_reenvio_na_abertura_tambem_esconde_o_botao(self):
        corpo = corpo_da_funcao("recuperar")
        ramo = corpo.split("salvo.encerrada", 1)[1].split("return;", 1)[0]

        self.assertIn("el.comecar.hidden = true", ramo)


class PermissaoRevogadaNoMeioNaoJogaACorridaForaTests(SimpleTestCase):
    """A permissão some no meio — o iOS faz isso em segundo plano, e basta um
    toque errado num novo pedido.

    Antes, isso chamava `encerrar(true)`, que descarta SEM olhar a distância, e
    a tela ainda dizia "corrida encerrada sem distância registrada" — falso,
    havia 5 km registrados. Apagar dado real e dizer que não havia dado é a
    versão pior do defeito que o projeto combate do outro lado.
    """

    def test_com_distancia_o_encerramento_e_o_normal(self):
        corpo = corpo_da_funcao("erroDoGps")

        self.assertIn("estado.distancia >= 1", corpo)
        self.assertIn("encerrar(false)", corpo)

    def test_sem_distancia_continua_descartando(self):
        """Contra-controle: sem ele, um `encerrar(false)` incondicional tentaria
        salvar corrida vazia toda vez que a permissão fosse negada na largada."""
        corpo = corpo_da_funcao("erroDoGps")

        self.assertIn("encerrar(true)", corpo)


class OErroDizOQueAconteceuTests(SimpleTestCase):
    """A mensagem que explica não pode ser sobrescrita pela genérica.

    Medido no navegador: negar a localização na largada mostrava "Corrida
    encerrada sem distância registrada". Verdade, mas irrelevante — e escondia
    a única coisa que a pessoa pode resolver, que é a permissão.

    `encerrar()` termina dizendo a frase da distância, então quem quer explicar
    o motivo precisa falar DEPOIS dele.
    """

    def test_a_explicacao_da_permissao_vem_depois_do_encerrar(self):
        corpo = sem_comentarios(corpo_da_funcao("erroDoGps"))
        ramo = corpo.split("PERMISSION_DENIED", 1)[1]
        fecha = ramo.index("encerrar(true)")
        explica = ramo.index("Sem permissao de localizacao")

        self.assertGreater(
            explica, fecha,
            "a explicação é escrita antes e o encerrar a sobrescreve",
        )


class DuploToqueNaoQuebraACorridaTests(SimpleTestCase):
    """A regra é de ESTADO, não do DOM.

    `hidden` no botão protege no navegador real, e foi o que segurou até aqui.
    Mas depender do DOM para uma regra de estado é frágil: um `click()`
    programático, um atalho de teclado, ou alguém mover o `hidden` de lugar
    reabrem o caminho.

    Medido antes da guarda: um segundo `comecar()` trocava o `op_id` e zerava
    os contadores da corrida em andamento — ela perdia a identidade com que
    seria salva. E dois toques em "Encerrar" com a rede caída disparavam DOIS
    envios; o servidor é idempotente e não duplicaria a corrida, mas a segunda
    resposta sobrescreve a mensagem da primeira.
    """

    def test_comecar_recusa_por_cima_de_corrida_viva_ou_envio_em_voo(self):
        corpo = corpo_da_funcao("comecar")
        guarda = corpo.index("estado.correndo || estado.enviando")
        primeira_escrita = corpo.index("estado.opId = identificador()")

        self.assertLess(guarda, primeira_escrita, "a guarda vem depois do estrago")

    def test_encerrar_recusa_durante_o_envio(self):
        corpo = corpo_da_funcao("encerrar")
        guarda = corpo.index("if (estado.enviando) return;")
        limpeza = corpo.index("clearWatch")

        self.assertLess(guarda, limpeza)

    def test_o_envio_marca_e_desmarca_o_estado_nos_dois_ramos(self):
        """Se ele não desmarcasse na falha, a tela ficaria travada para sempre:
        nem começar de novo, nem encerrar."""
        corpo = corpo_da_funcao("salvar")

        self.assertIn("estado.enviando = true", corpo)
        self.assertEqual(corpo.count("estado.enviando = false"), 2)
