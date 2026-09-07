"""Gravar corrida: idempotência, limites e o que o servidor não pode conferir."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from workouts.models import Corrida

User = get_user_model()


class SalvarCorridaTests(TestCase):
    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="corredora@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)
        self.comecou = timezone.now() - timedelta(minutes=50)
        self.terminou = timezone.now()

    def _corpo(self, **mudancas):
        corpo = {
            "op_id": "corrida-abc-123",
            "comecou_em": self.comecou.isoformat(),
            "terminou_em": self.terminou.isoformat(),
            "distancia_m": 10_000,
            "duracao_s": 2_900,
            "teve_lacuna": False,
            "parciais": [{"km": 1, "segundos": 290.0}],
        }
        corpo.update(mudancas)
        return corpo

    def _postar(self, **mudancas):
        return self.client.post(
            "/treino/corridas/salvar/",
            data=json.dumps(self._corpo(**mudancas)),
            content_type="application/json",
        )

    def test_grava_a_corrida(self):
        resposta = self._postar()

        self.assertEqual(resposta.status_code, 200)
        corrida = Corrida.objects.get(user=self.pessoa)
        self.assertEqual(corrida.distancia_m, 10_000)
        self.assertEqual(corrida.parciais, [{"km": 1, "segundos": 290.0}])

    def test_reenvio_nao_duplica(self):
        """A fila offline reenvia o que ficou parado. Sem chave, o reenvio
        criaria uma segunda corrida idêntica — o mesmo problema que
        `SyncedOperation` resolve para água e suplemento."""
        self._postar()
        resposta = self._postar()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_reenvio_responde_200_e_nao_erro(self):
        """Erro faria a fila tentar de novo para sempre."""
        self._postar()

        resposta = self._postar()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["distancia_m"], 10_000)

    def test_duas_pessoas_podem_sortear_o_mesmo_identificador(self):
        """A chave nasce no navegador. Global, ela faria a corrida de uma
        pessoa bloquear a de outra."""
        self._postar()
        outra = User.objects.create_user(
            email="outro@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(outra)

        self._postar()

        self.assertEqual(Corrida.objects.count(), 2)

    def test_recusa_distancia_absurda(self):
        """O servidor não tem as leituras e não pode conferir a distância. O
        que ele pode é recusar o impossível — senão um POST forjado inventa uma
        maratona."""
        resposta = self._postar(distancia_m=40_000_000)

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_recusa_tempo_em_movimento_maior_que_o_relogio(self):
        """Cinquenta minutos de relógio não cabem duas horas de movimento."""
        resposta = self._postar(duracao_s=7_200)

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_recusa_corrida_que_termina_antes_de_comecar(self):
        resposta = self._postar(
            terminou_em=(self.comecou - timedelta(minutes=5)).isoformat()
        )

        self.assertEqual(resposta.status_code, 400)

    def test_recusa_numero_negativo(self):
        self.assertEqual(self._postar(distancia_m=-5).status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_recusa_corpo_sem_identificador(self):
        self.assertEqual(self._postar(op_id="").status_code, 400)

    def test_recusa_corpo_invalido(self):
        resposta = self.client.post(
            "/treino/corridas/salvar/", data="nao é json",
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 400)

    def test_anonimo_nao_grava(self):
        self.client.logout()

        resposta = self._postar()

        self.assertIn(resposta.status_code, (302, 403))
        self.assertEqual(Corrida.objects.count(), 0)

    def test_ninguem_grava_corrida_na_conta_de_outra_pessoa(self):
        """O dono vem da SESSÃO, e o corpo não tem campo de usuário. Um POST
        que tentasse escolher o dono não teria por onde."""
        self._postar()

        corrida = Corrida.objects.get()
        self.assertEqual(corrida.user, self.pessoa)


class CorridaModeloTests(TestCase):
    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="modelo@exemplo.com", password="senha-bem-forte-123"
        )

    def _corrida(self, **campos):
        base = dict(
            user=self.pessoa, op_id="x", comecou_em=timezone.now(),
            terminou_em=timezone.now(), distancia_m=10_000, duracao_s=3_000,
        )
        base.update(campos)
        return Corrida.objects.create(**base)

    def test_o_pace_e_derivado_e_nao_guardado(self):
        """Terceira cópia do mesmo fato é cópia para ficar errada."""
        corrida = self._corrida()

        self.assertEqual(corrida.pace_s_km, 300.0)
        self.assertNotIn("pace", [f.name for f in Corrida._meta.fields])

    def test_sem_distancia_nao_ha_pace(self):
        self.assertIsNone(self._corrida(distancia_m=0).pace_s_km)

    def test_apagar_a_conta_apaga_a_corrida(self):
        """Rota diz onde a pessoa mora. Toda FK para User neste projeto é
        CASCADE para que apagar a conta apague o dado pessoal."""
        self._corrida()

        self.pessoa.delete()

        self.assertEqual(Corrida.objects.count(), 0)

    def test_o_tracado_nao_e_guardado(self):
        """Decisão, não pendência: não existe mapa, e guardar coordenada "para
        quando existir" é coletar o dado mais sensível do app por antecipação."""
        campos = {f.name for f in Corrida._meta.fields}

        for proibido in ("tracado", "rota", "pontos", "lat", "lon", "coordenadas"):
            with self.subTest(campo=proibido):
                self.assertNotIn(proibido, campos)


