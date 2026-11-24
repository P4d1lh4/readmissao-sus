# Atributos por episódio (S09)

Tabela `atributo_episodio` do banco DuckDB local (`data/sih.duckdb`, fora do git): uma linha por episódio elegível, ou seja, por episódio de `coorte_episodio` com `readmissao_30d` não nulo (D01: seguir com o linkage). É a entrada do modelo. Este documento traz só agregados; nenhuma linha por episódio sai do banco.

## Como recriar

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

O SQL está em `sql/06_atributos.sql`, rodado por `src/readmissao_sus/atributos.py` depois dos episódios (S07). O script reescreve só o bloco entre as marcas `atributos` abaixo. A regra das contíguas sem motivo (D03) continua parâmetro, com padrão `mesmo_hospital` (decidido em 24/11/2026): `--contiguas-sem-motivo nenhuma|todas` muda os episódios e, com eles, os atributos.

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

Números de 24/11/2026, com a regra da D03 (`mesmo_hospital`); estão no bloco abaixo. As taxas são do alvo do modelo, `readmissao_nao_planejada_30d` (D04). Entre parênteses, a de `readmissao_30d`, que conta também as voltas programadas.

- **940.139 episódios elegíveis**, com taxa de readmissão não planejada de 5,52% (9,53%). São os mesmos da `coorte_episodio` em `docs/coorte.md`: a tabela não tira nem acrescenta episódios.
- **Histórico.** É o grupo de atributos com o sinal mais forte. A readmissão não planejada vai de 4,10% sem episódio anterior em 365 dias a 17,98% com 5 ou mais (5,76% a 67,20%). A taxa também sobe quando a última alta foi há pouco tempo: 18,25% com `dias_desde_ultima_alta` entre 2 e 7 (41,01%). Com o alvo antigo, o histórico parecia bem mais forte porque as voltas programadas (ciclos de tratamento) se repetem nas mesmas chaves.
- **Efeito de `historico_completo`.** Nas entradas com janela incompleta (55,85% dos episódios, quase todas de 2023), só 16,17% têm episódio anterior em 365 dias, contra 22,10% nas de janela completa, e a média de `episodios_365d` cai de 0,729 para 0,403. A diferença é o histórico que ficou antes de 01/01/2023. Mesmo assim, a taxa dos dois grupos é parecida (5,68% e 5,32%; 9,30% e 9,83%). Sem tratamento, o modelo pode ler "sem histórico" em 2023 como risco menor do que é.
- **Colisões.** 7.219 chaves têm episódios sobrepostos. Na D01, que media por internação, eram 7.214; a diferença vem dos episódios juntados pela D03. Entre os elegíveis, 16.336 (1,74%) são de chave colidente e 12.593 (1,34%) se sobrepõem a outro episódio. A taxa nas chaves colidentes (11,92%; 15,89%) é mais que o dobro da geral: quando duas pessoas dividem a chave, as internações de uma viram readmissão da outra. 1.645 elegíveis têm um óbito antes da entrada na mesma chave, o que só acontece com colisão. Essas marcas servem para avaliar o modelo sem esses grupos.
- **CEP genérico.** 45,46% dos elegíveis. Com o alvo antigo, a taxa era menor nesse grupo (8,10% contra 10,73%), como na D01. Com o alvo atual, fica parecida e até um pouco maior (5,62% contra 5,44%). A diferença do alvo antigo vinha das voltas programadas, mais comuns entre as altas com CEP específico.
- **Nulos.** Só `dias_desde_ultima_alta` (80,21%, nulo quando não há episódio anterior nos dados) e uma idade inválida. Nenhum diagnóstico ficou sem capítulo e nenhum procedimento ficou sem grupo.

## Contagens

<!-- atributos:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->
Gerado por `.venv\Scripts\python scripts\construir_banco.py` em 24/11/2026. Só agregados.

Regra dos episódios: **transferência + permanência + contíguas sem motivo no mesmo hospital** (`contiguas_sem_motivo = 'mesmo_hospital'`). Episódios elegíveis (linhas de `atributo_episodio`): **940.139**; readmitidos em 30 dias: 89.641 (9,53%); sem as voltas programadas (alvo da D04): 51.891 (5,52%).

#### Colunas: tipo e nulos

