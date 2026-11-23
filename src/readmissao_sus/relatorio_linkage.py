"""Bloco de números da S03 em Markdown (só agregados) e sua gravação em docs/decisoes.md."""

from __future__ import annotations

from pathlib import Path

from readmissao_sus.linkage_viabilidade import JANELA_DIAS, LIMIAR_COMPLETUDE, Readmissao, Resultado

COMANDO = r".venv\Scripts\python scripts\medir_linkage.py"
MARCA_INICIO = "<!-- linkage-viabilidade:inicio (gerado por scripts/medir_linkage.py; não editar à mão) -->"
MARCA_FIM = "<!-- linkage-viabilidade:fim -->"


def gerar_bloco(r: Resultado, data_geracao: str) -> str:
    partes = [
        MARCA_INICIO,
        f"Gerado por `{COMANDO}` em {data_geracao}. Só agregados.",
        "",
        "#### Os cinco números",
        "",
        _tabela_cinco_numeros(r),
        "",
        "#### Internações por chave",
        "",
        _tabela(["Internações na chave", "Chaves", "% das chaves"],
                [[faixa, _milhar(n), _pct(n, r.chaves.chaves)] for faixa, n in r.chaves.distribuicao.items()]),
        "",
        "#### Preparação da base",
        "",
        _tabela_preparo(r),
        "",
        "#### Cobertura e censura",
        "",
        _tabela(["Meses entre saída e competência (até)", "AIHs IDENT=1 já processadas"],
                [[str(lag), _pct_f(f)] for lag, f in r.cobertura.completude_por_lag.items()]),
        "",
        f"Última competência: {r.cobertura.ultima_competencia}. Limiar de completude: "
        f"{_pct_f(LIMIAR_COMPLETUDE)}. Fim da cobertura completa: **{_data(r.cobertura.fim)}**. "
        f"Altas-índice: saída de {_data(r.cobertura.inicio)} a **{_data(r.cobertura.limite_indice)}** "
        f"(data de corte = fim da cobertura − {JANELA_DIAS} dias).",
        "",
        "#### Readmissão em 30 dias: decomposição",
        "",
        _tabela_readmissao(r),
        "",
        "#### Placeholders na chave e colisões",
        "",
        _tabela(["Grupo de chaves", "Chaves", "Chaves com 2+ internações", "Chaves colidentes",
                 "% colidentes entre as com 2+"],
                [[g.nome, _milhar(g.chaves), _milhar(g.chaves_multiplas), _milhar(g.chaves_colidentes),
                  _pct(g.chaves_colidentes, g.chaves_multiplas)] for g in r.placeholders]),
        "",
        f"Internações sobrepostas: {_milhar(r.chaves.sobrepostas)}; destas, "
        f"{_milhar(r.chaves.sobrepostas_mesmo_cnes)} ({_pct(r.chaves.sobrepostas_mesmo_cnes, r.chaves.sobrepostas)}) "
        "no mesmo hospital da internação anterior da chave e "
        f"{_milhar(r.chaves.sobrepostas_menor_1_ano)} ({_pct(r.chaves.sobrepostas_menor_1_ano, r.chaves.sobrepostas)}) "
        "em menores de 1 ano.",
        "",
        "#### Plano B: óbito hospitalar e permanência",
        "",
        _tabela_plano_b(r),
        MARCA_FIM,
    ]
    return "\n".join(partes)


def gravar_bloco(caminho: Path, bloco: str) -> None:
    """Substitui o bloco entre as marcas; se não houver marcas, acrescenta ao fim do arquivo."""
    texto = caminho.read_text(encoding="utf-8") if caminho.exists() else "# Decisões\n"
    inicio, fim = texto.find(MARCA_INICIO), texto.find(MARCA_FIM)
    if inicio == -1 or fim == -1:
        novo = texto.rstrip("\n") + "\n\n" + bloco + "\n"
    else:
        novo = texto[:inicio] + bloco + texto[fim + len(MARCA_FIM):]
    caminho.write_text(novo, encoding="utf-8")


