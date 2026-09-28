"""A linguagem da alimentação: ESTIMATIVA e SUGESTÃO, nunca "plano" — e a
landing não promete "dieta".

Por que isto importa (decisão do dono, 21/09/2026, sobre a pesquisa legal
guardada em `gabrielmrvb/nutriplan-docs`): a Lei 8.234/1991 faz da
prescrição dietética uma atividade privativa do nutricionista, e a página
"Exercício ilegal da profissão" do CFN (30/01/2026) lê a "oferta de planos
alimentares por leigos, especialmente no ambiente digital" como conduta
enquadrável no art. 47 da Lei das Contravenções Penais. O NutriPlan não
prescreve — aplica fórmulas públicas aos dados que a pessoa digita e monta
um cardápio de exemplo —, e o texto tem de dizer isso com as palavras
certas. "Plano" e "dieta" são as palavras do conselho para COMIDA; para o
treino elas continuam livres, porque não há conselho privativo em jogo.

Quatro réguas, cada uma com o que protege:

1. o cadastro e a dieta AVISAM que o resultado não substitui nutricionista;
2. nenhuma tela da alimentação chama o resultado de "plano";
3. a landing e as descrições públicas (meta, manifesto) não prometem
   "dieta" — "anunciar que a exerce" está no tipo do art. 47.
4. o cadastro, a última etapa e a Alimentação — as telas que ENTREGAM
   número — dizem que a orientação de quem tem registro profissional (CRN
   para nutrição, CREF para Educação Física) não é substituída (§4 do
   Gate 1, mensagem do dono de 28/09/2026; `AVISO_CRN_CREF`). A ficha de
   treino (`templates/workouts/`) e a tela de pagamento (que não existe)
   ficam de fora deste lote — registrado no ledger. A cláusula 2 dos Termos
   é de outro lote (Lote 4) e por isso continua com a frase antiga
   (`AVISO`), coexistindo até lá.

A régua mede o TEXTO VISÍVEL, sem `<script>`, `<style>`, comentário e tag:
o `CLAUDE.md` registra o teste que passou por acidente porque o marcador
também estava dentro do JavaScript, e o inverso — reprovar por uma palavra
num comentário — seria o mesmo erro ao contrário.
"""
import html as entidades
import re
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from plans.models import NutritionPlan
from accounts.test_tres_etapas import ETAPA1, ETAPA2, ETAPA3, etapa
from config.seo import DESCRICAO_PADRAO
from accounts import papeis

#: A frase do aviso, a mesma no cadastro, na última etapa e junto do cardápio
#: — hoje só nos Termos (Lote 4 ainda não a trocou). NÃO confundir com
#: `AVISO_CRN_CREF`, abaixo: as duas frases coexistem até o Lote 4 levar a
#: nova para a cláusula 2 dos Termos.
AVISO = "não substitui nutricionista nem médico"

#: O aviso regulatório do §4 do Gate 1 (LGPD, mensagem do dono de
#: 28/09/2026): o app calcula e organiza, não prescreve, e a orientação de
#: quem tem registro profissional — CRN para nutrição, CREF para Educação
#: Física — não é substituída. Fica nas três telas que ENTREGAM número
#: (cadastro, última etapa do onboarding, Alimentação); a ficha de treino e
#: a tela de pagamento (que não existe) ficam de fora deste lote.
AVISO_CRN_CREF = (
    "não substitui a orientação de um nutricionista (registrado no CRN) "
    "nem de um profissional de Educação Física (registrado no CREF)"
)

#: A palavra proibida na alimentação, como palavra inteira: "planos" e
#: "plano" caem; "planejar" e "plano de fundo" não existem nessas telas, e
#: se um dia existirem o teste dirá onde.
PLANO = re.compile(r"\bplanos?\b", re.IGNORECASE)
DIETA = re.compile(r"\bdietas?\b", re.IGNORECASE)


def texto_visivel(html):
    """O que a pessoa lê: sem script, estilo, comentário nem tag."""
    sem_blocos = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    sem_comentarios = re.sub(r"<!--.*?-->", " ", sem_blocos, flags=re.S)
    sem_tags = re.sub(r"<[^>]+>", " ", sem_comentarios)
    return re.sub(r"\s+", " ", entidades.unescape(sem_tags)).strip()


def apenas_o_main(html):
    """Só o `<main>`: a barra de cima, o rodapé e o `<head>` ficam de fora."""
    corpo = html.split("<main", 1)[1] if "<main" in html else html
    return corpo.split("</main>", 1)[0]


