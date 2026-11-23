from datetime import date

import duckdb
import pytest

from readmissao_sus.episodio_leitura import Estrato, ler_episodios, selecionar_amostra

COLUNAS = "N_AIH, IDENT, ANO_CMPT, MES_CMPT, CGC_HOSP, CNPJ_MANT, MUNIC_MOV, RACA_COR, NACIONAL, NASC, CEP"


@pytest.fixture()
def banco(tmp_path):
    """Banco mínimo com as tabelas lidas (episodio, episodio_membro, internacao, coorte_episodio)
    e um Parquet com os campos que o banco não guarda."""
    con = duckdb.connect()
    con.execute(
        "create table internacao as select * from (values "
        "('A1', '0000001', date '2024-03-01', date '2024-03-04', 'I210', '0303060190', '31'), "
        "('A2', '0000002', date '2024-03-04', date '2024-03-12', 'I500', '0406030103', '12'), "
        "('B1', '0000001', date '2024-05-01', date '2024-05-02', 'J189', '0303140151', '12')"
        ") t(n_aih, cnes, dt_inter, dt_saida, diag_princ, proc_rea, cobranca)"
    )
    con.execute(
        "create table episodio_membro as select * from (values ('A1', 'A1', 1), ('A1', 'A2', 2), ('B1', 'B1', 1)) "
        "t(episodio_id, n_aih, posicao)"
    )
    con.execute(
        "create table episodio as select * from (values "
        "('A1', 'k1', '3', 70::smallint, '4', '261160', '02', 2, 1, 0), "
        "('B1', 'k2', '1', 30::smallint, '4', '260890', '01', 1, 0, 0)"
        ") t(episodio_id, chave, sexo, idade, cod_idade, munic_res, car_int, n_internacoes, "
        "ligacoes_transferencia, ligacoes_permanencia)"
    )
    con.execute("create table coorte_episodio as select * from episodio")
    parquet = tmp_path / "RDPE2403.parquet"
    con.execute(
        f"copy (select * from (values "
        f"('A1', '1', '2024', '03', '', '11444777000161', '261160', '03', '010', '19540101', '50000000'), "
        f"('A2', '1', '2024', '03', '11222333000181', '', '260890', '01', '010', '19540101', '50000000'), "
        f"('A2', '1', '2024', '01', '99999999999999', '', '999999', '01', '010', '19540101', '50000000'), "
        f"('B1', '1', '2024', '05', '00000000000000', '', '260890', '02', '010', '19940101', '50000000')"
        f") t({COLUNAS})) to '{parquet.as_posix()}' (format parquet)"
    )
    yield con, [parquet]
    con.close()


def test_le_episodio_com_aihs_em_ordem_e_campos_do_parquet(banco):
    con, parquets = banco
    [episodio] = ler_episodios(con, parquets, ["A1"])

    assert [i.n_aih for i in episodio.internacoes] == ["A1", "A2"]
    assert (episodio.dt_inter, episodio.dt_saida, episodio.cobranca) == (date(2024, 3, 1), date(2024, 3, 12), "12")
    # Hospital da alta: CNES da última AIH, CNPJ e município da competência mais recente.
    assert episodio.estabelecimento_alta.cnes == "0000002"
    assert episodio.estabelecimento_alta.cnpj == "11222333000181"
    assert episodio.estabelecimento_alta.municipio == "260890"
    assert (episodio.raca_cor, episodio.nacional, episodio.idade) == ("03", "010", 70)


def test_episodio_sem_cnpj_falha_ou_fica_de_fora(banco):
    con, parquets = banco
    with pytest.raises(ValueError, match="CNPJ"):
        ler_episodios(con, parquets, ["B1"])
    assert [e.episodio_id for e in ler_episodios(con, parquets, ["B1", "A1"], pular_incompletos=True)] == ["A1"]


def test_episodio_inexistente_falha(banco):
    con, parquets = banco
    with pytest.raises(KeyError, match="X9"):
        ler_episodios(con, parquets, ["X9"])


def test_amostra_por_estrato_sem_repetir_e_com_filtro(banco):
    con, parquets = banco
    estratos = [Estrato("multi", "n_internacoes > 1", 1), Estrato("qualquer", "true", 1)]

    with pytest.raises(ValueError, match="qualquer"):
        selecionar_amostra(con, parquets, lambda e: True, estratos)  # B1 não tem CNPJ
    amostra = selecionar_amostra(con, parquets, lambda e: True, estratos[:1])
    assert [(s.nome, e.episodio_id) for s, e in amostra] == [("multi", "A1")]
    with pytest.raises(ValueError, match="multi"):
        selecionar_amostra(con, parquets, lambda e: False, estratos[:1])
