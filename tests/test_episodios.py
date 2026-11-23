from datetime import date

import duckdb
import pandas as pd
import pytest

from readmissao_sus.banco import COLUNAS_FONTE, montar_coorte, preparar_internacoes
from readmissao_sus.episodios import (
    REGRA_PADRAO, REGRA_PROPOSTA_D03, RegraEpisodio, comparar_regras, montar_episodios,
)

INICIO = date(2023, 1, 1)
CORTE = date(2024, 10, 1)


def _aih(pessoa, n_aih, inter, saida, cobranca="12", cnes="1111111", morte="0", diag="I500"):
    """Uma AIH IDENT = 1; `pessoa` vira a data de nascimento, e com ela a chave de linkage."""
    return {
        "N_AIH": n_aih, "IDENT": "1", "ANO_CMPT": saida[:4], "MES_CMPT": saida[4:6],
        "NASC": pessoa, "SEXO": "1", "CEP": "55290456", "MUNIC_RES": "260790", "IDADE": "50",
        "COD_IDADE": "4", "DT_INTER": inter, "DT_SAIDA": saida, "DIAG_PRINC": diag,
        "PROC_REA": "0303060212", "CNES": cnes, "CAR_INT": "02", "COBRANCA": cobranca,
        "MORTE": morte, "UTI_MES_TO": "0",
    }


def _cenario():
    linhas = [
        # Transferência (31) com nova AIH no mesmo dia, no dia seguinte e 2 dias depois.
        _aih("19700101", "T0A", "20230301", "20230305", "31", cnes="1111111"),
        _aih("19700101", "T0B", "20230305", "20230310", "12", cnes="2222222"),
        _aih("19700102", "T1A", "20230301", "20230305", "31"),
        _aih("19700102", "T1B", "20230306", "20230310", "12", cnes="2222222"),
        _aih("19700103", "T2A", "20230301", "20230305", "31"),
        _aih("19700103", "T2B", "20230307", "20230310", "12", cnes="2222222"),
        # Alta comum seguida de nova AIH no mesmo dia: no mesmo hospital e em outro.
        _aih("19700104", "AMA", "20230301", "20230305", "12", cnes="1111111"),
        _aih("19700104", "AMB", "20230305", "20230310", "12", cnes="1111111"),
        _aih("19700105", "AOA", "20230301", "20230305", "12", cnes="1111111"),
        _aih("19700105", "AOB", "20230306", "20230310", "12", cnes="2222222"),
        # Permanência (26, mudança de procedimento) seguida de nova AIH no dia seguinte.
        _aih("19700106", "PA", "20230301", "20230305", "26"),
        _aih("19700106", "PB", "20230306", "20230310", "12"),
        # Cadeia A → B → C, e readmissão 10 dias depois da saída final.
        _aih("19700107", "CA", "20230301", "20230303", "31", cnes="1111111"),
        _aih("19700107", "CB", "20230303", "20230308", "31", cnes="2222222"),
        _aih("19700107", "CC", "20230309", "20230315", "12", cnes="3333333", diag="J189"),
        _aih("19700107", "CR", "20230325", "20230327", "12"),
        # Cadeia que termina em óbito: o episódio inteiro sai da coorte.
        _aih("19700108", "OA", "20230301", "20230305", "31"),
        _aih("19700108", "OB", "20230305", "20230308", "41", cnes="2222222", morte="1"),
        # Sobreposta: começa antes da saída da transferência; é colisão, não continuação.
        _aih("19700109", "SA", "20230301", "20230305", "31"),
        _aih("19700109", "SB", "20230304", "20230310", "12", cnes="2222222"),
        # Cadeia que atravessa a data de corte: a saída final manda, e o episódio é censurado.
        _aih("19700110", "XA", "20240925", "20240930", "31"),
        _aih("19700110", "XB", "20241001", "20241005", "12", cnes="2222222"),
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS_FONTE), dtype="string")


