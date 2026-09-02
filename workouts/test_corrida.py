"""A matemática da corrida, com coordenadas conhecidas.

Testar isto com um telefone na rua seria testar o GPS, não o código. As
distâncias abaixo saem de pontos escolhidos: um grau de latitude são cerca de
111,3 km em qualquer lugar do planeta, e é essa constante que dá uma referência
INDEPENDENTE da função sob teste.
"""
from django.test import SimpleTestCase

from workouts import corrida


class DistanciaTests(SimpleTestCase):
    """Haversine contra uma referência que não vem da própria função."""

    def test_um_grau_de_latitude_sao_cerca_de_111_km(self):
        """A referência é geográfica, e não calculada por `distancia_m`: um
        teste que chama a função para produzir o esperado não prova nada."""
        metros = corrida.distancia_m((0.0, 0.0), (1.0, 0.0))

        self.assertAlmostEqual(metros, 111_195, delta=200)

    def test_um_grau_de_longitude_encolhe_perto_do_polo(self):
        """No equador um grau de longitude é ~111 km; a 60° de latitude é
        metade disso, porque o paralelo é menor. Se a função tratasse a Terra
        como um plano, os dois dariam igual."""
        equador = corrida.distancia_m((0.0, 0.0), (0.0, 1.0))
        norte = corrida.distancia_m((60.0, 0.0), (60.0, 1.0))

        self.assertAlmostEqual(norte / equador, 0.5, delta=0.01)

    def test_o_mesmo_ponto_da_zero(self):
        self.assertEqual(corrida.distancia_m((-23.55, -46.63), (-23.55, -46.63)), 0.0)

    def test_a_distancia_nao_depende_da_ordem(self):
        a, b = (-23.5505, -46.6333), (-23.5605, -46.6433)

        self.assertAlmostEqual(
            corrida.distancia_m(a, b), corrida.distancia_m(b, a), places=6
        )


def _linha(quantos, passo_graus=0.00003, intervalo=1, accuracy=5.0, inicio_t=0):
    """Leituras em linha reta ao norte, a ritmo de corrida.

    0,00003° ≈ 3,3 m, e a uma leitura por segundo isso são 3,3 m/s — cinco
    minutos por quilômetro. A primeira versão usava 0,0001° por segundo, que
    são 11 m/s: os dados de teste "corriam" a 40 km/h e o filtro de teleporte
    recusava tudo, com razão.
    """
    return [
        {
            "lat": -23.55 + n * passo_graus,
            "lon": -46.63,
            "t": inicio_t + n * intervalo,
            "accuracy": accuracy,
        }
        for n in range(quantos)
    ]


class PercursoTests(SimpleTestCase):
    """O que entra na distância e o que é descartado."""

    def test_soma_os_trechos_de_uma_linha_reta(self):
        leituras = _linha(11)  # 10 trechos de ~3,3 m

        resultado = corrida.percurso(leituras)

        self.assertAlmostEqual(resultado["distancia_m"], 33.4, delta=1.0)
        self.assertEqual(resultado["descartadas"], 0)

    def test_leitura_imprecisa_e_descartada(self):
        """Prédio e túnel fazem a posição andar sem ninguém andar."""
        leituras = _linha(5)
        leituras[2]["accuracy"] = 80.0
        leituras[2]["lat"] += 0.005  # ~555 m de salto

        resultado = corrida.percurso(leituras)

        self.assertEqual(resultado["descartadas"], 1)
        self.assertAlmostEqual(resultado["distancia_m"], 13.4, delta=1.0)

    def test_teleporte_e_descartado_mesmo_com_precisao_boa(self):
        """O telefone reencontra o sinal e "pula". A linha reta entre os dois
        pontos é distância que ninguém percorreu — e a `accuracy` reportada
        pode estar ótima."""
        leituras = _linha(4)
        leituras[2]["lat"] += 0.5  # ~55 km em 1 segundo

        resultado = corrida.percurso(leituras)

        self.assertEqual(resultado["descartadas"], 1)
        self.assertLess(resultado["distancia_m"], 50)

    def test_parado_no_sinal_nao_vira_distancia(self):
        """Dez minutos esperando, com o GPS oscilando meio metro, não podem
        virar trezentos metros."""
        leituras = [
            {"lat": -23.55 + (n % 2) * 0.000005, "lon": -46.63, "t": n, "accuracy": 5.0}
            for n in range(600)
        ]

        resultado = corrida.percurso(leituras)

        self.assertEqual(resultado["distancia_m"], 0.0)

    def test_uma_leitura_ruim_no_meio_nao_parte_a_corrida(self):
        """Descartar o ponto e continuar da última leitura BOA: sem isso, um
        ponto ruim no meio de um trecho reto perderia o trecho inteiro."""
        leituras = _linha(11)
        leituras[5]["accuracy"] = 200.0

        resultado = corrida.percurso(leituras)

        self.assertEqual(resultado["descartadas"], 1)
        self.assertAlmostEqual(resultado["distancia_m"], 33.4, delta=1.0)

    def test_a_primeira_leitura_tambem_passa_pelo_filtro(self):
        """Começar com a posição errada desloca o traçado inteiro."""
        leituras = _linha(5)
        leituras[0]["accuracy"] = 300.0

        resultado = corrida.percurso(leituras)

        self.assertEqual(resultado["descartadas"], 1)
        self.assertAlmostEqual(resultado["distancia_m"], 10.0, delta=1.0)

    def test_o_limite_de_precisao_e_parametro(self):
        """Ele é palpite até alguém medir a `accuracy` da rua. Palpite enterrado
        na função é palpite que ninguém revisa."""
        leituras = _linha(5, accuracy=50.0)

        apertado = corrida.percurso(leituras)
        frouxo = corrida.percurso(leituras, precisao_maxima=100.0)

        self.assertEqual(apertado["distancia_m"], 0.0)
        self.assertGreater(frouxo["distancia_m"], 10)


