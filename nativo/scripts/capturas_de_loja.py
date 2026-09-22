# -*- coding: utf-8 -*-
"""As capturas de LISTAGEM das duas lojas, tiradas das telas de verdade
(Fase 3 da missão Capacitor, 22/09/2026).

Fonte: a CONTA do demo (a pessoa fictícia do seed, com dieta, treino e
histórico cheios), num servidor local, logada — e não as rotas `/demo/`:
aquelas trazem a faixa "Ambiente de demonstração" e o selo DEMO, que não
são o app. Nada de conta real, nada de dado de gente. `--cookie` recebe a
sessão (o `conta_de_loja.py` a cria). O navegador é
o Chrome que o `agent-browser` instala, dirigido por CDP
(`scripts/qa/nav.py`), porque a loja pede PIXEL EXATO e só o
`deviceScaleFactor` do `Emulation.setDeviceMetricsOverride` entrega isso
sem esticar imagem:

    iPhone 6.9"  1290×2796   (obrigatório na App Store)
    iPhone 6.5"  1242×2688   (obrigatório para quem ainda suporta)
    iPad 13"     2048×2732   (obrigatório porque o app aceita iPad)
    Telefone     1080×1920   (Play Store)
    Tablet 7"    1200×1920   (Play, opcional)
    Tablet 10"   1600×2560   (Play, opcional)

    ../../.venv/Scripts/python.exe capturas_de_loja.py [--base URL] [--saida PASTA] [--tema dark|light]
"""
import argparse
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "qa"))
import nav  # noqa: E402

#: (nome, largura em px, altura em px, escala). A largura CSS é largura/escala.
APARELHOS = [
    ("ios-6.9", 1290, 2796, 3),
    ("ios-6.5", 1242, 2688, 3),
    ("ipad-13", 2048, 2732, 2),
    ("android-telefone", 1080, 1920, 3),
    ("android-tablet-7", 1200, 1920, 2),
    ("android-tablet-10", 1600, 2560, 2),
]

#: (arquivo, caminho, espera) — a ordem é a da listagem.
TELAS = [
    ("1-hoje", "/", 3.0),
    ("2-treino", "/treino/", 2.5),
    ("3-execucao", "/treino/agora/", 2.5),
    ("4-progresso", "/historico/", 2.5),
    ("5-agua", "/hidratacao/", 2.0),
]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=os.environ.get("NUTRIPLAN_URL", "https://nutriplan-xxfn.onrender.com"))
    p.add_argument("--saida", default="capturas-loja")
    p.add_argument("--tema", default="dark", choices=["dark", "light"])
    p.add_argument("--cookie", default=os.environ.get("NUTRIPLAN_SESSAO", ""), help="sessionid da conta de vitrine")
    args = p.parse_args(argv)

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    s = nav.Sessao("loja")
    if args.cookie:
        from urllib.parse import urlparse
        s.cmd("Network.enable")
        s.cmd("Network.setCookie", name="sessionid", value=args.cookie, domain=urlparse(args.base).hostname, path="/")
    s.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": args.tema},
                                                  {"name": "prefers-reduced-motion", "value": "reduce"}])
    feitas = []
    for nome, largura, altura, escala in APARELHOS:
        s.cmd("Emulation.setDeviceMetricsOverride", width=largura // escala, height=altura // escala,
              deviceScaleFactor=escala, mobile=escala == 3)
        for arquivo, caminho, espera in TELAS:
            s.cmd("Page.navigate", url=args.base + caminho)
            time.sleep(espera)
            dados = s.cmd("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            alvo = saida / ("%s-%s.png" % (nome, arquivo))
            alvo.write_bytes(base64.b64decode(dados["data"]))
            feitas.append(alvo)
            print("%-18s %-12s %6d bytes  %s" % (nome, arquivo, alvo.stat().st_size, alvo))
    print("capturas:", len(feitas), "em", saida)
    return feitas


if __name__ == "__main__":
    main()
