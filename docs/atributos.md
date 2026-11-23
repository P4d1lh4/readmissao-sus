# Atributos por episódio (S09)

Tabela `atributo_episodio` do banco DuckDB local (`data/sih.duckdb`, fora do git): uma linha por episódio elegível, ou seja, por episódio de `coorte_episodio` com `readmissao_30d` não nulo (D01: seguir com o linkage). É a entrada do modelo. Este documento traz só agregados; nenhuma linha por episódio sai do banco.

## Como recriar

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

O SQL está em `sql/06_atributos.sql`, rodado por `src/readmissao_sus/atributos.py` depois dos episódios (S07). O script reescreve só o bloco entre as marcas `atributos` abaixo. A regra das contíguas sem motivo (D03) continua parâmetro, com padrão `nenhuma`: `--contiguas-sem-motivo mesmo_hospital` muda os episódios e, com eles, os atributos.

## Atributos

| Grupo | Colunas | Origem |
| --- | --- | --- |
| Alvo | `readmissao_30d` | `coorte_episodio` (S07) |
| Paciente e entrada | `idade`, `sexo`, `capitulo_cid`, `grupo_sigtap`, `car_int` | primeira internação do episódio |
| Episódio | `dias_permanencia`, `dias_uti`, `usou_uti`, `n_aihs`, `n_hospitais`, `houve_transferencia`, `houve_permanencia`, `houve_contigua_sem_motivo`, `cep_generico`, `cnes_alta`, `ano_alta` | episódio inteiro; `cnes_alta` e `ano_alta` vêm da última internação |
| Histórico da chave | `historico_completo`, `episodios_365d`, `dias_internado_365d`, `dias_desde_ultima_alta`, `historico_com_obito` | outros episódios da mesma chave |
| Colisões | `chave_colidente`, `episodio_sobreposto` | pares sobrepostos em `episodio_sobreposicao` |
| Identificação | `episodio_id`, `chave`, `dt_inter`, `dt_saida` | não são atributos: servem para separar treino e teste por tempo ou por chave |

Fontes dos códigos (tabelas do TabWin em `TAB_SIH.zip`, FTP do DATASUS, consultadas em 23/11/2026; transcritas em `src/readmissao_sus/dicionario_sih.py`):

- **Capítulo da CID-10** (`capitulo_cid`): `CNV/CID10CAP.CNV`, pela faixa da categoria (3 primeiros caracteres de `DIAG_PRINC`): I = A00–B99, II = C00–D48, …, IX = I00–I99, …, XXII = U04–U99. U00–U03 não tem capítulo no CNV e fica nulo.
- **Grupo SIGTAP** (`grupo_sigtap`): `DBF/TB_GRUPO.DBF` (competência 202407), que o `RD2008.DEF` usa para agrupar `PROC_REA`. O grupo é `CO_GRUPO`, os 2 primeiros dígitos do código de 10 dígitos do procedimento (01 a 09; 03 = clínicos, 04 = cirúrgicos).
- **Sexo**: `CNV/SEXO.CNV` (1 = M; 2 e 3 = F; o resto, nulo).
- **Idade**: `CNV/IDADEDET.CNV`, que lê `COD_IDADE` + `IDADE`: 2 = dias e 3 = meses (viram 0 ano), 4 = anos, 5 = 100 + `IDADE` anos; outro código vira nulo.
- **Caráter** (`car_int`): `CNV/CARATEND.CNV`, como em `docs/inventario-sih.md`.

Outras definições: `dias_permanencia` = saída final − entrada (0 no mesmo dia); `dias_uti` = soma de `UTI_MES_TO` das internações do episódio; `usou_uti` = `dias_uti > 0`; `houve_transferencia` e `houve_permanencia` = o episódio juntou alguma internação por esse motivo (S07); `houve_contigua_sem_motivo` só pode ser verdadeira com a D03 diferente de `nenhuma`.

## Histórico sem vazamento

O histórico do episódio atual E usa os outros episódios H da **mesma chave** que terminaram antes da entrada de E:

