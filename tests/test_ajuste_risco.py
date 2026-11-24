"""Ajuste de risco sem o hospital da alta, para a razão O/E por hospital (S14, D05)."""

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from readmissao_sus.ajuste_risco import (
    ATRIBUTOS_CATEGORICOS_AJUSTE,
    fator_recalibracao,
    pontuar_ajustado,
    treinar_ajuste,
)
from readmissao_sus.modelagem import ALVO, dividir_por_tempo
from readmissao_sus.razao_oe import COLUNA_PROBABILIDADE, contar_leituras
from sintetico_modelo import episodios_sinteticos


def test_ajuste_nao_usa_o_hospital_da_alta() -> None:
    treino, _ = dividir_por_tempo(episodios_sinteticos(600, seed=1))
    pipeline = treinar_ajuste(treino, classificador=LogisticRegression(max_iter=500))

    assert "cnes_alta" not in ATRIBUTOS_CATEGORICOS_AJUSTE
    nomes = pipeline.named_steps["preprocessador"].get_feature_names_out()
    assert not any("cnes_alta" in n for n in nomes)
    assert any("car_int" in n for n in nomes)


def test_trocar_o_hospital_nao_muda_a_probabilidade() -> None:
    treino, teste = dividir_por_tempo(episodios_sinteticos(800, seed=2))
    pipeline = treinar_ajuste(treino, classificador=LogisticRegression(max_iter=500))

    original = pontuar_ajustado(pipeline, teste).altas[COLUNA_PROBABILIDADE]
    outro_hospital = pontuar_ajustado(pipeline, teste.assign(cnes_alta="0000001")).altas[COLUNA_PROBABILIDADE]
    np.testing.assert_allclose(original, outro_hospital)


def test_recalibracao_iguala_o_total_esperado_ao_observado() -> None:
    treino, teste = dividir_por_tempo(episodios_sinteticos(800, seed=4))
    ajustadas = pontuar_ajustado(treinar_ajuste(treino, classificador=LogisticRegression(max_iter=500)), teste)

    assert ajustadas.altas[COLUNA_PROBABILIDADE].sum() == pytest.approx(teste[ALVO].sum())
    assert ajustadas.fator_recalibracao > 0
    assert 0.5 < ajustadas.roc_auc_teste <= 1


def test_fator_recalibracao_rejeita_esperado_zero() -> None:
    assert fator_recalibracao(np.array([1, 0]), np.array([0.25, 0.25])) == pytest.approx(2)
    with pytest.raises(ValueError, match="positivo"):
        fator_recalibracao(np.array([1]), np.array([0.0]))


def test_contar_leituras_pelo_ic() -> None:
    tabela = pd.DataFrame({"ic95_inf": [1.2, 0.5, 0.3], "ic95_sup": [2.0, 1.5, 0.8]})
    assert contar_leituras(tabela) == {"acima": 1, "abaixo": 1, "compativel": 1}