class MesmosLimitesTests(TestCase):
    """O Python e o JavaScript filtram com os MESMOS números.

    Os dois calculam distância — o navegador para mostrar ao vivo, o Python
    para os testes e para qualquer recontagem futura. Duas cópias do mesmo
    limite é como uma delas fica para trás, e o sintoma seria o pior possível:
    a tela mostrando uma distância e o servidor guardando outra, sem erro
    nenhum aparecer.

    O teste lê o arquivo do worker porque não há como executar o JavaScript
    aqui: não existe Node neste ambiente, e está no `CLAUDE.md`.
    """

    def setUp(self):
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent
        self.js = (raiz / "static" / "js" / "corrida.js").read_text(encoding="utf-8")

    def test_os_limites_do_filtro_batem(self):
        from workouts import corrida

        pares = (
            ("PRECISAO_MAXIMA_M", corrida.PRECISAO_MAXIMA_M),
            ("VELOCIDADE_MAXIMA_MS", corrida.VELOCIDADE_MAXIMA_MS),
            ("DESLOCAMENTO_MINIMO_M", corrida.DESLOCAMENTO_MINIMO_M),
        )
        for nome, valor in pares:
            with self.subTest(limite=nome):
                self.assertIn(f"var {nome} = {valor}", self.js)

    def test_o_raio_da_terra_bate(self):
        from workouts import corrida

        self.assertIn(f"var RAIO_DA_TERRA_M = {corrida.RAIO_DA_TERRA_M}", self.js)

    def test_o_navegador_nao_manda_coordenada(self):
        """O corpo que sobe tem distância, tempo e parciais. Coordenada morre
        no aparelho — e este teste é o que impede alguém de acrescentar
        `pontos` ao payload sem passar pela decisão."""
        corpo = self.js[self.js.index("var corpo = {") :][:400]

        for proibido in ("lat", "lon", "coords", "tracado", "pontos"):
            with self.subTest(campo=proibido):
                self.assertNotIn(proibido, corpo)

    def test_a_ancora_some_quando_a_pagina_volta(self):
        """Ligar o ponto de antes ao de agora desenharia uma reta que ninguém
        correu."""
        trecho = self.js[self.js.index("visibilitychange") :][:900]

        self.assertIn("estado.ancora = null", trecho)
        self.assertIn("estado.teveLacuna = true", trecho)