- `H.dt_saida <= E.dt_inter`, e H vem antes de E na ordem `(dt_inter, dt_saida, episodio_id)`, a mesma da D01 e da readmissão. As datas não têm hora: uma saída no mesmo dia da entrada conta como anterior, como a D01 conta uma entrada no dia da saída como readmissão. É o espelho exato do rótulo: H é anterior a E se e só se E é candidato a readmissão de H;
- o próprio E nunca entra, nem episódio que começa ou termina depois da entrada de E. Com isso, nada do que acontece depois da alta de E (inclusive a readmissão que ele rotula) aparece nos atributos;
- entram **todos** os episódios anteriores da chave, elegíveis ou não: censurados não podem ser anteriores a um elegível, mas os de saída antes de 01/01/2023 (`alta_antes_do_inicio`) e os terminados em óbito entram. Um óbito antes da entrada de E é impossível para uma pessoa só; quando aparece, é colisão de chave, e fica marcado em `historico_com_obito`.

Janela de 365 dias, contada para trás a partir da entrada de E: o intervalo `[E.dt_inter − 365, E.dt_inter]`.

- `episodios_365d`: episódios anteriores com saída dentro da janela;
- `dias_internado_365d`: dias dessas estadias dentro da janela (`saída − max(entrada, início da janela)`, a mesma conta da permanência). Uma estadia que começou antes da janela conta só a parte dentro dela;
- `dias_desde_ultima_alta`: `E.dt_inter −` a saída mais recente entre **todos** os episódios anteriores, sem limite de janela. Nulo quando não há episódio anterior nos dados.

### Início dos dados e `historico_completo`

Os dados começam nas saídas de 01/01/2023 (D01, tratamento 3: saídas de 2022 só aparecem quando processadas com atraso). `historico_completo` é verdadeiro quando a janela inteira está dentro dos dados: `E.dt_inter − 365 >= 01/01/2023`, ou seja, entrada a partir de 01/01/2024.

Efeito: nos episódios com `historico_completo = false` (entrada em 2023), parte do histórico real ficou antes dos dados. `episodios_365d` e `dias_internado_365d` saem subestimados, e `dias_desde_ultima_alta` sai nulo ou grande demais. A tabela "Efeito do início dos dados no histórico" abaixo mede a diferença. Quem treina o modelo tem três saídas: usar a marca como atributo, treinar só com `historico_completo = true` ou avaliar os dois grupos em separado. A tabela não escolhe; isso fica para a história do modelo.

### Colisões

Dois episódios da mesma chave **sobrepostos** (o seguinte começa antes da saída do anterior; D01, tratamento 5) não são da mesma pessoa, ou são AIHs administrativas da mesma estadia. Pela regra acima, um nunca conta no histórico do outro. Os pares ficam em `episodio_sobreposicao` (toda a tabela `episodio`, inclusive óbitos e censurados), e cada episódio elegível recebe duas marcas:

- `chave_colidente`: a chave tem pelo menos um par sobreposto, em qualquer data. O histórico dessas chaves pode misturar pessoas diferentes;
- `episodio_sobreposto`: o próprio episódio está em algum par.

As contagens estão na tabela "Colisões (D01)" abaixo.

## Leitura dos números

Números de 23/11/2026, com a regra padrão da D03 (`nenhuma`); estão no bloco abaixo.

