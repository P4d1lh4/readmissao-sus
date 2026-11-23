"""Regra da readmissão programada (D04, S13), usada em sql/04_episodio.sql.

A volta (o episódio seguinte em até 30 dias) é programada quando a primeira AIH dela é eletiva
(CAR_INT 01, se `eletiva`) ou tem procedimento ou diagnóstico principal de
`dicionario_sih.SEMPRE_PROGRAMADOS`. A volta programada não conta como readmissão no alvo
`readmissao_nao_planejada_30d` e também não censura: uma volta não planejada depois dela, ainda
dentro dos 30 dias, conta.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from readmissao_sus import dicionario_sih as dic

TIPOS = ("procedimento", "cid")


@dataclass(frozen=True)
class RegraProgramada:
    eletiva: bool = True
    sempre_programados: tuple[tuple[str, str, str], ...] = dic.SEMPRE_PROGRAMADOS

    def __post_init__(self) -> None:
        invalidos = [t for t, _, _ in self.sempre_programados if t not in TIPOS]
        if invalidos:
            raise ValueError(f"Tipo inválido em sempre_programados: {invalidos} (use {TIPOS}).")


REGRA_PROGRAMADA_PADRAO = RegraProgramada()


def carregar_regra(con: duckdb.DuckDBPyConnection, regra: RegraProgramada) -> None:
    """Cria dic_sempre_programado e a variável eletiva_programada lidas por 04_episodio.sql."""
    con.execute("set variable eletiva_programada = ?", [regra.eletiva])
    con.execute("set variable car_int_eletivo = ?", [dic.CAR_INT_ELETIVO])
    con.execute(
        "create or replace table dic_sempre_programado "
        "(tipo varchar, prefixo varchar, descricao varchar, primary key (tipo, prefixo))"
    )
    if regra.sempre_programados:
        con.executemany("insert into dic_sempre_programado values (?, ?, ?)",
                        list(regra.sempre_programados))
