"""Leitura de DBF/DBC do DATASUS e conversão para Parquet.

A camada bruta guarda todos os campos como texto, sem espaços nas pontas e com
vazio virando nulo. O tipo declarado no DBF (ex.: char(13), numeric(3)) fica nos
metadados do Parquet, para a tipagem ser feita depois de forma explícita.
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyreaddbc import readdbc

ENCODING_DATASUS = "latin-1"
CHAVE_METADADOS = b"dbf_campos"
_TAM_CABECALHO = 32
_TAM_DESCRITOR = 32
_FIM_DESCRITORES = 0x0D
_MARCA_APAGADO = b"*"


@dataclass(frozen=True)
class CampoDbf:
    nome: str
    tipo: str
    tamanho: int
    decimais: int

    @property
    def tipo_legivel(self) -> str:
        nomes = {"C": "char", "N": "numeric", "F": "float", "D": "date", "L": "logical"}
        base = nomes.get(self.tipo, self.tipo)
        if self.decimais:
            return f"{base}({self.tamanho},{self.decimais})"
        return f"{base}({self.tamanho})"


def ler_dbf(caminho: Path) -> tuple[pd.DataFrame, list[CampoDbf]]:
    """Lê um DBF inteiro como bytes de largura fixa. Registros apagados são descartados."""
    dados = Path(caminho).read_bytes()
    n_registros, tam_cabecalho, tam_registro = struct.unpack("<IHH", dados[4:12])
    campos = _ler_descritores(dados, tam_cabecalho)

    tipo_registro = np.dtype(
        [("_apagado", "S1")] + [(c.nome, f"S{c.tamanho}") for c in campos]
    )
    if tipo_registro.itemsize != tam_registro:
        raise ValueError(
            f"{caminho}: tamanho de registro {tam_registro} não bate com os campos ({tipo_registro.itemsize})"
        )
    fim = tam_cabecalho + n_registros * tam_registro
    registros = np.frombuffer(dados[tam_cabecalho:fim], dtype=tipo_registro, count=n_registros)
    registros = registros[registros["_apagado"] != _MARCA_APAGADO]

    bruto = pd.DataFrame(
        {c.nome: np.char.decode(registros[c.nome], ENCODING_DATASUS) for c in campos}
    )
    return normalizar_registros(bruto), campos


def normalizar_registros(bruto: pd.DataFrame) -> pd.DataFrame:
    """Conversão da camada bruta: texto sem espaços nas pontas, vazio vira nulo.

    Não altera o DataFrame recebido.
    """
    colunas = {}
    for nome in bruto.columns:
        texto = bruto[nome].astype("string").str.strip()
        colunas[nome] = texto.mask(texto == "", pd.NA)
    return pd.DataFrame(colunas, index=bruto.index).reset_index(drop=True)


def dbc_para_parquet(dbc: Path, parquet: Path) -> int:
    """Descompacta o DBC, lê o DBF e grava o Parquet de forma atômica. Devolve o nº de linhas."""
    parquet.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        dbf = Path(tmp) / (dbc.stem + ".dbf")
        readdbc.dbc2dbf(str(dbc), str(dbf))
        df, campos = ler_dbf(dbf)
    salvar_parquet(df, campos, parquet)
    return len(df)


def salvar_parquet(df: pd.DataFrame, campos: list[CampoDbf], destino: Path) -> None:
    tabela = pa.Table.from_pandas(df, preserve_index=False)
    metadados = dict(tabela.schema.metadata or {})
    metadados[CHAVE_METADADOS] = json.dumps([asdict(c) for c in campos]).encode()
    tabela = tabela.replace_schema_metadata(metadados)
    parcial = destino.with_name(destino.name + ".part")
    pq.write_table(tabela, parcial)
    os.replace(parcial, destino)


def ler_campos_parquet(caminho: Path) -> list[CampoDbf]:
    """Campos DBF originais gravados nos metadados do Parquet."""
    metadados = pq.read_schema(caminho).metadata or {}
    if CHAVE_METADADOS not in metadados:
        return []
    return [CampoDbf(**c) for c in json.loads(metadados[CHAVE_METADADOS])]


def _ler_descritores(dados: bytes, tam_cabecalho: int) -> list[CampoDbf]:
    campos = []
    pos = _TAM_CABECALHO
    while pos < tam_cabecalho and dados[pos] != _FIM_DESCRITORES:
        descritor = dados[pos : pos + _TAM_DESCRITOR]
        nome = descritor[:11].split(b"\x00", 1)[0].decode("ascii").strip()
        campos.append(
            CampoDbf(
                nome=nome,
                tipo=chr(descritor[11]),
                tamanho=descritor[16],
                decimais=descritor[17],
            )
        )
        pos += _TAM_DESCRITOR
    return campos
