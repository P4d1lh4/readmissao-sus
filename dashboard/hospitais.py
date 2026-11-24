"""Aba Hospitais do dashboard (S11): razão O/E por CNES com IC 95%, a partir do CSV agregado."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Paleta do Health-Project, validada para daltonismo em fundo claro (azul/laranja + cinza neutro).
COR_ACIMA = "#eb6834"
COR_ABAIXO = "#2a78d6"
COR_NEUTRA = "#898781"
ACIMA = "Acima do esperado"
ABAIXO = "Abaixo do esperado"
COMPATIVEL = "Compatível com o esperado"
CORES = {ACIMA: COR_ACIMA, COMPATIVEL: COR_NEUTRA, ABAIXO: COR_ABAIXO}
ALTURA_LINHA = 18
ALTURA_MINIMA = 320
MARGEM_VERTICAL = 90


def classificar(tabela: pd.DataFrame) -> pd.Series:
    """Acima/abaixo quando o IC 95% inteiro fica de um lado de 1; senão, compatível."""
    return pd.Series(COMPATIVEL, index=tabela.index).mask(tabela["ic95_inf"] > 1, ACIMA).mask(
        tabela["ic95_sup"] < 1, ABAIXO
    )


def filtrar(tabela: pd.DataFrame, minimo_altas: int) -> pd.DataFrame:
    """Hospitais com pelo menos `minimo_altas` altas, da maior para a menor razão O/E."""
    recorte = tabela[tabela["altas"] >= minimo_altas]
    return recorte.sort_values("razao_oe", ascending=False).reset_index(drop=True)


def tabela_formatada(tabela: pd.DataFrame) -> pd.DataFrame:
    """Valores como texto no padrão brasileiro (o st.dataframe não formata assim)."""
    def numero(valor: float, casas: int) -> str:
        return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")

    return pd.DataFrame(
        {
            "CNES": tabela["cnes"],
            "Altas": tabela["altas"].map(lambda v: numero(v, 0)),
            "Observado": tabela["observado"].map(lambda v: numero(v, 0)),
            "Esperado": tabela["esperado"].map(lambda v: numero(v, 1)),
            "Razão O/E": tabela["razao_oe"].map(lambda v: numero(v, 2)),
            "IC 95%": [f"{numero(i, 2)} a {numero(s, 2)}" for i, s in zip(tabela["ic95_inf"], tabela["ic95_sup"])],
            "Leitura": classificar(tabela),
        }
    )


def grafico_oe(tabela: pd.DataFrame) -> go.Figure:
    """Ponto = razão O/E, barra = IC 95%, linha em 1 = observado igual ao esperado."""
    grupos = classificar(tabela)
    figura = go.Figure()
    for grupo, cor in CORES.items():
        parte = tabela[grupos == grupo]
        if parte.empty:
            continue
        figura.add_trace(
            go.Scatter(
                x=parte["razao_oe"],
                y=parte["cnes"],
                mode="markers",
                name=grupo,
                marker={"color": cor, "size": 8},
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": parte["ic95_sup"] - parte["razao_oe"],
                    "arrayminus": parte["razao_oe"] - parte["ic95_inf"],
                    "color": cor,
                    "thickness": 2,
                    "width": 0,
                },
                customdata=parte[["altas", "observado", "esperado", "ic95_inf", "ic95_sup"]].to_numpy(),
                hovertemplate=(
                    "CNES %{y}<br>Razão O/E %{x:.2f} (IC 95% %{customdata[3]:.2f} a %{customdata[4]:.2f})"
                    "<br>%{customdata[0]:,} altas; observado %{customdata[1]:,}, esperado %{customdata[2]:,.1f}"
                    "<extra></extra>"
                ),
            )
        )
    figura.add_vline(x=1, line_color=COR_NEUTRA, line_width=1.5, line_dash="dot")
    figura.update_layout(
        height=max(ALTURA_MINIMA, ALTURA_LINHA * len(tabela) + MARGEM_VERTICAL),
        # Eixo x no topo: com muitos hospitais o gráfico fica alto e a escala precisa estar à vista.
        xaxis={"title": "Razão observado/esperado (IC 95%)", "side": "top"},
        yaxis={
            "categoryorder": "array",
            "categoryarray": list(tabela["cnes"])[::-1],
            "range": [-0.5, len(tabela) - 0.5],
            "title": "CNES",
            "type": "category",
        },
        legend={"orientation": "h", "y": 0, "yanchor": "top", "x": 0},
        margin={"l": 10, "r": 10, "t": 70, "b": 40},
        separators=",.",
    )
    return figura
