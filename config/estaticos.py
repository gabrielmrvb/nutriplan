# -*- coding: utf-8 -*-
"""PROTÓTIPO (auditoria 20/09/2026, Fase 3): a folha vai para o navegador SEM
os comentários.

Medido em produção: `app.css` tem 340 067 bytes, e 60 % são comentário — o
arquivo é lido de ponta a ponta por quem programa, e isso é decisão. Mas o
navegador de quem usa recebia os comentários também: 106 KB gzip na primeira
visita (a maior transferência depois do HTML); sem os comentários, 23 KB
gzip. A fonte continua UM arquivo comentado; o que muda é a cópia que o
`collectstatic` entrega, antes de ganhar o hash no nome. Não mergeia sem
decisão do dono ("nada de build step" está no CLAUDE.md — isto é um
pós-processo do collectstatic, e a decisão de chamá-lo de build é dele).
"""
import os
import re
import tempfile

from django.core.files.storage import FileSystemStorage
from whitenoise.storage import CompressedManifestStaticFilesStorage

COMENTARIO = re.compile(r"/\*.*?\*/", re.S)
LINHAS_VAZIAS = re.compile(r"\n[ \t]*\n+")


def sem_comentarios(texto: str) -> str:
    return LINHAS_VAZIAS.sub("\n", COMENTARIO.sub("", texto)).strip() + "\n"


class ArmazenamentoDeEstaticos(CompressedManifestStaticFilesStorage):
    """Igual ao do whitenoise, com uma passada antes do hash: o CSS perde os
    comentários. O hash no nome do arquivo passa a ser o do conteúdo servido,
    então cache nenhum guarda a versão errada."""

    def post_process(self, paths, dry_run=False, **options):
        # `paths` mapeia nome -> (armazenamento de ORIGEM, caminho): o hash é
        # calculado sobre a origem (a pasta `static/` do repositório), não
        # sobre a cópia em STATIC_ROOT. A folha limpa vai para uma pasta
        # temporária que passa a ser a origem dela — e para a cópia sem hash.
        if not dry_run:
            for nome in list(paths):
                if nome.replace("\\", "/").endswith("css/app.css"):
                    origem, caminho = paths[nome]
                    with origem.open(caminho) as f:
                        texto = f.read().decode("utf-8")
                    limpo = sem_comentarios(texto)
                    pasta = tempfile.mkdtemp(prefix="nutriplan-css-")
                    os.makedirs(os.path.join(pasta, "css"), exist_ok=True)
                    for destino in (os.path.join(pasta, "css", "app.css"), self.path(nome)):
                        with open(destino, "w", encoding="utf-8", newline="\n") as f:
                            f.write(limpo)
                    paths[nome] = (FileSystemStorage(pasta), "css/app.css")
        yield from super().post_process(paths, dry_run=dry_run, **options)
