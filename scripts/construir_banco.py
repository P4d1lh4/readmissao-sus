"""Recria data/sih.duckdb do zero a partir dos Parquet e atualiza as contagens em docs/coorte.md.

Uso: .venv\\Scripts\\python scripts\\construir_banco.py
Lê data/parquet/RDPE*.parquet e roda o SQL de sql/ (staging, internações, coorte). O sal da
chave de linkage vem da variável READMISSAO_SAL_CHAVE ou de data/sal_chave.txt (criado na
primeira vez; fora do git). O documento recebe só agregados.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.banco import construir_banco, obter_sal  # noqa: E402
from readmissao_sus.relatorio_coorte import gerar_bloco, gravar_bloco  # noqa: E402

DIR_PARQUET = RAIZ / "data" / "parquet"
BANCO = RAIZ / "data" / "sih.duckdb"
ARQUIVO_SAL = RAIZ / "data" / "sal_chave.txt"
DOC_COORTE = RAIZ / "docs" / "coorte.md"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    arquivos = sorted(DIR_PARQUET.glob("RDPE*.parquet"))
    if not arquivos:
        print(f"ERRO: nenhum RDPE*.parquet em {DIR_PARQUET}. Rode scripts/baixar_sih.py antes.",
              file=sys.stderr)
        return 1
    construcao = construir_banco(BANCO, arquivos, obter_sal(ARQUIVO_SAL))
    bloco = gerar_bloco(construcao, date.today().strftime("%d/%m/%Y"))
    gravar_bloco(DOC_COORTE, bloco)
    print(bloco)
    print(f"\nBanco recriado em {BANCO.relative_to(RAIZ)} a partir de {len(arquivos)} arquivos.")
    print(f"Bloco gravado em {DOC_COORTE.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
