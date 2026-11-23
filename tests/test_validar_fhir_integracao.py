"""Roda scripts/validar_fhir.py de verdade (Docker + validador HL7) nos exemplos de fhir/exemplos/.

Fora da suíte padrão (pytest.ini). Rodar com: .venv\\Scripts\\python -m pytest -m integracao
Pulado se o Docker não estiver instalado ou o daemon não responder.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "validar_fhir.py"
EXEMPLOS = RAIZ / "fhir" / "exemplos"
TIMEOUT_DOCKER_S = 60
TIMEOUT_VALIDADOR_S = 900


def _docker_disponivel() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, timeout=TIMEOUT_DOCKER_S
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.integracao


@pytest.fixture(scope="module", autouse=True)
def _exige_docker():
    # Checado só quando o teste roda: na suíte padrão (deselecionado) não chama o Docker.
    if not _docker_disponivel():
        pytest.skip("Docker ausente ou parado")


def _validar(nome: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(EXEMPLOS / nome)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT_VALIDADOR_S,
    )


def test_exemplo_valido_passa_sem_erros():
    resultado = _validar("sumario-alta-valido.json")

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "Resumo: 0 erro(s)" in resultado.stdout
    assert "Resultado: VÁLIDO" in resultado.stdout


def test_exemplo_invalido_falha_com_os_erros_esperados():
    resultado = _validar("sumario-alta-invalido.json")

    assert resultado.returncode == 1, resultado.stdout + resultado.stderr
    assert "Resultado: INVÁLIDO" in resultado.stdout
    # Erro 1: falta a seção obrigatória "Procedimento(s)" (slice procedimento, min 1).
    assert "Slice 'Composition.section:procedimento': a matching slice is required" in resultado.stdout
    # Erro 2: I5099 não existe na CID-10 da RNDS (CodeSystem BRCID10, completo no pacote reds-go).
    assert "Unknown code 'I5099' in the CodeSystem 'http://www.saude.gov.br/fhir/r4/CodeSystem/BRCID10'" in resultado.stdout
