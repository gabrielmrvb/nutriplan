"""O painel de gestão: quem entra, o que ele conta, e o que ele não faz.

Três frentes, e a ordem é deliberada. Autorização primeiro — um painel de
negócio errado sobre autorização é um vazamento, não um bug de número. Depois
o significado dos números, que é onde este tipo de tela mente com mais
facilidade. Por último o custo, medido desde a primeira versão em vez de
depois que ficar lento.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts import papeis
from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    ClassificacaoDeConta,
    Goal,
    Profile,
    Sex,
    WeightEntry,
)
from plans.models import HydrationLog, MealLog, NutritionPlan

User = get_user_model()


class BaseDoPainel(TestCase):
    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def pessoa(self, email, **extras):
        return User.objects.create_user(
            email=email, password="senha-bem-forte-123", **extras
        )

    def operador(self, email="gestor@exemplo.com", papel=None):
        quem = self.pessoa(email)
        quem.is_staff = True
        quem.save(update_fields=["is_staff"])
        quem.groups.add(Group.objects.get(name=papel or papeis.ADMINISTRADORES))
        return quem

    def perfil(self, quem, completo=True):
        return Profile.objects.create(
            user=quem,
            sex=Sex.MALE,
            birth_date=date(1995, 4, 12),
            height_cm=178,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
            onboarding_step=ONBOARDING_DONE if completo else 2,
        )


class AcessoAoPainelTests(BaseDoPainel):
    """A chave é a permissão dedicada, e não `is_staff`."""

    ROTAS = ("/gestao/", "/gestao/pessoas/", "/gestao/atividade/")

    def test_administrador_entra(self):
        self.client.force_login(self.operador())

        for rota in self.ROTAS:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)

    def test_suporte_nao_entra(self):
        self.client.force_login(
            self.operador("sup@exemplo.com", papeis.SUPORTE)
        )

        for rota in self.ROTAS:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 403)

    def test_staff_sem_a_permissao_nao_entra(self):
        """O teste que separa a chave do flag: se o painel olhasse `is_staff`,
        este passaria por acidente e a separação seria só uma intenção escrita
        no comentário."""
        avulso = self.pessoa("staff-avulso@exemplo.com")
        avulso.is_staff = True
        avulso.save(update_fields=["is_staff"])
        self.client.force_login(avulso)

        self.assertEqual(self.client.get("/gestao/").status_code, 403)

    def test_quem_tem_a_permissao_entra_mesmo_sem_ser_staff(self):
        """O outro lado da mesma separação. Sem este, "não é `is_staff`"
        continuaria sendo meia prova."""
        sem_staff = self.pessoa("so-permissao@exemplo.com")
        sem_staff.user_permissions.add(
            Permission.objects.get(
                codename="ver_painel_de_gestao", content_type__app_label="accounts"
            )
        )
        self.client.force_login(sem_staff)

        self.assertEqual(self.client.get("/gestao/").status_code, 200)

    def test_usuario_comum_leva_403(self):
        self.client.force_login(self.pessoa("comum@exemplo.com"))

        self.assertEqual(self.client.get("/gestao/").status_code, 403)

    def test_anonimo_vai_para_o_login(self):
        """403 para quem não entrou seria uma tela sem saída: o problema dela é
        sessão, não permissão."""
        resposta = self.client.get("/gestao/")

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("entrar", resposta["Location"])


class NumerosDoPainelTests(BaseDoPainel):
    """Cada número responde a UMA pergunta, e não à parecida do lado."""

    def setUp(self):
        self.client.force_login(self.operador())

    def test_nenhuma_conta_e_classificada_por_adivinhacao(self):
        """A migração não olha e-mail, não olha data, não olha nada. Conta
        antiga nasce sem classificação porque o banco não sabe o que ela é."""
        self.pessoa("qualquer@exemplo.com")

        de_fabrica = User.objects.get(email="qualquer@exemplo.com")

        self.assertEqual(
            de_fabrica.classificacao, ClassificacaoDeConta.NAO_CLASSIFICADA
        )

    def test_o_painel_mostra_quantas_estao_sem_classificacao(self):
        """Esconder esse número deixaria a tela bonita e falsa: sem ele, quem
        lê "3 pessoas" acha que sabemos o que são as outras 49."""
        for i in range(3):
            self.pessoa(f"sem-classe{i}@exemplo.com")

        html = self.client.get("/gestao/").content.decode()

        self.assertIn("Não classificada", html)

    def test_o_peso_do_cadastro_nao_conta_como_engajamento(self):
        """O passo 1 EXIGE o peso. Contá-lo como ação voluntária faria
        "terminou o cadastro" virar "está engajada", e o funil mediria a si
        mesmo."""
        quem = self.pessoa("so-pesou@exemplo.com")
        self.perfil(quem)
        WeightEntry.objects.create(
            user=quem, date=timezone.localdate(), weight_kg=Decimal("80.00")
        )

        from gestao.metricas import numeros_do_painel

        self.assertEqual(numeros_do_painel()["funil"]["com_acao"], 0)

    def test_agua_zerada_nao_conta_como_agua_bebida(self):
        """A linha de hidratação nasce por `get_or_create` quando a tela do dia
        abre. Existir não é ter bebido."""
        quem = self.pessoa("abriu-a-tela@exemplo.com")
        HydrationLog.objects.create(user=quem, date=timezone.localdate(), ml=0)

        from gestao.metricas import numeros_do_painel

        self.assertEqual(numeros_do_painel()["funil"]["com_acao"], 0)

    def test_marcar_refeicao_conta(self):
        """Controle positivo: sem ele, um `com_acao` quebrado que devolvesse
        sempre zero passaria nos dois testes acima como se fosse rigor."""
        quem = self.pessoa("marcou@exemplo.com")
        MealLog.objects.create(
            user=quem, date=timezone.localdate(), status="eaten"
        )

        from gestao.metricas import numeros_do_painel

        self.assertEqual(numeros_do_painel()["funil"]["com_acao"], 1)

    def test_nenhuma_metrica_e_rotulada_como_retencao(self):
        """Retenção é de coorte: pega quem entrou junto e mede quem voltou.

        O risco não é a palavra aparecer — a explicação da tela diz, de
        propósito, que aquilo NÃO é retenção. O risco é um RÓTULO de métrica
        dizer "retenção", porque rótulo é o que a pessoa lê ao bater o olho, e
        a partir dali ela compara o número com referência de outra coisa.

        Por isso o teste lê os títulos e os termos da lista de dados, e não o
        HTML inteiro. A primeira versão lia tudo e tentava descontar a frase da
        explicação com um `replace` — que removia uma ocorrência de duas e
        falhava por um motivo que não tinha nada a ver com o risco.
        """
        import re

        html = self.client.get("/gestao/").content.decode()
        rotulos = re.findall(r"<(?:h1|h2|dt)[^>]*>(.*?)</(?:h1|h2|dt)>", html, re.S)

        self.assertTrue(rotulos)
        for rotulo in rotulos:
            with self.subTest(rotulo=rotulo.strip()[:50]):
                self.assertNotIn("reten", rotulo.lower())
                self.assertNotIn("d7", rotulo.lower())
                self.assertNotIn("churn", rotulo.lower())

    def test_atividade_conta_pessoas_e_nao_registros(self):
        """Quem marca cinco refeições continua sendo uma pessoa. Contar linhas
        faria o dia dela parecer um dia movimentado."""
        quem = self.pessoa("aplicada@exemplo.com")
        hoje = timezone.localdate()
        for i in range(5):
            MealLog.objects.create(
                user=quem, date=hoje, status="eaten", slot_name=f"refeicao {i}"
            )

        resposta = self.client.get("/gestao/atividade/")

        linha = [d for d in resposta.context["dias"] if d[0] == hoje]
        self.assertEqual(linha[0][1][0], 1)

    def test_o_funil_conta_quem_tem_plano(self):
        quem = self.pessoa("com-plano@exemplo.com")
        self.perfil(quem)
        NutritionPlan.objects.create(
            user=quem, weight_kg=Decimal("80"), height_cm=178, age_years=30,
            sex=Sex.MALE, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
            bmr_kcal=1700, tdee_kcal=2300, target_kcal=2600,
            protein_g=160, carb_g=300, fat_g=70,
        )

        from gestao.metricas import numeros_do_painel

        numeros = numeros_do_painel()
        self.assertEqual(numeros["funil"]["com_plano"], 1)
        self.assertEqual(numeros["onboarding_completo"], 1)


class CustoDoPainelTests(BaseDoPainel):
    """O custo não pode crescer com o número de contas.

    Medido agora, e não quando a tela ficar lenta: o padrão ingênuo aqui —
    uma consulta por conta para saber se ela tem plano — funciona com 52
    contas e derruba a página com cinco mil. E o painel é justamente a tela
    que alguém abre quando o produto cresceu.
    """

    def setUp(self):
        self.client.force_login(self.operador())

    def _povoar(self, quantas, prefixo):
        hoje = timezone.localdate()
        for i in range(quantas):
            quem = self.pessoa(f"{prefixo}{i:03d}@exemplo.com")
            self.perfil(quem)
            MealLog.objects.create(user=quem, date=hoje, status="eaten")
            NutritionPlan.objects.create(
                user=quem, weight_kg=Decimal("80"), height_cm=178, age_years=30,
                sex=Sex.MALE, activity_level=ActivityLevel.LIGHT, goal=Goal.BULK,
                bmr_kcal=1700, tdee_kcal=2300, target_kcal=2600,
                protein_g=160, carb_g=300, fat_g=70,
            )

    def _medir(self, rota):
        # Uma visita para aquecer o cache de ContentType, e só então a medição:
        # senão a primeira sai mais cara por um motivo que não tem nada a ver
        # com o volume.
        self.client.get(rota)
        with CaptureQueriesContext(connection) as consultas:
            self.client.get(rota)
        return len(consultas)

    def test_o_painel_custa_o_mesmo_com_dez_e_com_quarenta_contas(self):
        self._povoar(10, "custo-a")
        poucas = self._medir("/gestao/")

        self._povoar(30, "custo-b")
        muitas = self._medir("/gestao/")

        self.assertEqual(poucas, muitas)

    def test_a_lista_de_pessoas_custa_o_mesmo_com_dez_e_com_quarenta(self):
        self._povoar(10, "lista-a")
        poucas = self._medir("/gestao/pessoas/")

        self._povoar(30, "lista-b")
        muitas = self._medir("/gestao/pessoas/")

        self.assertEqual(poucas, muitas)

    def test_a_atividade_custa_o_mesmo_com_dez_e_com_quarenta(self):
        self._povoar(10, "ativ-a")
        poucas = self._medir("/gestao/atividade/")

        self._povoar(30, "ativ-b")
        muitas = self._medir("/gestao/atividade/")

        self.assertEqual(poucas, muitas)

    def test_a_lista_e_paginada(self):
        """Sem paginação a tela funciona com 52 contas e para de funcionar com
        cinco mil — e a hora de descobrir não é quando houver cinco mil."""
        self._povoar(60, "pag")

        resposta = self.client.get("/gestao/pessoas/")

        pagina = resposta.context["pagina"]
        self.assertTrue(pagina.has_other_pages())
        self.assertLessEqual(len(pagina.object_list), 50)


class OPainelNaoFazTests(BaseDoPainel):
    """O que ele deliberadamente não oferece.

    Cada item aqui é uma porta que um painel de negócio abre com facilidade e
    que este não abre: entrar na conta de alguém, baixar a lista inteira, ou
    mostrar o histórico pessoal de peso e de refeição pessoa por pessoa.
    """

    def setUp(self):
        self.client.force_login(self.operador())
        alvo = self.pessoa("privada@exemplo.com")
        self.perfil(alvo)
        WeightEntry.objects.create(
            user=alvo, date=timezone.localdate(), weight_kg=Decimal("81.40")
        )

    def test_nao_oferece_entrar_na_conta_de_ninguem(self):
        html = self.client.get("/gestao/pessoas/").content.decode()

        for pista in ("impersonat", "entrar como", "login-as", "assumir"):
            with self.subTest(pista=pista):
                self.assertNotIn(pista, html.lower())

    def test_nao_oferece_baixar_a_lista(self):
        html = self.client.get("/gestao/pessoas/").content.decode()

        for pista in ("csv", "exportar", "download", "planilha"):
            with self.subTest(pista=pista):
                self.assertNotIn(pista, html.lower())

    def test_nao_mostra_peso_de_ninguem(self):
        """Peso é o dado mais sensível do app e não responde nenhuma pergunta
        de negócio. A pergunta agregada — quantas pessoas registram — está no
        painel; a série de alguém não está em lugar nenhum daqui."""
        for rota in ("/gestao/", "/gestao/pessoas/", "/gestao/atividade/"):
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertNotIn("81,40", html)
                self.assertNotIn("81.40", html)
