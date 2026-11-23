from datetime import date, datetime, timedelta, timezone

import pytest

from readmissao_sus.fhir_sumario import (
    DADO_AUSENTE,
    PERFIL,
    SISTEMA_CID10,
    SISTEMA_CNES,
    SISTEMA_CNPJ,
    SISTEMA_CNS,
    SISTEMA_SIGTAP,
    Episodio,
    Estabelecimento,
    Internacao,
    montar_bundle,
)

GERADO_EM = datetime(2024, 3, 20, 10, 0, tzinfo=timezone(timedelta(hours=-3)))


def _internacao(n_aih, cnes, inicio, fim, cid="I500", proc="0303060212", cobranca="12"):
    return Internacao(n_aih, cnes, inicio, fim, cid, proc, cobranca)


def _episodio(*internacoes, sexo="1", car_int="02"):
    internacoes = internacoes or (_internacao("2624100000001", "0000001", date(2024, 3, 8), date(2024, 3, 15)),)
    return Episodio(
        episodio_id=internacoes[0].n_aih,
        chave="ab" * 32,
        sexo=sexo,
        idade=65,
        cod_idade="4",
        munic_res="261160",
        raca_cor="03",
        nacional="010",
        car_int=car_int,
        internacoes=tuple(internacoes),
        estabelecimento_alta=Estabelecimento(internacoes[-1].cnes, "11222333000181", "260890"),
    )


def _transferencia():
    return _episodio(
        _internacao("2624100000001", "0000001", date(2024, 3, 1), date(2024, 3, 4), cid="I21.0", proc="0303060190", cobranca="31"),
        _internacao("2624100000002", "0000002", date(2024, 3, 4), date(2024, 3, 12), cid="I500", proc="0406030103"),
    )


def _recursos(bundle, tipo):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == tipo]


def _codigos(recursos, sistema):
    return [c["code"] for r in recursos for c in r["code"]["coding"] if c["system"] == sistema]


def test_bundle_document_com_composition_primeiro_e_tipos_esperados():
    bundle = montar_bundle(_episodio(), GERADO_EM)

    assert bundle["type"] == "document"
    assert bundle["timestamp"] == "2024-03-20T10:00:00-03:00"
    assert bundle["identifier"]["value"].startswith("urn:uuid:")
    tipos = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert tipos[0] == "Composition"
    assert sorted(tipos) == sorted(
        ["Composition", "Patient", "Encounter", "Organization", "Practitioner", "Condition", "Procedure"]
    )


def test_cada_recurso_declara_o_perfil_e_tem_narrativa():
    for entrada in montar_bundle(_transferencia(), GERADO_EM)["entry"]:
        recurso = entrada["resource"]
        assert recurso["meta"]["profile"] == [PERFIL[recurso["resourceType"]]]
        assert recurso["text"]["div"].startswith('<div xmlns="http://www.w3.org/1999/xhtml">')


def _referencias(no):
    if isinstance(no, dict):
        for chave, valor in no.items():
            if chave == "reference":
                yield valor
            else:
                yield from _referencias(valor)
    elif isinstance(no, list):
        for item in no:
            yield from _referencias(item)


def test_todas_as_referencias_resolvem_dentro_do_bundle_e_toda_entrada_e_referenciada():
    bundle = montar_bundle(_transferencia(), GERADO_EM)
    urls = [e["fullUrl"] for e in bundle["entry"]]
    referencias = set(_referencias(bundle))

    assert len(urls) == len(set(urls))
    assert referencias <= set(urls)
    assert set(urls[1:]) <= referencias  # só a Composition não é referenciada


def test_composition_aponta_paciente_contato_autores_e_secoes_obrigatorias():
    bundle = montar_bundle(_transferencia(), GERADO_EM)
    por_url = {e["fullUrl"]: e["resource"] for e in bundle["entry"]}
    composicao = bundle["entry"][0]["resource"]

    assert por_url[composicao["subject"]["reference"]]["resourceType"] == "Patient"
    assert por_url[composicao["encounter"]["reference"]]["resourceType"] == "Encounter"
    assert sorted(por_url[a["reference"]]["resourceType"] for a in composicao["author"]) == ["Organization", "Practitioner"]
    secoes = {s["title"]: [por_url[e["reference"]]["resourceType"] for e in s["entry"]] for s in composicao["section"]}
    assert secoes == {
        "Contato Assistencial": ["Encounter"],
        "Diagnóstico(s)": ["Condition", "Condition"],
        "Procedimento(s)": ["Procedure", "Procedure"],
    }