def _montar(regra=REGRA_PADRAO):
    con = duckdb.connect()
    con.register("bruto_df", _cenario())
    preparar_internacoes(con, "bruto_df", "sal")
    montar_coorte(con, INICIO, CORTE)
    montar_episodios(con, regra, INICIO, CORTE)
    return con


@pytest.fixture
def con():
    return _montar()


def _episodio_de(con, n_aih):
    return con.execute(
        """
        select e.aihs, e.dt_inter, e.dt_saida, e.cobranca, e.hospitais, e.obito
        from episodio e join episodio_membro m using (episodio_id) where m.n_aih = ?
        """,
        [n_aih],
    ).fetchone()


def test_transferencia_no_mesmo_dia_junta(con):
    aihs, inter, saida, cobranca, hospitais, _ = _episodio_de(con, "T0B")

    assert aihs == ["T0A", "T0B"]
    assert (inter, saida, cobranca) == (date(2023, 3, 1), date(2023, 3, 10), "12")
    assert hospitais == ["1111111", "2222222"]


def test_transferencia_no_dia_seguinte_junta(con):
    assert _episodio_de(con, "T1A")[0] == ["T1A", "T1B"]


def test_transferencia_seguida_de_aih_dois_dias_depois_nao_junta(con):
    assert _episodio_de(con, "T2A")[0] == ["T2A"]
    assert _episodio_de(con, "T2B")[0] == ["T2B"]
    dias, readmitida = con.execute(
        "select dias_ate_readmissao, readmissao_30d from coorte_episodio where episodio_id = 'T2A'"
    ).fetchone()
    assert (dias, readmitida) == (2, True)


def test_alta_comum_nao_junta_no_padrao(con):
    for n_aih in ("AMA", "AMB", "AOA", "AOB"):
        assert _episodio_de(con, n_aih)[0] == [n_aih]


def test_sobreposta_nao_junta(con):
    assert _episodio_de(con, "SB")[0] == ["SB"]


def test_permanencia_junta_no_padrao_e_nao_junta_sem_o_parametro(con):
    assert _episodio_de(con, "PA")[0] == ["PA", "PB"]

    sem = _montar(RegraEpisodio(juntar_permanencia=False))
    assert _episodio_de(sem, "PA")[0] == ["PA"]
    assert _episodio_de(sem, "T0A")[0] == ["T0A", "T0B"]   # transferência continua juntando


def test_contiguas_sem_motivo_seguem_o_parametro_da_d03():
    proposta = _montar(REGRA_PROPOSTA_D03)
    assert _episodio_de(proposta, "AMA")[0] == ["AMA", "AMB"]   # mesmo hospital: junta
    assert _episodio_de(proposta, "AOA")[0] == ["AOA"]          # outro hospital: não junta

    todas = _montar(RegraEpisodio(contiguas_sem_motivo="todas"))
    assert _episodio_de(todas, "AOA")[0] == ["AOA", "AOB"]
    assert _episodio_de(todas, "T2A")[0] == ["T2A"]             # 2 dias continua separado


def test_regra_invalida_falha():
    with pytest.raises(ValueError, match="contiguas_sem_motivo"):
        RegraEpisodio(contiguas_sem_motivo="mesmo_cid")


def test_cadeia_de_tres_internacoes_vira_um_episodio(con):
    aihs, inter, saida, cobranca, hospitais, obito = _episodio_de(con, "CC")

    assert aihs == ["CA", "CB", "CC"]
    assert (inter, saida, cobranca, obito) == (date(2023, 3, 1), date(2023, 3, 15), "12", False)
    assert hospitais == ["1111111", "2222222", "3333333"]
    linha = con.execute(
        "select n_internacoes, n_hospitais, ligacoes_transferencia, diag_princ, diag_princ_saida, "
        "readmissao_30d, dias_ate_readmissao from coorte_episodio where episodio_id = 'CA'"
    ).fetchone()
    assert linha == (3, 3, 2, "I500", "J189", True, 10)


