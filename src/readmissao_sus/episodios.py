"""Junção de internações contíguas em episódios (história S07), com o SQL de sql/04 e sql/05.

A regra fica em `RegraEpisodio`. A transferência (COBRANCA 29, 31, 32) seguida de nova AIH da
mesma chave no dia da saída ou no seguinte sempre junta. A permanência (21–28) junta por padrão
(D01, tratamento 6). As contíguas "sem motivo" (alta seguida de nova AIH em 0–1 dia) dependem
da D03, que aguarda decisão do usuário: o padrão conservador é não juntar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb

from readmissao_sus.cobertura import JANELA_DIAS
from readmissao_sus.sql_versionado import executar_sql

DIAS_CONTIGUIDADE = 1
SQL_EPISODIOS = ("04_episodio.sql", "05_episodio_contagens.sql")
CONTIGUAS_SEM_MOTIVO = ("nenhuma", "mesmo_hospital", "todas")


@dataclass(frozen=True)
class RegraEpisodio:
    """Quais saídas, seguidas de nova AIH contígua, continuam o mesmo episódio.

    contiguas_sem_motivo (D03): 'nenhuma' (padrão conservador: alta seguida de nova AIH conta
    como readmissão), 'mesmo_hospital' (proposta da D03: junta se a nova AIH é no mesmo CNES)
    ou 'todas'.
    """

    juntar_permanencia: bool = True
    contiguas_sem_motivo: str = "nenhuma"

    def __post_init__(self) -> None:
        if self.contiguas_sem_motivo not in CONTIGUAS_SEM_MOTIVO:
            opcoes = ", ".join(CONTIGUAS_SEM_MOTIVO)
            raise ValueError(
                f"contiguas_sem_motivo inválida: {self.contiguas_sem_motivo!r} (use {opcoes})."
            )

    @property
    def descricao(self) -> str:
        partes = ["transferência"]
        if self.juntar_permanencia:
            partes.append("permanência")
        if self.contiguas_sem_motivo == "mesmo_hospital":
            partes.append("contíguas sem motivo no mesmo hospital")
        elif self.contiguas_sem_motivo == "todas":
            partes.append("todas as contíguas sem motivo")
        return " + ".join(partes)


REGRA_PADRAO = RegraEpisodio()
REGRA_PROPOSTA_D03 = RegraEpisodio(contiguas_sem_motivo="mesmo_hospital")
REGRAS_COMPARADAS = (
    RegraEpisodio(juntar_permanencia=False),
    REGRA_PADRAO,
    REGRA_PROPOSTA_D03,
    RegraEpisodio(contiguas_sem_motivo="todas"),
)


@dataclass(frozen=True)
class ComparacaoRegra:
    regra: RegraEpisodio
    internacoes: int
    episodios: int
    altas_indice: int
    readmitidas: int

    @property
    def taxa(self) -> float:
        return self.readmitidas / self.altas_indice if self.altas_indice else 0.0


@dataclass(frozen=True)
class Episodios:
    regra: RegraEpisodio
    resumo: dict[str, list[tuple[str, int]]]
    motivos: list[tuple[str, int, int, int]]
    sem_motivo: list[tuple]
    procedimentos: list[tuple[str, str, bool, int]]
    comparacao: list[ComparacaoRegra]


def montar_episodios(
    con: duckdb.DuckDBPyConnection, regra: RegraEpisodio, inicio: date, corte: date
) -> None:
    """Cria as tabelas de episódio (precisa de internacao, coorte e dic_cobranca)."""
    variaveis = {
        "juntar_permanencia": regra.juntar_permanencia,
        "contiguas_sem_motivo": regra.contiguas_sem_motivo,
        "dias_contiguidade": DIAS_CONTIGUIDADE,
        "janela_dias": JANELA_DIAS,
        "inicio_indice": inicio,
        "corte_indice": corte,
    }
    for nome, valor in variaveis.items():
        con.execute(f"set variable {nome} = ?", [valor])
    for nome in SQL_EPISODIOS:
        executar_sql(con, nome)
    con.execute(
        "create or replace table episodio_parametros as select ?::boolean as juntar_permanencia, "
        "?::varchar as contiguas_sem_motivo, ?::integer as dias_contiguidade, "
        "?::integer as janela_dias",
        [regra.juntar_permanencia, regra.contiguas_sem_motivo, DIAS_CONTIGUIDADE, JANELA_DIAS],
    )


def comparar_regras(
    con: duckdb.DuckDBPyConnection, regra: RegraEpisodio, inicio: date, corte: date
) -> Episodios:
    """Monta os episódios com cada regra de REGRAS_COMPARADAS e termina com `regra`.

    As tabelas que ficam no banco são as de `regra`; das outras sobra só a comparação.
    """
    comparacao = []
    for alternativa in (*[r for r in REGRAS_COMPARADAS if r != regra], regra):
        montar_episodios(con, alternativa, inicio, corte)
        comparacao.append(_comparacao(con, alternativa))
    ordem = {r: i for i, r in enumerate(REGRAS_COMPARADAS)}
    comparacao.sort(key=lambda c: ordem.get(c.regra, len(ordem)))
    return ler_episodios(con, regra, comparacao)


def ler_episodios(
    con: duckdb.DuckDBPyConnection, regra: RegraEpisodio, comparacao: list[ComparacaoRegra]
) -> Episodios:
    resumo: dict[str, list[tuple[str, int]]] = {}
    for secao, item, valor in con.execute(
        "select secao, item, valor from episodio_resumo order by secao, ordem"
    ).fetchall():
        resumo.setdefault(secao, []).append((item, int(valor or 0)))
    return Episodios(
        regra=regra,
        resumo=resumo,
        motivos=con.execute("select * from episodio_motivos").fetchall(),
        sem_motivo=con.execute("select * from contiguas_sem_motivo").fetchall(),
        procedimentos=con.execute("select * from contiguas_procedimentos").fetchall(),
        comparacao=comparacao,
    )


def _comparacao(con: duckdb.DuckDBPyConnection, regra: RegraEpisodio) -> ComparacaoRegra:
    internacoes, episodios, altas, readmitidas = con.execute(
        """
        select (select count(*) from internacao), (select count(*) from episodio),
               count(*) filter (where elegivel_indice), count(*) filter (where readmissao_30d)
        from coorte_episodio
        """
    ).fetchone()
    return ComparacaoRegra(regra, internacoes, episodios, altas, readmitidas)
