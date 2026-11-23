# Coorte de altas (S06)

Banco DuckDB local (`data/sih.duckdb`, fora do git) montado a partir dos Parquet do SIH-RD de PE, com o SQL versionado em `sql/`. Este documento explica as tabelas e as regras e mostra quantas linhas cada filtro remove.

## Como recriar

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

O comando apaga e recria o banco do zero a partir de `data/parquet/RDPE*.parquet` (cerca de 1 min). Ele monta tudo num arquivo temporário (`data/sih.duckdb.novo`) e só troca o banco antigo no fim. Depois reescreve o bloco de contagens abaixo, entre as marcas `coorte`. O resto deste arquivo não é tocado.

## Tabelas

| Tabela | Arquivo SQL | Uma linha por | Conteúdo |
| --- | --- | --- | --- |
| `dic_cobranca` | carregada de `dicionario_sih.py` | código de COBRANCA | descrição e marcas de óbito e transferência |
| `stg_aih` | `sql/01_staging.sql` | linha dos Parquet | campos tipados (datas como DATE, MORTE como booleano, IDADE e UTI_MES_TO como inteiros), chave de linkage com sal e marcas de qualidade |
| `internacao` | `sql/02_internacao.sql` | internação (AIH IDENT = 1) | saída e motivo finais, `obito`, `longa_permanencia` e marcas da chave |
| `coorte` | `sql/03_coorte.sql` | alta sem óbito | colunas de `internacao` mais as marcas `censurada`, `alta_antes_do_inicio` e `elegivel_indice` |
| `coorte_filtros`, `coorte_detalhes` | `sql/03_coorte.sql` | filtro / item | as contagens deste documento |
| `coorte_parametros` | `banco.py` | — | última competência, início, data de corte e fim da cobertura |

A `internacao` guarda também os óbitos: uma readmissão pode terminar em óbito, e a S07 precisa dela para achar a próxima internação. A `coorte` é o conjunto de altas que podem ser internação-índice.

As regras de episódio (deduplicação por `N_AIH`, IDENT = 5 como continuação, óbito) existem só em `sql/01_staging.sql` e `sql/02_internacao.sql`. `src/readmissao_sus/linkage_viabilidade.py` (S03) roda os mesmos dois arquivos num banco em memória. Os números da D01 em `docs/decisoes.md` não mudaram com isso (conferido rodando `scripts/medir_linkage.py`).

## Filtros e marcas

**Filtro** tira a linha da coorte. **Marca** é uma coluna booleana: a linha fica, e quem usa a coorte decide o que fazer com ela.

Filtros, nesta ordem:

1. **Só AIH normal (IDENT = 1).** Pelo dicionário (`IDENT.CNV`), `1` = normal e `5` = longa permanência. A AIH 5 é continuação de uma AIH 1 com o mesmo `N_AIH` (D01, tratamento 2): suas linhas saem da contagem, mas não se perdem. Quando a saída da AIH 5 passa da saída da AIH 1, a internação recebe a maior `DT_SAIDA` das AIHs 5 e o `COBRANCA` e o `MORTE` dessa última AIH 5. AIH 5 sem a AIH 1 correspondente (internação que começou antes de 2023) é descartada. Qualquer outro IDENT também sai.
2. **Uma linha por `N_AIH`.** Entre AIHs 1 repetidas fica a da competência mais recente (D01, tratamento 1). Hoje não há nenhuma; a regra fica para reapresentações futuras.
3. **Datas válidas.** `DT_INTER` e `DT_SAIDA` precisam ser datas reais no formato `aaaammdd` (8 dígitos; `00000000`, `20230230` e `2023011` viram nulo) e a saída não pode ser anterior à entrada.
4. **Sem óbito.** Sai a alta com `MORTE = 1` ou `COBRANCA` de óbito (41, 42, 43, 65, 66, 67), olhando a saída final do episódio. Os códigos 63 e 64 (alta da mãe com óbito do recém-nascido ou fetal) ficam: a paciente saiu viva.

Marcas na `coorte`:

- `censurada`: saída depois da data de corte (D01, tratamento 3). Os 30 dias seguintes não estão cobertos pelos dados, então a alta não pode receber rótulo de readmissão. A data de corte é calculada por `src/readmissao_sus/cobertura.py`, a mesma função da S03.
- `alta_antes_do_inicio`: saída antes de 01/01/2023. Saídas de 2022 só aparecem quando processadas com atraso e formam uma amostra viciada.
- `elegivel_indice`: nem censurada nem antes do início. Só essas são altas-índice. O número bate com as 1.066.521 altas-índice da D01.
- `cep_generico`: CEP terminado em `000`, o CEP geral da localidade (D01, condição 2). Serve para avaliar o modelo nesse grupo em separado.
- Também vêm de `internacao`: `longa_permanencia`, `cep_zerado`, `nasc_0101`, `nasc_antes_1900`, `menor_1_ano` e `nasc_invalida`.

### Datas inválidas e placeholders

