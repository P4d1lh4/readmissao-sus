"""Ajuste de risco para comparar hospitais pela razão O/E (S14, D05 em docs/decisoes.md).

O modelo principal usa o hospital da alta (`cnes_alta`) como atributo: o esperado de cada
hospital já carrega parte do efeito dele, e a razão O/E tende a 1. Para comparar hospitais, o
esperado vem de um segundo modelo com os mesmos atributos e o mesmo protocolo, mas sem o
hospital: ele estima o risco de cada alta só pelo perfil do paciente e da internação.

O modelo aprende com as altas de 2023 e pontua as de 2024. Como a taxa muda de um ano para o
outro, o esperado de 2024 é multiplicado por um fator único, para que o total esperado bata com o
total observado. A razão de cada hospital passa a ser relativa à média do estado no ano, e não ao
nível de 2023.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline

from readmissao_sus.modelagem import (
    ALVO,
    ATRIBUTOS_CATEGORICOS,
    alvo,
    candidatos,
    montar_pipeline,
    preparar_atributos,
)
from readmissao_sus.razao_oe import COLUNA_HOSPITAL, COLUNA_PROBABILIDADE

ATRIBUTOS_CATEGORICOS_AJUSTE = tuple(c for c in ATRIBUTOS_CATEGORICOS if c != COLUNA_HOSPITAL)
MODELO_AJUSTE = "XGBoost"


@dataclass(frozen=True)
class AltasAjustadas:
    """Altas do teste com a probabilidade do ajuste já recalibrada, e os agregados do ajuste."""

    altas: pd.DataFrame
    fator_recalibracao: float
    roc_auc_teste: float


def treinar_ajuste(
    treino: pd.DataFrame, random_state: int = 42, classificador: BaseEstimator | None = None
) -> Pipeline:
    """Mesmo pipeline e mesmo XGBoost do modelo principal, sem `cnes_alta`."""
    escolhido = classificador if classificador is not None else candidatos(random_state)[MODELO_AJUSTE]
    pipeline = montar_pipeline(escolhido, categoricos=ATRIBUTOS_CATEGORICOS_AJUSTE)
    return pipeline.fit(preparar_atributos(treino), alvo(treino))


def fator_recalibracao(observado: np.ndarray, esperado: np.ndarray) -> float:
    """Fator que iguala o total esperado ao total observado (observado / esperado)."""
    total_esperado = float(np.sum(esperado))
    if total_esperado <= 0:
        raise ValueError("O total esperado precisa ser positivo para recalibrar.")
    return float(np.sum(observado)) / total_esperado


def pontuar_ajustado(pipeline: Pipeline, teste: pd.DataFrame) -> AltasAjustadas:
    """Pontua o teste em memória e recalibra no total do ano; nada por episódio sai daqui para disco."""
    bruta = pipeline.predict_proba(preparar_atributos(teste))[:, 1]
    y = teste[ALVO].astype(int).to_numpy()
    fator = fator_recalibracao(y, bruta)
    altas = teste.assign(**{COLUNA_PROBABILIDADE: bruta * fator})
    roc = float(roc_auc_score(y, bruta)) if len(np.unique(y)) == 2 else float("nan")
    return AltasAjustadas(altas, fator, roc)
