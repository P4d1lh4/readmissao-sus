import hashlib
from pathlib import Path

import pytest

from readmissao_sus import validador_fhir
from readmissao_sus.validador_fhir import (
    IMAGEM_JAVA,
    VALIDADOR_ARQUIVO,
    ErroValidador,
    MensagemConhecida,
    comando_docker,
    formatar_resumo,
    garantir_validador,
    interpretar_outcome,
)


def _issue(severidade, texto, local="Bundle.entry[0]"):
    return {"severity": severidade, "code": "processing", "details": {"text": texto}, "expression": [local]}


def _outcome(*issues):
    return {"resourceType": "OperationOutcome", "issue": list(issues)}


def test_versoes_fixas():
    assert len(validador_fhir.VALIDADOR_SHA256) == 64
    assert "/releases/download/7.0.3/" in validador_fhir.VALIDADOR_URL
    tag, digest = IMAGEM_JAVA.split("@sha256:")
    assert ":" in tag and not tag.endswith(":latest")
    assert len(digest) == 64


def test_conta_erros_avisos_e_informacoes():
    resumo = interpretar_outcome(
        _outcome(
            _issue("error", "faltou seção"),
            _issue("fatal", "JSON quebrado"),
            _issue("warning", "sem narrativa"),
            _issue("information", "All OK"),
        )
    )
    assert (resumo.erros, resumo.avisos, resumo.informacoes, resumo.conhecidas) == (2, 1, 1, 0)
    assert not resumo.valido


def test_so_informacao_e_valido():
    resumo = interpretar_outcome(_outcome(_issue("information", "All OK", local="")))
    assert resumo.valido
    assert "0 erro(s)" in formatar_resumo(resumo)
    assert "Resultado: VÁLIDO" in formatar_resumo(resumo)


def test_bundle_de_outcomes_soma_todos():
    saida = {
        "resourceType": "Bundle",
        "entry": [{"resource": _outcome(_issue("error", "a"))}, {"resource": _outcome(_issue("error", "b"))}],
    }
    assert interpretar_outcome(saida).erros == 2


def test_mensagem_conhecida_sai_dos_erros_mas_aparece_no_resumo():
    conhecida = MensagemConhecida(r"^Erro do perfil", "o perfil exige um código que não existe")
    resumo = interpretar_outcome(
        _outcome(_issue("error", "Erro do perfil X"), _issue("error", "Erro real")), [conhecida]
    )
    assert (resumo.erros, resumo.conhecidas) == (1, 1)
    texto = formatar_resumo(resumo)
    assert "[CONHECIDA]" in texto and "o perfil exige" in texto
    assert "[ERRO] Bundle.entry[0]: Erro real" in texto


def test_informacao_nunca_vira_conhecida():
    conhecida = MensagemConhecida("All OK", "x")
    assert interpretar_outcome(_outcome(_issue("information", "All OK")), [conhecida]).conhecidas == 0


def test_saida_inesperada_falha():
    with pytest.raises(ErroValidador, match="Saída inesperada"):
        interpretar_outcome({"resourceType": "Patient"})


def test_comando_docker_monta_entrada_so_leitura_e_pacotes_em_ordem(tmp_path):
    arquivo = tmp_path / "doc" / "sumario.json"
    jar = tmp_path / "cache" / VALIDADOR_ARQUIVO
    pacotes = [tmp_path / "pacotes" / "a.tgz", tmp_path / "pacotes" / "b.tgz"]

    comando = comando_docker(arquivo, jar, pacotes, tmp_path / "saida", "o.json", eh_bundle=True)

    texto = " ".join(comando)
    assert f"{arquivo.parent.resolve()}:/entrada:ro" in texto
    assert f"{pacotes[0].parent.resolve()}:/pacotes:ro" in texto
    assert f"{validador_fhir.VOLUME_CACHE_FHIR}:/root/.fhir" in texto
    assert "-ig /pacotes/a.tgz -ig /pacotes/b.tgz" in texto
    assert f"-bundle Composition:0 {validador_fhir.PERFIL_SUMARIO_ALTA}" in texto
    assert "-tx" not in comando


