#!/usr/bin/env python3
"""Gera o SQL da tabela de precos para colar no SQL Editor do Supabase.

Nenhuma chave secreta do projeto passa por aqui: o script so escreve um arquivo
com INSERTs, que voce revisa e cola. A tabela `precos` tem `codigo` como chave
primaria global e uma coluna `fornecedor` — o delete+insert de cada fornecedor
nunca mexe nos precos dos outros.

Uso:
    python3 tools/extract_catalog.py             # gera build/precos.json
    python3 tools/sync_supabase.py                # gera supabase/precos.sql (Knup)
    python3 tools/extract_catalog_onistek.py      # gera build/precos-onistek.json
    python3 tools/sync_supabase.py onistek        # gera supabase/precos-onistek.sql
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_BUILD = RAIZ / "build"
DIR_SUPABASE = RAIZ / "supabase"

FORNECEDORES = {
    "knup": {
        "nome": "Knup",
        "entrada": DIR_BUILD / "precos.json",
        "saida": DIR_SUPABASE / "precos.sql",
    },
    "onistek": {
        "nome": "Onistek",
        "entrada": DIR_BUILD / "precos-onistek.json",
        "saida": DIR_SUPABASE / "precos-onistek.sql",
    },
}


def texto_sql(valor) -> str:
    if valor is None:
        return "null"
    return "'" + str(valor).replace("'", "''") + "'"


def main() -> None:
    chave = (sys.argv[1].lower() if len(sys.argv) > 1 else "knup")
    if chave not in FORNECEDORES:
        raise SystemExit(f"fornecedor desconhecido: {chave} (opções: {', '.join(FORNECEDORES)})")
    cfg = FORNECEDORES[chave]
    fornecedor, entrada, saida = cfg["nome"], cfg["entrada"], cfg["saida"]

    if not entrada.exists():
        raise SystemExit(f"rode antes o extrator do {fornecedor}  (falta {entrada})")
    precos = json.loads(entrada.read_text("utf-8"))

    linhas = [
        "-- Tabela de preços gerada por tools/sync_supabase.py — não editar à mão.",
        "-- Cole no SQL Editor do Supabase depois do schema.sql.",
        f"-- {len(precos)} produtos · fornecedor {fornecedor}",
        "",
        "begin;",
        f"delete from public.precos where fornecedor = {texto_sql(fornecedor)};",
        "insert into public.precos (codigo, de, valor, faixas, fornecedor) values",
    ]
    valores = []
    for codigo, info in sorted(precos.items()):
        faixas = json.dumps(info.get("faixas") or [], ensure_ascii=False)
        valores.append(
            f"  ({texto_sql(codigo)}, {texto_sql(info.get('de'))}, "
            f"{texto_sql(info['valor'])}, {texto_sql(faixas)}::jsonb, "
            f"{texto_sql(fornecedor)})")
    linhas.append(",\n".join(valores))
    linhas.append("on conflict (codigo) do update set")
    linhas.append("  de = excluded.de, valor = excluded.valor, faixas = excluded.faixas,")
    linhas.append("  fornecedor = excluded.fornecedor, atualizado_em = now();")
    linhas.append("commit;")

    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n".join(linhas) + "\n", "utf-8")
    promos = sum(1 for i in precos.values() if i.get("de"))
    faixas_n = sum(1 for i in precos.values() if i.get("faixas"))
    print(f"{len(precos)} preços em {saida.relative_to(RAIZ)} "
          f"({promos} em promoção, {faixas_n} com faixa por volume)")


if __name__ == "__main__":
    main()
