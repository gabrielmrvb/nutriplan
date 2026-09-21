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

Três réguas, cada uma com o que protege:

1. o cadastro e a dieta AVISAM que o resultado não substitui nutricionista;
2. nenhuma tela da alimentação chama o resultado de "plano";
3. a landing e as descrições públicas (meta, manifesto) não prometem
   "dieta" — "anunciar que a exerce" está no tipo do art. 47.

A régua mede o TEXTO VISÍVEL, sem `<script>`, `<style>`, comentário e tag:
o `CLAUDE.md` registra o teste que passou por acidente porque o marcador
também estava dentro do JavaScript, e o inverso — reprovar por uma palavra
num comentário — seria o mesmo erro ao contrário.
"""
import html as entidades
import re

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.test_tres_etapas import ETAPA1, ETAPA2, ETAPA3, etapa
from config.seo import DESCRICAO_PADRAO
from accounts import papeis

#: A frase do aviso, a mesma no cadastro, na última etapa e junto do cardápio.
AVISO = "não substitui nutricionista nem médico"

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
        self.assertIn(AVISO, texto)

    def test_a_ultima_etapa_avisa_e_o_botao_calcula_uma_estimativa(self):
        self.pessoa()
        html = self.client.get(etapa(3)).content.decode()
        texto = texto_visivel(html)
        self.assertIn(AVISO, texto)
        self.assertIn("Calcular minha estimativa", texto)
        self.assertNotIn("Criar meu plano", texto)

    def test_a_mensagem_de_pronto_fala_em_estimativa(self):
        self.pessoa()
        self.client.post(etapa(3), ETAPA3)
        texto = texto_visivel(self.client.get(reverse("plans:today")).content.decode())
        self.assertIn("Sua estimativa está pronta", texto)
        self.assertNotIn("Seu plano está pronto", texto)

    def test_a_home_avisa_junto_do_cardapio(self):
        self.pessoa_completa()
        html = self.client.get(reverse("plans:today")).content.decode()
        cardapio = html.split("Seu cardápio de hoje", 1)[1]
        self.assertIn(AVISO, texto_visivel(cardapio))

    def test_os_termos_dizem_de_quem_e_a_prescricao(self):
        texto = texto_visivel(self.client.get(reverse("termos")).content.decode())
        self.assertIn(AVISO, texto)
        self.assertIn("Lei 8.234/1991", texto)


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
