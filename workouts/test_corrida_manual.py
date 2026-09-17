# -*- coding: utf-8 -*-
"""A corrida registrada à mão — esteira, relógio, celular no bolso.

BENCHMARK-2026-09 (d): Strava e NRC têm registro manual de graça; um pilar só
com GPS ao vivo parece inacabado (DELTA de 16/09, D5/U20). Aqui o registro
manual reutiliza os tetos do GPS (`corrida_views`), o `op_id` da fila
(duplo toque = uma corrida) e o padrão de exclusão em duas etapas da conta.

Corrida por GPS não se edita: o traço contradiria os números.
"""
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from workouts.models import Corrida
from workouts.tests import create_user


def _campos(html):
    return dict(re.findall(r'name="([a-z_]+)"[^>]*?value="([^"]*)"', html))


def _regra_css(css, seletor):
    """Corpo da regra CSS `seletor`, sem comentários — mesma âncora de
    `plans/test_agua_zerar_nao_empurra.py` e `config/tests.py::_regras`: exige
    a chave de abertura logo após o seletor, então não casa por acidente com
    um comentário que só cita o seletor."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", css)
    assert m, "regra não encontrada: " + seletor
    return m.group(1)


class ORegistroManualTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="manual@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()

    def _post(self, op_id=None, **extra):
        dados = {"distancia_km": "5,2", "tempo": "28:10", "data": self.hoje.isoformat(),
                 "sensacao": "normal", "op_id": op_id or uuid.uuid4().hex}
        dados.update(extra)
        return self.client.post(reverse("workouts:corrida_nova"), dados)

    def test_o_get_traz_um_op_id_escondido_e_a_data_de_hoje(self):
        html = self.client.get(reverse("workouts:corrida_nova")).content.decode()
        campos = _campos(html)
        self.assertEqual(len(campos["op_id"]), 32)
        self.assertEqual(campos["data"], self.hoje.isoformat())

    def test_cria_com_virgula_e_mm_ss(self):
        r = self._post()
        self.assertEqual(r.status_code, 302)
        c = Corrida.objects.get(user=self.pessoa)
        self.assertEqual((c.distancia_m, c.duracao_s, c.origem, c.sensacao), (5200, 1690, "manual", "normal"))
        self.assertEqual(timezone.localtime(c.comecou_em).hour, 12)
        self.assertEqual(c.terminou_em - c.comecou_em, timedelta(seconds=1690))

    def test_h_mm_ss_tambem_vale(self):
        self._post(distancia_km="21,1", tempo="1:58:30")
        self.assertEqual(Corrida.objects.get().duracao_s, 7110)

    def test_o_duplo_toque_grava_uma_corrida(self):
        op = uuid.uuid4().hex
        self._post(op_id=op); self._post(op_id=op)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_recusa_data_futura_tetos_e_velocidade_impossivel(self):
        amanha = (self.hoje + timedelta(days=1)).isoformat()
        for extra in ({"data": amanha}, {"distancia_km": "0,01"}, {"distancia_km": "301"},
                      {"tempo": "13:00:00"}, {"distancia_km": "10", "tempo": "10:00"},
                      # o relógio nunca marca 99 segundos nem 60 minutos — o
                      # regex aceitava as duas antes de _TEMPO prender
                      # minutos e segundos a [0-5]?\d / [0-5]\d.
                      {"tempo": "5:99"}, {"tempo": "1:60:00"}):
            r = self._post(**extra)
            self.assertEqual(r.status_code, 200, extra)
            self.assertContains(r, 'aria-invalid="true"')
        self.assertEqual(Corrida.objects.count(), 0)

    def test_a_lista_mostra_a_mao_a_sensacao_e_os_links(self):
        """Âncora em `class="corrida__origem">à mão` e não em "à mão" solto:
        a string aparece QUATRO vezes na tela (o link "Registrar corrida à
        mão", este marcador, a nota de que só corrida à mão se edita, e o
        estado vazio) — `assertIn("à mão", html)` passava mesmo se o `<span>`
        do marcador nunca tivesse existido, porque as outras três ocorrências
        bastavam sozinhas (a armadilha do nutriplan-qa)."""
        self._post()
        html = self.client.get(reverse("workouts:corridas")).content.decode()
        c = Corrida.objects.get()
        self.assertIn('class="corrida__origem">à mão', html)
        self.assertIn('class="corrida__sensacao">normal', html)
        self.assertIn(reverse("workouts:corrida_editar", args=[c.pk]), html)
        self.assertIn(reverse("workouts:corrida_excluir", args=[c.pk]), html)


class EdicaoEExclusaoTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="edita@exemplo.com")
        self.outra = create_user(email="outra@exemplo.com")
        self.client.force_login(self.pessoa)
        agora = timezone.now()
        self.manual = Corrida.objects.create(user=self.pessoa, op_id="m1", origem="manual", comecou_em=agora - timedelta(minutes=30), terminou_em=agora, distancia_m=5000, duracao_s=1800)
        self.gps = Corrida.objects.create(user=self.pessoa, op_id="g1", origem="gps", comecou_em=agora - timedelta(hours=2), terminou_em=agora - timedelta(hours=1), distancia_m=8000, duracao_s=3600)

    def test_edita_a_manual(self):
        url = reverse("workouts:corrida_editar", args=[self.manual.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"distancia_km": "5,5", "tempo": "30:00", "data": timezone.localdate().isoformat(), "sensacao": "pesada"})
        self.assertEqual(r.status_code, 302)
        self.manual.refresh_from_db()
        self.assertEqual((self.manual.distancia_m, self.manual.duracao_s, self.manual.sensacao), (5500, 1800, "pesada"))

    def test_gps_nao_edita_e_corrida_alheia_e_404(self):
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[self.gps.pk])).status_code, 404)
        self.client.force_login(self.outra)
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[self.manual.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("workouts:corrida_excluir", args=[self.manual.pk])).status_code, 404)

    def test_exclusao_em_duas_etapas_vale_para_gps_e_manual(self):
        for corrida in (self.manual, self.gps):
            url = reverse("workouts:corrida_excluir", args=[corrida.pk])
            html = self.client.get(url).content.decode()
            self.assertIn("Excluir esta corrida", html)
            self.assertIn("Cancelar", html)
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 0)


class OsBotoesDeAcaoNaoSeSobrepoemTests(SimpleTestCase):
    """MOB-11 de novo, agora em `.corrida__acoes`: editar/excluir são dois
    `.btn-link` lado a lado, e o `.btn-link` carrega `margin: -.75rem -.35rem`
    para o alvo de 44px não empurrar o layout. Com `gap: .2rem` o vão real
    era .2 - .35 - .35 = -.5rem — as duas caixas de 44px se sobrepunham em
    ~8px, o mesmo formato de falha já corrigido em `.agua__zerar` (MOB-11) e
    `.agora__desfazer`.

    Sabotagem que precisa ficar vermelha: tirar o `margin-inline: 0` de
    `.corrida__acoes .btn-link`.
    """

    def setUp(self):
        self.css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")

    def test_os_links_nao_avancam_um_sobre_o_outro(self):
        self.assertRegex(self.css, r"\.corrida__acoes\s+\.btn-link\s*\{[^}]*margin-inline:\s*0")

    def test_o_vao_entre_os_dois_fica_com_pelo_menos_8px(self):
        """Sem a margem negativa, o vão real é o próprio `gap` — por isso ele
        precisa valer >= 8px (--espaco-3), e não os .2rem (3,2px) de antes."""
        acoes = _regra_css(self.css, ".corrida__acoes")
        self.assertRegex(acoes, r"gap:\s*var\(--espaco-3\)")


def _tag_do_input(html, nome):
    """A tag `<input ...>` inteira que carrega `name="nome"`, para conferir
    atributo sem depender da ORDEM em que o Django os escreve — `class` pode
    vir antes ou depois de `name` conforme o widget."""
    m = re.search(r'<input\b[^>]*\bname="%s"[^>]*>' % re.escape(nome), html)
    assert m, "não achei <input name=\"%s\"> no HTML" % nome
    return m.group(0)


class C1OsCamposDeTextoTemAClasseDoSistemaVisualTests(TestCase):
    """C1 (avaliação de mercado, 17/09/2026): `CorridaManualForm` é um
    `forms.Form` cru, e `partials/field.html` documenta que a classe
    `field-input` vem do FORM, não do template — é `CamposDoNutriPlanMixin`
    (`accounts/forms.py`) quem faz isso pelos formulários de senha. O de
    corrida nasceu sem ela: os três campos de texto ficavam sem a moldura de
    52px, abaixo da régua de toque de 44px que o CLAUDE.md exige medida nas
    duas dimensões.

    `sensacao` fica de fora de propósito: é `RadioSelect`, e `.field-input`
    carrega `min-height: 3.25rem` — clampado por cima do `height: 1.2rem` que
    `.choice-list input` dá ao próprio rádio, incharia o círculo de marcação
    para o tamanho de um campo de texto.
    """

    def setUp(self):
        self.pessoa = create_user(email="estilo-corrida@exemplo.com")
        self.client.force_login(self.pessoa)

    def test_distancia_tempo_e_data_levam_field_input(self):
        html = self.client.get(reverse("workouts:corrida_nova")).content.decode()
        for nome in ("distancia_km", "tempo", "data"):
            with self.subTest(campo=nome):
                self.assertRegex(_tag_do_input(html, nome), r'class="field-input"')

    def test_a_sensacao_continua_radio_sem_field_input(self):
        """CONTROLE: greenwashing seria aplicar a classe em TODO widget —
        inclusive no rádio, onde ela quebraria o tamanho do círculo. Este
        teste falha se alguém trocar o `setdefault` seletivo por
        `CamposDoNutriPlanMixin` (que veste todo campo, sem distinção)."""
        html = self.client.get(reverse("workouts:corrida_nova")).content.decode()
        for tag in re.findall(r'<input\b[^>]*\bname="sensacao"[^>]*>', html):
            self.assertNotIn("field-input", tag)


class I2DistanciaNaoFinitaNaoDerrubaOFormularioTests(TestCase):
    """I2 (avaliação de mercado, 17/09/2026): `clean_distancia_km` fazia
    `int(km * 1000)` FORA do `try/except InvalidOperation` — `Decimal("nan")`
    e `Decimal("inf")` são conversões VÁLIDAS (não levantam
    `InvalidOperation`), então passavam pelo `try` e só explodiam na conta
    seguinte: `int(Decimal("nan") * 1000)` levanta `decimal.InvalidOperation`
    sem handler por perto — 500 para quem digitou "nan" ou colou algo torto
    de um teclado numérico de aparelho estranho, em vez do erro de validação
    de sempre.
    """

    def setUp(self):
        self.pessoa = create_user(email="naofinito@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()

    def _post(self, distancia_km):
        return self.client.post(
            reverse("workouts:corrida_nova"),
            {"distancia_km": distancia_km, "tempo": "28:10", "data": self.hoje.isoformat(),
             "sensacao": "", "op_id": uuid.uuid4().hex},
        )

    def test_nan_inf_e_menos_inf_viram_erro_de_validacao_e_nao_500(self):
        for bruto in ("nan", "inf", "-inf"):
            with self.subTest(distancia_km=bruto):
                r = self._post(bruto)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, 'aria-invalid="true"')
        self.assertEqual(Corrida.objects.count(), 0)


class I3ReenvioComOpIdReusadoNaoApagaAPrimeiraTests(TestCase):
    """I3 (avaliação de mercado, 17/09/2026): o `post` engolia TODO
    `IntegrityError` como se fosse sempre o duplo toque do bfcache — mas o
    `op_id` volta escondido no formulário quando o navegador restaura a
    página pelo botão Voltar (bfcache), e nada impede um SEGUNDO envio, com
    dados DIFERENTES, sob o mesmo `op_id` (a pessoa volta, edita o campo à
    mão e manda de novo sem notar que o `op_id` é o de antes). O código
    antigo respondia "Corrida registrada." e a corrida nova sumia em
    silêncio — a fila offline errou de causa, mas o sintoma (perda silenciosa
    de dado) é o mesmo que ela existe para evitar.
    """

    def setUp(self):
        self.pessoa = create_user(email="reenvio@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        self.op_id = uuid.uuid4().hex

    def _post(self, distancia_km, tempo="28:10"):
        return self.client.post(
            reverse("workouts:corrida_nova"),
            {"distancia_km": distancia_km, "tempo": tempo, "data": self.hoje.isoformat(),
             "sensacao": "normal", "op_id": self.op_id},
        )

    def test_o_duplo_toque_de_verdade_ainda_responde_sucesso(self):
        """O comportamento que já existia continua: MESMOS dados, mesmo
        `op_id` — é o duplo toque, e responde como sucesso."""
        self._post("5,2")
        r = self._post("5,2")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)
        self.assertEqual(Corrida.objects.get().distancia_m, 5200)

    def test_op_id_reusado_com_dados_diferentes_nao_e_engolido(self):
        self._post("5,2")
        r = self._post("8")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "já foi usado por outra corrida")
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)
        self.assertEqual(Corrida.objects.get().distancia_m, 5200)


class I1OLinkDeRegistroManualFicaDentroDoCorridaAgoraTests(TestCase):
    """I1 (avaliação de mercado, 17/09/2026): o link "Registrar corrida à
    mão" morava FORA de `section.corrida-agora`, sozinho entre dois `.card`
    — três blocos quase colados na tela, porque um `<a>` solto não entra na
    cadeia de espaçamento `.card + .card` (que só vale entre `.card`
    vizinhos). Ele virou o último filho de `.corrida-acoes`, que já dá `gap`
    e os 48px dos outros botões daquela ação — sem CSS novo.

    A âncora do teste é a PRÓPRIA seção: da abertura de
    `class="card corrida-agora"` até o `</section>` que a fecha — se o link
    saísse de novo para fora, o trecho capturado pararia antes dele.
    """

    def setUp(self):
        self.pessoa = create_user(email="link-corrida@exemplo.com")
        self.client.force_login(self.pessoa)

    def test_o_link_fica_dentro_da_secao_corrida_agora(self):
        html = self.client.get(reverse("workouts:corridas")).content.decode()
        m = re.search(r'class="card corrida-agora".*?</section>', html, re.S)
        self.assertIsNotNone(m, "seção .corrida-agora não encontrada")
        self.assertIn(reverse("workouts:corrida_nova"), m.group(0))
