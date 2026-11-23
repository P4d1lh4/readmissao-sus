"""Baixa para fhir/pacotes/ os pacotes FHIR do Sumário de Alta (decisão D02).

Uso: .venv\\Scripts\\python scripts\\baixar_pacotes_fhir.py
Idempotente: pacote já presente com o SHA-256 esperado não é baixado de novo.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.pacotes_fhir import (  # noqa: E402
    PACOTES,
    ErroPacote,
    baixar_http,
    baixar_pacotes,
    dependencias_externas,
)

DIR_PACOTES = RAIZ / "fhir" / "pacotes"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        baixados = baixar_pacotes(PACOTES, DIR_PACOTES, baixar_http)
        externas = dependencias_externas(PACOTES, DIR_PACOTES)
    except ErroPacote as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"Pacotes FHIR: {len(baixados)} baixado(s), {len(PACOTES) - len(baixados)} já estavam em dia.")
    for pacote in PACOTES:
        print(f"  {DIR_PACOTES.relative_to(RAIZ) / pacote.arquivo}  ({pacote.nome}#{pacote.versao})")
    print("Dependências que o validador busca no registro de pacotes:")
    for nome, versao in externas.items():
        print(f"  {nome}#{versao}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
