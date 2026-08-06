#!/usr/bin/env python3
"""Gera o SQL da tabela de precos para colar no SQL Editor do Supabase.

Nenhuma chave secreta do projeto passa por aqui: o script so escreve um arquivo
com INSERTs, que voce revisa e cola.

Uso:
    python3 tools/extract_catalog.py     # gera build/precos.json
    python3 tools/sync_supabase.py       # gera supabase/precos.sql
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "build" / "precos.json"
SAIDA = RAIZ / "supabase" / "precos.sql"
FORNECEDOR = "Knup"


def texto_sql(valor) -> str:
    if valor is None:
        return "null"
    return "'" + str(valor).replace("'", "''") + "'"


def main() -> None:
    if not ENTRADA.exists():
        raise SystemExit(f"rode antes: python3 tools/extract_catalog.py  (falta {ENTRADA})")
    precos = json.loads(ENTRADA.read_text("utf-8"))

    linhas = [
        "-- Tabela de preços gerada por tools/sync_supabase.py — não editar à mão.",
        "-- Cole no SQL Editor do Supabase depois do schema.sql.",
        f"-- {len(precos)} produtos · fornecedor {FORNECEDOR}",
        "",
        "begin;",
        f"delete from public.precos where fornecedor = {texto_sql(FORNECEDOR)};",
        "insert into public.precos (codigo, de, valor, faixas, fornecedor) values",
    ]
    valores = []
    for codigo, info in sorted(precos.items()):
        faixas = json.dumps(info.get("faixas") or [], ensure_ascii=False)
        valores.append(
            f"  ({texto_sql(codigo)}, {texto_sql(info.get('de'))}, "
            f"{texto_sql(info['valor'])}, {texto_sql(faixas)}::jsonb, "
            f"{texto_sql(FORNECEDOR)})")
    linhas.append(",\n".join(valores))
    linhas.append("on conflict (codigo) do update set")
    linhas.append("  de = excluded.de, valor = excluded.valor, faixas = excluded.faixas,")
    linhas.append("  fornecedor = excluded.fornecedor, atualizado_em = now();")
    linhas.append("commit;")

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text("\n".join(linhas) + "\n", "utf-8")
    promos = sum(1 for i in precos.values() if i.get("de"))
    faixas = sum(1 for i in precos.values() if i.get("faixas"))
    print(f"{len(precos)} preços em {SAIDA.relative_to(RAIZ)} "
          f"({promos} em promoção, {faixas} com faixa por volume)")


if __name__ == "__main__":
    main()
