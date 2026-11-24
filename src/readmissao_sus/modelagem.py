"""Modelo de readmissão em 30 dias com validação temporal (S10).

Adaptado de Health-Project/src/modeling.py para o contrato de `atributo_episodio` (S09,
docs/atributos.md). Treino com as altas de 2023, teste com as de 2024 até o corte de censura
(D01, condição 3). A seleção entre os candidatos usa validação cruzada agrupada pela chave de
linkage dentro do treino; o limiar é o de máximo F1 nas probabilidades out-of-fold.

Quais colunas entram e por quê está em docs/modelo.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

# Alvo da D04 (S13). O da S10, readmissao_30d, fica como coluna auxiliar.
ALVO = "readmissao_nao_planejada_30d"
ALVO_S10 = "readmissao_30d"
CHAVE = "chave"
DATA_ALTA = "dt_saida"
ANO_TREINO = 2023
ANO_TESTE = 2024
# Última alta-índice com os 30 dias seguintes dentro da cobertura completa (D01, tratamento 3).
CORTE_CENSURA = date(2024, 10, 1)

ATRIBUTOS_NUMERICOS = (
    "idade",
    "dias_permanencia",
    "dias_uti",
    "n_aihs",
    "n_hospitais",
    "episodios_365d",
    "dias_internado_365d",
    "dias_desde_ultima_alta",
)
ATRIBUTOS_BINARIOS = (
    "usou_uti",
    "houve_transferencia",
    "houve_permanencia",
    "houve_contigua_sem_motivo",
    "cep_generico",
    "historico_com_obito",
)
ATRIBUTOS_CATEGORICOS = ("sexo", "capitulo_cid", "grupo_sigtap", "car_int", "cnes_alta")
ATRIBUTOS = ATRIBUTOS_NUMERICOS + ATRIBUTOS_BINARIOS + ATRIBUTOS_CATEGORICOS

# Colunas de atributo_episodio que nunca entram no modelo (motivo em docs/modelo.md).
COLUNAS_FORA = {
    "episodio_id": "identificador",
    "chave": "identificador; agrupa a validação cruzada",
    "dt_inter": "data; separa treino e teste",
    "dt_saida": "data; separa treino e teste",
    "readmissao_nao_planejada_30d": "alvo (D04)",
    "readmissao_30d": "alvo da S10; inclui as voltas programadas",
    "ano_alta": "constante dentro do treino e dentro do teste",
    "historico_completo": "constante (falso) em todo o treino; avaliada em separado",
    "chave_colidente": "usa episódios posteriores da chave (futuro); avaliada em separado",
    "episodio_sobreposto": "pode depender de um episódio que termina depois da alta",
}

CV_FOLDS = 5
# Categorias com menos de 0,1% das linhas do treino viram "infrequent" (cerca de 530 episódios
# em 2023): ficam 107 hospitais com coluna própria e o resto num grupo só.
FREQUENCIA_MINIMA_CATEGORIA = 0.001


def candidatos(random_state: int) -> dict[str, BaseEstimator]:
    """Sem pesos de classe: o desbalanceamento fica com o limiar e com a PR-AUC.

    Random Forest e XGBoost com tamanho limitado para caber em CPU com ~500 mil linhas.
    """
    return {
        "LogisticRegression": LogisticRegression(max_iter=1000),
        "RandomForest": RandomForestClassifier(
            n_estimators=100,
            max_depth=14,
            min_samples_leaf=50,
            max_features="sqrt",
            n_jobs=-1,
            random_state=random_state,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=20,
            tree_method="hist",
            eval_metric="logloss",
            n_jobs=-1,
            random_state=random_state,
        ),
    }


def _para_float32(x: np.ndarray) -> np.ndarray:
    return np.asarray(x, dtype=np.float32)


def montar_pipeline(
    classificador: BaseEstimator, categoricos: tuple[str, ...] = ATRIBUTOS_CATEGORICOS
) -> Pipeline:
    """Colunas de ATRIBUTOS -> pré-processamento -> classificador.

    `categoricos` permite tirar uma categoria do modelo (o ajuste de risco tira `cnes_alta`); as
    colunas fora das listas são descartadas pelo ColumnTransformer.

    `dias_desde_ultima_alta` é nula quando não há episódio anterior: a mediana entra no lugar
    e uma coluna indicadora diz que faltava. A saída é densa: o XGBoost leria os zeros
    implícitos de uma matriz esparsa como ausentes. Em float32, para a matriz do treino inteiro
    (~530 mil x ~150) caber na memória de um notebook.
    """
    numericos = Pipeline(
        steps=[
            ("imputador", SimpleImputer(strategy="median", add_indicator=True)),
            ("escala", StandardScaler()),
            ("float32", FunctionTransformer(_para_float32, feature_names_out="one-to-one")),
        ]
    )
    categoricos_pipeline = Pipeline(
        steps=[
            ("imputador", SimpleImputer(strategy="constant", fill_value="ausente")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",
                    min_frequency=FREQUENCIA_MINIMA_CATEGORIA,
                    sparse_output=False,
                    dtype=np.float32,
                ),
            ),
        ]
    )
    preprocessador = ColumnTransformer(
        transformers=[
            ("num", numericos, list(ATRIBUTOS_NUMERICOS)),
            ("bin", "passthrough", list(ATRIBUTOS_BINARIOS)),
            ("cat", categoricos_pipeline, list(categoricos)),
        ],
        sparse_threshold=0.0,
    )
    return Pipeline(steps=[("preprocessador", preprocessador), ("classificador", clone(classificador))])


def preparar_atributos(episodios: pd.DataFrame) -> pd.DataFrame:
    """Só as colunas de ATRIBUTOS, com sim/não como 0/1 e categorias como texto (nulo = NaN)."""
    x = episodios[list(ATRIBUTOS)].copy()
    for coluna in ATRIBUTOS_BINARIOS:
        x[coluna] = x[coluna].astype("float32")
    for coluna in ATRIBUTOS_NUMERICOS:
        x[coluna] = pd.to_numeric(x[coluna], errors="coerce").astype("float64")
    for coluna in ATRIBUTOS_CATEGORICOS:
        x[coluna] = x[coluna].astype(object).where(x[coluna].notna(), np.nan)
    return x


def alvo(episodios: pd.DataFrame) -> np.ndarray:
    return episodios[ALVO].astype(int).to_numpy()


def dividir_por_tempo(episodios: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Treino = altas de ANO_TREINO; teste = altas de ANO_TESTE até CORTE_CENSURA.

    A mesma chave pode aparecer nos dois lados, como aconteceria em uso: o modelo treinado com
    o passado pontua as altas seguintes de qualquer pessoa.
    """
    alta = pd.to_datetime(episodios[DATA_ALTA])
    treino = episodios[alta.dt.year == ANO_TREINO]
    teste = episodios[(alta.dt.year == ANO_TESTE) & (alta <= pd.Timestamp(CORTE_CENSURA))]
    return treino.reset_index(drop=True), teste.reset_index(drop=True)