def _tabela_cinco_numeros(r: Resultado) -> str:
    c, ra = r.chaves, r.readmissao
    return _tabela(["#", "Medida", "Valor"], [
        ["1", "Internações (episódios IDENT=1 deduplicados)", _milhar(c.internacoes)],
        ["2", "Chaves distintas (hash SHA-256 de NASC+SEXO+CEP+MUNIC_RES)", _milhar(c.chaves)],
        ["3", "Internações por chave (média; distribuição abaixo)",
         f"{c.internacoes / c.chaves:.2f}".replace(".", ",") if c.chaves else "—"],
        ["4", "Colisões: chaves com internações sobrepostas no tempo",
         f"{_milhar(c.chaves_colidentes)} ({_pct(c.chaves_colidentes, c.chaves_multiplas)} das "
         f"{_milhar(c.chaves_multiplas)} chaves com 2+ internações; {_milhar(c.internacoes_em_colisao)} internações)"],
        ["5", "Taxa bruta de readmissão em 30 dias (sem altas por óbito)",
         f"{_pct_f(ra.taxa_bruta)} ({_milhar(ra.readmitidas)} / {_milhar(ra.altas_indice)})"],
        ["5a", "… sem as contíguas após transferência", _pct_f(ra.taxa_sem_transferencia)],
        ["5b", "… sem as contíguas após transferência e após permanência",
         _pct_f(ra.taxa_sem_transferencia_permanencia)],
    ])


def _tabela_preparo(r: Resultado) -> str:
    p = r.preparo
    return _tabela(["Item", "Linhas"], [
        ["Linhas nos 24 arquivos", _milhar(p.linhas_brutas)],
        ["Linhas com N_AIH repetido (todas IDENT=5)", _milhar(p.linhas_n_aih_repetido)],
        ["Duplicatas de N_AIH entre AIHs IDENT=1 (removidas)", _milhar(p.ident1_duplicadas)],
        ["Linhas IDENT=5 (continuação)", _milhar(p.ident5_linhas)],
        ["AIHs distintas com IDENT=5", _milhar(p.ident5_aih_distintas)],
        ["AIHs IDENT=5 sem a IDENT=1 correspondente nos dados (descartadas)", _milhar(p.ident5_orfas)],
        ["Internações com data ausente ou saída antes da entrada (descartadas)", _milhar(p.datas_invalidas)],
        ["Internações na base final", _milhar(p.internacoes)],
    ])


def _tabela_readmissao(r: Resultado) -> str:
    linhas = []
    for nome, ra in (("Todas as chaves", r.readmissao),
                     ("Só chaves com CEP específico", r.readmissao_cep_especifico)):
        linhas.append([nome, *_colunas_readmissao(ra)])
    cabecalho = ["Grupo", "Altas-índice", "Óbitos excluídos", "Censuradas", "Readmitidas",
                 "Início em 0–1 dia", "2–7 dias", "8–30 dias", "Contíguas pós-transferência",
                 "Contíguas pós-permanência", "Taxa bruta", "Sem transf.", "Sem transf. e perm."]
    return _tabela(cabecalho, linhas)


def _colunas_readmissao(ra: Readmissao) -> list[str]:
    return [
        _milhar(ra.altas_indice), _milhar(ra.obitos_excluidos), _milhar(ra.censuradas),
        _milhar(ra.readmitidas), *(_milhar(n) for n in ra.por_gap.values()),
        _milhar(ra.contiguas_transferencia), _milhar(ra.contiguas_permanencia),
        _pct_f(ra.taxa_bruta), _pct_f(ra.taxa_sem_transferencia),
        _pct_f(ra.taxa_sem_transferencia_permanencia),
    ]


def _tabela_plano_b(r: Resultado) -> str:
    b = r.plano_b
    linhas = [
        ["Saídas no período coberto", _milhar(b.saidas)],
        ["Óbitos hospitalares", f"{_milhar(b.obitos)} ({_pct_f(b.taxa_obito)})"],
        ["Permanência média (dias)", f"{b.permanencia_media:.1f}".replace(".", ",")],
    ]
    linhas += [[f"Permanência p{round(q * 100)} (dias)", f"{v:g}".replace(".", ",")]
               for q, v in b.permanencia_quantis.items()]
    linhas += [[f"Permanência > {d} dias", f"{_milhar(n)} ({_pct(n, b.saidas)})"] for d, n in b.acima_de.items()]
    return _tabela(["Medida", "Valor"], linhas)


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    alinhamento = ["---"] + ["---:"] * (len(cabecalho) - 1)
    return "\n".join(_linha(x) for x in [cabecalho, alinhamento, *linhas])


def _linha(celulas: list[str]) -> str:
    return "| " + " | ".join(celulas) + " |"


def _pct(parte: int, total: int) -> str:
    return _pct_f(parte / total) if total else "—"


def _pct_f(fracao: float) -> str:
    return f"{100 * fracao:.2f}%".replace(".", ",")


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _data(d) -> str:
    return d.strftime("%d/%m/%Y")
