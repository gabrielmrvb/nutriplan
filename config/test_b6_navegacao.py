"""B6 — NAVEGAÇÃO: sair de uma tela pela porta por onde se entrou.

Dois achados, medidos no navegador.

1. `/treino/` manda para a etapa 2 do cadastro ("Seu objetivo e rotina", onde
   moram os dias de treino), e essa etapa NÃO tem barra de abas — `sem_tabbar`
   é decisão registrada, e é certa: os destinos da barra devolveriam quem está
   no meio do wizard. O problema era o que sobrava como saída. Medido, quando
   os dias eram o passo 3 de seis: "Voltar" apontava para o passo 2 (a tela de
   meta, que ninguém pediu) e "Salvar" ia para o Perfil. Nenhum dos dois voltava
   para o treino — de onde a pessoa veio e cuja ficha acabou de ser remontada
   com os dias que ela mudou. O único caminho de volta era o botão do NAVEGADOR.

   Desde 15/09/2026 o onboarding tem TRÊS etapas, e a divisão é perguntada
   DENTRO da etapa 2 quando os dias pedem — não há mais salto para um "passo
   4". A origem precisa sobreviver a isso também: ao erro de validação (a
   tela reabre com a pergunta) e ao salvar.

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

#: As CINCO abas, na ordem que o contrato fixa.
#:
#: `Progresso`, e não `Métricas`. O documento escreve `Progresso` duas vezes —
#: na barra de hoje e na barra futura, depois da medição do GPS — e não escreve
#: `Métricas` uma única vez. A barra nasceu com "Métricas" no primeiro commit e
#: nunca houve decisão registrada a respeito; o `[manter a estrutura real
#: atualmente publicada]` do contrato fala de ESTRUTURA, não de nomenclatura.
#:
#: UX-01 pôs Áreas no quarto item (Perfil saiu da barra: a barra responde
#: "onde eu vou", e Perfil é conta). O REDESENHO DE 22/09/2026 acrescentou a
#: primeira e renomeou a última:
#:
#: - **Hoje** existe porque a tela inicial voltou a ser o orquestrador do dia.
#:   A aba dizia "Alimentação" e levava para uma tela chamada "Hoje" que era a
#:   tela de dieta — a barra mentia sobre onde a pessoa estava;
#: - **Alimentação** ganhou tela própria (`plans:alimentacao`) e ficou com a
#:   aba que já tinha o nome dela;
#: - **Mais** é a antiga Áreas. O quarto item passou a guardar o que não é
#:   pilar do dia (Conquistas, Lista de compras, Perfil, Ajuda) além das áreas,
#:   e "Áreas" deixou de descrever o que há lá dentro.
#:
#: Cinco itens cabem: medido a 320px, "Alimentação" hifeniza e nada mais
#: quebra; de 360px para cima todos os rótulos ficam numa linha.
ABAS = ("Hoje", "Alimentação", "Treino", "Progresso", "Mais")


class AEdicaoVoltaParaOndeAPessoaEstavaTests(TestCase):
    """Quem sai do treino para trocar os dias de treino volta para o treino."""

    @classmethod
    def setUpTestData(cls):
        # `/treino/` monta a ficha na primeira visita, e sem catálogo de
        # exercícios ela levanta `NoTrainingDays`. Semear aqui é o que faz o
        # teste medir NAVEGAÇÃO em vez de medir a ausência do catálogo.
        call_command("seed_workouts", verbosity=0)

    #: A etapa 2 pede o objetivo, a atividade, os dias, a janela de sono e —
    #: com três dias, que já pedem a divisão — a preferência de divisão.
    #: Faltando um, o POST devolve 200 com o formulário inválido — e um teste
    #: de redirecionamento que aceitasse isso estaria medindo a recusa do
    #: formulário, não o caminho de volta.
    ETAPA_2 = {
        "goal": "cut",
        "activity_level": "light",
        "weekdays": ["0", "2", "4"], "musculacao": "sim",
        "wake_time": "07:00",
        "sleep_time": "23:00",
        "split_preference": "three",
    }

    def setUp(self):
        self.pessoa = create_complete_user(email="b6volta@exemplo.com")
        self.client.force_login(self.pessoa)

    def _botao_voltar(self, url):
        return self._voltar_em(self.client.get(url).content.decode())

    @staticmethod
    def _voltar_em(html):
        trecho = html[html.index('class="form-actions"'):]
        achado = re.search(r'href="([^"]+)"[^>]*>\s*Voltar', trecho)
        return achado.group(1) if achado else None

    def test_vindo_do_treino_o_voltar_aponta_para_o_treino(self):
        destino = self._botao_voltar(
            reverse("accounts:onboarding_step", kwargs={"step": 2})
            + "?origem=treino"
        )

        self.assertEqual(destino, reverse("workouts:routine"))

    def test_vindo_do_treino_salvar_devolve_ao_treino(self):
        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 2})
            + "?origem=treino",
            self.ETAPA_2,
        )

        self.assertRedirects(resposta, reverse("workouts:routine"))

    def test_quem_edita_os_dias_e_ainda_nao_escolheu_a_divisao_e_perguntado(self):
        """A pergunta da divisão, feita NA PRÓPRIA etapa 2, com a origem intacta.

        POR QUE ELE PRECISOU DE TESTE PRÓPRIO. Esta pergunta já existia — era
        um desvio para o passo 4 — e nenhum teste a mirava: ela era disparada
        sem querer pelo fixture `create_complete_user`, que criava gente "com
        onboarding completo" e a divisão por confirmar. Quando o fixture
        passou a confirmá-la — porque completar o cadastro passou a incluir
        essa resposta —, a pergunta ficaria sem cobertura nenhuma.

        O caso real é o de quem terminou o cadastro antes de a pergunta existir
        para a frequência dela, e agora edita os dias de treino: a escolha que
        o app estava usando é a de fábrica, não a dela, e a etapa 2 é o momento
        exato de perguntar — os dias novos estão sendo salvos e a divisão vai
        ser decidida junto.

        Com três etapas não há salto: a etapa 2 RECUSA o envio sem a divisão
        quando os dias pedem, reabre com o bloco visível e o erro no campo, e
        não grava nada. E a origem não se perde no caminho: a tela reaberta
        continua com a saída apontando para o Treino, e responder leva de
        volta para lá — não para o Perfil por ter passado por uma pergunta a
        mais.
        """
        pessoa = create_complete_user(
            email="b6divisao@exemplo.com", split_preference_confirmada=False
        )
        self.client.force_login(pessoa)
        sem_divisao = {k: v for k, v in self.ETAPA_2.items() if k != "split_preference"}
        url = (
            reverse("accounts:onboarding_step", kwargs={"step": 2})
            + "?origem=treino"
        )

        resposta = self.client.post(url, sem_divisao)

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["mostrar_divisao"])
        self.assertTrue(resposta.context["forms"]["divisao"].errors)
        pessoa.profile.refresh_from_db()
        self.assertFalse(pessoa.profile.split_preference_confirmada)
        # A origem sobreviveu à recusa: a saída da tela reaberta é o Treino.
        self.assertEqual(
            self._voltar_em(resposta.content.decode()), reverse("workouts:routine")
        )

        resposta = self.client.post(url, self.ETAPA_2)

        self.assertRedirects(resposta, reverse("workouts:routine"))
        pessoa.profile.refresh_from_db()
        self.assertTrue(pessoa.profile.split_preference_confirmada)

    def test_a_origem_forjada_nao_sobrevive_a_pergunta_da_divisao(self):
        """O par adversarial do teste acima: `?origem=` é lista fechada.

        A tela reaberta com a pergunta escreve a saída a partir da origem, e
        responder redireciona a partir dela. Uma origem forjada sobrevivendo a
        qualquer uma das duas seria redirecionamento aberto entrando pela
        porta que a correção abriu.
        """
        pessoa = create_complete_user(
            email="b6forjada@exemplo.com", split_preference_confirmada=False
        )
        self.client.force_login(pessoa)
        sem_divisao = {k: v for k, v in self.ETAPA_2.items() if k != "split_preference"}
        url = (
            reverse("accounts:onboarding_step", kwargs={"step": 2})
            + "?origem=https://exemplo.invalido/"
        )

        resposta = self.client.post(url, sem_divisao)

        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertEqual(self._voltar_em(html), reverse("accounts:profile"))
        self.assertNotIn("exemplo.invalido", html)

        resposta = self.client.post(url, self.ETAPA_2)

        self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_sem_origem_o_caminho_do_perfil_continua_igual(self):
        """O contra-controle. Uma correção que mandasse todo mundo para o
        treino quebraria os seis links de edição que saem do Perfil."""
        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 2}),
            self.ETAPA_2,
        )

        self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_sem_origem_o_voltar_tambem_sai_do_wizard(self):
        """Editando, "Voltar" é saída, e não um passo atrás: ele apontava para
        a etapa anterior enquanto "Salvar" ia para o Perfil — dois botões, duas
        portas diferentes, nenhuma delas a tela de origem."""
        self.assertEqual(
            self._botao_voltar(
                reverse("accounts:onboarding_step", kwargs={"step": 2})
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
                    reverse("accounts:onboarding_step", kwargs={"step": 2})
                    + "?origem=" + forjada,
                    self.ETAPA_2,
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

    def test_o_treino_manda_a_origem_em_TODOS_os_links(self):
        """De nada adianta a view aceitar `origem` se a tela não a envia.

        REMIRADO, NÃO AFROUXADO. A versão anterior cobrava exatamente DOIS
        links — o "Editar" do cartão de dias e o convite de quem não cadastrou
        nenhum. A ressalva da divisão trouxe um terceiro ("Mudar meus dias de
        treino"), ele entrou sem `?origem=treino`, e a guarda ficou vermelha
        pelo número, não pelo defeito. Os dois erros são reais e são
        diferentes: o link novo estava errado E o teste media a coisa errada.

        A propriedade é "todo link para a etapa dos dias (a 2) emitido por
        esta tela leva a origem". O piso de três impede que ela passe por
        vacuidade no dia em que alguém apagar os links em vez de corrigi-los.
        """
        from pathlib import Path

        ficha = (
            Path(__file__).resolve().parent.parent
            / "templates" / "workouts" / "routine.html"
        ).read_text(encoding="utf-8")

        com_origem = ficha.count(
            "{% url 'accounts:onboarding_step' step=2 %}?origem=treino"
        )
        total = ficha.count("{% url 'accounts:onboarding_step' step=2 %}")

        self.assertGreaterEqual(total, 3)
        self.assertEqual(total, com_origem)

    def test_o_passo_de_edicao_continua_sem_barra_de_abas(self):
        """A correção NÃO é devolver a barra ao wizard.

        Ela sai de propósito: os destinos dela passam por
        `OnboardingRequiredMixin` e devolveriam quem ainda não terminou. O
        conserto é a saída da própria etapa levar de volta.
        """
        resposta = self.client.get(
            reverse("accounts:onboarding_step", kwargs={"step": 2})
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
    #: `workouts:corridas` acende "Mais", e nunca "Treino": Corrida é um dos
    #: cinco pilares e não subárea de Treino — acender Treino ali era a
    #: subordinação visível na tela. O negativo tem teste próprio abaixo.
    TELAS = (
        ("plans:today", "Hoje"),
        ("plans:alimentacao", "Alimentação"),
        ("workouts:routine", "Treino"),
        ("plans:history", "Progresso"),
        # UX-01: as duas moram dentro de Mais. Conquistas já declarava
        # `nav = "profile"` e acendia "Perfil" — uma tela de ofensiva acendendo
        # a aba de conta —, e o destino novo corrige as duas de uma vez.
        ("accounts:profile", "Mais"),
        ("achievements:list", "Mais"),
        ("plans:shopping", "Alimentação"),
        # AS DUAS QUE NÃO ACENDIAM NADA passaram a acender (22/09/2026), e
        # cada uma acende o que é verdade: a hidratação é um CARTÃO da tela
        # Hoje, então a tela cheia dela é a mesma seção; a corrida continua
        # sem aba própria e mora em Mais, como as outras áreas.
        #
        # Antes disso nenhuma acendia, porque acender a errada (a água
        # acendia "Dieta" e a corrida acendia "Treino" — a subordinação que
        # `accounts.models.Pilar` diz não existir) é pior que não acender.
        ("plans:hydration", "Hoje"),
        ("workouts:corridas", "Mais"),
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
            # O VALOR de `aria-current`, e não "é `page`?".
            #
            # UX-01 trouxe a distinção que o mapa antigo já fazia: `page` é a
            # página EXATA, `true` é "você está dentro desta seção". A aba
            # Áreas fica acesa em Perfil, Corrida e Hidratação, que moram
            # dentro dela — e anunciar `page` ali seria dizer que a pessoa está
            # numa página em que ela não está.
            #
            # Devolver o valor mantém todo `if aria` deste arquivo funcionando
            # e ainda deixa cada teste exigir a semântica exata quando importa.
            marca = re.search(r'aria-current="([^"]+)"', atributos)
            saida.append(
                (rotulo, marca.group(1) if marca else None,
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

    def test_as_cinco_abas_estao_na_ordem_publicada(self):
        """A ordem e os rótulos que o contrato fixa, lidos do documento.

        O contrato manda manter a ESTRUTURA publicada — esta ordem, Corrida
        fora dela — e nomeia `Progresso`.
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
        self.assertEqual(len(destinos), 5)

    def test_a_corrida_nao_virou_aba(self):
        """O GPS numa PWA continua sem medição em aparelho, e a barra tem CINCO
        itens sem ser um deles.

        UX-01 mudou ONDE fica a porta de primeiro nível da corrida. Ela era o
        mapa `<details>` na barra de cima, na mesma página; hoje é a tela de
        Mais, que é o quinto item da barra. A régua não mudou — corrida não é
        aba —, mudou o lugar onde a porta é cobrada.

        A quinta aba de 22/09/2026 é Hoje, e não Corrida: as cinco cabem a
        360px porque quatro rótulos são curtos. Uma sexta não cabe, e escolher
        entre "o dia inteiro" e "uma área que parte das pessoas não usa" é a
        mesma conta que manteve a barra em quatro até aqui.
        """
        html = self.client.get(reverse("plans:today")).content.decode()
        barra = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]

        self.assertNotIn(reverse("workouts:corridas"), barra)
        # Controle positivo do recorte: a barra tem destino, e são cinco.
        #
        # `<a ... href=`, e não `href=` solto: os ícones viraram `<use
        # href="#icone-…">` do sprite em 22/09/2026, e `href="` cru passou a
        # contar dez — cinco links e cinco desenhos.
        self.assertEqual(len(re.findall(r'<a class="tabbar__item[^>]*href="', barra)), 5)
        # A barra alcança Mais...
        self.assertIn(reverse("areas"), barra)
        # ...e é lá que a porta da corrida mora.
        areas = self.client.get(reverse("areas")).content.decode()
        self.assertIn(reverse("workouts:corridas"), areas)

    def test_nenhuma_tela_de_pilar_acende_a_aba_de_outro_pilar(self):
        """Acender a aba errada é pior que não acender nenhuma — e acender a
        CERTA é melhor que as duas.

        A tela de água acendia "Dieta" e a de corridas acendia "Treino": a
        subordinação que `accounts.models.Pilar` diz não existir. A correção
        de então tirou a mentira e deixou a barra apagada nessas telas, que
        era o melhor possível com quatro abas e nenhuma correspondendo.

        Hoje as duas acendem, e cada uma acende o que é verdade — a água é um
        cartão da tela Hoje, a corrida mora em Mais. Este teste guarda o que
        sempre guardou: nenhuma OUTRA aba acesa junto.
        """
        proibidas = {
            "plans:hydration": ("Alimentação", "Treino", "Progresso", "Mais"),
            "workouts:corridas": ("Alimentação", "Treino", "Progresso", "Hoje"),
        }
        for rota, nao_pode in proibidas.items():
            with self.subTest(rota=rota):
                html = self.client.get(reverse(rota)).content.decode()
                barra = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]
                acesas = [
                    rotulo
                    for rotulo, _aria, ativo in self._abas(barra, "tabbar__item")
                    if ativo
                ]

                self.assertEqual(len(acesas), 1, barra)
                for rotulo in nao_pode:
                    self.assertNotIn(rotulo, acesas)


