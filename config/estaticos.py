# -*- coding: utf-8 -*-
"""O storage de estáticos de produção: o do whitenoise, com a folha SEM
comentários (decisão do dono, 20/09/2026).

`static/css/app.css` é UM arquivo lido de ponta a ponta, com seções
numeradas e comentários que contam por que cada regra existe — isso é
decisão de código e não muda aqui. O que mudou é o que o NAVEGADOR recebe:
medido em produção na auditoria de 20/09, a folha tinha 340 067 bytes e 60 %
eram comentário; 106 KB gzip na primeira visita, a maior transferência
depois do HTML. Sem os comentários, 23 KB gzip — e a cobertura de regras
(CDP, 24 rotas × 2 temas × 2 larguras) mostrou que 87 % dos bytes de regra
são usados: o peso não era CSS morto.

Como funciona: o `collectstatic` chama `post_process` com um mapa
`nome -> (armazenamento de ORIGEM, caminho)`, e é sobre a ORIGEM (a pasta
`static/` do repositório) que o `ManifestStaticFilesStorage` calcula o hash
e reescreve as `url()`. Então a folha limpa vai para uma pasta temporária,
que passa a ser a origem dela — e para a cópia sem hash em STATIC_ROOT, que
o whitenoise também serve. O hash no nome passa a ser o do conteúdo servido:
cache nenhum guarda a versão errada, e `push/assets.py::version()` continua
lendo a fonte, como sempre.

É o único pós-processo do `collectstatic`, e continua sendo "sem build step"
no sentido que o CLAUDE.md protege: nada é compilado, nenhum arquivo é
gerado para o repositório, e a fonte é o que se edita.
"""
import os
import re
import tempfile

from django.core.files.storage import FileSystemStorage
from whitenoise.storage import CompressedManifestStaticFilesStorage

COMENTARIO = re.compile(r"/\*.*?\*/", re.S)
LINHAS_VAZIAS = re.compile(r"\n[ \t]*\n+")


def sem_comentarios(texto: str) -> str:
    """Tira todo `/* … */` e as linhas que ficam vazias; termina em uma quebra."""
    return LINHAS_VAZIAS.sub("\n", COMENTARIO.sub("", texto)).strip() + "\n"


class ArmazenamentoDeEstaticos(CompressedManifestStaticFilesStorage):
    """Whitenoise + a folha do app sem comentários antes do hash."""

    #: A única folha tocada: é a que foi medida. JS e o resto saem como estão.
    ALVO = "css/app.css"

    def post_process(self, paths, dry_run=False, **options):
        if not dry_run:
            for nome in list(paths):
                if nome.replace("\\", "/") != self.ALVO:
                    continue
                origem, caminho = paths[nome]
                with origem.open(caminho) as f:
                    texto = f.read().decode("utf-8")
                limpo = sem_comentarios(texto)
                pasta = tempfile.mkdtemp(prefix="nutriplan-css-")
                os.makedirs(os.path.join(pasta, "css"), exist_ok=True)
                for destino in (os.path.join(pasta, "css", "app.css"), self.path(nome)):
                    with open(destino, "w", encoding="utf-8", newline="\n") as f:
                        f.write(limpo)
                paths[nome] = (FileSystemStorage(pasta), self.ALVO)
        yield from super().post_process(paths, dry_run=dry_run, **options)
