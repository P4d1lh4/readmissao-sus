import struct

import pandas as pd
import pytest

from readmissao_sus.dbf import CampoDbf, ler_campos_parquet, ler_dbf, normalizar_registros, salvar_parquet


def test_normalizar_registros_tira_espacos_e_converte_vazio_em_nulo():
    bruto = pd.DataFrame(
        {
            "N_AIH": ["2623100000017", "2623100000028 ", "             "],
            "SEXO": ["1", " 3", ""],
            "IDADE": [" 45", "0", "  "],
        }
    )
    original = bruto.copy()

    df = normalizar_registros(bruto)

    assert df["N_AIH"].tolist()[:2] == ["2623100000017", "2623100000028"]
    assert df["SEXO"].tolist()[:2] == ["1", "3"]
    assert df["IDADE"].tolist()[:2] == ["45", "0"]
    assert df.iloc[2].isna().all()
    assert all(isinstance(t, pd.StringDtype) for t in df.dtypes)
    pd.testing.assert_frame_equal(bruto, original)


def test_normalizar_registros_preserva_zeros_a_esquerda():
    df = normalizar_registros(pd.DataFrame({"CEP": ["05001000"], "MUNIC_RES": ["261160"]}))
    assert df.loc[0, "CEP"] == "05001000"


def _escrever_dbf(caminho, campos, linhas, apagados=()):
    tam_registro = 1 + sum(t for _, _, t in campos)
    tam_cabecalho = 32 + 32 * len(campos) + 1
    cab = struct.pack("<B3sIHH20x", 3, b"\x7b\x01\x01", len(linhas), tam_cabecalho, tam_registro)
    for nome, tipo, tam in campos:
        cab += nome.encode().ljust(11, b"\x00") + tipo.encode() + b"\x00" * 4 + bytes([tam, 0]) + b"\x00" * 14
    cab += b"\x0d"
    corpo = b""
    for i, linha in enumerate(linhas):
        corpo += b"*" if i in apagados else b" "
        for (_, _, tam), valor in zip(campos, linha):
            corpo += valor.encode("latin-1").ljust(tam)
    caminho.write_bytes(cab + corpo + b"\x1a")


def test_ler_dbf_le_campos_descarta_apagados_e_normaliza(tmp_path):
    dbf = tmp_path / "teste.dbf"
    campos = [("N_AIH", "C", 13), ("MORTE", "N", 1), ("COBRANCA", "C", 2)]
    _escrever_dbf(
        dbf,
        campos,
        [("2623100000017", "0", "12"), ("2623100000028", "1", "41"), ("2623100000039", "0", "  ")],
        apagados={1},
    )

    df, lidos = ler_dbf(dbf)

    assert [c.nome for c in lidos] == ["N_AIH", "MORTE", "COBRANCA"]
    assert lidos[1] == CampoDbf("MORTE", "N", 1, 0)
    assert df["N_AIH"].tolist() == ["2623100000017", "2623100000039"]
    assert df["COBRANCA"].isna().tolist() == [False, True]


def test_salvar_parquet_guarda_tipos_do_dbf_nos_metadados(tmp_path):
    destino = tmp_path / "x.parquet"
    campos = [CampoDbf("IDADE", "N", 2, 0)]
    salvar_parquet(normalizar_registros(pd.DataFrame({"IDADE": ["45"]})), campos, destino)

    assert ler_campos_parquet(destino) == campos
    assert pd.read_parquet(destino)["IDADE"].tolist() == ["45"]
    assert not (tmp_path / "x.parquet.part").exists()


@pytest.mark.parametrize("campo,esperado", [(CampoDbf("X", "C", 13, 0), "char(13)"), (CampoDbf("V", "N", 14, 2), "numeric(14,2)")])
def test_tipo_legivel(campo, esperado):
    assert campo.tipo_legivel == esperado
