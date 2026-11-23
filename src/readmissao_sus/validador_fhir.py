"""Validador oficial HL7 (validator_cli.jar) rodando num container Java.

O jar tem versão e SHA-256 fixos e fica em `.cache/validador/` (fora do git). A imagem
Docker tem tag e digest fixos. O cache de pacotes FHIR do validador (`~/.fhir` dentro
do container) é um volume Docker nomeado, para as dependências HL7 serem baixadas uma vez.

A saída do validador (OperationOutcome em JSON, via `-output`) é lida aqui e resumida
em erros, avisos e informações. Mensagens conhecidas causadas pelo próprio perfil
(não pelo documento) estão em `MENSAGENS_CONHECIDAS`, cada uma com justificativa.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from readmissao_sus.pacotes_fhir import PACOTES, Baixador, ErroPacote, sha256_arquivo

VALIDADOR_VERSAO = "7.0.3"
VALIDADOR_URL = (
    f"https://github.com/hapifhir/org.hl7.fhir.core/releases/download/{VALIDADOR_VERSAO}/validator_cli.jar"
)
VALIDADOR_SHA256 = "57aa43fb40cec5de41def81c927725fd85908eeb71509b7f9313e04d9b8ec79b"
VALIDADOR_ARQUIVO = f"validator_cli-{VALIDADOR_VERSAO}.jar"

# Temurin 21.0.13.1+2 (JRE). A tag fixa a versão; o digest fixa o conteúdo.
IMAGEM_JAVA = (
    "eclipse-temurin:21.0.13.1_2-jre"
    "@sha256:b57b0a974dc5ba8b24009a97aeb9ffd178e172727736279e5de73605f40c6813"
)
VOLUME_CACHE_FHIR = "readmissao-sus-fhir"
# Respostas do tx.fhir.org guardadas no mesmo volume, para não repetir consultas.
CACHE_TERMINOLOGIA = "/root/.fhir/tx-cache"
MEMORIA_JAVA = "-Xmx3g"

VERSAO_FHIR = "4.0.1"
PERFIL_SUMARIO_ALTA = "https://fhir.saude.go.gov.br/r4/core/StructureDefinition/sumario-alta"
# Ordem do -ig: dependência (reds-go) antes do guia que a usa (core).
ORDEM_PACOTES = ("br.go.ses.reds-go", "br.go.ses.core")

SEVERIDADES_ERRO = frozenset({"fatal", "error"})
SEVERIDADE_AVISO = "warning"
COMENTARIO_FHIRPATH = re.compile(r"/\*.*?\*/")


class ErroValidador(RuntimeError):
    """Falha ao preparar ou rodar o validador (não é erro de validação do documento)."""


@dataclass(frozen=True)
class MensagemConhecida:
    """Mensagem causada pelo perfil, não pelo documento, rebaixada para informação."""

    padrao: str
    justificativa: str

    def casa(self, texto: str) -> bool:
        return re.search(self.padrao, texto) is not None


MENSAGENS_CONHECIDAS: tuple[MensagemConhecida, ...] = (
    MensagemConhecida(
        padrao=r"^Constraint failed: BrasileiroSeSomenteSeNasceNoBrasil:",
        justificativa=(
            "a invariante do perfil individuo (br.go.ses.core 1.2.6) exige patient-birthPlace.country = '10' "
            "para brasileiros, mas o mesmo perfil liga country ao ValueSet iso3166-1-3 (required), em que o "
            "Brasil é 'BRA'; nenhum documento satisfaz as duas regras ao mesmo tempo"
        ),
    ),
    MensagemConhecida(
        padrao=(
            r"^None of the codings provided are in the value set 'Condition Category Codes' .*"
            r"codes = http://www\.saude\.gov\.br/fhir/r4/CodeSystem/BRCategoriaDiagnostico#\d+\)$"
        ),
        justificativa=(
            "o perfil diagnostico-sumario-alta liga Condition.category a BRCategoriaDiagnostico (required), "
            "fora do ValueSet extensible do FHIR R4; o validador avisa por causa do perfil, não do documento"
        ),
    ),
)


@dataclass(frozen=True)
class Mensagem:
    severidade: str
    local: str
    texto: str
    conhecida: MensagemConhecida | None = None

    @property
    def categoria(self) -> str:
        if self.conhecida is not None:
            return "conhecida"
        if self.severidade in SEVERIDADES_ERRO:
            return "erro"
        if self.severidade == SEVERIDADE_AVISO:
            return "aviso"
        return "informacao"


@dataclass(frozen=True)
class Resumo:
    mensagens: tuple[Mensagem, ...]

    def _contar(self, categoria: str) -> int:
        return sum(1 for m in self.mensagens if m.categoria == categoria)

    @property
    def erros(self) -> int:
        return self._contar("erro")

    @property
    def avisos(self) -> int:
        return self._contar("aviso")

    @property
    def informacoes(self) -> int:
        return self._contar("informacao")

    @property
    def conhecidas(self) -> int:
        return self._contar("conhecida")

    @property
    def valido(self) -> bool:
        return self.erros == 0


def garantir_validador(dir_cache: Path, baixar: Baixador) -> Path:
    """Devolve o caminho do jar, baixando-o só se faltar ou tiver hash errado."""
    dir_cache.mkdir(parents=True, exist_ok=True)
    jar = dir_cache / VALIDADOR_ARQUIVO
    if jar.is_file() and sha256_arquivo(jar) == VALIDADOR_SHA256:
        return jar
    parcial = jar.with_name(jar.name + ".part")
    try:
        baixar(VALIDADOR_URL, parcial)
        obtido = sha256_arquivo(parcial)
        if obtido != VALIDADOR_SHA256:
            raise ErroValidador(
                f"{VALIDADOR_ARQUIVO}: SHA-256 {obtido} diferente do esperado {VALIDADOR_SHA256}."
            )
    except (OSError, ErroPacote) as erro:
        parcial.unlink(missing_ok=True)
        raise ErroValidador(f"Falha ao baixar {VALIDADOR_URL}: {erro}") from erro
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    os.replace(parcial, jar)
    return jar


def arquivos_pacotes(dir_pacotes: Path) -> list[Path]:
    por_nome = {p.nome: dir_pacotes / p.arquivo for p in PACOTES}
    caminhos = [por_nome[nome] for nome in ORDEM_PACOTES]
    faltando = [c.name for c in caminhos if not c.is_file()]
    if faltando:
        raise ErroValidador(
            f"Pacotes FHIR ausentes em {dir_pacotes}: {', '.join(faltando)}. "
            "Rode .venv\\Scripts\\python scripts\\baixar_pacotes_fhir.py."
        )
    return caminhos


def comando_docker(
    arquivo: Path,
    jar: Path,
    pacotes: Sequence[Path],
    dir_saida: Path,
    nome_saida: str,
    perfil: str = PERFIL_SUMARIO_ALTA,
    eh_bundle: bool = True,
    com_terminologia: bool = True,
) -> list[str]:
    """Monta o `docker run` do validador. Entrada, jar e pacotes entram só para leitura.

    Num Bundle, o perfil vai para a Composition (`-bundle Composition:0`). Com `-profile`,
    o validador 7.0.3 deixou de reportar os problemas das próprias entradas do Bundle
    (ex.: código inexistente na CID-10), só os vistos a partir da Composition (D02).
    """
    montagens = [
        ("/entrada", arquivo.parent, "ro"),
        ("/validador", jar.parent, "ro"),
        ("/pacotes", pacotes[0].parent, "ro"),
        ("/saida", dir_saida, "rw"),
    ]
    if any(p.parent != pacotes[0].parent for p in pacotes):
        raise ErroValidador("Os pacotes FHIR precisam estar no mesmo diretório.")
    comando = ["docker", "run", "--rm"]
    for destino, origem, modo in montagens:
        comando += ["-v", f"{origem.resolve()}:{destino}:{modo}"]
    comando += ["-v", f"{VOLUME_CACHE_FHIR}:/root/.fhir", IMAGEM_JAVA]
    comando += ["java", MEMORIA_JAVA, "-jar", f"/validador/{jar.name}", f"/entrada/{arquivo.name}"]
    comando += ["-version", VERSAO_FHIR]
    for pacote in pacotes:
        comando += ["-ig", f"/pacotes/{pacote.name}"]
    comando += ["-bundle", "Composition:0", perfil] if eh_bundle else ["-profile", perfil]
    comando += ["-output", f"/saida/{nome_saida}", "-txCache", CACHE_TERMINOLOGIA]
    if not com_terminologia:
        comando += ["-tx", "n/a"]
    return comando


def _issues(saida: dict) -> Iterable[dict]:
    """Issues do OperationOutcome; com vários arquivos o validador devolve um Bundle deles."""
    if saida.get("resourceType") == "OperationOutcome":
        yield from saida.get("issue", [])
    elif saida.get("resourceType") == "Bundle":
        for entrada in saida.get("entry", []):
            yield from _issues(entrada.get("resource", {}))
    else:
        raise ErroValidador(f"Saída inesperada do validador: resourceType={saida.get('resourceType')!r}.")


def _local(issue: dict) -> str:
    """FHIRPath do problema, sem os comentários `/*Tipo/id*/` que o validador insere."""
    for chave in ("expression", "location"):
        if issue.get(chave):
            return COMENTARIO_FHIRPATH.sub("", issue[chave][0])
    return ""


def _texto(issue: dict) -> str:
    return issue.get("details", {}).get("text") or issue.get("diagnostics") or ""


def interpretar_outcome(
    saida: dict, conhecidas: Iterable[MensagemConhecida] = MENSAGENS_CONHECIDAS
) -> Resumo:
    conhecidas = tuple(conhecidas)
    mensagens = []
    for issue in _issues(saida):
        texto = _texto(issue)
        severidade = issue.get("severity", "information")
        conhecida = None
        if severidade != "information":
            conhecida = next((c for c in conhecidas if c.casa(texto)), None)
        mensagens.append(Mensagem(severidade, _local(issue), texto, conhecida))
    return Resumo(tuple(mensagens))


def formatar_resumo(resumo: Resumo) -> str:
    linhas = []
    for categoria, rotulo in (("erro", "ERRO"), ("aviso", "AVISO"), ("conhecida", "CONHECIDA")):
        for m in (m for m in resumo.mensagens if m.categoria == categoria):
            linhas.append(f"  [{rotulo}] {m.local}: {m.texto}")
            if m.conhecida is not None:
                linhas.append(f"      ({m.severidade} rebaixado: {m.conhecida.justificativa})")
    linhas.append(
        f"Resumo: {resumo.erros} erro(s), {resumo.avisos} aviso(s), {resumo.informacoes} informação(ões), "
        f"{resumo.conhecidas} mensagem(ns) conhecida(s) do perfil."
    )
    linhas.append("Resultado: VÁLIDO" if resumo.valido else "Resultado: INVÁLIDO")
    return "\n".join(linhas)
