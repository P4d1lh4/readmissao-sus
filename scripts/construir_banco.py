"""Recria data/sih.duckdb do zero a partir dos Parquet e atualiza docs/coorte.md e docs/atributos.md.

Uso: .venv\\Scripts\\python scripts\\construir_banco.py [--contiguas-sem-motivo REGRA]
     [--sem-permanencia]
Lê data/parquet/RDPE*.parquet e roda o SQL de sql/ (staging, internações, coorte, episódios,
atributos).
O sal da chave de linkage vem da variável READMISSAO_SAL_CHAVE ou de data/sal_chave.txt
(criado na primeira vez; fora do git). A regra dos episódios tem padrão em
readmissao_sus.episodios.REGRA_PADRAO (D03 em docs/decisoes.md). O documento recebe só agregados.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus import relatorio_atributos, relatorio_coorte, relatorio_episodios  # noqa: E402
from readmissao_sus.banco import construir_banco, obter_sal  # noqa: E402
from readmissao_sus.episodios import CONTIGUAS_SEM_MOTIVO, REGRA_PADRAO, RegraEpisodio  # noqa: E402

DIR_PARQUET = RAIZ / "data" / "parquet"
BANCO = RAIZ / "data" / "sih.duckdb"
ARQUIVO_SAL = RAIZ / "data" / "sal_chave.txt"
DOC_COORTE = RAIZ / "docs" / "coorte.md"
DOC_ATRIBUTOS = RAIZ / "docs" / "atributos.md"


def ler_regra(argv: list[str] | None = None) -> RegraEpisodio:
    parser = argparse.ArgumentParser(description="Recria data/sih.duckdb a partir dos Parquet.")
    parser.add_argument(
        "--contiguas-sem-motivo", choices=CONTIGUAS_SEM_MOTIVO,
        default=REGRA_PADRAO.contiguas_sem_motivo,
        help="regra da D03 para alta seguida de nova AIH em 0–1 dia (padrão: %(default)s)",
    )
    parser.add_argument(
        "--sem-permanencia", action="store_true",
        help="não junta a saída por permanência (COBRANCA 21–28) à AIH seguinte",
    )
    args = parser.parse_args(argv)
    return RegraEpisodio(
        juntar_permanencia=REGRA_PADRAO.juntar_permanencia and not args.sem_permanencia,
        contiguas_sem_motivo=args.contiguas_sem_motivo,
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    regra = ler_regra()
    arquivos = sorted(DIR_PARQUET.glob("RDPE*.parquet"))
    if not arquivos:
        print(f"ERRO: nenhum RDPE*.parquet em {DIR_PARQUET}. Rode scripts/baixar_sih.py antes.",
              file=sys.stderr)
        return 1
    construcao = construir_banco(BANCO, arquivos, obter_sal(ARQUIVO_SAL), regra)
    hoje = date.today().strftime("%d/%m/%Y")
    blocos = [
        (relatorio_coorte, relatorio_coorte.gerar_bloco(construcao, hoje)),
        (relatorio_episodios, relatorio_episodios.gerar_bloco(construcao.episodios, hoje)),
    ]
    for modulo, bloco in blocos:
        modulo.gravar_bloco(DOC_COORTE, bloco)
        print(bloco, end="\n\n")
    bloco_atributos = relatorio_atributos.gerar_bloco(construcao.atributos, regra, hoje)
    relatorio_atributos.gravar_bloco(DOC_ATRIBUTOS, bloco_atributos)
    print(f"Banco recriado em {BANCO.relative_to(RAIZ)} a partir de {len(arquivos)} arquivos.")
    print(f"Regra dos episódios: {regra.descricao}.")
    print(f"Blocos gravados em {DOC_COORTE.relative_to(RAIZ)} e {DOC_ATRIBUTOS.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
