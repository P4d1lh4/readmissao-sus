# Inventário do SIH-RD — Pernambuco, 2023–2024

Gerado por `scripts/baixar_sih.py` em 23/11/2026. Contém só agregados; nenhum registro individual sai de `data/`.

Arquivos: `RDPEaamm.dbc` do FTP do DATASUS (`ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados`). O `aamm` do nome é a **competência de processamento** da AIH, não o mês da alta: um arquivo de 2023 pode trazer saídas de 2022, e AIHs de saídas de dezembro/2024 podem aparecer só em competências de 2025.

## Linhas por ano

| Ano (competência) | Arquivos | Linhas |
| --- | ---: | ---: |
| 2023 | 12 | 617.948 |
| 2024 | 12 | 669.715 |
| **Total** | 24 | **1.287.663** |

## Campos usados no projeto

Tipo é o declarado no cabeçalho do DBF. No Parquet bruto (`data/parquet/`) todos os campos ficam como texto, sem espaços nas pontas e com vazio convertido em nulo; a tipagem é feita depois. "% nulos/vazios" conta nulos e textos vazios.

Observação: o informe técnico chama a data de internação de `DI_INTER`, mas nos arquivos o campo se chama `DT_INTER`.

| Campo | Existe | Tipo no DBF | % nulos/vazios 2023 | % nulos/vazios 2024 | % nulos/vazios total |
| --- | --- | --- | --- | --- | --- |
| N_AIH | sim | char(13) | 0,00% | 0,00% | 0,00% |
| IDENT | sim | char(1) | 0,00% | 0,00% | 0,00% |
| NASC | sim | char(8) | 0,00% | 0,00% | 0,00% |
| SEXO | sim | char(1) | 0,00% | 0,00% | 0,00% |
| CEP | sim | char(8) | 0,00% | 0,00% | 0,00% |
| MUNIC_RES | sim | char(6) | 0,00% | 0,00% | 0,00% |
| DT_INTER | sim | char(8) | 0,00% | 0,00% | 0,00% |
| DT_SAIDA | sim | char(8) | 0,00% | 0,00% | 0,00% |
| DIAG_PRINC | sim | char(4) | 0,00% | 0,00% | 0,00% |
| PROC_REA | sim | char(10) | 0,00% | 0,00% | 0,00% |
| CNES | sim | char(7) | 0,00% | 0,00% | 0,00% |
| MORTE | sim | numeric(1) | 0,00% | 0,00% | 0,00% |
| CAR_INT | sim | char(2) | 0,00% | 0,00% | 0,00% |
| COBRANCA | sim | char(2) | 0,00% | 0,00% | 0,00% |
| UTI_MES_TO | sim | numeric(3) | 0,00% | 0,00% | 0,00% |
| IDADE | sim | numeric(2) | 0,00% | 0,00% | 0,00% |

## Dicionário: IDENT, MORTE e COBRANCA

- **IDENT** — char(1), "Identificação do tipo da AIH". Códigos: `1` = Normal, `5` = Longa permanência (demais valores o TabWin agrupa como "Outras/ignorado").
- **MORTE** — numeric(1), "Indica Óbito". Códigos: `1` = Com óbito, `0` = Sem óbito.
- **COBRANCA** — char(2), "Motivo de Saída/Permanência". Códigos 1x = alta, 2x = permanência, 3x = transferência, 4x = óbito, 51 = encerramento administrativo, 6x = parto (mãe e recém-nascido). Transferência: 29, 31, 32. Óbito: 41, 42, 43, 65, 66, 67 (63 e 64 são alta da mãe com óbito do recém-nascido/fetal).

Fontes:

- Layout e descrição dos campos: Informe Técnico SIH, processamento 2016-03, Tabela 1 (layout RD*.dbf de 2008 em diante): ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Doc/IT_SIHSUS_1603.pdf.
- Códigos: Tabelas do TabWin para o SIH: ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip (RD2008.DEF e CNV/IDENT.CNV, CNV/MORTES.CNV, CNV/SAIDAPERM.CNV, CNV/CARATEND.CNV).

### Distribuição de IDENT

| Código | Significado | Linhas | % |
| --- | --- | ---: | ---: |
| 1 | Normal | 1.280.396 | 99,44% |
| 5 | Longa permanência | 7.267 | 0,56% |

### Distribuição de MORTE

| Código | Significado | Linhas | % |
| --- | --- | ---: | ---: |
| 0 | Sem óbito | 1.232.608 | 95,72% |
| 1 | Com óbito | 55.055 | 4,28% |

### Distribuição de COBRANCA (motivo de saída/permanência)

| Código | Significado | Linhas | % |
| --- | --- | ---: | ---: |
| 12 | Alta melhorado | 713.323 | 55,40% |
| 61 | Alta da mãe/puérpera e do recém-nascido | 151.166 | 11,74% |
| 15 | Alta com previsão de retorno p/ acompanhamento do paciente | 86.701 | 6,73% |
| 31 | Transferência para outro estabelecimento | 70.181 | 5,45% |
| 26 | Permanência por mudança de procedimento | 62.392 | 4,85% |
| 41 | Óbito com DO fornecida pelo médico assistente | 49.749 | 3,86% |
| 11 | Alta curado | 49.719 | 3,86% |
| 51 | Encerramento administrativo | 14.697 | 1,14% |
| 27 | Permanência por reoperação | 14.191 | 1,10% |
| 21 | Permanência por características próprias da doença | 12.635 | 0,98% |
| 16 | Alta por evasão | 10.570 | 0,82% |
| 14 | Alta a pedido | 8.921 | 0,69% |
| 22 | Permanência por intercorrência | 8.846 | 0,69% |
| 18 | Alta por outros motivos | 7.792 | 0,61% |
| 62 | Alta da mãe/puérpera e permanência do recém-nascido | 7.740 | 0,60% |
| 28 | Permanência por outros motivos | 4.991 | 0,39% |
| 25 | Permanência proc. doação órg., tec., cél. — doador morto | 4.500 | 0,35% |
| 42 | Óbito com DO fornecida pelo IML | 4.088 | 0,32% |
| 23 | Permanência por impossibilidade sócio-familiar | 3.021 | 0,23% |
| 43 | Óbito com DO fornecida pelo SVO | 1.204 | 0,09% |
| 64 | Alta da mãe/puérpera com óbito fetal | 924 | 0,07% |
| 63 | Alta da mãe/puérpera e óbito do recém-nascido | 285 | 0,02% |
| 24 | Permanência proc. doação órg., tec., cél. — doador vivo | 13 | 0,00% |
| 66 | Óbito da mãe/puérpera e alta do recém-nascido | 10 | 0,00% |
| 67 | Óbito da mãe/puérpera e permanência do recém-nascido | 3 | 0,00% |
| 65 | Óbito da gestante e do concepto | 1 | 0,00% |

### Distribuição de CAR_INT (caráter da internação)

| Código | Significado | Linhas | % |
| --- | --- | ---: | ---: |
| 02 | Urgência | 910.292 | 70,69% |
| 01 | Eletivo | 371.712 | 28,87% |
| 05 | Outros tipos de acidente de trânsito | 4.550 | 0,35% |
| 06 | Outros tipos de lesões e envenenamentos por agentes químicos ou físicos | 1.109 | 0,09% |
