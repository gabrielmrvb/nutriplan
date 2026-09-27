"""A etapa 2 não responde no lugar de ninguém — o item 5 da missão "quem
entra não desiste" (26/09/2026).

Três coisas que a tela fazia e não devia, as três medidas nas personas:

1. **o equipamento abria MARCADO em "academia completa"**, porque o campo do
   perfil nascia com esse valor. Quem passasse batido saía declarando um
   lugar de treino que não escolheu — e desde 24/09 o campo é obrigatório
   para quem faz musculação, o que torna a marca prévia uma contradição: a
   tela exige a resposta e já a dá;
2. **"Quantos grupos musculares por dia?" era perguntado a quem nunca
   montou um treino** (achado #13). Para o iniciante quem decide é o motor —
   corpo inteiro em casa, divisão por frequência na academia —, então a
   pergunta não tem consequência e some;
3. o aceite dos Termos precisa ser a ÚLTIMA coisa antes de "Criar conta":
   ler a frase, marcar, criar. Este arquivo prende a ordem, que hoje já é
   essa — é uma régua contra a regressão, não uma mudança.
"""
import re

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Equipamento, Experiencia, Profile, User

ETAPA1 = {
    "sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82,4",
    "termos": "on", "saude": "on", "transferencia": "on",
}


def etapa(n):
    return reverse("accounts:onboarding_step", kwargs={"step": n})


def _campo(html, nome):
    """As tags `<input>` de um campo de rádio, na ordem da tela."""
    return re.findall(r"<input[^>]*name=\"%s\"[^>]*>" % nome, html)


class ATelaNaoRespondePelaPessoaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(
            email="etapa2@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)

    def test_o_equipamento_abre_sem_nada_marcado(self):
        html = self.client.get(etapa(2)).content.decode()
        opcoes = _campo(html, "equipamento")
        self.assertTrue(opcoes, "a etapa 2 deixou de perguntar o equipamento")
        marcadas = [o for o in opcoes if "checked" in o]
        self.assertFalse(
            marcadas, "a tela abriu com uma resposta que ninguém deu: %s" % marcadas
        )

    def test_quem_ja_respondeu_reabre_com_a_resposta(self):
        """CONTROLE POSITIVO: a marca sumiu de quem não respondeu, e não do
        campo. Quem volta para trocar o equipamento vê o que tinha."""
        perfil = Profile.objects.get(user=self.user)
        perfil.equipamento = Equipamento.PESO_CORPORAL
        perfil.save(update_fields=["equipamento"])
        html = self.client.get(etapa(2)).content.decode()
        marcadas = [o for o in _campo(html, "equipamento") if "checked" in o]
        self.assertEqual(len(marcadas), 1, marcadas)
        self.assertIn('value="peso_corporal"', marcadas[0])

    def test_o_nivel_tambem_continua_sem_marca(self):
        """A experiência já nascia assim desde 17/09/2026, e é a régua que o
        equipamento passou a seguir — o teste fica para as duas andarem
        juntas."""
        html = self.client.get(etapa(2)).content.decode()
        self.assertFalse([o for o in _campo(html, "experiencia") if "checked" in o])


class ADivisaoEPerguntaDeQuemJaTreinaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _abrir(self, nivel):
        self.user = User.objects.create_user(
            email="divisao-%s@exemplo.com" % nivel, password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)
        perfil = Profile.objects.get(user=self.user)
        perfil.experiencia = nivel
        perfil.save(update_fields=["experiencia"])
        for weekday in (0, 2, 4):
            self.user.training_days.create(weekday=weekday, duration_min=60)
        return self.client.get(etapa(2))

    def _bloco_visivel(self, html):
        """O bloco da divisão existe E não está `hidden`.

        Procurar só a pergunta acharia o `<div>` escondido — a tela o mantém
        no HTML para quem envia sem JavaScript.
        """
        achado = re.search(r"<div class=\"revela\" data-revela-divisao[^>]*>", html)
        if not achado:
            return False
        return "hidden" not in achado.group(0)

    def test_quem_esta_comecando_nao_ve_a_pergunta(self):
        resposta = self._abrir(Experiencia.INICIANTE)
        self.assertFalse(resposta.context["mostrar_divisao"])
        self.assertFalse(self._bloco_visivel(resposta.content.decode()))

    def test_quem_ja_treina_ve(self):
        """CONTROLE POSITIVO: a pergunta some para quem começa, e não da
        tela."""
        resposta = self._abrir(Experiencia.INTERMEDIARIO)
        self.assertTrue(resposta.context["mostrar_divisao"])
        self.assertTrue(self._bloco_visivel(resposta.content.decode()))

    def test_o_envio_de_quem_comeca_passa_sem_a_divisao(self):
        """A pergunta que não é feita não pode ser exigida no envio."""
        self._abrir(Experiencia.INICIANTE)
        resposta = self.client.post(etapa(2), {
            "goal": "cut", "activity_level": "light",
            "experiencia": Experiencia.INICIANTE,
            "equipamento": Equipamento.PESO_CORPORAL,
            "weekdays": ["0", "2", "4"], "musculacao": "sim",
            "wake_time": "07:00", "sleep_time": "23:30",
        })
        self.assertEqual(resposta.status_code, 302, getattr(resposta, "context", None))


class OAceiteVemLogoAcimaDoBotaoTests(TestCase):
    """Ler, marcar, criar — nessa ordem e sem nada no meio."""

    def test_a_caixa_dos_termos_e_a_ultima_coisa_antes_de_criar_conta(self):
        html = self.client.get(reverse("accounts:signup")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        aceite = corpo.rindex('name="termos"')
        # O BOTÃO POR EXPRESSÃO, tolerante a quebra de linha dentro da tag
        # (revisão do PR #162): `index(">Criar conta<")` exigia o texto colado
        # nas tags, e reformatar o `<button>` levantava `ValueError` em vez de
        # uma falha que dissesse algo sobre ORDEM.
        achou = re.compile(r">\s*Criar conta\s*<", re.I).search(corpo, aceite)
        self.assertIsNotNone(achou, "não há botão 'Criar conta' DEPOIS da caixa dos termos")
        botao = achou.start()
        entre = re.sub(r"<[^>]+>", " ", corpo[aceite:botao])
        entre = " ".join(entre.split())
        # Entre a caixa e o botão só pode haver o rótulo da própria caixa e os
        # dois links legais — nenhum campo, nenhuma outra pergunta. E "campo" é
        # QUALQUER controle: `<select>` e `<textarea>` escapavam de uma régua
        # que só procurava `<input`.
        depois_do_rotulo = corpo[corpo.index("</label>", aceite):botao]
        for controle in ("<input", "<select", "<textarea"):
            with self.subTest(controle=controle):
                self.assertNotIn(controle, depois_do_rotulo)
        self.assertIn("Termos de Uso", entre)
