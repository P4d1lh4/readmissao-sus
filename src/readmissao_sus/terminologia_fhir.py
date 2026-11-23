"""Códigos dos CodeSystems da RNDS lidos direto do pacote FHIR (.tgz), sem servidor.

Usado para escolher a amostra da S08 só com códigos que existem no BRCID10, no BRTabelaSUS
e no BRMunicipio (todos `content: complete` no br.go.ses.reds-go).
"""

from __future__ import annotations

import json
import tarfile
from collections.abc import Iterable
from pathlib import Path


def _todos(conceitos: Iterable[dict]) -> Iterable[str]:
    for conceito in conceitos:
        yield conceito["code"]
        yield from _todos(conceito.get("concept", []))


def codigos(pacote: Path, url_codesystem: str) -> frozenset[str]:
    """Códigos do CodeSystem com essa URL canônica dentro do pacote."""
    with tarfile.open(pacote, "r:gz") as tar:
        for membro in tar.getmembers():
            nome = Path(membro.name).name
            if not (nome.startswith("CodeSystem-") and nome.endswith(".json")):
                continue
            arquivo = tar.extractfile(membro)
            if arquivo is None:
                continue
            recurso = json.load(arquivo)
            if recurso.get("url") == url_codesystem:
                return frozenset(_todos(recurso.get("concept", [])))
    raise KeyError(f"CodeSystem {url_codesystem} não encontrado em {pacote.name}")
