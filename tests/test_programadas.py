"""Alvo sem readmissões programadas (D04, S13): readmissao_nao_planejada_30d."""

from datetime import date

import duckdb
import pandas as pd
import pytest

from readmissao_sus.banco import COLUNAS_FONTE, montar_coorte, preparar_internacoes
from readmissao_sus.episodios import REGRA_PADRAO, montar_episodios
from readmissao_sus.programadas import RegraProgramada

INICIO = date(2023, 1, 1)
CORTE = date(2024, 10, 1)
URGENCIA, ELETIVA = "02", "01"
CLINICO = "0303060212"
QUIMIO = "0304080020"          # internação p/ quimioterapia de administração contínua
INTERCORRENCIA_ONCO = "0304100013"  # tratamento de intercorrências clínicas: não é programada


def _aih(pessoa, n_aih, inter, saida, car_int=URGENCIA, proc=CLINICO, diag="I500"):
    return {
        "N_AIH": n_aih, "IDENT": "1", "ANO_CMPT": saida[:4], "MES_CMPT": saida[4:6],
        "NASC": pessoa, "SEXO": "1", "CEP": "55290456", "MUNIC_RES": "260790", "IDADE": "50",
        "COD_IDADE": "4", "DT_INTER": inter, "DT_SAIDA": saida, "DIAG_PRINC": diag,
        "PROC_REA": proc, "CNES": "1111111", "CAR_INT": car_int, "COBRANCA": "12",
        "MORTE": "0", "UTI_MES_TO": "0",
    }


def _cenario():
    linhas = [
        # Volta de urgência em 10 dias: conta.
        _aih("19700101", "U1", "20230301", "20230305"),
        _aih("19700101", "U2", "20230315", "20230318"),
        # Volta eletiva em 10 dias: não conta.
        _aih("19700102", "E1", "20230301", "20230305"),
        _aih("19700102", "E2", "20230315", "20230318", car_int=ELETIVA),
        # Volta de urgência com procedimento sempre programado (quimioterapia): não conta.
        _aih("19700103", "Q1", "20230301", "20230305"),
        _aih("19700103", "Q2", "20230315", "20230318", proc=QUIMIO),
        # Volta de urgência com CID sempre programado (Z51.1, sessão de quimioterapia): não conta.
        _aih("19700104", "Z1", "20230301", "20230305"),
        _aih("19700104", "Z2", "20230315", "20230318", diag="Z511"),
        # Intercorrência oncológica (030410) não está na lista: conta.
        _aih("19700105", "I1", "20230301", "20230305"),
        _aih("19700105", "I2", "20230315", "20230318", proc=INTERCORRENCIA_ONCO),
        # Programada em 5 dias e urgência em 20: a programada não censura, a urgência conta.
        _aih("19700106", "P1", "20230301", "20230305"),
        _aih("19700106", "P2", "20230310", "20230312", car_int=ELETIVA),
        _aih("19700106", "P3", "20230325", "20230328"),
        # Programada em 5 dias e urgência em 40: a urgência está fora da janela.
        _aih("19700107", "F1", "20230301", "20230305"),
        _aih("19700107", "F2", "20230310", "20230312", proc=QUIMIO),
        _aih("19700107", "F3", "20230414", "20230416"),
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS_FONTE), dtype="string")


def _montar(programada=RegraProgramada()):
    con = duckdb.connect()
    con.register("bruto_df", _cenario())
    preparar_internacoes(con, "bruto_df", "sal")
    montar_coorte(con, INICIO, CORTE)
    montar_episodios(con, REGRA_PADRAO, INICIO, CORTE, programada)
    return con


@pytest.fixture(scope="module")
def con():
    return _montar()


def _alvos(con, episodio_id):
    return con.execute(
        "select readmissao_30d, readmissao_nao_planejada_30d, dias_ate_readmissao, "
        "dias_ate_readmissao_nao_planejada from coorte_episodio where episodio_id = ?",
        [episodio_id],
    ).fetchone()


def test_volta_de_urgencia_conta(con):
    assert _alvos(con, "U1") == (True, True, 10, 10)


def test_volta_eletiva_nao_conta(con):
    assert _alvos(con, "E1") == (True, False, 10, None)


def test_volta_com_procedimento_sempre_programado_nao_conta(con):
    assert _alvos(con, "Q1") == (True, False, 10, None)


def test_volta_com_cid_sempre_programado_nao_conta(con):
    assert _alvos(con, "Z1") == (True, False, 10, None)


def test_intercorrencia_oncologica_conta(con):
    assert _alvos(con, "I1") == (True, True, 10, 10)


def test_programada_nao_censura_a_volta_nao_planejada_seguinte(con):
    assert _alvos(con, "P1") == (True, True, 5, 20)
    assert _alvos(con, "F1") == (True, False, 5, None)


def test_coluna_antiga_nao_muda_com_a_regra():
    """readmissao_30d é a mesma com e sem a regra de programadas (e sem nenhuma lista)."""
    consulta = "select episodio_id, readmissao_30d, dias_ate_readmissao from coorte_episodio order by 1"
    padrao = _montar().execute(consulta).fetchall()
    sem_regra = _montar(RegraProgramada(eletiva=False, sempre_programados=())).execute(consulta)
    assert sem_regra.fetchall() == padrao


def test_sem_regra_o_alvo_novo_e_igual_ao_antigo():
    con = _montar(RegraProgramada(eletiva=False, sempre_programados=()))
    diferentes = con.execute(
        "select count(*) from coorte_episodio "
        "where readmissao_30d is distinct from readmissao_nao_planejada_30d"
    ).fetchone()[0]
    assert diferentes == 0


def test_eletiva_nao_programada_pelo_parametro():
    con = _montar(RegraProgramada(eletiva=False))
    assert _alvos(con, "E1") == (True, True, 10, 10)
    assert _alvos(con, "Q1") == (True, False, 10, None)   # a lista continua valendo


def test_alta_eletiva_tambem_e_indice(con):
    # P2 é a volta programada de P1 e também alta-índice: a urgência 13 dias depois conta.
    assert _alvos(con, "P2") == (True, True, 13, 13)
    assert _alvos(con, "U2") == (False, False, None, None)


def test_contagens_da_d04(con):
    itens = dict(con.execute(
        "select item, valor from episodio_resumo where secao = 'readmissao'"
    ).fetchall())
    assert itens["Readmitidas em 30 dias sem as voltas programadas (D04)"] == 4   # U1, I1, P1, P2
    assert itens["Readmitidas com a primeira volta programada"] == 5          # E1, Q1, Z1, P1, F1
    assert itens["… e com volta não planejada depois, ainda em 30 dias (continuam no alvo)"] == 1
    assert itens["Reclassificadas: readmitidas que saem do alvo (só voltas programadas)"] == 4


def test_tipo_invalido_falha():
    with pytest.raises(ValueError, match="Tipo inválido"):
        RegraProgramada(sempre_programados=(("sigtap", "0304", "x"),))
