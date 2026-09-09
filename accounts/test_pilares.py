# -*- coding: utf-8 -*-
"""Os cinco pilares do NutriPlan: o que a pessoa quer cuidar, e o que primeiro.

Três coisas são protegidas aqui, e elas têm naturezas diferentes.

**O invariante.** A prioridade tem de ser um dos interesses marcados, e isso é
garantido pelo BANCO — `prioridade_pertence_aos_interesses`. É o primeiro
`CheckConstraint` do repositório, e ele existe pela mesma razão que o
`UniqueConstraint` de `RegistroAdministrativo` já dizia: duas transações
simultâneas atravessam juntas uma checagem em Python.

**A ausência de invenção.** Ninguém ganha preferência por ter usado o app. Uso
não é declaração, e a migration não infere nada — quem não respondeu fica com
`prioridade == ""`, que é um estado de verdade e não um buraco.

**A ausência de restrição.** Interesse organiza, não tranca. Quem escolheu só
Corrida continua com Dieta, Treino, Hidratação e Progresso abertos. É a
diferença entre personalizar e esconder, e ela precisa de teste porque é fácil
de perder numa refatoração que "simplifica" a navegação.
"""
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.forms import InteressesForm
from accounts.models import CAMPO_DO_PILAR, Pilar, Profile, User
from accounts.tests import STEP1, STEP2, STEP3, STEP4, STEP5, STEP6, step_url


class OInvarianteMoraNoBancoTests(TestCase):
    """A prioridade não pode apontar para uma área não marcada."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="pilar@exemplo.com", password="senha-bem-forte-123"
        )
        self.perfil = Profile.objects.create(
            user=self.user, sex="M", birth_date="1995-04-12", height_cm=178
        )

    def test_prioridade_fora_dos_interesses_e_recusada_pelo_banco(self):
        """O caso concreto: a tela de personalização posterior desmarca áreas e
        escolhe a principal no MESMO envio. Uma ordem de escrita trocada
        deixaria "prioridade corrida" com corrida desmarcada, e nenhuma tela do
        app sabe desenhar isso."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Profile.objects.filter(pk=self.perfil.pk).update(
                    interesse_dieta=True,
                    interesse_corrida=False,
                    prioridade=Pilar.CORRIDA,
                )

    def test_prioridade_dentro_dos_interesses_passa(self):
        """Controle positivo: sem ele, uma constraint que recusasse TUDO
        deixaria o teste acima verde e a personalização impossível."""
        Profile.objects.filter(pk=self.perfil.pk).update(
            interesse_corrida=True, prioridade=Pilar.CORRIDA
        )

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.prioridade, Pilar.CORRIDA)

    def test_prioridade_vazia_e_sempre_valida(self):
        """É o estado de quem ainda não respondeu, e é onde TODO usuário
        existente entrou por esta migration. Se a constraint o recusasse, a
        migration teria derrubado o app inteiro."""
        Profile.objects.filter(pk=self.perfil.pk).update(prioridade="")

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.prioridade, "")
        self.assertFalse(self.perfil.personalizacao_declarada)

    def test_o_invariante_vale_para_os_CINCO(self):
        """Varre os cinco em vez de confiar num só: uma constraint escrita à
        mão com cinco ramos erra em um deles, e o teste de um pilar só não
        veria."""
        for pilar, campo in CAMPO_DO_PILAR.items():
            with self.subTest(pilar=pilar):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Profile.objects.filter(pk=self.perfil.pk).update(
                            **{c: False for c in CAMPO_DO_PILAR.values()},
                            prioridade=pilar,
                        )
                # E o par positivo, no mesmo laço: o ramo daquele pilar existe.
                Profile.objects.filter(pk=self.perfil.pk).update(
                    **{c: (c == campo) for c in CAMPO_DO_PILAR.values()},
                    prioridade=pilar,
                )

    def test_interesses_devolve_os_marcados_na_ordem_da_tela(self):
        Profile.objects.filter(pk=self.perfil.pk).update(
            interesse_dieta=True, interesse_corrida=True, prioridade=Pilar.DIETA
        )
        self.perfil.refresh_from_db()

        self.assertEqual(self.perfil.interesses, [Pilar.DIETA, Pilar.CORRIDA])


