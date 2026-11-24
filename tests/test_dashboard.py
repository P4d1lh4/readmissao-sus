"""Aba Hospitais do dashboard (S11), com um CSV agregado sintético."""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from dashboard import hospitais

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
TABELA = pd.DataFrame(
    {
        "cnes": ["0000001", "0000002", "0000003"],
        "altas": [500, 150, 1000],
        "observado": [80, 10, 40],
        "esperado": [50.0, 10.0, 60.0],
        "razao_oe": [1.6, 1.0, 0.667],
        "ic95_inf": [1.27, 0.48, 0.48],
        "ic95_sup": [1.99, 1.84, 0.91],
    }
)


def test_classifica_pelo_ic_e_filtra_pelo_minimo_de_altas() -> None:
    assert list(hospitais.classificar(TABELA)) == [hospitais.ACIMA, hospitais.COMPATIVEL, hospitais.ABAIXO]
    assert list(hospitais.filtrar(TABELA, 200)["cnes"]) == ["0000001", "0000003"]


def test_grafico_tem_um_ponto_por_hospital_com_ic() -> None:
    figura = hospitais.grafico_oe(TABELA)
    assert sum(len(t.x) for t in figura.data) == len(TABELA)
    assert {t.name for t in figura.data} == {hospitais.ACIMA, hospitais.COMPATIVEL, hospitais.ABAIXO}


@pytest.fixture()
def csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / "hospitais_oe.csv"
    TABELA.to_csv(caminho, index=False)
    monkeypatch.setenv("READMISSAO_HOSPITAIS_CSV", str(caminho))
    return caminho


def test_app_mostra_tabela_e_grafico_e_filtra(csv: Path) -> None:
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert [t.label for t in app.tabs] == ["Hospitais"]
    assert len(app.dataframe[0].value) == 3
    assert app.get("plotly_chart")
    assert [e.label for e in app.expander] == ["Como ler a tabela"]
    assert "**0000001**" in app.expander[0].markdown[0].value

    app.number_input[0].set_value(600).run()
    assert not app.exception
    assert list(app.dataframe[0].value["CNES"]) == ["0000003"]


def test_app_sem_csv_mostra_como_gerar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("READMISSAO_HOSPITAIS_CSV", str(tmp_path / "nao.csv"))
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "razao_hospitais.py" in app.info[0].value