- **963.767 episódios elegíveis** e taxa de 11,78%, os mesmos da `coorte_episodio` em `docs/coorte.md`: a tabela não tira nem acrescenta episódios.
- **Histórico.** É o grupo de atributos com o sinal mais forte: a readmissão vai de 7,51% sem episódio anterior em 365 dias a 67,20% com 5 ou mais. A taxa também sobe quando a última alta foi há pouco tempo (42,75% com `dias_desde_ultima_alta` entre 2 e 7).
- **Efeito de `historico_completo`.** Nas entradas de 2023 (janela incompleta, 55,91% dos episódios), só 18,10% têm episódio anterior em 365 dias, contra 23,67% nas de 2024, e a média de `episodios_365d` cai de 0,780 para 0,445. A diferença é o histórico que ficou antes de 01/01/2023. Mesmo assim, a taxa de readmissão dos dois grupos é parecida (11,90% e 11,68%), e o histórico separa bem os readmitidos nos dois. Sem tratamento, o modelo pode ler "sem histórico" em 2023 como risco menor do que é.
- **Colisões.** 7.214 chaves têm episódios sobrepostos, o mesmo número de chaves colidentes da D01 (que media por internação). Entre os elegíveis, 17.239 (1,79%) são de chave colidente e 12.801 (1,33%) se sobrepõem a outro episódio. A taxa nas chaves colidentes (21,72%) é quase o dobro da geral: quando duas pessoas dividem a chave, as internações de uma viram readmissão da outra. 1.680 elegíveis têm um óbito antes da entrada na mesma chave, o que só acontece com colisão. Essas marcas servem para avaliar o modelo sem esses grupos.
- **CEP genérico.** 45,26% dos elegíveis, com taxa menor (9,98% contra 13,26%), como na D01.
- **Nulos.** Só `dias_desde_ultima_alta` (78,47%, nulo quando não há episódio anterior nos dados) e uma idade inválida. Nenhum diagnóstico ficou sem capítulo e nenhum procedimento ficou sem grupo.

## Contagens

<!-- atributos:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->
Gerado por `.venv\Scripts\python scripts\construir_banco.py` em 23/11/2026. Só agregados.

Regra dos episódios: **transferência + permanência** (`contiguas_sem_motivo = 'nenhuma'`). Episódios elegíveis (linhas de `atributo_episodio`): **963.767**; readmitidos em 30 dias: 113.511 (11,78%).

#### Colunas: tipo e nulos

| Coluna | Tipo | Descrição | % nulos |
| --- | ---: | ---: | ---: |
| `episodio_id` | VARCHAR | identificador ou data (não é atributo) | 0,00% |
| `chave` | VARCHAR | identificador ou data (não é atributo) | 0,00% |
| `readmissao_30d` | BOOLEAN | Alvo: novo episódio da mesma chave em até 30 dias após a alta | 0,00% |
| `idade` | SMALLINT | Idade em anos na entrada (COD_IDADE em dias ou meses vira 0) | 0,00% |
| `sexo` | VARCHAR | Sexo (1 = M; 2 e 3 = F) | 0,00% |
| `capitulo_cid` | VARCHAR | Capítulo da CID-10 do diagnóstico principal da entrada | 0,00% |
| `grupo_sigtap` | VARCHAR | Grupo SIGTAP do procedimento principal da entrada | 0,00% |
| `car_int` | VARCHAR | Caráter da internação na entrada | 0,00% |
| `dias_permanencia` | INTEGER | Dias de permanência do episódio (saída − entrada) | 0,00% |
| `dias_uti` | INTEGER | Diárias de UTI somadas no episódio (UTI_MES_TO) | 0,00% |
| `usou_uti` | BOOLEAN | Teve diária de UTI no episódio | 0,00% |
| `n_aihs` | INTEGER | Internações (AIHs) no episódio | 0,00% |
| `n_hospitais` | INTEGER | Hospitais (CNES) distintos no episódio | 0,00% |
| `houve_transferencia` | BOOLEAN | Episódio juntou internações por transferência | 0,00% |
| `houve_permanencia` | BOOLEAN | Episódio juntou internações por permanência | 0,00% |
| `houve_contigua_sem_motivo` | BOOLEAN | Episódio juntou contíguas sem motivo (só com a D03 diferente de 'nenhuma') | 0,00% |
| `cep_generico` | BOOLEAN | CEP terminado em 000 (D01, condição 2) | 0,00% |
| `cnes_alta` | VARCHAR | CNES do hospital da alta (última internação) | 0,00% |
| `ano_alta` | SMALLINT | Ano da alta | 0,00% |
| `dt_inter` | DATE | identificador ou data (não é atributo) | 0,00% |
| `dt_saida` | DATE | identificador ou data (não é atributo) | 0,00% |
| `historico_completo` | BOOLEAN | Janela de 365 dias antes da entrada inteira dentro dos dados | 0,00% |
| `episodios_365d` | INTEGER | Episódios anteriores da chave com saída nos 365 dias antes da entrada | 0,00% |
| `dias_internado_365d` | INTEGER | Dias internado nesses episódios, dentro da janela | 0,00% |
| `dias_desde_ultima_alta` | INTEGER | Dias entre a última alta anterior da chave e a entrada | 78,47% |
| `historico_com_obito` | BOOLEAN | Algum episódio anterior da chave terminou em óbito (colisão) | 0,00% |
| `chave_colidente` | BOOLEAN | A chave tem episódios sobrepostos no tempo (D01) | 0,00% |
| `episodio_sobreposto` | BOOLEAN | Este episódio se sobrepõe a outro da mesma chave | 0,00% |