class ACorridaTemPortaTests(TestCase):
    """Tela sem porta não é tela.

    A tela de corridas nasceu alcançável só digitando o endereço — o mesmo
    defeito da ação administrativa que ganhou rota e não ganhou botão. Uma
    funcionalidade que ninguém encontra é código que passa nos testes e não
    serve a ninguém, e testar a rota não pega isso: ela respondia 200 o tempo
    todo.
    """

    def setUp(self):
        from datetime import date, time

        from accounts.models import (
            ONBOARDING_DONE, ActivityLevel, Goal, Profile, Sex,
        )

        self.pessoa = User.objects.create_user(
            email="porta@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.pessoa, sex=Sex.MALE, birth_date=date(1995, 4, 12),
            height_cm=178, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            wake_time=time(7, 0), sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE,
        )
        self.client.force_login(self.pessoa)

    def test_a_tela_de_treino_leva_as_corridas(self):
        html = self.client.get("/treino/").content.decode()

        self.assertIn('href="/treino/corridas/"', html)

    def test_a_porta_avisa_do_limite_antes_de_abrir(self):
        """Quem chega na tela de corridas já sabe o que vai encontrar. O aviso
        aparece de novo lá, e de propósito: este é o que evita a pessoa entrar
        achando que dá para guardar o telefone."""
        html = self.client.get("/treino/").content.decode()

        self.assertIn("tela acesa", html)


class CsrfDeVerdadeTests(TestCase):
    """O cliente de teste do Django NÃO confere CSRF por padrão.

    Todos os outros testes daqui postam com a checagem desligada — então
    nenhum deles prova que o endpoint aceita o token pelo cabeçalho, que é como
    o `fetch` do navegador manda. Um endpoint que só funciona nos testes é
    exatamente o tipo de coisa que aparece em produção como "não consegui
    salvar".
    """

    def setUp(self):
        from django.test import Client

        self.pessoa = User.objects.create_user(
            email="csrf@exemplo.com", password="senha-bem-forte-123"
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.pessoa)
        self.comecou = timezone.now() - timedelta(minutes=30)

    def _corpo(self):
        return json.dumps(
            {
                "op_id": "corrida-csrf",
                "comecou_em": self.comecou.isoformat(),
                "terminou_em": timezone.now().isoformat(),
                "distancia_m": 5_000,
                "duracao_s": 1_500,
                "parciais": [],
            }
        )

    def test_com_o_token_no_cabecalho_grava(self):
        # O cookie nasce numa visita comum; é ele que o `fetch` lê.
        self.client.get("/treino/corridas/")
        token = self.client.cookies["csrftoken"].value

        resposta = self.client.post(
            "/treino/corridas/salvar/",
            data=self._corpo(),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Corrida.objects.count(), 1)

    def test_sem_o_token_o_servidor_recusa(self):
        """Controle: sem isto, o teste acima passaria igual se a proteção
        estivesse desligada."""
        resposta = self.client.post(
            "/treino/corridas/salvar/",
            data=self._corpo(),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Corrida.objects.count(), 0)