class ComCadastroCompleto(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        papeis.sincronizar_papeis()

    def pessoa(self, email="linguagem@exemplo.com"):
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        return user

    def pessoa_completa(self, email="completa@exemplo.com"):
        user = self.pessoa(email)
        self.client.post(etapa(3), ETAPA3)
        return user


class OCadastroEADietaAvisamTests(ComCadastroCompleto):
    def test_a_tela_de_criar_conta_avisa_que_nao_substitui_nutricionista(self):
        texto = texto_visivel(self.client.get(reverse("accounts:signup")).content.decode())
        self.assertIn(AVISO_CRN_CREF, texto)

    def test_a_ultima_etapa_avisa_e_o_botao_calcula_uma_estimativa(self):
        self.pessoa()
        html = self.client.get(etapa(3)).content.decode()
        texto = texto_visivel(html)
        self.assertIn(AVISO_CRN_CREF, texto)
        self.assertIn("Calcular minha estimativa", texto)
        self.assertNotIn("Criar meu plano", texto)

    def test_a_mensagem_de_pronto_fala_em_estimativa(self):
        self.pessoa()
        self.client.post(etapa(3), ETAPA3)
        texto = texto_visivel(self.client.get(reverse("plans:today")).content.decode())
        self.assertIn("Sua estimativa está pronta", texto)
        self.assertNotIn("Seu plano está pronto", texto)

    def test_a_tela_do_cardapio_avisa_junto_do_cardapio(self):
        """O aviso mora onde o cardápio mora, e o cardápio mudou de tela em
        22/09/2026: a Hoje virou o painel do dia e a Alimentação ganhou
        endereço próprio."""
        self.pessoa_completa()
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        cardapio = html.split("Seu cardápio de hoje", 1)[1]
        self.assertIn(AVISO_CRN_CREF, texto_visivel(cardapio))

    def test_os_termos_dizem_de_quem_e_a_prescricao(self):
        """Os Termos continuam com a frase ANTIGA (`AVISO`): a cláusula 2 é
        do Lote 4 (`templates/legal/`, fora do escopo deste lote), e as duas
        frases coexistem até lá."""
        texto = texto_visivel(self.client.get(reverse("termos")).content.decode())
        self.assertIn(AVISO, texto)
        self.assertIn("Lei 8.234/1991", texto)


class OAvisoCRNCREFApareceOndeOAppEntregaNumeroTests(ComCadastroCompleto):
    """§4 do Gate 1 (mensagem do dono, 28/09/2026): o app entrega número em
    cinco lugares, e o Lote 3 cobre três — o cadastro por e-mail, a última
    etapa do onboarding e a Alimentação. A ficha de treino
    (`templates/workouts/`) e a tela de pagamento (que não existe) ficam de
    fora, registrado no ledger. A MESMA frase nas três telas é o que este
    teste prende — sabotar qualquer uma das três a derruba."""

    def test_o_mesmo_aviso_aparece_nas_tres_telas(self):
        """`accounts:signup` redireciona quem já está logado — por isso a
        leitura da tela de cadastro vem ANTES de `self.pessoa()`."""
        signup = texto_visivel(self.client.get(reverse("accounts:signup")).content.decode())

        self.pessoa()
        etapa_3 = texto_visivel(self.client.get(etapa(3)).content.decode())
        self.client.post(etapa(3), ETAPA3)
        alimentacao = texto_visivel(self.client.get(reverse("plans:alimentacao")).content.decode())

        for nome, texto in (("signup", signup), ("etapa 3", etapa_3), ("alimentação", alimentacao)):
            with self.subTest(tela=nome):
                self.assertIn(AVISO_CRN_CREF, texto)


class NenhumaTelaDaAlimentacaoChamaDePlanoTests(ComCadastroCompleto):
    """O `<main>` de cada tela, sem a palavra — inclusive onde o treino mora
    ao lado: "plano" não é o nome de nada que o app entrega. A ficha é
    "ficha", a corrida é "programa"... e o que o teste achar, o teste diz."""

    def test_as_telas_de_quem_ja_tem_cardapio(self):
        self.pessoa_completa()
        rotas = [reverse("plans:today"), reverse("plans:history"), reverse("accounts:profile"),
                 reverse("ajuda:index"), "/nao-existe-esta-tela/"]
        for rota in rotas:
            with self.subTest(rota=rota):
                texto = texto_visivel(apenas_o_main(self.client.get(rota).content.decode()))
                self.assertIsNone(PLANO.search(texto), texto[:400])

    def test_as_telas_de_quem_ainda_nao_tem_conta(self):
        for rota in (reverse("plans:today"), reverse("accounts:signup"), reverse("accounts:login")):
            with self.subTest(rota=rota):
                texto = texto_visivel(apenas_o_main(self.client.get(rota).content.decode()))
                self.assertIsNone(PLANO.search(texto), texto[:400])

    def test_a_ultima_etapa_do_cadastro(self):
        self.pessoa()
        texto = texto_visivel(apenas_o_main(self.client.get(etapa(3)).content.decode()))
        self.assertIsNone(PLANO.search(texto), texto[:400])

    def test_o_painel_de_gestao(self):
        gestor = User.objects.create_user(email="gestor@exemplo.com", password="senha-bem-forte-123")
        gestor.is_staff = True
        gestor.save(update_fields=["is_staff"])
        gestor.groups.add(Group.objects.get(name=papeis.ADMINISTRADORES))
        self.client.force_login(gestor)
        for rota in ("/gestao/", "/gestao/pessoas/"):
            with self.subTest(rota=rota):
                texto = texto_visivel(apenas_o_main(self.client.get(rota).content.decode()))
                self.assertIsNone(PLANO.search(texto), texto[:400])


#: O rótulo que saiu da tela em 24/09/2026 (decisão do dono, depois de usar o
#: app): o card JÁ diz qual receita é, e o botão diz a AÇÃO. "Comi esta" era o
#: card contando a mesma coisa duas vezes — e, na folha da receita aberta por
#: link, "esta" não tinha a quem apontar.
COMI_ESTA = re.compile(r"\bcomi esta\b", re.IGNORECASE)

#: "Pulei" virou "Não comi" na mesma decisão. A Ajuda ENSINAVA o botão pelo
#: nome antigo — texto de produto contradizendo a tela, na mesma área do app.
PULEI = re.compile(r"\bpulei\b", re.IGNORECASE)


class NenhumaTelaDizComiEstaTests(ComCadastroCompleto):
    """O botão de registrar refeição diz "Registrar", em toda tela que o tem."""

    def test_o_cardapio_diz_registrar(self):
        self.pessoa_completa()
        texto = texto_visivel(
            self.client.get(reverse("plans:alimentacao")).content.decode()
        )
        self.assertIn("Registrar", texto)
        self.assertIsNone(COMI_ESTA.search(texto), texto[:400])

    def test_a_folha_da_receita_diz_registrar(self):
        """A folha é a tela em que o rótulo antigo mentia: aberta por link, ela
        não tem "esta" nenhuma ao lado."""
        pessoa = self.pessoa_completa()
        plano = NutritionPlan.objects.filter(user=pessoa, is_active=True).first()
        slot = plano.slots.order_by("order").first()
        opcao = slot.options.order_by("rank").first()
        html = self.client.get(
            reverse("plans:receita", args=[slot.pk, opcao.pk])
        ).content.decode()
        texto = texto_visivel(html)
        self.assertIn("Registrar", texto)
        self.assertIsNone(COMI_ESTA.search(texto), texto[:400])

    def test_nenhuma_tela_de_quem_tem_cardapio_diz_comi_esta_nem_pulei(self):
        self.pessoa_completa()
        for rota in (reverse("plans:today"), reverse("plans:alimentacao"),
                     reverse("plans:history"), reverse("ajuda:index")):
            with self.subTest(rota=rota):
                texto = texto_visivel(
                    apenas_o_main(self.client.get(rota).content.decode())
                )
                self.assertIsNone(COMI_ESTA.search(texto), texto[:400])
                self.assertIsNone(PULEI.search(texto), texto[:400])

    def test_os_templates_versionados_nao_guardam_os_rotulos_antigos(self):
        """A régua por rota cobre cinco telas; a promessa é "tela nenhuma".

        Esta varre `templates/` inteiro — o mesmo padrão de
        `config/test_design_system.py` —, fora dos comentários, que contam a
        história e precisam citar o nome antigo.
        """
        import subprocess

        from django.conf import settings

        raiz = Path(settings.BASE_DIR)
        arquivos = subprocess.run(
            ["git", "ls-files", "templates"],
            cwd=raiz, capture_output=True, text=True, check=True,
        ).stdout.split()
        achados = []
        for caminho in arquivos:
            if not caminho.endswith(".html"):
                continue
            texto = (raiz / caminho).read_text(encoding="utf-8")
            sem_comentario = re.sub(r"{% comment %}.*?{% endcomment %}", " ", texto, flags=re.S)
            sem_comentario = re.sub(r"{#.*?#}", " ", sem_comentario, flags=re.S)
            for regua, nome in ((COMI_ESTA, "Comi esta"), (PULEI, "Pulei")):
                if regua.search(sem_comentario):
                    achados.append("%s: %s" % (caminho, nome))
        self.assertEqual(achados, [])
class NenhumaTelaLogadaDaAlimentacaoFalaEmOpcaoAOuBTests(ComCadastroCompleto):
    """O rótulo A/B saiu da INTERFACE em 23/09/2026 — o card de receita não
    escreve mais "A" nem "B"; `plans.models.OptionLabel` continua existindo,
    mas só no banco e na lista de compras (rótulo de outra tarefa, por isso
    `/lista-de-compras/` fica de fora daqui de propósito). A frase abaixo do
    cardápio e a pergunta da FAQ tinham ficado para trás: diziam "escolher
    entre A e B" para uma pessoa que nunca vê essas letras na tela."""

    #: Palavra inteira, para não casar com nomes que têm "a" ou "b" soltos no
    #: meio ("proteína", "abaixo"...). E a LETRA é maiúscula de propósito: com
    #: `IGNORECASE` no grupo todo, uma frase futura como "não há opção a
    #: perder" reprovaria o CI sem ter nada a ver com o rótulo das opções — e
    #: régua de nomenclatura não pode virar censura de vocabulário, que é o
    #: contrapeso já escrito no `CLAUDE.md`. "A e B" fica insensível, porque
    #: ali as duas letras juntas só podem ser o rótulo.
    OPCAO_AB = re.compile(r"(?i:\bA e B\b)|\b[Oo]p[cç][aã]o\s+[AB]\b")

    def test_as_telas_da_alimentacao_nao_citam_a_letra_das_opcoes(self):
        self.pessoa_completa()
        for rota in (reverse("plans:today"), reverse("plans:alimentacao")):
            with self.subTest(rota=rota):
                texto = texto_visivel(apenas_o_main(self.client.get(rota).content.decode()))
                self.assertIsNone(self.OPCAO_AB.search(texto), texto[:400])

    def test_a_regua_pega_o_rotulo_e_deixa_a_prosa_em_paz(self):
        """Controle positivo E contrapeso no mesmo teste: ela tem de achar o
        rótulo escrito de qualquer jeito, e NÃO pode achar a preposição."""
        for frase in ("Opção A", "opção B", "A e B fecham a mesma caloria", "a e b"):
            with self.subTest(acha=frase):
                self.assertIsNotNone(self.OPCAO_AB.search(frase))
        for frase in ("não há opção a perder", "cada opção básica", "uma opção boa"):
            with self.subTest(ignora=frase):
                self.assertIsNone(self.OPCAO_AB.search(frase))


class ALandingEAsDescricoesNaoPrometemDietaTests(TestCase):
    def test_a_landing_fala_em_estimativa_e_nao_em_dieta(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        texto = texto_visivel(apenas_o_main(html))
        self.assertIn("estimativa", texto.lower())
        self.assertIsNone(DIETA.search(texto), texto[:400])
        self.assertIsNone(PLANO.search(texto), texto[:400])

    def test_o_titulo_e_a_descricao_da_landing(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        cabeca = html.split("</head>", 1)[0]
        for atributo in ("<title>", 'name="description"', 'property="og:description"', '"description":'):
            with self.subTest(atributo=atributo):
                self.assertIn(atributo, cabeca)
        self.assertIsNone(DIETA.search(cabeca), cabeca[:600])
        self.assertIsNone(PLANO.search(cabeca), cabeca[:600])

    def test_a_descricao_padrao_e_o_manifesto(self):
        self.assertIsNone(DIETA.search(DESCRICAO_PADRAO), DESCRICAO_PADRAO)
        self.assertIsNone(PLANO.search(DESCRICAO_PADRAO), DESCRICAO_PADRAO)
        manifesto = self.client.get(reverse("manifest")).json()
        self.assertIsNone(DIETA.search(manifesto["description"]), manifesto["description"])
        self.assertIsNone(PLANO.search(manifesto["description"]), manifesto["description"])

    def test_as_descricoes_das_telas_publicas(self):
        for rota in (reverse("accounts:signup"), reverse("accounts:login"), reverse("ajuda:index")):
            with self.subTest(rota=rota):
                cabeca = self.client.get(rota).content.decode().split("</head>", 1)[0]
                descricao = re.search(r'name="description" content="([^"]*)"', cabeca).group(1)
                self.assertIsNone(DIETA.search(descricao), descricao)
                self.assertIsNone(PLANO.search(descricao), descricao)