#### Efeito do início dos dados no histórico

| historico_completo | Episódios | Com episódio em 365 dias | Média episodios_365d | Média dias_internado_365d | Sem episódio anterior | Readmissão 30 dias | Readmissão com histórico | Readmissão sem histórico |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sim | 424.949 | 23,67% | 0,780 | 3,29 | 74,13% | 11,90% | 27,36% | 7,11% |
| não | 538.818 | 18,10% | 0,445 | 2,36 | 81,89% | 11,68% | 29,24% | 7,80% |

#### Colisões (D01)

| Item | Valor |
| --- | ---: |
| Pares de episódios sobrepostos da mesma chave (toda a tabela episodio) | 8.183 |
| Chaves com episódios sobrepostos | 7.214 |
| Episódios envolvidos em alguma sobreposição | 15.191 |
| Episódios elegíveis com chave_colidente | 17.239 |
| Episódios elegíveis com episodio_sobreposto | 12.801 |
| Episódios elegíveis com historico_com_obito | 1.680 |

#### `readmissao_30d`: Alvo: novo episódio da mesma chave em até 30 dias após a alta

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 113.511 | 11,78% | 100,00% |
| não | 850.256 | 88,22% | 0,00% |

#### `idade`: Idade em anos na entrada (COD_IDADE em dias ou meses vira 0)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0 | 66.294 | 6,88% | 9,55% |
| 1–4 | 38.820 | 4,03% | 10,41% |
| 5–14 | 55.678 | 5,78% | 13,50% |
| 15–49 | 456.303 | 47,35% | 9,39% |
| 50–64 | 160.046 | 16,61% | 14,85% |
| 65–79 | 132.344 | 13,73% | 15,52% |
| 80+ | 54.281 | 5,63% | 15,56% |
| idade inválida | 1 | 0,00% | 0,00% |

#### `sexo`: Sexo (1 = M; 2 e 3 = F)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| F | 571.707 | 59,32% | 11,07% |
| M | 392.060 | 40,68% | 12,81% |

