# -*- coding: utf-8 -*-
"""O gunicorn atende com THREADS (decisão do dono, 21/09/2026).

O k6 mediu o free com dois workers síncronos: teto de 5 usuários simultâneos,
p95 @10 de 1,5–3,7 s, 16 % de erro a 25 — cada pedido que esperava o Neon
segurava um worker inteiro. `gthread` deixa um worker atender `WEB_THREADS`
pedidos enquanto os outros esperam I/O. Os dois serviços (produção e staging)
sobem com o MESMO comando — o staging é onde se mede — e a variável está
declarada nos dois, para o painel não divergir do arquivo.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RENDER = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")


class OGunicornAtendeComThreadsTests(SimpleTestCase):
    def test_os_dois_servicos_sobem_com_gthread_e_threads_da_variavel(self):
        comandos = re.findall(r'startCommand:\s*"([^"]+)"', RENDER)
        self.assertEqual(len(comandos), 2, "produção e staging")
        for comando in comandos:
            with self.subTest(comando=comando):
                self.assertIn("--worker-class gthread", comando)
                self.assertIn("--threads ${WEB_THREADS:-2}", comando)
                self.assertIn("--workers ${WEB_CONCURRENCY:-2}", comando, "dois workers continuam sendo o teto de memória do free")

    def test_a_variavel_esta_declarada_nos_dois_servicos(self):
        self.assertEqual(len(re.findall(r"- key: WEB_THREADS\s*\n\s*value: \"2\"", RENDER)), 2, "2, medido: 4 piora o /demo/hoje já a 5 usuários")
