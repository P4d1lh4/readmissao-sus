"""Sumário de Alta em FHIR (Bundle do tipo document) a partir de um episódio do SIH (S08).

`montar_bundle` é pura: recebe um `Episodio` (dados simples, lidos do banco por
`episodio_leitura.py`) e devolve o Bundle como dicionário JSON. Segue o perfil `sumario-alta`
da SES-GO 1.2.6 e os perfis de cada entrada (D02 em docs/decisoes.md).

Escolhas (detalhadas no README, seção "Sumário de Alta a partir do episódio"):
- um episódio com várias AIHs (transferência, permanência) vira um único Encounter, com o
  período total e o hospital da alta como serviceProvider e autor; os outros hospitais
  aparecem na narrativa;
- um Procedure por AIH (PROC_REA, com o período da AIH) e um Condition por CID distinto
  (DIAG_PRINC da primeira AIH como principal, os das AIHs seguintes como secundários);
- o SIH não identifica paciente nem profissional: o Patient tem nome e CNS sintéticos, e o
  que o SIH não tem vai com a extensão data-absent-reason (`unknown`), não com dado inventado.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from readmissao_sus import sih_fhir_mapa as mapa

Json = dict[str, Any]

CORE = "https://fhir.saude.go.gov.br/r4/core"
RNDS = "http://www.saude.gov.br/fhir/r4"
PERFIL = {
    "Composition": f"{CORE}/StructureDefinition/sumario-alta",
    "Patient": f"{CORE}/StructureDefinition/individuo",
    "Encounter": f"{CORE}/StructureDefinition/contato-assistencial-sumario-alta",
    "Condition": f"{CORE}/StructureDefinition/diagnostico-sumario-alta",
    "Procedure": f"{CORE}/StructureDefinition/procedimento-sumario-alta",
    "Organization": f"{CORE}/StructureDefinition/estabelecimento-saude",
    "Practitioner": f"{CORE}/StructureDefinition/profissional",
}
SISTEMA_CID10 = f"{RNDS}/CodeSystem/BRCID10"
SISTEMA_SIGTAP = f"{RNDS}/CodeSystem/BRTabelaSUS"
SISTEMA_CNES = "https://fhir.saude.go.gov.br/sid/cnes"
SISTEMA_CNPJ = "https://fhir.saude.go.gov.br/sid/cnpj"
SISTEMA_CNS = "https://fhir.saude.go.gov.br/sid/cns"
SISTEMA_CPF = "https://fhir.saude.go.gov.br/sid/cpf"
SISTEMA_CATEGORIA_DIAGNOSTICO = f"{RNDS}/CodeSystem/BRCategoriaDiagnostico"
DADO_AUSENTE = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
EXT_DESCRICAO_EVOLUCAO = f"{CORE}/StructureDefinition/sd-descricao-evolucao"
EXT_TIPO_ENDERECO = f"{CORE}/StructureDefinition/tipo-informacao-endereco"

MODALIDADE_HOSPITALAR = "04"
PROCEDENCIA_AUSENTE = "99"
CATEGORIA_PRINCIPAL, CATEGORIA_SECUNDARIO = "01", "02"
FILIACAO_DESCONHECIDA = "03"
NAO_INFORMADO = "Não informado"
# A invariante DataComPrecisaoDeDia do perfil profissional exige uma data com dia e não aceita
# data-absent-reason; o profissional é um marcador, e esta data também.
NASCIMENTO_PROFISSIONAL = "1900-01-01"
TITULO = "Sumário de Alta"
NAMESPACE_UUID = uuid.UUID("6f1b0c52-4a8e-5d3b-9c2a-7e5d1f0a3b48")
AVISO_SINTETICO = (
    "Documento gerado a partir de dados públicos e anonimizados do SIH/SUS para estudo; "
    "não é documento clínico real e não foi enviado à RNDS."
)


@dataclass(frozen=True)
class Internacao:
    """Uma AIH do episódio, na ordem da cadeia."""

    n_aih: str
    cnes: str
    dt_inter: date
    dt_saida: date
    diag_princ: str
    proc_rea: str
    cobranca: str | None


@dataclass(frozen=True)
class Estabelecimento:
    cnes: str
    cnpj: str
    municipio: str


@dataclass(frozen=True)
class Episodio:
    """Dados de um episódio (sih.duckdb + campos do Parquet que o banco não guarda)."""

    episodio_id: str
    chave: str
    sexo: str | None
    idade: int
    cod_idade: str
    munic_res: str
    raca_cor: str | None
    nacional: str | None
    car_int: str | None
    internacoes: tuple[Internacao, ...]
    estabelecimento_alta: Estabelecimento

    @property
    def dt_inter(self) -> date:
        return self.internacoes[0].dt_inter

    @property
    def dt_saida(self) -> date:
        return self.internacoes[-1].dt_saida

    @property
    def cobranca(self) -> str | None:
        return self.internacoes[-1].cobranca


def montar_bundle(episodio: Episodio, gerado_em: datetime) -> Json:
    """Bundle document: Composition, Patient, Encounter, Organization, Practitioner,
    Conditions e Procedures, todos referenciados por urn:uuid."""
    if not episodio.internacoes:
        raise ValueError(f"Episódio {episodio.episodio_id} sem internações.")
    ids = _Ids(episodio.episodio_id)
    condicoes = _condicoes(episodio, ids)
    procedimentos = _procedimentos(episodio, ids)
    recursos = [
        (ids.composicao, _composicao(episodio, ids, condicoes, procedimentos, gerado_em)),
        (ids.paciente, _paciente(episodio)),
        (ids.contato, _contato(episodio, ids, condicoes, procedimentos)),
        (ids.estabelecimento, _estabelecimento(episodio.estabelecimento_alta)),
        (ids.profissional, _profissional()),
        *((u, r) for u, r, _ in condicoes),
        *((u, r) for u, r, _ in procedimentos),
    ]
    return {
        "resourceType": "Bundle",
        "identifier": {"system": "urn:ietf:rfc:3986", "value": ids.urn("bundle")},
        "type": "document",
        "timestamp": gerado_em.isoformat(timespec="seconds"),
        "entry": [{"fullUrl": url, "resource": recurso} for url, recurso in recursos],
    }


class _Ids:
    """UUIDs determinísticos (uuid5) por episódio: gerar de novo dá o mesmo Bundle."""

    def __init__(self, episodio_id: str) -> None:
        self._base = episodio_id
        self.composicao = self.urn("composicao")
        self.paciente = self.urn("paciente")
        self.contato = self.urn("contato")
        self.estabelecimento = self.urn("estabelecimento")
        self.profissional = self.urn("profissional")

    def urn(self, papel: str) -> str:
        return f"urn:uuid:{uuid.uuid5(NAMESPACE_UUID, f'{self._base}/{papel}')}"


def _ref(url: str) -> Json:
    return {"reference": url}


def _codificado(sistema: str, codigo: str) -> Json:
    return {"coding": [{"system": sistema, "code": codigo}]}


def _narrativa(*paragrafos: str) -> Json:
    corpo = "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in paragrafos)
    return {"status": "generated", "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{corpo}</div>'}


def _ausente() -> Json:
    """Extensão data-absent-reason para elemento obrigatório que o SIH não tem."""
    return {"extension": [{"url": DADO_AUSENTE, "valueCode": "unknown"}]}


def _recurso(tipo: str, texto: Json, **campos: Any) -> Json:
    return {"resourceType": tipo, "meta": {"profile": [PERFIL[tipo]]}, "text": texto, **campos}


def _br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def _composicao(
    episodio: Episodio, ids: _Ids, condicoes: list, procedimentos: list, gerado_em: datetime
) -> Json:
    secoes = [
        {"title": "Contato Assistencial", "entry": [_ref(ids.contato)]},
        {"title": "Diagnóstico(s)", "entry": [_ref(u) for u, _, _ in condicoes]},
        {"title": "Procedimento(s)", "entry": [_ref(u) for u, _, _ in procedimentos]},
    ]
    texto = _narrativa(
        f"Sumário de Alta do episódio {episodio.episodio_id}: internação de {_br(episodio.dt_inter)} "
        f"a {_br(episodio.dt_saida)}, diagnóstico principal CID-10 {condicoes[0][2]}.",
        AVISO_SINTETICO,
    )
    return _recurso(
        "Composition", texto,
        status="final",
        type=_codificado(f"{CORE}/CodeSystem/tipo-documento-representado-clinico", "sumario-alta"),
        subject=_ref(ids.paciente),
        encounter=_ref(ids.contato),
        date=gerado_em.isoformat(timespec="seconds"),
        author=[_ref(ids.estabelecimento), _ref(ids.profissional)],
        title=TITULO,
        section=secoes,
    )


def _paciente(episodio: Episodio) -> Json:
    nascimento = mapa.nascimento_aproximado(episodio.idade, episodio.cod_idade, episodio.dt_inter)
    nacionalidade = mapa.nacionalidade(episodio.nacional)
    nome = mapa.nome_sintetico(episodio.chave)
    texto = _narrativa(
        f"{nome} (identificação sintética), sexo {mapa.genero(episodio.sexo)}, "
        f"idade na entrada {episodio.idade} (COD_IDADE {episodio.cod_idade}), "
        f"município de residência IBGE {episodio.munic_res}.",
        "A data de nascimento é aproximada (data da entrada menos a idade) e o município de "
        "nascimento repete o de residência; CPF, endereço e filiação não constam do SIH público.",
    )
    return _recurso(
        "Patient", texto,
        extension=[
            {
                "url": f"{RNDS}/StructureDefinition/BRRacaCorEtnia-1.0",
                "extension": [{
                    "url": "race",
                    "valueCodeableConcept": _codificado(f"{RNDS}/CodeSystem/BRRacaCor", mapa.raca_cor(episodio.raca_cor)),
                }],
            },
            {
                "url": f"{CORE}/StructureDefinition/filiacao",
                "extension": [
                    {"url": "tipo", "valueCode": FILIACAO_DESCONHECIDA},
                    {"url": "nome", "valueString": NAO_INFORMADO},
                ],
            },
            {
                "url": f"{RNDS}/StructureDefinition/BRNacionalidade",
                "valueCodeableConcept": _codificado(f"{RNDS}/CodeSystem/BRNacionalidade", nacionalidade),
            },
            {"url": "http://hl7.org/fhir/StructureDefinition/patient-birthPlace", "valueAddress": _local_nascimento(nacionalidade, episodio.munic_res)},
        ],
        identifier=[
            {"system": SISTEMA_CPF, "_value": _ausente()},
            {"system": SISTEMA_CNS, "value": mapa.cns_sintetico(episodio.chave)},
        ],
        name=[{"use": "official", "text": nome}],
        gender=mapa.genero(episodio.sexo),
        birthDate=nascimento.isoformat(),
        address=[_endereco_paciente(episodio.munic_res)],
    )


def _local_nascimento(nacionalidade: str, municipio_residencia: str) -> Json:
    """O SIH não tem o município de nascimento, mas o perfil o exige para brasileiros (invariante
    MunicipioNascimentoSeNacionalidadeBrasileira, binding required, sem data-absent-reason).
    Vai o município de residência como substituto sintético, dito na narrativa do Patient."""
    if nacionalidade == "B":
        return {"city": municipio_residencia, "country": "BRA"}
    return {"_country": _ausente()}


def _endereco_paciente(municipio: str) -> Json:
    tipos = ("tipologradouro", "logradouro", "bairro")
    linhas = [
        {"extension": [{"url": DADO_AUSENTE, "valueCode": "unknown"}, {"url": EXT_TIPO_ENDERECO, "valueCode": t}]}
        for t in tipos
    ]
    return {"use": "home", "_line": linhas, "city": municipio, "country": "BRA"}


def _contato(episodio: Episodio, ids: _Ids, condicoes: list, procedimentos: list) -> Json:
    aihs = ", ".join(f"{i.n_aih} (CNES {i.cnes}, {_br(i.dt_inter)}–{_br(i.dt_saida)})" for i in episodio.internacoes)
    resumo = (
        f"Episódio com {len(episodio.internacoes)} AIH(s) do SIH/SUS: {aihs}. "
        f"Saída com COBRANCA {episodio.cobranca}."
    )
    diagnosticos = [
        {
            "condition": _ref(u),
            "use": _codificado(SISTEMA_CATEGORIA_DIAGNOSTICO, CATEGORIA_PRINCIPAL if n == 0 else CATEGORIA_SECUNDARIO),
        }
        for n, (u, _, _) in enumerate(condicoes)
    ]
    return _recurso(
        "Encounter", _narrativa(resumo),
        extension=[{
            "url": EXT_DESCRICAO_EVOLUCAO,
            "valueString": resumo + " O SIH não traz a evolução clínica; texto gerado a partir das AIHs.",
        }],
        status="finished",
        **{"class": {"system": f"{RNDS}/CodeSystem/BRModalidadeAssistencial", "code": MODALIDADE_HOSPITALAR}},
        priority=_codificado(f"{RNDS}/CodeSystem/BRCaraterAtendimento", mapa.carater_atendimento(episodio.car_int)),
        subject=_ref(ids.paciente),
        participant=[{"individual": _ref(ids.profissional)}],
        period={"start": episodio.dt_inter.isoformat(), "end": episodio.dt_saida.isoformat()},
        diagnosis=diagnosticos + [{"condition": _ref(u)} for u, _, _ in procedimentos],
        hospitalization={
            "admitSource": _codificado(f"{RNDS}/CodeSystem/BRProcedencia", PROCEDENCIA_AUSENTE),
            "dischargeDisposition": _codificado(f"{RNDS}/CodeSystem/BRMotivoDesfecho", mapa.motivo_desfecho(episodio.cobranca)),
        },
        serviceProvider=_ref(ids.estabelecimento),
    )


def _condicoes(episodio: Episodio, ids: _Ids) -> list[tuple[str, Json, str]]:
    """(urn, Condition, código) por CID distinto, na ordem das AIHs; o primeiro é o principal."""
    codigos = list(dict.fromkeys(mapa.cid10(i.diag_princ) for i in episodio.internacoes))
    resultado = []
    for n, codigo in enumerate(codigos):
        categoria = CATEGORIA_PRINCIPAL if n == 0 else CATEGORIA_SECUNDARIO
        rotulo = "principal" if n == 0 else "secundário"
        url = ids.urn(f"diagnostico/{n}")
        condicao = _recurso(
            "Condition", _narrativa(f"Diagnóstico {rotulo}: CID-10 {codigo} (DIAG_PRINC da AIH)."),
            category=[_codificado(SISTEMA_CATEGORIA_DIAGNOSTICO, categoria)],
            code=_codificado(SISTEMA_CID10, codigo),
            subject=_ref(ids.paciente),
            encounter=_ref(ids.contato),
            recordedDate=episodio.dt_saida.isoformat(),
        )
        resultado.append((url, condicao, codigo))
    return resultado


def _procedimentos(episodio: Episodio, ids: _Ids) -> list[tuple[str, Json, str]]:
    """(urn, Procedure, código) por AIH; o perfil só aceita performedDateTime: vai a entrada da AIH."""
    resultado = []
    for n, aih in enumerate(episodio.internacoes):
        codigo = mapa.sigtap(aih.proc_rea)
        url = ids.urn(f"procedimento/{n}")
        procedimento = _recurso(
            "Procedure",
            _narrativa(f"Procedimento SIGTAP {codigo} (PROC_REA da AIH {aih.n_aih}), CNES {aih.cnes}."),
            status="completed",
            code=_codificado(SISTEMA_SIGTAP, codigo),
            subject=_ref(ids.paciente),
            encounter=_ref(ids.contato),
            performedDateTime=aih.dt_inter.isoformat(),
        )
        resultado.append((url, procedimento, codigo))
    return resultado


def _estabelecimento(estab: Estabelecimento) -> Json:
    codigo = mapa.cnes(estab.cnes)
    texto = _narrativa(
        f"Estabelecimento de saúde CNES {codigo}, município IBGE {estab.municipio}.",
        "Nome, telefone e endereço não constam do SIH-RD.",
    )
    linhas = [{"id": "bairro", **_ausente()}, {"id": "logradouro", **_ausente()}]
    return _recurso(
        "Organization", texto,
        identifier=[
            {"system": SISTEMA_CNES, "value": codigo},
            {"system": SISTEMA_CNPJ, "value": estab.cnpj},
        ],
        active=True,
        name=f"Estabelecimento CNES {codigo}",
        alias=[f"CNES {codigo}"],
        telecom=[{"system": "phone", "_value": _ausente()}],
        address=[{
            "_line": linhas,
            "city": estab.municipio,
            "state": estab.municipio[:2],
            "_postalCode": _ausente(),
        }],
    )


def _profissional() -> Json:
    texto = _narrativa("Profissional responsável não identificado: o SIH-RD público não traz o profissional.")
    return _recurso(
        "Practitioner", texto,
        identifier=[{"system": SISTEMA_CPF, "_value": _ausente()}],
        name=[{"use": "official", "text": "Profissional Não Identificado"}],
        telecom=[{"system": "phone", "_value": _ausente()}],
        gender="unknown",
        birthDate=NASCIMENTO_PROFISSIONAL,
    )
