# -*- coding: utf-8 -*-
"""A suíte roda numa DATA CONGELADA por padrão; a noturna roda na data real.

O incidente que pede isto está no CLAUDE.md ("O PRE-PUSH TESTA O COMMIT QUE
SOBE"): o push de terça 15/09/2026 passou "3044 OK" e o MESMO `main`
reprovava `plans.test_stress` na quarta — o orçamento de consultas media a
Home no dia em que a suíte rodava, e o teto tinha sido medido numa terça.
Em 18/09 aconteceu de novo, de outro jeito: `test_a_ficha_de_OUTRO_dia`
assumia que a ficha de outro dia mostra a opção 1, e a variação depende de
QUAL ocorrência da letra vem a seguir — do calendário. Um teste que passa
numa terça e cai numa quarta não está medindo o código; está medindo o dia.

Duas coisas, e as duas têm dono:

* **o gate é determinístico.** `RunnerUnico.setup_test_environment` liga
  este relógio: `django.utils.timezone.now()` devolve a HORA real de agora
  com a DATA local trocada por `DATA_DA_SUITE` — quarta-feira 16/09/2026,
  o "pior estado" que `plans/test_stress.py` já congelava à mão (dia de
  treino, com série registrada). Só a data: a hora continua real e
  monotônica, então `created_at` continua ordenando e nada que dependa de
  "agora > antes" muda. E só `timezone.now`: o app deriva "hoje" de
  `localdate()`/`localtime()` — nunca de `date.today()` (`plans/shopping.py`
  explica por quê) —, e os dois leem `now()` do módulo, na hora da chamada.
  O que NÃO lê é o `default=timezone.now` de campo de modelo, que guardou o
  OBJETO da função na definição da classe: `ligar()` troca esses defaults
  também, e `desligar()` os devolve.
* **a deriva do calendário tem quem a veja.** `.github/workflows/noturna.yml`
  roda a suíte completa toda madrugada com `NUTRIPLAN_DATA_REAL=1` — o
  relógio de verdade — e abre (ou comenta) uma issue quando fica vermelha,
  fechando-a quando volta a passar. O gate não vê o dia; a noturna só vê.

`NUTRIPLAN_DATA_DA_SUITE=AAAA-MM-DD` escolhe outra data: é assim que se
reproduz localmente o que a noturna achou, ou se varre a semana atrás de
teste que depende do dia.
"""
import os
from contextlib import contextmanager
from datetime import date, timezone as fuso_utc

from django.apps import apps
from django.utils import timezone

#: Desliga o congelamento: a suíte roda no relógio real. É o que a noturna faz.
VARIAVEL_DATA_REAL = "NUTRIPLAN_DATA_REAL"
#: Escolhe a data congelada (ISO, `2026-09-21`). Vence o padrão; perde para a real.
VARIAVEL_DATA = "NUTRIPLAN_DATA_DA_SUITE"
#: Quarta-feira 16/09/2026: dia de treino do fixture, com série registrada —
#: o pior estado medido em `plans/test_stress.py`. Mudar a data é mudar o
#: que o gate mede; a noturna é quem cobre os outros dias.
DATA_DA_SUITE = date(2026, 9, 16)

#: Para o log, em pt-BR e sem depender do locale da máquina: `strftime("%A")`
#: diz "Wednesday" no Actions e "quarta-feira" num Windows em português.
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

#: A função ORIGINAL, guardada uma vez na importação — é dela que a hora real
#: vem enquanto o relógio está ligado, e é ela que `desligar()` devolve.
_agora_real = timezone.now


def data_congelada():
    """A data que a suíte usa como hoje, ou `None` para o relógio real."""
    if os.environ.get(VARIAVEL_DATA_REAL):
        return None
    escrita = os.environ.get(VARIAVEL_DATA)
    return date.fromisoformat(escrita) if escrita else DATA_DA_SUITE


def agora_congelado(dia, agora_real=None):
    """`timezone.now()` com a data LOCAL trocada por `dia` e a hora real.

    Troca-se a data no fuso do projeto (`TIME_ZONE`), não em UTC: das 21h à
    meia-noite de Brasília o UTC já está no dia seguinte, e trocar lá faria
    `localdate()` devolver a véspera de `dia` nessas três horas.
    """
    local = timezone.localtime(agora_real or _agora_real())
    local = local.replace(year=dia.year, month=dia.month, day=dia.day)
    return local.astimezone(fuso_utc.utc)


def _trocar_default(campo, funcao):
    """Troca o `default` E esquece o cache: `Field.get_default()` guarda o
    callable em `_get_default` (`cached_property`) na primeira chamada, e
    mudar só `campo.default` depois disso não muda linha nenhuma."""
    campo.default = funcao
    campo.__dict__.pop("_get_default", None)


class Relogio:
    """O relógio da suíte: `ligar()` instala, `desligar()` devolve o anterior.

    `dia=None` é o relógio real — o mesmo objeto serve para suspender o
    congelamento num trecho de teste, e a devolução fica num lugar só.
    """

    def __init__(self, dia):
        self.dia = dia
        self._anterior = None
        self._defaults = []
        self._ligado = False

    def agora(self):
        if self.dia is None:
            return _agora_real()
        return agora_congelado(self.dia)

    def ligar(self):
        if self._ligado:
            return self
        self._anterior = timezone.now
        timezone.now = self.agora
        # `default=timezone.now` guardou o OBJETO original na definição da
        # classe; sem isto o `unlocked_at` de uma conquista nasceria na data
        # real. O `default` pode ser o original ou o de um relógio de fora
        # (a suíte, quando um teste congela outra data por cima).
        for modelo in apps.get_models(include_auto_created=True):
            for campo in modelo._meta.get_fields():
                default = getattr(campo, "default", None)
                if default is _agora_real or isinstance(getattr(default, "__self__", None), Relogio):
                    self._defaults.append((campo, default))
                    _trocar_default(campo, self.agora)
        self._ligado = True
        return self

    def desligar(self):
        if not self._ligado:
            return
        for campo, anterior in self._defaults:
            _trocar_default(campo, anterior)
        self._defaults = []
        timezone.now = self._anterior
        self._ligado = False


@contextmanager
def congelado_em(dia):
    """Um trecho de teste noutra data — por cima do relógio da suíte.

    `dia=None` é o relógio real, com o congelamento suspenso: é o que um
    teste usa quando precisa do dia de hoje de verdade (ver `relogio_real`).
    """
    relogio = Relogio(dia).ligar()
    try:
        yield relogio
    finally:
        relogio.desligar()


def relogio_real():
    """Um trecho de teste no relógio de verdade, com o congelamento suspenso."""
    return congelado_em(None)


def ligar_para_a_suite(escrever=print):
    """O que o runner chama: liga o relógio (ou não) e DIZ qual valeu.

    A frase vai para o log da suíte de propósito: é como se confere, num run
    do Actions, se aquela execução mediu a data congelada ou a real.
    """
    dia = data_congelada()
    if dia is None:
        escrever("Relógio: DATA REAL (%s=1) — a suíte mede o dia de hoje." % VARIAVEL_DATA_REAL)
        return None
    escrever(
        "Relógio: data congelada em %s (%s); %s=1 para o relógio real."
        % (dia.isoformat(), DIAS[dia.weekday()], VARIAVEL_DATA_REAL)
    )
    return Relogio(dia).ligar()