class OFormularioNaoDeixaEscolhaAcidentalTests(TestCase):
    """A prioridade é uma pergunta própria, e não "o primeiro que o dedo pegou".

    Mas ela também não pode virar um erro que a pessoa não entende: marcar a
    principal IMPLICA o interesse, e uma área só dispensa a pergunta.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="forma@exemplo.com", password="senha-bem-forte-123"
        )
        self.perfil = Profile.objects.create(
            user=self.user, sex="M", birth_date="1995-04-12", height_cm=178
        )

    def enviar(self, interesses, prioridade=""):
        return InteressesForm(
            data={"interesses": interesses, "prioridade": prioridade},
            instance=self.perfil,
        )

    def test_uma_area_so_vira_a_principal_sem_perguntar(self):
        form = self.enviar(["dieta"])

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["prioridade"], Pilar.DIETA)

    def test_varias_areas_sem_principal_PERGUNTAM(self):
        """É a regra que impede a escolha acidental. Sem ela, o produto
        escolheria sozinho — e escolher sozinho é exatamente o que o dono
        pediu para não fazer."""
        form = self.enviar(["dieta", "corrida"])

        self.assertFalse(form.is_valid())
        self.assertIn("qual vem primeiro", str(form.errors))

    def test_escolher_a_principal_marca_a_area(self):
        """Sem JavaScript, alguém pode escolher a principal sem marcar a caixa
        de cima. Devolver erro seria cobrar do dedo uma coerência que o
        formulário garante sozinho."""
        form = self.enviar([], prioridade="corrida")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["interesses"], [Pilar.CORRIDA])

    def test_nenhuma_area_e_recusado(self):
        form = self.enviar([])

        self.assertFalse(form.is_valid())
        self.assertIn("pelo menos uma área", str(form.errors))

    def test_salvar_escreve_os_cinco_booleanos(self):
        form = self.enviar(["dieta", "hidratacao"], prioridade="hidratacao")
        self.assertTrue(form.is_valid(), form.errors)

        form.save()
        self.perfil.refresh_from_db()

        self.assertTrue(self.perfil.interesse_dieta)
        self.assertTrue(self.perfil.interesse_hidratacao)
        self.assertFalse(self.perfil.interesse_treino)
        self.assertFalse(self.perfil.interesse_corrida)
        self.assertFalse(self.perfil.interesse_progresso)
        self.assertEqual(self.perfil.prioridade, Pilar.HIDRATACAO)

    def test_desmarcar_area_NAO_apaga_historico(self):
        """Interesse organiza a tela; ele não é dono de dado nenhum.

        A prova é indireta de propósito: o formulário só escreve os seis campos
        de preferência, e é isso que garante que nada mais seja tocado.
        """
        from plans.models import HydrationLog
        from django.utils import timezone

        HydrationLog.objects.create(
            user=self.user, date=timezone.localdate(), ml=1500
        )

        form = self.enviar(["dieta", "hidratacao"], prioridade="hidratacao")
        self.assertTrue(form.is_valid())
        form.save()
        # E agora ela tira a hidratação.
        form = self.enviar(["dieta"], prioridade="dieta")
        self.assertTrue(form.is_valid())
        form.save()

        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.interesse_hidratacao)
        self.assertEqual(
            HydrationLog.objects.get(user=self.user).ml,
            1500,
            "desmarcar a área apagou a água registrada",
        )


class OUsuarioQueJaExistiaNaoGanhaPreferenciaInventadaTests(TestCase):
    """A migration não fabrica intenção humana.

    Medido nos 33 perfis do banco de desenvolvimento no dia em que ela rodou:
    `onboarding_step` foi para `[3, 5, 7]` — quem estava em 6 subiu e continua
    completo — e ZERO perfis ficaram com prioridade ou interesse.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="antigo@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        # E NÃO responde o 6 — é o usuário que a migration deixou completo sem
        # nunca ter visto a pergunta.
        Profile.objects.filter(user=self.user).update(onboarding_step=7)

    def test_ele_continua_entrando_no_app(self):
        resposta = self.client.get(reverse("plans:today"))

        self.assertEqual(resposta.status_code, 200)

    def test_ele_nao_tem_preferencia_nenhuma(self):
        perfil = Profile.objects.get(user=self.user)

        self.assertEqual(perfil.prioridade, "")
        self.assertEqual(perfil.interesses, [])
        self.assertFalse(perfil.personalizacao_declarada)

    def test_a_tela_dele_e_a_de_sempre(self):
        """Controle do "nada muda": o cartão do topo continua existindo e as
        seções continuam todas lá. Prioridade vazia não é uma experiência
        degradada — é a experiência de antes."""
        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn('class="card agora-card', html)
        self.assertIn('class="card agua-card', html)
        self.assertIn("Seu cardápio de hoje", html)


