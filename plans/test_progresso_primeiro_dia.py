"""O Progresso no primeiro dia diz o que a pessoa já fez hoje.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, R1 e
M6). A persona de academia registrou três refeições no primeiro dia: uma
feita, uma pulada e uma "comi outra coisa". A Home dizia "1/5 refeições ·
1 fora" e o Progresso, na mesma hora, "— · Marque uma refeição para a
aderência começar". A frase pedia o que já tinha sido feito.

A causa estava em `evolucao.tile_de_dieta`: ele olhava só os dias FECHADOS,
e sem dia fechado caía no convite mesmo com hoje cheio de marcação. A
doutrina de 22/09 (CLAUDE.md, lote 2) já dizia o que a tela deve mostrar
nesse caso: "1/2 · hoje, até agora", sem porcentagem. Hoje ainda não é nota.

Na mesma tela havia três detalhes que também afirmavam coisa que não
aconteceu:

- a seta ↓ da água no primeiro dia, uma "tendência" calculada sobre um dia
  que ainda não terminou;
- a legenda "dia cheio" no mapa da corrida, onde a cor escura quer dizer "a
  corrida mais longa do período";
- as listas de apoio ("O que mais você registrou", "Melhores cargas"), que
  eram `<ul>` com classes que o CSS nunca definiu e apareciam com marcador
  de lista.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans import evolucao, services
from plans.models import HydrationLog, MealLog, MealStatus
from plans.test_numeros_do_progresso import _caixa
from plans.tests import create_complete_user


class OPrimeiroDiaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="primeiro-dia@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)
        self.user.date_joined = timezone.now()
        self.user.save(update_fields=["date_joined"])
        services.sync_active_plan(self.user)
        self.slots = list(services.get_active_plan(self.user).slots.all().order_by("time"))

    def _marcar(self, slot, status, kcal="0"):
        MealLog.objects.update_or_create(
            user=self.user, slot=slot, date=timezone.localdate(),
            defaults={"status": status, "kcal": Decimal(kcal)},
        )

    def _tiles(self):
        return _caixa(self.client.get(reverse("plans:history")).content.decode())

    def test_com_refeicao_marcada_hoje_o_cardapio_nao_pede_para_marcar(self):
        self._marcar(self.slots[0], MealStatus.DONE, "400")
        self._marcar(self.slots[1], MealStatus.SKIPPED)
        self._marcar(self.slots[2], MealStatus.OFF_PLAN, "300")
        dieta = self._tiles()["dieta"]
        self.assertNotIn("Marque uma refeição", dieta["frase"])
        self.assertIn("hoje, até agora", dieta["frase"])
        self.assertRegex(dieta["valor"], r"^1/\d+$")
        self.assertNotIn("%", dieta["valor"])

    def test_sem_nada_marcado_o_convite_continua(self):
        """Controle: o convite só sai quando há o que mostrar no lugar."""
        dieta = self._tiles()["dieta"]
        self.assertEqual(dieta["valor"], "—")
        self.assertIn("Marque uma refeição", dieta["frase"])

    def test_a_agua_de_hoje_nao_tem_seta(self):
        HydrationLog.objects.create(user=self.user, date=timezone.localdate(), ml=750)
        plano = services.get_active_plan(self.user)
        tile = next(t for t in evolucao.reunir(self.user, "semana", plano=plano)["tiles"] if t.chave == "agua")
        self.assertEqual(tile.valor, "750")
        self.assertIn("meta", tile.frase)  # com meta, a seta seria "caindo": 750 de 2.500+
        self.assertEqual(tile.direcao, evolucao.SEM_DIRECAO)


class ALegendaDizOQueACorMedeTests(TestCase):
    def test_a_corrida_e_a_agua_tem_legenda_propria(self):
        user = create_complete_user(email="legenda@exemplo.com")
        HydrationLog.objects.create(user=user, date=timezone.localdate(), ml=750)
        self.client.force_login(user)
        html = self.client.get(reverse("plans:history")).content.decode()
        agua = html.split('id="area-agua"', 1)[1].split("</section>", 1)[0]
        self.assertIn("meta batida", agua)
        self.assertNotIn("dia cheio", agua)

    def test_o_template_da_a_corrida_a_propria_legenda(self):
        fonte = (Path(settings.BASE_DIR) / "templates/plans/_progresso_area.html").read_text(encoding="utf-8")
        ramo = fonte.split("area.chave == 'corrida' %}", 1)[1].split("{% elif", 1)[0]
        self.assertIn("a mais longa do período", ramo)
        self.assertNotIn("dia cheio", ramo)


class AsListasDeApoioNaoTemMarcadorTests(TestCase):
    """As classes `data-list__item`, `__nome` e `__valor` não existiam no
    CSS: a lista aparecia com marcador e sem o valor à direita."""

    def test_o_css_define_a_linha_da_lista(self):
        css = (Path(settings.BASE_DIR) / "static/css/app.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        regra = re.search(r"ul\.data-list\s*\{([^}]*)\}", css)
        self.assertIsNotNone(regra, "falta a regra de ul.data-list")
        self.assertIn("list-style: none", regra.group(1))
        for classe in ("data-list__item", "data-list__valor"):
            self.assertRegex(css, r"\.%s\s*\{" % classe)
