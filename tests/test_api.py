"""API do Sumário de Alta com risco (S11), com banco, Parquet e modelo sintéticos."""

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from sintetico_modelo import episodios_sinteticos, salvar_modelo_sintetico

LIMIAR = 0.2
COLUNAS_PARQUET = "N_AIH, IDENT, ANO_CMPT, MES_CMPT, CGC_HOSP, CNPJ_MANT, MUNIC_MOV, RACA_COR, NACIONAL"


def _montar_banco(banco: Path, dir_parquet: Path) -> None:
    """A1 elegível e completo; B1 elegível sem CNPJ; C1 existe mas não é elegível."""
    atributos = episodios_sinteticos(2, seed=4).assign(episodio_id=["A1", "B1"])
    with duckdb.connect(str(banco)) as con:
        con.execute("create table atributo_episodio as select * from atributos")
        con.execute(
            "create table internacao as select * from (values "
            "('A1', '0000001', date '2024-03-01', date '2024-03-04', 'I210', '0303060190', '31'), "
            "('A2', '0000002', date '2024-03-04', date '2024-03-12', 'I500', '0406030103', '12'), "
            "('B1', '0000001', date '2024-05-01', date '2024-05-02', 'J189', '0303140151', '12'), "
            "('C1', '0000001', date '2024-06-01', date '2024-06-02', 'J189', '0303140151', '12')"
            ") t(n_aih, cnes, dt_inter, dt_saida, diag_princ, proc_rea, cobranca)"
        )
        con.execute(
            "create table episodio_membro as select * from (values "
            "('A1', 'A1', 1), ('A1', 'A2', 2), ('B1', 'B1', 1), ('C1', 'C1', 1)) t(episodio_id, n_aih, posicao)"
        )
        con.execute(
            "create table episodio as select * from (values "
            "('A1', 'k1', '3', 70::smallint, '4', '261160', '02'), "
            "('B1', 'k2', '1', 30::smallint, '4', '260890', '01'), "
            "('C1', 'k3', '1', 40::smallint, '4', '260890', '01')"
            ") t(episodio_id, chave, sexo, idade, cod_idade, munic_res, car_int)"
        )
        dir_parquet.mkdir()
        parquet = (dir_parquet / "RDPE2403.parquet").as_posix()
        con.execute(
            "copy (select * from (values "
            "('A1', '1', '2024', '03', '', '11444777000161', '261160', '03', '010'), "
            "('A2', '1', '2024', '03', '11222333000181', '', '260890', '01', '010'), "
            "('B1', '1', '2024', '05', '00000000000000', '', '260890', '02', '010'), "
            "('C1', '1', '2024', '06', '11222333000181', '', '260890', '02', '010')"
            f") t({COLUNAS_PARQUET})) to '{parquet}' (format parquet)"
        )


@pytest.fixture(scope="module")
def cliente(tmp_path_factory: pytest.TempPathFactory):
    raiz = tmp_path_factory.mktemp("api")
    _montar_banco(raiz / "sih.duckdb", raiz / "parquet")
    salvar_modelo_sintetico(raiz / "models", limiar=LIMIAR)
    with TestClient(create_app(raiz / "sih.duckdb", raiz / "parquet", raiz / "models")) as cliente:
        yield cliente


def test_saude_com_modelo_carregado(cliente: TestClient) -> None:
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "modelo": "LogisticRegression", "limiar": LIMIAR}


def test_sumario_de_episodio_elegivel_tem_bundle_e_probabilidade(cliente: TestClient) -> None:
    resposta = cliente.get("/episodios/A1/sumario-alta")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"episodio_id", "modelo", "probabilidade", "limiar", "acima_do_limiar", "bundle"}
    assert corpo["episodio_id"] == "A1"
    assert 0 <= corpo["probabilidade"] <= 1
    assert corpo["limiar"] == LIMIAR
    assert corpo["acima_do_limiar"] is (corpo["probabilidade"] >= LIMIAR)
    bundle = corpo["bundle"]
    assert (bundle["resourceType"], bundle["type"]) == ("Bundle", "document")
    tipos = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert tipos[0] == "Composition" and tipos.count("Procedure") == 2


@pytest.mark.parametrize("episodio_id", ["X9", "C1"])
def test_episodio_inexistente_ou_nao_elegivel_da_404(cliente: TestClient, episodio_id: str) -> None:
    resposta = cliente.get(f"/episodios/{episodio_id}/sumario-alta")
    assert resposta.status_code == 404


def test_episodio_elegivel_sem_cnpj_da_422(cliente: TestClient) -> None:
    assert cliente.get("/episodios/B1/sumario-alta").status_code == 422


def test_sem_banco_nem_modelo_responde_503(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "nao.duckdb", tmp_path, tmp_path)) as cliente:
        assert cliente.get("/saude").json()["status"] == "indisponivel"
        assert cliente.get("/episodios/A1/sumario-alta").status_code == 503
