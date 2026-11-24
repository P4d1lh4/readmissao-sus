from datetime import date

import duckdb
import pandas as pd
import pytest

from readmissao_sus.atributos import faixa_sql, ler_resumo, montar_atributos
from readmissao_sus.banco import COLUNAS_FONTE, montar_coorte, preparar_internacoes
from readmissao_sus.episodios import REGRA_NENHUMA, REGRA_PADRAO, REGRA_D03, montar_episodios

INICIO = date(2023, 1, 1)
CORTE = date(2024, 10, 1)


def _aih(pessoa, n_aih, inter, saida, cobranca="12", cnes="1111111", morte="0", **extra):
    """Uma AIH IDENT = 1; `pessoa` vira a data de nascimento, e com ela a chave de linkage."""
    linha = {
        "N_AIH": n_aih, "IDENT": "1", "ANO_CMPT": saida[:4], "MES_CMPT": saida[4:6],
        "NASC": pessoa, "SEXO": "3", "CEP": "55290456", "MUNIC_RES": "260790", "IDADE": "50",
        "COD_IDADE": "4", "DT_INTER": inter, "DT_SAIDA": saida, "DIAG_PRINC": "I500",
        "PROC_REA": "0303060212", "CNES": cnes, "CAR_INT": "02", "COBRANCA": cobranca,
        "MORTE": morte, "UTI_MES_TO": "0",
    }
    return {**linha, **extra}


def _cenario():
    linhas = [
        # Anterior, atual e posterior: o atual só vê o anterior; o posterior vê os dois.
        _aih("19600101", "H1", "20240101", "20240105"),
        _aih("19600101", "E1", "20240301", "20240310", UTI_MES_TO="3"),
        _aih("19600101", "L1", "20240501", "20240503"),
        # Sobreposição (colisão): E2 e O2 não contam um para o outro; ambos veem H2.
        _aih("19600102", "H2", "20240101", "20240103"),
        _aih("19600102", "E2", "20240301", "20240310"),
        _aih("19600102", "O2", "20240305", "20240320", cnes="2222222"),
        # Alta seguida de nova AIH no mesmo dia (D03 'nenhuma': episódios separados).
        _aih("19600103", "A3", "20240201", "20240210"),
        _aih("19600103", "B3", "20240210", "20240215"),
        # Janela de 365 dias antes de 01/03/2024: começa em 02/03/2023.
        _aih("19600104", "V4", "20230110", "20230201"),
        _aih("19600104", "S4", "20230220", "20230305"),
        _aih("19600104", "E4", "20240301", "20240304"),
        # Bordas da janela: saída no primeiro dia dela conta; no dia anterior, não.
        _aih("19600105", "D5", "20230225", "20230302"),
        _aih("19600105", "E5", "20240301", "20240302"),
        _aih("19600106", "D6", "20230225", "20230301"),
        _aih("19600106", "E6", "20240301", "20240302"),
        # historico_completo: entrada em 01/01/2024 tem a janela inteira; em 31/12/2023, não.
        _aih("19600107", "C7", "20240101", "20240103", SEXO="1"),
        _aih("19600108", "C8", "20231231", "20240103"),
        # Histórico com episódio não elegível: saída antes do início e episódio com óbito.
        _aih("19600109", "P9", "20221201", "20221220"),
        _aih("19600109", "E9", "20230110", "20230112"),
        _aih("19600110", "M10", "20230301", "20230305", cobranca="41", morte="1"),
        _aih("19600110", "E10", "20230401", "20230405"),
        # Censurado depois do atual não entra; o atual é elegível.
        _aih("19600111", "E11", "20240901", "20240905"),
        _aih("19600111", "X11", "20241010", "20241015"),
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS_FONTE), dtype="string")


def _montar(regra=REGRA_NENHUMA):
    con = duckdb.connect()
    con.register("bruto_df", _cenario())
    preparar_internacoes(con, "bruto_df", "sal")
    montar_coorte(con, INICIO, CORTE)
    montar_episodios(con, regra, INICIO, CORTE)
    montar_atributos(con, INICIO)
    return con


@pytest.fixture(scope="module")
def con():
    return _montar()


def _hist(con, episodio_id):
    return con.execute(
        "select episodios_365d, dias_internado_365d, dias_desde_ultima_alta "
        "from atributo_episodio where episodio_id = ?",
        [episodio_id],
    ).fetchone()


def _coluna(con, episodio_id, coluna):
    linha = con.execute(
        f"select {coluna} from atributo_episodio where episodio_id = ?", [episodio_id]
    ).fetchone()
    return None if linha is None else linha[0]


def test_historico_conta_so_episodios_com_saida_antes_da_entrada(con):
    assert _hist(con, "H1") == (0, 0, None)
    assert _hist(con, "E1") == (1, 4, 56)
    assert _hist(con, "L1") == (2, 13, 52)


