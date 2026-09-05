"""B6 — NAVEGAÇÃO: sair de uma tela pela porta por onde se entrou.

Dois achados, medidos no navegador.

1. `/treino/` manda para o passo 3 do cadastro ("Dias de treino"), e esse passo
   NÃO tem barra de abas — `sem_tabbar` é decisão registrada, e é certa: os
   destinos da barra devolveriam quem está no meio do wizard. O problema era o
   que sobrava como saída. Medido: "Voltar" apontava para o passo 2 (a tela de
   meta, que ninguém pediu) e "Salvar" ia para o Perfil. Nenhum dos dois voltava
   para o treino — de onde a pessoa veio e cuja ficha acabou de ser remontada
   com os dias que ela mudou. O único caminho de volta era o botão do NAVEGADOR.

2. As duas navegações principais do app — a barra de baixo no celular e a de
   cima no desktop — marcavam a aba da vez só com uma classe visual. Medido:
   `aria-current` voltava `null` nas quatro abas, em todas as telas. A barra do
   painel de gestão já usava o atributo; a navegação que todo mundo usa, não.

O que este arquivo NÃO refaz: `TodaTelaTemPortaTests` continua respondendo
"existe link para este destino em algum template?". Aqui a pergunta é outra —
"a saída leva de volta para onde a pessoa estava?".
"""
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.views import OnboardingStepMixin
from plans.tests import create_complete_user

User = get_user_model()

#: As quatro abas, na ordem que o contrato fixa.
#:
#: `Progresso`, e não `Métricas`. O documento escreve `Progresso` duas vezes —
#: na barra de hoje e na barra futura, depois da medição do GPS — e não escreve
#: `Métricas` uma única vez. A barra nasceu com "Métricas" no primeiro commit e
#: nunca houve decisão registrada a respeito; o `[manter a estrutura real
#: atualmente publicada]` do contrato fala de ESTRUTURA — quatro abas, esta
#: ordem, Corrida sob Treino —, não de nomenclatura.
ABAS = ("Dieta", "Treino", "Progresso", "Perfil")


