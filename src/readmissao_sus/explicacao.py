"""Contribuição de cada atributo para uma previsão (S10), adaptada de Health-Project/src/explain.py."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import xgboost as xgb
from sklearn.pipeline import Pipeline

from readmissao_sus.modelagem import ATRIBUTOS, ATRIBUTOS_CATEGORICOS, preparar_atributos

PREFIXO_INDICADOR = "missingindicator_"


def atributo_de_origem(nome_transformado: str) -> str:
    """Atributo de uma coluna do pré-processador (ex. "cat__cnes_alta_0000434" -> "cnes_alta")."""
    bloco, resto = nome_transformado.split("__", 1)
    if bloco != "cat":
        return resto.removeprefix(PREFIXO_INDICADOR)
    opcoes = [c for c in ATRIBUTOS_CATEGORICOS if resto == c or resto.startswith(f"{c}_")]
    return max(opcoes, key=len)


def explicar_registro(pipeline: Pipeline, registro: Mapping[str, Any]) -> pd.Series | None:
    """Contribuições SHAP exatas do XGBoost, em log-odds, somadas por atributo de origem.

    Positivo aumenta o risco. Devolve None quando o classificador não é XGBoost.
    """
    classificador = pipeline.named_steps["classificador"]
    if not isinstance(classificador, xgb.XGBClassifier):
        return None
    linha = preparar_atributos(pd.DataFrame([{c: registro.get(c) for c in ATRIBUTOS}]))
    transformado = pipeline[:-1].transform(linha)
    contribuicoes = classificador.get_booster().predict(xgb.DMatrix(transformado), pred_contribs=True)[0]
    nomes = pipeline.named_steps["preprocessador"].get_feature_names_out()
    # O último valor é o termo base do modelo, não um atributo.
    por_atributo = pd.Series(contribuicoes[:-1]).groupby([atributo_de_origem(n) for n in nomes]).sum()
    return por_atributo.sort_values(key=abs, ascending=False)