| Coluna | Tipo | Descrição | % nulos |
| --- | ---: | ---: | ---: |
| `episodio_id` | VARCHAR | identificador ou data (não é atributo) | 0,00% |
| `chave` | VARCHAR | identificador ou data (não é atributo) | 0,00% |
| `readmissao_30d` | BOOLEAN | Alvo da S10 (auxiliar): novo episódio da mesma chave em até 30 dias após a alta | 0,00% |
| `readmissao_nao_planejada_30d` | BOOLEAN | Alvo (D04): como readmissao_30d, mas só com voltas não programadas | 0,00% |
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
| `houve_contigua_sem_motivo` | BOOLEAN | Episódio juntou contíguas sem motivo (D03: só no mesmo hospital) | 0,00% |
| `cep_generico` | BOOLEAN | CEP terminado em 000 (D01, condição 2) | 0,00% |
| `cnes_alta` | VARCHAR | CNES do hospital da alta (última internação) | 0,00% |
| `ano_alta` | SMALLINT | Ano da alta | 0,00% |
| `dt_inter` | DATE | identificador ou data (não é atributo) | 0,00% |
| `dt_saida` | DATE | identificador ou data (não é atributo) | 0,00% |
| `historico_completo` | BOOLEAN | Janela de 365 dias antes da entrada inteira dentro dos dados | 0,00% |
| `episodios_365d` | INTEGER | Episódios anteriores da chave com saída nos 365 dias antes da entrada | 0,00% |
| `dias_internado_365d` | INTEGER | Dias internado nesses episódios, dentro da janela | 0,00% |
| `dias_desde_ultima_alta` | INTEGER | Dias entre a última alta anterior da chave e a entrada | 80,21% |
| `historico_com_obito` | BOOLEAN | Algum episódio anterior da chave terminou em óbito (colisão) | 0,00% |
| `chave_colidente` | BOOLEAN | A chave tem episódios sobrepostos no tempo (D01) | 0,00% |
| `episodio_sobreposto` | BOOLEAN | Este episódio se sobrepõe a outro da mesma chave | 0,00% |

#### Efeito do início dos dados no histórico

| historico_completo | Episódios | Com episódio em 365 dias | Média episodios_365d | Média dias_internado_365d | Sem episódio anterior | Readmissão 30 dias | Readmissão com histórico | Readmissão sem histórico |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sim | 415.036 | 22,10% | 0,729 | 2,76 | 75,66% | 9,83% | 25,11% | 5,50% |
| não | 525.103 | 16,17% | 0,403 | 1,83 | 83,82% | 9,30% | 26,66% | 5,95% |

#### Colisões (D01)

| Item | Valor |
| --- | ---: |
| Pares de episódios sobrepostos da mesma chave (toda a tabela episodio) | 8.066 |
| Chaves com episódios sobrepostos | 7.219 |
| Episódios envolvidos em alguma sobreposição | 15.045 |
| Episódios elegíveis com chave_colidente | 16.336 |
| Episódios elegíveis com episodio_sobreposto | 12.593 |
| Episódios elegíveis com historico_com_obito | 1.645 |

#### `readmissao_30d`: Alvo da S10 (auxiliar): novo episódio da mesma chave em até 30 dias após a alta

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 89.641 | 9,53% | 100,00% | 57,89% |
| não | 850.498 | 90,47% | 0,00% | 0,00% |

#### `readmissao_nao_planejada_30d`: Alvo (D04): como readmissao_30d, mas só com voltas não programadas

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 51.891 | 5,52% | 100,00% | 100,00% |
| não | 888.248 | 94,48% | 4,25% | 0,00% |

#### `idade`: Idade em anos na entrada (COD_IDADE em dias ou meses vira 0)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 63.609 | 6,77% | 5,55% | 5,08% |
| 1–4 | 38.227 | 4,07% | 9,06% | 4,93% |
| 5–14 | 55.064 | 5,86% | 12,53% | 6,04% |
| 15–49 | 448.447 | 47,70% | 7,80% | 4,56% |
| 50–64 | 155.516 | 16,54% | 12,35% | 5,89% |
| 65–79 | 127.498 | 13,56% | 12,28% | 7,14% |
| 80+ | 51.777 | 5,51% | 11,44% | 9,17% |
| idade inválida | 1 | 0,00% | 0,00% | 0,00% |

#### `sexo`: Sexo (1 = M; 2 e 3 = F)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| F | 558.659 | 59,42% | 8,97% | 5,05% |
| M | 381.480 | 40,58% | 10,36% | 6,21% |

