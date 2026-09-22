# -*- coding: utf-8 -*-
"""Os legais publicados com ACEITE e as DUAS caixas de consentimento
(decisão do dono, 21/09/2026).

O que a LGPD pede, e onde cada pedido vira tela:

- dado de saúde só com consentimento "específico e destacado" (art. 11, I):
  a caixa `saude`, sozinha, com o texto dizendo o que é tratado e para quê;
- transferência internacional com consentimento "específico e em destaque
  … com informação prévia sobre o caráter internacional" (art. 33, VIII): a
  caixa `transferencia`, dizendo Estados Unidos, Render e Neon;
- "cláusula destacada das demais cláusulas contratuais" (art. 8º, § 1º): as
  duas caixas NÃO são o "li e aceito os Termos" — são três controles;
- "o titular será informado com destaque" quando o tratamento é condição do
  serviço (art. 9º, § 3º): "Sem isso o app não funciona" em cada caixa;
- ônus da prova do controlador (art. 8º, § 2º): `Consentimento` guarda
  quem, o quê, qual VERSÃO do texto e quando.

E o momento: as caixas moram na ETAPA 1 do cadastro, que é onde o dado de
saúde é pedido — e por onde TODO mundo passa, inclusive quem entra pelo
Google e nunca vê o formulário de e-mail e senha. O aceite dos Termos fica no
formulário de criar conta (caminho do e-mail) e, para quem veio pelo Google,
na mesma etapa 1. Quem já tinha conta antes disto passa UMA vez por
`/conta/consentimento/` antes de qualquer tela do app — menos "Excluir minha
conta", que continua aberta: ninguém precisa consentir para ir embora.
"""
from datetime import date

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts import consentimento
from accounts.models import ONBOARDING_DONE, Consentimento, Profile, User
from accounts.test_tres_etapas import ETAPA1_SEM_CAIXAS as ETAPA1, ETAPA2, ETAPA3, etapa

CAIXAS = {"saude": "on", "transferencia": "on"}
TRES = {**CAIXAS, "termos": "on"}
CONTA = {"email": "nova@exemplo.com", "first_name": "Nova", "password1": "senha-bem-forte-123", "password2": "senha-bem-forte-123"}


def sem_scripts(html):
    import re

    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S)


class ConsentimentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="c@exemplo.com"):
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        return user

    # -- o formulário de criar conta (caminho do e-mail) ------------------

    def test_criar_conta_exige_o_aceite_dos_termos(self):
        resposta = self.client.post(reverse("accounts:signup"), CONTA)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(User.objects.filter(email="nova@exemplo.com").exists())
        self.assertContains(resposta, "Termos de Uso")

    def test_criar_conta_com_o_aceite_grava_o_consentimento_dos_termos(self):
        self.client.post(reverse("accounts:signup"), {**CONTA, "termos": "on"})
        user = User.objects.get(email="nova@exemplo.com")
        registro = Consentimento.objects.get(user=user, tipo=Consentimento.Tipo.TERMOS)
        self.assertEqual(registro.versao, consentimento.VERSAO_DOS_LEGAIS)

    def test_a_tela_de_criar_conta_mostra_a_caixa_dos_termos_com_os_links(self):
        html = sem_scripts(self.client.get(reverse("accounts:signup")).content.decode())
        self.assertIn('name="termos"', html)
        self.assertIn(reverse("termos"), html)
        self.assertIn(reverse("privacidade"), html)

    # -- a etapa 1: onde o dado de saúde é pedido --------------------------

    def test_a_etapa_1_mostra_as_duas_caixas_desmarcadas_e_separadas(self):
        self.pessoa()
        html = sem_scripts(self.client.get(etapa(1)).content.decode())
        self.assertIn('name="saude"', html)
        self.assertIn('name="transferencia"', html)
        self.assertNotRegex(html, r'name="saude"[^>]*\bchecked\b')
        self.assertNotRegex(html, r'name="transferencia"[^>]*\bchecked\b')
        self.assertIn("Sem isso o app não funciona", html)
        self.assertIn("Estados Unidos", html)

    def test_quem_veio_pelo_google_ve_tambem_a_caixa_dos_termos_na_etapa_1(self):
        """Sem passar pelo formulário de e-mail, o aceite dos Termos ainda não
        existe — e é aqui que ele é pedido."""
        self.pessoa()
        html = sem_scripts(self.client.get(etapa(1)).content.decode())
        self.assertIn('name="termos"', html)

    def test_quem_ja_aceitou_os_termos_no_cadastro_nao_os_ve_de_novo(self):
        user = self.pessoa()
        consentimento.registrar(user, [Consentimento.Tipo.TERMOS])
        html = sem_scripts(self.client.get(etapa(1)).content.decode())
        self.assertNotIn('name="termos"', html)
        self.assertIn('name="saude"', html)

    def test_a_etapa_1_nao_avanca_sem_as_caixas(self):
        user = self.pessoa()
        resposta = self.client.post(etapa(1), ETAPA1)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "marque")
        self.assertFalse(Profile.objects.filter(user=user).exists(), "sem consentimento não se grava dado de saúde")
        self.assertFalse(Consentimento.objects.filter(user=user).exists())

    def test_a_etapa_1_com_uma_caixa_so_tambem_nao_avanca(self):
        user = self.pessoa()
        resposta = self.client.post(etapa(1), {**ETAPA1, "saude": "on", "termos": "on"})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Profile.objects.filter(user=user).exists())

    def test_a_etapa_1_com_as_caixas_grava_o_perfil_e_os_tres_registros(self):
        user = self.pessoa()
        resposta = self.client.post(etapa(1), {**ETAPA1, **TRES})
        self.assertRedirects(resposta, etapa(2))
        tipos = set(Consentimento.objects.filter(user=user).values_list("tipo", flat=True))
        self.assertEqual(tipos, {"termos", "saude", "transferencia"})
        perfil = Profile.objects.get(user=user)
        self.assertEqual(perfil.consentimento_versao, consentimento.VERSAO_DOS_LEGAIS)
        self.assertEqual(consentimento.faltam(perfil), set())

    def test_voltar_a_etapa_1_depois_de_consentir_nao_pede_de_novo(self):
        user = self.pessoa()
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        html = sem_scripts(self.client.get(etapa(1)).content.decode())
        self.assertNotIn('name="saude"', html)
        # e o POST sem caixas continua valendo, porque o consentimento já existe
        resposta = self.client.post(etapa(1), ETAPA1)
        self.assertRedirects(resposta, etapa(2))

    def test_a_edicao_do_perfil_pela_etapa_1_nao_mostra_as_caixas(self):
        user = self.pessoa()
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        html = sem_scripts(self.client.get(etapa(1)).content.decode())
        self.assertNotIn('name="saude"', html)

    def test_a_edicao_por_quem_nunca_consentiu_e_nao_foi_marcado_tambem_nao_pede(self):
        """O perfil de fixture (criado direto, sem cadastro) edita a etapa 1 pelo
        Perfil sem caixa nenhuma: a guarda das contas antigas é a marca da
        migration, e a etapa 1 em EDIÇÃO nunca é o lugar de consentir — três
        classes de `accounts.tests` postavam o payload cru e reprovavam."""
        user = self.pessoa()
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        Consentimento.objects.filter(user=user).delete()
        Profile.objects.filter(user=user).update(consentimento_versao="")
        html = sem_scripts(self.client.get(etapa(1)).content.decode())
        self.assertNotIn('name="saude"', html)
        resposta = self.client.post(etapa(1), {**ETAPA1, "height_cm": 181})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Profile.objects.get(user=user).height_cm, 181)

    # -- quem já tinha conta antes ------------------------------------------

    def _completa_sem_consentimento(self, email="antiga@exemplo.com"):
        user = self.pessoa(email)
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        # o que a migration 0038 faz com toda conta que existia no deploy
        Consentimento.objects.filter(user=user).delete()
        Profile.objects.filter(user=user).update(consentimento_versao="", precisa_consentir=True)
        return user

    def test_conta_antiga_e_levada_ao_consentimento_antes_de_qualquer_tela(self):
        self._completa_sem_consentimento()
        for rota in (reverse("plans:today"), reverse("workouts:routine"), reverse("accounts:profile")):
            with self.subTest(rota=rota):
                self.assertRedirects(self.client.get(rota), reverse("accounts:consentimento"), fetch_redirect_response=False)

    def test_a_tela_de_consentimento_grava_e_devolve_para_o_dia(self):
        user = self._completa_sem_consentimento()
        html = sem_scripts(self.client.get(reverse("accounts:consentimento")).content.decode())
        self.assertIn('name="saude"', html)
        self.assertIn('name="termos"', html)
        resposta = self.client.post(reverse("accounts:consentimento"), TRES)
        self.assertRedirects(resposta, reverse("plans:today"), fetch_redirect_response=False)
        self.assertEqual(Consentimento.objects.filter(user=user).count(), 3)
        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)

    def test_a_tela_de_consentimento_sem_as_caixas_nao_libera(self):
        self._completa_sem_consentimento()
        resposta = self.client.post(reverse("accounts:consentimento"), {"termos": "on"})
        self.assertEqual(resposta.status_code, 200)
        self.assertRedirects(self.client.get(reverse("plans:today")), reverse("accounts:consentimento"), fetch_redirect_response=False)

    def test_excluir_a_conta_nao_exige_consentimento(self):
        """Ninguém precisa consentir para ir embora."""
        self._completa_sem_consentimento()
        self.assertEqual(self.client.get(reverse("accounts:excluir_conta")).status_code, 200)

    def test_uma_versao_nova_dos_legais_pede_o_consentimento_de_novo(self):
        user = self.pessoa("versao@exemplo.com")
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        Consentimento.objects.filter(user=user).update(versao="2020-01-01")
        Profile.objects.filter(user=user).update(consentimento_versao="2020-01-01")
        perfil = Profile.objects.get(user=user)
        self.assertTrue(consentimento.deve_consentir(perfil))
        self.assertEqual(consentimento.faltam(perfil), {"termos", "saude", "transferencia"})

    def test_perfil_de_fixture_sem_versao_nem_marca_nao_e_barrado(self):
        """Fixtures e seeds criam o perfil direto, sem cadastro: não consentiram
        nada e NÃO são a conta antiga da migration — a guarda os deixa em paz.
        Em produção esse estado não existe: toda conta nova passa pela etapa 1."""
        self.assertFalse(consentimento.deve_consentir(Profile(consentimento_versao="", precisa_consentir=False)))
        self.assertTrue(consentimento.deve_consentir(Profile(consentimento_versao="", precisa_consentir=True)))
        self.assertFalse(consentimento.deve_consentir(Profile(consentimento_versao=consentimento.VERSAO_DOS_LEGAIS)))
        self.assertTrue(consentimento.deve_consentir(Profile(consentimento_versao="2020-01-01")))

    def test_o_registro_diz_quando_e_qual_versao(self):
        user = self.pessoa("prova@exemplo.com")
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        registro = Consentimento.objects.get(user=user, tipo="saude")
        self.assertEqual(registro.versao, consentimento.VERSAO_DOS_LEGAIS)
        self.assertIsNotNone(registro.dado_em)
        # a versão é a data do texto, no formato ISO — o mesmo que os legais mostram
        date.fromisoformat(consentimento.VERSAO_DOS_LEGAIS)


