"""Bloco de contagens dos episódios (S07) em Markdown, gravado em docs/coorte.md. Só agregados."""

from __future__ import annotations

from pathlib import Path

from readmissao_sus.episodios import (
    DIAS_CONTIGUIDADE, REGRA_PADRAO, REGRA_PROPOSTA_D03, Episodios, RegraEpisodio,
)
from readmissao_sus.formato_md import gravar_entre_marcas, milhar, pct, pct_f, tabela

COMANDO = r".venv\Scripts\python scripts\construir_banco.py"
MARCA_INICIO = "<!-- episodios:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->"
MARCA_FIM = "<!-- episodios:fim -->"
NOME_TIPO = {
    "transferencia": "Transferência (29, 31, 32)",
    "permanencia": "Permanência (21–28)",
    "sem_motivo": "Outras saídas sem óbito (alta, 51, 6x)",
}
TITULOS_RESUMO = {
    "juncao": "Internações x episódios",
    "tamanho": "Internações por episódio",
    "desfecho": "Desfecho, censura e marcas (coorte_episodio)",
}


def gerar_bloco(e: Episodios, data_geracao: str) -> str:
    partes = [
        MARCA_INICIO,
        f"Gerado por `{COMANDO}` em {data_geracao}. Só agregados.",
        "",
        f"Regra usada nas tabelas do banco: **{e.regra.descricao}** "
        f"(`juntar_permanencia = {e.regra.juntar_permanencia}`, "
        f"`contiguas_sem_motivo = '{e.regra.contiguas_sem_motivo}'`). "
        f"Contígua = nova AIH da mesma chave em 0–{DIAS_CONTIGUIDADE} dia após a saída.",
    ]
    for secao, titulo in TITULOS_RESUMO.items():
        linhas = [[item, milhar(n)] for item, n in e.resumo.get(secao, [])]
        partes += ["", f"#### {titulo}", "", tabela(["Item", "Valor"], linhas)]
        if secao == "juncao":
            partes += ["", "#### Saídas sem óbito por motivo", "", _tabela_motivos(e)]
    partes += ["", "#### Readmissão em 30 dias por episódio", "", _tabela_readmissao(e)]
    partes += ["", "#### Comparação das regras", "", _tabela_comparacao(e)]
    partes += ["", "#### Contíguas sem motivo (D03)", "", _tabela_sem_motivo(e)]
    partes += ["", "Pares de procedimento mais frequentes nas contíguas sem motivo:", "",
               _tabela_procedimentos(e)]
    partes.append(MARCA_FIM)
    return "\n".join(partes)


def gravar_bloco(caminho: Path, bloco: str) -> None:
    gravar_entre_marcas(caminho, bloco, MARCA_INICIO, MARCA_FIM, "# Coorte")


def _tabela_motivos(e: Episodios) -> str:
    linhas = [
        [NOME_TIPO.get(tipo, tipo), milhar(saidas), milhar(candidatas), milhar(juntadas),
         pct(juntadas, saidas)]
        for tipo, saidas, candidatas, juntadas in e.motivos
    ]
    return tabela(["Motivo da saída", "Saídas", "Seguidas de nova AIH em 0–1 dia", "Juntadas",
                   "% juntadas"], linhas)


def _tabela_readmissao(e: Episodios) -> str:
    itens = dict(e.resumo.get("readmissao", []))
    altas = itens.get("Altas-índice (episódios elegíveis)", 0)
    linhas = [[item, milhar(n)] for item, n in e.resumo.get("readmissao", [])]
    readmitidas = itens.get("Readmitidas em 30 dias", 0)
    linhas.insert(2, ["Taxa de readmissão em 30 dias", pct(readmitidas, altas)])
    return tabela(["Item", "Valor"], linhas)


def _tabela_comparacao(e: Episodios) -> str:
    linhas = [
        [_nome_regra(c.regra), milhar(c.internacoes), milhar(c.episodios),
         milhar(c.altas_indice), milhar(c.readmitidas), pct_f(c.taxa)]
        for c in e.comparacao
    ]
    texto = tabela(["Regra", "Internações", "Episódios", "Altas-índice", "Readmitidas",
                    "Taxa 30 dias"], linhas)
    return texto + (
        "\n\nReferência (D01, por internação, sem juntar): 20,32% bruta; 11,82% tirando as "
        "altas-índice seguidas de contígua após transferência ou permanência."
    )


def _nome_regra(regra: RegraEpisodio) -> str:
    marcas = []
    if regra == REGRA_PADRAO:
        marcas.append("padrão")
    if regra == REGRA_PROPOSTA_D03:
        marcas.append("proposta D03")
    sufixo = f" ({', '.join(marcas)})" if marcas else ""
    return regra.descricao + sufixo


def _tabela_sem_motivo(e: Episodios) -> str:
    linhas = []
    for grupo, mesmo_hospital, pares, dia0, cid, proc, grupo_proc, eletiva in e.sem_motivo:
        linhas.append([
            grupo, "mesmo" if mesmo_hospital else "outro", milhar(pares), pct(dia0, pares),
            pct(cid, pares), pct(proc, pares), pct(grupo_proc, pares), pct(eletiva, pares),
        ])
    total = sum(linha[2] for linha in e.sem_motivo)
    texto = tabela(["Saída anterior", "Hospital", "Pares", "Mesmo dia", "Mesmo CID (3 car.)",
                    "Mesmo procedimento", "Mesmo grupo SIGTAP", "Seguinte eletiva"], linhas)
    return texto + (
        f"\n\nTotal: {milhar(total)} pares em toda a base (a primeira AIH seguinte de cada "
        "saída). O item \"Contíguas sem motivo com saída anterior no período\" acima restringe "
        "ao período das altas-índice, para comparar com a D01."
    )


def _tabela_procedimentos(e: Episodios) -> str:
    linhas = [[a, b, "mesmo" if mesmo else "outro", milhar(n)]
              for a, b, mesmo, n in e.procedimentos]
    return tabela(["Procedimento anterior", "Procedimento seguinte", "Hospital", "Pares"], linhas)
