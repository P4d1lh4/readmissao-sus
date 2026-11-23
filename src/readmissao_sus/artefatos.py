"""Leitura do modelo salvo em models/ (S10), adaptada de Health-Project/src/artifacts.py."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from joblib import load
from sklearn.pipeline import Pipeline

from readmissao_sus.modelagem import ATRIBUTOS, preparar_atributos
from readmissao_sus.treino import ARQUIVO_METADATA, ARQUIVO_MODELO


@dataclass(frozen=True)
class Previsao:
    probabilidade: float
    limiar: float
    alerta: int


@dataclass(frozen=True)
class Artefatos:
    pipeline: Pipeline
    modelo: str
    limiar: float

    def prever(self, registro: Mapping[str, Any]) -> Previsao:
        """Prevê a partir de um episódio; campos ausentes viram nulos e são imputados."""
        linha = preparar_atributos(pd.DataFrame([{c: registro.get(c) for c in ATRIBUTOS}]))
        probabilidade = float(self.pipeline.predict_proba(linha)[0, 1])
        return Previsao(probabilidade, self.limiar, int(probabilidade >= self.limiar))


def carregar_artefatos(dir_modelo: Path) -> Artefatos:
    metadata = json.loads((dir_modelo / ARQUIVO_METADATA).read_text(encoding="utf-8"))
    if list(metadata["atributos"]) != list(ATRIBUTOS):
        raise ValueError(
            "Os atributos do modelo salvo divergem de modelagem.ATRIBUTOS; treine o modelo de novo."
        )
    return Artefatos(
        pipeline=load(dir_modelo / ARQUIVO_MODELO),
        modelo=metadata["modelo"],
        limiar=float(metadata["limiar"]),
    )
