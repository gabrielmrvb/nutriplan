"""Versão dos arquivos estáticos, para nenhum cache servir CSS velho.

Em 24/08/2026 um deploy de layout chegou pela metade no navegador: o HTML era
o novo e a folha de estilo era a antiga, servida do cache. O resultado não é
"uma versão atrás" — é o app inteiro sem estilo, porque marcação nova não casa
com CSS velho. Aconteceu em três camadas ao mesmo tempo (cache do service
worker, cache HTTP do navegador e cache do `fetch` dentro do próprio service
worker), e corrigir uma de cada vez só troca qual delas quebra da próxima.

A solução que resolve as três de uma vez é não deixar o endereço do arquivo
repetir: `app.css?v=<hash do conteúdo>`. Conteúdo novo, URL nova, cache nenhum
tem o que servir de errado — e o arquivo velho continua cacheável para sempre,
que é o comportamento que a gente queria desde o começo.

**O hash não pode ser calculado uma vez por processo.** Foi a primeira versão
disto, e ela reintroduziu o bug em desenvolvimento: o `runserver` recarrega
quando um `.py` ou um template muda, não quando o CSS muda, então o processo
seguia servindo a URL antiga para um arquivo novo. Agora o custo por requisição
é dois `os.stat`, e o conteúdo só é relido quando data ou tamanho mudam.
"""
from hashlib import blake2b
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

#: Arquivos que participam da versão. São os que descrevem a aparência e o
#: comportamento do app — os que precisam chegar juntos com o HTML.
VERSIONED = ("css/app.css", "js/pwa.js", "js/fila.js")

#: {caminho: (assinatura do stat, hash do conteúdo)}
_cache = {}


def _find(relative_path: str):
    """Onde o arquivo mora: na pasta de origem ou na coletada pelo collectstatic."""
    for base in [*settings.STATICFILES_DIRS, settings.STATIC_ROOT]:
        candidate = Path(base) / relative_path
        if candidate.exists():
            return candidate
    return None


def _digest_of(relative_path: str) -> bytes:
    path = _find(relative_path)
    if path is None:
        return relative_path.encode()

    info = path.stat()
    signature = (info.st_mtime_ns, info.st_size)
    cached = _cache.get(path)
    if cached is None or cached[0] != signature:
        _cache[path] = (signature, blake2b(path.read_bytes(), digest_size=8).digest())
    return _cache[path][1]


def version() -> str:
    """Oito caracteres que mudam quando qualquer arquivo versionado muda."""
    digest = blake2b(digest_size=4)
    for relative_path in VERSIONED:
        digest.update(_digest_of(relative_path))
    return digest.hexdigest()


def asset(relative_path: str) -> str:
    """URL do estático com a versão pendurada: `/static/css/app.css?v=1a2b3c4d`."""
    return f"{static(relative_path)}?v={version()}"


def reset_cache():
    """Esquece o que já foi lido. Existe para os testes, que trocam arquivos."""
    _cache.clear()
