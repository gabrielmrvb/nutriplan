# -*- coding: utf-8 -*-
"""Os atritos da Home que a rodada 2 de experiência deixou (24/09/2026).

**A ofensiva em zero convida, e não cobra.** A frase já não ABRIA com o que
faltou desde 22/09 — mas continuava terminando nele: "Recomeça hoje: treino
no dia de treino, mais dieta ou água. Ontem faltou treino e dieta ou água."
Duas coisas erradas na mesma linha: a palavra "faltou", que é a única leitura
possível de um contador em zero, e a instrução, que repete a REGRA ("treino
no dia de treino, mais dieta ou água") em vez de dizer o que fazer nos
próximos dez segundos. O texto de quem está em zero passou a ser a porta do
dia: "Recomeça hoje: registre uma refeição ou um copo d'água."

**Um só registro de peso na Home.** MEDIDO no navegador, conta de teste com
Progresso declarado: TRÊS caminhos para a mesma ação na mesma tela — o
cartão AGORA com "Registrar peso", o cartão do painel com "Registrar peso"
e a faixa `#pesar` com "Peso de hoje · Registrar". Os dois primeiros são
âncoras para o terceiro. A faixa fica (é onde o campo está); os cartões
passam a levar ao Progresso, que é outra pergunta.
"""
import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Pilar, TrainingDay
from plans import services, streaks
from plans.models import HydrationLog
from plans.tests import create_complete_user


class AOfensivaEmZeroConvidaTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="ofensiva-zero@exemplo.com")
        self.user.date_joined = timezone.now() - timedelta(days=10)
        self.user.save(update_fields=["date_joined"])
        self.hoje = timezone.localdate()

    def _mensagem(self):
        """A frase de QUEM ESTÁ EM ZERO, montada direto.

        Zerar a sequência por fixture é caro e frágil — o dia de descanso
        fecha sozinho, e uma conta de dez dias sem treino previsto tem dez
        dias de ofensiva. O que esta classe mede é o TEXTO, e o texto é uma
        função de `dias`, `falta_hoje` e `falta_ontem`.
        """
        return streaks.Ofensiva(
            dias=0, recorde=0, hoje_completo=False,
            falta_hoje=["treino", "dieta ou água"],
            falta_ontem=["dieta ou água"],
        ).mensagem

    def test_a_frase_de_zero_nao_diz_faltou(self):
        frase = self._mensagem()
        self.assertNotIn("faltou", frase.lower(), frase)

    def test_a_frase_de_zero_diz_o_que_fazer_agora(self):
        """Uma AÇÃO de dez segundos, não a régua do dia. "treino no dia de
        treino, mais dieta ou água" descreve como o contador funciona; quem
        está em zero precisa do primeiro toque."""
        frase = self._mensagem()
        # "Recomeça" porque este fixture tem conta de ontem; quem chega hoje
        # lê "Comece hoje" com as mesmas palavras — o teste logo abaixo.
        self.assertIn("Recomeça hoje", frase)
        self.assertIn("refeição", frase)
        self.assertIn("copo", frase)

    def test_quem_tem_sequencia_viva_continua_com_o_texto_de_sempre(self):
        """Controle positivo: a mudança é SÓ do zero. As frases de 1, de
        menos de 7 e de 30 dias não são desta missão."""
        ofensiva = streaks.Ofensiva(
            dias=3, recorde=3, hoje_completo=True, falta_hoje=[], falta_ontem=None
        )
        self.assertIn("3 dias seguidos", ofensiva.mensagem)

    def test_em_risco_continua_dizendo_o_que_falta_hoje(self):
        """HOJE ainda dá para fazer, e ali nomear o pilar é instrução, não
        cobrança — a frase de risco não muda."""
        ofensiva = streaks.Ofensiva(
            dias=2, recorde=2, hoje_completo=False,
            falta_hoje=["dieta ou água"], falta_ontem=None,
        )
        self.assertIn("dieta ou água", ofensiva.mensagem)

    def test_o_zero_nunca_nomeia_o_que_faltou_e_a_instrucao_e_a_mesma(self):
        """Era o ramo de `falta_ontem` que trazia a cobrança de volta, e o
        que ele NÃO pode mais fazer é nomear a falta. A INSTRUÇÃO é a mesma
        com e sem ontem medido; o que `falta_ontem` ainda decide é só o
        VERBO, porque "recomeça" é falso para quem criou a conta hoje."""
        com_ontem = streaks.Ofensiva(
            dias=0, recorde=0, hoje_completo=False, falta_hoje=["treino"],
            falta_ontem=["dieta ou água"],
        )
        sem_ontem = streaks.Ofensiva(
            dias=0, recorde=0, hoje_completo=False, falta_hoje=["treino"],
            falta_ontem=None,
        )
        instrucao = ": registre uma refeição ou um copo d'água."
        self.assertEqual(com_ontem.mensagem, "Recomeça hoje" + instrucao)
        self.assertEqual(sem_ontem.mensagem, "Comece hoje" + instrucao)
        for frase in (com_ontem.mensagem, sem_ontem.mensagem):
            self.assertNotIn("faltou", frase)
            self.assertNotIn("dieta ou água", frase)
            self.assertNotIn("treino", frase)


class UmSoRegistroDePesoNaHomeTests(TestCase):
    """MEDIDO no navegador: três "Registrar peso" na mesma tela."""

    def setUp(self):
        self.user = create_complete_user(email="peso-unico@exemplo.com")
        perfil = self.user.profile
        perfil.interesse_progresso = True
        perfil.prioridade = Pilar.PROGRESSO
        perfil.save()
        # Sem pesagem nesta semana: é o estado que acende o convite, e é nele
        # que os três caminhos apareciam juntos.
        self.user.weight_entries.update(
            date=timezone.localdate() - timedelta(days=9)
        )
        services.sync_active_plan(self.user)
        self.client.force_login(self.user)

    def _home(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        return html.split("<main", 1)[1].split("</main>", 1)[0]

    def test_a_home_oferece_registrar_peso_uma_vez_so(self):
        corpo = self._home()
        texto = re.sub(r"<[^>]+>", " ", corpo)
        # No máximo UM caminho até a faixa, e ele é o cartão AGORA quando a
        # pesagem é a ação do momento. O que saiu foi o TERCEIRO: o rodapé do
        # cartão do painel, que oferecia a mesma coisa ao lado.
        self.assertLessEqual(len(re.findall(r'href="#pesar"', corpo)), 1, corpo[:300])
        self.assertLessEqual(len(re.findall(r"Registrar peso", texto)), 1, texto[:300])

    def test_a_faixa_do_peso_continua_na_tela(self):
        """O que sai são os ATALHOS; o campo fica — tirá-lo seria esconder a
        ação em vez de deduplicá-la."""
        corpo = self._home()
        self.assertIn('id="pesar"', corpo)
        self.assertIn("Peso de hoje", corpo)

    def test_os_cartoes_levam_ao_progresso(self):
        """"Ver progresso" é outra pergunta, e a porta continua existindo."""
        corpo = self._home()
        self.assertIn(reverse("plans:history"), corpo)

    def test_quem_ja_se_pesou_hoje_nao_ve_a_faixa(self):
        """Controle positivo do convite: com o peso de hoje registrado, a
        faixa não aparece e nada mais oferece a ação."""
        self.user.weight_entries.update(date=timezone.localdate())
        corpo = self._home()
        self.assertNotIn('id="pesar"', corpo)
        self.assertEqual(len(re.findall(r'href="#pesar"', corpo)), 0)
