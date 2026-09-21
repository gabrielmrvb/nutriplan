# -*- coding: utf-8 -*-
"""O drill mensal de restauração no Actions (21/09/2026).

`restaurar-mensal.yml` despeja produção com um role somente leitura, restaura
no Postgres 18 do job, confere contra a origem e abre issue se falhar. O que
se prende aqui, sem rede e sem Postgres:

* o fluxo roda todo mês E pelo botão, com o segredo (nunca uma URL escrita),
  o Postgres do job em versão que lê o dump do 18, os três scripts na ordem,
  `pipefail` onde há `tee`, `MANTER_BANCO=1` antes da conferência, o alerta
  com `if: failure()` e `issues: write` — e NENHUM `upload-artifact`: o dump
  tem dado de gente real e o repositório é público;
* a conferência (`scripts/conferir_restauracao.py`): tolera o drift pequeno
  de um banco vivo, reprova tabela sumida ou divergência maior, reprova
  migrações diferentes e reprova dump sem gente;
* `restaurar.sh` só mantém o banco quando `MANTER_BANCO=1` diz;
* o CLAUDE.md conta que o drill existe e onde vive o segredo.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

from scripts import conferir_restauracao as cr

RAIZ = Path(__file__).resolve().parents[1]
FLUXO = (RAIZ / ".github" / "workflows" / "restaurar-mensal.yml").read_text(encoding="utf-8")
RESTAURAR = (RAIZ / "scripts" / "restaurar.sh").read_text(encoding="utf-8")


def sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class OFluxoMensalTests(SimpleTestCase):
    def test_roda_todo_mes_e_pelo_botao(self):
        corpo = sem_comentarios(FLUXO)
        self.assertRegex(corpo, r'cron:\s*"0 9 1 \* \*"')
        self.assertIn("workflow_dispatch:", corpo)
        self.assertNotIn("push:", corpo, "um drill de produção não roda a cada commit")

    def test_a_url_vem_do_segredo_e_nunca_esta_escrita(self):
        corpo = sem_comentarios(FLUXO)
        self.assertEqual(corpo.count("${{ secrets.BACKUP_DATABASE_URL }}"), 2, "despejo e conferência")
        self.assertNotRegex(corpo, r"postgres(ql)?://\S*neon\.tech", "URL de produção escrita no fluxo")

    def test_o_postgres_do_job_le_o_dump_do_18(self):
        versao = re.search(r"image:\s*postgres:(\d+)", FLUXO)
        self.assertIsNotNone(versao)
        self.assertGreaterEqual(int(versao.group(1)), 17, "pg_dump 18 escreve SET transaction_timeout, que só existe a partir do 17")
        self.assertIn("postgresql-client-18", FLUXO)

    def test_os_tres_passos_na_ordem_e_com_as_guardas(self):
        corpo = sem_comentarios(FLUXO)
        despejo = corpo.index("scripts/backup.sh")
        restauro = corpo.index("scripts/restaurar.sh")
        conferencia = corpo.index("scripts/conferir_restauracao.py")
        self.assertLess(despejo, restauro)
        self.assertLess(restauro, conferencia)
        self.assertLess(corpo.index('MANTER_BANCO: "1"'), restauro, "sem manter o banco, a conferência não tem o que conferir")
        self.assertLess(corpo.index("set -o pipefail"), conferencia, "com tee, o código de saída seria o do tee")
        self.assertIn("$RUNNER_TEMP", corpo, "o dump mora fora do checkout e morre com o job")

    def test_alerta_por_issue_quando_falha(self):
        corpo = sem_comentarios(FLUXO)
        self.assertIn("if: failure()", corpo)
        self.assertRegex(corpo, r"issues:\s*write")
        self.assertIn("gh issue create", corpo)

    def test_o_dump_nunca_vira_artefato(self):
        self.assertNotIn("upload-artifact", FLUXO)
        self.assertNotIn("upload_artifact", FLUXO)


class AConferenciaTests(SimpleTestCase):
    ORIGEM = {"accounts_user": 74, "plans_hydrationlog": 1000, "django_session": 40, "workouts_exerciselog": 500}

    def test_o_drift_pequeno_de_um_banco_vivo_nao_e_falha(self):
        destino = dict(self.ORIGEM, plans_hydrationlog=992, workouts_exerciselog=497, django_session=1)
        divergencias, resumo = cr.comparar(self.ORIGEM, destino)
        self.assertEqual(divergencias, [])
        self.assertEqual(resumo["tabelas"], 4)

    def test_divergencia_maior_que_a_tolerancia_e_falha_nomeada(self):
        destino = dict(self.ORIGEM, plans_hydrationlog=900)
        divergencias, _ = cr.comparar(self.ORIGEM, destino)
        self.assertEqual(len(divergencias), 1)
        self.assertIn("plans_hydrationlog: origem 1000, restaurado 900", divergencias[0])

    def test_tabela_que_sumiu_e_falha(self):
        destino = {k: v for k, v in self.ORIGEM.items() if k != "workouts_exerciselog"}
        divergencias, _ = cr.comparar(self.ORIGEM, destino)
        self.assertEqual(len(divergencias), 1)
        self.assertIn("workouts_exerciselog", divergencias[0])
        self.assertIn("NÃO no restaurado", divergencias[0])

    def test_a_tolerancia_e_um_por_cento_ou_cinco_linhas(self):
        self.assertEqual(cr.tolerancia(10), 5)
        self.assertEqual(cr.tolerancia(1000), 10)

    def test_migracoes_diferentes_reprovam_mesmo_com_contagens_iguais(self):
        falhas = cr.conferir(self.ORIGEM, dict(self.ORIGEM), [("accounts", "0001"), ("accounts", "0002")], [("accounts", "0001")], usuarios=74)
        self.assertEqual(len(falhas), 1)
        self.assertIn("django_migrations difere", falhas[0])
        self.assertIn("0002", falhas[0])

    def test_dump_sem_gente_reprova(self):
        falhas = cr.conferir(self.ORIGEM, dict(self.ORIGEM), [], [], usuarios=0)
        self.assertEqual(len(falhas), 1)
        self.assertIn("accounts_user", falhas[0])

    def test_tudo_igual_confere(self):
        self.assertEqual(cr.conferir(self.ORIGEM, dict(self.ORIGEM), [("a", "1")], [("a", "1")], usuarios=74), [])

    def test_as_urls_entram_por_ambiente_e_nunca_por_argumento(self):
        with self.settings():
            import os
            from unittest import mock
            with mock.patch.dict(os.environ, {"ORIGEM_URL": "", "DESTINO_URL": ""}):
                with self.assertRaisesMessage(SystemExit, "ambiente"):
                    cr.main()
        texto = (RAIZ / "scripts" / "conferir_restauracao.py").read_text(encoding="utf-8")
        self.assertNotIn("sys.argv", texto)


class ORestaurarMantemOBancoSoQuandoPedidoTests(SimpleTestCase):
    def test_a_flag_existe_e_o_padrao_continua_apagando(self):
        corpo = sem_comentarios(RESTAURAR)
        self.assertIn('if [ "${MANTER_BANCO:-}" = "1" ]; then', corpo)
        self.assertRegex(corpo, r'else\s*\n\s*echo "Apagando o banco de teste\."\s*\n\s*psql -d "\$ALVO" -q -c "DROP DATABASE IF EXISTS \$BANCO;"')


class ODrillEstaDocumentadoTests(SimpleTestCase):
    def test_o_claude_md_conta_o_drill_e_o_segredo(self):
        texto = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
        secao = texto[texto.index("## Backup e restauração"):]
        self.assertIn("restaurar-mensal.yml", secao)
        self.assertIn("BACKUP_DATABASE_URL", secao)
        self.assertIn("nutriplan_leitor", secao)