class OServidorRecusaOImpossivelTests(TestCase):
    """Três recusas que faltavam, e a razão de as três terem passado.

    A conferência olhava cada número SOZINHO: distância dentro do teto,
    duração dentro do teto, fim depois do começo. Nenhuma delas via a relação
    entre eles nem o tamanho do que vinha junto.

    O docstring de `_conferir` diz que ela existe para um POST forjado não
    "inventar uma maratona". Ele inventava — só que rápida: 100 km em
    dezesseis minutos passava, porque 100.000 está abaixo do teto de distância
    e 1.000 s está abaixo do teto de duração.

    Medido contra o servidor de desenvolvimento durante a auditoria, com conta
    de QA.
    """

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="impossivel@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)
        self.comecou = timezone.now() - timedelta(minutes=50)
        self.terminou = timezone.now()

    def _postar(self, **mudancas):
        corpo = {
            "op_id": "corrida-limite",
            "comecou_em": self.comecou.isoformat(),
            "terminou_em": self.terminou.isoformat(),
            "distancia_m": 10_000, "duracao_s": 2_900,
            "teve_lacuna": False, "parciais": [{"km": 1, "segundos": 290.0}],
        }
        corpo.update(mudancas)
        return self.client.post("/treino/corridas/salvar/",
                                data=json.dumps(corpo),
                                content_type="application/json")

    def test_corrida_de_distancia_zero_e_recusada(self):
        """0 m com 2.900 s de duração não é corrida — é o GPS tremendo parado,
        ou um reenvio torto. Entrava no histórico como uma linha vazia."""
        resposta = self._postar(distancia_m=0, op_id="zero")

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_velocidade_impossivel_e_recusada(self):
        """100 km em 1.000 s = 100 m/s. Os dois números passavam sozinhos."""
        resposta = self._postar(distancia_m=100_000, duracao_s=1_000,
                                op_id="voando")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("velocidade", resposta.json()["erro"])
        self.assertEqual(Corrida.objects.count(), 0)

    def test_parciais_demais_sao_recusadas(self):
        """`parciais` é JSON livre e ia inteiro para o banco."""
        resposta = self._postar(
            parciais=[{"km": i, "segundos": 300} for i in range(5_000)],
            op_id="gordo",
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_parciais_que_nao_sao_lista_sao_recusadas(self):
        resposta = self._postar(parciais={"km": 1}, op_id="torto")

        self.assertEqual(resposta.status_code, 400)

    def test_uma_corrida_normal_continua_passando(self):
        """CONTROLE POSITIVO. Sem ele, uma guarda apertada demais recusaria
        corrida de gente de verdade e os testes acima não notariam.

        10 km em 48 minutos é 3,45 m/s — pace de 4:50/km.
        """
        resposta = self._postar(op_id="normal")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Corrida.objects.count(), 1)

    def test_um_recorde_mundial_ainda_passa(self):
        """A guarda recusa o IMPOSSÍVEL, não o excepcional: a maratona mundial
        é 42,195 km em 2h01 (5,78 m/s), e ela tem de passar.

        A JANELA VIAJA JUNTO, e isto não é arrumação: a primeira versão deste
        teste trocou só a duração e deixou o `setUp` de 50 minutos, então
        7.299 s de movimento dentro de 3.000 s de relógio caíam na regra
        "tempo em movimento maior que o tempo total" — que é ANTERIOR a esta
        auditoria e estava certa. O teste ficava vermelho acusando o guarda
        errado, e o guarda de velocidade que ele veio provar nunca era
        alcançado.
        """
        resposta = self._postar(
            distancia_m=42_195, duracao_s=7_299, op_id="recorde",
            comecou_em=(self.terminou - timedelta(seconds=7_400)).isoformat(),
        )

        self.assertEqual(resposta.status_code, 200, resposta.content[:200])


class DuracaoZeroNaoAtravessaAGuardaDeVelocidadeTests(TestCase):
    """O `duracao > 0` que protegia a divisão desligava a regra inteira.

    Achado em revisão adversarial da própria correção: a guarda de velocidade
    foi escrita para recusar o impossível, e a proteção contra divisão por zero
    abriu a porta exatamente no caso mais extremo. Medido contra o servidor de
    desenvolvimento com conta de QA: 299.999 m em 0 s respondeu **200** e
    gravou a corrida.
    """

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="zero-segundos@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)
        self.instante = timezone.now()

    def _postar(self, **mudancas):
        corpo = {
            "op_id": "duracao-zero",
            "comecou_em": self.instante.isoformat(),
            "terminou_em": self.instante.isoformat(),
            "distancia_m": 299_999, "duracao_s": 0,
            "teve_lacuna": False, "parciais": [],
        }
        corpo.update(mudancas)
        return self.client.post("/treino/corridas/salvar/", data=json.dumps(corpo),
                                content_type="application/json")

    def test_trezentos_km_em_zero_segundos_e_recusado(self):
        resposta = self._postar()

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_qualquer_distancia_com_duracao_zero_e_recusada(self):
        """Não é só o número gigante: 100 m em zero segundo também é
        impossível, e passava pelo mesmo buraco."""
        resposta = self._postar(distancia_m=100, op_id="cem-metros-zero")

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Corrida.objects.count(), 0)

    def test_uma_corrida_de_um_segundo_ainda_passa_se_for_possivel(self):
        """CONTROLE POSITIVO: a guarda recusa duração ZERO, não duração curta.
        Dez metros em um segundo é 10 m/s — abaixo do teto de 12,5."""
        resposta = self._postar(distancia_m=60, duracao_s=6, op_id="curtinha")

        self.assertEqual(resposta.status_code, 200, resposta.content[:200])
        self.assertEqual(Corrida.objects.count(), 1)
