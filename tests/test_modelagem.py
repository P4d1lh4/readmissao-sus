"""Testes do modelo (S10) com episódios sintéticos e treino pequeno em diretório temporário."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from readmissao_sus.artefatos import carregar_artefatos
from readmissao_sus.explicacao import atributo_de_origem, explicar_registro
from readmissao_sus.modelagem import (
    ATRIBUTOS,
    COLUNAS_FORA,
    CORTE_CENSURA,
    alvo,
    amostrar_por_chave,
    dividir_por_tempo,
    escolher_limiar,
    folds_por_chave,
    montar_pipeline,
    preparar_atributos,
)
from readmissao_sus.treino import treinar_e_salvar
from sintetico_modelo import episodios_sinteticos

CLASSIFICADORES_PEQUENOS = {
    "LogisticRegression": LogisticRegression(max_iter=500),
    "RandomForest": RandomForestClassifier(n_estimators=20, max_depth=4, random_state=0),
    "XGBoost": XGBClassifier(n_estimators=30, max_depth=3, tree_method="hist", random_state=0),
}


@pytest.fixture(scope="module")
def treinado(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, dict]:
    raiz = tmp_path_factory.mktemp("treino")
    metricas = treinar_e_salvar(
        episodios_sinteticos(1500, seed=1),
        dir_modelo=raiz / "models",
        dir_relatorios=raiz / "reports",
        random_state=0,
        fracao_cv=0.8,
        max_linhas_importancia=300,
        classificadores=CLASSIFICADORES_PEQUENOS,
    )
    return raiz / "models", raiz / "reports", metricas


def test_divisao_temporal_sem_alta_de_2024_no_treino_nem_alta_censurada_no_teste() -> None:
    episodios = episodios_sinteticos(2000, seed=2)
    treino, teste = dividir_por_tempo(episodios)

    alta_treino = pd.to_datetime(treino["dt_saida"])
    alta_teste = pd.to_datetime(teste["dt_saida"])
    assert (alta_treino.dt.year == 2023).all()
    assert (alta_teste.dt.year == 2024).all()
    assert alta_teste.max() <= pd.Timestamp(CORTE_CENSURA)
    assert set(treino["episodio_id"]).isdisjoint(teste["episodio_id"])
    depois_do_corte = pd.to_datetime(episodios["dt_saida"]) > pd.Timestamp(CORTE_CENSURA)
    assert len(treino) + len(teste) == int((~depois_do_corte).sum())


def test_cv_agrupada_nao_poe_a_mesma_chave_em_dois_folds() -> None:
    treino, _ = dividir_por_tempo(episodios_sinteticos(2000, seed=3))
    folds = folds_por_chave(treino, n_splits=5, random_state=0)
    chaves = treino["chave"].to_numpy()

    assert len(folds) == 5
    vistos: set[str] = set()
    for idx_ajuste, idx_validacao in folds:
        validacao = set(chaves[idx_validacao])
        assert validacao.isdisjoint(chaves[idx_ajuste])
        assert validacao.isdisjoint(vistos)
        vistos |= validacao
    assert sum(len(v) for _, v in folds) == len(treino)


def test_amostra_da_cv_leva_chaves_inteiras() -> None:
    treino, _ = dividir_por_tempo(episodios_sinteticos(2000, seed=4))
    amostra = amostrar_por_chave(treino, 0.5, random_state=0)

    por_chave = treino.groupby("chave").size()
    assert amostra.groupby("chave").size().equals(por_chave[amostra["chave"].unique()].sort_index())
    assert 0.3 < amostra["chave"].nunique() / treino["chave"].nunique() < 0.7


def test_limiar_maximiza_f1() -> None:
    y = np.array([0, 0, 0, 1, 0, 1, 1])
    proba = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])

    assert escolher_limiar(y, proba) == 0.4


def test_atributos_nao_incluem_identificadores_alvo_nem_futuro() -> None:
    proibidas = {"episodio_id", "chave", "dt_inter", "dt_saida", "readmissao_30d", "ano_alta",
                 "historico_completo", "chave_colidente", "episodio_sobreposto"}

    assert proibidas <= set(COLUNAS_FORA)
    assert proibidas.isdisjoint(ATRIBUTOS)


def test_limiar_salvo_no_metadata_e_igual_ao_das_metricas(treinado) -> None:
    dir_modelo, dir_relatorios, metricas = treinado
    metadata = json.loads((dir_modelo / "metadata.json").read_text(encoding="utf-8"))
    no_disco = json.loads((dir_relatorios / "metrics.json").read_text(encoding="utf-8"))

    assert 0 < metadata["limiar"] < 1
    assert metadata["limiar"] == no_disco["teste"]["limiar"] == metricas["teste"]["limiar"]
    assert metadata["versao_sklearn"] == sklearn.__version__
    assert metadata["atributos"] == list(ATRIBUTOS)


def test_metricas_tem_cv_teste_e_grupos(treinado) -> None:
    _, dir_relatorios, _ = treinado
    metricas = json.loads((dir_relatorios / "metrics.json").read_text(encoding="utf-8"))

    assert set(metricas["cv"]) == set(CLASSIFICADORES_PEQUENOS)
    for resumo in metricas["cv"].values():
        assert {"roc_auc_media", "roc_auc_desvio", "pr_auc_media", "pr_auc_desvio"} <= set(resumo)
    teste = metricas["teste"]
    for campo in ("roc_auc", "pr_auc", "brier", "prevalencia", "limiar", "precisao", "recall", "f1"):
        assert teste[campo] is not None, campo
    assert np.array(teste["matriz_confusao"]).sum() == metricas["teste_episodios"]
    for grupo in ("cep_generico", "historico_completo"):
        partes = metricas["teste_por_grupo"][grupo]
        assert sum(p["episodios"] for p in partes.values()) == metricas["teste_episodios"]
    assert metricas["variante_historico"]["teste"]["episodios"] == metricas["teste_episodios"]
    investigacao = metricas["investigacao_vazamento"]
    assert set(investigacao["ablacoes_teste"]) == {"sem_historico", "sem_cnes_alta"}
    assert investigacao["teste_sem_readmissao_0_1_dia"]["positivos_removidos"] > 0


def test_relatorios_so_tem_agregados(treinado) -> None:
    _, dir_relatorios, metricas = treinado
    importancias = pd.read_csv(dir_relatorios / "importancia_atributos.csv")

    assert sorted(p.name for p in dir_relatorios.iterdir()) == ["importancia_atributos.csv", "metrics.json"]
    assert sorted(importancias["atributo"]) == sorted(ATRIBUTOS)
    assert len(importancias) < metricas["teste_episodios"]


def test_modelo_salvo_preve_com_campos_ausentes_e_hospital_novo(treinado) -> None:
    artefatos = carregar_artefatos(treinado[0])
    completo = episodios_sinteticos(1, seed=9).iloc[0].to_dict()

    for registro in (completo, {"idade": 70, "cnes_alta": "1234567"}, {}):
        previsao = artefatos.prever(registro)
        assert 0.0 < previsao.probabilidade < 1.0
        assert previsao.alerta == int(previsao.probabilidade >= previsao.limiar)


def test_explicacao_soma_por_atributo_de_origem() -> None:
    episodios = episodios_sinteticos(800, seed=5)
    registro = episodios.iloc[0].to_dict()
    xgb = montar_pipeline(CLASSIFICADORES_PEQUENOS["XGBoost"]).fit(
        preparar_atributos(episodios), alvo(episodios)
    )
    lr = montar_pipeline(CLASSIFICADORES_PEQUENOS["LogisticRegression"]).fit(
        preparar_atributos(episodios), alvo(episodios)
    )
    contribuicoes = explicar_registro(xgb, registro)

    assert atributo_de_origem("cat__cnes_alta_0000434") == "cnes_alta"
    assert atributo_de_origem("num__missingindicator_dias_desde_ultima_alta") == "dias_desde_ultima_alta"
    assert set(contribuicoes.index) <= set(ATRIBUTOS)
    assert "episodios_365d" in contribuicoes.index
    assert explicar_registro(lr, registro) is None
