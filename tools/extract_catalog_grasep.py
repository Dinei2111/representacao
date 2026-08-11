#!/usr/bin/env python3
"""Extrai o catalogo Grasep (PDF) para JSON + imagens WebP.

O layout do Grasep e bem diferente do Knup (sem fonte fixa por tipo de
elemento — cada secao usa uma familia diferente), mas os marcadores do
produto se repetem em todo o catalogo, em qualquer fonte:

  - codigo: uma linha curta so com o codigo, tipo 'D-X006' ou 'Modelo: D-AI05'
  - quantidade por caixa: 'NNPÇS/CAIXA' (ou 'N PÇS/CAIXA') perto do codigo
  - preco: 'R$ NNN,NN' seguido de 'por' — o catalogo nao usa preco riscado
    nem faixa por volume, um preco por produto
  - nome: a linha em negrito, tamanho >= 7.5pt, que vem antes do codigo

A grade de tiles e montada a partir da posicao dos codigos (como no Knup):
agrupa por linha (mesma faixa de y), corta colunas no meio do caminho entre
codigos vizinhos, e fecha a base de cada linha depois do preco daquela linha
(nao no meio do caminho pro proximo codigo — o nome do produto seguinte fica
bem mais perto do proprio codigo do que o preco do produto anterior).

Uso:
    python3 tools/extract_catalog_grasep.py [--paginas 2-31] [--sem-imagens]

Atualiza (faz merge, sem apagar os produtos de outros fornecedores):
    data/produtos.json      catalogo sem precos (vai para o site)
    build/precos.json       precos por codigo
    assets/produtos/*.webp  fotos 428px + thumbs 200px
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pymupdf
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
PDF = RAIZ / "catalogo" / "Grasep_A_Vista_03082026.pdf"
DIR_DADOS = RAIZ / "data"
DIR_BUILD = RAIZ / "build"
DIR_IMG = RAIZ / "assets" / "produtos"
FORNECEDOR = "Grasep"

RE_CODIGO = re.compile(r"^(?=[A-Z0-9]*[A-Z])[A-Z0-9]{1,8}-[A-Za-z0-9./+]+(?:\s[A-Z]{2,4})?$")
RE_CODIGO_MODELO = re.compile(r"Modelo\s*:?\s*([A-Z0-9]{1,8}-[A-Za-z0-9./+]+)", re.I)
RE_QTD = re.compile(r"^(\d{1,4})\s*P[ÇC]S?/?\s*CAIXA$", re.I)
RE_QTD_BUSCA = re.compile(r"(\d{1,4})\s*P[ÇC]S?/?\s*CAIXA", re.I)
RE_PRECO = re.compile(r"^R\$\s*([\d.\s]*\d,\d{2})$")
RE_BULLET = re.compile(r"^[•·]")
RE_DIMENSAO = re.compile(r"^[\d.,*x ]+(MM|CM)$", re.I)
RE_DATA_PAGINA = re.compile(r"^\d{1,2}/\d{1,2}(?:/\d{4})?$")

# tokens curtos com fonte de icone que passam pelo regex de codigo por acaso
RUIDO_CODIGO = {"HI-FI"}

# paginas sem grade de produtos (sumario/capa/contracapa)
PAGINAS_IGNORADAS = {1, 32}

MARGEM_TOPO = 32.0     # pula a faixa da data/categoria/numero de pagina
MARGEM_RODAPE = 15.0


def limpar(texto: str) -> str:
    texto = texto.replace("ﬁ", "fi").replace("ﬂ", "fl").replace(" ", " ")
    texto = unicodedata.normalize("NFC", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return " ".join(_sem_repeticoes(texto.split(" ")))


def _sem_repeticoes(partes: list[str]) -> list[str]:
    """O PDF desenha alguns rotulos em dobro (negrito por sobreposicao):
    'MAXIMUS i7 MAXIMUS i7 TELA 23.8" TELA 23.8"' -> 'MAXIMUS i7 TELA 23.8"'."""
    resultado, i = [], 0
    while i < len(partes):
        for tam in range(min(6, (len(partes) - i) // 2), 0, -1):
            if partes[i:i + tam] == partes[i + tam:i + 2 * tam]:
                resultado.extend(partes[i:i + tam])
                i += 2 * tam
                break
        else:
            resultado.append(partes[i])
            i += 1
    return resultado


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "item"


def coletar_linhas(pagina) -> list[dict]:
    """Uma linha de texto por item (join dos spans), com a fonte do maior span."""
    linhas = []
    for blk in pagina.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            spans = ln["spans"]
            if not spans:
                continue
            texto = limpar("".join(sp["text"] for sp in spans))
            if not texto:
                continue
            maior = max(spans, key=lambda sp: sp["size"])
            x0, y0, x1, y1 = ln["bbox"]
            linhas.append({
                "texto": texto, "tam": round(maior["size"], 1),
                "negrito": bool(re.search(r"bold|black|heavy", maior["font"], re.I)),
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
            })
    return linhas


def extrair_codigo(texto: str) -> tuple[str, int | None] | None:
    """Codigo do produto e, se a quantidade por caixa vier colada na mesma
    linha ('Modelo: A24E99-05      3 PÇS/CAIXA'), a quantidade tambem."""
    m = RE_CODIGO_MODELO.search(texto)
    if m and any(c.isdigit() for c in m.group(1)):
        qm = RE_QTD_BUSCA.search(texto[m.end():])
        return m.group(1).upper(), (int(qm.group(1)) if qm else None)
    if RE_CODIGO.match(texto) and any(c.isdigit() for c in texto) and texto.upper() not in RUIDO_CODIGO:
        return texto.upper(), None
    return None


def riscos_da_pagina(pagina) -> list:
    """Tracos horizontais finos da pagina — e assim que o catalogo risca o
    preco antigo numa promocao (igual ao catalogo Knup)."""
    return [d["rect"] for d in pagina.get_drawings() if d["rect"].height <= 2.2 and d["rect"].width >= 12]


def esta_riscado(linha: dict, riscos: list) -> bool:
    largura = linha["x1"] - linha["x0"]
    for r in riscos:
        sobre = min(r.x1, linha["x1"]) - max(r.x0, linha["x0"])
        meio = (r.y0 + r.y1) / 2
        if sobre >= 0.5 * largura and linha["y0"] - 2 < meio < linha["y1"] + 2:
            return True
    return False


def agrupar_por_y(itens: list[dict], tol: float) -> list[list[dict]]:
    grupos: list[list[dict]] = []
    for it in sorted(itens, key=lambda s: s["y0"]):
        for g in grupos:
            if abs(g[0]["y0"] - it["y0"]) <= tol:
                g.append(it)
                break
        else:
            grupos.append([it])
    grupos.sort(key=lambda g: g[0]["y0"])
    return grupos


def montar_tiles(linhas: list[dict], altura_pag: float, largura_pag: float) -> list[dict]:
    """Retangulo de cada produto: linhas pela posicao dos codigos, colunas
    pelo meio do caminho entre codigos vizinhos, base logo depois do preco
    daquela linha (ou do proprio codigo, se a linha nao tiver preco perto)."""
    codigos = []
    for l in linhas:
        achado = extrair_codigo(l["texto"])
        if achado:
            codigos.append({**l, "codigo": achado[0], "qtd_inline": achado[1]})
    if not codigos:
        return []
    precos = [l for l in linhas if RE_PRECO.match(l["texto"])]

    filas = agrupar_por_y(codigos, tol=25.0)
    limites = []
    for i, fila in enumerate(filas):
        y1_fila = max(c["y1"] for c in fila)
        y0_proxima = filas[i + 1][0]["y0"] if i + 1 < len(filas) else altura_pag
        candidatos = [p["y1"] for p in precos if y1_fila - 5 <= p["y0"] < y0_proxima - 5]
        limites.append(max([y1_fila] + candidatos) + 8)

    tiles = []
    for i, fila in enumerate(filas):
        fila = sorted(fila, key=lambda c: c["x0"])
        topo = MARGEM_TOPO if i == 0 else limites[i - 1]
        base = min(limites[i], altura_pag - MARGEM_RODAPE)
        for j, c in enumerate(fila):
            esq = 0.0 if j == 0 else (fila[j - 1]["x1"] + c["x0"]) / 2
            dir_ = largura_pag if j == len(fila) - 1 else (c["x1"] + fila[j + 1]["x0"]) / 2
            tiles.append({"codigo": c["codigo"], "cod_y0": c["y0"], "cod_cx": c["cx"],
                          "cod_x1": c["x1"], "qtd_inline": c["qtd_inline"],
                          "rect": (esq, topo, dir_, max(base, topo + 10))})
    return tiles


def dentro(rect, it) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= it["cx"] <= x1 and y0 <= it["cy"] <= y1


def texto_do_cabecalho(linhas: list[dict]) -> str | None:
    """Faixa de categoria no topo da pagina: maior fonte perto da margem
    esquerda, ignorando a data e o numero da pagina (que ficam nas pontas)."""
    topo = [l for l in linhas if l["y0"] <= 30 and l["tam"] >= 10
            and not RE_DATA_PAGINA.match(l["texto"])]
    if not topo:
        return None
    topo.sort(key=lambda l: l["x0"])
    return topo[0]["texto"]


def extrair_pagina(pagina, pno: int, categoria_atual: str) -> tuple[list[dict], str, list[str]]:
    linhas = coletar_linhas(pagina)
    largura_pag, altura_pag = pagina.rect.width, pagina.rect.height
    categoria_atual = texto_do_cabecalho(linhas) or categoria_atual
    linhas = [l for l in linhas if l["y0"] > 30]      # tira a faixa de cabecalho/rodape

    tiles = montar_tiles(linhas, altura_pag, largura_pag)
    imagens_pag = [im for im in pagina.get_image_info(xrefs=True) if im["xref"]]
    riscos = riscos_da_pagina(pagina)

    # numa promocao (de/por), o preco riscado fica dentro do retangulo certo,
    # mas o preco atual do lado costuma sair desenhado largo o bastante pra
    # invadir a coluna vizinha — por isso ele e pareado com o riscado mais
    # proximo (na mesma linha) em vez de so olhar em que retangulo caiu
    precos_pagina = []
    for l in linhas:
        m = RE_PRECO.match(l["texto"])
        if m:
            precos_pagina.append({"valor": m.group(1), "riscado": esta_riscado(l, riscos),
                                  "cx": l["cx"], "cy": l["cy"], "linha": l})
    riscados_pag = [p for p in precos_pagina if p["riscado"]]
    normais_pag = [p for p in precos_pagina if not p["riscado"]]

    # 'N PÇS/CAIXA' da pagina inteira: nas paginas de computador o rotulo fica
    # na mesma linha do codigo mas bem a direita, atravessando a borda da
    # coluna — entao serve de reserva quando nao cai dentro do retangulo
    qtds_pagina = []
    for l in linhas:
        m = RE_QTD.match(l["texto"])
        if m:
            qtds_pagina.append({"valor": int(m.group(1)), "x0": l["x0"], "y0": l["y0"]})

    usados = set()
    pares = []
    for r in riscados_pag:
        candidatos = [n for n in normais_pag
                      if id(n) not in usados and abs(n["cy"] - r["cy"]) <= 15]
        par = min(candidatos, key=lambda n: abs(n["cx"] - r["cx"])) if candidatos else None
        if par:
            usados.add(id(par))
        pares.append((r, par))

    def tile_do(l: dict) -> dict | None:
        return next((t for t in tiles if dentro(t["rect"], l)), None) \
            or (min(tiles, key=lambda t: abs(t["cod_cx"] - l["cx"])) if tiles else None)

    precos_por_tile = defaultdict(list)
    for r, par in pares:
        alvo = tile_do(r["linha"])
        if not alvo:
            continue
        precos_por_tile[id(alvo)].append((r["valor"], True))
        if par:
            precos_por_tile[id(alvo)].append((par["valor"], False))
    for n in normais_pag:
        if id(n) in usados:
            continue
        candidatas = [t for t in tiles if t["rect"][1] - 3 <= n["cy"] <= t["rect"][3] + 3]
        if not candidatas:
            continue
        alvo = min(candidatas, key=lambda t: abs(t["cod_cx"] - n["cx"]))
        precos_por_tile[id(alvo)].append((n["valor"], False))

    avisos: list[str] = []
    produtos = []
    for tile in tiles:
        rect = tile["rect"]
        internos = [l for l in linhas if dentro(rect, l)]

        precos_tile = precos_por_tile.get(id(tile), [])
        # a quantidade por caixa fica sempre na linha do codigo, a direita
        # dele — e nao necessariamente dentro da coluna, porque o rotulo do
        # vizinho as vezes atravessa a borda. Por isso essa regra vem antes
        # da busca por quem cai dentro do retangulo (que fica como reserva).
        qtd = tile["qtd_inline"]
        if qtd is None:
            a_direita = [q for q in qtds_pagina
                         if abs(q["y0"] - tile["cod_y0"]) <= 16 and q["x0"] >= tile["cod_x1"] - 2]
            if a_direita:
                qtd = min(a_direita, key=lambda q: q["x0"] - tile["cod_x1"])["valor"]
        candidatos = []
        for l in internos:
            t = l["texto"]
            achado = extrair_codigo(t)
            if achado and achado[0] == tile["codigo"]:
                continue
            if RE_PRECO.match(t):
                continue
            m = RE_QTD.match(t)
            if m:
                qtd = qtd or int(m.group(1))
                continue
            if t.strip().lower() == "por" or RE_DATA_PAGINA.match(t):
                continue
            if l["tam"] < 4.5 or RE_DIMENSAO.match(t):
                continue                       # fragmento minusculo ou so dimensao: ruido
            candidatos.append(l)

        # promocao: preco riscado e o antigo ('de'), o outro e o atual
        riscados = [v for v, r in precos_tile if r]
        normais = [v for v, r in precos_tile if not r]
        de, preco = None, None
        if riscados and normais:
            de, preco = riscados[0], normais[0]
        elif normais:
            preco = normais[0]
        elif riscados:
            preco = riscados[0]
        sobras = normais[1:] + riscados[1:] if (riscados and normais) else (normais[1:] or riscados[1:])
        if sobras:
            avisos.append(f"pág {pno}: preço sem dono em {tile['codigo']}: {sobras}")

        # nome: so a primeira leva de linhas grandes antes do codigo — o
        # resto (specs, outro rotulo tipo "MAXIMUS i5") volta pra descricao
        qualificam = sorted((l for l in candidatos if l["tam"] >= 6.9 and l["y0"] < tile["cod_y0"]),
                             key=lambda l: l["y0"])
        primeiro_grupo = []
        for l in qualificam:
            if primeiro_grupo and l["y0"] - primeiro_grupo[-1]["y0"] > 20:
                break
            primeiro_grupo.append(l)
        nome = limpar(" ".join(l["texto"] for l in primeiro_grupo))
        # gabinetes lado a lado: o selo "N FANS INCLUSOS" do vizinho às vezes
        # cola no nome — fica só o primeiro selo, que é o do proprio tile
        nome = re.sub(r"^(.*\d+ FANS INCLUSOS)\s+\d+ FANS INCLUSOS.*$", r"\1", nome)

        no_nome = {id(l) for l in primeiro_grupo}
        vistos, specs = set(), []
        for l in sorted((l for l in candidatos if id(l) not in no_nome), key=lambda l: (l["y0"], l["x0"])):
            texto = re.sub(r"^[•·]\s*", "", l["texto"]).strip()
            if not texto or texto in vistos:
                continue
            # selo de icone ('SOM', 'AUX', 'TECNOLOGIA'...): token curto, sem
            # numero nem ':', com fonte pequena — nao chega a ser uma spec
            eh_selo = (l["tam"] < 7.5 and len(texto.split()) <= 2
                       and not any(c.isdigit() for c in texto) and ":" not in texto)
            if eh_selo and not RE_BULLET.match(l["texto"]):
                continue
            vistos.add(texto)
            specs.append(texto)

        if preco is None:
            avisos.append(f"pág {pno}: {tile['codigo']} ficou sem preço")
        if not nome:
            avisos.append(f"pág {pno}: {tile['codigo']} ficou sem nome")
            nome = categoria_atual.title()

        caixas_img = []
        for im in imagens_pag:
            b = im["bbox"]
            larg, alt = b[2] - b[0], b[3] - b[1]
            if not (10 <= larg <= 480 and 10 <= alt <= 480):
                continue
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            if rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
                caixas_img.append(b)
        area = None
        if caixas_img:
            area = (min(b[0] for b in caixas_img), min(b[1] for b in caixas_img),
                    max(b[2] for b in caixas_img), max(b[3] for b in caixas_img))
            area = (max(area[0], rect[0]), max(area[1], rect[1]),
                    min(area[2], rect[2]), min(area[3], rect[3]))
        if area is None:
            avisos.append(f"pág {pno}: {tile['codigo']} ficou sem imagem")

        produtos.append({
            "codigo": tile["codigo"], "nome": nome, "specs": specs,
            "preco_valor": preco, "preco_de": de, "qtd_caixa": qtd,
            "categoria": categoria_atual, "pagina": pno, "area_foto": area,
        })
    return produtos, categoria_atual, avisos


def aparar_branco(img: Image.Image, limiar: int = 247) -> Image.Image:
    cinza = img.convert("L")
    mascara = cinza.point(lambda v: 0 if v >= limiar else 255)
    caixa = mascara.getbbox()
    if not caixa:
        return img
    folga = 6
    return img.crop((max(0, caixa[0] - folga), max(0, caixa[1] - folga),
                     min(img.width, caixa[2] + folga), min(img.height, caixa[3] + folga)))


def salvar_foto(pagina, area, destino: Path, thumb: Path) -> bool:
    try:
        clip = pymupdf.Rect(area).intersect(pagina.rect)
        if clip.is_empty or clip.width < 8 or clip.height < 8:
            return False
        pix = pagina.get_pixmap(clip=clip, dpi=200, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception as exc:                   # pragma: no cover
        print(f"  ! falha ao renderizar {destino.name}: {exc}")
        return False
    img = aparar_branco(img)
    grande = img.copy()
    grande.thumbnail((700, 700), Image.LANCZOS)
    grande.save(destino, "WEBP", quality=80, method=6)
    pequena = img.copy()
    pequena.thumbnail((260, 260), Image.LANCZOS)
    pequena.save(thumb, "WEBP", quality=76, method=6)
    return True


def carregar_json(caminho: Path, padrao):
    if caminho.exists():
        return json.loads(caminho.read_text("utf-8"))
    return padrao


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", help="intervalo 1-based, ex.: 2-10")
    ap.add_argument("--sem-imagens", action="store_true")
    args = ap.parse_args()

    doc = pymupdf.open(PDF)
    inicio, fim = 1, doc.page_count
    if args.paginas:
        partes = args.paginas.split("-")
        inicio, fim = int(partes[0]), int(partes[-1])

    DIR_DADOS.mkdir(exist_ok=True)
    DIR_BUILD.mkdir(exist_ok=True)
    DIR_IMG.mkdir(parents=True, exist_ok=True)

    produtos: list[dict] = []
    avisos: list[str] = []
    categoria = "GRASEP"
    for pno in range(inicio, fim + 1):        # primeiro cabecalho real da faixa
        if pno in PAGINAS_IGNORADAS:
            continue
        cab = texto_do_cabecalho(coletar_linhas(doc[pno - 1]))
        if cab:
            categoria = cab
            break
    for pno in range(inicio, fim + 1):
        if pno in PAGINAS_IGNORADAS:
            continue
        novos, categoria, novos_avisos = extrair_pagina(doc[pno - 1], pno, categoria)
        produtos.extend(novos)
        avisos.extend(novos_avisos)

    # pág 20: "VIGA SUSPENSA P/ PAINEL EXTERIOR DE LED" (50CM e 96CM) não tem
    # código próprio no catálogo — ficam colados no tile do painel vizinho
    # (D-EXT50100P2.976), que também acaba herdando o preço errado (o da
    # viga, não o seu). Ajusta os dois manualmente; conferido direto no PDF.
    if inicio <= 20 <= fim:
        for p in produtos:
            if p["codigo"] == "D-EXT50100P2.976":
                p["preco_valor"] = "2980,00"
                p["nome"] = "Painel Externo de LED"
                p["qtd_caixa"] = 6
                p["specs"] = [s for s in p["specs"] if "de comprimento" not in s]
        produtos += [
            {"codigo": "D-VIGA50", "nome": "VIGA SUSPENSA P/ PAINEL EXTERIOR DE LED",
             "specs": ["50CM de comprimento"], "preco_valor": "180,00", "preco_de": None,
             "qtd_caixa": 8, "categoria": "PAINÉIS DE LED E SUPORTES", "pagina": 20,
             "area_foto": (219, 356, 380, 410)},
            {"codigo": "D-VIGA96", "nome": "VIGA SUSPENSA P/ PAINEL EXTERIOR DE LED",
             "specs": ["96CM de comprimento"], "preco_valor": "320,00", "preco_de": None,
             "qtd_caixa": 2, "categoria": "PAINÉIS DE LED E SUPORTES", "pagina": 20,
             "area_foto": (412, 333, 586, 425)},
        ]

    # mesmo codigo pode se repetir (variante de cor na mesma foto, tabela de
    # cartoes de memoria): fica so a primeira ocorrencia, como no Knup
    finais, vistos = [], set()
    for p in produtos:
        if p["codigo"] in vistos:
            continue
        vistos.add(p["codigo"])
        finais.append(p)

    precos_novos = {}
    catalogo_novo = []
    for p in finais:
        ident = slug(p["codigo"])
        imagens = []
        if not args.sem_imagens and p["area_foto"]:
            destino = DIR_IMG / f"{ident}.webp"
            thumb = DIR_IMG / f"{ident}-t.webp"
            if destino.exists() or salvar_foto(doc[p["pagina"] - 1], p["area_foto"], destino, thumb):
                imagens.append(ident)
        if p["preco_valor"]:
            precos_novos[p["codigo"]] = {"de": p["preco_de"], "valor": p["preco_valor"], "faixas": []}
        catalogo_novo.append({
            "codigo": p["codigo"], "nome": p["nome"], "categoria": p["categoria"],
            "specs": p["specs"], "qtd_caixa": p["qtd_caixa"],
            "lancamento": False, "promocao": bool(p["preco_de"]),
            "fornecedor": FORNECEDOR, "pagina": p["pagina"], "imagens": imagens,
        })

    # merge: preserva produtos e precos de outros fornecedores (ex.: Knup)
    arq_produtos = DIR_DADOS / "produtos.json"
    dados = carregar_json(arq_produtos, {"catalogo": "", "produtos": []})
    outros = [p for p in dados.get("produtos", []) if p.get("fornecedor") != FORNECEDOR]
    codigos_outros = {p["codigo"] for p in outros}
    colisoes = codigos_outros & {p["codigo"] for p in catalogo_novo}
    if colisoes:
        avisos.append(f"código já usado por outro fornecedor: {sorted(colisoes)}")
    titulo_grasep = "Grasep — tabela à vista 03/08/2026"
    titulo_antigo = dados.get("catalogo", "")
    titulos_outros = [t for t in titulo_antigo.split(" · ") if t and "Grasep" not in t] if outros else []
    dados["catalogo"] = " · ".join(titulos_outros + [titulo_grasep])
    dados["produtos"] = outros + catalogo_novo
    arq_produtos.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")

    arq_precos = DIR_BUILD / "precos.json"
    precos_existentes = carregar_json(arq_precos, {})
    precos = {c: v for c, v in precos_existentes.items() if c in codigos_outros}
    precos.update(precos_novos)
    arq_precos.write_text(json.dumps(precos, ensure_ascii=False, indent=1), "utf-8")

    sem_nome = [p for p in catalogo_novo if not p["nome"] or p["nome"] == p["categoria"].title()]
    sem_img = [p for p in catalogo_novo if not p["imagens"]]
    sem_spec = [p for p in catalogo_novo if not p["specs"]]
    print(f"produtos Grasep: {len(catalogo_novo)}  (brutos {len(produtos)}, duplicados {len(produtos) - len(finais)})")
    print(f"com preço: {len(precos_novos)}")
    print(f"sem nome (usou categoria): {len(sem_nome)}  sem imagem: {len(sem_img)}  sem specs: {len(sem_spec)}")
    if avisos:
        print(f"\nAVISOS ({len(avisos)}) — conferir no PDF:")
        for a in avisos[:60]:
            print("  •", a)
    else:
        print("\nsem avisos de layout")
    print(f"\ntotal combinado em data/produtos.json: {len(dados['produtos'])} produtos")


if __name__ == "__main__":
    main()
