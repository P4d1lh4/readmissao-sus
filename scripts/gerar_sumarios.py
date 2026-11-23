"""Gera o Sumário de Alta em FHIR de uma amostra de 20 episódios e valida todos (S08).

Uso:
    .venv\\Scripts\\python scripts\\gerar_sumarios.py
    .venv\\Scripts\\python scripts\\gerar_sumarios.py --sem-validar
    .venv\\Scripts\\python scripts\\gerar_sumarios.py --sem-terminologia

Lê os episódios de data/sih.duckdb (e CNPJ/município do hospital, raça/cor e nacionalidade
dos Parquet em data/parquet/), grava um Bundle por episódio em fhir/saida/ (fora do git) e
roda scripts/validar_fhir.py uma vez na pasta inteira. A amostra é estratificada e
determinística (estratos em src/readmissao_sus/episodio_leitura.py).
Código de saída: o do validador (0 sem erros), ou 2 se não houver banco/Parquet.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import validar_fhir  # noqa: E402  (scripts/ está no sys.path ao rodar este script)

from readmissao_sus import sih_fhir_mapa as mapa  # noqa: E402
from readmissao_sus.episodio_leitura import selecionar_amostra  # noqa: E402
from readmissao_sus.fhir_sumario import SISTEMA_CID10, SISTEMA_SIGTAP, Episodio, montar_bundle  # noqa: E402
from readmissao_sus.pacotes_fhir import PACOTES  # noqa: E402
from readmissao_sus.terminologia_fhir import codigos  # noqa: E402

BANCO = RAIZ / "data" / "sih.duckdb"
DIR_PARQUET = RAIZ / "data" / "parquet"
DIR_SAIDA = RAIZ / "fhir" / "saida"
PACOTE_RNDS = "br.go.ses.reds-go"
SISTEMA_MUNICIPIO = "http://www.saude.gov.br/fhir/r4/CodeSystem/BRDivisaoGeograficaBrasil"
PREFIXO_ARQUIVO = "sumario-alta-"
SAIDA_FALHA = 2


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera e valida o Sumário de Alta de 20 episódios.")
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=DIR_SAIDA)
    parser.add_argument("--sem-validar", action="store_true", help="só gera os Bundles")
    parser.add_argument("--sem-terminologia", action="store_true", help="repassa -tx n/a ao validador")
    return parser.parse_args(argv)


def _filtro_terminologia(pacote: Path):
    """Aceita só episódios cujos códigos existem nos CodeSystems da RNDS do pacote."""
    cid, sigtap, municipios = (codigos(pacote, s) for s in (SISTEMA_CID10, SISTEMA_SIGTAP, SISTEMA_MUNICIPIO))

    def aceita(episodio: Episodio) -> bool:
        try:
            diagnosticos = {mapa.cid10(i.diag_princ) for i in episodio.internacoes}
        except ValueError:
            return False
        return (
            diagnosticos <= cid
            and all(i.proc_rea in sigtap for i in episodio.internacoes)
            and episodio.munic_res in municipios
            and episodio.estabelecimento_alta.municipio in municipios
        )

    return aceita


def _descrever(episodio: Episodio) -> str:
    hospitais = len({i.cnes for i in episodio.internacoes})
    return (
        f"{len(episodio.internacoes)} AIH(s), {hospitais} hospital(is), sexo {mapa.genero(episodio.sexo)}, "
        f"CAR_INT {episodio.car_int}, COBRANCA final {episodio.cobranca}, "
        f"{(episodio.dt_saida - episodio.dt_inter).days} dia(s)"
    )


def _gravar(amostra, saida: Path, gerado_em: datetime) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    for antigo in saida.glob(f"{PREFIXO_ARQUIVO}*.json"):
        antigo.unlink()
    for n, (estrato, episodio) in enumerate(amostra, start=1):
        arquivo = saida / f"{PREFIXO_ARQUIVO}{n:02d}.json"
        bundle = montar_bundle(episodio, gerado_em)
        arquivo.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{arquivo.name}: [{estrato.nome}] {_descrever(episodio)}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = _argumentos(argv)
    parquets = sorted(DIR_PARQUET.glob("RDPE*.parquet"))
    if not args.banco.is_file() or not parquets:
        print("ERRO: falta data/sih.duckdb ou data/parquet/. Rode scripts\\construir_banco.py.", file=sys.stderr)
        return SAIDA_FALHA
    pacote = RAIZ / "fhir" / "pacotes" / next(p.arquivo for p in PACOTES if p.nome == PACOTE_RNDS)
    con = duckdb.connect(str(args.banco), read_only=True)
    try:
        amostra = selecionar_amostra(con, parquets, _filtro_terminologia(pacote))
    finally:
        con.close()
    _gravar(amostra, args.saida, datetime.now().astimezone())
    print(f"{len(amostra)} Bundle(s) gravado(s) em {args.saida}")
    if args.sem_validar:
        return 0
    return validar_fhir.main([str(args.saida)] + (["--sem-terminologia"] if args.sem_terminologia else []))


if __name__ == "__main__":
    sys.exit(main())
