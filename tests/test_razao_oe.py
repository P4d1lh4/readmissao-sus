"""Razão O/E por hospital, IC de Poisson exato e o CSV agregado (S11)."""

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from readmissao_sus.modelagem import ALVO, CORTE_CENSURA
from readmissao_sus.razao_oe import COLUNAS_SAIDA, ic_poisson_exato, razao_por_hospital
from sintetico_modelo import episodios_sinteticos, salvar_modelo_sintetico

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import razao_hospitais  # noqa: E402

COLUNAS_POR_EPISODIO = {"episodio_id", "chave", "probabilidade", "dt_saida", "dt_inter", ALVO}


def _altas(cnes: str, n: int, readmissoes: int, probabilidade: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"cnes_alta": cnes, ALVO: [True] * readmissoes + [False] * (n - readmissoes), "probabilidade": probabilidade}
    )


def test_ic_poisson_exato_bate_com_valores_tabelados() -> None:
    inferior, superior = ic_poisson_exato(np.array([0, 10]))
    # Garwood (1936): O = 0 -> (0; 3,689); O = 10 -> (4,795; 18,390).
    np.testing.assert_allclose(inferior, [0.0, 4.7954], atol=1e-3)
    np.testing.assert_allclose(superior, [3.6889, 18.3904], atol=1e-3)


def test_razao_por_hospital_soma_probabilidades_e_filtra_minimo() -> None:
    altas = pd.concat(
        [
            _altas("0000001", 100, 10, 0.08),  # esperado 8, O/E 1,25
            _altas("0000002", 200, 0, 0.05),  # esperado 10, O/E 0
            _altas("0000003", 99, 50, 0.1),  # abaixo do mínimo
            _altas(None, 300, 30, 0.1),  # sem CNES
        ]
    )
    tabela = razao_por_hospital(altas, minimo_altas=100)

    assert tuple(tabela.columns) == COLUNAS_SAIDA
    assert list(tabela["cnes"]) == ["0000001", "0000002"]
    primeiro = tabela.iloc[0]
    assert (primeiro["altas"], primeiro["observado"]) == (100, 10)
    assert primeiro["esperado"] == pytest.approx(8)
    assert primeiro["razao_oe"] == pytest.approx(1.25)
    assert (primeiro["ic95_inf"], primeiro["ic95_sup"]) == pytest.approx((4.7954 / 8, 18.3904 / 8), abs=1e-3)
    segundo = tabela.iloc[1]
    assert (segundo["razao_oe"], segundo["ic95_inf"]) == (0, 0)
    assert segundo["ic95_sup"] == pytest.approx(3.6889 / 10, abs=1e-3)


def test_script_grava_csv_so_com_agregados_do_teste(tmp_path: Path) -> None:
    episodios = episodios_sinteticos(1500, seed=3)
    banco = tmp_path / "sih.duckdb"
    with duckdb.connect(str(banco)) as con:
        con.execute("create table atributo_episodio as select * from episodios")
    saida = tmp_path / "reports" / "hospitais_oe.csv"
    argumentos = ["--banco", str(banco), "--saida", str(saida), "--minimo-altas", "10"]

    assert razao_hospitais.main(argumentos + ["--dir-modelo", str(salvar_modelo_sintetico(tmp_path / "m"))]) == 0

    resumo = json.loads((saida.parent / razao_hospitais.NOME_RESUMO).read_text(encoding="utf-8"))
    assert "cnes_alta" not in resumo["atributos"]
    assert set(resumo["leituras_ajuste"]) == {"acima", "abaixo", "compativel"}
    assert resumo["leituras_modelo_principal"] is not None
    csv = pd.read_csv(saida, dtype={"cnes": str})
    assert csv["esperado"].sum() == pytest.approx(csv["observado"].sum())   # recalibrado no total
    assert tuple(csv.columns) == COLUNAS_SAIDA
    assert not COLUNAS_POR_EPISODIO & set(csv.columns)
    alta = pd.to_datetime(episodios["dt_saida"])
    teste = episodios[(alta.dt.year == 2024) & (alta <= pd.Timestamp(CORTE_CENSURA))]
    assert csv["altas"].sum() == len(teste)
    assert csv["observado"].sum() == teste[ALVO].sum()
    assert csv["cnes"].is_unique and len(csv) == teste["cnes_alta"].nunique()


def test_script_sem_modelo_principal_so_nao_compara(tmp_path: Path) -> None:
    episodios = episodios_sinteticos(900, seed=5)
    banco = tmp_path / "sih.duckdb"
    with duckdb.connect(str(banco)) as con:
        con.execute("create table atributo_episodio as select * from episodios")
    saida = tmp_path / "hospitais_oe.csv"

    assert razao_hospitais.main(["--banco", str(banco), "--saida", str(saida), "--minimo-altas", "10",
                                 "--dir-modelo", str(tmp_path / "sem_modelo")]) == 0
    resumo = json.loads((tmp_path / razao_hospitais.NOME_RESUMO).read_text(encoding="utf-8"))
    assert resumo["leituras_modelo_principal"] is None
