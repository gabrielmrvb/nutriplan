# -*- coding: utf-8 -*-
"""Importar corrida de arquivo GPX/TCX (decisão 4 da avaliação de UX, 20/09/2026).

O registro à mão continua sendo o caminho; a importação de ARQUIVO é a
segunda porta — quem já corre com Garmin, Strava ou Apple Saúde exporta o
percurso e traz o número pronto, em vez de digitar. A Strava API fica de fora
(precisa de app registrado e credencial que este ambiente não tem — está em
`docs/running-analise.md`), e GPS ao vivo em segundo plano continua fora por
ausência de API na PWA.

O parser é PURO: recebe o conteúdo do arquivo e devolve as leituras no formato
que `workouts.corrida.percurso` já entende — o mesmo motor que trata o GPS ao
vivo trata o arquivo, então a distância sai de uma conta só.
"""
from datetime import datetime, timezone as tz

from django.test import SimpleTestCase

from workouts import importar_corrida as imp


def _gpx(trkpts, ns=True):
    """Um GPX mínimo. `trkpts` = [(lat, lon, iso_time_ou_None), ...]."""
    abre = '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">' if ns else "<gpx>"
    linhas = []
    for lat, lon, t in trkpts:
        tempo = f"<time>{t}</time>" if t else ""
        linhas.append(f'<trkpt lat="{lat}" lon="{lon}">{tempo}</trkpt>')
    return f'<?xml version="1.0"?>{abre}<trk><trkseg>{"".join(linhas)}</trkseg></trk></gpx>'


def _tcx(pontos):
    """Um TCX mínimo. `pontos` = [(lat, lon, iso_time), ...]."""
    tps = []
    for lat, lon, t in pontos:
        tps.append(
            f"<Trackpoint><Time>{t}</Time><Position>"
            f"<LatitudeDegrees>{lat}</LatitudeDegrees>"
            f"<LongitudeDegrees>{lon}</LongitudeDegrees>"
            f"</Position></Trackpoint>"
        )
    return (
        '<?xml version="1.0"?>'
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        f"<Activities><Activity><Lap><Track>{''.join(tps)}</Track></Lap></Activity></Activities>"
        "</TrainingCenterDatabase>"
    )


class ParserExtraiPontosTests(SimpleTestCase):
    def test_gpx_extrai_lat_lon_e_t_relativo_ao_inicio(self):
        """O parser devolve as coordenadas EXATAS do arquivo e o t em segundos
        contado a partir da primeira leitura — é isso que `percurso` consome."""
        gpx = _gpx([
            (-23.500, -46.600, "2026-09-20T10:00:00Z"),
            (-23.501, -46.600, "2026-09-20T10:01:00Z"),
            (-23.502, -46.600, "2026-09-20T10:02:00Z"),
        ])
        leituras, comecou = imp.leituras_de_arquivo(gpx, "corrida.gpx")
        self.assertEqual([l["lat"] for l in leituras], [-23.500, -23.501, -23.502])
        self.assertEqual([l["lon"] for l in leituras], [-46.600, -46.600, -46.600])
        self.assertEqual([l["t"] for l in leituras], [0.0, 60.0, 120.0])
        self.assertEqual(comecou, datetime(2026, 9, 20, 10, 0, 0, tzinfo=tz.utc))

    def test_tcx_extrai_lat_lon_e_t(self):
        tcx = _tcx([
            (-23.500, -46.600, "2026-09-20T10:00:00Z"),
            (-23.501, -46.600, "2026-09-20T10:00:30Z"),
        ])
        leituras, comecou = imp.leituras_de_arquivo(tcx, "corrida.tcx")
        self.assertEqual([l["lat"] for l in leituras], [-23.500, -23.501])
        self.assertEqual([l["t"] for l in leituras], [0.0, 30.0])
        self.assertEqual(comecou, datetime(2026, 9, 20, 10, 0, 0, tzinfo=tz.utc))

    def test_reconhece_gpx_pela_raiz_mesmo_com_extensao_errada(self):
        """O formato é decidido pela raiz do XML, não pela extensão: um GPX
        salvo como .txt ainda é um GPX."""
        gpx = _gpx([(-23.5, -46.6, "2026-09-20T10:00:00Z"), (-23.501, -46.6, "2026-09-20T10:01:00Z")])
        leituras, _ = imp.leituras_de_arquivo(gpx, "qualquer.txt")
        self.assertEqual(len(leituras), 2)

    def test_gpx_sem_namespace_tambem_parseia(self):
        gpx = _gpx([(-23.5, -46.6, "2026-09-20T10:00:00Z"), (-23.501, -46.6, "2026-09-20T10:01:00Z")], ns=False)
        leituras, _ = imp.leituras_de_arquivo(gpx, "corrida.gpx")
        self.assertEqual(len(leituras), 2)

    def test_pontos_sem_posicao_sao_ignorados(self):
        """TCX traz Trackpoint só com batimento (sem Position). Ele não é ponto
        de percurso e não pode virar leitura sem lat/lon."""
        tcx = (
            '<?xml version="1.0"?>'
            '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
            "<Activities><Activity><Lap><Track>"
            "<Trackpoint><Time>2026-09-20T10:00:00Z</Time><HeartRateBpm><Value>120</Value></HeartRateBpm></Trackpoint>"
            "<Trackpoint><Time>2026-09-20T10:00:00Z</Time><Position><LatitudeDegrees>-23.5</LatitudeDegrees><LongitudeDegrees>-46.6</LongitudeDegrees></Position></Trackpoint>"
            "<Trackpoint><Time>2026-09-20T10:01:00Z</Time><Position><LatitudeDegrees>-23.501</LatitudeDegrees><LongitudeDegrees>-46.6</LongitudeDegrees></Position></Trackpoint>"
            "</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
        )
        leituras, _ = imp.leituras_de_arquivo(tcx, "corrida.tcx")
        self.assertEqual(len(leituras), 2)


