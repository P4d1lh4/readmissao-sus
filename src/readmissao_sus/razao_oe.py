"""Razão observado/esperado (O/E) de readmissão por hospital da alta (S11).

O esperado de um hospital é a soma das probabilidades do modelo nas suas altas; o observado é
o número de readmissões não planejadas em 30 dias (alvo da D04). O IC 95% é o de Poisson exato
(Garwood) para o observado, dividido pelo esperado, que é tratado como fixo.

A saída tem só agregados por CNES: nenhuma coluna por episódio.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import chi2
from sklearn.pipeline import Pipeline

from readmissao_sus.modelagem import ALVO, ANO_TESTE, ATRIBUTOS, DATA_ALTA, dividir_por_tempo, preparar_atributos

COLUNA_HOSPITAL = "cnes_alta"
COLUNA_PROBABILIDADE = "probabilidade"
MINIMO_ALTAS = 100
NIVEL_CONFIANCA = 0.95
COLUNAS_SAIDA = ("cnes", "altas", "observado", "esperado", "razao_oe", "ic95_inf", "ic95_sup")


def ic_poisson_exato(observado: np.ndarray, nivel: float = NIVEL_CONFIANCA) -> tuple[np.ndarray, np.ndarray]:
    """Limites exatos (Garwood) para a média de uma Poisson com `observado` eventos."""
    o = np.asarray(observado, dtype=float)
    alfa = 1 - nivel
    inferior = np.where(o > 0, chi2.ppf(alfa / 2, 2 * np.maximum(o, 1)) / 2, 0.0)
    superior = chi2.ppf(1 - alfa / 2, 2 * (o + 1)) / 2
    return inferior, superior


def ler_altas_teste(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Altas do teste (ANO_TESTE até o corte de censura) com os atributos e o alvo."""
    colunas = ", ".join(dict.fromkeys((*ATRIBUTOS, ALVO, DATA_ALTA)))
    altas = con.execute(
        f"select {colunas} from atributo_episodio where year({DATA_ALTA}) = ?", [ANO_TESTE]
    ).df()
    return dividir_por_tempo(altas)[1]


def pontuar(pipeline: Pipeline, altas: pd.DataFrame) -> pd.DataFrame:
    """As mesmas altas com a coluna `probabilidade` do modelo, só em memória."""
    probabilidade = pipeline.predict_proba(preparar_atributos(altas))[:, 1]
    return altas.assign(**{COLUNA_PROBABILIDADE: probabilidade})


def razao_por_hospital(altas: pd.DataFrame, minimo_altas: int = MINIMO_ALTAS) -> pd.DataFrame:
    """Uma linha por CNES com pelo menos `minimo_altas` altas, da maior para a menor razão O/E.

    `altas` precisa de `cnes_alta`, do alvo e de `probabilidade`; altas sem CNES ficam de fora.
    """
    agrupado = (
        altas.dropna(subset=[COLUNA_HOSPITAL])
        .assign(_observado=lambda d: d[ALVO].astype(int))
        .groupby(COLUNA_HOSPITAL)
        .agg(altas=(ALVO, "size"), observado=("_observado", "sum"), esperado=(COLUNA_PROBABILIDADE, "sum"))
    )
    agrupado = agrupado[agrupado["altas"] >= minimo_altas]
    inferior, superior = ic_poisson_exato(agrupado["observado"].to_numpy())
    esperado = agrupado["esperado"].to_numpy()
    tabela = agrupado.assign(
        razao_oe=agrupado["observado"] / esperado,
        ic95_inf=inferior / esperado,
        ic95_sup=superior / esperado,
    )
    tabela = tabela.rename_axis("cnes").reset_index()
    tabela = tabela.astype({"altas": int, "observado": int})
    return tabela.sort_values(["razao_oe", "cnes"], ascending=[False, True]).reset_index(drop=True)[
        list(COLUNAS_SAIDA)
    ]