class NenhumPilarFicaEscondidoTests(TestCase):
    """Interesse PERSONALIZA. Ele não restringe.

    Quem marcou só Corrida continua com as outras quatro áreas abertas — e
    este teste existe porque "esconder o que não foi marcado" é a
    simplificação tentadora que transformaria a personalização em prisão.
    """

    @classmethod
    def setUpTestData(cls):
        # A ficha da semana precisa do catálogo de exercícios; sem ele a tela
        # de treino estoura, e o teste reprovaria por falta de fixture em vez
        # de por área escondida — que é o que ele mede.
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="so-corrida@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        self.client.post(
            step_url(6), {"interesses": ["corrida"], "prioridade": "corrida"}
        )

    def test_as_cinco_areas_continuam_respondendo(self):
        for nome in (
            "plans:today",
            "plans:hydration",
            "plans:history",
            "workouts:routine",
            "workouts:corridas",
        ):
            with self.subTest(area=nome):
                self.assertEqual(
                    self.client.get(reverse(nome)).status_code, 200, nome
                )

    def test_a_pessoa_declarou_mesmo_so_corrida(self):
        """Controle positivo do teste acima: sem ele, um `setUp` que falhasse
        em salvar deixaria todas as áreas abertas por acidente, e o teste
        passaria sem provar nada."""
        perfil = Profile.objects.get(user=self.user)

        self.assertEqual(perfil.interesses, [Pilar.CORRIDA])
        self.assertEqual(perfil.prioridade, Pilar.CORRIDA)


class AMigrationNaoEscreveNENHUMAPreferenciaTests(TestCase):
    """A guarda que nenhum teste de comportamento consegue dar.

    A migration roda uma vez, na criação do banco de teste — antes de qualquer
    usuário de teste existir. Um `RunPython` que fabricasse preferência
    passaria por todos os testes desta suíte sem tocar em ninguém, porque não
    há ninguém quando ele roda. Medido: uma sabotagem que acrescenta
    `interesse_treino=True, prioridade="treino"` ao `update` fica VERDE.

    Então a asserção é sobre o que ela ESCREVE, lido da fonte. É estrutural, e
    está declarado como estrutural. O que ela protege é a regra que o dono pôs
    como primeira restrição desta campanha: uso não é intenção declarada, e a
    migration não pode inferir preferência de quem já usava o app.
    """

    def test_o_runpython_so_mexe_no_passo_do_onboarding(self):
        import importlib
        import inspect

        modulo = importlib.import_module("accounts.migrations.0024_pilares_e_prioridade")
        fonte = inspect.getsource(modulo.preservar_quem_ja_terminou)

        self.assertIn("onboarding_step", fonte)
        for campo in list(CAMPO_DO_PILAR.values()) + ["prioridade"]:
            with self.subTest(campo=campo):
                self.assertNotIn(
                    campo,
                    fonte,
                    "a migration escreve preferência — uso não é declaração",
                )

    def test_a_volta_tambem_nao_escreve_preferencia(self):
        """Controle do teste acima pelo outro lado: a reversão também não pode
        inventar nada, e ela é o caminho menos olhado de toda migration."""
        import importlib
        import inspect

        modulo = importlib.import_module("accounts.migrations.0024_pilares_e_prioridade")
        fonte = inspect.getsource(modulo.desfazer)

        for campo in list(CAMPO_DO_PILAR.values()) + ["prioridade"]:
            with self.subTest(campo=campo):
                self.assertNotIn(campo, fonte)


