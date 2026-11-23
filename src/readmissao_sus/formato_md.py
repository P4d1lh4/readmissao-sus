"""Formatação em Markdown (pt-BR) dos blocos gerados em docs/."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    alinhamento = ["---"] + ["---:"] * (len(cabecalho) - 1)
    return "\n".join(_linha(x) for x in [cabecalho, alinhamento, *linhas])


def pct(parte: int, total: int) -> str:
    return pct_f(parte / total) if total else "—"


def pct_f(fracao: float) -> str:
    return f"{100 * fracao:.2f}%".replace(".", ",")


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def gravar_entre_marcas(caminho: Path, bloco: str, marca_inicio: str, marca_fim: str,
                        titulo: str) -> None:
    """Substitui o bloco entre as marcas; se não houver marcas, acrescenta ao fim do arquivo."""
    texto = caminho.read_text(encoding="utf-8") if caminho.exists() else f"{titulo}\n"
    inicio, fim = texto.find(marca_inicio), texto.find(marca_fim)
    if inicio == -1 or fim == -1:
        novo = texto.rstrip("\n") + "\n\n" + bloco + "\n"
    else:
        novo = texto[:inicio] + bloco + texto[fim + len(marca_fim):]
    caminho.write_text(novo, encoding="utf-8")


def _linha(celulas: list[str]) -> str:
    return "| " + " | ".join(celulas) + " |"
