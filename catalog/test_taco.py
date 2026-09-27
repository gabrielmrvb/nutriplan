# -*- coding: utf-8 -*-
"""A TACO importada, e os trinta alimentos que ela tem de achar.

O DEFEITO QUE ISTO FECHA (achado das personas, 21/09/2026): "comi outra
coisa" comparava o nome digitado com os 102 alimentos CURADOS — os que o
motor usa para montar receita — e nada mais. Quem comeu pão de queijo, açaí,
cuscuz, mortadela ou coxinha escrevia o nome, não casava com nada, e a
refeição entrava no histórico com ZERO caloria. O aviso dizia "não
encontramos" e a pessoa não tinha o que fazer com a informação.

A base é a TACO 4ª edição (NEPA/UNICAMP, 2011), pela cópia normalizada de
github.com/brolesi/taco (MIT, DOI 10.5281/zenodo.22145839) — fonte e versão
escritas na chave `fonte` do próprio `catalog/data/taco.json` e no docstring
de `seed_taco`.

A SABOTAGEM DESTE ARQUIVO, e ela é a prova de que ele mede o que diz medir:
tire as linhas de banana de `catalog/data/taco.json` e
`test_os_trinta_alimentos_mais_comuns_sao_achados` fica VERMELHO. É por isso
que a turma dos trinta roda com a TACO SOZINHA (`seed_taco` sem
`seed_catalog`): o catálogo curado tem "Banana prata", e com ele no banco a
busca acharia banana de qualquer jeito — o teste passaria sem a tabela e
estaria medindo o catálogo antigo.
"""
import json

from django.core.management import call_command
from django.test import TestCase

from catalog import busca
from catalog.models import Food, FoodSource
from catalog.management.commands.seed_taco import ARQUIVO

#: O QUE UMA PESSOA DIGITA, e não o que a tabela publica.
#:
#: Trinta termos, em minúscula e SEM acento, porque é assim que se digita no
#: teclado do celular — o acento é a primeira coisa que ninguém põe. A lista é
#: o prato brasileiro de todo dia (arroz, feijão, ovo, frango, carne, pão,
#: café, leite), as frutas e legumes mais comprados, e o que a pessoa come
#: FORA do plano, que é justamente o caso desta tela: linguiça, mortadela,
#: coxinha, biscoito, refrigerante, cerveja.
TRINTA = [
    "arroz", "feijao", "ovo", "frango", "carne", "pao", "queijo", "leite",
    "cafe", "acucar", "manteiga", "azeite", "macarrao", "batata", "farinha",
    "tapioca", "banana", "maca", "laranja", "mamao", "tomate", "cebola",
    "cenoura", "couve", "abobora", "linguica", "mortadela", "biscoito",
    "refrigerante", "cerveja",
]


class ATacoEntraNoCatalogoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_taco", verbosity=0)

    def test_o_seed_traz_a_tabela_inteira(self):
        """Quantos alimentos a importação grava, e que eles são da TACO."""
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        esperados = len(dados["alimentos"])
        self.assertGreater(esperados, 500, "a tabela encolheu — confira o JSON")
        self.assertEqual(
            Food.objects.filter(source=FoodSource.TACO).count(), esperados
        )

    def test_a_fonte_e_a_versao_estao_escritas_no_arquivo(self):
        """Tabela nutricional sem procedência é número solto.

        Quem for conferir um valor precisa saber de que edição ele veio, e
        quem for redistribuir precisa saber a licença da cópia.
        """
        fonte = json.loads(ARQUIVO.read_text(encoding="utf-8"))["fonte"]
        self.assertIn("TACO", fonte["tabela"])
        self.assertIn("4", fonte["edicao"])
        self.assertIn("UNICAMP", fonte["instituicao"])
        self.assertIn("brolesi/taco", fonte["copia"])
        self.assertTrue(fonte["doi_da_copia"])

    def test_os_trinta_alimentos_mais_comuns_sao_achados(self):
        """A régua do item 3: os trinta têm de ser ACHADOS, sem acento.

        Sabotagem: apague as linhas de banana do `taco.json` e este teste cai.
        """
        for termo in TRINTA:
            with self.subTest(termo=termo):
                achados = list(busca.sugerir(termo))
                self.assertTrue(
                    achados,
                    '"%s" não foi achado na TACO — a tela diria "não '
                    "encontramos\" e a refeição entraria sem caloria" % termo,
                )

    def test_nenhum_alimento_importado_entra_sem_energia(self):
        """Zero caloria num alimento que tem caloria é pior que não tê-lo.

        A geração descarta a linha sem energia publicada e a linha cuja energia
        não fecha com os macros — a razão está na chave `fonte`. Aqui se mede o
        resultado: nada de kcal zero com macro, nem macro zero com kcal.

        A BEBIDA ALCOÓLICA É A EXCEÇÃO, e é a mesma da geração: o etanol
        carrega 7 kcal/g e não é macro nenhum, então "Cana, aguardente" tem
        energia publicada com os três macros em zero. O número está certo; o
        que não vale ali é a régua.
        """
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        alcoolicas = {
            a["nome"]
            for a in dados["alimentos"]
            if a["categoria"].startswith("Bebidas")
        }
        self.assertTrue(alcoolicas, "a categoria de bebidas sumiu do JSON")
        for food in Food.objects.filter(source=FoodSource.TACO):
            if food.name in alcoolicas:
                continue
            with self.subTest(nome=food.name):
                macros = food.protein_g + food.carb_g + food.fat_g
                if food.kcal == 0:
                    self.assertEqual(macros, 0, food.name)
                else:
                    self.assertGreater(macros, 0, food.name)

    def test_a_coluna_de_busca_nao_diverge_do_nome(self):
        """`busca` é escrita por três caminhos (seed, seed e migration) e lida
        por um. Divergir é a busca deixar de achar sem ninguém ver."""
        for nome, chave in Food.objects.values_list("name", "busca"):
            with self.subTest(nome=nome):
                self.assertEqual(chave, busca.normalizar(nome))


class OCuradoGanhaDoImportadoTests(TestCase):
    """Os dois seeds no banco, na ordem do build."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_taco", verbosity=0)

    def test_nome_repetido_fica_com_o_catalogo_curado(self):
        """Os 102 curados têm porção, corredor de mercado e papel no prato — o
        cardápio e a lista de compras leem isso. A linha crua da tabela não
        pode tomar o lugar deles."""
        repetidos = (
            Food.objects.filter(source=FoodSource.TACO)
            .values_list("name", flat=True)
            .distinct()
        )
        curados = set(
            Food.objects.exclude(source=FoodSource.TACO).values_list("name", flat=True)
        )
        self.assertFalse(curados & set(repetidos))

    def test_o_seed_do_catalogo_nao_aposenta_a_taco(self):
        """`seed_catalog` aposenta o que não está no `foods.json` — e a TACO
        nunca está. Sem a exceção, todo deploy desativaria os 583 alimentos
        logo depois de o outro seed os ativar."""
        call_command("seed_catalog", verbosity=0)
        self.assertEqual(
            Food.objects.filter(source=FoodSource.TACO, is_active=False).count(), 0
        )

    def test_os_trinta_continuam_achados_com_os_dois_seeds(self):
        """O estado real de produção. O teste da turma dos trinta lá em cima
        roda com a TACO sozinha porque é a sabotagem que precisa disso; este
        mede o que a pessoa vê."""
        for termo in TRINTA:
            with self.subTest(termo=termo):
                self.assertTrue(list(busca.sugerir(termo)), termo)
