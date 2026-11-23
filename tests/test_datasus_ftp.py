import ftplib

import pytest

from readmissao_sus.datasus_ftp import ErroDownload, baixar_faltantes, nomes_arquivos_rd


def test_nomes_arquivos_rd_gera_24_meses():
    nomes = nomes_arquivos_rd("pe", [2023, 2024])
    assert len(nomes) == 24
    assert nomes[0] == "RDPE2301.dbc"
    assert nomes[-1] == "RDPE2412.dbc"


def test_nomes_arquivos_rd_rejeita_uf_invalida():
    with pytest.raises(ValueError):
        nomes_arquivos_rd("PER", [2023])


def test_baixar_faltantes_nao_baixa_o_que_ja_existe(tmp_path):
    (tmp_path / "RDPE2301.dbc").write_bytes(b"ja existe")
    pedidos = []

    def baixar(nome, caminho):
        pedidos.append(nome)
        caminho.write_bytes(b"conteudo")

    nomes = ["RDPE2301.dbc", "RDPE2302.dbc"]
    assert baixar_faltantes(nomes, tmp_path, baixar) == ["RDPE2302.dbc"]
    assert baixar_faltantes(nomes, tmp_path, baixar) == []
    assert pedidos == ["RDPE2302.dbc"]
    assert (tmp_path / "RDPE2301.dbc").read_bytes() == b"ja existe"


def test_baixar_faltantes_rebaixa_arquivo_vazio(tmp_path):
    (tmp_path / "RDPE2301.dbc").write_bytes(b"")
    assert baixar_faltantes(["RDPE2301.dbc"], tmp_path, lambda n, c: c.write_bytes(b"x")) == ["RDPE2301.dbc"]


def test_baixar_faltantes_falha_de_rede_da_mensagem_clara_e_nao_deixa_lixo(tmp_path):
    def baixar(nome, caminho):
        caminho.write_bytes(b"metade")
        raise ftplib.error_temp("421 Service not available")

    with pytest.raises(ErroDownload, match="RDPE2301.dbc.*rode o script de novo"):
        baixar_faltantes(["RDPE2301.dbc"], tmp_path, baixar)
    assert list(tmp_path.iterdir()) == []
