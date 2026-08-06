#!/usr/bin/env python3
"""Cifra a tabela de precos com uma senha (AES-256-GCM + PBKDF2-SHA256).

O site e estatico: qualquer coisa publicada no repositorio pode ser lida por
quem abrir a pagina. Por isso os precos nao ficam escondidos com CSS — eles sao
publicados ja cifrados e so viram texto no navegador de quem digitar a senha.

Uso:
    python3 tools/encrypt_prices.py --senha "minha-senha"
    SENHA_TABELA="minha-senha" python3 tools/encrypt_prices.py

Le  : build/precos.json   (gerado por extract_catalog.py, fora do versionamento)
Gera: assets/precos.enc   (versionado; inutil sem a senha)
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "build" / "precos.json"
SAIDA = RAIZ / "assets" / "precos.enc"
ITERACOES = 250_000


def cifrar(dados: bytes, senha: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    nonce = os.urandom(12)
    chave = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, ITERACOES, 32)
    conteudo = AESGCM(chave).encrypt(nonce, dados, None)
    return {
        "v": 1, "kdf": "PBKDF2-SHA256", "iter": ITERACOES, "cifra": "AES-GCM",
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "dados": base64.b64encode(conteudo).decode(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senha", help="senha da tabela (ou variavel SENHA_TABELA)")
    args = ap.parse_args()

    senha = args.senha or os.environ.get("SENHA_TABELA") or getpass.getpass("Senha da tabela: ")
    if len(senha) < 4:
        raise SystemExit("senha muito curta")
    if not ENTRADA.exists():
        raise SystemExit(f"rode antes: python3 tools/extract_catalog.py  (falta {ENTRADA})")

    precos = json.loads(ENTRADA.read_text("utf-8"))
    pacote = cifrar(json.dumps(precos, ensure_ascii=False, separators=(",", ":")).encode(),
                    senha)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(pacote), "utf-8")
    print(f"{len(precos)} preços cifrados em {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