#### `capitulo_cid`: Capítulo da CID-10 do diagnóstico principal da entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| XV. Gravidez, parto e puerpério | 176.732 | 18,34% | 5,42% |
| XIX. Lesões, envenenamentos e outras consequências de causas externas | 100.190 | 10,40% | 6,18% |
| XI. Doenças do aparelho digestivo | 95.196 | 9,88% | 6,79% |
| X. Doenças do aparelho respiratório | 84.620 | 8,78% | 11,53% |
| II. Neoplasias (tumores) | 83.881 | 8,70% | 29,22% |
| IX. Doenças do aparelho circulatório | 74.263 | 7,71% | 11,10% |
| XIV. Doenças do aparelho geniturinário | 67.463 | 7,00% | 10,59% |
| I. Algumas doenças infecciosas e parasitárias | 49.727 | 5,16% | 16,38% |
| XII. Doenças da pele e do tecido subcutâneo | 41.747 | 4,33% | 14,23% |
| XVI. Algumas afecções originadas no período perinatal | 40.292 | 4,18% | 8,70% |
| XXI. Fatores que influenciam o estado de saúde e o contato com serviços de saúde | 34.405 | 3,57% | 7,47% |
| XVIII. Sintomas, sinais e achados anormais de exames clínicos e laboratoriais | 21.280 | 2,21% | 15,92% |
| VI. Doenças do sistema nervoso | 19.173 | 1,99% | 18,56% |
| XIII. Doenças do sistema osteomuscular e do tecido conjuntivo | 16.659 | 1,73% | 17,70% |
| IV. Doenças endócrinas, nutricionais e metabólicas | 16.377 | 1,70% | 32,45% |
| V. Transtornos mentais e comportamentais | 12.053 | 1,25% | 13,13% |
| VII. Doenças do olho e anexos | 10.541 | 1,09% | 6,25% |
| III. Doenças do sangue, órgãos hematopoéticos e transtornos imunitários | 9.706 | 1,01% | 31,67% |
| XVII. Malformações congênitas, deformidades e anomalias cromossômicas | 7.713 | 0,80% | 11,29% |
| VIII. Doenças do ouvido e da apófise mastoide | 1.697 | 0,18% | 3,71% |
| XXII. Códigos para propósitos especiais | 52 | 0,01% | 7,69% |

#### `grupo_sigtap`: Grupo SIGTAP do procedimento principal da entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 03 Procedimentos clínicos | 549.497 | 57,02% | 15,91% |
| 04 Procedimentos cirúrgicos | 403.900 | 41,91% | 5,72% |
| 05 Transplantes de órgãos, tecidos e células | 8.670 | 0,90% | 31,37% |
| 02 Procedimentos com finalidade diagnóstica | 1.700 | 0,18% | 13,24% |

#### `car_int`: Caráter da internação na entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 02 Urgência | 665.994 | 69,10% | 10,68% |
| 01 Eletivo | 293.507 | 30,45% | 14,36% |
| 05 Outros tipos de acidente de trânsito | 3.321 | 0,34% | 6,81% |
| 06 Outros tipos de lesões e envenenamentos por agentes químicos ou físicos | 945 | 0,10% | 4,66% |

#### `dias_permanencia`: Dias de permanência do episódio (saída − entrada)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0 | 104.234 | 10,82% | 23,99% |
| 1 | 172.690 | 17,92% | 6,32% |
| 2–3 | 301.983 | 31,33% | 7,66% |
| 4–7 | 199.253 | 20,67% | 10,62% |
| 8–14 | 107.079 | 11,11% | 14,12% |
| 15–30 | 57.637 | 5,98% | 21,69% |
| 31+ | 20.891 | 2,17% | 27,18% |

#### `dias_uti`: Diárias de UTI somadas no episódio (UTI_MES_TO)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0 | 913.027 | 94,74% | 10,97% |
| 1–3 | 20.496 | 2,13% | 16,18% |
| 4–7 | 12.305 | 1,28% | 22,45% |
| 8+ | 17.939 | 1,86% | 40,64% |

#### `usou_uti`: Teve diária de UTI no episódio

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 50.740 | 5,26% | 26,35% |
| não | 913.027 | 94,74% | 10,97% |

#### `n_aihs`: Internações (AIHs) no episódio

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 1 | 896.873 | 93,06% | 11,44% |
| 2 | 53.916 | 5,59% | 14,61% |
| 3 | 8.722 | 0,90% | 21,59% |
| 4+ | 4.256 | 0,44% | 27,98% |

#### `n_hospitais`: Hospitais (CNES) distintos no episódio

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 1 | 944.901 | 98,04% | 11,68% |
| 2 | 18.372 | 1,91% | 16,49% |
| 3+ | 494 | 0,05% | 28,54% |

