"""API do Sumário de Alta com risco de readmissão (S11), adaptada de Health-Project/api/main.py.

Subir (na raiz do projeto):
    .venv\\Scripts\\python -m uvicorn api.main:app --port 8000

Lê data/sih.duckdb (só leitura), data/parquet/ e models/, todos fora do git. Os caminhos podem
ser trocados por READMISSAO_BANCO, READMISSAO_PARQUET e READMISSAO_MODELOS.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

import duckdb  # noqa: E402
from fastapi import FastAPI, HTTPException, Path as Caminho, Request  # noqa: E402

from readmissao_sus.artefatos import Artefatos, carregar_artefatos  # noqa: E402
from readmissao_sus.sumario_risco import montar_sumario_com_risco  # noqa: E402
from readmissao_sus.treino import ARQUIVO_METADATA, ARQUIVO_MODELO  # noqa: E402

TITULO = "API do Sumário de Alta com risco de readmissão"
VERSAO = "0.1.0"
PADRAO_ID_EPISODIO = r"^[0-9A-Za-z]{1,32}$"
PREFIXO_PARQUET = "RDPE*.parquet"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Recursos:
    con: duckdb.DuckDBPyConnection
    parquets: tuple[Path, ...]
    artefatos: Artefatos


def _carregar(banco: Path, dir_parquet: Path, dir_modelo: Path) -> Recursos | None:
    """Abre o banco só para leitura e carrega o modelo; None se faltar algum arquivo."""
    parquets = tuple(sorted(dir_parquet.glob(PREFIXO_PARQUET)))
    modelo_ok = all((dir_modelo / nome).is_file() for nome in (ARQUIVO_MODELO, ARQUIVO_METADATA))
    if not banco.is_file() or not parquets or not modelo_ok:
        logger.warning("Falta banco, Parquet ou modelo (%s, %s, %s); a API responderá 503.", banco, dir_parquet, dir_modelo)
        return None
    return Recursos(duckdb.connect(str(banco), read_only=True), parquets, carregar_artefatos(dir_modelo))


def create_app(banco: Path, dir_parquet: Path, dir_modelo: Path) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        app.state.recursos = _carregar(banco, dir_parquet, dir_modelo)
        yield
        if app.state.recursos is not None:
            app.state.recursos.con.close()

    app = FastAPI(title=TITULO, version=VERSAO, lifespan=ciclo_de_vida)

    def _recursos(request: Request) -> Recursos:
        recursos: Recursos | None = request.app.state.recursos
        if recursos is None:
            raise HTTPException(status_code=503, detail="Banco ou modelo indisponível. Rode o pipeline antes.")
        return recursos

    @app.get("/saude")
    def saude(request: Request) -> dict[str, Any]:
        recursos: Recursos | None = request.app.state.recursos
        if recursos is None:
            return {"status": "indisponivel", "modelo": None, "limiar": None}
        return {"status": "ok", "modelo": recursos.artefatos.modelo, "limiar": recursos.artefatos.limiar}

    @app.get("/episodios/{episodio_id}/sumario-alta")
    def sumario_alta(
        request: Request, episodio_id: str = Caminho(pattern=PADRAO_ID_EPISODIO)
    ) -> dict[str, Any]:
        recursos = _recursos(request)
        cursor = recursos.con.cursor()  # uma conexão por requisição: as rotas rodam em threads
        try:
            sumario = montar_sumario_com_risco(
                cursor, recursos.parquets, recursos.artefatos, episodio_id, datetime.now().astimezone()
            )
        except LookupError:  # EpisodioNaoElegivel, ou KeyError de um episódio sem AIHs no banco
            raise HTTPException(status_code=404, detail="Episódio inexistente ou não elegível.")
        except ValueError:
            raise HTTPException(status_code=422, detail="Faltam CNPJ ou município do hospital para montar o Sumário.")
        finally:
            cursor.close()
        return asdict(sumario)

    return app


app = create_app(
    Path(os.environ.get("READMISSAO_BANCO", RAIZ / "data" / "sih.duckdb")),
    Path(os.environ.get("READMISSAO_PARQUET", RAIZ / "data" / "parquet")),
    Path(os.environ.get("READMISSAO_MODELOS", RAIZ / "models")),
)
