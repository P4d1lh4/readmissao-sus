import importlib

import readmissao_sus

DEPENDENCIAS = (
    "pandas", "pyarrow", "duckdb", "pyreaddbc", "sklearn", "xgboost", "joblib",
    "scipy", "fastapi", "uvicorn", "httpx", "streamlit", "plotly",
)


def test_pacote_importa_e_tem_versao():
    assert readmissao_sus.__version__ == "0.1.0"


def test_dependencias_importam():
    for nome in DEPENDENCIAS:
        assert importlib.import_module(nome) is not None, nome
