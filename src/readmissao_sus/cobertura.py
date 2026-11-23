"""Cobertura dos dados e data de corte da censura (D01, tratamento 3).

AIHs de uma saída aparecem em competências até alguns meses depois. A cobertura completa vai até
o último mês de saída em que pelo menos LIMIAR_COMPLETUDE das AIHs já foram processadas; a
alta-índice precisa ter os JANELA_DIAS seguintes dentro dela.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

JANELA_DIAS = 30
LIMIAR_COMPLETUDE = 0.98
LAG_MAXIMO_MESES = 6


@dataclass(frozen=True)
class Cobertura:
    ultima_competencia: str
    completude_por_lag: dict[int, float]
    fim: date
    inicio: date
    limite_indice: date


def calcular_cobertura(con: duckdb.DuckDBPyConnection, relacao: str = "competencias") -> Cobertura:
    """Estima, pelo atraso entre saída e competência, até quando as saídas estão completas.

    `relacao` tem uma linha por AIH IDENT=1 (sem deduplicar), com `dt_saida` e `competencia`
    (primeiro dia do mês da competência), ambas do tipo DATE.

    A completude do mês de saída m é a fração de AIHs processadas até (última competência - m)
    meses depois, medida nas saídas antigas o bastante para terem o atraso todo observado.
    """
    primeira, ultima = con.execute(
        f"select min(competencia), max(competencia) from {relacao}"
    ).fetchone()
    ultima_idx = _indice_mes(ultima)
    linhas = con.execute(
        f"""
        with t as (
            select {_sql_indice_mes('competencia')} - {_sql_indice_mes('dt_saida')} as lag
            from {relacao}
            where dt_saida is not null and {_sql_indice_mes('dt_saida')} between ? and ?
        )
        select lag, count(*) from t group by lag order by lag
        """,
        [_indice_mes(primeira), ultima_idx - LAG_MAXIMO_MESES],
    ).fetchall()
    total = sum(n for _, n in linhas)
    acumulado, completude = 0, {}
    for lag, n in linhas:
        acumulado += n
        completude[int(lag)] = acumulado / total if total else 0.0
    lag_minimo = min((lag for lag, f in completude.items() if f >= LIMIAR_COMPLETUDE), default=0)
    fim = _ultimo_dia_do_mes(ultima_idx - lag_minimo)
    inicio = _primeiro_dia_do_mes(_indice_mes(primeira))
    return Cobertura(
        ultima.strftime("%Y%m"), completude, fim, inicio, fim - timedelta(days=JANELA_DIAS)
    )


def _indice_mes(d: date) -> int:
    return d.year * 12 + d.month - 1


def _sql_indice_mes(expr: str) -> str:
    return f"(year({expr}) * 12 + month({expr}) - 1)"


def _primeiro_dia_do_mes(indice: int) -> date:
    return date(indice // 12, indice % 12 + 1, 1)


def _ultimo_dia_do_mes(indice: int) -> date:
    return _primeiro_dia_do_mes(indice + 1) - timedelta(days=1)
