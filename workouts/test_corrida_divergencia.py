# -*- coding: utf-8 -*-
"""A divergência entre a Corrida da web e a Corrida da API é DELIBERADA.

Existem dois caminhos que calculam distância, e eles não concordam:

    web / PWA      -> motor JavaScript, traçado NÃO persiste
    mobile / API   -> `workouts/corrida.py` autoritativo, traçado persiste

Isso tem cara de dívida técnica e não é. Unificar foi proposto e **recusado
pelo dono do produto em 04/09/2026**: a PWA não consegue cumprir o requisito
central (GPS em segundo plano com a tela bloqueada) de jeito nenhum, então
fazê-la enviar coordenada começaria a coletar o dado mais sensível do app de
52 contas reais sem resolver nada.

Estes testes existem porque a decisão é frágil de um jeito específico: ela
parece um descuido. Quem chegar depois vê um motor Python testado de um lado e
um cálculo em JavaScript do outro, e a conclusão natural é "isto está
duplicado, vou unificar". Documentação não impede isso — teste vermelho
impede.

O raciocínio completo está em `docs/corrida-mobile-arquitetura.md`, seção 3-B.
"""
import json
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from push.test_cache_privado import sem_comentarios
from workouts.models import Corrida, TracoDaCorrida

User = get_user_model()


class OCaminhoDaWebNaoColetaCoordenadaTests(TestCase):
    """O endpoint que a PWA publicada usa não aceita, não calcula e não guarda
    percurso — e é assim que tem de continuar até alguém decidir o contrário."""

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="corredora.web@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)
        self.comecou = timezone.now() - timedelta(minutes=50)
        self.terminou = timezone.now()

    def _postar(self, **mudancas):
        corpo = {
            "op_id": "corrida-web-1",
            "comecou_em": self.comecou.isoformat(),
            "terminou_em": self.terminou.isoformat(),
            "distancia_m": 10_000,
            "duracao_s": 2_900,
            "teve_lacuna": False,
            "parciais": [],
        }
        corpo.update(mudancas)
        return self.client.post(
            "/treino/corridas/salvar/",
            data=json.dumps(corpo),
            content_type="application/json",
        )

    def test_a_rota_da_pwa_nao_guarda_tracado_nem_quando_recebe_pontos(self):
        """Alguém pode passar a mandar `pontos` para cá — um cliente novo, um
        teste, um copiar-e-colar da API. A rota tem de ignorar.

        Não é sobre desconfiar do cliente: é que aceitar silenciosamente faria
        a coleta de coordenada começar sem ninguém ter decidido que ela
        começasse.
        """
        pontos = [
            {"lat": -23.55 + i * 0.0001, "lon": -46.63, "t": i, "accuracy": 5}
            for i in range(60)
        ]

        resposta = self._postar(pontos=pontos)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(TracoDaCorrida.objects.count(), 0)

    def test_a_distancia_da_web_continua_sendo_a_do_cliente(self):
        """Contraste deliberado com a API, onde o número do cliente é ignorado.

        Se algum dia esta asserção falhar, alguém ligou o motor autoritativo no
        caminho da web — que é exatamente a unificação recusada. Falhar aqui é
        o aviso.
        """
        self._postar(distancia_m=10_000)

        corrida = Corrida.objects.get(user=self.pessoa)
        self.assertEqual(corrida.distancia_m, 10_000)

    def test_o_javascript_da_pwa_nao_envia_coordenada(self):
        """A asserção é sobre o CORPO do envio, não sobre o arquivo inteiro.

        `corrida.js` manipula latitude e longitude o tempo todo — é o que ele
        faz para calcular a distância no aparelho. Procurar "lat" no arquivo
        acusaria sempre. O que importa é o objeto que vai no `JSON.stringify`,
        e é só ele que este teste lê.

        Comentários saem antes: este projeto comenta muito, e o comentário
        vizinho cita o nome da coisa que a asserção procura.
        """
        with open("static/js/corrida.js", encoding="utf-8") as arquivo:
            codigo = sem_comentarios(arquivo.read())

        inicio = codigo.index("function salvar()")
        corpo = codigo[inicio : codigo.index("};", inicio)]

        # Controle positivo: se o recorte errar o bloco, estas duas falham e o
        # teste não passa por estar olhando para lugar nenhum.
        self.assertIn("op_id", corpo)
        self.assertIn("distancia_m", corpo)

        self.assertNotIn("lat", corpo)
        self.assertNotIn("lon", corpo)
        self.assertNotIn("pontos", corpo)


class OTracadoNaoTemTelaNoAdminTests(TestCase):
    """O percurso é o dado mais sensível do app, e nenhuma tela administrativa
    o alcança.

    Hoje a proteção é a AUSÊNCIA de registro — a mesma fragilidade que o B10
    apontou em `WeightEntry`: "a única das nove que um `@admin.register`
    distraído reabriria sem tocar em permissão nenhuma".

    Este teste transforma a ausência em contrato. Registrar o traçado no Admin
    passa a exigir apagar uma asserção que diz por que ele não pode ser
    registrado.
    """

    def test_o_tracado_nao_esta_registrado_no_admin(self):
        registrados = {m._meta.label for m in admin.site._registry}

        self.assertNotIn("workouts.TracoDaCorrida", registrados)

    def test_a_corrida_tambem_nao_esta_registrada(self):
        """Mesma família: a corrida diz a que horas a pessoa saiu de casa, e
        não responde pergunta de suporte nenhuma."""
        registrados = {m._meta.label for m in admin.site._registry}

        self.assertNotIn("workouts.Corrida", registrados)
