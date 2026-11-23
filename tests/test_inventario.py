import pandas as pd

from readmissao_sus.dbf import CampoDbf
from readmissao_sus.inventario import CAMPOS_ALVO, ano_do_arquivo, consolidar, resumir, tabela_campos_md


def _df():
    return pd.DataFrame(
        {
            "N_AIH": ["1", "2", "3", "4"],
            "SEXO": ["1", "3", None, ""],
            "MORTE": ["0", "0", "1", "0"],
            "COBRANCA": ["12", "31", "41", None],
        },
        dtype="string",
    )


def test_ano_do_arquivo():
    assert ano_do_arquivo("RDPE2301.parquet") == 2023
    assert ano_do_arquivo("RDPE2412.dbc") == 2024


def test_resumir_conta_nulos_e_vazios_e_frequencias():
    r = resumir(_df(), [CampoDbf("SEXO", "C", 1, 0)], 2023)

    assert r.linhas == 4
    assert r.nulos["SEXO"] == 2
    assert r.nulos["N_AIH"] == 0
    assert r.tipos["SEXO"] == "char(1)"
    assert "CEP" not in r.nulos
    assert r.frequencias["COBRANCA"]["(nulo)"] == 1
    assert r.frequencias["MORTE"]["0"] == 3


def test_consolidar_soma_por_ano_e_tabela_indica_ausentes():
    inv = consolidar([resumir(_df(), [], 2023), resumir(_df(), [], 2023), resumir(_df(), [], 2024)])

    assert inv.linhas_por_ano == {2023: 8, 2024: 4}
    assert inv.nulos_por_ano["SEXO"] == {2023: 4, 2024: 2}
    tabela = tabela_campos_md(inv)
    assert len(tabela.splitlines()) == 2 + len(CAMPOS_ALVO)
    assert "| CEP | não |" in tabela
    assert "| SEXO | sim | string | 50,00% | 50,00% | 50,00% |" in tabela
