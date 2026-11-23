import hashlib
from datetime import date

import duckdb
import pandas as pd

from readmissao_sus.linkage_viabilidade import COLUNAS_BRUTAS, analisar, analisar_dataframe
from readmissao_sus.relatorio_linkage import MARCA_FIM, MARCA_INICIO, gerar_bloco, gravar_bloco

PESSOAS = {
    "A": ("19500101", "1", "50000000", "261160"),  # CEP genérico (termina em 000)
    "B": ("19600202", "3", "50721110", "261160"),
    "C": ("19700303", "1", "55290123", "260790"),
    "D": ("19800404", "3", "55290456", "260790"),
    "E": ("19900505", "1", "55290789", "260790"),
    "F": ("20000606", "3", "56300111", "261110"),
    "G": ("19850707", "1", "56300222", "261110"),
}


def _aih(n_aih, pessoa, inter, saida, cobranca="12", morte="0", ident="1", competencia=None):
    nasc, sexo, cep, munic = PESSOAS[pessoa]
    comp = competencia or saida[:6]
    return {
        "N_AIH": n_aih, "IDENT": ident, "NASC": nasc, "SEXO": sexo, "CEP": cep, "MUNIC_RES": munic,
        "DT_INTER": inter, "DT_SAIDA": saida, "COBRANCA": cobranca, "MORTE": morte,
        "ANO_CMPT": comp[:4], "MES_CMPT": comp[4:], "CNES": "1234567",
    }


def _cenario():
    linhas = [
        # A: readmissão aos 15 dias; a terceira internação vem 71 dias depois (não conta).
        _aih("A1", "A", "20230301", "20230305"),
        _aih("A2", "A", "20230320", "20230322"),
        _aih("A3", "A", "20230601", "20230603"),
        # B: saída por transferência e nova AIH no mesmo dia (contígua, não é readmissão real).
        _aih("B1", "B", "20230401", "20230410", cobranca="31"),
        _aih("B2", "B", "20230410", "20230415"),
        # C: óbito, fora do denominador.
        _aih("C1", "C", "20230501", "20230503", cobranca="41", morte="1"),
        # D: duas internações sobrepostas na mesma chave (colisão).
        _aih("D1", "D", "20230701", "20230710"),
        _aih("D2", "D", "20230705", "20230708"),
        # E: alta depois da data de corte (censurada).
        _aih("E1", "E", "20241210", "20241212"),
        # F: permanência por mudança de procedimento, nova AIH no dia seguinte.
        _aih("F1", "F", "20230801", "20230805", cobranca="26"),
        _aih("F2", "F", "20230806", "20230809"),
        # G: longa permanência; a IDENT=5 estende a saída até 31/10 e só assim há readmissão.
        _aih("G1", "G", "20230901", "20230930", cobranca="21"),
        _aih("G1", "G", "20230901", "20231031", ident="5"),
        _aih("G2", "G", "20231115", "20231116"),
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS_BRUTAS), dtype="string")


def test_conta_colisoes_por_sobreposicao_no_tempo():
    r = analisar_dataframe(_cenario())

    assert r.chaves.internacoes == 13
    assert r.chaves.chaves == 7
    assert r.chaves.distribuicao == {"1": 2, "2": 4, "3": 1, "4": 0, "5–9": 0, "10+": 0}
    assert r.chaves.chaves_multiplas == 5
    assert r.chaves.chaves_colidentes == 1
    assert r.chaves.internacoes_em_colisao == 2
    assert r.chaves.sobrepostas == 1
    genericos = next(g for g in r.placeholders if g.nome.startswith("CEP terminado"))
    assert (genericos.chaves, genericos.chaves_multiplas, genericos.chaves_colidentes) == (1, 1, 0)


def test_taxa_de_readmissao_exclui_obito_e_censura_e_separa_contiguas():
    r = analisar_dataframe(_cenario())
    ra = r.readmissao

    assert r.cobertura.fim == date(2024, 12, 31)
    assert r.cobertura.limite_indice == date(2024, 12, 1)
    assert ra.altas_indice == 11
    assert ra.obitos_excluidos == 1
    assert ra.censuradas == 1
    assert ra.readmitidas == 4  # A1, B1 (transferência), F1 (permanência), G1 (pela IDENT=5)
    assert ra.contiguas_transferencia == 1
    assert ra.contiguas_permanencia == 1
    assert ra.por_gap == {"0–1": 2, "2–7": 0, "8–30": 2}
    assert ra.taxa_bruta == 4 / 11
    assert ra.taxa_sem_transferencia == 3 / 10
    assert ra.taxa_sem_transferencia_permanencia == 2 / 9


def test_plano_b_usa_saida_final_da_longa_permanencia():
    b = analisar_dataframe(_cenario()).plano_b

    assert b.saidas == 13
    assert b.obitos == 1
    assert b.acima_de[30] == 1  # G1: 01/09 a 31/10


def test_chave_fica_so_como_hash_e_ident1_duplicada_e_removida():
    df = _cenario()
    repetida = df[df["N_AIH"] == "A1"].assign(MES_CMPT="04")
    con = duckdb.connect()
    con.register("bruto_df", pd.concat([df, repetida], ignore_index=True))
    r = analisar(con, "bruto_df")

    assert r.preparo.ident1_duplicadas == 1
    assert r.preparo.ident5_linhas == 1
    assert r.preparo.ident5_orfas == 0
    assert r.preparo.internacoes == 13
    colunas = {c[0] for c in con.execute("describe internacoes").fetchall()}
    assert not colunas & {"NASC", "SEXO", "CEP", "MUNIC_RES", "nasc", "cep"}
    esperado = hashlib.sha256("|".join(PESSOAS["A"]).encode()).hexdigest()
    hashes = {h for (h,) in con.execute("select distinct chave from internacoes").fetchall()}
    assert esperado in hashes


def test_censura_usa_atraso_de_processamento():
    df = _cenario()
    # Saída de 03/2023 processada só na competência seguinte: 1 de 14 AIHs no período com atraso.
    atrasada = pd.DataFrame([_aih("H1", "E", "20230302", "20230303", competencia="202304")],
                            columns=list(COLUNAS_BRUTAS), dtype="string")
    r = analisar_dataframe(pd.concat([df, atrasada], ignore_index=True))

    assert r.cobertura.completude_por_lag[0] < 0.98
    assert r.cobertura.fim == date(2024, 11, 30)
    assert r.cobertura.limite_indice == date(2024, 10, 31)


def test_gravar_bloco_substitui_so_o_trecho_gerado(tmp_path):
    destino = tmp_path / "decisoes.md"
    destino.write_text(f"# Decisões\n\nantes\n\n{MARCA_INICIO}\nvelho\n{MARCA_FIM}\n\ndepois\n", encoding="utf-8")
    bloco = gerar_bloco(analisar_dataframe(_cenario()), "01/01/2025")

    gravar_bloco(destino, bloco)

    texto = destino.read_text(encoding="utf-8")
    assert "velho" not in texto
    assert texto.count(MARCA_INICIO) == 1
    assert texto.startswith("# Decisões\n\nantes") and texto.rstrip().endswith("depois")
    assert "36,36%" in texto
    assert "19500101" not in texto and "50000000" not in texto
