"""Gera reports/hospitais_oe.csv: razão observado/esperado por hospital no teste 2024 (S11, S14).

Uso: .venv\\Scripts\\python scripts\\razao_hospitais.py [--minimo-altas 100] [--random-state 42]
Lê as altas de 2023 e do teste 2024 de atributo_episodio (data/sih.duckdb, só leitura). O
esperado vem do modelo de ajuste de risco, sem o hospital da alta (D05): treinado com 2023,
aplicado ao teste e recalibrado no total do ano. Grava só agregados por CNES (altas, observado,
esperado, razão O/E e IC 95% de Poisson exato) e, em reports/hospitais_ajuste.json, o resumo do
ajuste. Se houver modelo em models/, o JSON também conta as leituras com o esperado do modelo
principal, para comparar. Nenhuma probabilidade por episódio é gravada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from readmissao_sus.ajuste_risco import (  # noqa: E402
    ATRIBUTOS_CATEGORICOS_AJUSTE,
    MODELO_AJUSTE,
    pontuar_ajustado,
    treinar_ajuste,
)
from readmissao_sus.artefatos import carregar_artefatos  # noqa: E402
from readmissao_sus.modelagem import ATRIBUTOS_BINARIOS, ATRIBUTOS_NUMERICOS  # noqa: E402
from readmissao_sus.razao_oe import (  # noqa: E402
    MINIMO_ALTAS,
    contar_leituras,
    ler_treino_e_teste,
    pontuar,
    razao_por_hospital,
)
from readmissao_sus.treino import ARQUIVO_METADATA  # noqa: E402

BANCO = RAIZ / "data" / "sih.duckdb"
DIR_MODELO = RAIZ / "models"
SAIDA = RAIZ / "reports" / "hospitais_oe.csv"
NOME_RESUMO = "hospitais_ajuste.json"


def _comparar_com_modelo_principal(
    dir_modelo: Path, teste: pd.DataFrame, minimo_altas: int
) -> dict[str, int] | None:
    """Leituras com o esperado do modelo principal (com o hospital), se houver modelo salvo."""
    if not (dir_modelo / ARQUIVO_METADATA).is_file():
        return None
    artefatos = carregar_artefatos(dir_modelo)
    return contar_leituras(razao_por_hospital(pontuar(artefatos.pipeline, teste), minimo_altas))


def _resumo(
    tabela: pd.DataFrame, teste: pd.DataFrame, treino_altas: int, fator: float, roc: float,
    principal: dict[str, int] | None, random_state: int,
) -> dict[str, Any]:
    return {
        "metodo": (
            f"esperado = probabilidade de um {MODELO_AJUSTE} sem o hospital da alta, treinado com as "
            "altas de 2023 e aplicado ao teste 2024, multiplicada pelo fator de recalibração (D05)"
        ),
        "atributos": [*ATRIBUTOS_NUMERICOS, *ATRIBUTOS_BINARIOS, *ATRIBUTOS_CATEGORICOS_AJUSTE],
        "random_state": random_state,
        "treino_altas": treino_altas,
        "teste_altas": int(len(teste)),
        "roc_auc_teste_ajuste": roc,
        "fator_recalibracao": fator,
        "hospitais": int(len(tabela)),
        "altas_nos_hospitais": int(tabela["altas"].sum()),
        "observado_nos_hospitais": int(tabela["observado"].sum()),
        "esperado_nos_hospitais": float(tabela["esperado"].sum()),
        "leituras_ajuste": contar_leituras(tabela),
        "leituras_modelo_principal": principal,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Razão O/E de readmissão por hospital, com ajuste de risco.")
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--dir-modelo", type=Path, default=DIR_MODELO,
                        help="modelo principal, só para comparar as leituras (opcional)")
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--minimo-altas", type=int, default=MINIMO_ALTAS)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args(argv)
    if not args.banco.is_file():
        sys.exit(f"Banco não encontrado: {args.banco}. Rode scripts\\construir_banco.py antes.")

    with duckdb.connect(str(args.banco), read_only=True) as con:
        treino, teste = ler_treino_e_teste(con)
    print(f"Ajuste de risco: treino com {len(treino):,} altas de 2023", flush=True)
    ajustadas = pontuar_ajustado(treinar_ajuste(treino, args.random_state), teste)
    tabela = razao_por_hospital(ajustadas.altas, args.minimo_altas)
    principal = _comparar_com_modelo_principal(args.dir_modelo, teste, args.minimo_altas)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(args.saida, index=False, float_format="%.6f")
    resumo = _resumo(tabela, teste, len(treino), ajustadas.fator_recalibracao, ajustadas.roc_auc_teste,
                     principal, args.random_state)
    (args.saida.parent / NOME_RESUMO).write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"{len(teste):,} altas do teste; {len(tabela)} hospitais com >= {args.minimo_altas} altas "
        f"gravados em {args.saida}. ROC-AUC do ajuste {ajustadas.roc_auc_teste:.3f}; fator "
        f"{ajustadas.fator_recalibracao:.3f}; leituras {resumo['leituras_ajuste']} "
        f"(modelo principal: {principal})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
