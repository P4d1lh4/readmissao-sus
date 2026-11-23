"""Inventário agregado das colunas do SIH-RD (sem nenhum registro individual)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from readmissao_sus.dbf import CampoDbf, ler_campos_parquet

CAMPOS_ALVO = (
    "N_AIH", "IDENT", "NASC", "SEXO", "CEP", "MUNIC_RES", "DT_INTER", "DT_SAIDA",
    "DIAG_PRINC", "PROC_REA", "CNES", "MORTE", "CAR_INT", "COBRANCA", "UTI_MES_TO", "IDADE",
)
CAMPOS_CODIFICADOS = ("IDENT", "MORTE", "COBRANCA", "CAR_INT")


@dataclass(frozen=True)
class ResumoArquivo:
    ano: int
    linhas: int
    tipos: dict[str, str]
    nulos: dict[str, int]
    frequencias: dict[str, Counter] = field(default_factory=dict)


@dataclass(frozen=True)
class Inventario:
    linhas_por_ano: dict[int, int]
    tipos: dict[str, set[str]]
    nulos_por_ano: dict[str, dict[int, int]]
    frequencias: dict[str, Counter]

    @property
    def total_linhas(self) -> int:
        return sum(self.linhas_por_ano.values())


def ano_do_arquivo(nome: str) -> int:
    """RDPE2301 -> 2023 (o aamm do nome é a competência de processamento)."""
    return 2000 + int(Path(nome).stem[4:6])


def resumir(df: pd.DataFrame, campos: list[CampoDbf], ano: int) -> ResumoArquivo:
    """Contagens de um arquivo: nulos/vazios dos campos-alvo presentes e frequências dos códigos."""
    tipos_dbf = {c.nome: c.tipo_legivel for c in campos}
    presentes = [c for c in CAMPOS_ALVO if c in df.columns]
    nulos = {c: int(_nulo_ou_vazio(df[c]).sum()) for c in presentes}
    tipos = {c: tipos_dbf.get(c, str(df[c].dtype)) for c in presentes}
    frequencias = {
        c: Counter(df[c].fillna("(nulo)").astype(str).value_counts().to_dict())
        for c in CAMPOS_CODIFICADOS
        if c in df.columns
    }
    return ResumoArquivo(ano, len(df), tipos, nulos, frequencias)


def consolidar(resumos: list[ResumoArquivo]) -> Inventario:
    linhas: Counter = Counter()
    tipos: dict[str, set[str]] = {}
    nulos: dict[str, dict[int, int]] = {}
    frequencias: dict[str, Counter] = {}
    for r in resumos:
        linhas[r.ano] += r.linhas
        for campo, tipo in r.tipos.items():
            tipos.setdefault(campo, set()).add(tipo)
        for campo, n in r.nulos.items():
            por_ano = nulos.setdefault(campo, {})
            por_ano[r.ano] = por_ano.get(r.ano, 0) + n
        for campo, cont in r.frequencias.items():
            frequencias[campo] = frequencias.get(campo, Counter()) + cont
    return Inventario(dict(sorted(linhas.items())), tipos, nulos, frequencias)


def inventariar_parquets(arquivos: list[Path]) -> Inventario:
    resumos = []
    for caminho in sorted(arquivos):
        nomes = pq.read_schema(caminho).names
        colunas = [c for c in dict.fromkeys(CAMPOS_ALVO + CAMPOS_CODIFICADOS) if c in nomes]
        df = pq.read_table(caminho, columns=colunas).to_pandas()
        df = _completar_linhas(df, pq.ParquetFile(caminho).metadata.num_rows)
        resumos.append(resumir(df, ler_campos_parquet(caminho), ano_do_arquivo(caminho.name)))
    return consolidar(resumos)


def tabela_campos_md(inv: Inventario) -> str:
    anos = list(inv.linhas_por_ano)
    cabecalho = ["Campo", "Existe", "Tipo no DBF"] + [f"% nulos/vazios {a}" for a in anos] + ["% nulos/vazios total"]
    linhas = [_linha_md(cabecalho), _linha_md(["---"] * len(cabecalho))]
    for campo in CAMPOS_ALVO:
        if campo not in inv.tipos:
            linhas.append(_linha_md([campo, "não", "—"] + ["—"] * (len(anos) + 1)))
            continue
        por_ano = inv.nulos_por_ano[campo]
        pcts = [_pct(por_ano.get(a, 0), inv.linhas_por_ano[a]) for a in anos]
        total = _pct(sum(por_ano.values()), inv.total_linhas)
        tipo = ", ".join(sorted(inv.tipos[campo]))
        linhas.append(_linha_md([campo, "sim", tipo] + pcts + [total]))
    return "\n".join(linhas)


def tabela_linhas_md(inv: Inventario, arquivos_por_ano: dict[int, int]) -> str:
    linhas = [_linha_md(["Ano (competência)", "Arquivos", "Linhas"]), _linha_md(["---", "---:", "---:"])]
    for ano, n in inv.linhas_por_ano.items():
        linhas.append(_linha_md([str(ano), str(arquivos_por_ano.get(ano, 0)), _milhar(n)]))
    linhas.append(_linha_md(["**Total**", str(sum(arquivos_por_ano.values())), f"**{_milhar(inv.total_linhas)}**"]))
    return "\n".join(linhas)


def tabela_frequencias_md(inv: Inventario, campo: str, rotulos: dict[str, str]) -> str:
    cont = inv.frequencias.get(campo, Counter())
    total = sum(cont.values())
    linhas = [_linha_md(["Código", "Significado", "Linhas", "%"]), _linha_md(["---", "---", "---:", "---:"])]
    for codigo, n in sorted(cont.items(), key=lambda kv: (-kv[1], kv[0])):
        linhas.append(_linha_md([codigo, rotulos.get(codigo, "(fora da tabela oficial)"), _milhar(n), _pct(n, total)]))
    return "\n".join(linhas)


def _completar_linhas(df: pd.DataFrame, n_linhas: int) -> pd.DataFrame:
    # Quando nenhum campo-alvo existe, o DataFrame vem sem linhas; mantém a contagem real.
    if df.columns.empty:
        return pd.DataFrame(index=range(n_linhas))
    return df


def _nulo_ou_vazio(serie: pd.Series) -> pd.Series:
    return serie.isna() | (serie.astype("string").str.strip() == "").fillna(False)


def _pct(parte: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{100 * parte / total:.2f}%".replace(".", ",")


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _linha_md(celulas: list[str]) -> str:
    return "| " + " | ".join(celulas) + " |"