class AEdicaoVoltaParaOndeAPessoaEstavaTests(TestCase):
    """Quem sai do treino para trocar os dias de treino volta para o treino."""

    @classmethod
    def setUpTestData(cls):
        # `/treino/` monta a ficha na primeira visita, e sem catálogo de
        # exercícios ela levanta `NoTrainingDays`. Semear aqui é o que faz o
        # teste medir NAVEGAÇÃO em vez de medir a ausência do catálogo.
        call_command("seed_workouts", verbosity=0)

    #: O passo 3 pede cinco campos: os dias, o horário, o tempo disponível e a
    #: janela de sono. Faltando um, o POST devolve 200 com o formulário
    #: inválido — e um teste de redirecionamento que aceitasse isso estaria
    #: medindo a recusa do formulário, não o caminho de volta.
    PASSO_3 = {
        "weekdays": ["0", "2", "4"],
        "start_time": "19:00",
        "duration_min": "60",
        "wake_time": "07:00",
        "sleep_time": "23:00",
    }

    def setUp(self):
        self.pessoa = create_complete_user(email="b6volta@exemplo.com")
        self.client.force_login(self.pessoa)

    def _botao_voltar(self, url):
        html = self.client.get(url).content.decode()
        trecho = html[html.index('class="form-actions"'):]
        achado = re.search(r'href="([^"]+)"[^>]*>\s*Voltar', trecho)
        return achado.group(1) if achado else None

    def test_vindo_do_treino_o_voltar_aponta_para_o_treino(self):
        destino = self._botao_voltar(
            reverse("accounts:onboarding_step", kwargs={"step": 3})
            + "?origem=treino"
        )

        self.assertEqual(destino, reverse("workouts:routine"))

    def test_vindo_do_treino_salvar_devolve_ao_treino(self):
        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3})
            + "?origem=treino",
            self.PASSO_3,
        )

        self.assertRedirects(resposta, reverse("workouts:routine"))

    def test_sem_origem_o_caminho_do_perfil_continua_igual(self):
        """O contra-controle. Uma correção que mandasse todo mundo para o
        treino quebraria os seis links de edição que saem do Perfil."""
        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            self.PASSO_3,
        )

        self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_sem_origem_o_voltar_tambem_sai_do_wizard(self):
        """Editando, "Voltar" é saída, e não um passo atrás: ele apontava para
        o passo 2 enquanto "Salvar" ia para o Perfil — dois botões, duas portas
        diferentes, nenhuma delas a tela de origem."""
        self.assertEqual(
            self._botao_voltar(
                reverse("accounts:onboarding_step", kwargs={"step": 3})
            ),
            reverse("accounts:profile"),
        )

    def test_origem_forjada_nao_vira_redirecionamento_aberto(self):
        """A origem vem do endereço, e endereço é do cliente. A lista é
        fechada, como em `LogWeightView`."""
        for forjada in ("https://exemplo.invalido/roubo", "//evil.example",
                        "/gestao/", "treino/../../etc"):
            with self.subTest(origem=forjada):
                resposta = self.client.post(
                    reverse("accounts:onboarding_step", kwargs={"step": 3})
                    + "?origem=" + forjada,
                    self.PASSO_3,
                )
                self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_a_lista_de_origens_e_fechada(self):
        """A guarda em si, e não só o efeito dela: um `dict` vazio ou um
        `getattr` que aceitasse qualquer coisa passaria nos testes acima por
        acidente, porque o padrão também é o Perfil."""
        self.assertIn("treino", OnboardingStepMixin.ORIGENS)
        self.assertEqual(
            set(OnboardingStepMixin.ORIGENS.values()), {"workouts:routine"}
        )
        self.assertEqual(OnboardingStepMixin.ORIGEM_PADRAO, "accounts:profile")

    def test_o_treino_manda_a_origem_nos_dois_links(self):
        """De nada adianta a view aceitar `origem` se a tela não a envia.

        São dois links, e os dois importam: o "Editar" do cartão de dias de
        treino e o convite de quem ainda não cadastrou nenhum.
        """
        from pathlib import Path

        ficha = (
            Path(__file__).resolve().parent.parent
            / "templates" / "workouts" / "routine.html"
        ).read_text(encoding="utf-8")

        com_origem = ficha.count(
            "{% url 'accounts:onboarding_step' step=3 %}?origem=treino"
        )
        total = ficha.count("{% url 'accounts:onboarding_step' step=3 %}")

        self.assertEqual(com_origem, 2)
        self.assertEqual(total, com_origem)

    def test_o_passo_de_edicao_continua_sem_barra_de_abas(self):
        """A correção NÃO é devolver a barra ao wizard.

        Ela sai de propósito: os destinos dela passam por
        `OnboardingRequiredMixin` e devolveriam quem ainda não terminou. O
        conserto é a saída do próprio passo levar de volta.
        """
        resposta = self.client.get(
            reverse("accounts:onboarding_step", kwargs={"step": 3})
        )

        self.assertTrue(resposta.context["sem_tabbar"])
        self.assertNotContains(resposta, 'class="tabbar"')