class OPerfilDaPortaParaMudarDepoisTests(TestCase):
    """A escolha do onboarding não é eterna, e a porta para mudá-la já tinha um
    padrão pronto: cinco cartões do Perfil apontam para um passo do wizard.

    O cartão aparece SEMPRE, inclusive para quem nunca respondeu — para essa
    pessoa ele é o convite, no lugar onde ela já vai procurar quando quiser
    mexer no app. Esconder o cartão de quem não declarou deixaria a pergunta
    sem porta, que é o defeito que `TodaTelaTemPortaTests` existe para pegar.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="perfil-areas@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)

    def perfil_html(self):
        return self.client.get(reverse("accounts:profile")).content.decode()

    def cartao(self):
        """O CARTÃO "Suas áreas", recortado — e o recorte não é zelo.

        Desde que o mapa das cinco áreas entrou na barra de cima, os cinco
        rótulos de `Pilar` aparecem em TODA página autenticada. Uma asserção
        de rótulo sobre a página inteira passaria com o cartão vazio, ou com o
        `{% for %}` dele quebrado. Foi uma revisão adversarial que pegou.
        """
        html = self.perfil_html()
        self.assertIn("Prioridade no NutriPlan", html)
        return html.split("Prioridade no NutriPlan", 1)[1].split("</section>", 1)[0]

    def test_quem_nao_declarou_ve_o_ESTADO_e_nao_uma_cobranca(self):
        """O texto anterior convidava e desconvidava na mesma frase.

        "Você ainda não disse o que quer cuidar. Escolher organiza o que
        aparece primeiro; nada fica escondido por não ter sido marcado." — se
        nada fica escondido, por que escolher? A pergunta parecia não ter
        consequência, e foi por isso que a etapa passou por morta.

        Ela tem consequência: a prioridade abre ramos no cartão AGORA, decide
        onde a seção da área entra na Home e move o limiar do aviso de
        hidratação. O cartão passou a dizer o ESTADO — organização padrão — em
        vez de cobrar uma resposta cuja utilidade ele mesmo negava.
        """
        self.client.post(step_url(6), {"interesses": ["dieta"], "prioridade": "dieta"})
        Profile.objects.filter(user=self.user).update(
            prioridade="", **{c: False for c in CAMPO_DO_PILAR.values()}
        )

        cartao = self.cartao()

        self.assertIn("Nenhuma prioridade definida", cartao)
        self.assertIn("organização padrão", cartao)
        self.assertNotIn("ainda não disse o que quer cuidar", cartao)
        self.assertNotIn("nada fica escondido", cartao)

    def test_quem_declarou_ve_as_areas_e_qual_e_a_principal(self):
        self.client.post(
            step_url(6),
            {"interesses": ["dieta", "corrida"], "prioridade": "corrida"},
        )

        cartao = self.cartao()

        # A PRINCIPAL VEM NOMEADA, e não marcada com um selo dentro de uma
        # lista. Antes o cartão listava tudo junto e pintava a importante —
        # informação correta, leitura pior: quem lê precisava procurar qual era
        # a principal em vez de já receber a resposta.
        self.assertIn("Principal", cartao)
        self.assertIn("Também quero acompanhar", cartao)
        self.assertIn("Corrida", cartao)
        self.assertIn("Alimentação", cartao)
        # E as três não escolhidas ficam de fora DELE — o cartão diz o que a
        # pessoa escolheu, não o que o app tem. Quem lista as cinco é o mapa.
        for fora in ("Treino", "Hidratação", "Progresso"):
            with self.subTest(fora=fora):
                self.assertNotIn(fora, cartao)

    def test_o_cartao_leva_de_volta_ao_passo_das_areas(self):
        """A porta. Sem ela, mudar de ideia exigiria adivinhar uma URL."""
        self.client.post(step_url(6), {"interesses": ["dieta"], "prioridade": "dieta"})

        self.assertIn(step_url(6), self.perfil_html())

    def test_o_cartao_nao_promete_restricao(self):
        """A frase importa: interesse organiza, não tranca. Um texto do tipo
        "só as áreas escolhidas aparecem" seria falso e assustaria quem não
        quer perder nada."""
        self.client.post(step_url(6), {"interesses": ["dieta"], "prioridade": "dieta"})

        cartao = self.cartao()

        # Trechos que cabem numa LINHA do template: `assertIn` compara o HTML
        # cru, e a frase quebra entre duas linhas. É a mesma armadilha que já
        # apareceu na Hidratação V2.
        #
        # A frase mudou em 08/09/2026 junto com o cartão: ela agora nomeia a
        # consequência ANTES de garantir o acesso, porque era a consequência
        # que faltava — "nada fica escondido" sozinho fazia a escolha parecer
        # inútil.
        self.assertIn("organiza a tela inicial e alguns avisos", cartao)
        self.assertIn("Todas as áreas", cartao)
        self.assertIn("continuam disponíveis", cartao)


class NenhumaMigrationFabricaPreferenciaTests(TestCase):
    """A guarda acima lê DUAS funções nomeadas. Esta lê todas as migrations.

    O buraco que uma revisão adversarial apontou: um terceiro `RunPython`
    acrescentado a `operations`, um `AddField(default=True)`, ou uma migration
    0025 que fabrique preferência passavam intocados pelos dois testes de cima,
    que inspecionam `preservar_quem_ja_terminou` e `desfazer` e nada mais.

    A régua aqui é o ARQUIVO inteiro, de todas as migrations de `accounts`:
    fora da 0024 — que é quem CRIA os campos — nenhuma pode escrever
    preferência de ninguém.
    """

    #: A que cria os campos. Ela cita os nomes por obrigação (`AddField`), e é
    #: por isso que ela é a exceção — e a única.
    CRIADORA = "0024_pilares_e_prioridade"

    def migrations(self):
        from pathlib import Path

        pasta = Path(__file__).resolve().parent / "migrations"
        return sorted(
            p for p in pasta.glob("0*.py") if p.stem != self.CRIADORA
        )

    #: O que caracteriza FABRICAR preferência: escrever nos campos.
    #:
    #: A régua era "não CITAR o campo", e ela reprovou a primeira migration
    #: honesta que apareceu — a `0025`, que só troca o RÓTULO dos pilares e no
    #: banco é no-op. Citar não é escrever: o risco real é `RunPython`,
    #: `RunSQL` e um `default` verdadeiro, que são os três jeitos de uma
    #: migration marcar área para gente que não pediu.
    ESCRITAS = ("RunPython", "RunSQL", "default=True")

    @staticmethod
    def sem_dependencias(fonte):
        """A migration sem o bloco `dependencies`, que é NOME DE ARQUIVO.

        A régua reprovou a `0026`, que não escreve preferência nenhuma: ela só
        depende da `0025_alter_profile_prioridade`, e o nome da dependência
        contém "prioridade". Lida assim, a guarda reprovaria TODA migration de
        dados de `accounts` daqui para frente — bastaria ter um `RunPython` e
        depender da última, que por acaso se chama assim.

        Isso é mirar no lugar errado: o risco é escrever NO CAMPO, e o bloco de
        dependências não escreve em nada. Ele sai da leitura, e o resto — que é
        onde `RunPython` de verdade opera — continua inteiro sob a régua.
        """
        import re

        return re.sub(r"dependencies\s*=\s*\[.*?\]", "", fonte, flags=re.S)

    def test_o_bloco_de_dependencias_nao_conta_como_escrita(self):
        """Controle da correção acima, com as duas metades.

        Sem ele, alguém poderia "consertar" a guarda apagando fonte demais e
        ela passaria a aceitar uma escrita de verdade.
        """
        so_dependencia = (
            'dependencies = [("accounts", "0025_alter_profile_prioridade")]\n'
            "operations = [migrations.RunPython(seja_o_que_for)]"
        )
        de_verdade = (
            'dependencies = [("accounts", "0001_initial")]\n'
            "operations = [migrations.RunPython(marca_prioridade)]\n"
            'def marca_prioridade(apps, schema): perfil.prioridade = "treino"'
        )

        self.assertNotIn("prioridade", self.sem_dependencias(so_dependencia))
        self.assertIn("prioridade", self.sem_dependencias(de_verdade))

    def test_nenhuma_outra_migration_ESCREVE_nos_seis_campos(self):
        arquivos = self.migrations()

        # Controle positivo: se o `glob` parasse de achar arquivo, o laço
        # abaixo não rodaria e o teste passaria sem medir nada.
        self.assertGreater(len(arquivos), 20, arquivos)

        campos = list(CAMPO_DO_PILAR.values()) + ["prioridade"]
        for caminho in arquivos:
            fonte = self.sem_dependencias(caminho.read_text(encoding="utf-8"))
            if not any(campo in fonte for campo in campos):
                continue
            for escrita in self.ESCRITAS:
                with self.subTest(migration=caminho.stem, escrita=escrita):
                    self.assertNotIn(
                        escrita,
                        fonte,
                        "%s cita os campos de preferência E %s — uso não é "
                        "declaração" % (caminho.stem, escrita),
                    )

    def test_a_migration_do_rotulo_nao_mexe_em_valor_nenhum(self):
        """A 0025 renomeia a TELA. Se ela tivesse mexido em `value`, todo
        `CheckConstraint`, todo `CAMPO_DO_PILAR` e toda linha gravada
        apontariam para um identificador que deixou de existir."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parent
            / "migrations"
            / "0025_alter_profile_prioridade.py"
        ).read_text(encoding="utf-8")

        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn("'%s'" % pilar.value, fonte)
        self.assertNotIn("RunPython", fonte)
        self.assertNotIn("RunSQL", fonte)

    def test_a_criadora_nao_traz_nenhum_default_verdadeiro(self):
        """O outro jeito de fabricar: `AddField(default=True)`.

        Ele não passa por `RunPython` nenhum, então as duas guardas de função
        não o veriam — e ele marcaria a área de TODA conta existente de uma vez.
        """
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parent / "migrations" / (self.CRIADORA + ".py")
        ).read_text(encoding="utf-8")

        self.assertIn("default=False", fonte)
        self.assertNotIn("default=True", fonte)
