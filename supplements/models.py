"""Suplementos: o catálogo e o que foi tomado hoje.

Duas decisões sobre o escopo, tomadas antes de escrever o modelo.

**Não é prescrição.** O app mostra a faixa de dose que a literatura usa e diz
para que serve — não decide por ninguém, não sabe o que a pessoa toma de
remédio e não conhece a função renal dela. Cada tela carrega isso escrito, e o
campo `cuidado` existe para os casos em que a ressalva é específica.

**Mito e fato juntos.** O campo `mito` não é enfeite: quase todo suplemento
desta lista carrega uma crença errada mais popular que a informação certa —
creatina "faz mal ao rim", whey "é obrigatório", pré-treino "é pré-requisito.
Desmentir ao lado da dose é o que separa um catálogo de uma vitrine.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.formats import number_format
from django.utils import timezone


class Attribute(models.TextChoices):
    """Para que o suplemento serve, em uma palavra.

    Vira pílula na tela, e é o que permite a pessoa varrer seis cartões e
    achar o que interessa sem ler seis parágrafos.
    """

    FORCA = "forca", "Força"
    RECUPERACAO = "recuperacao", "Recuperação"
    RESISTENCIA = "resistencia", "Resistência"
    SAUDE = "saude", "Saúde"
    ENERGIA = "energia", "Energia"
    PROTEINA = "proteina", "Proteína"


class Evidence(models.TextChoices):
    """Quanta ciência sustenta o uso.

    Está aqui porque é a informação que mais falta numa loja de suplemento e a
    que mais muda a decisão: creatina e whey não estão no mesmo patamar de
    pré-treino, e dizer isso é mais útil que qualquer descrição.
    """

    FORTE = "forte", "Evidência forte"
    MODERADA = "moderada", "Evidência moderada"
    LIMITADA = "limitada", "Evidência limitada"


class Unit(models.TextChoices):
    G = "g", "g"
    MG = "mg", "mg"
    DOSE = "dose", "dose"


class Supplement(models.Model):
    slug = models.SlugField("apelido", max_length=40, unique=True)
    name = models.CharField("nome", max_length=60)
    purpose = models.CharField("para que serve", max_length=140)

    attributes = models.JSONField("atributos", default=list, blank=True)
    evidence = models.CharField(
        "evidência", max_length=10, choices=Evidence.choices, default=Evidence.MODERADA
    )

    # A dose vem em duas formas porque os suplementos vêm em duas formas: uns
    # escalam com o peso (creatina, cafeína), outros não (ômega-3,
    # multivitamínico). Guardar as duas evita inventar um "por kg" falso para
    # quem não tem.
    dose_per_kg = models.DecimalField(
        "dose por kg", max_digits=6, decimal_places=3, null=True, blank=True
    )
    dose_fixed = models.DecimalField(
        "dose fixa", max_digits=7, decimal_places=2, null=True, blank=True
    )
    unit = models.CharField("unidade", max_length=6, choices=Unit.choices, default=Unit.G)
    dose_note = models.CharField("sobre a dose", max_length=160, blank=True)
    timing = models.CharField("quando tomar", max_length=120, blank=True)

    myth = models.CharField("mito", max_length=200, blank=True)
    fact = models.CharField("fato", max_length=240, blank=True)
    #: Ressalva específica deste suplemento, quando existe. Fica em destaque.
    caution = models.CharField("cuidado", max_length=240, blank=True)

    order = models.PositiveSmallIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "suplemento"
        verbose_name_plural = "suplementos"
        ordering = ("order", "name")

    def __str__(self):
        return self.name

    # ------------------------------------------------------------- dose
    def dose_para(self, weight_kg):
        """A dose do dia para este peso, já arredondada para o mundo real.

        Arredonda para meio grama porque ninguém pesa creatina em balança de
        precisão: a dosadora do pote tem 5 g e a colher de chá, cerca de 3.
        Devolver "4,63 g" seria exato e inútil.
        """
        if self.dose_per_kg and weight_kg:
            bruto = Decimal(weight_kg) * self.dose_per_kg
            if self.unit == Unit.MG:
                return int(round(bruto / 10) * 10)
            return (bruto * 2).quantize(Decimal("1")) / 2
        return self.dose_fixed

    def dose_display(self, weight_kg=None) -> str:
        """A dose escrita como o resto do app escreve número.

        Passa pelo formatador de localidade em vez de interpolar direto: o app
        é pt-br e mostra "62,50" no campo de carga: uma dose de "2.5 g" na
        mesma tela é a emenda que denuncia que aquele pedaço foi escrito por
        outra pessoa. E `normalize()` antes, para "1.00 dose" virar "1 dose" —
        Decimal guarda as casas significativas e as imprime todas.
        """
        valor = self.dose_para(weight_kg)
        if valor is None:
            return "conforme o rótulo"

        if isinstance(valor, Decimal):
            texto = number_format(valor.normalize(), use_l10n=True)
        else:
            texto = number_format(valor, use_l10n=True)

        if self.unit == Unit.DOSE:
            return f"{texto} dose" + ("s" if valor != 1 else "")
        return f"{texto} {self.get_unit_display()}"

    @property
    def attribute_labels(self) -> list:
        rotulos = dict(Attribute.choices)
        return [rotulos.get(a, a) for a in (self.attributes or [])]


class SupplementLog(models.Model):
    """Um toque: tomei isto hoje.

    Sem quantidade e sem horário de propósito. O checklist existe para ser
    resolvido num toque entre uma coisa e outra — pedir quantos gramas foram
    transformaria a marcação num formulário, e formulário no meio do dia é o
    que ninguém preenche.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supplement_logs",
    )
    supplement = models.ForeignKey(
        Supplement, on_delete=models.CASCADE, related_name="logs"
    )
    date = models.DateField("data", default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "suplemento tomado"
        verbose_name_plural = "suplementos tomados"
        ordering = ("-date",)
        constraints = [
            # Um por dia. Sem isto, tocar duas vezes no mesmo botão criaria dois
            # registros e o checklist passaria a mentir sobre o próprio estado.
            models.UniqueConstraint(
                fields=("user", "supplement", "date"), name="um_suplemento_por_dia"
            )
        ]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.supplement} em {self.date}"
