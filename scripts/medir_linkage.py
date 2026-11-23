"""Mede a viabilidade do linkage determinístico (S03) e grava os números em docs/decisoes.md.

Uso: .venv\\Scripts\\python scripts\\medir_linkage.py
Lê data/parquet/RDPE*.parquet. A chave só existe como hash, em memória; o documento recebe
apenas agregados, entre as marcas do bloco gerado (o resto do arquivo não é tocado).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import duckdb  # noqa: E402

from readmissao_sus.linkage_viabilidade import analisar  # noqa: E402
from readmissao_sus.relatorio_linkage import gerar_bloco, gravar_bloco  # noqa: E402

DIR_PARQUET = RAIZ / "data" / "parquet"
DECISOES = RAIZ / "docs" / "decisoes.md"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    arquivos = sorted(DIR_PARQUET.glob("RDPE*.parquet"))
    if not arquivos:
        print(f"ERRO: nenhum RDPE*.parquet em {DIR_PARQUET}. Rode scripts/baixar_sih.py antes.", file=sys.stderr)
        return 1
    con = duckdb.connect()
    lista = ", ".join(f"'{p.as_posix()}'" for p in arquivos)
    con.execute(f"create view rd as select * from read_parquet([{lista}], union_by_name = true)")
    resultado = analisar(con, "rd")
    bloco = gerar_bloco(resultado, date.today().strftime("%d/%m/%Y"))
    gravar_bloco(DECISOES, bloco)
    print(bloco)
    print(f"\nBloco gravado em {DECISOES.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
