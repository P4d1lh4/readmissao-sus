"""Episódios sintéticos no formato de atributo_episodio e um modelo salvo, para os testes (S10, S11)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.linear_model import LogisticRegression

from readmissao_sus.modelagem import ATRIBUTOS, alvo, montar_pipeline, preparar_atributos
from readmissao_sus.treino import ARQUIVO_METADATA, ARQUIVO_MODELO

INICIO = date(2023, 1, 1)
FIM = date(2024, 12, 31)
HOSPITAIS = ("0000434", "0000655", "0000477", "2427427", "9999999")


def episodios_sinteticos(n: int, seed: int = 0) -> pd.DataFrame:
    """`n` episódios de ~n/3 chaves, com altas espalhadas por 2023 e 2024 (inclusive após o corte).

    O alvo depende do histórico e da idade, para que o modelo tenha sinal a aprender.
    """
    rng = np.random.default_rng(seed)
    dias = (FIM - INICIO).days
    saida = [INICIO + timedelta(days=int(d)) for d in rng.integers(0, dias + 1, n)]
    permanencia = rng.integers(0, 15, n)
    episodios_365d = rng.poisson(0.4, n)
    idade = rng.integers(0, 95, n).astype(float)
    idade[0] = np.nan
    logito = -2.2 + 0.8 * episodios_365d + 0.01 * (idade - 50) + 0.05 * permanencia
    readmissao = rng.random(n) < 1 / (1 + np.exp(-np.nan_to_num(logito)))
    desde_ultima = np.where(episodios_365d > 0, rng.integers(0, 365, n), np.nan)
    entrada = [s - timedelta(days=int(p)) for s, p in zip(saida, permanencia)]
    return pd.DataFrame(
        {
            "episodio_id": [f"E{i:06d}" for i in range(n)],
            "chave": [f"K{k:05d}" for k in rng.integers(0, max(n // 3, 1), n)],
            "readmissao_nao_planejada_30d": readmissao,
            "readmissao_30d": readmissao | (rng.random(n) < 0.05),
            "idade": idade,
            "sexo": rng.choice(["F", "M"], n),
            "capitulo_cid": rng.choice(["IX", "XV", "II", "X"], n),
            "grupo_sigtap": rng.choice(["03", "04"], n),
            "car_int": rng.choice(["01", "02"], n),
            "dias_permanencia": permanencia,
            "dias_uti": rng.integers(0, 3, n),
            "usou_uti": rng.random(n) < 0.1,
            "n_aihs": rng.integers(1, 3, n),
            "n_hospitais": np.ones(n, dtype=int),
            "houve_transferencia": rng.random(n) < 0.05,
            "houve_permanencia": rng.random(n) < 0.05,
            "houve_contigua_sem_motivo": np.zeros(n, dtype=bool),
            "cep_generico": rng.random(n) < 0.45,
            "cnes_alta": rng.choice(HOSPITAIS, n),
            "ano_alta": [s.year for s in saida],
            "dt_inter": entrada,
            "dt_saida": saida,
            "historico_completo": [e >= date(2024, 1, 1) for e in entrada],
            "episodios_365d": episodios_365d,
            "dias_internado_365d": episodios_365d * rng.integers(0, 10, n),
            "dias_desde_ultima_alta": desde_ultima,
            "historico_com_obito": np.zeros(n, dtype=bool),
            "chave_colidente": rng.random(n) < 0.02,
            "episodio_sobreposto": np.zeros(n, dtype=bool),
            "dias_ate_readmissao": np.where(readmissao, rng.integers(0, 31, n), np.nan),
        }
    )


def salvar_modelo_sintetico(dir_modelo: Path, limiar: float = 0.2, n: int = 600, seed: int = 0) -> Path:
    """Regressão logística treinada em episódios sintéticos, gravada como em models/ (S11)."""
    episodios = episodios_sinteticos(n, seed=seed)
    pipeline = montar_pipeline(LogisticRegression(max_iter=500)).fit(preparar_atributos(episodios), alvo(episodios))
    dir_modelo.mkdir(parents=True, exist_ok=True)
    dump(pipeline, dir_modelo / ARQUIVO_MODELO)
    metadata = {"modelo": "LogisticRegression", "atributos": list(ATRIBUTOS), "limiar": limiar}
    (dir_modelo / ARQUIVO_METADATA).write_text(json.dumps(metadata), encoding="utf-8")
    return dir_modelo
