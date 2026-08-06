#!/usr/bin/env python3
"""Gera build/qa.html: cada pagina do PDF renderizada ao lado dos produtos extraidos.

Serve para conferir visualmente se nome, specs, codigo, preco e foto de cada
tile bateram com o catalogo original.

Uso:
    python3 tools/qa_report.py            # todas as paginas com produtos
    python3 tools/qa_report.py 8 33 46    # apenas estas paginas
"""

from __future__ import annotations

import html
import json
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
PDF = RAIZ / "catalogo" / "Knup_A_Vista_03082026.pdf"
DIR_BUILD = RAIZ / "build"
DIR_PAGINAS = DIR_BUILD / "paginas"


def main() -> None:
    produtos = json.loads((RAIZ / "data" / "produtos.json").read_text("utf-8"))["produtos"]
    precos = {}
    arq_precos = DIR_BUILD / "precos.json"
    if arq_precos.exists():
        precos = json.loads(arq_precos.read_text("utf-8"))

    por_pagina = defaultdict(list)
    for p in produtos:
        por_pagina[p["pagina"]].append(p)

    alvos = [int(a) for a in sys.argv[1:]] or sorted(por_pagina)
    DIR_PAGINAS.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)

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
        img_pag = DIR_PAGINAS / f"p{pno:03d}.png"
        if not img_pag.exists():
            doc[pno - 1].get_pixmap(dpi=110).save(img_pag)
        itens = por_pagina.get(pno, [])
        partes.append(f'<h2>Página {pno} — {len(itens)} produtos</h2><div class="pag">')
        partes.append(f'<img src="paginas/{img_pag.name}" loading="lazy">')
        partes.append('<div class="itens">')
        for p in itens:
            falta = "" if (p["nome"] and p["imagens"] and precos.get(p["codigo"])) else " falta"
            foto = (f'<img src="../assets/produtos/{p["imagens"][0]}-t.webp" loading="lazy">'
                    if p["imagens"] else "")
            specs = "".join(f"<li>{html.escape(s)}</li>" for s in p["specs"])
            partes.append(
                f'<div class="item{falta}">{foto}'
                f'<div class="cat">{html.escape(p["categoria"])}</div>'
                f'<b>{html.escape(p["nome"]) or "<i>SEM NOME</i>"}</b><br>'
                f'<span class="cod">{html.escape(p["codigo"])}</span> · '
                f'<span class="preco">R$ '
                f'{(precos.get(p["codigo"]) or {}).get("valor", "—")}</span> · '
                f'cx {p["qtd_caixa"] or "—"}'
                f'{" · <b>LANÇAMENTO</b>" if p["lancamento"] else ""}'
                f'<ul>{specs}</ul></div>')
        partes.append("</div></div>")

    saida = DIR_BUILD / "qa.html"
    saida.write_text("\n".join(partes), "utf-8")
    print("gerado:", saida, f"({len(alvos)} páginas)")


if __name__ == "__main__":
    main()