class AAbaDaVezEAnunciadaTests(TestCase):
    """`is-active` é pintura. Quem ouve a tela precisa do `aria-current`."""

    @classmethod
    def setUpTestData(cls):
        # `/treino/` monta a ficha na primeira visita, e sem catálogo de
        # exercícios ela levanta `NoTrainingDays`. Semear aqui é o que faz o
        # teste medir NAVEGAÇÃO em vez de medir a ausência do catálogo.
        call_command("seed_workouts", verbosity=0)

    #: (rota, rótulo da aba que deve estar marcada)
    #: Telas que ACENDEM uma aba, e qual.
    #:
    #: `workouts:corridas` saiu daqui, e a saída é a decisão do produto:
    #: Corrida é um dos cinco pilares e não subárea de Treino. Acender "Treino"
    #: ali era a subordinação visível na tela. Ver `SEM_ABA` logo abaixo.
    TELAS = (
        ("plans:today", "Dieta"),
        ("workouts:routine", "Treino"),
        ("plans:history", "Progresso"),
        ("accounts:profile", "Perfil"),
        ("achievements:list", "Perfil"),
        ("plans:shopping", "Dieta"),
    )

    #: Telas de PILAR que a barra de baixo não carrega — e onde nenhuma aba
    #: acende, porque acender a errada é pior que não acender nenhuma.
    #:
    #: O par de cada uma é a área que o MAPA marca: a orientação não some, ela
    #: muda de componente.
    SEM_ABA = (
        ("workouts:corridas", "Corrida"),
        ("plans:hydration", "Hidratação"),
    )

    def setUp(self):
        self.pessoa = create_complete_user(email="b6aba@exemplo.com")
        self.client.force_login(self.pessoa)

    def _abas(self, html, classe):
        """(rótulo, tem aria-current) de cada item de uma das navegações."""
        padrao = re.compile(
            r'<a class="%s([^"]*)"([^>]*)>(.*?)</a>' % classe, re.S
        )
        saida = []
        for extras, atributos, corpo in padrao.findall(html):
            rotulo = re.sub(r"<[^>]+>", " ", corpo)
            rotulo = " ".join(rotulo.split())
            saida.append(
                (rotulo, 'aria-current="page"' in atributos,
                 "is-active" in extras)
            )
        return saida

    def test_cada_tela_marca_uma_aba_so_e_a_certa(self):
        for rota, esperada in self.TELAS:
            with self.subTest(rota=rota):
                html = self.client.get(reverse(rota)).content.decode()
                marcadas = [
                    r for r, aria, _ in self._abas(html, "tabbar__item") if aria
                ]
                self.assertEqual(marcadas, [esperada])

    def test_a_pintura_e_o_anuncio_dizem_a_mesma_coisa(self):
        """Se um dia os dois divergirem, a tela mente para metade das pessoas.
        """
        for rota, _ in self.TELAS:
            with self.subTest(rota=rota):
                html = self.client.get(reverse(rota)).content.decode()
                for classe in ("tabbar__item", "app-bar__link"):
                    abas = self._abas(html, classe)
                    self.assertEqual(
                        [r for r, aria, _ in abas if aria],
                        [r for r, _, ativa in abas if ativa],
                        "%s divergiu em %s" % (classe, rota),
                    )

    def test_a_navegacao_de_desktop_tambem_anuncia(self):
        """Acima de 60rem a barra de baixo some e quem navega é a de cima."""
        html = self.client.get(reverse("workouts:routine")).content.decode()

        marcadas = [
            r for r, aria, _ in self._abas(html, "app-bar__link") if aria
        ]
        self.assertEqual(marcadas, ["Treino"])

    def test_as_quatro_abas_estao_na_ordem_publicada(self):
        """A ordem e os rótulos que o contrato fixa, lidos do documento.

        O contrato manda manter a ESTRUTURA publicada — quatro abas, esta
        ordem, Corrida fora dela — e nomeia a terceira de `Progresso`.
        """
        html = self.client.get(reverse("plans:today")).content.decode()

        # As DUAS navegações: a de baixo no celular e a de cima acima de 60rem.
        # Renomear uma e esquecer a outra deixaria o app chamando a mesma tela
        # de dois jeitos conforme a largura.
        for classe in ("tabbar__item", "app-bar__link"):
            with self.subTest(navegacao=classe):
                self.assertEqual(
                    [r for r, _, _ in self._abas(html, classe)], list(ABAS)
                )

    def test_nenhuma_aba_repete_destino(self):
        html = self.client.get(reverse("plans:today")).content.decode()

        destinos = re.findall(
            r'<a class="tabbar__item[^"]*"[^>]*?href="([^"]+)"', html, re.S
        )
        self.assertEqual(len(destinos), len(set(destinos)))
        self.assertEqual(len(destinos), 4)

    def test_a_corrida_nao_virou_aba(self):
        """O GPS numa PWA continua sem medição em aparelho, e a barra continua
        com quatro itens.

        O que MUDOU: a corrida deixou de ser alcançada só pelo treino. Ela é um
        dos cinco pilares e tem porta de primeiro nível no mapa — o que a
        asserção antiga (`assertNotIn` na página INTEIRA) proibia sem querer,
        porque o mapa mora na mesma página.

        A régua certa é a BARRA: corrida não é aba. E ali onde o mapa aparece,
        ele aparece — este teste passou a exigir as duas coisas.
        """
        html = self.client.get(reverse("plans:today")).content.decode()
        barra = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]

        self.assertNotIn(reverse("workouts:corridas"), barra)
        # Controle positivo do recorte: a barra tem destino, e são quatro.
        self.assertEqual(len(re.findall(r'href="', barra)), 4)
        # E a porta de primeiro nível existe, fora da barra.
        self.assertIn(reverse("workouts:corridas"), html)

    def test_a_tela_de_pilar_sem_aba_nao_acende_nenhuma(self):
        """Acender a aba errada é pior que não acender nenhuma.

        A tela de água acendia "Dieta" e a de corridas acendia "Treino" — a
        subordinação que `accounts.models.Pilar` diz não existir. Quem
        orienta agora é o mapa, e o par está em `SEM_ABA`.
        """
        for rota, area in self.SEM_ABA:
            with self.subTest(rota=rota):
                html = self.client.get(reverse(rota)).content.decode()
                barra = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]
                marcadas = [
                    r for r, aria, _ in self._abas(barra, "tabbar__item") if aria
                ]

                self.assertEqual(marcadas, [])
                mapa = html.split('class="mapa"', 1)[1].split("</details>", 1)[0]
                atual = [t for t in mapa.split("<a ") if 'aria-current="page"' in t]
                self.assertEqual(len(atual), 1, mapa)
                self.assertIn(area, atual[0])


