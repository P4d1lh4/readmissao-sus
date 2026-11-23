import hashlib
import io
import json
import tarfile
import urllib.error

import pytest

from readmissao_sus.pacotes_fhir import (
    PACOTES,
    ErroPacote,
    PacoteFhir,
    baixar_pacotes,
    dependencias_externas,
)


def _tgz(nome, versao, dependencias=None):
    manifesto = {"name": nome, "version": versao, "dependencies": dependencias or {}}
    dados = json.dumps(manifesto).encode("utf-8")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(dados)
        tar.addfile(info, io.BytesIO(dados))
    return buffer.getvalue()


def _pacote(conteudo, nome="br.exemplo", versao="1.0.0"):
    return PacoteFhir(nome, versao, f"https://exemplo.test/{nome}", hashlib.sha256(conteudo).hexdigest())


class BaixadorFalso:
    def __init__(self, conteudos):
        self.conteudos = conteudos
        self.pedidos = []

    def __call__(self, url, caminho):
        self.pedidos.append(url)
        caminho.write_bytes(self.conteudos[url])


def test_pacotes_tem_versao_fixa_e_hash():
    assert {p.arquivo for p in PACOTES} == {"br.go.ses.core-1.2.6.tgz", "br.go.ses.reds-go-1.0.3.tgz"}
    assert all(len(p.sha256) == 64 for p in PACOTES)


def test_baixar_pacotes_e_idempotente(tmp_path):
    conteudo = _tgz("br.exemplo", "1.0.0")
    pacote = _pacote(conteudo)
    baixador = BaixadorFalso({pacote.url: conteudo})

    assert baixar_pacotes([pacote], tmp_path, baixador) == ["br.exemplo-1.0.0.tgz"]
    assert baixar_pacotes([pacote], tmp_path, baixador) == []
    assert baixador.pedidos == [pacote.url]
    assert (tmp_path / "br.exemplo-1.0.0.tgz").read_bytes() == conteudo


def test_baixar_pacotes_substitui_arquivo_corrompido(tmp_path):
    conteudo = _tgz("br.exemplo", "1.0.0")
    pacote = _pacote(conteudo)
    (tmp_path / pacote.arquivo).write_bytes(b"corrompido")

    assert baixar_pacotes([pacote], tmp_path, BaixadorFalso({pacote.url: conteudo})) == [pacote.arquivo]
    assert (tmp_path / pacote.arquivo).read_bytes() == conteudo


def test_hash_diferente_falha_e_nao_deixa_lixo(tmp_path):
    pacote = _pacote(_tgz("br.exemplo", "1.0.0"))
    publicado_depois = _tgz("br.exemplo", "1.0.1")

    with pytest.raises(ErroPacote, match="SHA-256 .* diferente do esperado"):
        baixar_pacotes([pacote], tmp_path, BaixadorFalso({pacote.url: publicado_depois}))
    assert list(tmp_path.iterdir()) == []


def test_package_json_com_outra_versao_falha(tmp_path):
    conteudo = _tgz("br.exemplo", "9.9.9")
    pacote = _pacote(conteudo, versao="1.0.0")

    with pytest.raises(ErroPacote, match="esperado br.exemplo#1.0.0"):
        baixar_pacotes([pacote], tmp_path, BaixadorFalso({pacote.url: conteudo}))
    assert list(tmp_path.iterdir()) == []


def test_falha_de_rede_da_mensagem_clara_e_nao_deixa_lixo(tmp_path):
    pacote = _pacote(b"x")

    def baixar(url, caminho):
        caminho.write_bytes(b"metade")
        raise urllib.error.URLError("timed out")

    with pytest.raises(ErroPacote, match="rode o script de novo"):
        baixar_pacotes([pacote], tmp_path, baixar)
    assert list(tmp_path.iterdir()) == []


def test_dependencias_externas_ignora_as_que_estao_na_lista(tmp_path):
    base = _tgz("br.base", "1.0.0", {"hl7.fhir.r4.core": "4.0.1"})
    guia = _tgz("br.guia", "2.0.0", {"hl7.fhir.r4.core": "4.0.1", "br.base": "1.0.0"})
    pacotes = [_pacote(base, "br.base", "1.0.0"), _pacote(guia, "br.guia", "2.0.0")]
    baixar_pacotes(pacotes, tmp_path, BaixadorFalso({pacotes[0].url: base, pacotes[1].url: guia}))

    assert dependencias_externas(pacotes, tmp_path) == {"hl7.fhir.r4.core": "4.0.1"}
