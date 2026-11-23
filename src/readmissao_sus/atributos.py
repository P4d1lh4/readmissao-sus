"""Atributos por episódio elegível (história S09), com o SQL de sql/06_atributos.sql.

A tabela `atributo_episodio` tem uma linha por episódio de `coorte_episodio` com rótulo
(`readmissao_30d` não nulo). O histórico da chave só usa episódios anteriores à entrada; a regra
está no cabeçalho do SQL e em docs/atributos.md. Aqui ficam a montagem e as contagens agregadas
que vão para o documento (faixas de cada atributo e taxa de readmissão em cada faixa).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import duckdb

from readmissao_sus import dicionario_sih as dic
from readmissao_sus.sql_versionado import executar_sql

DIAS_HISTORICO = 365
SQL_ATRIBUTOS = ("06_atributos.sql",)
TABELA = "atributo_episodio"
MAX_CATEGORIAS = 10
ROTULO_NULO = "nulo"


@dataclass(frozen=True)
class Atributo:
    """Como o documento resume uma coluna: faixas numéricas, categorias ou sim/não.

    `cortes`: limites inferiores das faixas de um inteiro, em ordem; cada faixa vai do corte
    até o próximo menos 1, e a última é aberta. Sem cortes, a coluna é categórica.
    """

    coluna: str
    descricao: str
    cortes: tuple[int, ...] = ()
    rotulos: dict[str, str] = field(default_factory=dict)
    rotulo_nulo: str = ROTULO_NULO
    por_volume: bool = True
    max_categorias: int = MAX_CATEGORIAS


def _sim_nao(coluna: str, descricao: str) -> Atributo:
    return Atributo(coluna, descricao, rotulos={"true": "sim", "false": "não"}, por_volume=False)


CAPITULOS = {romano: f"{romano}. {nome}" for _, romano, nome, _, _ in dic.CID10_CAPITULOS}
GRUPOS = {codigo: f"{codigo} {nome}" for codigo, nome in dic.SIGTAP_GRUPOS.items()}
CARATER = {codigo: f"{codigo} {nome}" for codigo, nome in dic.CAR_INT.items()}

ATRIBUTOS = (
    _sim_nao("readmissao_30d", "Alvo: novo episódio da mesma chave em até 30 dias após a alta"),
    Atributo("idade", "Idade em anos na entrada (COD_IDADE em dias ou meses vira 0)",
             cortes=(0, 1, 5, 15, 50, 65, 80), rotulo_nulo="idade inválida"),
    Atributo("sexo", "Sexo (1 = M; 2 e 3 = F)", rotulo_nulo="ignorado"),
    Atributo("capitulo_cid", "Capítulo da CID-10 do diagnóstico principal da entrada",
             rotulos=CAPITULOS, rotulo_nulo="sem capítulo no CID10CAP.CNV",
             max_categorias=len(CAPITULOS)),
    Atributo("grupo_sigtap", "Grupo SIGTAP do procedimento principal da entrada",
             rotulos=GRUPOS, rotulo_nulo="grupo desconhecido"),
    Atributo("car_int", "Caráter da internação na entrada", rotulos=CARATER),
    Atributo("dias_permanencia", "Dias de permanência do episódio (saída − entrada)",
             cortes=(0, 1, 2, 4, 8, 15, 31)),
    Atributo("dias_uti", "Diárias de UTI somadas no episódio (UTI_MES_TO)", cortes=(0, 1, 4, 8)),
    _sim_nao("usou_uti", "Teve diária de UTI no episódio"),
    Atributo("n_aihs", "Internações (AIHs) no episódio", cortes=(1, 2, 3, 4)),
    Atributo("n_hospitais", "Hospitais (CNES) distintos no episódio", cortes=(1, 2, 3)),
    _sim_nao("houve_transferencia", "Episódio juntou internações por transferência"),
    _sim_nao("houve_permanencia", "Episódio juntou internações por permanência"),
    _sim_nao("houve_contigua_sem_motivo",
             "Episódio juntou contíguas sem motivo (só com a D03 diferente de 'nenhuma')"),
    _sim_nao("cep_generico", "CEP terminado em 000 (D01, condição 2)"),
    Atributo("cnes_alta", "CNES do hospital da alta (última internação)"),
    Atributo("ano_alta", "Ano da alta", por_volume=False),
    _sim_nao("historico_completo", "Janela de 365 dias antes da entrada inteira dentro dos dados"),
    Atributo("episodios_365d", "Episódios anteriores da chave com saída nos 365 dias antes da entrada",
             cortes=(0, 1, 2, 3, 5)),
    Atributo("dias_internado_365d", "Dias internado nesses episódios, dentro da janela",
             cortes=(0, 1, 4, 8, 15, 31)),
    Atributo("dias_desde_ultima_alta", "Dias entre a última alta anterior da chave e a entrada",
             cortes=(0, 2, 8, 31, 91, 181, 366), rotulo_nulo="sem episódio anterior"),
    _sim_nao("historico_com_obito", "Algum episódio anterior da chave terminou em óbito (colisão)"),
    _sim_nao("chave_colidente", "A chave tem episódios sobrepostos no tempo (D01)"),
    _sim_nao("episodio_sobreposto", "Este episódio se sobrepõe a outro da mesma chave"),
)


@dataclass(frozen=True)
class Faixa:
    rotulo: str
    episodios: int
    readmitidos: int

    @property
    def taxa(self) -> float:
        return self.readmitidos / self.episodios if self.episodios else 0.0


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str
    nulos: int


@dataclass(frozen=True)
class ResumoAtributos:
    episodios: int
    readmitidos: int
    colunas: list[Coluna]
    faixas: dict[str, list[Faixa]]
    historico: list[tuple]
    colisoes: dict[str, int]
    dias_historico: int = DIAS_HISTORICO


def montar_atributos(con: duckdb.DuckDBPyConnection, inicio_dados: date) -> None:
    """Cria episodio_sobreposicao e atributo_episodio (precisa das tabelas de episódio)."""
    con.execute("set variable inicio_dados = ?", [inicio_dados])
    con.execute("set variable dias_historico = ?", [DIAS_HISTORICO])
    for nome in SQL_ATRIBUTOS:
        executar_sql(con, nome)


def ler_resumo(con: duckdb.DuckDBPyConnection) -> ResumoAtributos:
    episodios, readmitidos = con.execute(
        f"select count(*), count(*) filter (where readmissao_30d) from {TABELA}"
    ).fetchone()
    return ResumoAtributos(
        episodios=episodios,
        readmitidos=readmitidos,
        colunas=_colunas(con),
        faixas={a.coluna: _faixas(con, a) for a in ATRIBUTOS},
        historico=_historico(con),
        colisoes=_colisoes(con),
    )


def faixa_sql(coluna: str, cortes: tuple[int, ...]) -> str:
    """CASE que devolve o rótulo da faixa ('0', '1', '2–3', '8+') de uma coluna inteira."""
    ramos = []
    for i, inicio in reversed(list(enumerate(cortes))):
        if i == len(cortes) - 1:
            rotulo = f"{inicio}+"
        else:
            fim = cortes[i + 1] - 1
            rotulo = str(inicio) if fim == inicio else f"{inicio}–{fim}"
        ramos.append(f"when {coluna} >= {inicio} then '{rotulo}'")
    return f"case {' '.join(ramos)} end"


def _colunas(con: duckdb.DuckDBPyConnection) -> list[Coluna]:
    tipos = [(nome, tipo) for nome, tipo, *_ in con.execute(f"describe {TABELA}").fetchall()]
    contagens = ", ".join(f"count(*) - count({nome})" for nome, _ in tipos)
    nulos = con.execute(f"select {contagens} from {TABELA}").fetchone()
    return [Coluna(nome, tipo, n) for (nome, tipo), n in zip(tipos, nulos)]


def _faixas(con: duckdb.DuckDBPyConnection, atributo: Atributo) -> list[Faixa]:
    coluna = atributo.coluna
    rotulo = faixa_sql(coluna, atributo.cortes) if atributo.cortes else f"{coluna}::varchar"
    linhas = con.execute(
        f"""
        select {rotulo} as faixa, min({coluna}) as ordem, count(*), count(*) filter (where readmissao_30d)
        from {TABELA} group by 1
        """
    ).fetchall()
    nulas = [Faixa(atributo.rotulo_nulo, n, r) for faixa, _, n, r in linhas if faixa is None]
    validas = [(faixa, ordem, n, r) for faixa, ordem, n, r in linhas if faixa is not None]
    if atributo.cortes or not atributo.por_volume:
        # Em ordem de valor; nas colunas sim/não, "sim" primeiro.
        validas.sort(key=lambda x: (x[1] is False, x[1]))
    else:
        validas.sort(key=lambda x: (-x[2], x[0]))
    faixas = [Faixa(atributo.rotulos.get(f, f), n, r) for f, _, n, r in validas]
    return _agrupar_cauda(faixas, atributo.max_categorias) + nulas


def _agrupar_cauda(faixas: list[Faixa], maximo: int) -> list[Faixa]:
    if len(faixas) <= maximo + 1:
        return faixas
    cauda = faixas[maximo:]
    outras = Faixa(f"outras {len(cauda)} categorias", sum(f.episodios for f in cauda),
                   sum(f.readmitidos for f in cauda))
    return faixas[:maximo] + [outras]


def _historico(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Por historico_completo: episódios, com episódio anterior em 365 dias, médias e taxa."""
    return con.execute(
        f"""
        select historico_completo, count(*),
               count(*) filter (where episodios_365d > 0),
               avg(episodios_365d), avg(dias_internado_365d),
               count(*) filter (where dias_desde_ultima_alta is null),
               count(*) filter (where readmissao_30d),
               count(*) filter (where readmissao_30d and episodios_365d > 0),
               count(*) filter (where readmissao_30d and episodios_365d = 0)
        from {TABELA} group by 1 order by 1 desc
        """
    ).fetchall()


def _colisoes(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    nomes = ("pares", "chaves", "episodios_envolvidos", "elegiveis_chave_colidente",
             "elegiveis_sobrepostos", "elegiveis_historico_com_obito")
    valores = con.execute(
        f"""
        select
            (select count(*) from episodio_sobreposicao),
            (select count(distinct chave) from episodio_sobreposicao),
            (select count(*) from (select anterior from episodio_sobreposicao
                                   union select seguinte from episodio_sobreposicao)),
            count(*) filter (where chave_colidente),
            count(*) filter (where episodio_sobreposto),
            count(*) filter (where historico_com_obito)
        from {TABELA}
        """
    ).fetchone()
    return dict(zip(nomes, valores))