def amostrar_por_chave(treino: pd.DataFrame, fracao: float, random_state: int) -> pd.DataFrame:
    """Amostra de chaves inteiras (todos os episódios da chave sorteada), para a validação cruzada."""
    if not 0 < fracao <= 1:
        raise ValueError(f"fracao deve estar em (0, 1]; recebido {fracao}.")
    if fracao == 1:
        return treino
    chaves = pd.Series(treino[CHAVE].unique())
    sorteadas = chaves.sample(frac=fracao, random_state=random_state)
    return treino[treino[CHAVE].isin(set(sorteadas))].reset_index(drop=True)


def folds_por_chave(
    episodios: pd.DataFrame, n_splits: int, random_state: int
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Folds agrupados pela chave: cada chave sorteada vai inteira para um fold só.

    As chaves são embaralhadas e distribuídas em rodízio entre os folds. Com ~400 mil chaves a
    prevalência fica parecida entre os folds sem estratificar; o StratifiedGroupKFold e o
    GroupKFold do scikit-learn levaram minutos só para montar os folds nesse volume.
    """
    codigos, unicas = pd.factorize(episodios[CHAVE])
    ordem = np.random.default_rng(random_state).permutation(len(unicas))
    fold_da_chave = np.empty(len(unicas), dtype=int)
    fold_da_chave[ordem] = np.arange(len(unicas)) % n_splits
    fold = fold_da_chave[codigos]
    return [(np.flatnonzero(fold != k), np.flatnonzero(fold == k)) for k in range(n_splits)]


@dataclass(frozen=True)
class ResultadoCV:
    roc_auc_folds: tuple[float, ...]
    pr_auc_folds: tuple[float, ...]
    proba_oof: np.ndarray

    def resumo(self) -> dict[str, float]:
        return {
            "roc_auc_media": float(np.mean(self.roc_auc_folds)),
            "roc_auc_desvio": float(np.std(self.roc_auc_folds)),
            "pr_auc_media": float(np.mean(self.pr_auc_folds)),
            "pr_auc_desvio": float(np.std(self.pr_auc_folds)),
        }


def validar_candidato(
    classificador: BaseEstimator,
    episodios: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
) -> ResultadoCV:
    """Validação cruzada com os folds dados, guardando as probabilidades out-of-fold."""
    x = preparar_atributos(episodios)
    y = alvo(episodios)
    oof = np.full(len(episodios), np.nan)
    roc, pr = [], []
    for idx_ajuste, idx_validacao in folds:
        pipeline = montar_pipeline(classificador).fit(x.iloc[idx_ajuste], y[idx_ajuste])
        proba = pipeline.predict_proba(x.iloc[idx_validacao])[:, 1]
        oof[idx_validacao] = proba
        roc.append(float(roc_auc_score(y[idx_validacao], proba)))
        pr.append(float(average_precision_score(y[idx_validacao], proba)))
    return ResultadoCV(tuple(roc), tuple(pr), oof)


def escolher_limiar(y_true: np.ndarray, proba: np.ndarray) -> float:
    """Limiar que maximiza o F1 nas probabilidades out-of-fold."""
    precisao, recall, limiares = precision_recall_curve(y_true, proba)
    p, r = precisao[:-1], recall[:-1]
    f1 = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) > 0)
    return float(limiares[int(np.argmax(f1))])
