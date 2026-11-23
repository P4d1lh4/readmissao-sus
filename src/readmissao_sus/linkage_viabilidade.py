"""Viabilidade do linkage determinístico de internações do SIH-RD (história S03).

A chave é NASC + SEXO + CEP + MUNIC_RES. Logo depois de montada, ela vira um hash SHA-256 e os
campos originais são descartados: as tabelas intermediárias (só em memória) guardam o hash e
algumas marcas booleanas de qualidade da chave. O que sai daqui são apenas contagens agregadas.

Tratamentos (detalhados em docs/decisoes.md):
- a internação é definida pelas datas DT_INTER/DT_SAIDA, não pela competência do arquivo;
- AIHs IDENT=1 são deduplicadas por N_AIH (fica a da competência mais recente);
- AIHs IDENT=5 (longa permanência) são continuação da AIH IDENT=1 de mesmo N_AIH: estendem a
  saída e trazem o motivo de saída final; nunca são internação-índice nem readmissão;
- altas-índice cujos 30 dias seguintes passam da cobertura completa dos dados são censuradas.

As regras de episódio vêm do SQL versionado em sql/ (01_staging.sql e 02_internacao.sql), o
mesmo que monta data/sih.duckdb (banco.py). Aqui ele roda em memória e com sal vazio.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from readmissao_sus import dicionario_sih as dic
from readmissao_sus.banco import preparar_internacoes
from readmissao_sus.cobertura import JANELA_DIAS, LIMIAR_COMPLETUDE, Cobertura, calcular_cobertura

__all__ = ["JANELA_DIAS", "LIMIAR_COMPLETUDE", "Cobertura", "analisar", "analisar_dataframe"]

DIAS_CONTIGUIDADE = 1
COBRANCA_PERMANENCIA = frozenset({"21", "22", "23", "24", "25", "26", "27", "28"})
COLUNAS_BRUTAS = (
    "N_AIH", "IDENT", "NASC", "SEXO", "CEP", "MUNIC_RES", "DT_INTER", "DT_SAIDA",
    "COBRANCA", "MORTE", "ANO_CMPT", "MES_CMPT", "CNES",
)
FAIXAS_POR_CHAVE = ((1, 1), (2, 2), (3, 3), (4, 4), (5, 9), (10, None))
FAIXAS_GAP = ((0, 1), (2, 7), (8, 30))
QUANTIS_PERMANENCIA = (0.25, 0.5, 0.75, 0.9, 0.95, 0.99)


@dataclass(frozen=True)
class Preparo:
    linhas_brutas: int
    ident1_linhas: int
    ident1_duplicadas: int
    ident5_linhas: int
    ident5_aih_distintas: int
    ident5_orfas: int
    linhas_n_aih_repetido: int
    datas_invalidas: int
    internacoes: int


@dataclass(frozen=True)
class Chaves:
    internacoes: int
    chaves: int
    distribuicao: dict[str, int]
    chaves_multiplas: int
    chaves_colidentes: int
    internacoes_em_colisao: int
    sobrepostas: int
    sobrepostas_mesmo_cnes: int
    sobrepostas_menor_1_ano: int


@dataclass(frozen=True)
class GrupoPlaceholder:
    nome: str
    chaves: int
    chaves_multiplas: int
    chaves_colidentes: int


@dataclass(frozen=True)
class Readmissao:
    altas_indice: int
    obitos_excluidos: int
    censuradas: int
    readmitidas: int
    por_gap: dict[str, int]
    contiguas_transferencia: int
    contiguas_permanencia: int

    @property
    def taxa_bruta(self) -> float:
        return _razao(self.readmitidas, self.altas_indice)

    @property
    def taxa_sem_transferencia(self) -> float:
        n = self.contiguas_transferencia
        return _razao(self.readmitidas - n, self.altas_indice - n)

    @property
    def taxa_sem_transferencia_permanencia(self) -> float:
        n = self.contiguas_transferencia + self.contiguas_permanencia
        return _razao(self.readmitidas - n, self.altas_indice - n)


@dataclass(frozen=True)
class PlanoB:
    saidas: int
    obitos: int
    permanencia_media: float
    permanencia_quantis: dict[float, float]
    acima_de: dict[int, int]

    @property
    def taxa_obito(self) -> float:
        return _razao(self.obitos, self.saidas)


@dataclass(frozen=True)
class Resultado:
    preparo: Preparo
    cobertura: Cobertura
    chaves: Chaves
    placeholders: list[GrupoPlaceholder]
    readmissao: Readmissao
    readmissao_cep_especifico: Readmissao
    plano_b: PlanoB


def analisar(con: duckdb.DuckDBPyConnection, relacao_bruta: str) -> Resultado:
    """Roda a análise inteira sobre uma relação com as COLUNAS_BRUTAS (todas texto)."""
    preparo = preparar(con, relacao_bruta)
    cobertura = calcular_cobertura(con)
    marcar_sobreposicoes(con)
    return Resultado(
        preparo=preparo,
        cobertura=cobertura,
        chaves=medir_chaves(con),
        placeholders=medir_placeholders(con),
        readmissao=medir_readmissao(con, cobertura),
        readmissao_cep_especifico=medir_readmissao(con, cobertura, "not cep_generico"),
        plano_b=medir_plano_b(con, cobertura),
    )


def analisar_dataframe(df: pd.DataFrame) -> Resultado:
    con = duckdb.connect()
    con.register("bruto_df", df)
    return analisar(con, "bruto_df")


def preparar(con: duckdb.DuckDBPyConnection, relacao_bruta: str) -> Preparo:
    """Cria `competencias` (sem chave) e `internacoes` (chave só como hash) na conexão."""
    preparar_internacoes(con, relacao_bruta, sal="", completar=True)
    con.execute(
        """
        create or replace temp table competencias as
        select dt_saida, competencia from stg_aih where ident = '1'
        """
    )
    con.execute(
        "create or replace temp table continuacao as "
        "select distinct n_aih as N_AIH from stg_aih where ident = '5'"
    )
    con.execute(
        """
        create or replace temp table internacoes as
        select n_aih, chave, cep_generico, cep_zerado, nasc_0101, nasc_antes_1900 as nasc_antigo,
               cnes, menor_1_ano, dt_inter, dt_saida, cobranca, obito
        from internacao
        """
    )
    for tabela in ("internacao", "stg_aih", "dic_cobranca"):
        con.execute(f"drop table {tabela}")
    con.execute("drop view rd_bruto")
    return _contagens_preparo(con, relacao_bruta)


def _contagens_preparo(con: duckdb.DuckDBPyConnection, relacao_bruta: str) -> Preparo:
    linhas, n_aih_distintas, i1, i1_distintas, i5, i5_distintas = con.execute(
        f"""
        select count(*), count(distinct N_AIH),
               count(*) filter (where IDENT = '1'), count(distinct N_AIH) filter (where IDENT = '1'),
               count(*) filter (where IDENT = '5'), count(distinct N_AIH) filter (where IDENT = '5')
        from {relacao_bruta}
        """
    ).fetchone()
    orfas = con.execute(
        f"""
        select count(*) from continuacao
        where N_AIH not in (select N_AIH from {relacao_bruta} where IDENT = '1')
        """
    ).fetchone()[0]
    internacoes = con.execute("select count(*) from internacoes").fetchone()[0]
    return Preparo(
        linhas_brutas=linhas,
        ident1_linhas=i1,
        ident1_duplicadas=i1 - i1_distintas,
        ident5_linhas=i5,
        ident5_aih_distintas=i5_distintas,
        ident5_orfas=orfas,
        linhas_n_aih_repetido=linhas - n_aih_distintas,
        datas_invalidas=i1_distintas - internacoes,
        internacoes=internacoes,
    )


def marcar_sobreposicoes(con: duckdb.DuckDBPyConnection) -> None:
    """Marca a internação que começa antes de terminar outra da mesma chave (pessoas diferentes).

    `mesmo_cnes_anterior` compara com a internação imediatamente anterior da chave (aproximação:
    serve para separar sobreposições no mesmo hospital, que podem ser AIHs da mesma pessoa).
    """
    con.execute(
        """
        create or replace temp table internacoes as
        select *,
               coalesce(dt_inter < max(dt_saida) over anteriores, false) as sobreposta,
               coalesce(cnes = lag(cnes) over ordem, false) as mesmo_cnes_anterior
        from internacoes
        window ordem as (partition by chave order by dt_inter, dt_saida, n_aih),
               anteriores as (ordem rows between unbounded preceding and 1 preceding)
        """
    )


def medir_chaves(con: duckdb.DuckDBPyConnection) -> Chaves:
    con.execute(
        """
        create or replace temp table por_chave as
        select chave, count(*) as n, bool_or(sobreposta) as colidente,
               any_value(cep_generico) as cep_generico, any_value(cep_zerado) as cep_zerado,
               any_value(nasc_0101) as nasc_0101, any_value(nasc_antigo) as nasc_antigo
        from internacoes group by chave
        """
    )
    distribuicao = {}
    for minimo, maximo in FAIXAS_POR_CHAVE:
        teto = maximo if maximo is not None else 10**9
        distribuicao[_rotulo_faixa(minimo, maximo)] = con.execute(
            "select count(*) from por_chave where n between ? and ?", [minimo, teto]
        ).fetchone()[0]
    internacoes, chaves, multiplas, colidentes, em_colisao = con.execute(
        """
        select sum(n), count(*), count(*) filter (where n > 1),
               count(*) filter (where colidente), coalesce(sum(n) filter (where colidente), 0)
        from por_chave
        """
    ).fetchone()
    sobrepostas, mesmo_cnes, menor_1_ano = con.execute(
        """
        select count(*), count(*) filter (where mesmo_cnes_anterior),
               count(*) filter (where menor_1_ano)
        from internacoes where sobreposta
        """
    ).fetchone()
    return Chaves(
        int(internacoes or 0), chaves, distribuicao, multiplas, colidentes, int(em_colisao),
        sobrepostas, mesmo_cnes, menor_1_ano,
    )


def medir_placeholders(con: duckdb.DuckDBPyConnection) -> list[GrupoPlaceholder]:
    grupos = (
        ("Todas as chaves", "true"),
        ("CEP terminado em 000 (genérico da localidade)", "cep_generico"),
        ("CEP específico (não termina em 000)", "not cep_generico"),
        ("CEP 00000000", "cep_zerado"),
        ("NASC em 01/01", "nasc_0101"),
        ("NASC antes de 1900", "nasc_antigo"),
        ("Sem nenhum placeholder", "not (cep_generico or cep_zerado or nasc_0101 or nasc_antigo)"),
    )
    resultado = []
    for nome, filtro in grupos:
        chaves, multiplas, colidentes = con.execute(
            f"""
            select count(*), count(*) filter (where n > 1), count(*) filter (where colidente)
            from por_chave where {filtro}
            """
        ).fetchone()
        resultado.append(GrupoPlaceholder(nome, chaves, multiplas, colidentes))
    return resultado


def medir_readmissao(
    con: duckdb.DuckDBPyConnection, cobertura: Cobertura, filtro: str = "true"
) -> Readmissao:
    """Readmissão: próxima internação da mesma chave com início em [saída, saída + 30 dias].

    Internações sobrepostas não contam (começam antes da saída). Readmissões "contíguas"
    (início no dia da saída ou no seguinte) após saída por transferência ou permanência são
    medidas à parte: são continuação do mesmo episódio, não volta do paciente.
    """
    transferencia = _lista_sql(dic.COBRANCA_TRANSFERENCIA)
    permanencia = _lista_sql(COBRANCA_PERMANENCIA)
    periodo = [cobertura.inicio, cobertura.limite_indice]
    obitos, censuradas = con.execute(
        f"""
        select count(*) filter (where obito and dt_saida between ? and ?),
               count(*) filter (where not obito and dt_saida > ?)
        from internacoes where {filtro}
        """,
        [*periodo, cobertura.limite_indice],
    ).fetchone()
    con.execute(
        f"""
        create or replace temp table indice as
        with idx as (
            select * from internacoes
            where {filtro} and not obito and dt_saida between ? and ?
        ),
        prox as (
            select i.n_aih, min(r.dt_inter) as prox_inter
            from idx i join internacoes r
              on r.chave = i.chave and r.n_aih <> i.n_aih
             and r.dt_inter >= i.dt_saida and r.dt_inter <= i.dt_saida + {JANELA_DIAS}
             and (r.dt_inter, r.dt_saida, r.n_aih) > (i.dt_inter, i.dt_saida, i.n_aih)
            group by i.n_aih
        )
        select idx.cobranca, prox.prox_inter - idx.dt_saida as gap
        from idx left join prox using (n_aih)
        """,
        periodo,
    )
    altas, readmitidas, transf, perm = con.execute(
        f"""
        select count(*), count(gap),
               count(*) filter (where gap <= {DIAS_CONTIGUIDADE} and cobranca in ({transferencia})),
               count(*) filter (where gap <= {DIAS_CONTIGUIDADE} and cobranca in ({permanencia}))
        from indice
        """
    ).fetchone()
    por_gap = {
        _rotulo_faixa(a, b): con.execute(
            "select count(*) from indice where gap between ? and ?", [a, b]
        ).fetchone()[0]
        for a, b in FAIXAS_GAP
    }
    return Readmissao(altas, obitos, censuradas, readmitidas, por_gap, transf, perm)


def medir_plano_b(con: duckdb.DuckDBPyConnection, cobertura: Cobertura) -> PlanoB:
    """Óbito hospitalar e permanência (dias entre DT_INTER e a saída final) no período coberto."""
    base = "from internacoes where dt_saida between ? and ?"
    periodo = [cobertura.inicio, cobertura.fim]
    saidas, obitos, media = con.execute(
        f"select count(*), count(*) filter (where obito), avg(dt_saida - dt_inter) {base}", periodo
    ).fetchone()
    quantis = con.execute(
        f"select quantile_cont(dt_saida - dt_inter, {list(QUANTIS_PERMANENCIA)}) {base}", periodo
    ).fetchone()[0] or []
    acima = {
        dias: con.execute(
            f"select count(*) {base} and dt_saida - dt_inter > ?", [*periodo, dias]
        ).fetchone()[0]
        for dias in (7, 14, 30)
    }
    return PlanoB(
        saidas, obitos, float(media or 0.0), dict(zip(QUANTIS_PERMANENCIA, quantis)), acima
    )


def _razao(parte: int, total: int) -> float:
    return parte / total if total else 0.0


def _lista_sql(codigos: frozenset[str]) -> str:
    return ", ".join(f"'{c}'" for c in sorted(codigos))


def _rotulo_faixa(minimo: int, maximo: int | None) -> str:
    if maximo is None:
        return f"{minimo}+"
    return str(minimo) if minimo == maximo else f"{minimo}–{maximo}"
