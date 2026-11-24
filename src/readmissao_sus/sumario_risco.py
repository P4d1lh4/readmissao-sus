"""Sumário de Alta (S08) com a probabilidade de readmissão do modelo (S13), para a API (S11).

Elegível = episódio com linha em atributo_episodio. O Bundle vem de `episodio_leitura` e
`fhir_sumario`; a probabilidade, dos atributos do episódio em atributo_episodio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from readmissao_sus.artefatos import Artefatos
from readmissao_sus.episodio_leitura import ler_episodios
from readmissao_sus.fhir_sumario import Json, montar_bundle
from readmissao_sus.modelagem import ATRIBUTOS


class EpisodioNaoElegivel(LookupError):
    """Episódio inexistente ou sem linha em atributo_episodio."""


@dataclass(frozen=True)
class SumarioComRisco:
    episodio_id: str
    modelo: str
    probabilidade: float
    limiar: float
    acima_do_limiar: bool
    bundle: Json


def ler_atributos_episodio(con: duckdb.DuckDBPyConnection, episodio_id: str) -> dict[str, Any] | None:
    """Os ATRIBUTOS do episódio em atributo_episodio, ou None se ele não for elegível."""
    colunas = ", ".join(ATRIBUTOS)
    linhas = con.execute(
        f"select {colunas} from atributo_episodio where episodio_id = ?", [episodio_id]
    ).df()
    return None if linhas.empty else linhas.iloc[0].to_dict()


def montar_sumario_com_risco(
    con: duckdb.DuckDBPyConnection,
    parquets: Sequence[Path],
    artefatos: Artefatos,
    episodio_id: str,
    gerado_em: datetime,
) -> SumarioComRisco:
    """Bundle do Sumário de Alta mais probabilidade, limiar e alerta.

    Levanta EpisodioNaoElegivel se o episódio não tiver atributos e ValueError se faltar
    CNPJ ou município do hospital nos Parquet (o Bundle não pode ser montado).
    """
    registro = ler_atributos_episodio(con, episodio_id)
    if registro is None:
        raise EpisodioNaoElegivel(episodio_id)
    previsao = artefatos.prever(registro)
    [episodio] = ler_episodios(con, parquets, [episodio_id])
    return SumarioComRisco(
        episodio_id=episodio_id,
        modelo=artefatos.modelo,
        probabilidade=previsao.probabilidade,
        limiar=previsao.limiar,
        acima_do_limiar=bool(previsao.alerta),
        bundle=montar_bundle(episodio, gerado_em),
    )
