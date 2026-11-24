import hashlib
from datetime import date

import duckdb
import pandas as pd
import pytest

from readmissao_sus.banco import (
    COLUNAS_FONTE, VARIAVEL_SAL, construir_banco, criar_fonte, montar_coorte, obter_sal,
    preparar_internacoes,
)
from readmissao_sus.relatorio_coorte import MARCA_FIM, MARCA_INICIO, gerar_bloco, gravar_bloco

SAL = "sal-de-teste"
INICIO = date(2023, 1, 1)
CORTE = date(2024, 10, 1)
PESSOA = ("19800404", "3", "55290456", "260790")


def _aih(n_aih, inter="20230301", saida="20230305", ident="1", cobranca="12", morte="0",
         competencia=None, nasc=PESSOA[0], cep=PESSOA[2]):
    comp = competencia or (saida[:6] if saida and saida[:6].isdigit() else "202303")
    return {
        "N_AIH": n_aih, "IDENT": ident, "ANO_CMPT": comp[:4], "MES_CMPT": comp[4:],
        "NASC": nasc, "SEXO": PESSOA[1], "CEP": cep, "MUNIC_RES": PESSOA[3], "IDADE": "42",
        "COD_IDADE": "4", "DT_INTER": inter, "DT_SAIDA": saida, "DIAG_PRINC": "I500",
        "PROC_REA": "0303060212", "CNES": "1234567", "CAR_INT": "02", "COBRANCA": cobranca,
        "MORTE": morte, "UTI_MES_TO": "0",
    }


def _cenario():
    linhas = [
        _aih("OK1"),                                                      # alta comum: fica
        # Filtro 1: IDENT = 5 estende a saída de L1 e traz o motivo final; órfã e IDENT 3 saem.
        _aih("L1", "20230401", "20230430", cobranca="21"),
        _aih("L1", "20230401", "20230531", ident="5", cobranca="12"),
        _aih("ORFA", "20221001", "20230228", ident="5"),
        _aih("OUTRO", ident="3"),
        # Filtro 2: N_AIH repetido; fica a competência mais recente (saída de 06/03).
        _aih("DUP", "20230301", "20230305", competencia="202303"),
        _aih("DUP", "20230301", "20230306", competencia="202304"),
        # Filtro 3: datas inválidas ou saída antes da entrada.
        _aih("Z1", "00000000", "20230305"),
        _aih("Z2", "20230301", "20230230"),
        _aih("Z3", "20230301", "2023031"),
        _aih("Z4", "20230310", "20230305"),
        _aih("Z5", None, "20230305"),
        # Filtro 4: óbito por MORTE, por COBRANCA, e na AIH 5 final; 63 e 64 ficam.
        _aih("M1", morte="1", cobranca="12"),
        _aih("M2", cobranca="41"),
        _aih("M3", "20230501", "20230510", cobranca="21"),
        _aih("M3", "20230501", "20230620", ident="5", cobranca="43", morte="1"),
        _aih("V1", "20230701", "20230710", cobranca="41", morte="1"),     # óbito na AIH 1, mas
        _aih("V1", "20230701", "20230601", ident="5", cobranca="12"),     # AIH 5 anterior: óbito vale
        _aih("P63", cobranca="63"),
        _aih("P64", cobranca="64"),
        # Marcas: censura, início, CEP genérico, NASC placeholder.
        _aih("CENS", "20241001", "20241002"),
        _aih("LIM", "20240925", "20241001"),
        _aih("ANTES", "20221220", "20221231", competencia="202301"),
        _aih("GEN", cep="50000000"),
        _aih("ZERO", nasc="18991230"),
        _aih("NINV", nasc="19801345"),
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS_FONTE), dtype="string")


@pytest.fixture
def con():
    c = duckdb.connect()
    c.register("bruto_df", _cenario())
    preparar_internacoes(c, "bruto_df", SAL)
    montar_coorte(c, INICIO, CORTE)
    return c


def _coorte(con):
    return {r[0]: r[1:] for r in con.execute(
        "select n_aih, dt_saida, cobranca, censurada, alta_antes_do_inicio, elegivel_indice, "
        "cep_generico, nasc_antes_1900, nasc_invalida, longa_permanencia from coorte"
    ).fetchall()}


def test_filtros_contam_as_linhas_removidas_em_ordem(con):
    filtros = con.execute("select ordem, antes, removidas, depois from coorte_filtros order by ordem").fetchall()

    assert filtros == [
        (1, 26, 5, 21),   # 4 linhas IDENT=5 (L1, ORFA, M3, V1) e 1 IDENT=3
        (2, 21, 1, 20),   # DUP
        (3, 20, 5, 15),   # Z1 a Z5
        (4, 15, 4, 11),   # M1, M2, M3, V1
    ]
    detalhes = dict(con.execute("select item, linhas from coorte_detalhes where secao = 'ident'").fetchall())
    assert detalhes["Linhas IDENT = 5 (continuação de longa permanência)"] == 4
    assert detalhes["Linhas com outro IDENT"] == 1
    assert detalhes["AIHs IDENT = 5 sem a AIH 1 correspondente (descartadas)"] == 1


def test_so_aih_normal_forma_internacao_e_ident5_define_saida_final(con):
    coorte = _coorte(con)

    assert "ORFA" not in coorte and "OUTRO" not in coorte
    dt_saida, cobranca, *_, longa = coorte["L1"]
    assert (dt_saida, cobranca, longa) == (date(2023, 5, 31), "12", True)
    assert con.execute("select count(*) from coorte where n_aih = 'L1'").fetchone()[0] == 1


