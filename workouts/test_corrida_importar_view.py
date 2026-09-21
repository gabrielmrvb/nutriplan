# -*- coding: utf-8 -*-
"""A tela que importa uma corrida de arquivo (decisão 4 da avaliação, 20/09/2026).

O registro à mão continua sendo o caminho principal; esta é a segunda porta.
A view orquestra: lê o upload, chama o parser puro (`importar_corrida`),
aplica os MESMOS tetos do GPS (`corrida_views`) e grava uma `Corrida` com
`origem="arquivo"` — que não se edita, pelo mesmo motivo do GPS (o traço
contradiria os números). Idempotente pelo conteúdo: reimportar o mesmo arquivo
não cria uma segunda corrida.
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from workouts.corrida_views import TAMANHO_MAXIMO_ARQUIVO
from workouts.models import Corrida
from workouts.tests import create_user


def _gpx_bytes(n=25, lat0=-23.5, passo=0.001):
    pts = "".join(
        f'<trkpt lat="{lat0 + i * passo}" lon="-46.6"><time>2026-09-20T10:{i:02d}:00Z</time></trkpt>'
        for i in range(n)
    )
    xml = (
        '<?xml version="1.0"?>'
        '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><trkseg>{pts}</trkseg></trk></gpx>"
    )
    return xml.encode("utf-8")


def _upload(conteudo, nome="corrida.gpx"):
    return SimpleUploadedFile(nome, conteudo, content_type="application/gpx+xml")


class ImportarCorridaViewTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="importa@exemplo.com")
        self.client.force_login(self.pessoa)
        self.url = reverse("workouts:corrida_importar")

    def test_get_mostra_formulario_de_upload(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn('type="file"', html)
        self.assertIn('name="arquivo"', html)

    def test_importa_gpx_e_cria_corrida_de_arquivo(self):
        r = self.client.post(self.url, {"arquivo": _upload(_gpx_bytes())})
        self.assertRedirects(r, reverse("workouts:corridas"))
        corrida = Corrida.objects.get(user=self.pessoa)
        self.assertEqual(corrida.origem, Corrida.Origem.ARQUIVO)
        self.assertGreater(corrida.distancia_m, 2600)
        self.assertLess(corrida.distancia_m, 2750)
        self.assertEqual(corrida.duracao_s, 24 * 60)
        self.assertEqual(len(corrida.parciais), 2)

    def test_reimportar_o_mesmo_arquivo_nao_duplica(self):
        conteudo = _gpx_bytes()
        self.client.post(self.url, {"arquivo": _upload(conteudo)})
        self.client.post(self.url, {"arquivo": _upload(conteudo)})
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_arquivo_de_outra_pessoa_com_mesmo_conteudo_nao_colide(self):
        """O `op_id` do arquivo é único POR PESSOA (o constraint é
        `user, op_id`): duas pessoas podem importar o mesmo percurso."""
        conteudo = _gpx_bytes()
        self.client.post(self.url, {"arquivo": _upload(conteudo)})
        outra = create_user(email="outra-importa@exemplo.com")
        self.client.force_login(outra)
        self.client.post(self.url, {"arquivo": _upload(conteudo)})
        self.assertEqual(Corrida.objects.filter(user=outra).count(), 1)
        self.assertEqual(Corrida.objects.count(), 2)

    def test_sem_arquivo_volta_com_erro(self):
        r = self.client.post(self.url, {})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Corrida.objects.exists())
        self.assertContains(r, "arquivo")

    def test_arquivo_invalido_volta_com_erro_e_nao_cria(self):
        r = self.client.post(self.url, {"arquivo": _upload(b"isto nao e xml <<<", "corrida.gpx")})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Corrida.objects.exists())

    def test_arquivo_sem_pontos_volta_com_erro(self):
        vazio = b'<?xml version="1.0"?><gpx><trk><trkseg></trkseg></trk></gpx>'
        r = self.client.post(self.url, {"arquivo": _upload(vazio)})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Corrida.objects.exists())

    def test_doctype_e_recusado(self):
        veneno = (
            b'<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY a "x">]>'
            b'<gpx><trk><trkseg>'
            b'<trkpt lat="-23.5" lon="-46.6"><time>2026-09-20T10:00:00Z</time></trkpt>'
            b'<trkpt lat="-23.501" lon="-46.6"><time>2026-09-20T10:01:00Z</time></trkpt>'
            b'</trkseg></trk></gpx>'
        )
        r = self.client.post(self.url, {"arquivo": _upload(veneno)})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Corrida.objects.exists())

    def test_corrida_curta_demais_e_recusada(self):
        """Pontos a ~0,5 m um do outro são ruído de GPS parado — o motor recusa
        todos, a distância dá 0, e 0 não vira corrida (mesma régua do GPS)."""
        parado = _gpx_bytes(n=5, passo=0.000005)
        r = self.client.post(self.url, {"arquivo": _upload(parado)})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Corrida.objects.exists())

    def test_arquivo_grande_demais_e_recusado_sem_parsear(self):
        grande = b"a" * (TAMANHO_MAXIMO_ARQUIVO + 1)
        r = self.client.post(self.url, {"arquivo": _upload(grande)})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Corrida.objects.exists())

    def test_corrida_importada_nao_pode_ser_editada(self):
        self.client.post(self.url, {"arquivo": _upload(_gpx_bytes())})
        corrida = Corrida.objects.get(user=self.pessoa)
        r = self.client.get(reverse("workouts:corrida_editar", args=[corrida.pk]))
        self.assertEqual(r.status_code, 404)

    def test_anonimo_vai_para_o_login(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/entrar", r.url)
