# -*- coding: utf-8 -*-
"""As três perguntas de produto que o painel passou a responder (24/09/2026).

O app já tinha evento bruto, taxonomia fechada, alias no login e poda de 90
dias. O que faltava era responder, sem serviço externo:

1. **Onde a pessoa desiste** — o funil de entrada, da landing à primeira
   série, por coorte de dia e de semana, com a taxa entre cada passo.
2. **A pessoa volta?** — coortes por semana de cadastro com D1, D7 e D30.
3. **O que a base usa de fato** — registros e pessoas por área, por semana.

Dois eventos que a taxonomia declarava e ninguém disparava entraram junto
(`treino.serie_concluida`, `treino.concluido`), e um nasceu
(`site.landing_vista`): sem eles o funil não tinha topo nem fim, e o uso por
área enxergava tudo menos o treino.
"""
from datetime import timedelta

from django.conf import settings
from django.test import TestCase

from accounts.models import Pilar
from django.urls import reverse
from django.utils import timezone

from analytics import consultas
from analytics.models import Event


def _evento(nome, pessoa, quando, **props):
    """Um evento de uma pessoa anônima num instante exato.

    `anon_id` e não `user`: a chave de pessoa das consultas é
    `Coalesce(user_id, anon_id)`, e usar o anônimo dispensa criar conta para
    medir uma matriz — o que este arquivo testa é a CONTA, não o cadastro.
    """
    evento = Event.objects.create(name=nome, anon_id=pessoa, props=props)
    Event.objects.filter(pk=evento.pk).update(ts=quando)
    return evento


class OFunilDeEntradaTests(TestCase):
    def setUp(self):
        self.agora = timezone.now()
        self.ontem = self.agora - timedelta(days=1)

    def _caminho(self, pessoa, ate, inicio):
        """A pessoa percorre os passos até `ate`, um minuto por passo."""
        for n, (chave, _r, nome, props) in enumerate(consultas.PASSOS_DE_ENTRADA):
            _evento(nome, pessoa, inicio + timedelta(minutes=n), **{
                k.replace("props__", ""): v for k, v in props.items()
            })
            if chave == ate:
                return

    def test_cada_passo_conta_quem_chegou_e_a_taxa_do_anterior(self):
        for n in range(4):
            self._caminho("p%d" % n, "cadastro", self.ontem)
        self._caminho("p9", "serie", self.ontem)
        _coortes, total = consultas.funil_de_entrada(dias=7)
        por_chave = {e["chave"]: e for e in total["etapas"]}
        self.assertEqual(por_chave["landing"]["pessoas"], 5)
        self.assertEqual(por_chave["cadastro"]["pessoas"], 5)
        self.assertEqual(por_chave["etapa1"]["pessoas"], 1)
        self.assertEqual(por_chave["serie"]["pessoas"], 1)
        # 1 de 5 passou do cadastro para a etapa 1.
        self.assertEqual(por_chave["etapa1"]["pct_do_anterior"], 20)
        self.assertEqual(por_chave["etapa1"]["pct_do_topo"], 20)

    def test_a_ordem_no_tempo_manda(self):
        """Quem registrou uma série ANTES de começar o cadastro não converteu
        o cadastro: é outra pessoa no mesmo aparelho, ou dado sujo."""
        _evento("treino.serie_concluida", "fora_de_ordem", self.ontem)
        _evento("site.landing_vista", "fora_de_ordem", self.agora)
        _coortes, total = consultas.funil_de_entrada(dias=7)
        por_chave = {e["chave"]: e for e in total["etapas"]}
        self.assertEqual(por_chave["landing"]["pessoas"], 1)
        self.assertEqual(por_chave["serie"]["pessoas"], 0)

    def test_a_coorte_e_do_primeiro_passo_e_nao_do_dia_do_evento(self):
        """Quem abriu a landing ontem e treinou hoje pertence a ONTEM: contar
        a série de hoje como conversão de hoje faria a taxa de um dia depender
        do movimento do dia anterior."""
        self._caminho("lenta", "landing", self.ontem)
        for n, (_c, _r, nome, props) in enumerate(consultas.PASSOS_DE_ENTRADA[1:]):
            _evento(nome, "lenta", self.agora + timedelta(minutes=n), **{
                k.replace("props__", ""): v for k, v in props.items()
            })
        coortes, _total = consultas.funil_de_entrada(dias=7)
        self.assertEqual(len(coortes), 1)
        self.assertEqual(coortes[0]["quando"], timezone.localtime(self.ontem).date())
        self.assertEqual(coortes[0]["etapas"][-1]["pessoas"], 1)

    def test_por_semana_junta_as_coortes_do_dia(self):
        self._caminho("a", "cadastro", self.agora)
        self._caminho("b", "cadastro", self.agora - timedelta(days=2))
        por_dia, _ = consultas.funil_de_entrada(dias=30, por="dia")
        por_semana, _ = consultas.funil_de_entrada(dias=30, por="semana")
        self.assertEqual(len(por_dia), 2)
        self.assertLessEqual(len(por_semana), len(por_dia))

    def test_quem_entrou_direto_pelo_cadastro_nao_some_do_funil(self):
        """Link de cadastro compartilhado: a pessoa nunca viu a landing, e
        ficar de fora do funil faria a base parecer menor do que é."""
        _evento("onboarding.iniciado", "direto", self.agora)
        coortes, total = consultas.funil_de_entrada(dias=7)
        self.assertEqual(len(coortes), 1)
        self.assertEqual(total["etapas"][0]["pessoas"], 0)
        self.assertEqual(
            {e["chave"]: e["pessoas"] for e in total["etapas"]}["cadastro"], 0,
            "sem o passo de cima, o de baixo não tem de quem converter",
        )

    def test_sem_evento_nenhum_a_tela_nao_quebra(self):
        coortes, total = consultas.funil_de_entrada(dias=7)
        self.assertEqual(coortes, [])
        self.assertEqual(total["base"], 0)


