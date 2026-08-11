#!/usr/bin/env python3
"""Gera build/qa[-fornecedor].html: cada pagina do PDF ao lado dos produtos extraidos.

Serve para conferir visualmente se nome, specs, codigo, preco e foto de cada
tile bateram com o catalogo original.

Uso:
    python3 tools/qa_report.py                    # Knup, todas as paginas
    python3 tools/qa_report.py 8 33 46             # Knup, so estas paginas
    python3 tools/qa_report.py onistek             # Onistek, todas as paginas
    python3 tools/qa_report.py onistek 5 9         # Onistek, so estas paginas
"""

from __future__ import annotations

import html
import json
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
DIR_BUILD = RAIZ / "build"

FORNECEDORES = {
    "knup": {
        "pdf": RAIZ / "catalogo" / "Knup_A_Vista_03082026.pdf",
        "produtos": RAIZ / "data" / "produtos.json",
        "precos": DIR_BUILD / "precos.json",
        "imagens": RAIZ / "assets" / "produtos",
        "saida": DIR_BUILD / "qa.html",
        "paginas": DIR_BUILD / "paginas",
    },
    "onistek": {
        "pdf": RAIZ / "catalogo" / "Onistek_A_Vista_10082026.pdf",
        "produtos": RAIZ / "data" / "produtos-onistek.json",
        "precos": DIR_BUILD / "precos-onistek.json",
        "imagens": RAIZ / "assets" / "produtos",
        "saida": DIR_BUILD / "qa-onistek.html",
        "paginas": DIR_BUILD / "paginas-onistek",
    },
}


def bloco_preco(info) -> str:
    if not info:
        return '<span class="preco">—</span>'
    partes = []
    if info.get("de"):
        partes.append(f'<s>R$ {info["de"]}</s>')
    partes.append(f'<span class="preco">R$ {info["valor"]}</span>')
    for f in info.get("faixas", []):
        partes.append(f'<small>{f["a_partir"]}{f["unidade"]}: {f["valor"]}</small>')
    return " ".join(partes)


def main() -> None:
    args = sys.argv[1:]
    fornecedor = "knup"
    if args and args[0].lower() in FORNECEDORES:
        fornecedor = args.pop(0).lower()
    cfg = FORNECEDORES[fornecedor]

    produtos = json.loads(cfg["produtos"].read_text("utf-8"))["produtos"]
    precos = {}
    if cfg["precos"].exists():
        precos = json.loads(cfg["precos"].read_text("utf-8"))

    por_pagina = defaultdict(list)
    for p in produtos:
        por_pagina[p["pagina"]].append(p)

    alvos = [int(a) for a in args] or sorted(por_pagina)
    dir_paginas = cfg["paginas"]
    dir_paginas.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(cfg["pdf"])
    caminho_imagens = "../" + str(cfg["imagens"].relative_to(RAIZ))

    partes = ["""<meta charset="utf-8"><title>QA — extração do catálogo</title>
<style>
 body{font:13px/1.45 system-ui;margin:0;background:#111;color:#eee}
 .pag{display:flex;gap:16px;padding:16px;border-bottom:2px solid #333}
 .pag>img{width:520px;height:auto;background:#fff;position:sticky;top:8px;align-self:flex-start}
 .itens{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;flex:1}
 .item{background:#1c1c1c;border:1px solid #333;border-radius:6px;padding:8px;font-size:12px}
 .item img{width:70px;height:70px;object-fit:contain;background:#fff;float:right;border-radius:4px}
 .cod{color:#7cf}.preco{color:#8f8;font-weight:700}.cat{color:#fa0;font-size:11px}
 .falta{outline:2px solid #f55}
 ul{margin:4px 0 0 14px;padding:0}li{margin:1px 0}
 h2{margin:0;padding:8px 16px;background:#222;font-size:14px}
</style>"""]

    for pno in alvos:
        img_pag = dir_paginas / f"p{pno:03d}.png"
        if not img_pag.exists():
            doc[pno - 1].get_pixmap(dpi=110).save(img_pag)
        itens = por_pagina.get(pno, [])
        partes.append(f'<h2>Página {pno} — {len(itens)} produtos</h2><div class="pag">')
        partes.append(f'<img src="{dir_paginas.name}/{img_pag.name}" loading="lazy">')
        partes.append('<div class="itens">')
        for p in itens:
            falta = "" if (p["nome"] and p["imagens"] and precos.get(p["codigo"])) else " falta"
            foto = (f'<img src="{caminho_imagens}/{p["imagens"][0]}-t.webp" loading="lazy">'
                    if p["imagens"] else "")
            specs = "".join(f"<li>{html.escape(s)}</li>" for s in p["specs"])
            partes.append(
                f'<div class="item{falta}">{foto}'
                f'<div class="cat">{html.escape(p["categoria"])}</div>'
                f'<b>{html.escape(p["nome"]) or "<i>SEM NOME</i>"}</b><br>'
                f'<span class="cod">{html.escape(p["codigo"])}</span> · '
                f'{bloco_preco(precos.get(p["codigo"]))} · '
                f'cx {p["qtd_caixa"] or "—"}'
                f'{" · <b>LANÇAMENTO</b>" if p["lancamento"] else ""}'
                f'<ul>{specs}</ul></div>')
        partes.append("</div></div>")

    saida = cfg["saida"]
    saida.write_text("\n".join(partes), "utf-8")
    print("gerado:", saida, f"({len(alvos)} páginas)")


if __name__ == "__main__":
    main()
