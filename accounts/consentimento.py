# -*- coding: utf-8 -*-
"""Os três consentimentos que o app pede, e a régua de "ainda falta".

Por que existem (decisão do dono, 21/09/2026, sobre a pesquisa legal):

- dado de saúde só se trata com consentimento "específico e destacado, para
  finalidades específicas" (LGPD art. 11, I) — e "execução de contrato" NÃO
  está no art. 11, então "usar o app" não serve de base;
- guardar o dado nos Estados Unidos (Render em Oregon, Neon) é transferência
  internacional para país sem decisão de adequação da ANPD (só a União
  Europeia tem, Res. 32/2026), e o caminho é o consentimento "específico e
  em destaque … com informação prévia sobre o caráter internacional da
  operação" (art. 33, VIII);
- os Termos e a Política são a relação contratual, e o aceite deles é
  "cláusula destacada das demais" (art. 8º, § 1º) — por isso são TRÊS caixas
  e não um "li e aceito tudo".

A VERSÃO é a data do texto. Mudou o texto de forma que altere o que a pessoa
consentiu, sobe a versão aqui e nos legais, e todo mundo consente de novo
uma vez — é o que `faltam` calcula. O perfil guarda a versão consentida
(`Profile.consentimento_versao`) para a guarda das telas não custar consulta;
`Consentimento` guarda a prova, linha a linha.
"""
from django import forms
from django.db import transaction
from django.utils import timezone

from .models import Consentimento, Profile

#: A data dos textos vigentes de Termos e Política — a mesma que as duas
#: páginas mostram em "Última atualização". Subir isto pede consentimento de
#: novo a todo mundo; só se sobe quando o que se consente mudou.
VERSAO_DOS_LEGAIS = "2026-09-21"

TIPOS = (
    Consentimento.Tipo.TERMOS,
    Consentimento.Tipo.SAUDE,
    Consentimento.Tipo.TRANSFERENCIA,
)

#: O texto de cada caixa, curto e completo: o que é tratado, para quê, e
#: que sem isso o app não funciona (art. 9º, § 3º). Os Termos entram por
#: link no template, não aqui.
ROTULOS = {
    Consentimento.Tipo.TERMOS: "Li e aceito os Termos de Uso e a Política de Privacidade.",
    Consentimento.Tipo.SAUDE: (
        "Autorizo o NutriPlan a tratar meus dados de saúde — sexo, data de "
        "nascimento, altura, peso, objetivo, refeições, cargas e corridas — "
        "para calcular a estimativa de calorias, montar o cardápio de exemplo "
        "e a ficha de treino e acompanhar o que eu registrar. Sem isso o app "
        "não funciona."
    ),
    Consentimento.Tipo.TRANSFERENCIA: (
        "Estou ciente de que meus dados ficam em servidores nos Estados Unidos "
        "(Render, em Oregon, e Neon) e autorizo essa transferência "
        "internacional. Sem isso o app não funciona."
    ),
}

MENSAGEM_DE_ERRO = "Para continuar, marque esta caixa."


def versao_consentida(perfil_ou_usuario) -> str:
    """A versão para a qual a pessoa já consentiu os três, ou ''.

    Lê o perfil quando ele já está em mãos (a guarda das telas), e o banco
    quando recebe o usuário — o cadastro ainda não tem perfil."""
    if isinstance(perfil_ou_usuario, Profile):
        return perfil_ou_usuario.consentimento_versao
    try:
        perfil = perfil_ou_usuario.profile
    except Profile.DoesNotExist:
        perfil = None
    return perfil.consentimento_versao if perfil is not None else ""


def deve_consentir(perfil) -> bool:
    """A guarda das telas do app, para o perfil JÁ CARREGADO — zero consultas.

    Verdadeiro para a conta que existia antes dos legais e ainda não passou
    pela tela de consentimento (`precisa_consentir`, ligado pela migration),
    e para quem consentiu uma versão ANTERIOR dos textos. Falso para quem
    consentiu a versão vigente e para o perfil sem versão nenhuma que não foi
    marcado — o de fixture e de seed, que nunca passou pelo cadastro."""
    if perfil.precisa_consentir:
        return True
    return bool(perfil.consentimento_versao) and perfil.consentimento_versao != VERSAO_DOS_LEGAIS


def faltam(perfil_ou_usuario) -> set:
    """Os tipos que ainda não foram consentidos NA VERSÃO VIGENTE.

    Com o perfil carimbado na versão vigente, nada falta — zero consultas.
    Senão, olha as linhas de `Consentimento` desta versão: quem aceitou os
    Termos no formulário de e-mail e ainda não passou pela etapa 1 tem uma
    das três, e a etapa só pede as outras duas."""
    if versao_consentida(perfil_ou_usuario) == VERSAO_DOS_LEGAIS:
        return set()
    user = perfil_ou_usuario.user if isinstance(perfil_ou_usuario, Profile) else perfil_ou_usuario
    dados = set(
        Consentimento.objects.filter(user=user, versao=VERSAO_DOS_LEGAIS).values_list("tipo", flat=True)
    )
    return {str(tipo) for tipo in TIPOS} - dados


@transaction.atomic
def registrar(user, tipos, perfil=None) -> None:
    """Grava os consentimentos dados (idempotente por versão) e, quando os
    três estão dados, carimba o perfil — o que libera as telas do app."""
    agora = timezone.now()
    for tipo in tipos:
        Consentimento.objects.get_or_create(
            user=user, tipo=tipo, versao=VERSAO_DOS_LEGAIS, defaults={"dado_em": agora}
        )
    if perfil is None:
        try:
            perfil = user.profile
        except Profile.DoesNotExist:
            perfil = None
    if perfil is not None and perfil.pk and not faltam(user):
        perfil.consentimento_versao = VERSAO_DOS_LEGAIS
        perfil.precisa_consentir = False
        perfil.save(update_fields=["consentimento_versao", "precisa_consentir"])


class ConsentimentoForm(forms.Form):
    """As caixas que ainda faltam — só elas. Cada uma é obrigatória, e o erro
    fica ao lado da caixa, não no topo."""

    def __init__(self, *args, tipos=TIPOS, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipos = [str(tipo) for tipo in tipos]
        for tipo in self.tipos:
            self.fields[tipo] = forms.BooleanField(
                required=True, label=ROTULOS[tipo], error_messages={"required": MENSAGEM_DE_ERRO}
            )

    @property
    def vazio(self) -> bool:
        return not self.tipos

    @property
    def primeira_com_erro(self) -> str:
        """O nome da primeira caixa recusada — é ela que recebe `autofocus`
        ao reabrir, para o navegador rolar até o erro (as caixas ficam no fim
        do formulário, abaixo da dobra). Vazio quando nada foi recusado."""
        if not self.is_bound:
            return ""
        return next((tipo for tipo in self.tipos if self.errors.get(tipo)), "")

    def registrar(self, user, perfil=None):
        registrar(user, self.tipos, perfil=perfil)