class ARetencaoPorCoorteTests(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()

    def _conta(self, pessoa, nasceu, volta_em=()):
        inicio = timezone.now() - timedelta(days=(self.hoje - nasceu).days)
        _evento("conta.criada", pessoa, inicio)
        for d in volta_em:
            _evento(
                "dieta.refeicao_registrada", pessoa, inicio + timedelta(days=d)
            )

    def test_d1_e_d7_contam_quem_registrou_naquele_dia(self):
        self._conta("volta", self.hoje - timedelta(days=40), volta_em=(1, 7))
        self._conta("some", self.hoje - timedelta(days=40))
        linhas = consultas.retencao_por_coorte(semanas=8)
        self.assertEqual(len(linhas), 1)
        celulas = {c["d"]: c for c in linhas[0]["celulas"]}
        self.assertEqual(linhas[0]["base"], 2)
        self.assertEqual(celulas[1]["n"], 1)
        self.assertEqual(celulas[1]["pct"], 50)
        self.assertEqual(celulas[7]["n"], 1)
        self.assertEqual(celulas[30]["n"], 0)

    def test_janela_que_nao_fechou_vem_vazia_e_nao_zero(self):
        """Zero seria a tela afirmando que ninguém voltou de um prazo que
        ainda não chegou."""
        self._conta("nova", self.hoje - timedelta(days=2))
        linhas = consultas.retencao_por_coorte(semanas=8)
        celulas = {c["d"]: c for c in linhas[0]["celulas"]}
        self.assertEqual(celulas[1]["pct"], 0)
        self.assertIsNone(celulas[7]["pct"])
        self.assertIsNone(celulas[30]["pct"])

    def test_abrir_o_app_sem_registrar_nao_e_retencao(self):
        """`tela.vista` não conta: curiosidade não é uso."""
        inicio = timezone.now() - timedelta(days=40)
        _evento("conta.criada", "curiosa", inicio)
        _evento("tela.vista", "curiosa", inicio + timedelta(days=1))
        linhas = consultas.retencao_por_coorte(semanas=8)
        celulas = {c["d"]: c for c in linhas[0]["celulas"]}
        self.assertEqual(celulas[1]["n"], 0)

    def test_sem_cadastro_nenhum_devolve_lista_vazia(self):
        self.assertEqual(consultas.retencao_por_coorte(semanas=8), [])


class OUsoPorAreaTests(TestCase):
    def test_registros_e_pessoas_por_area(self):
        agora = timezone.now()
        _evento("dieta.refeicao_registrada", "a", agora)
        _evento("dieta.pulou", "a", agora)
        _evento("dieta.refeicao_registrada", "b", agora)
        _evento("treino.serie_concluida", "a", agora)
        linhas = consultas.uso_por_area(semanas=8)
        self.assertEqual(len(linhas), 1)
        por_area = {a["area"]: a for a in linhas[0]["areas"]}
        # Três registros de alimentação, mas DUAS pessoas: somar as pessoas
        # distintas de cada evento contaria a "a" duas vezes. A CHAVE é
        # `Pilar.DIETA` — "dieta" —, e o nome de tela ("Alimentação") sai de
        # `Pilar.label`: o valor nunca muda, a tela pode mudar.
        self.assertEqual(por_area[Pilar.DIETA]["registros"], 3)
        self.assertEqual(por_area[Pilar.DIETA]["pessoas"], 2)
        self.assertEqual(por_area[Pilar.TREINO]["registros"], 1)
        self.assertEqual(por_area[Pilar.CORRIDA]["registros"], 0)

    def test_toda_area_aparece_mesmo_zerada(self):
        """Área sem registro é RESPOSTA — some da tabela e ninguém repara que
        a corrida não é usada."""
        _evento("agua.registrada", "a", timezone.now())
        linhas = consultas.uso_por_area(semanas=8)
        self.assertEqual(
            {a["area"] for a in linhas[0]["areas"]}, set(consultas.EVENTOS_DA_AREA)
        )

    def test_a_lista_de_eventos_de_registro_e_a_mesma_da_retencao(self):
        """Duas definições de "usou o app" é como duas telas passam a
        discordar — e esta é a régua que impede a segunda de nascer."""
        achatada = {
            nome for nomes in consultas.EVENTOS_DA_AREA.values() for nome in nomes
        }
        self.assertEqual(set(consultas.EVENTOS_DE_REGISTRO), achatada)

    def test_todo_evento_de_area_existe_na_taxonomia(self):
        from analytics import catalogo

        for nome in consultas.EVENTOS_DE_REGISTRO:
            self.assertTrue(catalogo.existe(nome), nome)

    def test_todo_passo_do_funil_existe_na_taxonomia(self):
        from analytics import catalogo

        for _chave, _rotulo, nome, _f in consultas.PASSOS_DE_ENTRADA:
            self.assertTrue(catalogo.existe(nome), nome)


class AsTelasDeProdutoTests(TestCase):
    """As três respostas têm tela, e a tela é da gerência."""

    def setUp(self):
        from accounts.models import User

        self.gestor = User.objects.create_user(
            email="gestor@exemplo.com", password="senha-bem-forte-123", is_staff=True
        )
        self.gestor.is_superuser = True
        self.gestor.save(update_fields=["is_superuser"])
        self.client.force_login(self.gestor)
        # As tabelas de coorte e de uso desenham LINHAS: sem evento nenhum
        # elas mostram o estado vazio, e o teste mediria a ausência. O funil
        # é o contrário — os sete passos são a definição e aparecem sempre.
        nasceu = timezone.now() - timedelta(days=40)
        _evento("conta.criada", "semeada", nasceu)
        _evento("dieta.refeicao_registrada", "semeada", nasceu + timedelta(days=1))
        _evento("agua.registrada", "semeada", timezone.now())

    def test_a_tela_de_entrada_abre_e_nomeia_os_passos(self):
        html = self.client.get(reverse("analytics_painel:entrada")).content.decode()
        self.assertIn("Abriu a landing", html)
        self.assertIn("1ª série registrada", html)

    def test_a_tela_de_entrada_aceita_dia_e_semana(self):
        for por in ("dia", "semana"):
            resposta = self.client.get(
                reverse("analytics_painel:entrada") + "?por=%s" % por
            )
            self.assertEqual(resposta.status_code, 200)

    def test_granularidade_desconhecida_cai_no_padrao(self):
        """Lista fechada, como todo parâmetro de tela deste app."""
        resposta = self.client.get(
            reverse("analytics_painel:entrada") + "?por=../etc/passwd"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["por"], "dia")

    def test_a_tela_de_uso_lista_as_cinco_areas_com_o_nome_oficial(self):
        """E o nome é o de `Pilar.label` — "Alimentação", não "Alimentacao".
        A tela escrevia `capfirst` sobre o slug, e isso era um TERCEIRO
        vocabulário para as mesmas cinco áreas (`CLAUDE.md`, "Uma área, um
        nome"). Sabotado (voltando ao `capfirst`), este teste fica
        vermelho nas duas áreas com acento."""
        html = self.client.get(reverse("analytics_painel:uso")).content.decode()
        for valor in consultas.EVENTOS_DA_AREA:
            self.assertIn(Pilar(valor).label, html)
        self.assertNotIn("Alimentacao", html)
        self.assertNotIn("Hidratacao", html)

    def test_a_retencao_mostra_d1_d7_e_d30(self):
        html = self.client.get(reverse("analytics_painel:retencao")).content.decode()
        for degrau in ("D1", "D7", "D30"):
            self.assertIn(degrau, html)

    def test_as_tres_telas_exigem_a_permissao_da_gestao(self):
        self.client.logout()
        for nome in ("entrada", "uso", "retencao"):
            resposta = self.client.get(reverse("analytics_painel:%s" % nome))
            self.assertIn(resposta.status_code, (302, 403), nome)


class OTopoDoFunilNaoCustaOBancoTests(TestCase):
    """`site.landing_vista` é o único degrau que nasce no CLIENTE, e a razão é
    uma garantia medida: `/` anônima é a página mais barata do app, com ZERO
    consulta (`plans/test_landing.py`), porque é ela que o visitante novo vê
    com o Render dormindo e o Neon à parte. A primeira versão disparava o
    evento em `LandingView.get()` — um INSERT em toda visita, inclusive as de
    robô — e este teste é o que impede a volta.

    As DUAS pontas ficam presas aqui de propósito: o marcador no template sem
    o leitor no JavaScript é um evento que nunca chega, e o leitor sem o
    marcador é código morto. Já aconteceu neste repositório com o seletor do
    `pwa.js` (`CLAUDE.md`, "O JavaScript da página mora em `pwa.js`")."""

    def test_a_landing_nao_dispara_evento_pelo_servidor(self):
        with self.assertNumQueries(0):
            resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_o_template_da_landing_marca_o_evento_ao_abrir(self):
        html = self.client.get("/").content.decode()
        self.assertIn('data-evento-ao-abrir="site.landing_vista"', html)

    def test_o_javascript_dispara_o_que_o_marcador_pede(self):
        # SEM OS COMENTÁRIOS: este arquivo explica o marcador em prosa, e uma
        # asserção sobre o texto cru passaria com o código apagado — a
        # armadilha que o `CLAUDE.md` descreve na seção de Testes. Sabotado
        # (só o comentário sobrando), este teste fica vermelho.
        js = (settings.BASE_DIR / "static" / "js" / "analytics.js").read_text(
            encoding="utf-8"
        )
        codigo = chr(10).join(
            linha for linha in js.splitlines() if not linha.lstrip().startswith("//")
        )
        self.assertIn('querySelector("[data-evento-ao-abrir]")', codigo)
        self.assertIn('getAttribute("data-evento-ao-abrir")', codigo)
