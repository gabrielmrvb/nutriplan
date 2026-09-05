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
#: A ordem e os nomes são os dos CINCO PILARES (`accounts.models.Pilar`),
#: mais o Hoje na frente. A grade listava "Hoje, Treino, Histórico, Lista de
#: compras, Perfil" — sem Corrida, sem Hidratação, e com duas entradas que a
#: campanha decidiu que NÃO são pilares. Desde que o mapa das áreas passou a
#: aparecer na barra de cima desta mesma tela, a capa mostrava dois
#: inventários do produto que discordavam, e ela é a primeira coisa que um
#: avaliador vê.
AREAS = [
    # O painel usa o apelido e não `reverse()`: `plans:today` mora na raiz
    # da aplicação e reverteria para `/demo/`, que é esta própria capa.
    ("/demo/hoje/", "Hoje",
     "O orquestrador do dia: o que fazer agora, e como o dia está indo."),
    ("/demo/hoje/", "Alimentação",
     "O cardápio do dia, as refeições marcadas e a meta calórica."),
    ("workouts:routine", "Musculação",
     "A ficha da semana, com séries, cargas e o cronômetro de descanso."),
    ("workouts:corridas", "Corrida",
     "As corridas registradas, com distância e tempo — o traçado não sobe."),
    ("plans:hydration", "Hidratação",
     "Quanto você bebeu hoje, em goles, e como foi a semana."),
    ("plans:history", "Evolução",
     "Aderência, média de calorias e a curva de peso ao longo do tempo."),
    ("plans:shopping", "Lista de compras",
     "O que comprar para o cardápio da semana, agrupado por corredor."),
    ("accounts:profile", "Perfil",
     "Os dados que alimentam o cálculo: peso, altura, objetivo e treinos."),
]


def _endereco(rota: str) -> str:
    """O endereço de uma área dentro do demo.

    `reverse()` sozinho basta: a capa roda com o prefixo de script ligado, como
    todas as telas do demo, então ele já devolve `/demo/treino/`.

    Houve uma versão em que a capa rodava por fora do prefixo e este ajudante
    somava o `/demo` à mão. Ela tinha um defeito maior que a duplicação de
    prefixo: sem o prefixo, a capa renderizava com visitante anônimo, e a barra
    de cima oferecia "Entrar" e "Criar conta" — duas saídas do demo direto para
    a tela de login.
    """
    return rota if rota.startswith("/") else reverse(rota)


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