#### `houve_transferencia`: Episódio juntou internações por transferência

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 19.002 | 1,97% | 17,33% |
| não | 944.765 | 98,03% | 11,67% |

#### `houve_permanencia`: Episódio juntou internações por permanência

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 49.980 | 5,19% | 16,29% |
| não | 913.787 | 94,81% | 11,53% |

#### `houve_contigua_sem_motivo`: Episódio juntou contíguas sem motivo (só com a D03 diferente de 'nenhuma')

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| não | 963.767 | 100,00% | 11,78% |

#### `cep_generico`: CEP terminado em 000 (D01, condição 2)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 436.161 | 45,26% | 9,98% |
| não | 527.606 | 54,74% | 13,26% |

#### `cnes_alta`: CNES do hospital da alta (última internação)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0000434 | 66.236 | 6,87% | 20,68% |
| 0000655 | 38.160 | 3,96% | 7,80% |
| 0000477 | 35.824 | 3,72% | 41,34% |
| 0000426 | 33.572 | 3,48% | 8,13% |
| 0000396 | 28.609 | 2,97% | 21,04% |
| 2427427 | 27.059 | 2,81% | 13,98% |
| 2802783 | 25.609 | 2,66% | 9,91% |
| 2430711 | 24.378 | 2,53% | 6,05% |
| 0000418 | 24.101 | 2,50% | 6,24% |
| 0000582 | 21.040 | 2,18% | 21,17% |
| outras 250 categorias | 639.179 | 66,32% | 9,31% |

#### `ano_alta`: Ano da alta

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 2023 | 533.083 | 55,31% | 11,63% |
| 2024 | 430.684 | 44,69% | 11,96% |

#### `historico_completo`: Janela de 365 dias antes da entrada inteira dentro dos dados

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 424.949 | 44,09% | 11,90% |
| não | 538.818 | 55,91% | 11,68% |

#### `episodios_365d`: Episódios anteriores da chave com saída nos 365 dias antes da entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0 | 765.646 | 79,44% | 7,51% |
| 1 | 115.678 | 12,00% | 16,60% |
| 2 | 33.288 | 3,45% | 28,70% |
| 3–4 | 22.201 | 2,30% | 41,29% |
| 5+ | 26.954 | 2,80% | 67,20% |

#### `dias_internado_365d`: Dias internado nesses episódios, dentro da janela

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0 | 795.495 | 82,54% | 8,85% |
| 1–3 | 54.465 | 5,65% | 14,96% |
| 4–7 | 35.313 | 3,66% | 21,00% |
| 8–14 | 29.659 | 3,08% | 26,62% |
| 15–30 | 25.421 | 2,64% | 33,63% |
| 31+ | 23.414 | 2,43% | 47,31% |

#### `dias_desde_ultima_alta`: Dias entre a última alta anterior da chave e a entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| 0–1 | 25.349 | 2,63% | 30,44% |
| 2–7 | 25.914 | 2,69% | 42,75% |
| 8–30 | 52.120 | 5,41% | 41,73% |
| 31–90 | 44.588 | 4,63% | 20,19% |
| 91–180 | 26.547 | 2,75% | 14,38% |
| 181–365 | 23.603 | 2,45% | 11,34% |
| 366+ | 9.417 | 0,98% | 9,45% |
| sem episódio anterior | 756.229 | 78,47% | 7,48% |

#### `historico_com_obito`: Algum episódio anterior da chave terminou em óbito (colisão)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 1.680 | 0,17% | 4,11% |
| não | 962.087 | 99,83% | 11,79% |

#### `chave_colidente`: A chave tem episódios sobrepostos no tempo (D01)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 17.239 | 1,79% | 21,72% |
| não | 946.528 | 98,21% | 11,60% |

#### `episodio_sobreposto`: Este episódio se sobrepõe a outro da mesma chave

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias |
| --- | ---: | ---: | ---: |
| sim | 12.801 | 1,33% | 13,73% |
| não | 950.966 | 98,67% | 11,75% |
<!-- atributos:fim -->