def test_comando_docker_recurso_avulso_usa_profile_e_sem_terminologia(tmp_path):
    pacotes = [tmp_path / "a.tgz"]
    comando = comando_docker(
        tmp_path / "x.json", tmp_path / "v.jar", pacotes, tmp_path, "o.json",
        perfil="http://exemplo.test/p", eh_bundle=False, com_terminologia=False,
    )
    assert comando[comando.index("-profile") + 1] == "http://exemplo.test/p"
    assert comando[comando.index("-tx") + 1] == "n/a"


def test_garantir_validador_baixa_uma_vez(tmp_path, monkeypatch):
    conteudo = b"jar falso"
    monkeypatch.setattr(validador_fhir, "VALIDADOR_SHA256", hashlib.sha256(conteudo).hexdigest())
    pedidos = []

    def baixar(url, caminho: Path):
        pedidos.append(url)
        caminho.write_bytes(conteudo)

    assert garantir_validador(tmp_path, baixar).read_bytes() == conteudo
    assert garantir_validador(tmp_path, baixar).name == VALIDADOR_ARQUIVO
    assert len(pedidos) == 1


def test_garantir_validador_hash_errado_falha_sem_lixo(tmp_path):
    def baixar(url, caminho: Path):
        caminho.write_bytes(b"outro conteudo")

    with pytest.raises(ErroValidador, match="SHA-256"):
        garantir_validador(tmp_path, baixar)
    assert list(tmp_path.iterdir()) == []


def test_local_sem_comentarios_do_validador():
    issue = _issue("error", "x", local="Bundle.entry[5].resource/*Condition/null*/.code.coding[0]")
    assert interpretar_outcome(_outcome(issue)).mensagens[0].local == "Bundle.entry[5].resource.code.coding[0]"


TEXTO_NACIONALIDADE = (
    "Constraint failed: BrasileiroSeSomenteSeNasceNoBrasil: 'Brasileiro SE SOMENTE SE nasce no Brasil.' "
    "(defined in https://fhir.saude.go.gov.br/r4/core/StructureDefinition/individuo)"
)
TEXTO_CATEGORIA = (
    "None of the codings provided are in the value set 'Condition Category Codes' "
    "(http://hl7.org/fhir/ValueSet/condition-category|4.0.1), and a coding should come from this value set "
    "(codes = http://www.saude.gov.br/fhir/r4/CodeSystem/BRCategoriaDiagnostico#01)"
)


def test_mensagens_conhecidas_do_perfil_sao_rebaixadas():
    resumo = interpretar_outcome(_outcome(_issue("warning", TEXTO_NACIONALIDADE), _issue("warning", TEXTO_CATEGORIA)))
    assert (resumo.avisos, resumo.conhecidas) == (0, 2)


def test_mensagem_conhecida_nao_cobre_outro_codigo():
    outro = TEXTO_CATEGORIA.replace("BRCategoriaDiagnostico#01", "OutroSistema#01")
    assert interpretar_outcome(_outcome(_issue("warning", outro))).avisos == 1


def _outcome_de(arquivo, *issues):
    return {
        **_outcome(*issues),
        "extension": [{"url": validador_fhir.EXTENSAO_ARQUIVO, "valueString": f"/entrada/saida/{arquivo}"}],
    }


def test_resumo_por_arquivo_numa_pasta():
    saida = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": _outcome_de("a.json", _issue("information", "All OK"))},
            {"resource": _outcome_de("b.json", _issue("error", "x"), _issue("warning", TEXTO_CATEGORIA))},
        ],
    }
    por_arquivo = validador_fhir.interpretar_por_arquivo(saida)

    assert sorted(por_arquivo) == ["a.json", "b.json"]
    assert por_arquivo["a.json"].valido
    assert (por_arquivo["b.json"].erros, por_arquivo["b.json"].conhecidas) == (1, 1)
