"""Mapeamento dos códigos do SIH-RD para os CodeSystems da RNDS usados no Sumário de Alta (S08).

Funções puras, sem banco. Os códigos de destino vêm dos CodeSystems do pacote
br.go.ses.reds-go 1.0.3 (decisão D02 em docs/decisoes.md). A tabela completa campo do SIH ->
elemento FHIR está no README.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

SEM_REGISTRO = "99"

# COBRANCA (CNV/SAIDAPERM.CNV) -> BRMotivoDesfecho.
# 01 Alta clínica, 02 Alta Voluntária, 04 Evasão, 06 Óbito, 07 Permanência, 08 Retorno,
# 09 Transferência, 99 Sem registro no modelo de informação de origem.
_MOTIVO_DESFECHO = {
    "11": "01", "12": "01", "13": "01", "17": "01", "19": "01",
    "61": "01", "62": "01", "63": "01", "64": "01",
    "14": "02",
    "16": "04",
    "15": "08",
    "21": "07", "22": "07", "23": "07", "24": "07", "25": "07", "26": "07", "27": "07", "28": "07",
    "29": "09", "31": "09", "32": "09",
    "41": "06", "42": "06", "43": "06", "65": "06", "66": "06", "67": "06",
    # 18 (alta por outros motivos) e 51 (encerramento administrativo) não dizem o motivo.
    "18": SEM_REGISTRO, "51": SEM_REGISTRO,
}

# CAR_INT (CNV/CARATEND.CNV) -> BRCaraterAtendimento (01 Eletivo, 02 Urgência).
# Os acidentes e lesões (03–06) são atendimentos de urgência.
_CARATER = {"01": "01", "02": "02", "03": "02", "04": "02", "05": "02", "06": "02"}

# SEXO no SIH-RD: 1 masculino, 3 feminino (0 e 9: ignorado).
_SEXO = {"1": "male", "3": "female"}

# RACA_COR do SIH-RD usa os mesmos códigos do BRRacaCor.
_RACA_COR = frozenset({"01", "02", "03", "04", "05", "99"})

# NACIONAL do SIH-RD é o código do país; 010 é o Brasil.
NACIONAL_BRASIL = "010"

# COD_IDADE: 2 dias, 3 meses, 4 anos, 5 anos acima de 100 (IDADE = anos - 100).
_COD_IDADE_ANOS, _COD_IDADE_CENTENARIO = "4", "5"
_COD_IDADE_DIAS, _COD_IDADE_MESES = "2", "3"
ANOS_CENTENARIO = 100
DIAS_POR_MES = 30

_CID10 = re.compile(r"[A-Z][0-9]{2}[0-9A-Z]?")
_SIGTAP = re.compile(r"[0-9]{10}")
_CNES = re.compile(r"[0-9]{7}")
_CNPJ = re.compile(r"[0-9]{14}")


def motivo_desfecho(cobranca: str | None) -> str:
    return _MOTIVO_DESFECHO.get((cobranca or "").strip(), SEM_REGISTRO)


def carater_atendimento(car_int: str | None) -> str:
    return _CARATER.get((car_int or "").strip(), SEM_REGISTRO)


def genero(sexo: str | None) -> str:
    return _SEXO.get((sexo or "").strip(), "unknown")


def raca_cor(codigo: str | None) -> str:
    codigo = (codigo or "").strip()
    return codigo if codigo in _RACA_COR else SEM_REGISTRO


def nacionalidade(nacional: str | None) -> str:
    """BRNacionalidade: B (brasileiro) ou E (estrangeiro). O SIH não distingue o naturalizado."""
    return "B" if (nacional or "").strip() == NACIONAL_BRASIL else "E"


def cid10(codigo: str) -> str:
    """CID-10 do SIH ("I500", às vezes "I50.0" em outras fontes) no formato do BRCID10 (sem ponto)."""
    normal = codigo.strip().upper().replace(".", "")
    if not _CID10.fullmatch(normal):
        raise ValueError(f"Código CID-10 inválido: {codigo!r}")
    return normal


def sigtap(codigo: str) -> str:
    normal = codigo.strip()
    if not _SIGTAP.fullmatch(normal):
        raise ValueError(f"Procedimento SIGTAP precisa de 10 dígitos: {codigo!r}")
    return normal


def cnes(codigo: str) -> str:
    normal = codigo.strip()
    if not _CNES.fullmatch(normal):
        raise ValueError(f"CNES precisa de 7 dígitos: {codigo!r}")
    return normal


def cnpj_valido(codigo: str | None) -> str | None:
    """CNPJ com 14 dígitos e não zerado; None se ausente ou inválido."""
    normal = (codigo or "").strip()
    if _CNPJ.fullmatch(normal) and set(normal) != {"0"}:
        return normal
    return None


def nascimento_aproximado(idade: int, cod_idade: str, referencia: date) -> date:
    """Data de nascimento sintética: a data de referência (entrada) menos a idade do SIH.

    O banco não guarda NASC em claro (S06). A data resultante só preserva a idade na entrada;
    dia e mês são os da internação, não os reais.
    """
    unidade = (cod_idade or "").strip()
    if unidade == _COD_IDADE_DIAS:
        return referencia - timedelta(days=idade)
    if unidade == _COD_IDADE_MESES:
        return referencia - timedelta(days=idade * DIAS_POR_MES)
    anos = idade + ANOS_CENTENARIO if unidade == _COD_IDADE_CENTENARIO else idade
    if unidade not in (_COD_IDADE_ANOS, _COD_IDADE_CENTENARIO):
        anos = 0
    return _menos_anos(referencia, anos)


def _menos_anos(dia: date, anos: int) -> date:
    try:
        return dia.replace(year=dia.year - anos)
    except ValueError:  # 29/02 em ano não bissexto
        return dia.replace(year=dia.year - anos, day=28)


def cns_sintetico(chave: str) -> str:
    """CNS sintético de 15 dígitos derivado da chave de linkage (hash com sal).

    Começa com 0, que nenhum CNS real usa (definitivos começam com 1 ou 2; provisórios com
    7, 8 ou 9), então nunca coincide com o cartão de uma pessoa. A mesma chave gera o mesmo
    CNS em todos os episódios do paciente.
    """
    resumo = hashlib.sha256(f"readmissao-sus|cns|{chave}".encode()).hexdigest()
    digitos = "".join(str(int(c, 16) % 10) for c in resumo[:14])
    return "0" + digitos


def nome_sintetico(chave: str) -> str:
    return "Paciente Sintético " + hashlib.sha256(f"readmissao-sus|nome|{chave}".encode()).hexdigest()[:8]
