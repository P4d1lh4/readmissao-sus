"""Texto "Como ler a tabela" da aba Hospitais, com exemplos tirados do próprio CSV."""

from __future__ import annotations

import pandas as pd

from dashboard.hospitais import ACIMA, COMPATIVEL, classificar, numero

TITULO = "Como ler a tabela"

COLUNAS = """
Cada linha é um hospital, pelo CNES. A linha compara quantas altas desse hospital voltaram com
quantas o modelo esperava.

| Coluna | O que significa |
| --- | --- |
| **CNES** | código do hospital da alta |
| **Altas** | quantas altas o hospital teve no período |
| **Observado** | quantas dessas altas voltaram ao hospital (qualquer um) sem planejamento em até 30 dias |
| **Esperado** | quantas o modelo previa que voltassem, somando o risco de cada paciente |
| **Razão O/E** | observado ÷ esperado. 1 = como previsto; 2 = o dobro; 0,5 = a metade |
| **IC 95%** | a faixa de incerteza da razão. Hospital pequeno tem faixa larga |
| **Leitura** | "Acima" se a faixa inteira fica acima de 1, "Abaixo" se fica inteira abaixo de 1, "Compatível" se a faixa cruza o 1 |
"""

CUIDADOS = """
**O que a tabela não diz:**

- **Ela não diz que um hospital é pior que outro.** O hospital da alta é um dos atributos do modelo.
  Por isso, o esperado já leva em conta parte do jeito de cada hospital, e a razão mostra só o que
  sobrou além do que o modelo aprendeu com 2023. Para comparar hospitais seria preciso um modelo de
  ajuste de risco feito para isso, sem o hospital, e com dados clínicos que o SIH não tem.
- **Parte dos destaques é acaso.** Muitos hospitais são testados ao mesmo tempo, então alguns ficam
  "acima" ou "abaixo" só pela sorte.
- **A volta pode ser em outro hospital.** O observado conta a readmissão onde quer que ela aconteça.
  A volta é atribuída ao hospital que deu a alta, não ao que recebeu o paciente.
- **Pode haver erro de linkage.** Num hospital cujos pacientes têm muitos CEPs genéricos, pessoas
  diferentes podem ser contadas como a mesma, e isso infla o observado.

Em resumo, a tabela serve para **apontar onde olhar com mais atenção**, e não para montar um ranking
de qualidade.
"""


def _descrever(linha: pd.Series) -> str:
    return (
        f"**{linha['cnes']}**: {numero(linha['altas'], 0)} altas, {numero(linha['observado'], 0)} voltas "
        f"contra {numero(linha['esperado'], 1)} esperadas, razão **{numero(linha['razao_oe'], 2)}** "
        f"(IC de {numero(linha['ic95_inf'], 2)} a {numero(linha['ic95_sup'], 2)})"
    )


def exemplos(tabela: pd.DataFrame) -> list[str]:
    """Até três exemplos: o "acima" mais claro, um "acima" pequeno e um "compatível" de razão alta.

    O mais claro é o "acima" cuja faixa inteira fica mais longe de 1 (maior limite inferior do IC).
    O "compatível" mostra que a razão sozinha engana: ela pode ser alta e a faixa ainda cruzar o 1.
    """
    leitura = classificar(tabela)
    acima = tabela[leitura == ACIMA]
    compativel = tabela[leitura == COMPATIVEL]
    frases = []
    if not acima.empty:
        claro = acima.loc[acima["ic95_inf"].idxmax()]
        frases.append(
            f"- {_descrever(claro)}. É o caso mais claro: mesmo o limite de baixo da faixa fica acima "
            f"de 1. Voltaram cerca de {numero(claro['razao_oe'], 1)} vezes os pacientes que o modelo previa."
        )
        pequeno = acima.loc[acima["altas"].idxmin()]
        if pequeno["cnes"] != claro["cnes"]:
            frases.append(
                f"- {_descrever(pequeno)}. Também fica acima, mas, com poucas altas, a faixa é larga."
            )
    if not compativel.empty:
        alto = compativel.loc[compativel["razao_oe"].idxmax()]
        if alto["razao_oe"] > 1:
            frases.append(
                f"- {_descrever(alto)}. A razão é alta, mas a faixa cruza o 1, então fica "
                "**\"Compatível\"**: pode ser acaso. A razão sozinha engana; é a faixa de incerteza que "
                "diz se a diferença é real."
            )
    return frases


def texto(tabela: pd.DataFrame) -> str:
    """O texto inteiro, em Markdown, para o recorte que está na tela."""
    lista = exemplos(tabela)
    trecho_exemplos = ("\n**Exemplos desta tabela:**\n\n" + "\n".join(lista) + "\n") if lista else ""
    return COLUNAS + trecho_exemplos + CUIDADOS
