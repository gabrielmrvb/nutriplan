"""FASE 1 — a tela para de afirmar um resultado que ainda não foi calculado.

O DEFEITO, dito com precisão. `energy_balance` responde uma pergunta sobre o
PLANO: quanto a meta fica abaixo (ou acima) do gasto. É um número fixo, que não
depende de registro nenhum — quem escolheu Manutenção tem meta igual ao gasto e
recebe `kind == "balance"`, cujo texto é "Sem déficit nem superávit".

Só que essa linha é renderizada DENTRO de `today-hero__facts`, espremida entre
duas frases que são inequivocamente sobre HOJE: "faltam 2.055 kcal" e
"0/5 refeições". Quem abre o app de manhã, sem nada registrado, lê as três em
sequência e conclui a única coisa possível: que o app está dizendo que o dia
fechou em zero a zero. O app não sabe disso. Ninguém comeu ainda.

A CORREÇÃO É DE COMUNICAÇÃO, NÃO DE CÁLCULO. `energy_balance` continua exata e
intocada — os testes dela seguem valendo em `EnergyBalanceTests`. O que muda é
que, enquanto não houver registro nenhum, a linha deixa de afirmar o saldo e
passa a dizer o que fazer para tê-lo.

E A PORTA É `marked`, NÃO `consumed_kcal`. Quem marcou "Pulei" nas cinco
refeições consumiu zero caloria e REGISTROU o dia inteiro; mandar essa pessoa
"registrar suas refeições" seria pedir o que ela acabou de fazer. Registro
ausente e consumo zero são estados diferentes, e confundi-los é o mesmo erro
que a Fase 4 proíbe no Progresso.
"""
import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Goal

from . import services
from .models import MealLog, MealStatus, NutritionPlan
from .tests import create_complete_user


def com_plano(**kwargs):
    """Pessoa com onboarding completo E plano ativo já materializado.

    `create_complete_user` para no perfil: o plano nasce quando a tela pede,
    via `sync_active_plan`. Um teste que quer o SLOT antes de abrir a tela
    precisa pedir o plano na mão, senão recebe `None` e falha por fixture —
    ruído que esconderia o defeito que ele veio provar.
    """
    pessoa = create_complete_user(**kwargs)
    services.sync_active_plan(pessoa)
    return pessoa

#: A frase que a tela mostra enquanto o dia não tem registro nenhum.
CONVITE = "Registre suas refeições para acompanhar o saldo do dia."

#: As três afirmações de saldo que não podem aparecer num dia em branco.
AFIRMACOES = ("Sem déficit nem superávit", "Déficit", "Superávit")


def linha_do_saldo(resposta):
    """O texto DENTRO de `.today-hero__balance`, e só ele.

    Varrer a página inteira atrás de "déficit" não mede o que este arquivo
    quer: a tela explica o plano mais abaixo, num `<details>`, e lá as
    palavras são legítimas — "o déficit cheio ficaria abaixo do mínimo
    seguro" é justamente o texto que ensina o conceito. Uma asserção sobre a
    página toda casaria com essa explicação e reprovaria uma tela correta.

    É a armadilha que o `CLAUDE.md` registra como recorrente aqui: o seletor e
    o texto procurado são a mesma string em dois lugares. A âncora certa é a
    CLASSE do elemento que faz a afirmação.
    """
    html = resposta.content.decode("utf-8")
    marca = 'class="today-hero__balance'
    inicio = html.find(marca)
    if inicio < 0:
        return ""
    fim = html.find("</p>", inicio)
    return re.sub(r"<[^>]+>", " ", html[inicio:fim])