#### `capitulo_cid`: Capítulo da CID-10 do diagnóstico principal da entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| XV. Gravidez, parto e puerpério | 173.479 | 18,45% | 3,71% | 3,40% |
| XIX. Lesões, envenenamentos e outras consequências de causas externas | 99.162 | 10,55% | 5,01% | 3,78% |
| XI. Doenças do aparelho digestivo | 94.619 | 10,06% | 6,14% | 3,83% |
| II. Neoplasias (tumores) | 82.669 | 8,79% | 28,14% | 5,45% |
| X. Doenças do aparelho respiratório | 81.648 | 8,68% | 8,31% | 7,11% |
| IX. Doenças do aparelho circulatório | 72.491 | 7,71% | 8,54% | 7,37% |
| XIV. Doenças do aparelho geniturinário | 66.380 | 7,06% | 9,16% | 7,10% |
| I. Algumas doenças infecciosas e parasitárias | 46.232 | 4,92% | 10,95% | 7,92% |
| XII. Doenças da pele e do tecido subcutâneo | 38.956 | 4,14% | 7,79% | 4,15% |
| XVI. Algumas afecções originadas no período perinatal | 38.578 | 4,10% | 4,26% | 2,71% |
| XXI. Fatores que influenciam o estado de saúde e o contato com serviços de saúde | 34.156 | 3,63% | 6,64% | 4,47% |
| XVIII. Sintomas, sinais e achados anormais de exames clínicos e laboratoriais | 20.857 | 2,22% | 14,35% | 8,28% |
| VI. Doenças do sistema nervoso | 17.757 | 1,89% | 12,58% | 9,56% |
| XIII. Doenças do sistema osteomuscular e do tecido conjuntivo | 16.412 | 1,75% | 16,81% | 6,89% |
| IV. Doenças endócrinas, nutricionais e metabólicas | 15.897 | 1,69% | 30,56% | 16,55% |
| V. Transtornos mentais e comportamentais | 11.610 | 1,23% | 9,91% | 7,86% |
| VII. Doenças do olho e anexos | 10.427 | 1,11% | 5,19% | 1,13% |
| III. Doenças do sangue, órgãos hematopoéticos e transtornos imunitários | 9.460 | 1,01% | 29,46% | 17,73% |
| XVII. Malformações congênitas, deformidades e anomalias cromossômicas | 7.607 | 0,81% | 9,41% | 5,90% |
| VIII. Doenças do ouvido e da apófise mastoide | 1.691 | 0,18% | 3,49% | 3,19% |
| XXII. Códigos para propósitos especiais | 51 | 0,01% | 7,84% | 7,84% |

#### `grupo_sigtap`: Grupo SIGTAP do procedimento principal da entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 03 Procedimentos clínicos | 533.155 | 56,71% | 13,20% | 7,47% |
| 04 Procedimentos cirúrgicos | 397.364 | 42,27% | 4,28% | 2,58% |
| 05 Transplantes de órgãos, tecidos e células | 7.986 | 0,85% | 25,91% | 22,15% |
| 02 Procedimentos com finalidade diagnóstica | 1.634 | 0,17% | 11,08% | 4,04% |

#### `car_int`: Caráter da internação na entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 02 Urgência | 648.622 | 68,99% | 8,22% | 7,02% |
| 01 Eletivo | 287.265 | 30,56% | 12,55% | 2,14% |
| 05 Outros tipos de acidente de trânsito | 3.309 | 0,35% | 6,47% | 4,47% |
| 06 Outros tipos de lesões e envenenamentos por agentes químicos ou físicos | 943 | 0,10% | 4,14% | 4,03% |

#### `dias_permanencia`: Dias de permanência do episódio (saída − entrada)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 102.837 | 10,94% | 23,15% | 6,55% |
| 1 | 169.103 | 17,99% | 5,59% | 3,28% |
| 2–3 | 295.051 | 31,38% | 6,02% | 3,73% |
| 4–7 | 194.097 | 20,65% | 8,49% | 6,12% |
| 8–14 | 104.431 | 11,11% | 10,87% | 8,17% |
| 15–30 | 53.733 | 5,72% | 14,41% | 10,78% |
| 31+ | 20.887 | 2,22% | 14,72% | 11,46% |

#### `dias_uti`: Diárias de UTI somadas no episódio (UTI_MES_TO)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 895.505 | 95,25% | 9,43% | 5,36% |
| 1–3 | 19.369 | 2,06% | 11,10% | 7,28% |
| 4–7 | 11.087 | 1,18% | 11,17% | 8,42% |
| 8+ | 14.178 | 1,51% | 12,87% | 10,70% |

#### `usou_uti`: Teve diária de UTI no episódio

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 44.634 | 4,75% | 11,68% | 8,65% |
| não | 895.505 | 95,25% | 9,43% | 5,36% |

#### `n_aihs`: Internações (AIHs) no episódio

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 861.669 | 91,65% | 9,27% | 5,25% |
| 2 | 61.935 | 6,59% | 10,81% | 7,39% |
| 3 | 10.995 | 1,17% | 16,58% | 11,10% |
| 4+ | 5.540 | 0,59% | 22,76% | 15,16% |

#### `n_hospitais`: Hospitais (CNES) distintos no episódio

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 921.663 | 98,03% | 9,50% | 5,45% |
| 2 | 17.993 | 1,91% | 10,90% | 8,93% |
| 3+ | 483 | 0,05% | 17,18% | 14,29% |

#### `houve_transferencia`: Episódio juntou internações por transferência

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 18.574 | 1,98% | 11,27% | 9,21% |
| não | 921.565 | 98,02% | 9,50% | 5,45% |

