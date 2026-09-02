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
