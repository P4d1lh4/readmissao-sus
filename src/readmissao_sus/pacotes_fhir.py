"""Download idempotente e verificado dos pacotes FHIR (NPM .tgz) usados na validação.

Cada pacote tem versão fixa e SHA-256 esperado. O arquivo final se chama
`<nome>-<versão>.tgz`, que é o que o validador HL7 recebe com `-ig`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

HTTP_TIMEOUT_S = 120
USER_AGENT = "readmissao-sus/baixar-pacotes-fhir"
TAMANHO_BLOCO = 1 << 16

Baixador = Callable[[str, Path], None]


class ErroPacote(RuntimeError):
    """Falha ao baixar ou conferir um pacote FHIR."""


@dataclass(frozen=True)
class PacoteFhir:
    nome: str
    versao: str
    url: str
    sha256: str

    @property
    def arquivo(self) -> str:
        return f"{self.nome}-{self.versao}.tgz"


PACOTES: tuple[PacoteFhir, ...] = (
    # Guia CORE da SES-GO: traz o perfil sumario-alta (draft). Só existe no ambiente de
    # homologação; a URL não tem versão, por isso o SHA-256 fixa o conteúdo.
    PacoteFhir(
        nome="br.go.ses.core",
        versao="1.2.6",
        url="https://fhir-homolog.saude.go.gov.br/r4/core/package.tgz",
        sha256="c6ddb2970eb854d87e3a79999f45649814dcee83e767dc00a57d4ebbf345ba68",
    ),
    # Artefatos da RNDS (http://www.saude.gov.br/fhir/r4) empacotados pela SES-GO.
    # Dependência declarada de br.go.ses.core 1.2.6.
    PacoteFhir(
        nome="br.go.ses.reds-go",
        versao="1.0.3",
        url="https://packages.simplifier.net/br.go.ses.reds-go/1.0.3",
        sha256="be49b292d14b18801b4b744f1db44a86cc1031c1d84eda21a802bdb686dbfd87",
    ),
)


def sha256_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as entrada:
        for bloco in iter(lambda: entrada.read(TAMANHO_BLOCO), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def ler_package_json(tgz: Path) -> dict:
    """Lê `package/package.json` de um pacote FHIR NPM."""
    try:
        with tarfile.open(tgz, "r:gz") as tar:
            membro = tar.extractfile("package/package.json")
            if membro is None:
                raise ErroPacote(f"{tgz.name}: package/package.json não é um arquivo.")
            return json.loads(membro.read().decode("utf-8"))
    except (tarfile.TarError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as erro:
        raise ErroPacote(f"{tgz.name} não é um pacote FHIR NPM válido: {erro}") from erro


def pacote_em_dia(pacote: PacoteFhir, destino: Path) -> bool:
    caminho = destino / pacote.arquivo
    return caminho.is_file() and sha256_arquivo(caminho) == pacote.sha256


def baixar_pacotes(pacotes: Iterable[PacoteFhir], destino: Path, baixar: Baixador) -> list[str]:
    """Baixa só os pacotes ausentes ou com SHA-256 diferente do esperado.

    Grava em .part, confere SHA-256 e package.json e só então renomeia.
    Devolve os nomes de arquivo baixados nesta execução.
    """
    destino.mkdir(parents=True, exist_ok=True)
    baixados = []
    for pacote in pacotes:
        if pacote_em_dia(pacote, destino):
            continue
        final = destino / pacote.arquivo
        parcial = final.with_name(final.name + ".part")
        try:
            _baixar_e_conferir(pacote, parcial, baixar)
        except BaseException:
            parcial.unlink(missing_ok=True)
            raise
        os.replace(parcial, final)
        baixados.append(pacote.arquivo)
    return baixados


def dependencias_externas(pacotes: Iterable[PacoteFhir], destino: Path) -> dict[str, str]:
    """Dependências declaradas nos pacotes locais que não estão entre eles.

    São as que o validador ainda busca no registro (ex.: hl7.fhir.r4.core).
    """
    pacotes = tuple(pacotes)
    locais = {(p.nome, p.versao) for p in pacotes}
    externas: dict[str, str] = {}
    for pacote in pacotes:
        dependencias = ler_package_json(destino / pacote.arquivo).get("dependencies", {})
        externas |= {n: v for n, v in dependencias.items() if (n, v) not in locais}
    return dict(sorted(externas.items()))


def _baixar_e_conferir(pacote: PacoteFhir, parcial: Path, baixar: Baixador) -> None:
    try:
        baixar(pacote.url, parcial)
    except (urllib.error.URLError, OSError) as erro:
        raise ErroPacote(
            f"Falha ao baixar {pacote.arquivo} de {pacote.url}: {erro}. "
            "Verifique a conexão e rode o script de novo; os pacotes já baixados são mantidos."
        ) from erro
    obtido = sha256_arquivo(parcial)
    if obtido != pacote.sha256:
        raise ErroPacote(
            f"{pacote.arquivo}: SHA-256 {obtido} diferente do esperado {pacote.sha256}. "
            f"O conteúdo publicado em {pacote.url} mudou; revise a versão em docs/decisoes.md (D02) "
            "antes de atualizar o hash."
        )
    manifesto = ler_package_json(parcial)
    if (manifesto.get("name"), manifesto.get("version")) != (pacote.nome, pacote.versao):
        raise ErroPacote(
            f"{pacote.arquivo}: package.json diz {manifesto.get('name')}#{manifesto.get('version')}, "
            f"esperado {pacote.nome}#{pacote.versao}."
        )


def baixar_http(url: str, caminho: Path) -> None:
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, timeout=HTTP_TIMEOUT_S) as resposta, caminho.open("wb") as saida:
        for bloco in iter(lambda: resposta.read(TAMANHO_BLOCO), b""):
            saida.write(bloco)
