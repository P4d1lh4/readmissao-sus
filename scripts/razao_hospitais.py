"""Gera reports/hospitais_oe.csv: razão observado/esperado por hospital no teste 2024 (S11).

Uso: .venv\\Scripts\\python scripts\\razao_hospitais.py [--minimo-altas 100]
Lê as altas do teste de atributo_episodio (data/sih.duckdb, só leitura) e o modelo de models/,
pontua as altas em memória e grava só agregados por CNES: altas, observado, esperado (soma das
probabilidades), razão O/E e IC 95% de Poisson exato. Nenhuma probabilidade por episódio é gravada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.artefatos import carregar_artefatos  # noqa: E402
from readmissao_sus.razao_oe import MINIMO_ALTAS, ler_altas_teste, pontuar, razao_por_hospital  # noqa: E402

BANCO = RAIZ / "data" / "sih.duckdb"
DIR_MODELO = RAIZ / "models"
SAIDA = RAIZ / "reports" / "hospitais_oe.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Razão O/E de readmissão por hospital (S11).")
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--dir-modelo", type=Path, default=DIR_MODELO)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--minimo-altas", type=int, default=MINIMO_ALTAS)
    args = parser.parse_args(argv)
    if not args.banco.is_file():
        sys.exit(f"Banco não encontrado: {args.banco}. Rode scripts\\construir_banco.py antes.")

    artefatos = carregar_artefatos(args.dir_modelo)
    with duckdb.connect(str(args.banco), read_only=True) as con:
        altas = ler_altas_teste(con)
    tabela = razao_por_hospital(pontuar(artefatos.pipeline, altas), args.minimo_altas)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(args.saida, index=False, float_format="%.6f")
    print(
        f"{len(altas):,} altas do teste; {len(tabela)} hospitais com >= {args.minimo_altas} altas "
        f"gravados em {args.saida}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