def test_historico_exclui_o_proprio_episodio(con):
    assert _hist(con, "C7") == (0, 0, None)


def test_sobrepostos_nao_contam_um_para_o_outro_e_ficam_marcados(con):
    assert _hist(con, "E2") == (1, 2, 58)
    assert _hist(con, "O2") == (1, 2, 62)
    assert _coluna(con, "E2", "episodio_sobreposto") and _coluna(con, "O2", "chave_colidente")
    assert not _coluna(con, "H2", "episodio_sobreposto") and _coluna(con, "H2", "chave_colidente")
    assert not _coluna(con, "E1", "chave_colidente")


def test_saida_no_dia_da_entrada_conta_como_anterior(con):
    assert _hist(con, "B3") == (1, 9, 0)
    assert _hist(con, "A3") == (0, 0, None)


def test_janela_de_365_dias(con):
    # V4 saiu antes da janela; S4 entrou antes e saiu dentro: conta só a parte na janela.
    assert _hist(con, "E4") == (1, 3, 362)
    assert _hist(con, "E5") == (1, 0, 365)
    assert _hist(con, "E6") == (0, 0, 366)


def test_historico_completo(con):
    assert _coluna(con, "C7", "historico_completo") is True
    assert _coluna(con, "C8", "historico_completo") is False
    assert _coluna(con, "E9", "historico_completo") is False


def test_historico_usa_episodios_nao_elegiveis(con):
    assert _coluna(con, "P9", "episodios_365d") is None  # saída antes do início: sem linha
    assert _hist(con, "E9") == (1, 19, 21)
    assert _hist(con, "E10") == (1, 4, 27)
    assert _coluna(con, "E10", "historico_com_obito") is True


def test_so_episodios_elegiveis_e_rotulo_sem_vazamento_do_futuro(con):
    ids = {r[0] for r in con.execute("select episodio_id from atributo_episodio").fetchall()}
    assert "X11" not in ids and "M10" not in ids and "P9" not in ids
    assert _hist(con, "E11") == (0, 0, None)
    assert con.execute(
        "select count(*) from atributo_episodio where readmissao_30d is null").fetchone()[0] == 0
    assert _coluna(con, "E1", "readmissao_30d") is False
    assert _coluna(con, "A3", "readmissao_30d") is True


def test_atributos_do_episodio(con):
    linha = con.execute(
        "select idade, sexo, capitulo_cid, grupo_sigtap, car_int, dias_permanencia, dias_uti, "
        "usou_uti, n_aihs, n_hospitais, houve_transferencia, cnes_alta, ano_alta "
        "from atributo_episodio where episodio_id = 'E1'"
    ).fetchone()
    assert linha == (50, "F", "IX", "03", "02", 9, 3, True, 1, 1, False, "1111111", 2024)
    assert _coluna(con, "C7", "sexo") == "M"


def test_regra_d03_continua_parametro():
    con = _montar(REGRA_D03)
    assert _hist(con, "A3") == (0, 0, None)
    assert _coluna(con, "B3", "readmissao_30d") is None
    assert _coluna(con, "A3", "n_aihs") == 2 and _coluna(con, "A3", "houve_contigua_sem_motivo")


def test_faixa_sql():
    con = duckdb.connect()
    expr = faixa_sql("x", (0, 1, 2, 4))
    rotulos = [con.execute(f"select {expr} from (select {v} as x)").fetchone()[0]
               for v in (0, 1, 3, 9)]
    assert rotulos == ["0", "1", "2–3", "4+"]


def test_resumo_so_agregados(con):
    resumo = ler_resumo(con)
    assert resumo.episodios == con.execute("select count(*) from atributo_episodio").fetchone()[0]
    assert [f.rotulo for f in resumo.faixas["usou_uti"]] == ["sim", "não"]
    assert sum(f.episodios for f in resumo.faixas["idade"]) == resumo.episodios
    assert resumo.colisoes["chaves"] == 1


def test_bloco_do_documento_so_agregados(con, tmp_path):
    from readmissao_sus.relatorio_atributos import MARCA_FIM, MARCA_INICIO, gerar_bloco, gravar_bloco

    doc = tmp_path / "atributos.md"
    doc.write_text(f"# Atributos\n\ntexto\n\n{MARCA_INICIO}\nvelho\n{MARCA_FIM}\n", encoding="utf-8")
    gravar_bloco(doc, gerar_bloco(ler_resumo(con), REGRA_PADRAO, "01/01/2025"))
    texto = doc.read_text(encoding="utf-8")

    assert "velho" not in texto and "texto" in texto
    assert "#### `dias_desde_ultima_alta`" in texto and "| `idade` | SMALLINT |" in texto
    assert "IX. Doenças do aparelho circulatório" in texto
    assert "19600101" not in texto and "E1 " not in texto and "2024-03-01" not in texto
