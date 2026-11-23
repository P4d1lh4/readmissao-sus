"""Métricas do modelo de readmissão (S10): teste, grupos, calibração e importância.

Tudo aqui devolve agregados (contagens, médias, curvas por faixa); nada por episódio.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

FAIXAS_CALIBRACAO = 10
REPETICOES_PERMUTACAO = 3


def avaliar(y_true: np.ndarray, proba: np.ndarray, limiar: float) -> dict[str, Any]:
    """Métricas no limiar dado. ROC-AUC e PR-AUC ficam nulas se o grupo tiver uma classe só."""
    previsto = (proba >= limiar).astype(int)
    precisao, recall, f1, _ = precision_recall_fscore_support(
        y_true, previsto, average="binary", zero_division=0
    )
    duas_classes = len(np.unique(y_true)) == 2
    return {
        "episodios": int(len(y_true)),
        "roc_auc": float(roc_auc_score(y_true, proba)) if duas_classes else None,
        "pr_auc": float(average_precision_score(y_true, proba)) if duas_classes else None,
        "brier": float(brier_score_loss(y_true, proba, labels=[0, 1])),
        "prevalencia": float(np.mean(y_true)),
        "proba_media": float(np.mean(proba)),
        "limiar": limiar,
        "precisao": float(precisao),
        "recall": float(recall),
        "f1": float(f1),
        "matriz_confusao": confusion_matrix(y_true, previsto, labels=[0, 1]).tolist(),
    }


def avaliar_por_grupo(
    episodios: pd.DataFrame,
    y_true: np.ndarray,
    proba: np.ndarray,
    limiar: float,
    colunas: tuple[str, ...],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Métricas separadas por valor de cada coluna (ex. cep_generico sim/não), no mesmo limiar."""
    resultado: dict[str, dict[str, dict[str, Any]]] = {}
    for coluna in colunas:
        valores = episodios[coluna].to_numpy()
        resultado[coluna] = {
            _rotulo(valor): avaliar(y_true[valores == valor], proba[valores == valor], limiar)
            for valor in sorted(pd.unique(valores))
        }
    return resultado


def _rotulo(valor: Any) -> str:
    if isinstance(valor, (bool, np.bool_)):
        return "sim" if valor else "não"
    return str(valor)


def calibracao(y_true: np.ndarray, proba: np.ndarray, faixas: int = FAIXAS_CALIBRACAO) -> dict[str, Any]:
    """Previsto x observado em faixas de igual tamanho (decis da probabilidade prevista)."""
    ordem = np.argsort(proba, kind="stable")
    linhas = []
    for indices in np.array_split(ordem, faixas):
        if len(indices) == 0:
            continue
        linhas.append(
            {
                "episodios": int(len(indices)),
                "proba_min": float(proba[indices].min()),
                "proba_max": float(proba[indices].max()),
                "previsto_medio": float(proba[indices].mean()),
                "observado": float(y_true[indices].mean()),
            }
        )
    diferencas = [abs(f["previsto_medio"] - f["observado"]) for f in linhas]
    pesos = [f["episodios"] for f in linhas]
    return {
        "faixas": linhas,
        "maior_diferenca": float(max(diferencas)),
        "diferenca_media_ponderada": float(np.average(diferencas, weights=pesos)),
    }


def importancia_permutacao(
    pipeline: Pipeline, x: pd.DataFrame, y: np.ndarray, random_state: int
) -> pd.DataFrame:
    """Queda de ROC-AUC ao embaralhar cada coluna de entrada (uma linha por atributo)."""
    resultado = permutation_importance(
        pipeline, x, y, scoring="roc_auc", n_repeats=REPETICOES_PERMUTACAO, random_state=random_state
    )
    return (
        pd.DataFrame(
            {
                "atributo": list(x.columns),
                "queda_roc_auc_media": resultado.importances_mean,
                "queda_roc_auc_desvio": resultado.importances_std,
            }
        )
        .sort_values("queda_roc_auc_media", ascending=False)
        .reset_index(drop=True)
    )


def resumo_historico(episodios: pd.DataFrame) -> dict[str, Any]:
    """Como o histórico da chave aparece num conjunto (mostra a mudança entre 2023 e 2024)."""
    com_anterior = episodios["episodios_365d"] > 0
    return {
        "episodios": int(len(episodios)),
        "historico_completo": float(episodios["historico_completo"].astype(float).mean()),
        "com_episodio_365d": float(com_anterior.mean()),
        "media_episodios_365d": float(episodios["episodios_365d"].mean()),
        "media_dias_internado_365d": float(episodios["dias_internado_365d"].mean()),
        "sem_episodio_anterior": float(episodios["dias_desde_ultima_alta"].isna().mean()),
        "readmissao_30d": float(episodios["readmissao_30d"].astype(float).mean()),
    }