class AOrigemAtravessaOPassoDaDivisaoTests(TestCase):
    """Quem veio do treino e passou pelo passo 4 continua voltando ao treino.

    Editar os dias de treino pode ABRIR uma pergunta a mais: quem passa a
    treinar quatro dias ou mais e nunca confirmou a preferência de divisão é
    levado ao passo 4 antes de terminar. Sem carregar a origem nesse salto, a
    pessoa cairia no Perfil por ter passado por uma tela extra — o mesmo
    defeito, um passo adiante.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    #: Quatro dias: é o que faz a preferência de divisão passar a importar.
    PASSO_3 = {
        "weekdays": ["0", "2", "4", "6"],
        "start_time": "19:00",
        "duration_min": "60",
        "wake_time": "07:00",
        "sleep_time": "23:00",
    }

    def setUp(self):
        self.pessoa = create_complete_user(email="b6divisao@exemplo.com")
        self.pessoa.profile.split_preference_confirmada = False
        self.pessoa.profile.save(update_fields=["split_preference_confirmada"])
        self.client.force_login(self.pessoa)

    def _passo_3(self, origem=""):
        url = reverse("accounts:onboarding_step", kwargs={"step": 3})
        return url + ("?origem=" + origem if origem else "")

    def test_o_salto_para_a_divisao_leva_a_origem_junto(self):
        resposta = self.client.post(self._passo_3("treino"), self.PASSO_3)

        self.assertRedirects(
            resposta,
            reverse("accounts:onboarding_step", kwargs={"step": 4})
            + "?origem=treino",
        )

    def test_terminando_a_divisao_a_pessoa_volta_ao_treino(self):
        """A ponta do caminho, e é ela que importa: o salto só vale se a volta
        chegar no treino."""
        self.client.post(self._passo_3("treino"), self.PASSO_3)

        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 4})
            + "?origem=treino",
            # O VALOR do choice, não o nome da constante: `SplitPreference.TRES`
            # vale "three".
            {"split_preference": "three"},
        )

        self.assertRedirects(resposta, reverse("workouts:routine"))

    def test_sem_origem_o_salto_continua_indo_para_o_perfil(self):
        """O contra-controle: quem editou pelo Perfil não pode ser desviado."""
        resposta = self.client.post(self._passo_3(), self.PASSO_3)

        self.assertRedirects(
            resposta, reverse("accounts:onboarding_step", kwargs={"step": 4})
        )

    def test_origem_forjada_nao_viaja_no_salto(self):
        """A interpolação só acontece depois de a origem passar pela lista
        fechada — o valor nunca chega cru na URL."""
        resposta = self.client.post(
            self._passo_3("https://exemplo.invalido/roubo"), self.PASSO_3
        )

        self.assertRedirects(
            resposta, reverse("accounts:onboarding_step", kwargs={"step": 4})
        )