class IdadeMinimaTests(TestCase):
    """18 anos, como os Termos e a Política já diziam (o código aceitava 14)."""

    def setUp(self):
        self.client.force_login(User.objects.create_user(email="idade@exemplo.com", password="senha-bem-forte-123"))

    def test_dezessete_anos_e_recusado(self):
        hoje = date(2026, 9, 16)
        dezessete = hoje.replace(year=hoje.year - 17)
        resposta = self.client.post(etapa(1), {**ETAPA1, **TRES, "birth_date": dezessete.isoformat()})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "18 anos")
        self.assertFalse(Profile.objects.exists())

    def test_dezoito_anos_e_aceito(self):
        hoje = date(2026, 9, 16)
        dezoito = hoje.replace(year=hoje.year - 18)
        resposta = self.client.post(etapa(1), {**ETAPA1, **TRES, "birth_date": dezoito.isoformat()})
        self.assertRedirects(resposta, etapa(2))


@override_settings(LEGAL_PUBLICADO=True, LEGAL_RESPONSAVEL="Fulana de Tal", LEGAL_CONTATO="contato@exemplo.com")
class LegaisPublicadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_os_links_ficam_no_rodape_de_toda_tela(self):
        user = User.objects.create_user(email="rodape@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(user)
        self.client.post(etapa(1), {**ETAPA1, **TRES})
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        for rota in (reverse("plans:today"), reverse("workouts:routine"), reverse("plans:history"), reverse("accounts:profile")):
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertIn('href="%s"' % reverse("termos"), html)
                self.assertIn('href="%s"' % reverse("privacidade"), html)
                self.assertEqual(html.count('class="links-legais"'), 1, "uma vez por tela, não duas")
        # as telas de entrada já os tinham no próprio cartão; continuam com um só
        from django.test import Client

        anonimo = Client()
        for rota in (reverse("accounts:login"), reverse("accounts:signup")):
            with self.subTest(rota=rota):
                html = anonimo.get(rota).content.decode()
                self.assertEqual(html.count('class="links-legais"'), 1)

    def test_a_politica_diz_a_base_legal_a_transferencia_e_a_anpd(self):
        texto = self.client.get(reverse("privacidade")).content.decode()
        for trecho in ("consentimento", "transferência internacional", "Estados Unidos", "ANPD", "Fulana de Tal", "contato@exemplo.com"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, texto)
        self.assertNotIn("rascunho", texto)


class MigracaoDosConsentimentosTests(TransactionTestCase):
    """`0038` marca `precisa_consentir` em toda conta que existia com o cadastro
    TERMINADO — e só nela: quem estava no meio ainda passa pela etapa 1, e as
    contas do demo e de QA (`@nutriplan.invalid`) não são gente."""

    ANTES = ("accounts", "0037_profile_rastrear_uso")
    DEPOIS = ("accounts", "0038_consentimento")

    def _apps_em(self, alvo):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([alvo])
        return executor.loader.project_state([alvo]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_quem_ja_existia_com_cadastro_terminado_e_marcado(self):
        apps = self._apps_em(self.ANTES)
        User = apps.get_model("accounts", "User")
        Profile = apps.get_model("accounts", "Profile")
        for email, passo in (("antiga@exemplo.com", 7), ("no-meio@exemplo.com", 2), ("carlos.demo@nutriplan.invalid", 7)):
            user = User.objects.create(email=email, password="x")
            Profile.objects.create(user=user, sex="M", birth_date=date(1995, 4, 12), height_cm=178, onboarding_step=passo)
        apps = self._apps_em(self.DEPOIS)
        Profile = apps.get_model("accounts", "Profile")
        marcados = {p.user.email: p.precisa_consentir for p in Profile.objects.select_related("user")}
        self.assertEqual(marcados, {"antiga@exemplo.com": True, "no-meio@exemplo.com": False, "carlos.demo@nutriplan.invalid": False})
        self.assertEqual(set(Profile.objects.values_list("consentimento_versao", flat=True)), {""})