class OSaldoNaoAfirmaResultadoDeDiaEmBrancoTests(TestCase):
    def setUp(self):
        # Manutenção de propósito: é o objetivo que produz `kind == "balance"`,
        # a frase exata da queixa. Os outros objetivos entram nos testes de
        # baixo, para a correção não virar um remendo de um caso só.
        self.pessoa = com_plano(goal=Goal.MAINTAIN)
        self.client.force_login(self.pessoa)

    def _tela(self):
        return self.client.get(reverse("plans:today"))

    def _registrar(self, status=MealStatus.DONE, kcal=600):
        """Uma refeição registrada HOJE, presa ao plano ativo.

        Presa ao slot de propósito: `day_summary` filtra por `slot__plan`, e um
        log solto não somaria — o teste passaria por não medir nada.
        """
        plano = NutritionPlan.objects.filter(user=self.pessoa, is_active=True).first()
        slot = plano.slots.first()
        return MealLog.objects.create(
            user=self.pessoa,
            slot=slot,
            date=timezone.localdate(),
            status=status,
            kcal=kcal,
            slot_name=slot.name,
        )

    # ------------------------------------------------------------------ zero
    def test_sem_registro_a_tela_nao_afirma_saldo_nenhum(self):
        linha = linha_do_saldo(self._tela())

        self.assertNotEqual(linha, "", "a linha do saldo sumiu da tela")
        for afirmacao in AFIRMACOES:
            with self.subTest(afirmacao=afirmacao):
                self.assertNotIn(afirmacao, linha)

    def test_sem_registro_a_tela_diz_o_que_fazer(self):
        """Estado vazio é convite. Sumir com a linha deixaria um buraco."""
        self.assertContains(self._tela(), CONVITE)

    def test_o_contexto_marca_o_dia_em_branco(self):
        """A decisão é do servidor, e tem nome.

        Deixar o template comparar `summary.marked == 0` espalharia a regra
        pelo HTML — e o HTML não é onde se lê uma regra de produto.
        """
        self.assertFalse(self._tela().context["saldo_do_dia_ja_conta"])

    # --------------------------------------------------------------- parcial
    def test_uma_refeicao_registrada_ja_devolve_o_saldo(self):
        self._registrar()

        resposta = self._tela()

        self.assertTrue(resposta.context["saldo_do_dia_ja_conta"])
        self.assertContains(resposta, "Sem déficit nem superávit")
        self.assertNotContains(resposta, CONVITE)

    def test_pular_a_refeicao_e_registrar_e_nao_e_dia_em_branco(self):
        """"Registrou zero" não é "não registrou".

        Quem marcou "Pulei" respondeu ao app. Pedir a essa pessoa que registre
        as refeições seria devolver a ela a tarefa que ela cumpriu — e é a
        mesma distinção que o Progresso é obrigado a fazer.
        """
        self._registrar(status=MealStatus.SKIPPED, kcal=0)

        resposta = self._tela()

        self.assertTrue(resposta.context["saldo_do_dia_ja_conta"])
        self.assertNotContains(resposta, CONVITE)

    def test_comer_fora_do_plano_tambem_e_registro(self):
        self._registrar(status=MealStatus.OFF_PLAN, kcal=800)

        self.assertTrue(self._tela().context["saldo_do_dia_ja_conta"])

    def test_refeicao_pendente_nao_conta_como_registro(self):
        """`PENDING` é a linha que o app cria sozinho, não uma resposta."""
        self._registrar(status=MealStatus.PENDING, kcal=0)

        resposta = self._tela()

        self.assertFalse(resposta.context["saldo_do_dia_ja_conta"])
        self.assertContains(resposta, CONVITE)

    def test_registro_de_ontem_nao_desbloqueia_o_saldo_de_hoje(self):
        """O saldo é do DIA. Ontem não responde por hoje."""
        log = self._registrar()
        log.date = timezone.localdate() - timedelta(days=1)
        log.save(update_fields=["date"])

        resposta = self._tela()

        self.assertFalse(resposta.context["saldo_do_dia_ja_conta"])
        self.assertContains(resposta, CONVITE)


class OSaldoPreservadoValeParaTodosOsObjetivosTests(TestCase):
    """A correção não pode valer só para Manutenção.

    A queixa citava "Sem déficit nem superávit", que é o caso da Manutenção.
    Corrigir só ele deixaria Emagrecer e Ganhar massa afirmando "Déficit
    −513 kcal/dia" num dia sem uma única refeição registrada — o mesmo defeito,
    com outro texto.
    """

    def _com(self, goal, email):
        pessoa = com_plano(email=email, goal=goal)
        self.client.force_login(pessoa)
        return pessoa

    def test_nenhum_objetivo_afirma_saldo_com_o_dia_em_branco(self):
        for goal in Goal.values:
            with self.subTest(goal=goal):
                self._com(goal, f"branco-{goal}@exemplo.com")

                resposta = self.client.get(reverse("plans:today"))

                self.assertContains(resposta, CONVITE)
                linha = linha_do_saldo(resposta)
                for afirmacao in AFIRMACOES:
                    self.assertNotIn(afirmacao, linha)

    def test_todo_objetivo_recupera_o_saldo_depois_do_primeiro_registro(self):
        for goal in Goal.values:
            with self.subTest(goal=goal):
                pessoa = self._com(goal, f"cheio-{goal}@exemplo.com")
                plano = NutritionPlan.objects.filter(user=pessoa, is_active=True).first()
                slot = plano.slots.first()
                MealLog.objects.create(
                    user=pessoa, slot=slot, date=timezone.localdate(),
                    status=MealStatus.DONE, kcal=500, slot_name=slot.name,
                )

                resposta = self.client.get(reverse("plans:today"))

                self.assertNotContains(resposta, CONVITE)
                # A linha volta a existir, e diz alguma das quatro coisas que
                # `energy_balance` sabe dizer. Qual delas é decisão do motor,
                # e os testes dele já a prendem.
                self.assertContains(resposta, "today-hero__balance")


class OMotorDeSaldoNaoFoiTocadoTests(TestCase):
    """A Fase 1 é de TELA. Se ela mexeu no cálculo, este teste cai.

    Sem isto, "a tela parou de mentir" poderia ter sido obtido zerando o
    número — que consertaria a frase destruindo a informação.
    """

    def test_o_calculo_do_plano_independe_de_registro(self):
        from plans import views

        pessoa = com_plano(goal=Goal.CUT, email="motor@exemplo.com")
        plano = NutritionPlan.objects.filter(user=pessoa, is_active=True).first()

        antes = views.energy_balance(plano)
        slot = plano.slots.first()
        MealLog.objects.create(
            user=pessoa, slot=slot, date=timezone.localdate(),
            status=MealStatus.DONE, kcal=700, slot_name=slot.name,
        )
        depois = views.energy_balance(plano)

        self.assertEqual(antes, depois)
        self.assertEqual(antes["kind"], "deficit")
