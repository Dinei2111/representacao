#!/usr/bin/env python3
"""Extrai o catalogo Knup (PDF do InDesign) para JSON + imagens WebP.

O PDF tem uma grade regular de "tiles" de produto. Cada tile comeca por um
codigo em Dinamit-Bold (ex.: RG-SW51) com a quantidade por caixa a direita,
seguido da foto, do nome (Poppins-Bold), do preco (Poppins-*-SC700) e dos
bullets de especificacao (Poppins-Light/Thin).

Uso:
    python3 tools/extract_catalog.py [--paginas 1-82] [--sem-imagens]

Gera:
    data/produtos.json      catalogo sem precos (vai para o site)
    build/precos.json       precos por codigo (NAO versionado; entra no encrypt_prices.py)
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
PDF = RAIZ / "catalogo" / "Knup_A_Vista_03082026.pdf"
DIR_DADOS = RAIZ / "data"
DIR_BUILD = RAIZ / "build"
DIR_IMG = RAIZ / "assets" / "produtos"

# --- classificacao por fonte -------------------------------------------------
# com prefixo ('KP-SL80', 'KP-552/220v') ou sem prefixo ('GT210/1G', 'SL7013/1.5M')
RE_CODIGO = re.compile(r"^(?:[A-Z0-9]{1,6}-[A-Z0-9][A-Za-z0-9/.\-+ ]*"
                       r"|[A-Z]{1,4}\d[A-Za-z0-9/.\-+]*)$")
RE_PRECO = re.compile(r"^\d{1,3}(?:[.\s]?\d{3})*,\d{2}$")
RE_QTD = re.compile(r"^\d{1,4}$")
RE_ROTULO_PRECO = re.compile(r"^(R\$|CX|PÇS?|PCS?|UN|\d{1,3})$", re.I)
FONTES_NOME = ("Poppins-Bold", "Poppins-ExtraBold", "Poppins-SemiBold",
               "Poppins-Medium", "Poppins-Regular", "Poppins-Black")
RUIDO_NOME = {"R$", "CX", "LANÇAMENTO", "LANCAMENTO", "NOVO", "UN", "PÇ", "PC"}
# selo "COMPRE O COMBO" no canto do tile: nao e nome, nem spec, nem limite da foto
RUIDO_SELO = {"COMPRE O", "COMPRE", "COMBO", "O"}

# faixa de corpo de fonte em que os codigos aparecem (ha codigos em 7pt)
FONTE_COD = (6.8, 10.5)
LARGURA_PAG = 595.276
LARGURA_COLUNA = 143.0    # 4 colunas de produto por página
MARGEM_DIR = 578.0
FUNDO_PAG = 826.0

# paginas institucionais / capa / indice: sem grade de produtos
PAGINAS_IGNORADAS = {1}


# o PDF quebra estas palavras na ligadura 'fi'/'fl' e sobra um espaco no texto
CORRECOES = {
    "fi o": "fio", "fi os": "fios", "fi bra": "fibra", "fi rme": "firme",
    "fi ltro": "filtro", "efi ciência": "eficiência", "Certifi cado": "Certificado",
    "certifi cado": "certificado", "amplifi cador": "amplificador",
    "Amplifi cador": "Amplificador", "modifi cada": "modificada",
}
RE_CORRECOES = re.compile(r"\b(" + "|".join(map(re.escape, CORRECOES)) + r")\b")


def limpar(texto: str) -> str:
    """Normaliza ligaduras e espacos que o InDesign deixa no texto."""
    texto = texto.replace("ﬁ", "fi").replace("ﬂ", "fl")
    texto = texto.replace(" ", " ").replace("’", "'")
    texto = unicodedata.normalize("NFC", texto)
    texto = RE_CORRECOES.sub(lambda m: CORRECOES[m.group(1)], texto)
    return re.sub(r"\s+", " ", texto).strip()


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "item"


def coletar_spans(pagina) -> list[dict]:
    spans = []
    for blk in pagina.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for linha in blk["lines"]:
            for sp in linha["spans"]:
                txt = limpar(sp["text"])
                if not txt:
                    continue
                x0, y0, x1, y1 = sp["bbox"]
                spans.append({
                    "texto": txt, "fonte": sp["font"], "tam": round(sp["size"], 1),
                    "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
                })
    return spans


def eh_codigo(sp: dict) -> bool:
    return (sp["fonte"].startswith("Dinamit") and FONTE_COD[0] <= sp["tam"] <= FONTE_COD[1]
            and bool(RE_CODIGO.match(sp["texto"])))


def eh_qtd(sp: dict) -> bool:
    return (sp["fonte"].startswith("Dinamit") and FONTE_COD[0] <= sp["tam"] <= FONTE_COD[1]
            and bool(RE_QTD.match(sp["texto"])))


def eh_preco(sp: dict) -> bool:
    # o preco aparece em Poppins-Bold-SC700 e, em algumas secoes, em Poppins-Bold
    return (("SC700" in sp["fonte"] or "Bold" in sp["fonte"]) and sp["tam"] >= 7.5
            and bool(RE_PRECO.match(sp["texto"])))


def eh_cabecalho(sp: dict) -> bool:
    """Faixa de categoria no topo da secao (nunca um codigo de produto)."""
    return (sp["fonte"].startswith("Dinamit") and sp["tam"] >= 9.8
            and not RE_CODIGO.match(sp["texto"]))


def remover_sobreposicoes(spans: list[dict]) -> list[dict]:
    """Descarta os duplicados que o layout imprime por cima do codigo.

    O InDesign desenha 'RG-SW49' e, sobreposto, os pedacos 'RG' e 'SW49'. Sem
    isso, aceitar codigos sem prefixo criaria dezenas de produtos fantasmas.
    """
    din = [sp for sp in spans
           if sp["fonte"].startswith("Dinamit") and FONTE_COD[0] <= sp["tam"] <= FONTE_COD[1]]
    sobras = set()
    for a in din:
        for b in din:
            if a is b or id(b) in sobras:
                continue
            if (b["x0"] - 0.6 <= a["x0"] and a["x1"] <= b["x1"] + 0.6
                    and abs(a["y0"] - b["y0"]) <= 1.5
                    and (a["x1"] - a["x0"]) < (b["x1"] - b["x0"]) - 0.5):
                sobras.add(id(a))
                break
    return [sp for sp in spans if id(sp) not in sobras]


def juntar_dinamit(spans: list[dict]) -> list[dict]:
    """O InDesign quebra alguns codigos em varios spans ('KP' + '-RA937').

    Junta spans Dinamit vizinhos na mesma linha quando praticamente nao ha
    espaco entre eles, devolvendo a lista de spans com os codigos inteiros.
    """
    alvo = [sp for sp in spans
            if sp["fonte"].startswith("Dinamit") and FONTE_COD[0] <= sp["tam"] <= FONTE_COD[1]]
    outros = [sp for sp in spans if sp not in alvo]
    unidos: list[dict] = []
    for sp in sorted(alvo, key=lambda s: (round(s["y0"], 1), s["x0"])):
        ant = unidos[-1] if unidos else None
        if (ant and abs(ant["y0"] - sp["y0"]) <= 1.5
                and 0 <= sp["x0"] - ant["x1"] <= 2.5):
            ant["texto"] += sp["texto"]
            ant["x1"] = sp["x1"]
            ant["cx"] = (ant["x0"] + ant["x1"]) / 2
        else:
            unidos.append(dict(sp))
    return outros + unidos


def agrupar_linhas(itens: list[dict], tol: float = 4.0) -> list[list[dict]]:
    """Agrupa spans em linhas horizontais pela coordenada y."""
    linhas: list[list[dict]] = []
    for sp in sorted(itens, key=lambda s: (s["y0"], s["x0"])):
        for ln in linhas:
            if abs(ln[0]["y0"] - sp["y0"]) <= tol:
                ln.append(sp)
                break
        else:
            linhas.append([sp])
    for ln in linhas:
        ln.sort(key=lambda s: s["x0"])
    return linhas


def montar_tiles(spans: list[dict], cabecalhos: list[dict]) -> list[dict]:
    """Define o retangulo de cada produto a partir da posicao dos codigos."""
    codigos = [sp for sp in spans if eh_codigo(sp)]
    if not codigos:
        return []
    linhas = agrupar_linhas(codigos)
    tiles = []
    for i, linha in enumerate(linhas):
        topo = min(sp["y0"] for sp in linha) - 3
        base = (min(sp["y0"] for sp in linhas[i + 1]) - 4) if i + 1 < len(linhas) else FUNDO_PAG
        # a faixa da proxima categoria encerra a linha atual
        for h in cabecalhos:
            if topo + 6 < h["y0"] < base:
                base = h["y0"] - 2
        for j, sp in enumerate(linha):
            esq = sp["x0"] - 3
            dir_ = (linha[j + 1]["x0"] - 4) if j + 1 < len(linha) else MARGEM_DIR
            tiles.append({
                "codigo": sp["texto"], "rect": (esq, topo, dir_, base),
                "linha": i, "coluna": j,
            })
    return tiles


def dentro(rect, sp) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= sp["cx"] <= x1 and y0 <= sp["cy"] <= y1


def juntar_linha(linha: list[dict]) -> str:
    """Junta os spans de uma linha respeitando o espacamento real do PDF.

    O InDesign quebra palavras no meio ('Certi' + ligadura 'fi' + 'cado'), entao
    so entra espaco quando existe folga de verdade entre um span e o proximo.
    """
    texto = ""
    anterior = None
    for sp in sorted(linha, key=lambda s: s["x0"]):
        if anterior is not None and (
                sp["x0"] - anterior["x1"] > 0.55
                # 'FECHADURA' + 'INTELIGENTE' saem colados quando muda o peso da fonte
                or (sp["fonte"] != anterior["fonte"] and anterior["texto"][-1:].isalpha()
                    and sp["texto"][:1].isupper())):
            texto += " "
        texto += sp["texto"]
        anterior = sp
    texto = re.sub(r":(?=[^\s:])", ": ", texto)   # 'eficiência:80' -> 'eficiência: 80'
    return limpar(texto)


def montar_specs(spans_spec: list[dict]) -> list[str]:
    """Reconstroi os bullets: '•' abre um item, o resto da linha continua o anterior."""
    resultado: list[str] = []

    def acrescentar(trecho: str) -> None:
        trecho = limpar(trecho)
        if not trecho or not resultado:
            if trecho:
                resultado.append(trecho)
            return
        juncao = "" if resultado[-1].endswith("-") else " "
        resultado[-1] = limpar(resultado[-1] + juncao + trecho)

    for linha in agrupar_linhas(spans_spec, tol=3.0):
        texto = juntar_linha(linha)
        if not texto:
            continue
        partes = texto.split("•")
        acrescentar(partes[0])
        for parte in partes[1:]:
            parte = limpar(parte)
            if parte:
                resultado.append(parte)
    return [t for t in (limpar(t) for t in resultado) if t]


def area_das_fotos(imagens: list[dict], rect) -> tuple | None:
    """Retangulo que envolve as fotos dentro da regiao.

    Varias fotos do catalogo vem fatiadas em dezenas de sub-imagens ou sao
    composicoes (produto + embalagem + variacoes de cor), entao o que importa
    e a area ocupada, nao cada XObject isolado.
    """
    caixas = []
    for im in imagens:
        b = im["bbox"]
        larg, alt = b[2] - b[0], b[3] - b[1]
        if not (12 <= larg <= 420 and 12 <= alt <= 420):
            continue
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
            caixas.append(b)
    if not caixas:
        return None
    uniao = (min(b[0] for b in caixas), min(b[1] for b in caixas),
             max(b[2] for b in caixas), max(b[3] for b in caixas))
    # nao deixa a foto invadir a linha do codigo nem o selo colado na base
    return (max(uniao[0], rect[0]), max(uniao[1], rect[1]),
            min(uniao[2], rect[2]), min(uniao[3], rect[3]))


def faixa_da_foto(rect, internos: list[dict]):
    """Recorta a regiao entre a linha do codigo e o primeiro texto abaixo dela.

    Sem isso a foto renderizada acaba levando junto o rodape do codigo e o selo
    de LANCAMENTO que fica colado na base da imagem.
    """
    codigos = [sp["y1"] for sp in internos if eh_codigo(sp) or eh_qtd(sp)]
    topo = (max(codigos) + 1) if codigos else rect[1]
    abaixo = [sp["y0"] for sp in internos
              if not (eh_codigo(sp) or eh_qtd(sp)) and sp["y0"] > topo + 4
              and sp["texto"] not in RUIDO_SELO]
    base = (min(abaixo) - 1) if abaixo else rect[3]
    return (rect[0], topo, rect[2], max(base, topo + 10))


def classificar(internos: list[dict]):
    """Separa os spans de um tile em nome, specs, precos, quantidade e selo."""
    nome_spans, spec_spans, precos, qtd, lancamento = [], [], [], None, False
    for sp in sorted(internos, key=lambda s: (s["y0"], s["x0"])):
        t = sp["texto"]
        if eh_codigo(sp):
            continue
        if eh_qtd(sp):
            if qtd is None:
                qtd = int(t)
            continue
        if sp["fonte"].startswith("Dinamit") and sp["tam"] <= FONTE_COD[1]:
            continue                       # sobras da sobreposicao do layout
        if eh_preco(sp):
            precos.append(sp)
            continue
        if t.upper().startswith("LAN") and "AMENTO" in t.upper():
            lancamento = True
            continue
        if t in RUIDO_NOME or t in RUIDO_SELO:
            continue
        if sp["tam"] <= 7.5 and RE_ROTULO_PRECO.match(t):
            continue                       # 'R$', 'CX', contadores de cor, faixas
        if sp["tam"] >= 7.8 and sp["fonte"].startswith(FONTES_NOME) \
                and not sp["fonte"].endswith("Light"):
            nome_spans.append(sp)
        else:
            spec_spans.append(sp)
    return nome_spans, spec_spans, precos, qtd, lancamento


def texto_do_nome(nome_spans: list[dict]) -> str:
    partes = [juntar_linha(linha) for linha in agrupar_linhas(nome_spans, tol=3.0)]
    return limpar(" ".join(partes))


def rotulo_do_preco(sp_preco: dict, spans: list[dict]) -> str:
    """Le o prefixo do preco ('1 CX', '50 PÇS', 'R$') a esquerda do valor."""
    perto = [sp for sp in spans
             if sp["x1"] <= sp_preco["x0"] + 1 and sp_preco["x0"] - sp["x1"] < 22
             and abs(sp["cy"] - sp_preco["cy"]) <= 4 and sp["tam"] <= 7.5
             and RE_ROTULO_PRECO.match(sp["texto"])]
    perto.sort(key=lambda s: (round(s["y0"]), s["x0"]))
    rot = limpar(" ".join(sp["texto"] for sp in perto))
    return "" if rot in ("R$", "") else rot


def riscos_da_pagina(pagina) -> list:
    """Tracos horizontais finos da pagina — e assim que o catalogo risca o preco antigo."""
    return [d["rect"] for d in pagina.get_drawings()
            if d["rect"].height <= 2.2 and d["rect"].width >= 12]


def esta_riscado(sp: dict, riscos: list) -> bool:
    """O traco costuma comecar no 'R$' e parar um pouco antes do fim do numero,
    entao vale a sobreposicao (60% da largura) e nao o encaixe exato. A altura
    tem que cair no miolo do texto — assim o sublinhado do nome nao conta."""
    largura = sp["x1"] - sp["x0"]
    alto = sp["y1"] - sp["y0"]
    for r in riscos:
        sobre = min(r.x1, sp["x1"]) - max(r.x0, sp["x0"])
        meio = (r.y0 + r.y1) / 2
        if sobre >= 0.6 * largura and sp["y0"] + 0.25 * alto < meio < sp["y1"] - 0.15 * alto:
            return True
    return False


def ler_faixa(rotulo: str) -> dict | None:
    """'3 CX' -> a partir de 3 caixas; '50 PÇS' -> a partir de 50 pecas.

    Numero solto ('30') vem de uma faixa cujo 'CX' o layout desenhou separado.
    """
    m = re.match(r"^(\d{1,3})\s*(CX|PÇS?|PCS?)?$", rotulo.strip(), re.I)
    if not m:
        return None
    unidade = "pc" if (m.group(2) or "").upper().startswith(("PÇ", "PC")) else "cx"
    return {"a_partir": int(m.group(1)), "unidade": unidade}


def montar_precos(precos_spans: list[dict], spans: list[dict], riscos: list,
                  coluna: tuple[float, float],
                  largura_total: tuple[float, float]) -> tuple[dict, list[str]]:
    """Monta {de, valor, faixas} a partir dos precos que caem dentro do tile.

    Regras tiradas do proprio catalogo:
    - preco riscado e o preco antigo da promocao ('de 768,90 por 670,00');
    - preco com rotulo ('3 CX', '50 PÇS') e faixa por volume;
    - o preco corrente e o primeiro preco simples dentro da coluna do produto —
      olhar a coluna evita herdar o preco do vizinho quando o quadro estica.
    """
    def separar(limites):
        de, valor, faixas, sobras = None, None, [], []
        for sp in sorted(precos_spans, key=lambda s: (s["y0"], s["x0"])):
            if not limites[0] <= sp["cx"] <= limites[1]:
                continue
            rotulo = rotulo_do_preco(sp, spans)
            faixa = ler_faixa(rotulo) if rotulo else None
            if faixa:
                faixas.append({**faixa, "valor": sp["texto"]})
            elif esta_riscado(sp, riscos):
                de = de or sp["texto"]
            elif valor is None:
                valor = sp["texto"]
            else:
                sobras.append(sp["texto"])
        faixas.sort(key=lambda f: (f["unidade"], f["a_partir"]))
        return {"de": de, "valor": valor, "faixas": faixas}, sobras

    preco, sobras = separar(coluna)
    if preco["valor"] is None and not preco["faixas"]:
        # cards de combo e de tabela põem o preço fora da coluna do código;
        # aí o quadro inteiro é de um produto só e não há com quem confundir
        preco, sobras = separar(largura_total)
    if preco["valor"] is None and preco["faixas"]:
        # cards de tabela só trazem preços rotulados ('50 PÇS' / '1 CX'):
        # o de menor exigência vira o preço de referência
        base = min(preco["faixas"], key=lambda f: (f["unidade"] != "pc", f["a_partir"]))
        preco["valor"] = base["valor"]
        preco["faixas"] = [f for f in preco["faixas"] if f is not base]
    return preco, sobras


def specs_de_tabela(spec_spans: list[dict], rotulos: list[dict]) -> list[str]:
    """Layout em tabela: casa cada valor com o rotulo da linha (a esquerda).

    Um valor pode ocupar varias linhas ('Mac OS,' / 'Linux,' / 'Windows'), por
    isso cada linha vai para o rotulo mais proximo na vertical.
    """
    linhas_rotulo = [(sum(sp["cy"] for sp in ln) / len(ln), juntar_linha(ln))
                     for ln in agrupar_linhas(rotulos, tol=3.0)]
    if not linhas_rotulo:
        return []
    # rotulos de varias linhas ('Vel. de gravacao/' + 'Vel. de leitura') viram um so
    agrupados: list[list] = []
    for cy, texto in sorted(linhas_rotulo):
        if agrupados and cy - agrupados[-1][0] < 8:
            agrupados[-1][0] = cy
            agrupados[-1][1] = limpar(agrupados[-1][1] + " " + texto)
        else:
            agrupados.append([cy, texto])

    valores: dict[int, list[str]] = defaultdict(list)
    for ln in agrupar_linhas(spec_spans, tol=3.0):
        valor = juntar_linha(ln)
        if not valor:
            continue
        cy = sum(sp["cy"] for sp in ln) / len(ln)
        i = min(range(len(agrupados)), key=lambda k: abs(agrupados[k][0] - cy))
        valores[i].append(valor)

    itens = []
    for i, (_, rot) in enumerate(agrupados):
        if valores.get(i):
            itens.append(limpar(f"{rot}: {' '.join(valores[i])}"))
    return itens


def extrair_pagina(pagina, pno: int, categoria_atual: str):
    spans = juntar_dinamit(remover_sobreposicoes(coletar_spans(pagina)))
    imagens = [im for im in pagina.get_image_info(xrefs=True) if im["xref"]]
    riscos = riscos_da_pagina(pagina)

    cabecalhos = sorted(
        [sp for sp in spans if eh_cabecalho(sp)],
        key=lambda s: s["y0"])

    tiles = montar_tiles(spans, cabecalhos)
    por_linha = defaultdict(list)
    for t in tiles:
        por_linha[t["linha"]].append(t)

    produtos = []
    avisos: list[str] = []
    for tile in tiles:
        rect = tile["rect"]
        cat = categoria_atual
        for h in cabecalhos:
            if h["y0"] <= rect[1] + 6:
                cat = h["texto"]
        internos = [sp for sp in spans if dentro(rect, sp)]
        nome_spans, spec_spans, precos, qtd, lancamento = classificar(internos)
        nome = texto_do_nome(nome_spans)
        faixa = faixa_da_foto(rect, internos)
        # alguns combos sao desenho vetorial, sem imagem embutida: vale a faixa toda
        area = area_das_fotos(imagens, faixa) or (faixa if faixa[3] - faixa[1] > 40 else None)
        specs = montar_specs(spec_spans)

        if area is None:
            # Cards em formato de tabela (cabos, pendrives): nome, foto e
            # quantidade ficam a esquerda da primeira coluna de codigos e cada
            # coluna de codigo e uma variacao do mesmo produto.
            primeiro = min(por_linha[tile["linha"]], key=lambda t: t["rect"][0])
            zona = (18.0, rect[1], primeiro["rect"][0] - 1, rect[3])
            externos = [sp for sp in spans if dentro(zona, sp)]
            e_nome, e_spec, _, e_qtd, e_lanc = classificar(externos)
            nome = texto_do_nome(e_nome) or nome
            qtd = qtd or e_qtd
            lancamento = lancamento or e_lanc
            area = area_das_fotos(imagens, zona)
            tabela = specs_de_tabela(spec_spans + nome_spans, e_spec)
            if tabela:
                specs = tabela
            if not nome:
                # em alguns cards o titulo fica um pouco acima da linha do codigo
                acima = (18.0, rect[1] - 26, primeiro["rect"][0] - 1, rect[1])
                a_nome, _, _, _, _ = classificar([sp for sp in spans if dentro(acima, sp)])
                nome = texto_do_nome(a_nome)

        coluna = (rect[0], min(rect[2], rect[0] + LARGURA_COLUNA))
        preco, sobras = montar_precos(precos, spans, riscos, coluna, (rect[0], rect[2]))
        if sobras:
            avisos.append(f"pág {pno}: preço sem dono em {tile['codigo']}: {sobras}")
        if preco["valor"] is None:
            avisos.append(f"pág {pno}: {tile['codigo']} ficou sem preço")

        produtos.append({
            # um punhado de tiles nao tem titulo impresso: usa a categoria
            "codigo": tile["codigo"], "nome": nome or cat.title(), "specs": specs,
            "preco": preco,
            "qtd_caixa": qtd, "lancamento": lancamento,
            "categoria": cat, "pagina": pno, "area_foto": area,
        })

    if cabecalhos:
        categoria_atual = cabecalhos[-1]["texto"]
    return produtos, categoria_atual, avisos


def aparar_branco(img: Image.Image, limiar: int = 247) -> Image.Image:
    """Remove a moldura branca sobrando em volta da foto."""
    cinza = img.convert("L")
    mascara = cinza.point(lambda v: 0 if v >= limiar else 255)
    caixa = mascara.getbbox()
    if not caixa:
        return img
    folga = 6
    return img.crop((max(0, caixa[0] - folga), max(0, caixa[1] - folga),
                     min(img.width, caixa[2] + folga), min(img.height, caixa[3] + folga)))


def salvar_foto(pagina, area, destino: Path, thumb: Path) -> bool:
    """Renderiza a area da foto direto da pagina — igual ao catalogo impresso.

    Extrair o XObject nao serve: boa parte das fotos vem fatiada em dezenas de
    sub-imagens ou e uma composicao de produto + embalagem + variacoes.
    """
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", help="intervalo 1-based, ex.: 2-10")
    ap.add_argument("--sem-imagens", action="store_true")
    args = ap.parse_args()

    doc = pymupdf.open(PDF)
    inicio, fim = 1, doc.page_count
    if args.paginas:
        partes = args.paginas.split("-")
        inicio = int(partes[0])
        fim = int(partes[-1])

    DIR_DADOS.mkdir(exist_ok=True)
    DIR_BUILD.mkdir(exist_ok=True)
    DIR_IMG.mkdir(parents=True, exist_ok=True)

    produtos: list[dict] = []
    avisos: list[str] = []
    categoria = ""
    for pno in range(inicio, fim + 1):
        if pno in PAGINAS_IGNORADAS:
            continue
        pagina = doc[pno - 1]
        novos, categoria, novos_avisos = extrair_pagina(pagina, pno, categoria)
        produtos.extend(novos)
        avisos.extend(novos_avisos)

    # o mesmo codigo aparece de novo nas paginas de promocao: fica a versao
    # mais completa, sem duplicar o produto no site
    finais, vistos = [], {}
    for p in produtos:
        cod = p["codigo"]
        if cod in vistos:
            anterior = vistos[cod]
            if len(p["specs"]) > len(anterior["specs"]):
                anterior.update({k: p[k] for k in ("nome", "specs", "area_foto", "pagina")})
            if not anterior["preco"]["valor"]:
                anterior["preco"] = p["preco"]
            anterior["lancamento"] = anterior["lancamento"] or p["lancamento"]
            continue
        vistos[cod] = p
        finais.append(p)

    precos = {}
    catalogo = []
    for p in finais:
        ident = slug(p["codigo"])
        imagens = []
        if not args.sem_imagens and p["area_foto"]:
            destino = DIR_IMG / f"{ident}.webp"
            thumb = DIR_IMG / f"{ident}-t.webp"
            if destino.exists() or salvar_foto(doc[p["pagina"] - 1], p["area_foto"],
                                               destino, thumb):
                imagens.append(ident)
        if p["preco"]["valor"]:
            precos[p["codigo"]] = p["preco"]
        catalogo.append({
            "codigo": p["codigo"], "nome": p["nome"], "categoria": p["categoria"],
            "specs": p["specs"], "qtd_caixa": p["qtd_caixa"],
            "lancamento": p["lancamento"], "promocao": bool(p["preco"]["de"]),
            "fornecedor": "Knup", "pagina": p["pagina"], "imagens": imagens,
        })

    # faz merge: preserva produtos e precos de outros fornecedores (ex.: Grasep)
    titulo_knup = "Knup — tabela à vista 03/08/2026"
    arq_produtos = DIR_DADOS / "produtos.json"
    dados = json.loads(arq_produtos.read_text("utf-8")) if arq_produtos.exists() \
        else {"catalogo": "", "produtos": []}
    outros = [p for p in dados.get("produtos", []) if p.get("fornecedor") != "Knup"]
    titulos_outros = [t for t in dados.get("catalogo", "").split(" · ") if t and "Knup" not in t]
    dados["catalogo"] = " · ".join([titulo_knup] + titulos_outros)
    dados["produtos"] = catalogo + outros
    arq_produtos.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")

    arq_precos = DIR_BUILD / "precos.json"
    codigos_outros = {p["codigo"] for p in outros}
    precos_existentes = json.loads(arq_precos.read_text("utf-8")) if arq_precos.exists() else {}
    precos_finais = {c: v for c, v in precos_existentes.items() if c in codigos_outros}
    precos_finais.update(precos)
    arq_precos.write_text(json.dumps(precos_finais, ensure_ascii=False, indent=1), "utf-8")

    sem_nome = [p for p in catalogo if not p["nome"]]
    sem_img = [p for p in catalogo if not p["imagens"]]
    sem_spec = [p for p in catalogo if not p["specs"]]
    promos = [p for p in catalogo if p["promocao"]]
    com_faixa = [c for c, v in precos.items() if v["faixas"]]
    print(f"produtos: {len(catalogo)}  (brutos {len(produtos)}, duplicados {len(produtos)-len(finais)})")
    print(f"com preco: {len(precos)}  em promoção: {len(promos)}  "
          f"com faixa por volume: {len(com_faixa)}")
    print(f"sem nome: {len(sem_nome)}  sem imagem: {len(sem_img)}  sem specs: {len(sem_spec)}")
    for p in sem_nome[:10]:
        print("  sem nome:", p["codigo"], "pag", p["pagina"])
    for p in sem_img[:10]:
        print("  sem imagem:", p["codigo"], "pag", p["pagina"])
    if avisos:
        print(f"\nAVISOS ({len(avisos)}) — conferir no PDF:")
        for a in avisos[:40]:
            print("  •", a)
    else:
        print("\nsem avisos de layout")


if __name__ == "__main__":
    main()
