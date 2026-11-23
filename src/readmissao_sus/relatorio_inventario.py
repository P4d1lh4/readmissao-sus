"""Monta docs/inventario-sih.md a partir do inventário agregado."""

from __future__ import annotations

from readmissao_sus import dicionario_sih as dic
from readmissao_sus.inventario import Inventario, tabela_campos_md, tabela_frequencias_md, tabela_linhas_md


def gerar_documento(inv: Inventario, arquivos_por_ano: dict[int, int], data_geracao: str) -> str:
    transf = ", ".join(sorted(dic.COBRANCA_TRANSFERENCIA))
    obito = ", ".join(sorted(dic.COBRANCA_OBITO))
    partes = [
        "# Inventário do SIH-RD — Pernambuco, 2023–2024",
        "",
        f"Gerado por `scripts/baixar_sih.py` em {data_geracao}. Contém só agregados; "
        "nenhum registro individual sai de `data/`.",
        "",
        "Arquivos: `RDPEaamm.dbc` do FTP do DATASUS "
        "(`ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados`). "
        "O `aamm` do nome é a **competência de processamento** da AIH, não o mês da alta: "
        "um arquivo de 2023 pode trazer saídas de 2022, e AIHs de saídas de dezembro/2024 "
        "podem aparecer só em competências de 2025.",
        "",
        "## Linhas por ano",
        "",
        tabela_linhas_md(inv, arquivos_por_ano),
        "",
        "## Campos usados no projeto",
        "",
        "Tipo é o declarado no cabeçalho do DBF. No Parquet bruto (`data/parquet/`) todos os campos "
        "ficam como texto, sem espaços nas pontas e com vazio convertido em nulo; a tipagem é feita "
        "depois. \"% nulos/vazios\" conta nulos e textos vazios.",
        "",
        "Observação: o informe técnico chama a data de internação de `DI_INTER`, mas nos arquivos o "
        "campo se chama `DT_INTER`.",
        "",
        tabela_campos_md(inv),
        "",
        "## Dicionário: IDENT, MORTE e COBRANCA",
        "",
        "- **IDENT** — char(1), \"Identificação do tipo da AIH\". Códigos: `1` = Normal, "
        "`5` = Longa permanência (demais valores o TabWin agrupa como \"Outras/ignorado\").",
        "- **MORTE** — numeric(1), \"Indica Óbito\". Códigos: `1` = Com óbito, `0` = Sem óbito.",
        "- **COBRANCA** — char(2), \"Motivo de Saída/Permanência\". Códigos 1x = alta, 2x = permanência, "
        f"3x = transferência, 4x = óbito, 51 = encerramento administrativo, 6x = parto (mãe e recém-nascido). "
        f"Transferência: {transf}. Óbito: {obito} (63 e 64 são alta da mãe com óbito do recém-nascido/fetal).",
        "",
        "Fontes:",
        "",
        f"- Layout e descrição dos campos: {dic.FONTE_LAYOUT}.",
        f"- Códigos: {dic.FONTE_CODIGOS}.",
        "",
        "### Distribuição de IDENT",
        "",
        tabela_frequencias_md(inv, "IDENT", dic.IDENT),
        "",
        "### Distribuição de MORTE",
        "",
        tabela_frequencias_md(inv, "MORTE", dic.MORTE),
        "",
        "### Distribuição de COBRANCA (motivo de saída/permanência)",
        "",
        tabela_frequencias_md(inv, "COBRANCA", dic.COBRANCA),
        "",
        "### Distribuição de CAR_INT (caráter da internação)",
        "",
        tabela_frequencias_md(inv, "CAR_INT", dic.CAR_INT),
        "",
    ]
    return "\n".join(partes)
