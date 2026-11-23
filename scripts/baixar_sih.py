"""Baixa o SIH-RD de PE (2023–2024), converte para Parquet e gera docs/inventario-sih.md.

Uso: .venv\\Scripts\\python scripts\\baixar_sih.py
Idempotente: o que já existe em data/raw/ e data/parquet/ não é refeito.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.datasus_ftp import BaixadorFtp, ErroDownload, baixar_faltantes, nomes_arquivos_rd  # noqa: E402
from readmissao_sus.dbf import dbc_para_parquet  # noqa: E402
from readmissao_sus.inventario import ano_do_arquivo, inventariar_parquets  # noqa: E402
from readmissao_sus.relatorio_inventario import gerar_documento  # noqa: E402

UF = "PE"
ANOS = (2023, 2024)
DIR_RAW = RAIZ / "data" / "raw"
DIR_PARQUET = RAIZ / "data" / "parquet"
INVENTARIO = RAIZ / "docs" / "inventario-sih.md"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    nomes = nomes_arquivos_rd(UF, ANOS)

    baixador = BaixadorFtp()
    try:
        baixados = baixar_faltantes(nomes, DIR_RAW, baixador)
    except ErroDownload as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    finally:
        baixador.fechar()
    print(f"Download: {len(baixados)} arquivo(s) baixado(s), {len(nomes) - len(baixados)} já existiam.")

    parquets = []
    for nome in nomes:
        destino = DIR_PARQUET / (Path(nome).stem + ".parquet")
        if not destino.exists():
            linhas = dbc_para_parquet(DIR_RAW / nome, destino)
            print(f"Convertido {nome} -> {destino.name} ({linhas} linhas)")
        parquets.append(destino)

    inv = inventariar_parquets(parquets)
    arquivos_por_ano = Counter(ano_do_arquivo(p.name) for p in parquets)
    INVENTARIO.parent.mkdir(parents=True, exist_ok=True)
    INVENTARIO.write_text(
        gerar_documento(inv, dict(arquivos_por_ano), date.today().strftime("%d/%m/%Y")),
        encoding="utf-8",
    )
    print(f"Inventário gravado em {INVENTARIO.relative_to(RAIZ)}")
    for ano, n in inv.linhas_por_ano.items():
        print(f"  {ano}: {n} linhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
