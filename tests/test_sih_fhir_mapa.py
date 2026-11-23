from datetime import date

import pytest

from readmissao_sus import dicionario_sih as dic
from readmissao_sus import sih_fhir_mapa as mapa


@pytest.mark.parametrize(
    "cobranca, esperado",
    [("12", "01"), ("61", "01"), ("14", "02"), ("16", "04"), ("41", "06"), ("26", "07"),
     ("15", "08"), ("31", "09"), ("51", "99"), (None, "99"), ("00", "99")],
)
def test_motivo_desfecho(cobranca, esperado):
    assert mapa.motivo_desfecho(cobranca) == esperado


def test_todo_codigo_de_cobranca_do_dicionario_tem_motivo():
    assert set(dic.COBRANCA) <= set(mapa._MOTIVO_DESFECHO)
    assert {mapa.motivo_desfecho(c) for c in dic.COBRANCA_OBITO} == {"06"}
    assert {mapa.motivo_desfecho(c) for c in dic.COBRANCA_TRANSFERENCIA} == {"09"}
    assert {mapa.motivo_desfecho(c) for c in dic.COBRANCA_PERMANENCIA} == {"07"}


@pytest.mark.parametrize("car_int, esperado", [("01", "01"), ("02", "02"), ("05", "02"), ("06", "02"), ("", "99")])
def test_carater_atendimento(car_int, esperado):
    assert mapa.carater_atendimento(car_int) == esperado


def test_sexo_raca_e_nacionalidade():
    assert (mapa.genero("1"), mapa.genero("3"), mapa.genero("0")) == ("male", "female", "unknown")
    assert (mapa.raca_cor("03"), mapa.raca_cor("7"), mapa.raca_cor(None)) == ("03", "99", "99")
    assert (mapa.nacionalidade("010"), mapa.nacionalidade("081")) == ("B", "E")


@pytest.mark.parametrize("entrada, esperado", [("I500", "I500"), ("i50.0", "I500"), (" A09 ", "A09"), ("O800", "O800")])
def test_cid10_no_formato_do_brcid10(entrada, esperado):
    assert mapa.cid10(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "I5", "I5000", "1500"])
def test_cid10_invalido(entrada):
    with pytest.raises(ValueError):
        mapa.cid10(entrada)


def test_sigtap_cnes_e_cnpj():
    assert mapa.sigtap("0303060212") == "0303060212"
    assert mapa.cnes("0000001") == "0000001"
    with pytest.raises(ValueError):
        mapa.sigtap("303060212")
    with pytest.raises(ValueError):
        mapa.cnes("271203")
    assert mapa.cnpj_valido("11222333000181") == "11222333000181"
    assert mapa.cnpj_valido("00000000000000") is None
    assert mapa.cnpj_valido(None) is None


@pytest.mark.parametrize(
    "idade, cod, esperado",
    [(65, "4", date(1959, 3, 8)), (10, "2", date(2024, 2, 27)), (2, "3", date(2024, 1, 8)), (3, "5", date(1921, 3, 8))],
)
def test_nascimento_aproximado_preserva_a_idade_na_entrada(idade, cod, esperado):
    assert mapa.nascimento_aproximado(idade, cod, date(2024, 3, 8)) == esperado


def test_nascimento_aproximado_em_29_de_fevereiro():
    assert mapa.nascimento_aproximado(1, "4", date(2024, 2, 29)) == date(2023, 2, 28)


def test_cns_sintetico_estavel_por_chave_e_nunca_um_cns_real():
    cns = mapa.cns_sintetico("chave-a")
    assert cns == mapa.cns_sintetico("chave-a") != mapa.cns_sintetico("chave-b")
    assert len(cns) == 15 and cns.isdigit()
    assert cns[0] not in "12789"  # primeiros dígitos válidos do CNS