def test_cid10_no_brcid10_sem_ponto_e_principal_da_primeira_aih():
    bundle = montar_bundle(_transferencia(), GERADO_EM)
    condicoes = _recursos(bundle, "Condition")

    assert _codigos(condicoes, SISTEMA_CID10) == ["I210", "I500"]
    categorias = [c["category"][0]["coding"][0]["code"] for c in condicoes]
    assert categorias == ["01", "02"]


def test_cid_repetido_entre_aihs_vira_um_so_diagnostico():
    episodio = _episodio(
        _internacao("1", "0000001", date(2024, 1, 1), date(2024, 1, 3), cobranca="26"),
        _internacao("2", "0000001", date(2024, 1, 3), date(2024, 1, 9)),
    )
    assert len(_recursos(montar_bundle(episodio, GERADO_EM), "Condition")) == 1


def test_um_procedure_sigtap_por_aih_com_a_entrada_da_aih():
    procedimentos = _recursos(montar_bundle(_transferencia(), GERADO_EM), "Procedure")

    assert _codigos(procedimentos, SISTEMA_SIGTAP) == ["0303060190", "0406030103"]
    assert [p["performedDateTime"] for p in procedimentos] == ["2024-03-01", "2024-03-04"]


def test_encounter_periodo_total_hospital_da_alta_e_desfecho():
    bundle = montar_bundle(_transferencia(), GERADO_EM)
    contato = _recursos(bundle, "Encounter")[0]
    por_url = {e["fullUrl"]: e["resource"] for e in bundle["entry"]}
    organizacao = por_url[contato["serviceProvider"]["reference"]]

    assert contato["period"] == {"start": "2024-03-01", "end": "2024-03-12"}
    assert {"system": SISTEMA_CNES, "value": "0000002"} in organizacao["identifier"]
    assert {"system": SISTEMA_CNPJ, "value": "11222333000181"} in organizacao["identifier"]
    assert contato["hospitalization"]["dischargeDisposition"]["coding"][0]["code"] == "01"
    assert contato["priority"]["coding"][0]["code"] == "02"
    usos = [d.get("use", {}).get("coding", [{}])[0].get("code") for d in contato["diagnosis"]]
    assert usos == ["01", "02", None, None]  # dois diagnósticos e dois procedimentos
    assert "0000002" in contato["text"]["div"] and "0000001" in contato["text"]["div"]


def test_paciente_sintetico_sem_cpf_e_com_sexo_e_nascimento_aproximado():
    paciente = _recursos(montar_bundle(_episodio(sexo="3"), GERADO_EM), "Patient")[0]

    cns = next(i for i in paciente["identifier"] if i["system"] == SISTEMA_CNS)["value"]
    assert len(cns) == 15 and cns.startswith("0")
    cpf = next(i for i in paciente["identifier"] if i["system"] != SISTEMA_CNS)
    assert "value" not in cpf and cpf["_value"]["extension"][0]["url"] == DADO_AUSENTE
    assert paciente["gender"] == "female"
    assert paciente["birthDate"] == "1959-03-08"
    assert paciente["name"][0]["text"].startswith("Paciente Sintético ")


def test_mesmo_episodio_gera_o_mesmo_bundle():
    assert montar_bundle(_episodio(), GERADO_EM) == montar_bundle(_episodio(), GERADO_EM)


@pytest.mark.parametrize("campo, valor", [("diag_princ", "1500"), ("proc_rea", "030306"), ("cnes", "12345")])
def test_codigo_mal_formado_falha(campo, valor):
    base = _internacao("1", "0000001", date(2024, 1, 1), date(2024, 1, 2))
    ruim = Internacao(**{**base.__dict__, campo: valor})
    with pytest.raises(ValueError):
        montar_bundle(_episodio(ruim), GERADO_EM)


def test_episodio_sem_internacoes_falha():
    episodio = _episodio()
    vazio = Episodio(**{**episodio.__dict__, "internacoes": ()})
    with pytest.raises(ValueError, match="sem internações"):
        montar_bundle(vazio, GERADO_EM)


def test_local_de_nascimento_brasileiro_usa_o_municipio_de_residencia():
    paciente = _recursos(montar_bundle(_episodio(), GERADO_EM), "Patient")[0]
    local = next(e for e in paciente["extension"] if e["url"].endswith("patient-birthPlace"))["valueAddress"]
    assert local == {"city": "261160", "country": "BRA"}
    assert paciente["address"][0]["city"] == "261160"


def test_estrangeiro_sem_municipio_de_nascimento():
    estrangeiro = Episodio(**{**_episodio().__dict__, "nacional": "081"})
    paciente = _recursos(montar_bundle(estrangeiro, GERADO_EM), "Patient")[0]
    local = next(e for e in paciente["extension"] if e["url"].endswith("patient-birthPlace"))["valueAddress"]
    assert "city" not in local and "_country" in local