def test_obito_no_fim_da_cadeia_tira_o_episodio_da_coorte(con):
    assert _episodio_de(con, "OA")[5] is True
    no_s06 = con.execute("select count(*) from coorte where n_aih = 'OA'").fetchone()[0]
    na_coorte = con.execute(
        "select count(*) from coorte_episodio where episodio_id = 'OA'"
    ).fetchone()[0]
    assert (no_s06, na_coorte) == (1, 0)
    resumo = dict(con.execute(
        "select item, valor from episodio_resumo where secao = 'desfecho'"
    ).fetchall())
    assert resumo["Altas sem óbito da S06 dentro de episódio terminado em óbito"] == 1


def test_censura_usa_a_saida_final_do_episodio(con):
    s06 = con.execute("select elegivel_indice from coorte where n_aih = 'XA'").fetchone()[0]
    episodio = con.execute(
        "select censurada, elegivel_indice, readmissao_30d from coorte_episodio "
        "where episodio_id = 'XA'"
    ).fetchone()
    assert s06 is True
    assert episodio == (True, False, None)


def test_contagens_de_juncao(con):
    resumo = dict(con.execute(
        "select item, valor from episodio_resumo where secao = 'juncao'"
    ).fetchall())
    # 22 internações; ligações: T0, T1, P, C (2), O, X = 7 (T2, alta, sobreposta não ligam).
    assert resumo["Internações (tabela internacao)"] == 22
    assert resumo["Internações juntadas a uma anterior (internações − episódios)"] == 7
    assert resumo["Episódios (tabela episodio)"] == 15
    assert resumo["… depois de transferência"] == 6
    assert resumo["… depois de permanência"] == 1
    assert resumo["Maior episódio (internações)"] == 3
    motivos = {m[0]: m[1:] for m in con.execute("select * from episodio_motivos").fetchall()}
    # Transferências sem óbito: T0A, T1A, T2A, CA, CB, OA, SA, XA = 8; com AIH em 0–1 dia, 6.
    assert motivos["transferencia"] == (8, 6, 6)


def test_comparar_regras_termina_com_a_regra_pedida():
    con = _montar()
    episodios = comparar_regras(con, REGRA_PROPOSTA_D03, INICIO, CORTE)

    assert [c.regra.contiguas_sem_motivo for c in episodios.comparacao] == [
        "nenhuma", "nenhuma", "mesmo_hospital", "todas"]
    assert con.execute("select contiguas_sem_motivo from episodio_parametros").fetchone()[0] == (
        "mesmo_hospital")
    assert _episodio_de(con, "AMA")[0] == ["AMA", "AMB"]
    episodios_por_regra = [c.episodios for c in episodios.comparacao]
    assert episodios_por_regra == sorted(episodios_por_regra, reverse=True)


def test_bloco_do_documento_traz_contagens_e_comparacao_sem_dados_individuais(tmp_path):
    from readmissao_sus.relatorio_episodios import MARCA_FIM, MARCA_INICIO, gerar_bloco, gravar_bloco

    episodios = comparar_regras(_montar(), REGRA_PADRAO, INICIO, CORTE)
    bloco = gerar_bloco(episodios, "01/01/2025")
    doc = tmp_path / "coorte.md"
    doc.write_text(f"# Coorte\n\ntexto\n\n{MARCA_INICIO}\nvelho\n{MARCA_FIM}\n", encoding="utf-8")
    gravar_bloco(doc, bloco)
    texto = doc.read_text(encoding="utf-8")

    assert "velho" not in texto and "texto" in texto
    assert "| Episódios (tabela episodio) | 15 |" in texto
    assert "(proposta D03)" in texto and "(padrão)" in texto
    assert "19700107" not in texto and "T0A" not in texto