class ParserRecusaTests(SimpleTestCase):
    def test_recusa_doctype_para_barrar_xxe_e_billion_laughs(self):
        """GPX/TCX nunca declaram DTD. Recusar DOCTYPE mata de uma vez o XXE
        (entidade externa lendo arquivo do servidor) e o billion-laughs
        (expansão de entidade que explode a memória) — sem depender de uma
        biblioteca que este ambiente não tem (`defusedxml`)."""
        # DOIS pontos válidos de propósito: sem o guarda de DOCTYPE o arquivo
        # parsearia com sucesso, então quem faz o teste ficar vermelho ao
        # remover o guarda é O GUARDA, não a régua de "poucos pontos".
        veneno = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE gpx [<!ENTITY a "aaaa">]>'
            '<gpx><trk><trkseg>'
            '<trkpt lat="-23.5" lon="-46.6"><time>2026-09-20T10:00:00Z</time></trkpt>'
            '<trkpt lat="-23.501" lon="-46.6"><time>2026-09-20T10:01:00Z</time></trkpt>'
            '</trkseg></trk></gpx>'
        )
        with self.assertRaises(imp.ArquivoDeCorridaInvalido):
            imp.leituras_de_arquivo(veneno, "corrida.gpx")

    def test_recusa_xml_quebrado(self):
        with self.assertRaises(imp.ArquivoDeCorridaInvalido):
            imp.leituras_de_arquivo("isto não é xml <<<", "corrida.gpx")

    def test_recusa_formato_que_nao_e_gpx_nem_tcx(self):
        with self.assertRaises(imp.ArquivoDeCorridaInvalido):
            imp.leituras_de_arquivo('<?xml version="1.0"?><outra_coisa/>', "corrida.gpx")

    def test_recusa_arquivo_sem_nenhum_ponto(self):
        with self.assertRaises(imp.ArquivoDeCorridaInvalido):
            imp.leituras_de_arquivo(_gpx([]), "corrida.gpx")

    def test_recusa_arquivo_com_um_ponto_so(self):
        """Um ponto não faz percurso: sem dois não há distância nem tempo."""
        with self.assertRaises(imp.ArquivoDeCorridaInvalido):
            imp.leituras_de_arquivo(_gpx([(-23.5, -46.6, "2026-09-20T10:00:00Z")]), "corrida.gpx")

    def test_recusa_pontos_sem_horario(self):
        """Sem `<time>` não dá para pôr a leitura no tempo, e o motor da
        distância divide por segundos."""
        with self.assertRaises(imp.ArquivoDeCorridaInvalido):
            imp.leituras_de_arquivo(_gpx([(-23.5, -46.6, None), (-23.501, -46.6, None)]), "corrida.gpx")


class PipelineDeArquivoTests(SimpleTestCase):
    def test_calcula_distancia_duracao_e_parciais(self):
        """O caminho inteiro: parser → `corrida.percurso` → `corrida.parciais`.
        25 pontos a 0,001° de latitude (~111 m cada) e 60 s de intervalo dão
        ~2,67 km em 24 min, com 2 quilômetros cheios."""
        pts = [(-23.5 + i * 0.001, -46.6, f"2026-09-20T10:{i:02d}:00Z") for i in range(25)]
        dados = imp.corrida_de_arquivo(_gpx(pts), "corrida.gpx")
        self.assertGreater(dados["distancia_m"], 2600)
        self.assertLess(dados["distancia_m"], 2750)
        self.assertEqual(dados["duracao_s"], 24 * 60)
        self.assertEqual(dados["comecou_em"], datetime(2026, 9, 20, 10, 0, 0, tzinfo=tz.utc))
        self.assertEqual(dados["terminou_em"], datetime(2026, 9, 20, 10, 24, 0, tzinfo=tz.utc))
        self.assertEqual(len(dados["parciais"]), 2)

    def test_op_id_e_do_conteudo_para_reimportar_nao_duplicar(self):
        """Mesmo arquivo → mesmo `op_id`, para o `UniqueConstraint(user, op_id)`
        recusar a reimportação. Arquivo diferente → op_id diferente."""
        pts = [(-23.5 + i * 0.001, -46.6, f"2026-09-20T10:{i:02d}:00Z") for i in range(5)]
        a = imp.corrida_de_arquivo(_gpx(pts), "corrida.gpx")
        b = imp.corrida_de_arquivo(_gpx(pts), "corrida.gpx")
        self.assertEqual(a["op_id"], b["op_id"])
        outros = [(-23.6 + i * 0.001, -46.6, f"2026-09-20T11:{i:02d}:00Z") for i in range(5)]
        c = imp.corrida_de_arquivo(_gpx(outros), "corrida.gpx")
        self.assertNotEqual(a["op_id"], c["op_id"])
        self.assertLessEqual(len(a["op_id"]), 64)
