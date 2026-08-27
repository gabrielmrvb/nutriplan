"""A capa do demo e a página que explica o que ele é."""
from django.urls import reverse
from django.views.generic import TemplateView

from workouts.models import Split

from .middleware import PREFIXO, usuario_demo


#: As áreas do app, na ordem em que fazem sentido para quem chega de fora.
#:
#: Só existe aqui o que existe no app. A lista é escrita à mão e não gerada da
#: URLconf de propósito: rota não é área — `/conta/onboarding/3/` é uma rota e
#: não é um lugar para onde mandar um visitante.
AREAS = [
    # O painel usa o apelido e não `reverse()`: `plans:today` mora na raiz
    # da aplicação e reverteria para `/demo/`, que é esta própria capa.
    ("/demo/hoje/", "Hoje",
     "O painel do dia: meta calórica, macros, cardápio, água e ofensiva."),
    ("workouts:routine", "Treino",
     "A ficha da semana, com séries, cargas e o cronômetro de descanso."),
    ("supplements:list", "Suplementos",
     "O checklist do dia e o que cada suplemento faz, com nível de evidência."),
    ("plans:history", "Histórico",
     "Aderência, média de calorias e a curva de peso ao longo do tempo."),
    ("plans:shopping", "Lista de compras",
     "O que comprar para o cardápio da semana, agrupado por corredor."),
    ("accounts:profile", "Perfil",
     "Os dados que alimentam o cálculo: peso, altura, objetivo e treinos."),
]


def _endereco(rota: str) -> str:
    """O endereço de uma área dentro do demo.

    A capa é a única página do demo que roda SEM o prefixo de script — ela é
    uma rota própria, e não uma tela do app remontada. Então aqui o `/demo` é
    somado à mão: `reverse()` devolveria `/treino/`, que exige login.
    """
    if rota.startswith("/"):
        return rota
    return PREFIXO + reverse(rota)


class DemoHomeView(TemplateView):
    template_name = "demo/index.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        usuario = usuario_demo()
        perfil = getattr(usuario, "profile", None)
        plano = usuario.plans.filter(is_active=True).first() if usuario else None
        ficha = usuario.training_plans.filter(is_active=True).first() if usuario else None
        contexto.update(
            {
                "areas": [
                    {"url": _endereco(rota), "nome": nome, "descricao": descricao}
                    for rota, nome, descricao in AREAS
                ],
                "pessoa": usuario,
                "perfil": perfil,
                "plano": plano,
                "ficha": ficha,
                "divisao": ficha.get_split_display() if ficha else "",
                "nav": None,
            }
        )
        return contexto


class DemoSobreView(TemplateView):
    template_name = "demo/sobre.html"
