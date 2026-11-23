"""Banco DuckDB do SIH-RD (história S06): staging, internações e coorte a partir do SQL em sql/.

O SQL versionado em sql/ é a única fonte das regras de episódio (deduplicação por N_AIH,
IDENT = 5 como continuação, óbito) e da coorte. linkage_viabilidade (S03) usa os mesmos
arquivos 01 e 02, só que num banco em memória e com sal vazio.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from readmissao_sus import dicionario_sih as dic
from readmissao_sus.cobertura import Cobertura, calcular_cobertura

DIR_SQL = Path(__file__).resolve().parents[2] / "sql"
SQL_INTERNACOES = ("01_staging.sql", "02_internacao.sql")
SQL_COORTE = ("03_coorte.sql",)
COLUNAS_FONTE = (
    "N_AIH", "IDENT", "ANO_CMPT", "MES_CMPT", "NASC", "SEXO", "CEP", "MUNIC_RES", "IDADE",
    "COD_IDADE", "DT_INTER", "DT_SAIDA", "DIAG_PRINC", "PROC_REA", "CNES", "CAR_INT",
    "COBRANCA", "MORTE", "UTI_MES_TO",
)
VARIAVEL_SAL = "READMISSAO_SAL_CHAVE"
BYTES_SAL = 32
COMPETENCIAS_IDENT1 = "(select dt_saida, competencia from stg_aih where ident = '1')"


@dataclass(frozen=True)
class Construcao:
    cobertura: Cobertura
    filtros: list[tuple[int, str, int, int, int]]
    detalhes: dict[str, list[tuple[str, int]]]


def obter_sal(arquivo: Path) -> str:
    """Sal da chave de linkage: variável de ambiente, senão arquivo local (criado se faltar).

    O arquivo fica em data/, fora do git. Trocar o sal muda todas as chaves do banco; nada fora
    do banco depende delas.
    """
    do_ambiente = os.environ.get(VARIAVEL_SAL, "").strip()
    if do_ambiente:
        return do_ambiente
    if arquivo.exists():
        sal = arquivo.read_text(encoding="utf-8").strip()
        if not sal:
            raise ValueError(f"Arquivo de sal vazio: {arquivo}. Apague-o para gerar outro.")
        return sal
    sal = secrets.token_hex(BYTES_SAL)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(sal + "\n", encoding="utf-8")
    return sal


def executar_sql(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute((DIR_SQL / nome).read_text(encoding="utf-8"))


def carregar_dicionario(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        "create or replace table dic_cobranca "
        "(codigo varchar primary key, descricao varchar, obito boolean, transferencia boolean)"
    )
    con.executemany(
        "insert into dic_cobranca values (?, ?, ?, ?)",
        [(c, d, c in dic.COBRANCA_OBITO, c in dic.COBRANCA_TRANSFERENCIA)
         for c, d in sorted(dic.COBRANCA.items())],
    )


def criar_fonte(con: duckdb.DuckDBPyConnection, relacao: str, completar: bool = False) -> None:
    """Cria a view temporária rd_bruto com as COLUNAS_FONTE lidas de `relacao`.

    Sem `completar`, falta de coluna é erro. Com `completar`, as ausentes viram texto nulo
    (a S03 só precisa de parte delas).
    """
    existentes = {c[0] for c in con.execute(f"describe select * from {relacao}").fetchall()}
    faltando = [c for c in COLUNAS_FONTE if c not in existentes]
    if faltando and not completar:
        raise ValueError(f"Colunas ausentes em {relacao}: {', '.join(faltando)}")
    colunas = ", ".join(
        f"{c}::varchar as {c}" if c in existentes else f"null::varchar as {c}"
        for c in COLUNAS_FONTE
    )
    con.execute(f"create or replace temp view rd_bruto as select {colunas} from {relacao}")


def preparar_internacoes(
    con: duckdb.DuckDBPyConnection, relacao: str, sal: str, completar: bool = False
) -> None:
    """Cria dic_cobranca, stg_aih e internacao na conexão a partir de `relacao` (texto bruto)."""
    con.execute("set variable sal_chave = ?", [sal])
    carregar_dicionario(con)
    criar_fonte(con, relacao, completar)
    for nome in SQL_INTERNACOES:
        executar_sql(con, nome)


def montar_coorte(con: duckdb.DuckDBPyConnection, inicio: date, corte: date) -> None:
    """Cria coorte, coorte_filtros e coorte_detalhes (precisa de stg_aih e internacao)."""
    con.execute("set variable inicio_indice = ?", [inicio])
    con.execute("set variable corte_indice = ?", [corte])
    for nome in SQL_COORTE:
        executar_sql(con, nome)


def construir_banco(destino: Path, arquivos: list[Path], sal: str) -> Construcao:
    """Recria `destino` do zero a partir dos Parquet.

    Monta num arquivo temporário ao lado e só substitui o banco antigo no fim, para que uma
    falha no meio não deixe um banco pela metade.
    """
    if not arquivos:
        raise ValueError("Nenhum arquivo Parquet informado.")
    temporario = destino.with_name(destino.name + ".novo")
    _apagar_banco(temporario)
    con = duckdb.connect(str(temporario))
    try:
        lista = ", ".join(f"'{p.as_posix()}'" for p in arquivos)
        con.execute(
            f"create temp view parquet as select * from read_parquet([{lista}], union_by_name = true)"
        )
        preparar_internacoes(con, "parquet", sal)
        cobertura = calcular_cobertura(con, COMPETENCIAS_IDENT1)
        montar_coorte(con, cobertura.inicio, cobertura.limite_indice)
        _gravar_parametros(con, cobertura)
        resultado = ler_construcao(con, cobertura)
        con.execute("checkpoint")
    finally:
        con.close()
    _apagar_banco(destino)
    temporario.replace(destino)
    return resultado


def ler_construcao(con: duckdb.DuckDBPyConnection, cobertura: Cobertura) -> Construcao:
    filtros = con.execute(
        "select ordem, etapa, antes, removidas, depois from coorte_filtros order by ordem"
    ).fetchall()
    detalhes: dict[str, list[tuple[str, int]]] = {}
    for secao, item, linhas in con.execute(
        "select secao, item, linhas from coorte_detalhes order by secao, ordem"
    ).fetchall():
        detalhes.setdefault(secao, []).append((item, linhas))
    return Construcao(cobertura, filtros, detalhes)


def _gravar_parametros(con: duckdb.DuckDBPyConnection, cobertura: Cobertura) -> None:
    con.execute(
        "create or replace table coorte_parametros as select ?::varchar as ultima_competencia, "
        "?::date as inicio_indice, ?::date as corte_indice, ?::date as fim_cobertura",
        [cobertura.ultima_competencia, cobertura.inicio, cobertura.limite_indice, cobertura.fim],
    )


def _apagar_banco(caminho: Path) -> None:
    for arquivo in (caminho, caminho.with_name(caminho.name + ".wal")):
        arquivo.unlink(missing_ok=True)
