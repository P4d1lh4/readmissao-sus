"""Dashboard Streamlit do projeto (S11). Só lê agregados de reports/; nada por episódio.

Subir (na raiz do projeto):
    .venv\\Scripts\\python -m streamlit run dashboard\\app.py

O CSV da aba Hospitais vem de scripts/razao_hospitais.py; o caminho pode ser trocado por
READMISSAO_HOSPITAIS_CSV.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import hospitais, leitura  # noqa: E402

CSV_HOSPITAIS = Path(os.environ.get("READMISSAO_HOSPITAIS_CSV", RAIZ / "reports" / "hospitais_oe.csv"))
DICA_GERAR = "Rode `.venv\\Scripts\\python scripts\\razao_hospitais.py` para gerar `reports/hospitais_oe.csv`."
PASSO_ALTAS = 50

st.set_page_config(page_title="Readmissão SUS", layout="wide")


@st.cache_data
def ler_hospitais(caminho: str) -> pd.DataFrame:
    return pd.read_csv(caminho, dtype={"cnes": str})


def aba_hospitais(tabela: pd.DataFrame) -> None:
    st.caption(
        "Altas de 2024 até 01/10/2024, pelo hospital da alta. Observado = readmissões não planejadas em "
        "30 dias; esperado = quantas voltariam se os pacientes do hospital tivessem a taxa de pacientes "
        "de perfil parecido no estado. Razão acima de 1: mais readmissões do que pacientes parecidos "
        "tiveram em média. IC 95% de Poisson exato."
    )
    st.caption(
        "O esperado vem de um modelo de ajuste de risco sem o hospital (D05): idade, sexo, diagnóstico, "
        "procedimento, caráter, permanência, UTI e histórico. Ele não tem gravidade clínica, que o SIH "
        "não registra."
    )
    minimo_csv = int(tabela["altas"].min())
    minimo = st.number_input(
        "Mínimo de altas por hospital", min_value=minimo_csv, value=minimo_csv, step=PASSO_ALTAS
    )
    recorte = hospitais.filtrar(tabela, int(minimo))
    if recorte.empty:
        st.warning("Nenhum hospital com esse mínimo de altas.")
        return
    contagem = hospitais.classificar(recorte).value_counts()
    st.markdown(
        f"**{len(recorte)} hospitais**: {contagem.get(hospitais.ACIMA, 0)} acima do esperado, "
        f"{contagem.get(hospitais.ABAIXO, 0)} abaixo e {contagem.get(hospitais.COMPATIVEL, 0)} compatíveis."
    )
    st.plotly_chart(hospitais.grafico_oe(recorte), width="stretch")
    with st.expander(leitura.TITULO, expanded=True):
        st.markdown(leitura.texto(recorte))
    st.dataframe(hospitais.tabela_formatada(recorte), hide_index=True, width="stretch")


def main() -> None:
    st.title("Readmissão não planejada em 30 dias (SIH/SUS, PE)")
    [aba] = st.tabs(["Hospitais"])
    with aba:
        if not CSV_HOSPITAIS.is_file():
            st.info(DICA_GERAR)
        else:
            aba_hospitais(ler_hospitais(str(CSV_HOSPITAIS)))


main()
