"""Texto "Como ler a tabela" da aba Hospitais: exemplos escolhidos a partir do CSV."""

import pandas as pd

from dashboard import leitura

TABELA = pd.DataFrame(
    {
        "cnes": ["GRANDE", "PEQUENO", "INCERTO", "BAIXO", "NEUTRO"],
        "altas": [9000, 110, 190, 2000, 800],
        "observado": [400, 30, 8, 60, 40],
        "esperado": [150.0, 12.4, 4.2, 90.0, 41.0],
        "razao_oe": [2.66, 2.41, 1.93, 0.67, 0.98],
        "ic95_inf": [2.40, 1.63, 0.83, 0.51, 0.70],
        "ic95_sup": [2.93, 3.45, 3.80, 0.86, 1.33],
    }
)


def test_exemplos_escolhem_o_acima_grande_o_acima_pequeno_e_o_compativel_de_razao_alta() -> None:
    frases = leitura.exemplos(TABELA)

    assert len(frases) == 3
    assert "**GRANDE**: 9.000 altas, 400 voltas contra 150,0 esperadas, razão **2,66**" in frases[0]
    assert "caso mais claro" in frases[0]
    assert "**PEQUENO**" in frases[1] and "faixa é larga" in frases[1]
    assert "**INCERTO**" in frases[2] and "cruza o 1" in frases[2]


def test_caso_mais_claro_e_a_faixa_mais_alta_e_nao_o_maior_hospital() -> None:
    enorme_perto_de_1 = pd.DataFrame(
        {"cnes": ["ENORME"], "altas": [16000], "observado": [1170], "esperado": [1100.0],
         "razao_oe": [1.07], "ic95_inf": [1.01], "ic95_sup": [1.13]}
    )
    frases = leitura.exemplos(pd.concat([TABELA, enorme_perto_de_1], ignore_index=True))

    assert "**GRANDE**" in frases[0] and "caso mais claro" in frases[0]


def test_sem_compativel_acima_de_1_nao_inventa_exemplo() -> None:
    sem_incerto = TABELA[TABELA["cnes"] != "INCERTO"]
    frases = leitura.exemplos(sem_incerto)

    assert len(frases) == 2   # NEUTRO é compatível, mas com razão abaixo de 1
    assert not any("cruza o 1" in f for f in frases)


def test_sem_hospital_acima_so_explica_as_colunas_e_os_cuidados() -> None:
    texto = leitura.texto(TABELA[TABELA["cnes"].isin(["BAIXO", "NEUTRO"])])

    assert "Exemplos desta tabela" not in texto
    assert "| **Razão O/E** |" in texto
    assert "não diz que um hospital é pior que outro" in texto
