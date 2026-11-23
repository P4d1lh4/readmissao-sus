"""Leitura de episódios do banco (sih.duckdb) para o Sumário de Alta (S08).

Separa o acesso a dados da construção do Bundle (`fhir_sumario.montar_bundle`, pura).
O banco não guarda o CNPJ nem o município do hospital, nem raça/cor e nacionalidade do
paciente; esses campos vêm direto dos Parquet do SIH-RD, filtrados pelas AIHs do episódio.
NASC e CEP nunca são lidos.

A amostra (`selecionar_amostra`) é determinística: em cada estrato, os episódios são
ordenados por md5(episodio_id) e entram os primeiros que passam no `filtro`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import duckdb

from readmissao_sus import sih_fhir_mapa as mapa
from readmissao_sus.fhir_sumario import Episodio, Estabelecimento, Internacao

COLUNAS_PARQUET = ("N_AIH", "IDENT", "ANO_CMPT", "MES_CMPT", "CGC_HOSP", "CNPJ_MANT", "MUNIC_MOV", "RACA_COR", "NACIONAL")
CANDIDATOS_POR_VAGA = 20


@dataclass(frozen=True)
class Estrato:
    nome: str
    condicao: str  # SQL sobre coorte_episodio
    quantidade: int


SIMPLES = "n_internacoes = 1 and not longa_permanencia"
ESTRATOS: tuple[Estrato, ...] = (
    Estrato("simples, eletivo, masculino", f"{SIMPLES} and car_int = '01' and sexo = '1'", 2),
    Estrato("simples, eletivo, feminino", f"{SIMPLES} and car_int = '01' and sexo = '3'", 2),
    Estrato("simples, urgência, masculino", f"{SIMPLES} and car_int = '02' and sexo = '1'", 2),
    Estrato("simples, urgência, feminino", f"{SIMPLES} and car_int = '02' and sexo = '3'", 2),
    Estrato("simples, acidente (CAR_INT 05/06)", f"{SIMPLES} and car_int in ('05', '06')", 2),
    Estrato("simples, menor de 1 ano", f"{SIMPLES} and cod_idade in ('2', '3')", 1),
    Estrato("longa permanência (AIH 5)", "n_internacoes = 1 and longa_permanencia", 1),
    Estrato("saída final por transferência", "n_internacoes = 1 and cobranca in ('29', '31', '32')", 1),
    Estrato(
        "transferência entre hospitais, urgência",
        "ligacoes_transferencia > 0 and ligacoes_permanencia = 0 and n_hospitais > 1 and car_int = '02'", 2,
    ),
    Estrato(
        "transferência entre hospitais, eletivo",
        "ligacoes_transferencia > 0 and ligacoes_permanencia = 0 and n_hospitais > 1 and car_int = '01'", 1,
    ),
    Estrato("permanência, urgência", "ligacoes_permanencia > 0 and ligacoes_transferencia = 0 and car_int = '02'", 2),
    Estrato("permanência, eletivo", "ligacoes_permanencia > 0 and ligacoes_transferencia = 0 and car_int = '01'", 1),
    Estrato("transferência e permanência", "ligacoes_permanencia > 0 and ligacoes_transferencia > 0", 1),
)

SQL_MEMBROS = """
select m.episodio_id, i.n_aih, i.cnes, i.dt_inter, i.dt_saida, i.diag_princ, i.proc_rea, i.cobranca
from episodio_membro m join internacao i using (n_aih)
where m.episodio_id in (select unnest(?::varchar[]))
order by m.episodio_id, m.posicao
"""
SQL_EPISODIOS = """
select episodio_id, chave, sexo, idade, cod_idade, munic_res, car_int
from episodio where episodio_id in (select unnest(?::varchar[]))
"""


@dataclass(frozen=True)
class CamposParquet:
    cnpj: str | None
    munic_mov: str | None
    raca_cor: str | None
    nacional: str | None


def ler_campos_parquet(
    con: duckdb.DuckDBPyConnection, parquets: Sequence[Path], aihs: Sequence[str]
) -> dict[str, CamposParquet]:
    """CNPJ (CGC_HOSP, senão CNPJ_MANT), MUNIC_MOV, RACA_COR e NACIONAL por N_AIH (IDENT 1,
    competência mais recente, a mesma regra de 02_internacao.sql)."""
    if not aihs:
        return {}
    lista = ", ".join(f"'{p.as_posix()}'" for p in parquets)
    colunas = ", ".join(COLUNAS_PARQUET)
    linhas = con.execute(
        f"""
        select N_AIH, CGC_HOSP, CNPJ_MANT, MUNIC_MOV, RACA_COR, NACIONAL
        from (select {colunas} from read_parquet([{lista}], union_by_name = true))
        where IDENT = '1' and N_AIH in (select unnest(?::varchar[]))
        qualify row_number() over (partition by N_AIH order by ANO_CMPT desc, MES_CMPT desc) = 1
        """,
        [list(aihs)],
    ).fetchall()
    return {
        n_aih: CamposParquet(mapa.cnpj_valido(cgc) or mapa.cnpj_valido(mant), munic, raca, nacional)
        for n_aih, cgc, mant, munic, raca, nacional in linhas
    }


def ler_episodios(
    con: duckdb.DuckDBPyConnection, parquets: Sequence[Path], ids: Sequence[str], pular_incompletos: bool = False
) -> list[Episodio]:
    """Episódios na ordem de `ids`. Falha se algum não existir; sem CNPJ ou município do
    hospital nos Parquet, falha ou (com `pular_incompletos`) deixa o episódio de fora."""
    membros: dict[str, list[Internacao]] = {}
    for episodio_id, *campos in con.execute(SQL_MEMBROS, [list(ids)]).fetchall():
        membros.setdefault(episodio_id, []).append(Internacao(*campos))
    cabecalhos = {linha[0]: linha for linha in con.execute(SQL_EPISODIOS, [list(ids)]).fetchall()}
    faltando = [i for i in ids if i not in cabecalhos or i not in membros]
    if faltando:
        raise KeyError(f"Episódios ausentes no banco: {', '.join(faltando)}")
    aihs = [aih.n_aih for lista in membros.values() for aih in lista]
    extras = ler_campos_parquet(con, parquets, aihs)
    episodios = []
    for i in ids:
        try:
            episodios.append(_episodio(cabecalhos[i], tuple(membros[i]), extras))
        except ValueError:
            if not pular_incompletos:
                raise
    return episodios


def _episodio(cabecalho: tuple, internacoes: tuple[Internacao, ...], extras: dict[str, CamposParquet]) -> Episodio:
    episodio_id, chave, sexo, idade, cod_idade, munic_res, car_int = cabecalho
    primeira, alta = extras.get(internacoes[0].n_aih), extras.get(internacoes[-1].n_aih)
    if primeira is None or alta is None or alta.cnpj is None or not alta.munic_mov:
        raise ValueError(f"Episódio {episodio_id}: AIH sem CNPJ ou MUNIC_MOV nos Parquet.")
    return Episodio(
        episodio_id=episodio_id, chave=chave, sexo=sexo, idade=idade, cod_idade=cod_idade,
        munic_res=munic_res, raca_cor=primeira.raca_cor, nacional=primeira.nacional, car_int=car_int,
        internacoes=internacoes,
        estabelecimento_alta=Estabelecimento(internacoes[-1].cnes, alta.cnpj, alta.munic_mov),
    )


def candidatos(con: duckdb.DuckDBPyConnection, estrato: Estrato, limite: int) -> list[str]:
    return [
        linha[0]
        for linha in con.execute(
            f"select episodio_id from coorte_episodio where {estrato.condicao} "
            "order by md5(episodio_id) limit ?",
            [limite],
        ).fetchall()
    ]


def selecionar_amostra(
    con: duckdb.DuckDBPyConnection,
    parquets: Sequence[Path],
    filtro: Callable[[Episodio], bool],
    estratos: Sequence[Estrato] = ESTRATOS,
) -> list[tuple[Estrato, Episodio]]:
    """Amostra estratificada: `quantidade` episódios por estrato, sem repetir episódio."""
    escolhidos: list[tuple[Estrato, Episodio]] = []
    vistos: set[str] = set()
    for estrato in estratos:
        ids = [i for i in candidatos(con, estrato, estrato.quantidade * CANDIDATOS_POR_VAGA) if i not in vistos]
        lidos = ler_episodios(con, parquets, ids, pular_incompletos=True)
        aceitos = [e for e in lidos if filtro(e)][: estrato.quantidade]
        if len(aceitos) < estrato.quantidade:
            raise ValueError(f"Estrato '{estrato.nome}': só {len(aceitos)} episódio(s) aceito(s).")
        escolhidos += [(estrato, e) for e in aceitos]
        vistos.update(e.episodio_id for e in aceitos)
    return escolhidos

