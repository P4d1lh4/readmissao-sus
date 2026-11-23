"""Download idempotente dos arquivos RD do SIH/SUS no FTP público do DATASUS."""

from __future__ import annotations

import ftplib
import os
from collections.abc import Callable, Iterable
from pathlib import Path

FTP_HOST = "ftp.datasus.gov.br"
FTP_DIR_RD = "/dissemin/publicos/SIHSUS/200801_/Dados"
FTP_TIMEOUT_S = 60

Baixador = Callable[[str, Path], None]


class ErroDownload(RuntimeError):
    """Falha de rede ou do servidor ao baixar um arquivo do DATASUS."""


def nomes_arquivos_rd(uf: str, anos: Iterable[int]) -> list[str]:
    """Nomes RDuuaamm.dbc de todos os meses dos anos pedidos (ex.: RDPE2301.dbc)."""
    uf = uf.strip().upper()
    if len(uf) != 2 or not uf.isalpha():
        raise ValueError(f"UF inválida: {uf!r}")
    return [f"RD{uf}{ano % 100:02d}{mes:02d}.dbc" for ano in anos for mes in range(1, 13)]


def arquivos_faltantes(nomes: Iterable[str], destino: Path) -> list[str]:
    """Arquivos que ainda não existem (ou estão vazios) em `destino`."""
    return [n for n in nomes if not _existe_com_conteudo(destino / n)]


def baixar_faltantes(nomes: Iterable[str], destino: Path, baixar: Baixador) -> list[str]:
    """Baixa só o que falta. Cada arquivo é gravado em .part e renomeado ao final.

    Devolve a lista dos arquivos baixados nesta execução.
    """
    destino.mkdir(parents=True, exist_ok=True)
    baixados = []
    for nome in arquivos_faltantes(nomes, destino):
        final = destino / nome
        parcial = final.with_name(final.name + ".part")
        try:
            baixar(nome, parcial)
        except (*ftplib.all_errors, OSError) as erro:
            parcial.unlink(missing_ok=True)
            raise ErroDownload(
                f"Falha ao baixar {nome} de {FTP_HOST}{FTP_DIR_RD}: {erro}. "
                "Verifique a conexão e rode o script de novo; os arquivos já baixados são mantidos."
            ) from erro
        os.replace(parcial, final)
        baixados.append(nome)
    return baixados


class BaixadorFtp:
    """Baixador que reaproveita uma conexão FTP anônima ao DATASUS."""

    def __init__(self, host: str = FTP_HOST, diretorio: str = FTP_DIR_RD) -> None:
        self._host = host
        self._diretorio = diretorio
        self._ftp: ftplib.FTP | None = None

    def __call__(self, nome: str, caminho: Path) -> None:
        ftp = self._conectar()
        with caminho.open("wb") as saida:
            ftp.retrbinary(f"RETR {nome}", saida.write)

    def fechar(self) -> None:
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except (*ftplib.all_errors, OSError):
                self._ftp.close()
            self._ftp = None

    def _conectar(self) -> ftplib.FTP:
        if self._ftp is None:
            ftp = ftplib.FTP(self._host, timeout=FTP_TIMEOUT_S)
            ftp.login()
            ftp.cwd(self._diretorio)
            self._ftp = ftp
        return self._ftp


def _existe_com_conteudo(caminho: Path) -> bool:
    return caminho.is_file() and caminho.stat().st_size > 0
