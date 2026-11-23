"""Valida um recurso FHIR (JSON) com o validador oficial HL7 num container Java.

Uso:
    .venv\\Scripts\\python scripts\\validar_fhir.py fhir\\exemplos\\sumario-alta-valido.json
    .venv\\Scripts\\python scripts\\validar_fhir.py ARQUIVO.json --sem-terminologia

Valida contra os pacotes de fhir/pacotes/ e o perfil sumario-alta (decisão D02).
Código de saída: 0 sem erros; 1 com erro de validação; 2 se o validador não rodou.
Não é preciso Java no Windows: só o Docker.
Se tx.fhir.org não responder, valida de novo com -tx n/a e diz isso na linha "Modo".
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.pacotes_fhir import baixar_http  # noqa: E402
from readmissao_sus.validador_fhir import (  # noqa: E402
    PERFIL_SUMARIO_ALTA,
    ErroValidador,
    arquivos_pacotes,
    comando_docker,
    formatar_resumo,
    garantir_validador,
    interpretar_outcome,
)

DIR_CACHE = RAIZ / ".cache"
DIR_PACOTES = RAIZ / "fhir" / "pacotes"
NOME_SAIDA = "outcome.json"
SAIDA_VALIDO, SAIDA_INVALIDO, SAIDA_FALHA = 0, 1, 2
SEM_SERVIDOR_TX = "Unable to connect to terminology server"
MODO_COM_TX = "com terminologia (tx.fhir.org)"
MODO_SEM_TX = "sem terminologia (-tx n/a)"
MODO_FALLBACK = "sem terminologia (-tx n/a), porque tx.fhir.org não respondeu"


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida um recurso FHIR com o validador HL7 em Docker.")
    parser.add_argument("arquivo", type=Path, help="arquivo JSON a validar")
    parser.add_argument("--perfil", default=PERFIL_SUMARIO_ALTA, help="URL canônica do perfil")
    parser.add_argument(
        "--sem-terminologia",
        action="store_true",
        help="usa -tx n/a: não consulta tx.fhir.org (códigos de CodeSystems externos não são checados)",
    )
    parser.add_argument("--log", action="store_true", help="mostra o log completo do validador")
    return parser.parse_args(argv)


def _eh_bundle(arquivo: Path) -> bool:
    """JSON ilegível segue como recurso avulso: o próprio validador reporta o erro."""
    try:
        return json.loads(arquivo.read_text(encoding="utf-8")).get("resourceType") == "Bundle"
    except (ValueError, AttributeError):
        return False


def _rodar(args: argparse.Namespace, dir_saida: Path, com_terminologia: bool) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        raise ErroValidador("Docker não encontrado no PATH. Instale e abra o Docker Desktop.")
    jar = garantir_validador(DIR_CACHE / "validador", baixar_http)
    comando = comando_docker(
        args.arquivo,
        jar,
        arquivos_pacotes(DIR_PACOTES),
        dir_saida,
        NOME_SAIDA,
        perfil=args.perfil,
        eh_bundle=_eh_bundle(args.arquivo),
        com_terminologia=com_terminologia,
    )
    return subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _validar(args: argparse.Namespace, com_terminologia: bool) -> tuple[subprocess.CompletedProcess, dict | None]:
    """Roda o validador e devolve o processo e o OperationOutcome (None se não houve saída)."""
    with tempfile.TemporaryDirectory(dir=DIR_CACHE, prefix="saida-") as temporario:
        dir_saida = Path(temporario)
        processo = _rodar(args, dir_saida, com_terminologia)
        saida = dir_saida / NOME_SAIDA
        outcome = json.loads(saida.read_text(encoding="utf-8")) if saida.is_file() else None
    if args.log:
        print(processo.stdout + processo.stderr)
    return processo, outcome


def _sem_servidor_de_terminologia(processo: subprocess.CompletedProcess) -> bool:
    return SEM_SERVIDOR_TX in processo.stdout + processo.stderr


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = _argumentos(argv)
    if not args.arquivo.is_file():
        print(f"ERRO: arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        return SAIDA_FALHA
    DIR_CACHE.mkdir(exist_ok=True)
    modo = MODO_SEM_TX if args.sem_terminologia else MODO_COM_TX
    try:
        processo, outcome = _validar(args, com_terminologia=not args.sem_terminologia)
        if outcome is None and not args.sem_terminologia and _sem_servidor_de_terminologia(processo):
            print("AVISO: tx.fhir.org não respondeu; validando de novo sem terminologia (-tx n/a).", file=sys.stderr)
            modo = MODO_FALLBACK
            processo, outcome = _validar(args, com_terminologia=False)
    except ErroValidador as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return SAIDA_FALHA
    if outcome is None:
        print(processo.stdout[-4000:] + processo.stderr[-4000:], file=sys.stderr)
        print(f"ERRO: o validador não gerou saída (código {processo.returncode}).", file=sys.stderr)
        return SAIDA_FALHA
    resumo = interpretar_outcome(outcome)
    print(f"Arquivo: {args.arquivo}")
    print(f"Perfil: {args.perfil}")
    print(f"Modo: {modo}")
    print(formatar_resumo(resumo))
    return SAIDA_VALIDO if resumo.valido else SAIDA_INVALIDO


if __name__ == "__main__":
    sys.exit(main())
