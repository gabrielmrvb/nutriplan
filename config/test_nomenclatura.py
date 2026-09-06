# -*- coding: utf-8 -*-
"""Uma área, um nome — em todo o produto.

O NutriPlan tinha TRÊS vocabulários para cinco áreas. A barra de baixo dizia
"Dieta", "Treino" e "Progresso"; o mapa, o onboarding e o painel de gestão
diziam "Alimentação", "Musculação" e "Evolução"; e a documentação chamava o
quinto pilar de "Progresso". No celular os dois primeiros apareciam AO MESMO
TEMPO — a barra fixa embaixo, o mapa aberto em cima —, e a pessoa via
"Progresso" e "Evolução" apontando para a mesma tela.

Era exatamente o defeito que `escolhas.py` nomeia e diz estar evitando: "ver a
mesma área com dois nomes na mesma sessão é pior que a duplicata". A regra
tinha sido aplicada entre `Pilar.label` e `DETALHES`, e não entre `Pilar.label`
e a barra que já existia.

O padrão oficial, decidido pelo dono:

    Alimentação · Treino · Corrida · Hidratação · Progresso

ESTES TESTES PROTEGEM NOME DE PRODUTO, NÃO PALAVRA DA LÍNGUA.

"dieta", "musculação" e "evolução" continuam livres em texto educativo, em
explicação de treino e em qualquer frase que não seja o RÓTULO de uma área. As
asserções abaixo olham só onde o nome do pilar aparece como nome do pilar: os
itens de navegação, os cartões do onboarding, o chip do Perfil, as listas do
painel. É por isso que nenhuma delas varre a página inteira atrás de uma
palavra.
"""
import re
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import CAMPO_DO_PILAR, Pilar, User
from accounts.templatetags.escolhas import DETALHES
from accounts.templatetags.navegacao import DESTINO_DO_PILAR
from accounts.tests import STEP1, STEP2, STEP3, STEP4, STEP5, step_url

RAIZ = Path(__file__).resolve().parent.parent

#: O padrão oficial, escrito aqui à mão de propósito.
#:
#: Ler de `Pilar.label` faria o esperado sair da mesma fonte que o obtido, e
#: renomear um pilar moveria os dois lados juntos — o teste ficaria verde
#: enquanto a interface mudasse de vocabulário sozinha. É a tautologia que uma
#: revisão adversarial já pegou uma vez neste repositório.
OFICIAIS = {
    "dieta": "Alimentação",
    "treino": "Treino",
    "corrida": "Corrida",
    "hidratacao": "Hidratação",
    "progresso": "Progresso",
}

#: Nomes que este produto NÃO usa mais para nomear uma área.
APOSENTADOS = ("Dieta", "Musculação", "Evolução")


class OPadraoOficialTests(TestCase):
    def test_os_cinco_labels_sao_os_oficiais(self):
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertEqual(pilar.label, OFICIAIS[pilar.value])

    def test_a_lista_oficial_cobre_exatamente_os_cinco_pilares(self):
        """Controle da tabela acima: um sexto pilar sem nome oficial, ou um
        nome oficial órfão, para o teste de cima de servir."""
        self.assertEqual(set(OFICIAIS), {p.value for p in Pilar})

    def test_o_titulo_de_tela_nao_e_uma_segunda_fonte(self):
        """`DETALHES` guarda ícone e frase de apoio; o NOME ele lê de `Pilar`.

        Enquanto os dois eram escritos à mão, os dois divergiram — foi assim
        que "Musculação" sobreviveu no cartão do onboarding enquanto a barra
        dizia "Treino".
        """
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertEqual(DETALHES[pilar.value][1], pilar.label)

    def test_a_frase_de_apoio_continua_propria(self):
        """O outro lado: `DETALHES` não virou um espelho de `Pilar`. Ele
        continua carregando o que o modelo não tem — ícone e promessa."""
        for pilar in Pilar:
            icone, titulo, apoio = DETALHES[pilar.value][:3]
            with self.subTest(pilar=pilar.value):
                self.assertTrue(icone)
                self.assertNotEqual(apoio, titulo)
                self.assertGreater(len(apoio), len(titulo))


