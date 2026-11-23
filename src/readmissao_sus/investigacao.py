"""Checagens de vazamento e de mudança de distribuição do modelo (S10).

ROC-AUC acima de 0,80 é tratado como suspeita de vazamento. Estas medidas, todas agregadas,
dizem de onde vem o sinal: AUC de cada atributo sozinho, o vencedor reajustado sem um grupo de
atributos e o teste sem as readmissões em 0–1 dia (que a D03 ainda pode juntar ao episódio).
"""

from __future__ import annotations

import gc
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.metrics import average_precision_score, roc_auc_score

from readmissao_sus.modelagem import (
    ATRIBUTOS_BINARIOS,
    ATRIBUTOS_CATEGORICOS,
    ATRIBUTOS_NUMERICOS,
    alvo,
    montar_pipeline,
    preparar_atributos,
)

GRUPOS_ABLACAO = {
    "sem_historico": (
        "episodios_365d", "dias_internado_365d", "dias_desde_ultima_alta", "historico_com_obito",
    ),
    "sem_cnes_alta": ("cnes_alta",),
}
DIAS_CONTIGUA = 1


def auc_univariada(teste: pd.DataFrame) -> dict[str, float]:
    """ROC-AUC de cada atributo numérico ou sim/não sozinho, na direção que separa melhor."""
    y = alvo(teste)
    x = preparar_atributos(teste)
    resultado = {}
    for coluna in ATRIBUTOS_NUMERICOS + ATRIBUTOS_BINARIOS:
        valores = x[coluna].fillna(x[coluna].max() + 1 if coluna == "dias_desde_ultima_alta" else 0)
        auc = float(roc_auc_score(y, valores))
        resultado[coluna] = max(auc, 1 - auc)
    return dict(sorted(resultado.items(), key=lambda item: -item[1]))


def _anular(x: pd.DataFrame, colunas: tuple[str, ...]) -> pd.DataFrame:
    """Tira o conteúdo das colunas: viram constantes (0 ou "removido") no treino e no teste."""
    return x.assign(**{c: "removido" if c in ATRIBUTOS_CATEGORICOS else 0.0 for c in colunas})


def ablacoes(
    classificador: BaseEstimator, treino: pd.DataFrame, teste: pd.DataFrame
) -> dict[str, dict[str, float]]:
    """Vencedor reajustado sem cada grupo de atributos; métricas no teste."""
    x_treino, x_teste = preparar_atributos(treino), preparar_atributos(teste)
    y_treino, y_teste = alvo(treino), alvo(teste)
    resultado = {}
    for nome, colunas in GRUPOS_ABLACAO.items():
        pipeline = montar_pipeline(classificador).fit(_anular(x_treino, colunas), y_treino)
        proba = pipeline.predict_proba(_anular(x_teste, colunas))[:, 1]
        resultado[nome] = {
            "colunas": list(colunas),
            "roc_auc": float(roc_auc_score(y_teste, proba)),
            "pr_auc": float(average_precision_score(y_teste, proba)),
        }
        del pipeline
        gc.collect()
        print(f"Ablação {nome}: ROC-AUC {resultado[nome]['roc_auc']:.4f}", flush=True)
    return resultado


def sem_readmissao_contigua(teste: pd.DataFrame, proba: np.ndarray) -> dict[str, Any]:
    """Teste sem os positivos cuja readmissão começou em até DIAS_CONTIGUA dia após a alta."""
    y = alvo(teste)
    contigua = (y == 1) & (teste["dias_ate_readmissao"].to_numpy(dtype=float) <= DIAS_CONTIGUA)
    manter = ~contigua
    return {
        "positivos_removidos": int(contigua.sum()),
        "parcela_dos_positivos": float(contigua.sum() / max(int(y.sum()), 1)),
        "roc_auc": float(roc_auc_score(y[manter], proba[manter])),
        "pr_auc": float(average_precision_score(y[manter], proba[manter])),
        "prevalencia": float(y[manter].mean()),
    }