Em `stg_aih`, a data que não é válida vira nulo e ganha a marca `*_invalida`. Só as datas de internação e de saída filtram (filtro 3). As de nascimento não filtram, porque a coorte não depende de `NASC`; elas ficam marcadas:

- `NASC` antes de 1900: quase todas são `18991230`, a "data zero" de sistemas como Delphi e Excel, e não um nascimento real. Marca `nasc_antes_1900`.
- `NASC` em 01/01: aparece acima do esperado, provavelmente data estimada. Marca `nasc_0101`.

As contagens estão na seção "Qualidade das datas" abaixo.

## Chave de linkage e sal

A chave é `SHA-256(sal || NASC | SEXO | CEP | MUNIC_RES)`, gravada na coluna `chave` de `stg_aih`, `internacao` e `coorte`. `NASC` e `CEP` **não ficam em claro** no banco: só a chave e as marcas derivadas deles. `SEXO` e `MUNIC_RES` ficam, porque podem ser variáveis do modelo.

A D01 observa que um SHA-256 **sem sal** dessa chave pode ser revertido por força bruta: as datas de nascimento, os sexos, os CEPs e os municípios de PE formam um espaço pequeno. Com um sal secreto de 256 bits, quem tem só o banco não consegue montar a tabela de hashes. O sal vem, nesta ordem:

1. da variável de ambiente `READMISSAO_SAL_CHAVE`;
2. do arquivo `data/sal_chave.txt`, que o script cria na primeira vez com 32 bytes aleatórios (`secrets.token_hex`).

`data/` está no `.gitignore`: o sal, o banco e a chave nunca vão para o git, e nenhum arquivo commitado contém chave ou registro por internação. Recriar o banco mantém o mesmo sal. Apagar `data/sal_chave.txt` muda todas as chaves na próxima construção; nada fora do banco depende delas. Atenção: o sal protege o banco, não os Parquet em `data/parquet/`, que têm os campos em claro.

A S03 (`scripts/medir_linkage.py`) usa sal vazio, porque a chave dela só existe em memória e nunca é gravada.

## Contagens

<!-- coorte:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->
Gerado por `.venv\Scripts\python scripts\construir_banco.py` em 23/11/2026. Só agregados.

#### Filtros, em ordem

| # | Filtro | Antes | Removidas | Depois |
| --- | ---: | ---: | ---: | ---: |
| 1 | Só AIH normal (IDENT = 1) | 1.287.663 | 7.267 | 1.280.396 |
| 2 | Uma linha por N_AIH (fica a competência mais recente) | 1.280.396 | 0 | 1.280.396 |
| 3 | Datas de internação e saída válidas, saída ≥ internação | 1.280.396 | 0 | 1.280.396 |
| 4 | Sem óbito na saída final (MORTE = 1 ou COBRANCA de óbito) | 1.280.396 | 55.044 | 1.225.352 |

Linhas na coorte (tabela `coorte`): **1.225.352**.

Período das altas-índice: saída de 01/01/2023 a **01/10/2024** (última competência 202412; cobertura completa até 31/10/2024; corte = fim da cobertura − 30 dias).

#### Filtro 1: AIHs IDENT = 5 e outros

| Item | Linhas |
| --- | ---: |
| Linhas IDENT = 5 (continuação de longa permanência) | 7.267 |
| Linhas com outro IDENT | 0 |
| AIHs distintas com IDENT = 5 | 3.662 |
| AIHs IDENT = 5 sem a AIH 1 correspondente (descartadas) | 254 |
| Internações com AIH 5 (saída e motivo finais vindos da continuação, quando posterior) | 3.408 |

#### Qualidade das datas (linhas IDENT = 1, antes da deduplicação)

| Item | Linhas |
| --- | ---: |
| DT_INTER ausente ou inválida | 0 |
| DT_SAIDA ausente ou inválida | 0 |
| Saída antes da internação | 0 |
| Saída depois do fim da competência | 0 |
| NASC inválida (não é data) | 0 |
| NASC antes de 1900 (inclui 30/12/1899, data zero de sistemas) | 16 |
| NASC em 01/01 (data estimada) | 6.182 |
| NASC depois da internação | 0 |
| MORTE ausente ou fora de 0/1 | 0 |

#### Filtro 4: óbitos

| Item | Linhas |
| --- | ---: |
| Óbitos removidos | 55.044 |
| … com MORTE = 1 | 55.044 |
| … com COBRANCA de óbito | 55.044 |
| COBRANCA 63/64 (alta da mãe com óbito do recém-nascido/fetal), mantidas | 1.209 |

#### Marcas na coorte (não removem linhas)

| Item | Linhas |
| --- | ---: |
| Elegíveis a alta-índice (elegivel_indice) | 1.066.521 |
| Censuradas: saída depois da data de corte (censurada) | 144.549 |
| Saída antes do início do período (alta_antes_do_inicio) | 14.282 |
| CEP genérico (cep_generico), toda a coorte | 544.257 |
| CEP genérico entre as elegíveis | 474.704 |
<!-- coorte:fim -->
