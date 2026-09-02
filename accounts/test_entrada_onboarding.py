"""A porta de entrada do app nao pode devolver a pessoa para quem a mandou.

Existem DUAS reguas de "onboarding completo" neste projeto, e elas nao sao a
mesma coisa:

    Profile.onboarding_complete .... contador: `onboarding_step >= DONE`
    services.build_inputs ......... o que o MOTOR precisa para calcular

A segunda e mais exigente: alem do contador, ela exige peso registrado. Um
perfil pode satisfazer a primeira e falhar na segunda — passo 6, nenhuma
pesagem —, e ai as duas telas se empurram:

    /                  -> build_inputs recusa -> redirect para o onboarding
    /conta/onboarding/ -> contador diz completo -> redirect para /
    /                  -> ...

Loop infinito. A pessoa nao chega ao app e nao chega ao cadastro; a tela fica
branca e nao ha mensagem nenhuma explicando. Reproduzido no navegador, contra o
banco local, com uma conta em passo 6 e zero pesagens.

O contrato que estes testes fixam: quem decide se da para entrar no app e o
MOTOR. A tela de entrada do onboarding traduz a recusa dele para o passo que
resolve — nunca devolve para a tela que acabou de recusar.
"""
from django.test import TestCase
from django.test.client import RedirectCycleError

from accounts.models import Profile, WeightEntry
from plans import services
from plans.tests import create_complete_user


class EntradaDoOnboardingNaoFazLoopTests(TestCase):
    def setUp(self):
        self.pessoa = create_complete_user(email="loop@exemplo.com")
        self.client.force_login(self.pessoa)

    def _sem_peso(self):
        """Passo no fim, nenhuma pesagem: o estado que trava."""
        WeightEntry.objects.filter(user=self.pessoa).delete()
        perfil = Profile.objects.get(user=self.pessoa)
        self.assertTrue(perfil.onboarding_complete, "controle: o contador diz completo")
        self.assertIsNone(perfil.current_weight, "controle: o motor nao tem peso")
        return perfil

    def test_o_motor_e_a_tela_discordam_e_isso_e_o_bug(self):
        """O controle positivo do diagnostico.

        Sem esta afirmacao, os testes abaixo poderiam passar porque o estado
        nunca chegou a ser o problematico — e eu teria "provado" a correcao de
        um bug que o fixture nao reproduz.
        """
        perfil = self._sem_peso()

        self.assertTrue(perfil.onboarding_complete)
        with self.assertRaises(services.IncompleteProfile):
            services.build_inputs(self.pessoa)

    def test_hoje_nao_entra_em_loop_quando_falta_peso(self):
        """`RedirectCycleError` e o que o loop produz. Se ele voltar, o teste
        nao passa em silencio: ele estoura."""
        self._sem_peso()

        try:
            resposta = self.client.get("/", follow=True)
        except RedirectCycleError:
            self.fail("`/` e o onboarding se empurram: loop de redirecionamento")

        self.assertEqual(resposta.status_code, 200)

    def test_a_pessoa_para_no_passo_que_resolve(self):
        """Nao basta nao travar: tem que parar onde da para consertar."""
        self._sem_peso()

        resposta = self.client.get("/", follow=True)

        destino = resposta.redirect_chain[-1][0]
        self.assertIn("/conta/onboarding/1/", destino, resposta.redirect_chain)

    def test_a_tela_diz_o_que_falta(self):
        """Chegar no passo 1 sem explicacao pareceria o app se perdendo.

        A frase INTEIRA, e nao a palavra "peso": o passo 1 tem um campo de
        peso, entao procurar so a palavra passaria pelo rotulo do formulario
        mesmo sem mensagem nenhuma — um teste verde pelo motivo errado.
        """
        self._sem_peso()

        resposta = self.client.get("/", follow=True)

        self.assertContains(
            resposta, "Faltou registrar seu peso para calcularmos a dieta."
        )

    def test_so_uma_mensagem_e_nao_duas_quase_iguais(self):
        """A tela Hoje tambem avisava, e as duas empilhavam."""
        self._sem_peso()

        resposta = self.client.get("/", follow=True)

        self.assertNotContains(resposta, "Faltou completar seu cadastro")

    def test_quem_entra_no_wizard_de_proposito_nao_e_cobrado(self):
        """`/conta/onboarding/` tambem e o "continuar de onde parei"."""
        Profile.objects.filter(user=self.pessoa).update(onboarding_step=3)

        resposta = self.client.get("/conta/onboarding/", follow=True)

        self.assertNotContains(resposta, "Faltou")

    def test_controle_quem_tem_tudo_chega_no_hoje(self):
        """Sem isto, uma correcao que mandasse TODO MUNDO para o passo 1
        passaria nos testes acima como se fosse conserto."""
        resposta = self.client.get("/conta/onboarding/", follow=True)

        self.assertEqual(resposta.redirect_chain[-1][0], "/")
        self.assertEqual(resposta.status_code, 200)

    def test_controle_quem_esta_no_meio_do_wizard_continua_no_wizard(self):
        Profile.objects.filter(user=self.pessoa).update(onboarding_step=3)

        resposta = self.client.get("/conta/onboarding/", follow=True)

        # O passo EXATO, e nao o prefixo: "/conta/onboarding/" tambem casa com
        # a propria tela de entrada, entao o prefixo passaria mesmo se ela
        # tivesse parado de rotear.
        self.assertEqual("/conta/onboarding/3/", resposta.redirect_chain[-1][0])
