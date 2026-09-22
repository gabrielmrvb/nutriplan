"""A tela de quem está logado não pode ser reusada do disco depois do logout.

Medido em 22/09/2026 numa sessão logada do staging: `/historico/`, `/treino/`
e `/conta/perfil/` respondiam sem `Cache-Control` nenhum. Sem diretiva o
navegador guarda por heurística, e o que ele guarda aqui é peso, altura,
e-mail, objetivo e histórico de treino — dado de saúde. Num aparelho de casa,
sair da conta e apertar VOLTAR redesenhava a tela da pessoa anterior a partir
do disco, sem passar pelo servidor.

A diretiva escolhida é `private, no-cache, must-revalidate`. As três partes:

- `private` tira a página de qualquer cache compartilhado (o `Vary: Cookie`
  já ajudava, mas ele é uma dica de chaveamento, não uma proibição);
- `no-cache` obriga a REVALIDAR antes de reusar; depois do logout a
  revalidação devolve o 302 do login, e é isso que apaga a tela de trás;
- `must-revalidate` fecha a brecha do cache que responde do próprio estoque
  quando a rede falha.

E o que ela NÃO diz é tão decidido quanto o que diz: **nada de `no-store`**.
O service worker recusa guardar resposta com `no-store` (`podeGuardar`, em
`templates/pwa/sw.js`), e é o cache dele que faz a dieta abrir no metrô;
e o Chrome desliga o bfcache numa página `no-store`, que é exatamente o
"Voltar ao formulário" do 403 devolvendo o que a pessoa digitou. As duas
coisas são funcionalidades provadas deste app, e `no-store` derrubaria as
duas para ganhar sobre `no-cache` só o caso de quem lê o disco com
ferramenta forense — que já tem o banco do IndexedDB e o cache do worker ali
do lado.

Quem já declara a própria diretiva não é tocado: `never_cache` no login e na
gestão, `no-store` na exportação de dados. A regra só preenche o silêncio.
"""

from django.utils.functional import empty

#: A resposta é do dono da sessão, e vale só depois de perguntar ao servidor.
PRIVADA = "private, no-cache, must-revalidate"


class CachePrivadoMiddleware:
    """Marca como privada toda resposta HTML de uma sessão autenticada.

    Fica no FIM de `MIDDLEWARE` (o mais interno), para a fase de resposta
    rodar antes do gzip e depois de a view já ter dito o que tinha a dizer —
    e depois de `AuthenticationMiddleware`, que é quem põe `request.user`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        if resposta.has_header("Cache-Control"):
            return resposta
        # `text/html` e não "toda resposta": o JSON das rotas de fila e o
        # arquivo da exportação seguem outras regras, e o estático nem chega
        # aqui (o WhiteNoise responde antes).
        if not resposta.get("Content-Type", "").startswith("text/html"):
            return resposta
        # `request.user` é um `SimpleLazyObject`: LÊ-LO aqui forçaria a
        # consulta de sessão em toda resposta, e `/saude/vivo/` promete ZERO
        # consultas (a suíte reprovou exatamente por isso — o mesmo cuidado
        # que `config.observabilidade.usuario_anonimo` já documentava). Se a
        # view não resolveu o usuário, não havia dado de ninguém na tela.
        usuario = getattr(request, "user", None)
        if usuario is None or getattr(usuario, "_wrapped", None) is empty:
            return resposta
        if usuario.is_authenticated:
            resposta["Cache-Control"] = PRIVADA
        return resposta