class AOrigemSobreviveAPerguntaDaDivisaoTests(TestCase):
    """A divisão é pedida NA PRÓPRIA etapa 2, e a origem sobrevive à pergunta.

    Editar os dias de treino pode ABRIR uma pergunta a mais: quem passa a
    treinar dias suficientes para a preferência de divisão mudar a ficha
    (`preferencia_muda_a_divisao`) precisa respondê-la. Com seis passos isso
    era um salto para o passo 4, e a origem tinha de viajar nele; com três
    etapas a pergunta é feita na mesma tela — o servidor recusa o envio sem
    ela, reabre com o bloco visível e o erro no campo, e a origem continua na
    URL da tela reaberta. O que este arquivo protege é o mesmo: quem veio do
    Treino volta ao Treino depois de responder, e não cai no Perfil por ter
    passado por uma pergunta a mais.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    #: Quatro dias: é o que faz a preferência de divisão passar a importar
    #: (três já bastam hoje; quatro é a folga para a régua do motor mudar).
    ETAPA_2 = {
        "goal": "cut",
        "activity_level": "light",
        "weekdays": ["0", "2", "4", "6"], "musculacao": "sim",
        "wake_time": "07:00",
        "sleep_time": "23:00",
    }
    # O VALOR do choice, não o nome da constante: `SplitPreference.TRES`
    # vale "three".
    ETAPA_2_COM_DIVISAO = {**ETAPA_2, "split_preference": "three"}
    #: Dois dias: a divisão não muda nada e não é pedida.
    ETAPA_2_DOIS_DIAS = {**ETAPA_2, "weekdays": ["0", "3"], "musculacao": "sim"}

    def setUp(self):
        self.pessoa = create_complete_user(email="b6divisao@exemplo.com")
        self.pessoa.profile.split_preference_confirmada = False
        self.pessoa.profile.save(update_fields=["split_preference_confirmada"])
        self.client.force_login(self.pessoa)

    def _etapa_2(self, origem=""):
        url = reverse("accounts:onboarding_step", kwargs={"step": 2})
        return url + ("?origem=" + origem if origem else "")

    def _voltar_em(self, html):
        trecho = html[html.index('class="form-actions"'):]
        achado = re.search(r'href="([^"]+)"[^>]*>\s*Voltar', trecho)
        return achado.group(1) if achado else None

    def _confirmada(self):
        self.pessoa.profile.refresh_from_db()
        return self.pessoa.profile.split_preference_confirmada

    def test_a_divisao_e_pedida_na_propria_etapa_quando_os_dias_pedem(self):
        """Sem a divisão, com dias que pedem: 200, bloco visível, erro no
        campo — e NADA gravado, nem os dias, nem a confirmação."""
        dias_antes = sorted(self.pessoa.training_days.values_list("weekday", flat=True))

        resposta = self.client.post(self._etapa_2("treino"), self.ETAPA_2)

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["mostrar_divisao"])
        self.assertTrue(resposta.context["forms"]["divisao"].errors)
        self.assertEqual(
            sorted(self.pessoa.training_days.values_list("weekday", flat=True)),
            dias_antes,
        )
        self.assertFalse(self._confirmada())

    def test_a_origem_sobrevive_ao_erro_de_validacao(self):
        """A tela reaberta com a pergunta ainda sabe de onde a pessoa veio:
        "Voltar" aponta para o Treino, e o formulário reenvia para a MESMA
        URL — sem `action` próprio que descartasse o `?origem=`."""
        resposta = self.client.post(self._etapa_2("treino"), self.ETAPA_2)

        html = resposta.content.decode()
        self.assertEqual(self._voltar_em(html), reverse("workouts:routine"))
        # O formulário DA ETAPA — o último `<form` antes do campo dos dias; a
        # barra de cima tem o de sair, que tem `action` e não é este.
        formulario = re.findall(r"<form[^>]*>", html[: html.index('name="weekdays"')])[-1]
        self.assertNotIn("action=", formulario)

    def test_respondendo_a_divisao_a_pessoa_volta_ao_treino(self):
        """A ponta do caminho, e é ela que importa: a pergunta só vale se a
        volta chegar no treino — e com a divisão confirmada."""
        self.client.post(self._etapa_2("treino"), self.ETAPA_2)

        resposta = self.client.post(
            self._etapa_2("treino"), self.ETAPA_2_COM_DIVISAO
        )

        self.assertRedirects(resposta, reverse("workouts:routine"))
        self.assertTrue(self._confirmada())
        self.assertEqual(self.pessoa.training_days.count(), 4)

    def test_sem_origem_a_pergunta_continua_levando_ao_perfil(self):
        """O contra-controle: quem editou pelo Perfil não pode ser desviado."""
        resposta = self.client.post(self._etapa_2(), self.ETAPA_2)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self._voltar_em(resposta.content.decode()), reverse("accounts:profile")
        )

        resposta = self.client.post(self._etapa_2(), self.ETAPA_2_COM_DIVISAO)

        self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_origem_forjada_nao_viaja_na_pergunta(self):
        """A saída da tela reaberta e o redirecionamento de quem responde
        passam pela lista fechada — o valor nunca chega cru em lugar nenhum."""
        forjada = self._etapa_2("https://exemplo.invalido/roubo")

        resposta = self.client.post(forjada, self.ETAPA_2)

        html = resposta.content.decode()
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._voltar_em(html), reverse("accounts:profile"))
        self.assertNotIn("exemplo.invalido", html)

        resposta = self.client.post(forjada, self.ETAPA_2_COM_DIVISAO)

        self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_com_poucos_dias_a_divisao_nao_e_pedida(self):
        """O outro lado da régua: dois dias não pedem divisão, e o envio sem
        ela salva e volta direto ao Treino — sem confirmar uma escolha que a
        pessoa nunca viu."""
        resposta = self.client.post(self._etapa_2("treino"), self.ETAPA_2_DOIS_DIAS)

        self.assertRedirects(resposta, reverse("workouts:routine"))
        self.assertFalse(self._confirmada())
        self.assertEqual(self.pessoa.training_days.count(), 2)