#### `houve_permanencia`: Episódio juntou internações por permanência

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 49.169 | 5,23% | 12,91% | 8,49% |
| não | 890.970 | 94,77% | 9,35% | 5,36% |

#### `houve_contigua_sem_motivo`: Episódio juntou contíguas sem motivo (D03: só no mesmo hospital)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 15.848 | 1,69% | 14,15% | 8,83% |
| não | 924.291 | 98,31% | 9,46% | 5,46% |

#### `cep_generico`: CEP terminado em 000 (D01, condição 2)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 427.410 | 45,46% | 8,10% | 5,62% |
| não | 512.729 | 54,54% | 10,73% | 5,44% |

#### `cnes_alta`: CNES do hospital da alta (última internação)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0000434 | 65.638 | 6,98% | 19,94% | 12,12% |
| 0000655 | 37.991 | 4,04% | 7,35% | 6,73% |
| 0000477 | 34.984 | 3,72% | 39,92% | 0,61% |
| 0000426 | 33.108 | 3,52% | 6,82% | 6,14% |
| 0000396 | 28.185 | 3,00% | 19,83% | 10,28% |
| 2427427 | 25.546 | 2,72% | 8,82% | 3,77% |
| 2802783 | 25.523 | 2,71% | 9,54% | 4,44% |
| 2430711 | 24.193 | 2,57% | 5,32% | 5,18% |
| 0000418 | 24.038 | 2,56% | 5,96% | 5,23% |
| 0000582 | 20.814 | 2,21% | 20,32% | 2,47% |
| outras 250 categorias | 620.119 | 65,96% | 6,50% | 5,02% |

#### `ano_alta`: Ano da alta

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 2023 | 519.393 | 55,25% | 9,28% | 5,64% |
| 2024 | 420.746 | 44,75% | 9,85% | 5,37% |

#### `historico_completo`: Janela de 365 dias antes da entrada inteira dentro dos dados

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 415.036 | 44,15% | 9,83% | 5,32% |
| não | 525.103 | 55,85% | 9,30% | 5,68% |

#### `episodios_365d`: Episódios anteriores da chave com saída nos 365 dias antes da entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 763.503 | 81,21% | 5,76% | 4,10% |
| 1 | 104.557 | 11,12% | 14,09% | 8,78% |
| 2 | 28.935 | 3,08% | 25,25% | 13,56% |
| 3–4 | 18.805 | 2,00% | 38,72% | 16,42% |
| 5+ | 24.339 | 2,59% | 67,20% | 17,98% |

#### `dias_internado_365d`: Dias internado nesses episódios, dentro da janela

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 792.576 | 84,30% | 7,13% | 4,40% |
| 1–3 | 49.732 | 5,29% | 14,14% | 6,44% |
| 4–7 | 31.776 | 3,38% | 18,41% | 9,93% |
| 8–14 | 26.035 | 2,77% | 22,92% | 12,68% |
| 15–30 | 21.786 | 2,32% | 30,02% | 15,61% |
| 31+ | 18.234 | 1,94% | 42,38% | 21,70% |

#### `dias_desde_ultima_alta`: Dias entre a última alta anterior da chave e a entrada

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| 0–1 | 4.676 | 0,50% | 11,42% | 9,37% |
| 2–7 | 25.752 | 2,74% | 41,01% | 18,25% |
| 8–30 | 51.849 | 5,52% | 39,99% | 14,35% |
| 31–90 | 44.389 | 4,72% | 18,39% | 9,66% |
| 91–180 | 26.452 | 2,81% | 12,69% | 7,98% |
| 181–365 | 23.518 | 2,50% | 9,86% | 6,75% |
| 366+ | 9.383 | 1,00% | 7,82% | 5,58% |
| sem episódio anterior | 754.120 | 80,21% | 5,73% | 4,08% |

#### `historico_com_obito`: Algum episódio anterior da chave terminou em óbito (colisão)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 1.645 | 0,17% | 2,61% | 2,13% |
| não | 938.494 | 99,83% | 9,55% | 5,53% |

#### `chave_colidente`: A chave tem episódios sobrepostos no tempo (D01)

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 16.336 | 1,74% | 15,89% | 11,92% |
| não | 923.803 | 98,26% | 9,42% | 5,41% |

#### `episodio_sobreposto`: Este episódio se sobrepõe a outro da mesma chave

| Faixa ou categoria | Episódios | % dos episódios | Readmissão 30 dias | Não planejada 30 dias (D04) |
| --- | ---: | ---: | ---: | ---: |
| sim | 12.593 | 1,34% | 8,93% | 7,05% |
| não | 927.546 | 98,66% | 9,54% | 5,50% |
<!-- atributos:fim -->
