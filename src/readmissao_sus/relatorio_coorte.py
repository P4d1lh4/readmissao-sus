"""Bloco de contagens da coorte (S06) em Markdown, gravado em docs/coorte.md. Só agregados."""

from __future__ import annotations

from pathlib import Path

from readmissao_sus.banco import Construcao
from readmissao_sus.cobertura import JANELA_DIAS
from readmissao_sus.formato_md import data, gravar_entre_marcas, milhar, tabela

COMANDO = r".venv\Scripts\python scripts\construir_banco.py"
MARCA_INICIO = "<!-- coorte:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->"
MARCA_FIM = "<!-- coorte:fim -->"
TITULOS_DETALHE = {
    "ident": "Filtro 1: AIHs IDENT = 5 e outros",
    "datas": "Qualidade das datas (linhas IDENT = 1, antes da deduplicação)",
    "obito": "Filtro 4: óbitos",
    "marcas": "Marcas na coorte (não removem linhas)",
}


def gerar_bloco(c: Construcao, data_geracao: str) -> str:
    cob = c.cobertura
    partes = [
        MARCA_INICIO,
        f"Gerado por `{COMANDO}` em {data_geracao}. Só agregados.",
        "",
        "#### Filtros, em ordem",
        "",
        tabela(["#", "Filtro", "Antes", "Removidas", "Depois"],
               [[str(o), etapa, milhar(a), milhar(r), milhar(d)] for o, etapa, a, r, d in c.filtros]),
        "",
        f"Linhas na coorte (tabela `coorte`): **{milhar(c.filtros[-1][4])}**.",
        "",
        f"Período das altas-índice: saída de {data(cob.inicio)} a **{data(cob.limite_indice)}** "
        f"(última competência {cob.ultima_competencia}; cobertura completa até {data(cob.fim)}; "
        f"corte = fim da cobertura − {JANELA_DIAS} dias).",
    ]
    for secao, titulo in TITULOS_DETALHE.items():
        linhas = [[item, milhar(n)] for item, n in c.detalhes.get(secao, [])]
        partes += ["", f"#### {titulo}", "", tabela(["Item", "Linhas"], linhas)]
    partes.append(MARCA_FIM)
    return "\n".join(partes)


def gravar_bloco(caminho: Path, bloco: str) -> None:
    gravar_entre_marcas(caminho, bloco, MARCA_INICIO, MARCA_FIM, "# Coorte")