class BaseDaNomenclatura(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="nome@exemplo.com", interesses=("dieta",), principal="dieta"):
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        self.client.post(
            step_url(6),
            {"interesses": list(interesses), "prioridade": principal},
        )
        return user

    def rotulos(self, html, classe):
        """Os rótulos visíveis de uma navegação, sem o SVG do ícone."""
        achados = []
        for corpo in re.findall(
            r'<a class="%s[^"]*"[^>]*>(.*?)</a>' % classe, html, re.S
        ):
            texto = re.sub(r"<[^>]+>", " ", corpo)
            achados.append(" ".join(texto.split()))
        return achados


class ASBarrasEOMapaFalamAMesmaLinguaTests(BaseDaNomenclatura):
    def test_a_barra_de_baixo_usa_os_nomes_oficiais(self):
        self.pessoa("barra@exemplo.com")

        html = self.client.get(reverse("plans:today")).content.decode()
        abas = self.rotulos(html, "tabbar__item")

        self.assertEqual(abas, ["Alimentação", "Treino", "Progresso", "Perfil"])

    def test_a_barra_de_cima_usa_os_mesmos_nomes_da_de_baixo(self):
        """As duas aparecem na mesma página; divergir aqui é divergir na cara
        de quem redimensiona a janela."""
        self.pessoa("cima@exemplo.com")

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertEqual(
            self.rotulos(html, "app-bar__link"),
            self.rotulos(html, "tabbar__item"),
        )

    def test_o_mapa_e_a_barra_nomeiam_o_mesmo_destino_igual(self):
        """O contrato central desta campanha.

        Para cada item da barra, se o mapa leva ao MESMO endereço, o nome tem
        de ser o mesmo. É a comparação por DESTINO, e não por posição: uma
        reordenação de qualquer das duas não pode fazer este teste mentir.
        """
        self.pessoa("mapa@exemplo.com")
        html = self.client.get(reverse("plans:today")).content.decode()

        def por_destino(trecho, classe, dentro=None):
            """destino -> nome visível, sem o texto de apoio.

            O item do mapa carrega nome E frase de apoio dentro do mesmo `<a>`;
            comparar o `<a>` inteiro faria o teste acusar divergência entre
            "Treino" e "Treino A ficha da semana...". `dentro` recorta o
            elemento que carrega só o nome.
            """
            pares = {}
            for m in re.finditer(
                r'<a class="%s[^"]*"[^>]*?href="([^"]+)"[^>]*>(.*?)</a>' % classe,
                trecho,
                re.S,
            ):
                corpo = m.group(2)
                if dentro:
                    achado = re.search(
                        r'<span class="%s"[^>]*>(.*?)</span>' % dentro, corpo, re.S
                    )
                    corpo = achado.group(1) if achado else ""
                texto = re.sub(r"<[^>]+>", " ", corpo)
                pares[m.group(1)] = " ".join(texto.split()).replace(" principal", "")
            return pares

        barra = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]
        mapa = html.split('class="mapa"', 1)[1].split("</details>", 1)[0]

        da_barra = por_destino(barra, "tabbar__item")
        do_mapa = por_destino(mapa, "mapa__area", dentro="mapa__nome")

        comuns = set(da_barra) & set(do_mapa)
        # Controle positivo: sem destino em comum a comparação abaixo é vazia
        # e passaria sem medir nada. São três — Alimentação, Treino, Progresso.
        self.assertEqual(len(comuns), 3, (da_barra, do_mapa))
        for destino in sorted(comuns):
            with self.subTest(destino=destino):
                self.assertEqual(da_barra[destino], do_mapa[destino])

    def test_nenhum_nome_aposentado_sobrou_na_navegacao(self):
        """A régua é a NAVEGAÇÃO, e não a página: "dieta" e "evolução" seguem
        livres em texto educativo, que é onde elas são a palavra e não o
        rótulo."""
        self.pessoa("aposentado@exemplo.com")
        html = self.client.get(reverse("plans:today")).content.decode()

        barra = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]
        mapa = html.split('class="mapa"', 1)[1].split("</details>", 1)[0]

        for velho in APOSENTADOS:
            for onde, trecho in (("barra", barra), ("mapa", mapa)):
                with self.subTest(nome=velho, onde=onde):
                    self.assertNotIn(velho, trecho)


