"""Execução do SQL versionado em sql/ (a única fonte das regras de internação, coorte e episódio)."""

from __future__ import annotations

from pathlib import Path

import duckdb

DIR_SQL = Path(__file__).resolve().parents[2] / "sql"


def executar_sql(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute((DIR_SQL / nome).read_text(encoding="utf-8"))
