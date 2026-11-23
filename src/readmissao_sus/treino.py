"""Treino, avaliação e gravação do modelo de readmissão (S10).

Fluxo: divisão temporal -> validação cruzada agrupada pela chave (no treino ou numa amostra de
chaves do treino) -> limiar pelo máximo F1 out-of-fold -> reajuste do vencedor no treino inteiro
-> avaliação única no teste (geral, por grupo, calibração e importância por permutação) ->
modelo em models/ e agregados em reports/.
"""

from __future__ import annotations

import gc
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import sklearn
import xgboost
from joblib import dump
from sklearn.base import BaseEstimator

from readmissao_sus import avaliacao, investigacao
from readmissao_sus.modelagem import (
    ANO_TESTE,
    ANO_TREINO,
    ATRIBUTOS,
    CHAVE,
    COLUNAS_FORA,
    CORTE_CENSURA,
    CV_FOLDS,
    alvo,
    amostrar_por_chave,
    candidatos,
    dividir_por_tempo,
    escolher_limiar,
    folds_por_chave,
    montar_pipeline,
    preparar_atributos,
    validar_candidato,
)

ARQUIVO_MODELO = "modelo.joblib"
ARQUIVO_METADATA = "metadata.json"
ARQUIVO_METRICAS = "metrics.json"
ARQUIVO_IMPORTANCIA = "importancia_atributos.csv"

GRUPOS_AVALIACAO = ("cep_generico", "historico_completo", "chave_colidente", "car_int")
COLUNAS_LEITURA = ("episodio_id", CHAVE, "readmissao_30d", "dt_inter", "dt_saida", *ATRIBUTOS,
                   "historico_completo", "chave_colidente")
# Variante para medir o efeito do histórico incompleto de 2023: treino só com entradas a partir
# desta data, que têm ao menos 181 dias de dados antes da entrada.
INICIO_VARIANTE_HISTORICO = date(2023, 7, 1)


def ler_atributos(banco: Path) -> pd.DataFrame:
    """Lê de atributo_episodio só as colunas que o treino usa (banco aberto só para leitura)."""
    """Lê de atributo_episodio as colunas do treino e, de coorte_episodio, `dias_ate_readmissao`.

    `dias_ate_readmissao` nunca é atributo: só separa no teste as readmissões em 0–1 dia.
    """
    colunas = ", ".join(f"a.{c}" for c in dict.fromkeys(COLUNAS_LEITURA))
    with duckdb.connect(str(banco), read_only=True) as con:
        return con.sql(
            f"select {colunas}, c.dias_ate_readmissao from atributo_episodio a "
            "join coorte_episodio c using (episodio_id) order by a.episodio_id"
        ).df()