class PaceTests(SimpleTestCase):
    def test_dez_km_em_cinquenta_minutos_da_cinco_por_km(self):
        self.assertEqual(corrida.pace_por_km(10_000, 3000), 300.0)

    def test_sem_distancia_nao_ha_pace(self):
        self.assertIsNone(corrida.pace_por_km(0, 600))

    def test_sem_tempo_nao_ha_pace(self):
        self.assertIsNone(corrida.pace_por_km(1000, 0))

    def test_devolve_numero_e_nao_texto(self):
        """Número que nasce string não soma, não compara e não vira média."""
        self.assertIsInstance(corrida.pace_por_km(1000, 300), float)


class ParciaisTests(SimpleTestCase):
    """O quilômetro cheio cai entre duas leituras."""

    def _pontos(self, metros_por_segundo, segundos):
        return [
            {"t": t, "acumulado_m": t * metros_por_segundo, "lat": 0, "lon": 0}
            for t in range(segundos + 1)
        ]

    def test_ritmo_constante_da_parciais_iguais(self):
        pontos = self._pontos(5.0, 600)  # 5 m/s = 3min20/km, 3 km em 600 s

        marcas = corrida.parciais(pontos)

        self.assertEqual([m["km"] for m in marcas], [1, 2, 3])
        for marca in marcas:
            self.assertAlmostEqual(marca["segundos"], 200.0, delta=0.5)

    def test_o_instante_do_km_e_interpolado(self):
        """Atribuir ao ponto seguinte empurraria cada parcial para frente, e o
        erro se acumula: numa corrida de dez quilômetros, dez vezes."""
        pontos = [
            {"t": 0, "acumulado_m": 0, "lat": 0, "lon": 0},
            {"t": 100, "acumulado_m": 800, "lat": 0, "lon": 0},
            {"t": 200, "acumulado_m": 1600, "lat": 0, "lon": 0},
        ]

        marcas = corrida.parciais(pontos)

        # O km cai a 25% do caminho entre 800 m e 1600 m -> t = 125.
        self.assertEqual(len(marcas), 1)
        self.assertAlmostEqual(marcas[0]["segundos"], 125.0, delta=0.5)

    def test_o_trecho_final_incompleto_nao_vira_parcial(self):
        """"800 m em 4min" ao lado de parciais de 1 km convida a comparar pace
        de coisas de tamanho diferente."""
        pontos = self._pontos(5.0, 360)  # 1,8 km

        marcas = corrida.parciais(pontos)

        self.assertEqual(len(marcas), 1)

    def test_corrida_curta_demais_nao_tem_parcial(self):
        self.assertEqual(corrida.parciais(self._pontos(5.0, 100)), [])

    def test_sem_pontos_nao_quebra(self):
        self.assertEqual(corrida.parciais([]), [])
        self.assertEqual(corrida.parciais([{"t": 0, "acumulado_m": 0}]), [])


class CaminhadaLentaTests(SimpleTestCase):
    """O piso de deslocamento não pode zerar quem anda devagar.

    Com leitura a cada segundo e 1,2 m/s, TODO deslocamento fica abaixo do
    piso de ruído. Ingenuamente isso zeraria a distância de quem caminha — e
    caminhar é o começo de quem está voltando a correr.

    O que salva é a âncora não avançar quando a leitura é recusada: a próxima
    é comparada com o último ponto BOM, e passa. Era uma propriedade que eu
    tinha suposto sem provar.
    """

    def _caminhada(self, metros_por_segundo, segundos):
        # 1 m ≈ 0,000009° de latitude.
        grau_por_metro = 1 / 111_195
        return [
            {
                "lat": -23.55 + t * metros_por_segundo * grau_por_metro,
                "lon": -46.63,
                "t": t,
                "accuracy": 5.0,
            }
            for t in range(segundos + 1)
        ]

    def test_quem_anda_a_um_metro_por_segundo_acumula_distancia(self):
        leituras = self._caminhada(1.2, 60)

        resultado = corrida.percurso(leituras)

        self.assertAlmostEqual(resultado["distancia_m"], 72, delta=4)

    def test_a_ancora_nao_avanca_quando_a_leitura_e_recusada(self):
        """A propriedade que faz a caminhada funcionar. Se a âncora avançasse,
        cada trecho curto seria perdido e a distância ficaria em zero."""
        leituras = self._caminhada(1.0, 10)

        resultado = corrida.percurso(leituras)

        self.assertGreater(resultado["distancia_m"], 8)
        self.assertLess(resultado["distancia_m"], 12)

    def test_corrida_normal_nao_descarta_nada(self):
        """Controle: a 3 m/s todo trecho passa de primeira, e o número de
        descartes precisa ser zero — senão o filtro está mordendo corrida."""
        leituras = self._caminhada(3.0, 30)

        resultado = corrida.percurso(leituras)

        self.assertEqual(resultado["descartadas"], 0)
        self.assertAlmostEqual(resultado["distancia_m"], 90, delta=3)
