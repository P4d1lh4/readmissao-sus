"""Treina o modelo de readmissão em 30 dias com validação temporal (S10).

Uso: .venv\\Scripts\\python scripts\\treinar.py [--fracao-cv 0.5] [--random-state 42]
Lê atributo_episodio de data/sih.duckdb (S09), treina com as altas de 2023 e testa nas de 2024
até o corte de censura. Grava o modelo em models/ (fora do git) e só agregados em reports/
(metrics.json e importancia_atributos.csv). Escolhas e números em docs/modelo.md e no README.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.treino import ler_atributos, treinar_e_salvar  # noqa: E402

BANCO = RAIZ / "data" / "sih.duckdb"
FRACAO_CV_PADRAO = 0.5
MAX_LINHAS_IMPORTANCIA = 50_000


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Treina o modelo de readmissão (S10).")
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--dir-modelo", type=Path, default=RAIZ / "models")
    parser.add_argument("--dir-relatorios", type=Path, default=RAIZ / "reports")
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--fracao-cv", type=float, default=FRACAO_CV_PADRAO,
        help="fração das chaves do treino usada na validação cruzada (padrão: %(default)s)",
    )
    args = parser.parse_args(argv)
    if not args.banco.exists():
        sys.exit(f"Banco não encontrado: {args.banco}. Rode scripts\\construir_banco.py antes.")

    inicio = time.perf_counter()
    episodios = ler_atributos(args.banco)
    print(f"{len(episodios):,} episódios lidos de {args.banco.name}", flush=True)
    metricas = treinar_e_salvar(
        episodios,
        dir_modelo=args.dir_modelo,
        dir_relatorios=args.dir_relatorios,
        random_state=args.random_state,
        fracao_cv=args.fracao_cv,
        max_linhas_importancia=MAX_LINHAS_IMPORTANCIA,
    )
    resumo = {k: metricas[k] for k in ("modelo_vencedor", "cv", "teste")}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(f"Tempo total: {time.perf_counter() - inicio:.1f} s")


if __name__ == "__main__":
    main()