def test_n_aih_repetido_fica_a_competencia_mais_recente(con):
    assert _coorte(con)["DUP"][0] == date(2023, 3, 6)


def test_datas_invalidas_saem_e_sao_contadas(con):
    coorte = _coorte(con)
    datas = dict(con.execute("select item, linhas from coorte_detalhes where secao = 'datas'").fetchall())

    assert not {"Z1", "Z2", "Z3", "Z4", "Z5"} & coorte.keys()
    assert datas["DT_INTER ausente ou inválida"] == 2   # Z1 (00000000) e Z5 (nulo)
    assert datas["DT_SAIDA ausente ou inválida"] == 2   # Z2 (30/02) e Z3 (7 dígitos)
    assert datas["Saída antes da internação"] == 1      # Z4
    assert datas["NASC inválida (não é data)"] == 1     # NINV fica, só marcada
    assert datas["NASC antes de 1900 (inclui 30/12/1899, data zero de sistemas)"] == 1
    assert coorte["NINV"][7] is True and coorte["ZERO"][6] is True


def test_obito_sai_pela_saida_final_e_63_64_ficam(con):
    coorte = _coorte(con)
    obito = dict(con.execute("select item, linhas from coorte_detalhes where secao = 'obito'").fetchall())

    assert not {"M1", "M2", "M3", "V1"} & coorte.keys()
    assert {"P63", "P64"} <= coorte.keys()
    assert obito["Óbitos removidos"] == 4
    assert obito["… com MORTE = 1"] == 3      # M1, M3 (pela AIH 5) e V1
    assert obito["… com COBRANCA de óbito"] == 3  # M2, M3, V1
    assert con.execute("select count(*) from internacao where obito").fetchone()[0] == 4


def test_censura_inicio_e_cep_generico_sao_marcas_e_nao_filtros(con):
    coorte = _coorte(con)

    assert coorte["CENS"][2:5] == (True, False, False)
    assert coorte["LIM"][2:5] == (False, False, True)   # saída no dia do corte ainda entra
    assert coorte["ANTES"][2:5] == (False, True, False)
    assert coorte["GEN"][5] is True and coorte["OK1"][5] is False
    marcas = dict(con.execute("select item, linhas from coorte_detalhes where secao = 'marcas'").fetchall())
    assert marcas["Elegíveis a alta-índice (elegivel_indice)"] == 9
    assert marcas["Censuradas: saída depois da data de corte (censurada)"] == 1


def test_chave_usa_sal_e_nasc_cep_nao_ficam_em_claro(con):
    sem_sal = hashlib.sha256("|".join(PESSOA).encode()).hexdigest()
    com_sal = hashlib.sha256((SAL + "|".join(PESSOA)).encode()).hexdigest()
    chaves = {c for (c,) in con.execute("select distinct chave from coorte").fetchall()}

    assert com_sal in chaves and sem_sal not in chaves
    for tabela in ("stg_aih", "internacao", "coorte"):
        colunas = {c[0].lower() for c in con.execute(f"describe {tabela}").fetchall()}
        assert not colunas & {"nasc", "cep"}


def test_fonte_sem_coluna_obrigatoria_falha():
    c = duckdb.connect()
    c.register("bruto_df", _cenario().drop(columns=["DIAG_PRINC"]))

    with pytest.raises(ValueError, match="DIAG_PRINC"):
        criar_fonte(c, "bruto_df")


def test_construir_banco_recria_do_zero_e_gera_bloco(tmp_path):
    parquet = tmp_path / "RDPE2303.parquet"
    _cenario().to_parquet(parquet)
    destino = tmp_path / "sih.duckdb"
    with duckdb.connect(str(destino)) as velho:
        velho.execute("create table sobra as select 1 as x")

    resultado = construir_banco(destino, [parquet], SAL)

    with duckdb.connect(str(destino), read_only=True) as c:
        tabelas = {t for (t,) in c.execute("show tables").fetchall()}
        assert "sobra" not in tabelas
        assert {"stg_aih", "internacao", "coorte", "coorte_filtros", "coorte_detalhes"} <= tabelas
        assert {"episodio", "episodio_membro", "coorte_episodio", "episodio_parametros"} <= tabelas
        assert c.execute("select count(*) from coorte").fetchone()[0] == resultado.filtros[-1][4]
        assert c.execute("select contiguas_sem_motivo from episodio_parametros").fetchone()[0] == "mesmo_hospital"   # padrão da D03
    assert not (tmp_path / "sih.duckdb.novo").exists()
    doc = tmp_path / "coorte.md"
    doc.write_text(f"# Coorte\n\ntexto\n\n{MARCA_INICIO}\nvelho\n{MARCA_FIM}\n", encoding="utf-8")
    gravar_bloco(doc, gerar_bloco(resultado, "01/01/2025"))
    texto = doc.read_text(encoding="utf-8")
    assert "velho" not in texto and "texto" in texto
    assert "| 4 | Sem óbito" in texto
    assert PESSOA[0] not in texto and PESSOA[2] not in texto


def test_obter_sal_prefere_ambiente_e_cria_arquivo(tmp_path, monkeypatch):
    arquivo = tmp_path / "sal_chave.txt"
    monkeypatch.delenv(VARIAVEL_SAL, raising=False)

    gerado = obter_sal(arquivo)
    assert len(gerado) == 64 and arquivo.read_text(encoding="utf-8").strip() == gerado
    assert obter_sal(arquivo) == gerado
    monkeypatch.setenv(VARIAVEL_SAL, "do-ambiente")
    assert obter_sal(arquivo) == "do-ambiente"
