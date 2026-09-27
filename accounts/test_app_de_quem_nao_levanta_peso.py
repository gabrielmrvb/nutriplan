# -*- coding: utf-8 -*-
"""Quem diz que não faz musculação usa um app coerente com isso.

A pergunta "você faz musculação?" entrou em 22/09/2026 e resolveu UMA tela: o
painel de treino parou de cobrar "Cadastrar meus dias". O resto do app
continuou de academia, e a persona que só corre via, na ordem:

1. a terceira aba da barra dizendo "Treino";
2. a etapa 3 oferecendo "Treino" como área para acompanhar — e, marcada, um
   selo de área principal apontando para a tela que diz "você não tem ficha";
3. no fim do cadastro, "cardápio de exemplo e ficha montados";
4. o Progresso abrindo com "Treinos 0 — Sem dia de treino combinado";
5. o e-mail de boas-vindas mandando abrir a ficha de hoje;
6. e zero conquistas possíveis, porque as onze regras eram de treino, ofensiva
   e recorde de carga.

Item 4 da missão "quem entra não desiste" (26/09/2026). O que NÃO está aqui: o
cartão da Home, ADIADO por decisão do dono até o veto do PR #138, que redesenha
`templates/plans/today.html`.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Musculacao, Pilar, Profile, TrainingDay
from accounts.templatetags.navegacao import ABAS, abas_de
from plans.tests import create_complete_user
from workouts.models import Corrida


def so_corre(email="corredor@exemplo.com"):
    """Uma pessoa com cadastro completo que respondeu que NÃO faz musculação."""
    user = create_complete_user(email=email)
    TrainingDay.objects.filter(user=user).delete()
    # PELA INSTÂNCIA, e não por `update()` no queryset: `create_complete_user`
    # já tocou `user.profile`, e o Django guarda a reversa do OneToOne no
    # próprio `user` — um `update()` mudaria o banco e deixaria o cache velho.
    # É a mesma armadilha que `acertar_ficha` documenta em `accounts/views.py`.
    perfil = user.profile
    perfil.musculacao = Musculacao.NAO
    perfil.save(update_fields=["musculacao", "updated_at"])
    return user


class ARegraMoraNumLugarTests(TestCase):
    def test_a_propriedade_le_a_resposta_e_nao_o_silencio(self):
        """Branco é "não perguntado", e não "não faz": tratá-lo como "não faz"
        mudaria a navegação de toda conta anterior à pergunta."""
        user = create_complete_user(email="regra@exemplo.com")
        perfil = user.profile
        self.assertEqual(perfil.musculacao, "")
        self.assertFalse(perfil.nao_faz_musculacao)
        perfil.musculacao = Musculacao.SIM
        self.assertFalse(perfil.nao_faz_musculacao)
        perfil.musculacao = Musculacao.NAO
        self.assertTrue(perfil.nao_faz_musculacao)


class AAbaDeTreinoViraCorridaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_quem_nao_faz_musculacao_tem_aba_de_corrida(self):
        user = so_corre()
        chaves = [aba["chave"] for aba in abas_de(user)]
        self.assertIn("corrida", chaves)
        self.assertNotIn("treino", chaves)
        # A barra continua com QUATRO itens: a conta de largura a 320px não
        # muda porque a aba é substituída na posição, não acrescentada.
        self.assertEqual(len(chaves), len(ABAS))

    def test_quem_faz_musculacao_nao_muda_de_barra(self):
        user = create_complete_user(email="levanta@exemplo.com")
        Profile.objects.filter(user=user).update(musculacao=Musculacao.SIM)
        user.refresh_from_db()
        self.assertEqual(abas_de(user), ABAS)

    def test_quem_nunca_respondeu_nao_muda_de_barra(self):
        self.assertEqual(abas_de(create_complete_user(email="quieto@exemplo.com")), ABAS)

    def test_anonimo_e_shell_offline_ficam_com_a_barra_canonica(self):
        """O shell de offline é pré-cacheado e servido a quem pegar o aparelho
        depois: "esta pessoa não faz musculação" é identidade, e é o mesmo
        motivo de `data-usuario` não entrar lá."""
        self.assertEqual(abas_de(None), ABAS)
        self.assertEqual(abas_de(so_corre("shell@exemplo.com"), shell_offline=True), ABAS)

    def test_so_uma_aba_acende_na_tela_de_corridas(self):
        """"Mais" acendia por `running` também: com a aba própria, as duas
        acendiam juntas e `aria-current="page"` saía duplicado na mesma barra."""
        user = so_corre("acende@exemplo.com")
        acesas = [
            aba["chave"]
            for aba in abas_de(user)
            if "running" in aba["navs"]
        ]
        self.assertEqual(acesas, ["corrida"])

    def test_a_tela_desenha_a_aba_de_corrida(self):
        """A prova pela PÁGINA, e não pela função: a tag lê o perfil do
        contexto, e um `abas_de` certo com a tag errada não muda nada."""
        user = so_corre("tela@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("plans:hydration")).content.decode()
        barra = html.split('class="tabbar', 1)[1]
        self.assertIn("Corrida", barra)
        self.assertIn("icone-bicicleta", barra)


class AEtapaTresNaoOfereceTreinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _form(self, perfil):
        from accounts.forms import InteressesForm

        return InteressesForm(instance=perfil)

    def test_treino_sai_das_duas_listas(self):
        user = so_corre("etapa3@exemplo.com")
        user.refresh_from_db()
        form = self._form(user.profile)
        for campo in ("interesses", "prioridade"):
            valores = [v for v, _ in form.fields[campo].choices]
            with self.subTest(campo=campo):
                self.assertNotIn(Pilar.TREINO, valores)
                self.assertIn(Pilar.CORRIDA, valores)

    def test_quem_faz_musculacao_continua_com_treino(self):
        user = create_complete_user(email="etapa3-sim@exemplo.com")
        Profile.objects.filter(user=user).update(musculacao=Musculacao.SIM)
        user.refresh_from_db()
        valores = [v for v, _ in self._form(user.profile).fields["interesses"].choices]
        self.assertIn(Pilar.TREINO, valores)

    def test_treino_gravado_antes_da_resposta_e_descartado(self):
        """Marcou "Treino" na etapa 3, voltou à etapa 2 e disse que não faz. O
        pilar chega por `initial`, que não passa pela validação de choices."""
        from accounts.forms import InteressesForm

        user = so_corre("etapa3-volta@exemplo.com")
        Profile.objects.filter(user=user).update(
            interesse_treino=True, prioridade=Pilar.TREINO, interesse_corrida=True
        )
        user.refresh_from_db()
        form = InteressesForm(
            instance=user.profile,
            data={"interesses": [Pilar.CORRIDA], "prioridade": Pilar.CORRIDA},
        )
        self.assertTrue(form.is_valid(), form.errors)
        perfil = form.save()
        self.assertFalse(perfil.interesse_treino)
        self.assertEqual(perfil.prioridade, Pilar.CORRIDA)


class ADivisaoNaoEPerguntadaTests(TestCase):
    """O campo da divisão não é exigido nem renderizado para quem não levanta
    peso — o último item da lista do dono ("o campo da divisão é explícito ou
    removido")."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_a_etapa_2_de_quem_nao_faz_musculacao_nao_pede_divisao(self):
        user = so_corre("divisao@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(
            reverse("accounts:onboarding_step", args=[2])
        ).content.decode()
        # O bloco da academia existe no HTML (é o `[data-so-musculacao]` que o
        # `pwa.js` esconde), mas a PERGUNTA da divisão não pode estar exigida:
        # é o servidor que decide, e sem JavaScript também.
        self.assertNotIn('name="split_preference" required', html)

    def test_o_envio_sem_dias_nao_exige_divisao(self):
        user = so_corre("divisao-post@exemplo.com")
        self.client.force_login(user)
        resposta = self.client.post(
            reverse("accounts:onboarding_step", args=[2]),
            {"musculacao": Musculacao.NAO, "goal": user.profile.goal,
             "activity_level": user.profile.activity_level,
             "meal_style": user.profile.meal_style,
             "wake_time": "07:00", "sleep_time": "23:00"},
        )
        self.assertIn(resposta.status_code, (200, 302))
        if resposta.status_code == 200:
            self.assertNotIn("Escolha como dividir", resposta.content.decode())


class OProgressoDeQuemSoCorreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _painel(self, user):
        from plans import evolucao

        user.refresh_from_db()
        return evolucao.reunir(user, "semana", perfil=user.profile)

    def test_corrida_vem_antes_do_treino_e_o_treino_sem_dado_sai(self):
        user = so_corre("progresso@exemplo.com")
        chaves = [a.chave for a in self._painel(user)["areas"]]
        self.assertEqual(chaves, ["dieta", "corrida", "agua"])

    def test_o_treino_com_historico_continua_na_tela(self):
        """Quem treinou antes de mudar a resposta continua vendo o próprio
        histórico — apagá-lo seria o app decidir que aquilo não aconteceu."""
        from workouts.models import Exercise, ExerciseLog

        user = so_corre("progresso-historico@exemplo.com")
        ExerciseLog.objects.create(
            user=user, exercise=Exercise.objects.filter(is_active=True).first(),
            date=timezone.localdate(), set_number=1, weight_kg=Decimal("20"), reps=10,
        )
        chaves = [a.chave for a in self._painel(user)["areas"]]
        self.assertEqual(chaves, ["dieta", "corrida", "agua", "treino"])

    def test_quem_faz_musculacao_nao_muda_de_ordem(self):
        user = create_complete_user(email="progresso-sim@exemplo.com")
        Profile.objects.filter(user=user).update(musculacao=Musculacao.SIM)
        chaves = [a.chave for a in self._painel(user)["areas"]]
        self.assertEqual(chaves, ["dieta", "treino", "agua", "corrida"])

    def test_o_tile_de_treino_da_lugar_ao_de_corrida(self):
        user = so_corre("tile@exemplo.com")
        agora = timezone.now()
        Corrida.objects.create(
            user=user, op_id="tile-1", comecou_em=agora - timedelta(minutes=30),
            terminou_em=agora, distancia_m=5200, duracao_s=1800,
        )
        tiles = {t.chave for t in self._painel(user)["tiles"]}
        self.assertIn("corrida", tiles)
        self.assertNotIn("treino", tiles)

    def test_a_tela_abre_e_nao_fala_de_treino_combinado(self):
        user = so_corre("tela-progresso@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertNotIn("Sem dia de treino combinado no período", html)


class AsConquistasDeCorridaTests(TestCase):
    """As quatro novas, e elas valem para todo mundo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="conquista-corrida@exemplo.com")

    def _correr(self, metros, quando=None):
        fim = quando or timezone.now()
        Corrida.objects.create(
            user=self.user, op_id="c-%d-%s" % (metros, fim.isoformat()),
            comecou_em=fim - timedelta(minutes=30), terminou_em=fim,
            distancia_m=metros, duracao_s=1800,
        )

    def _slugs(self):
        from achievements import services

        return {c.slug for c in services.avaliar(self.user)}

    def test_as_quatro_existem_no_catalogo(self):
        from achievements.regras import CATALOGO, Familia

        de_corrida = [r.slug for r in CATALOGO if r.familia == Familia.CORRIDA]
        self.assertEqual(
            sorted(de_corrida),
            ["corrida-100km", "corrida-10k", "corrida-5k", "primeira-corrida"],
        )

    def test_sem_corrida_nenhuma_nasce(self):
        self.assertEqual(self._slugs() & {"primeira-corrida", "corrida-5k"}, set())

    def test_a_primeira_corrida_desbloqueia(self):
        self._correr(3000)
        self.assertIn("primeira-corrida", self._slugs())
        self.assertNotIn("corrida-5k", self._slugs())

    def test_cinco_quilometros_numa_corrida(self):
        self._correr(5100)
        nascidas = self._slugs()
        self.assertIn("corrida-5k", nascidas)
        self.assertNotIn("corrida-10k", nascidas)

    def test_dez_quilometros_numa_corrida_traz_os_cinco_tambem(self):
        self._correr(10000)
        nascidas = self._slugs()
        self.assertIn("corrida-5k", nascidas)
        self.assertIn("corrida-10k", nascidas)

    def test_cem_quilometros_sao_somados(self):
        """Dez corridas de 10 km: nenhuma delas é 100, e o marco é do acúmulo."""
        agora = timezone.now()
        for n in range(10):
            self._correr(10000, agora - timedelta(days=n))
        self.assertIn("corrida-100km", self._slugs())

    def test_o_marco_nao_renasce_a_cada_corrida_mais_longa(self):
        """Nenhuma delas é repetível: marco que renasce é confete."""
        self._correr(6000)
        self.assertIn("corrida-5k", self._slugs())
        self._correr(7000)
        self.assertNotIn("corrida-5k", self._slugs())

    def test_a_corrida_aparece_no_progresso_de_quem_ja_correu(self):
        self._correr(5200)
        from achievements import services

        services.avaliar(self.user)
        self.client.force_login(self.user)
        html = self.client.get(reverse("achievements:list")).content.decode()
        self.assertIn("5 km de uma vez", html)


class AFraseDoFimDoCadastroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_sem_ficha_a_frase_nao_promete_ficha(self):
        from django.contrib.messages import get_messages

        user = so_corre("frase@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=3)
        self.client.force_login(user)
        # A etapa 3 é COMPOSTA (`nomes_dos_forms = ("comida", "areas")`): sem
        # `meal_style` o envio volta 200 com o erro do outro formulário, e o
        # teste mediria a validação em vez da frase.
        resposta = self.client.post(
            reverse("accounts:onboarding_step", args=[3]),
            {
                "meal_style": user.profile.meal_style,
                "interesses": [Pilar.CORRIDA],
                "prioridade": Pilar.CORRIDA,
            },
            follow=False,
        )
        self.assertEqual(resposta.status_code, 302, resposta.content[:400])
        frases = [m.message for m in get_messages(resposta.wsgi_request)]
        self.assertTrue(frases)
        self.assertNotIn("ficha", " ".join(frases))
        self.assertIn("estimativa está pronta", " ".join(frases))


class OEmailDeBoasVindasTemVersaoPorPerfilTests(TestCase):
    """As TRÊS versões renderizadas — e a que sai hoje é a do branco.

    No cadastro a pergunta "você faz musculação?" ainda não foi feita (ela é
    da etapa 2), então `musculacao` está vazia. As outras duas existem para o
    dia em que o envio se mudar para depois da confirmação de e-mail, o que a
    docstring de `boas_vindas` já anuncia — e são testadas para não apodrecer.
    """

    def _render(self, musculacao):
        from django.template.loader import render_to_string

        contexto = {
            "nome": "Ana", "url_base": "https://exemplo.test",
            "descadastro": "https://exemplo.test/sair/", "preferencias": "https://exemplo.test/avisos/",
            "musculacao": musculacao,
        }
        return (
            render_to_string("email/boas_vindas.txt", contexto),
            render_to_string("email/boas_vindas.html", contexto),
        )

    def test_quem_disse_que_nao_faz_musculacao_nao_recebe_promessa_de_ficha(self):
        for corpo in self._render(Musculacao.NAO):
            self.assertNotIn("ficha", corpo)
            self.assertIn("Corrida", corpo)

    def test_quem_disse_que_faz_recebe_a_ficha(self):
        for corpo in self._render(Musculacao.SIM):
            self.assertIn("ficha de hoje", corpo)

    def test_antes_da_pergunta_a_frase_nao_promete_nem_nega(self):
        """O caso real de hoje: a pessoa acabou de criar a conta."""
        for corpo in self._render(""):
            self.assertIn("etapa 2", corpo)
            self.assertIn("Corrida", corpo)

    def test_o_envio_leva_a_resposta_do_perfil(self):
        """A prova de que o contexto chega: sem isto, as três versões acima
        existiriam e o e-mail sairia sempre na do branco."""
        from django.core import mail

        from avisos import services as avisos

        user = create_complete_user(email="boas-vindas@exemplo.com")
        Profile.objects.filter(user=user).update(musculacao=Musculacao.NAO)
        user.refresh_from_db()
        self.assertEqual(avisos.boas_vindas(user), "enviado")
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("ficha", mail.outbox[0].body)


class ACorridaTemPortaComFichaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_o_painel_com_ficha_leva_as_corridas(self):
        """`_corrida.html` estava nos dois ramos de "sem ficha" e em nenhum com
        ficha: quem levanta peso E corre não tinha caminho daqui."""
        from workouts import services as treino

        user = create_complete_user(email="porta@exemplo.com")
        treino.create_routine(user)
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIsNotNone(treino.get_active_routine(user))
        self.assertIn(reverse("workouts:corridas"), html)

    def test_o_painel_sem_ficha_continua_levando(self):
        user = so_corre("porta-sem@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIn(reverse("workouts:corridas"), html)