class OOnboardingEOPerfilConcordamTests(BaseDaNomenclatura):
    def test_os_cartoes_do_passo_das_areas_usam_os_nomes_oficiais(self):
        user = User.objects.create_user(
            email="wizard@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)

        html = self.client.get(step_url(6)).content.decode()
        # Os CARTÕES, e não a página: o passo 6 declara `sem_tabbar`, que
        # desliga o mapa e a barra de baixo — mas NÃO a barra de cima, que
        # continua imprimindo "Alimentação", "Treino" e "Progresso". A versão
        # anterior varria o HTML inteiro, e três dos cinco subTests passavam
        # por causa dela: esvaziar o título do cartão os deixaria verdes. Uma
        # revisão adversarial mediu.
        cartoes = html.split('class="choice-list', 1)[1].split("</ul>", 1)[0]

        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn(OFICIAIS[pilar.value], cartoes)
        for velho in APOSENTADOS:
            if velho in OFICIAIS.values():
                continue
            with self.subTest(nome=velho):
                self.assertNotIn(velho, cartoes)

    def test_o_perfil_repete_o_nome_que_o_onboarding_ofereceu(self):
        """A pessoa escolheu uma palavra; o Perfil tem de devolver a MESMA."""
        self.pessoa("perfil@exemplo.com", ("treino", "progresso"), "progresso")

        html = self.client.get(reverse("accounts:profile")).content.decode()
        cartao = html.split("Suas áreas", 1)[1].split("</section>", 1)[0]

        self.assertIn("Treino", cartao)
        self.assertIn("Progresso", cartao)
        self.assertNotIn("Musculação", cartao)
        self.assertNotIn("Evolução", cartao)


class AGestaoFalaALinguaDoProdutoTests(TestCase):
    """O painel monta as listas a partir de `Pilar.choices`, então ele segue a
    fonte por construção. O teste existe para o dia em que alguém escrever os
    rótulos à mão ali — que é como a divergência começou na barra."""

    @classmethod
    def setUpTestData(cls):
        from accounts import papeis

        papeis.sincronizar_papeis()

    def test_o_painel_usa_os_nomes_oficiais(self):
        from django.contrib.auth.models import Group

        from accounts import papeis

        operador = User.objects.create_user(
            email="gestor-nome@exemplo.com", password="senha-bem-forte-123",
            is_staff=True,
        )
        operador.groups.add(Group.objects.get(name=papeis.ADMINISTRADORES))
        self.client.force_login(operador)

        # Sem NINGUÉM declarado o cartão mostra o estado vazio, e o teste
        # mediria a ausência das cinco palavras em vez do vocabulário delas.
        from accounts.models import Profile

        declarante = User.objects.create_user(
            email="declarou@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=declarante, sex="M", birth_date="1995-04-12", height_cm=178,
            prioridade=Pilar.PROGRESSO,
            **{campo: True for campo in CAMPO_DO_PILAR.values()},
        )

        html = self.client.get("/gestao/").content.decode()
        cartao = html.split("O que as pessoas vieram cuidar", 1)[1]
        cartao = cartao.split("</section>", 1)[0]

        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.assertIn(OFICIAIS[pilar.value], cartao)
        for velho in ("Musculação", "Evolução"):
            with self.subTest(nome=velho):
                self.assertNotIn(velho, cartao)


class ORenomearNaoMoveNadaTests(TestCase):
    """O nome é de TELA. Nada do que é identificador pode ter andado junto.

    É a metade da campanha que ninguém vê e que quebraria tudo: os `value` de
    `Pilar` estão em banco, no `CheckConstraint`, nas chaves de
    `CAMPO_DO_PILAR` e no `name` dos campos do formulário.
    """

    def test_os_identificadores_internos_continuam_os_mesmos(self):
        self.assertEqual(
            [p.value for p in Pilar],
            ["dieta", "treino", "corrida", "hidratacao", "progresso"],
        )

    def test_os_campos_do_banco_continuam_os_mesmos(self):
        self.assertEqual(
            list(CAMPO_DO_PILAR.values()),
            [
                "interesse_dieta",
                "interesse_treino",
                "interesse_corrida",
                "interesse_hidratacao",
                "interesse_progresso",
            ],
        )

    def test_o_destino_de_cada_area_continua_o_mesmo(self):
        """Renomear não pode mudar para onde a área leva — foi por isso que a
        troca não tocou em `DESTINO_DO_PILAR`."""
        self.assertEqual(
            {p: rota for p, (rota, _nav) in DESTINO_DO_PILAR.items()},
            {
                Pilar.DIETA: "plans:today",
                Pilar.TREINO: "workouts:routine",
                Pilar.CORRIDA: "workouts:corridas",
                Pilar.HIDRATACAO: "plans:hydration",
                Pilar.PROGRESSO: "plans:history",
            },
        )

    def test_as_chaves_de_nav_continuam_as_mesmas(self):
        self.assertEqual(
            [nav for _rota, nav in DESTINO_DO_PILAR.values()],
            ["today", "workout", "running", "hydration", "history"],
        )


class ANomenclaturaNaoProibePalavraTests(TestCase):
    """O contrapeso, e ele é deliberado.

    Um teste que varresse o HTML atrás de "dieta" transformaria a padronização
    numa proibição de vocabulário: o app fala de dieta o tempo todo — "sua
    dieta calculada", "recalcula a dieta", "não é prescrição". Estas palavras
    continuam livres onde são palavras.
    """

    def test_a_descricao_do_app_continua_podendo_dizer_dieta(self):
        conteudo = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")

        self.assertIn("Sua dieta calculada", conteudo)

    def test_o_texto_educativo_da_hidratacao_continua_inteiro(self):
        conteudo = (
            RAIZ / "templates" / "plans" / "hydration.html"
        ).read_text(encoding="utf-8")

        # Trecho que cabe numa linha do template: o HTML cru quebra a frase.
        self.assertIn("uma regra prática para adulto ativo", conteudo)


class ACapaDoDemoNaoFicaParaTrasTests(TestCase):
    """A capa do demo escreve os cinco nomes à mão, e nada guardava isso.

    `demo.views.AREAS` é uma lista de `(destino, nome, descrição)` montada no
    Python — ela não lê `Pilar.label`, e não pode ler: metade das entradas não
    é pilar (Hoje, Lista de compras, Perfil). Nesta campanha ela foi corrigida
    por edição manual, e uma revisão adversarial apontou o buraco: renomear um
    pilar amanhã deixa a capa com o nome velho, em silêncio, na tela que o
    comentário do próprio arquivo chama de primeira coisa que um avaliador vê.

    A régua não exige que a capa liste os cinco — ela lista oito destinos de
    propósito. Exige que, QUANDO ela nomear uma área, o nome seja o oficial.
    """

    def nomes_da_capa(self):
        from demo.views import AREAS

        return [nome for _destino, nome, _descricao in AREAS]

    def test_a_capa_nao_usa_nome_aposentado(self):
        nomes = self.nomes_da_capa()

        # Controle positivo: sem entradas, o laço abaixo não mediria nada.
        self.assertGreater(len(nomes), 5, nomes)
        for velho in APOSENTADOS:
            with self.subTest(nome=velho):
                self.assertNotIn(velho, nomes)

    def test_os_cinco_pilares_da_capa_usam_o_label_oficial(self):
        """Cada pilar que a capa mostra tem de chamar-se como o resto do app.

        Comparado com `Pilar.label` e não com a tabela `OFICIAIS`: aqui a
        pergunta é "a capa acompanha a fonte?", e não "a fonte está certa?" —
        essa segunda já tem teste próprio em `OPadraoOficialTests`.
        """
        nomes = set(self.nomes_da_capa())
        rotulos = {p.label for p in Pilar}

        presentes = nomes & rotulos
        self.assertEqual(
            presentes,
            rotulos,
            "a capa do demo deixou de nomear algum pilar com o rótulo oficial",
        )