def _escrever_json(caminho: Path, conteudo: dict[str, Any]) -> None:
    caminho.write_text(json.dumps(conteudo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _contagens(treino: pd.DataFrame, teste: pd.DataFrame, amostra_cv: pd.DataFrame) -> dict[str, int]:
    return {
        "treino_episodios": int(len(treino)),
        "treino_chaves": int(treino[CHAVE].nunique()),
        "teste_episodios": int(len(teste)),
        "teste_chaves": int(teste[CHAVE].nunique()),
        "chaves_em_treino_e_teste": int(len(set(treino[CHAVE]) & set(teste[CHAVE]))),
        "cv_episodios": int(len(amostra_cv)),
        "cv_chaves": int(amostra_cv[CHAVE].nunique()),
    }


def _variante_historico(
    classificador: BaseEstimator, treino: pd.DataFrame, teste: pd.DataFrame, limiar: float
) -> dict[str, Any]:
    """Mesmo modelo treinado só com as entradas de 2023 com mais histórico nos dados."""
    recorte = treino[pd.to_datetime(treino["dt_inter"]) >= pd.Timestamp(INICIO_VARIANTE_HISTORICO)]
    pipeline = montar_pipeline(classificador).fit(preparar_atributos(recorte), alvo(recorte))
    proba = pipeline.predict_proba(preparar_atributos(teste))[:, 1]
    y = alvo(teste)
    return {
        "descricao": (
            f"vencedor treinado só com entradas a partir de {INICIO_VARIANTE_HISTORICO:%d/%m/%Y}, "
            "com o limiar do modelo principal"
        ),
        "treino_episodios": int(len(recorte)),
        "teste": avaliacao.avaliar(y, proba, limiar),
        "teste_por_grupo": avaliacao.avaliar_por_grupo(teste, y, proba, limiar, ("historico_completo",)),
    }


def treinar_e_salvar(
    episodios: pd.DataFrame,
    dir_modelo: Path,
    dir_relatorios: Path,
    random_state: int = 42,
    n_splits: int = CV_FOLDS,
    fracao_cv: float = 1.0,
    max_linhas_importancia: int | None = None,
    classificadores: dict[str, BaseEstimator] | None = None,
    com_variante_historico: bool = True,
    com_investigacao: bool = True,
) -> dict[str, Any]:
    """Seleciona, ajusta, avalia uma vez no teste e grava modelo, metadata e métricas agregadas."""
    inicio = time.perf_counter()
    opcoes = classificadores if classificadores is not None else candidatos(random_state)
    treino, teste = dividir_por_tempo(episodios)
    amostra_cv = amostrar_por_chave(treino, fracao_cv, random_state)
    folds = folds_por_chave(amostra_cv, n_splits, random_state)

    resultados, tempos_cv = {}, {}
    for nome, classificador in opcoes.items():
        t0 = time.perf_counter()
        resultados[nome] = validar_candidato(classificador, amostra_cv, folds)
        tempos_cv[nome] = round(time.perf_counter() - t0, 1)
        print(f"CV {nome}: {resultados[nome].resumo()} ({tempos_cv[nome]} s)", flush=True)
    cv = {nome: {**r.resumo(), "segundos": tempos_cv[nome]} for nome, r in resultados.items()}
    vencedor = max(cv, key=lambda nome: cv[nome]["roc_auc_media"])
    limiar = escolher_limiar(alvo(amostra_cv), resultados[vencedor].proba_oof)

    pipeline = montar_pipeline(opcoes[vencedor]).fit(preparar_atributos(treino), alvo(treino))
    y_teste = alvo(teste)
    proba = pipeline.predict_proba(preparar_atributos(teste))[:, 1]
    del resultados
    gc.collect()
    print(f"Teste {vencedor}: ROC-AUC {avaliacao.avaliar(y_teste, proba, limiar)['roc_auc']:.4f}", flush=True)

    amostra_imp = teste
    if max_linhas_importancia is not None and len(teste) > max_linhas_importancia:
        amostra_imp = teste.sample(n=max_linhas_importancia, random_state=random_state)
    importancias = avaliacao.importancia_permutacao(
        pipeline, preparar_atributos(amostra_imp), alvo(amostra_imp), random_state
    )

    contagens = _contagens(treino, teste, amostra_cv)
    metricas: dict[str, Any] = {
        "modelo_vencedor": vencedor,
        "divisao": (
            f"treino = altas de {ANO_TREINO}; teste = altas de {ANO_TESTE} até "
            f"{CORTE_CENSURA:%d/%m/%Y} (corte de censura da D01)"
        ),
        "validacao_cruzada": (
            f"{n_splits} folds agrupados por chave (chaves embaralhadas, uma chave num fold só), em "
            f"{fracao_cv:.0%} das chaves do treino (amostra de chaves inteiras)"
        ),
        "selecao": "maior ROC-AUC média na validação cruzada",
        "limiar_selecao": "máximo F1 nas probabilidades out-of-fold do vencedor",
        "random_state": random_state,
        "atributos": list(ATRIBUTOS),
        "colunas_fora": COLUNAS_FORA,
        **contagens,
        "cv": cv,
        "teste": avaliacao.avaliar(y_teste, proba, limiar),
        "teste_por_grupo": avaliacao.avaliar_por_grupo(teste, y_teste, proba, limiar, GRUPOS_AVALIACAO),
        "calibracao_teste": avaliacao.calibracao(y_teste, proba),
        "historico_treino": avaliacao.resumo_historico(treino),
        "historico_teste": avaliacao.resumo_historico(teste),
        "importancia_episodios": int(len(amostra_imp)),
    }
    if com_variante_historico:
        metricas["variante_historico"] = _variante_historico(opcoes[vencedor], treino, teste, limiar)
    if com_investigacao:
        metricas["investigacao_vazamento"] = {
            "auc_univariada_teste": investigacao.auc_univariada(teste),
            "teste_sem_readmissao_0_1_dia": investigacao.sem_readmissao_contigua(teste, proba),
            "ablacoes_teste": investigacao.ablacoes(opcoes[vencedor], treino, teste),
        }
    metricas["segundos_total"] = round(time.perf_counter() - inicio, 1)

    metadata = {
        "modelo": vencedor,
        "atributos": list(ATRIBUTOS),
        "limiar": limiar,
        "random_state": random_state,
        "versao_sklearn": sklearn.__version__,
        "versao_xgboost": xgboost.__version__,
        "treinado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corte_censura": CORTE_CENSURA.isoformat(),
        **contagens,
    }
    dir_modelo.mkdir(parents=True, exist_ok=True)
    dir_relatorios.mkdir(parents=True, exist_ok=True)
    dump(pipeline, dir_modelo / ARQUIVO_MODELO)
    _escrever_json(dir_modelo / ARQUIVO_METADATA, metadata)
    _escrever_json(dir_relatorios / ARQUIVO_METRICAS, metricas)
    importancias.to_csv(dir_relatorios / ARQUIVO_IMPORTANCIA, index=False, encoding="utf-8")
    return metricas

