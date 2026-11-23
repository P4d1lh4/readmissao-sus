"""Bloco de contagens dos atributos (S09) em Markdown, gravado em docs/atributos.md. Só agregados."""

from __future__ import annotations

from pathlib import Path

from readmissao_sus.atributos import ATRIBUTOS, ResumoAtributos
from readmissao_sus.episodios import RegraEpisodio
from readmissao_sus.formato_md import gravar_entre_marcas, milhar, pct, pct_f, tabela

COMANDO = r".venv\Scripts\python scripts\construir_banco.py"
MARCA_INICIO = "<!-- atributos:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->"
MARCA_FIM = "<!-- atributos:fim -->"
NOMES_COLISAO = {
    "pares": "Pares de episódios sobrepostos da mesma chave (toda a tabela episodio)",
    "chaves": "Chaves com episódios sobrepostos",
    "episodios_envolvidos": "Episódios envolvidos em alguma sobreposição",
    "elegiveis_chave_colidente": "Episódios elegíveis com chave_colidente",
    "elegiveis_sobrepostos": "Episódios elegíveis com episodio_sobreposto",
    "elegiveis_historico_com_obito": "Episódios elegíveis com historico_com_obito",
}


def gerar_bloco(r: ResumoAtributos, regra: RegraEpisodio, data_geracao: str) -> str:
    descricoes = {a.coluna: a.descricao for a in ATRIBUTOS}
    partes = [
        MARCA_INICIO,
        f"Gerado por `{COMANDO}` em {data_geracao}. Só agregados.",
        "",
        f"Regra dos episódios: **{regra.descricao}** "
        f"(`contiguas_sem_motivo = '{regra.contiguas_sem_motivo}'`). "
        f"Episódios elegíveis (linhas de `atributo_episodio`): **{milhar(r.episodios)}**; "
        f"readmitidos em 30 dias: {milhar(r.readmitidos)} ({pct(r.readmitidos, r.episodios)}); "
        f"sem as voltas programadas (alvo da D04): {milhar(r.nao_planejados)} "
        f"({pct(r.nao_planejados, r.episodios)}).",
        "",
        "#### Colunas: tipo e nulos",
        "",
        tabela(["Coluna", "Tipo", "Descrição", "% nulos"],
               [[f"`{c.nome}`", c.tipo, descricoes.get(c.nome, "identificador ou data (não é atributo)"),
                 pct(c.nulos, r.episodios)] for c in r.colunas]),
        "",
        "#### Efeito do início dos dados no histórico",
        "",
        _tabela_historico(r),
        "",
        "#### Colisões (D01)",
        "",
        tabela(["Item", "Valor"], [[NOMES_COLISAO[k], milhar(v)] for k, v in r.colisoes.items()]),
    ]
    for a in ATRIBUTOS:
        linhas = [[f.rotulo, milhar(f.episodios), pct(f.episodios, r.episodios), pct_f(f.taxa),
                   pct_f(f.taxa_nao_planejada)]
                  for f in r.faixas[a.coluna]]
        partes += ["", f"#### `{a.coluna}`: {a.descricao}", "",
                   tabela(["Faixa ou categoria", "Episódios", "% dos episódios", "Readmissão 30 dias",
                           "Não planejada 30 dias (D04)"], linhas)]
    partes.append(MARCA_FIM)
    return "\n".join(partes)


def gravar_bloco(caminho: Path, bloco: str) -> None:
    gravar_entre_marcas(caminho, bloco, MARCA_INICIO, MARCA_FIM, "# Atributos")


def _tabela_historico(r: ResumoAtributos) -> str:
    linhas = []
    for completo, n, com_hist, media_ep, media_dias, sem_anterior, readm, readm_com, readm_sem in (
            r.historico):
        sem_hist = n - com_hist
        linhas.append([
            "sim" if completo else "não", milhar(n), pct(com_hist, n),
            f"{media_ep:.3f}".replace(".", ","), f"{media_dias:.2f}".replace(".", ","),
            pct(sem_anterior, n), pct(readm, n), pct(readm_com, com_hist), pct(readm_sem, sem_hist),
        ])
    return tabela(
        ["historico_completo", "Episódios", "Com episódio em 365 dias", "Média episodios_365d",
         "Média dias_internado_365d", "Sem episódio anterior", "Readmissão 30 dias",
         "Readmissão com histórico", "Readmissão sem histórico"],
        linhas,
    )
