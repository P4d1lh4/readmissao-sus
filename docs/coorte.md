# Coorte de altas (S06) e episódios (S07)

Banco DuckDB local (`data/sih.duckdb`, fora do git) montado a partir dos Parquet do SIH-RD de PE, com o SQL versionado em `sql/`. Este documento explica as tabelas e as regras, mostra quantas linhas cada filtro remove e quantas internações viraram episódios.

## Como recriar

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

O comando apaga e recria o banco do zero a partir de `data/parquet/RDPE*.parquet` (cerca de 5 min; a maior parte é montar os episódios com as quatro regras comparadas). Ele monta tudo num arquivo temporário (`data/sih.duckdb.novo`) e só troca o banco antigo no fim. Depois reescreve os dois blocos de contagens abaixo, entre as marcas `coorte` e `episodios`. O resto deste arquivo não é tocado.

A regra das contíguas sem motivo (D03) é um parâmetro: `--contiguas-sem-motivo nenhuma|mesmo_hospital|todas` (padrão `nenhuma`, definido em `REGRA_PADRAO` de `src/readmissao_sus/episodios.py`). `--sem-permanencia` deixa de juntar a saída por permanência.

## Tabelas

| Tabela | Arquivo SQL | Uma linha por | Conteúdo |
| --- | --- | --- | --- |
| `dic_cobranca` | carregada de `dicionario_sih.py` | código de COBRANCA | descrição e marcas de óbito e transferência |
| `stg_aih` | `sql/01_staging.sql` | linha dos Parquet | campos tipados (datas como DATE, MORTE como booleano, IDADE e UTI_MES_TO como inteiros), chave de linkage com sal e marcas de qualidade |
| `internacao` | `sql/02_internacao.sql` | internação (AIH IDENT = 1) | saída e motivo finais, `obito`, `longa_permanencia` e marcas da chave |
| `coorte` | `sql/03_coorte.sql` | alta sem óbito | colunas de `internacao` mais as marcas `censurada`, `alta_antes_do_inicio` e `elegivel_indice` |
| `coorte_filtros`, `coorte_detalhes` | `sql/03_coorte.sql` | filtro / item | as contagens deste documento |
| `coorte_parametros` | `banco.py` | — | última competência, início, data de corte e fim da cobertura |
| `episodio_candidato` | `sql/04_episodio.sql` | par de internações contíguas | tipo da ligação (transferência, permanência, sem motivo), se a regra aceita e as comparações de hospital, CID e procedimento |
| `episodio_ligacao` | `sql/04_episodio.sql` | ligação A → B aceita | no máximo uma por internação anterior e uma por seguinte |
| `episodio_membro` | `sql/04_episodio.sql` | internação | episódio (`episodio_id` = `n_aih` da primeira), posição na cadeia e tipo da ligação que a trouxe |
| `episodio` | `sql/04_episodio.sql` | episódio | entrada da primeira, saída e desfecho da última, AIHs e hospitais em ordem, contagem de ligações por tipo |
| `coorte_episodio` | `sql/04_episodio.sql` | episódio sem óbito | colunas de `episodio` mais `censurada`, `alta_antes_do_inicio`, `elegivel_indice`, `fim_sem_continuacao`, `dias_ate_readmissao` e `readmissao_30d` |
| `episodio_resumo`, `episodio_motivos`, `contiguas_sem_motivo`, `contiguas_procedimentos` | `sql/05_episodio_contagens.sql` | item | as contagens do bloco `episodios` |
| `episodio_parametros` | `episodios.py` | — | a regra usada (`juntar_permanencia`, `contiguas_sem_motivo`), contiguidade e janela |
| `dic_sexo`, `dic_cid10_capitulo`, `dic_sigtap_grupo` | carregadas de `dicionario_sih.py` | código | sexo, faixas dos capítulos da CID-10 e grupos SIGTAP (S09; fontes em `docs/atributos.md`) |
| `episodio_sobreposicao` | `sql/06_atributos.sql` | par de episódios sobrepostos da mesma chave | colisões da D01, por episódio |
| `atributo_episodio` | `sql/06_atributos.sql` | episódio elegível | alvo, atributos do episódio e histórico da chave (S09, `docs/atributos.md`) |

A `internacao` guarda também os óbitos: uma readmissão pode terminar em óbito, e a S07 precisa dela para achar a próxima internação. A `coorte` é o conjunto de altas que podem ser internação-índice.

As regras de internação (deduplicação por `N_AIH`, IDENT = 5 como continuação, óbito) existem só em `sql/01_staging.sql` e `sql/02_internacao.sql`. `src/readmissao_sus/linkage_viabilidade.py` (S03) roda os mesmos dois arquivos num banco em memória. Os números da D01 em `docs/decisoes.md` não mudaram com isso (conferido rodando `scripts/medir_linkage.py`).

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

## Episódios (S07)

Uma internação que continua em outra AIH (transferência, troca de AIH com o paciente ainda internado) não é readmissão. A S07 junta essas internações num **episódio** e passa a usar o episódio como unidade da coorte e do rótulo. O SQL está em `sql/04_episodio.sql` (regras) e `sql/05_episodio_contagens.sql` (contagens); `src/readmissao_sus/episodios.py` define os parâmetros e roda os dois.

### Regra de junção

A internação B continua a internação A quando:

1. as duas têm a mesma chave de linkage;
2. A não terminou em óbito;
3. B começa no dia da saída de A ou no dia seguinte (`0 ≤ DT_INTER(B) − DT_SAIDA(A) ≤ 1`) e vem depois de A na ordem `(DT_INTER, DT_SAIDA, N_AIH)`, a mesma da D01. B que começa antes da saída de A é sobreposta (colisão, D01 tratamento 5) e nunca junta;
4. o motivo de saída de A (`COBRANCA`, pelo dicionário `SAIDAPERM.CNV`) permite:
   - **transferência** (29, 31, 32): sempre junta;
   - **permanência** (21–28: a AIH fecha, mas o paciente continua internado): junta por padrão (`juntar_permanencia = True`; ampliação baseada na D01, tratamento 6);
   - **outras saídas sem óbito** (alta 1x, encerramento administrativo 51, alta no parto 6x): dependem da D03 (`contiguas_sem_motivo`). O padrão conservador é `nenhuma`: só junta o que o motivo de saída justifica, e a alta seguida de nova AIH continua contando como readmissão. `mesmo_hospital` (proposta da D03) junta quando a nova AIH é no mesmo CNES; `todas` junta qualquer contígua.

Quando há mais de uma candidata, cada A fica com a primeira B (pela ordem acima) e cada B fica com a A de saída mais tardia. Assim cada internação tem no máximo uma anterior e uma seguinte, e as ligações formam **cadeias**: A → B → C vira um único episódio (posição 1, 2, 3 em `episodio_membro`). As candidatas que perdem a disputa ficam como episódios próprios e são contadas no bloco ("ficaram sem par").

### O que o episódio herda

- **Entrada** (`dt_inter`, `cnes`, `diag_princ`, `proc_rea`, `car_int`, idade): da primeira internação. Os dados da última ficam em `cnes_saida`, `diag_princ_saida` e `proc_rea_saida`; `aihs` e `hospitais` guardam a sequência inteira.
- **Saída e desfecho** (`dt_saida`, `cobranca`, `morte`, `obito`): da última internação. Óbito no fim da cadeia tira o episódio inteiro da `coorte_episodio`, como o filtro 4 da S06 tira a internação com óbito. Uma alta sem óbito da S06 seguida de transferência para uma internação que termina em óbito deixa, portanto, de ser alta-índice.
- **Marcas da chave** (`cep_generico`, `cep_zerado`, `nasc_0101`, `nasc_antes_1900`, `nasc_invalida`): iguais em toda a cadeia, porque vêm dos campos da chave. `menor_1_ano` vem da primeira internação. `longa_permanencia` é verdadeira se alguma internação da cadeia teve AIH 5.

### Censura e marcas da coorte

As marcas da `coorte_episodio` são as da S06, calculadas sobre a **saída final do episódio**, com a mesma data de corte:

- `censurada`: a saída final passa da data de corte. Uma cadeia cuja primeira internação seria alta-índice na S06, mas que só termina depois do corte, fica censurada: os 30 dias seguintes ao fim real do cuidado não estão cobertos;
- `alta_antes_do_inicio`: a saída final é anterior a 01/01/2023;
- `elegivel_indice`: nenhuma das duas. Só os episódios elegíveis têm rótulo; nos outros, `readmissao_30d` é nulo;
- `fim_sem_continuacao` (nova): o episódio termina numa saída por transferência ou permanência sem nova AIH em 0–1 dia na mesma chave. Pode ser transferência para fora de PE, para serviço que não fatura AIH, internação domiciliar (29, 32) ou falha do linkage. Fica como marca, não como filtro.

**Readmissão por episódio**: o próximo episódio da mesma chave que começa entre a saída final e 30 dias depois (pode terminar em óbito). Episódios sobrepostos não contam, como na D01.

### Leitura dos números

- A regra padrão (transferência + permanência) junta 118.356 internações e deixa 1.162.040 episódios a partir de 1.280.396 internações. Das 70.159 saídas por transferência sem óbito, 26.792 foram juntadas; quase todas as outras não têm nova AIH da mesma chave em 0–1 dia.
- A taxa de readmissão em 30 dias por episódio fica em **11,78%**, contra os 11,82% da D01 (que tirava a alta-índice contígua do numerador e do denominador, por internação). A diferença é pequena, e a direção era esperada: o episódio é a unidade, as cadeias com óbito no fim saem da coorte e a censura usa a saída final. Os números da D01 não mudam.
- As contíguas sem motivo no período das altas-índice são exatamente as 27.916 da D01. Com a proposta da D03 (mesmo hospital), a taxa cai para 9,53%; juntando todas, 9,13%. A escolha está na D03 de `docs/decisoes.md`.
- O maior episódio tem 40 internações, todas no mesmo hospital e ligadas por permanência (448 dias): AIHs sucessivas de uma internação longa. 182 episódios têm 10 ou mais internações.

### Contagens dos episódios

<!-- episodios:inicio (gerado por scripts/construir_banco.py; não editar à mão) -->
Gerado por `.venv\Scripts\python scripts\construir_banco.py` em 23/11/2026. Só agregados.

Regra usada nas tabelas do banco: **transferência + permanência** (`juntar_permanencia = True`, `contiguas_sem_motivo = 'nenhuma'`). Contígua = nova AIH da mesma chave em 0–1 dia após a saída.

#### Internações x episódios

| Item | Valor |
| --- | ---: |
| Internações (tabela internacao) | 1.280.396 |
| Episódios (tabela episodio) | 1.162.040 |
| Episódios com 2 ou mais internações | 87.445 |
| Internações juntadas a uma anterior (internações − episódios) | 118.356 |
| … depois de transferência | 26.792 |
| … depois de permanência | 91.564 |
| … contíguas sem motivo (regra D03) | 0 |
| Episódios com mais de um hospital | 25.456 |
| Maior episódio (internações) | 40 |
| Candidatas aceitas pela regra que ficaram sem par (disputa entre AIHs) | 144 |
| Contíguas sem motivo com saída anterior no período das altas-índice (D01: 27.916) | 27.916 |

#### Saídas sem óbito por motivo

| Motivo da saída | Saídas | Seguidas de nova AIH em 0–1 dia | Juntadas | % juntadas |
| --- | ---: | ---: | ---: | ---: |
| Transferência (29, 31, 32) | 70.159 | 26.827 | 26.792 | 38,19% |
| Permanência (21–28) | 103.566 | 91.673 | 91.564 | 88,41% |
| Outras saídas sem óbito (alta, 51, 6x) | 1.051.627 | 31.186 | 0 | 0,00% |

#### Internações por episódio

| Item | Valor |
| --- | ---: |
| 1 internação | 1.074.595 |
| 2 internações | 69.252 |
| 3 internações | 11.875 |
| 4 ou mais internações | 6.318 |

#### Desfecho, censura e marcas (coorte_episodio)

| Item | Valor |
| --- | ---: |
| Episódios com óbito na última internação (fora da coorte) | 55.044 |
| … com 2 ou mais internações | 9.587 |
| Altas sem óbito da S06 dentro de episódio terminado em óbito | 15.273 |
| Episódios na coorte (tabela coorte_episodio) | 1.106.996 |
| Elegíveis a alta-índice (elegivel_indice) | 963.767 |
| Censurados: saída final depois da data de corte (censurada) | 131.752 |
| … com internação elegível na S06 (a cadeia passou do corte) | 1.308 |
| Saída final antes do início do período (alta_antes_do_inicio) | 11.477 |
| Elegíveis que terminam em transferência ou permanência sem continuação (fim_sem_continuacao) | 46.568 |
| CEP genérico entre as elegíveis | 436.161 |

#### Readmissão em 30 dias por episódio

| Item | Valor |
| --- | ---: |
| Altas-índice (episódios elegíveis) | 963.767 |
| Readmitidas em 30 dias | 113.511 |
| Taxa de readmissão em 30 dias | 11,78% |
| … início em 0–1 dia | 27.898 |
| … em 2–7 dias | 28.196 |
| … em 8–30 dias | 57.417 |
| Readmitidas em 30 dias sem as voltas programadas (D04) | 69.868 |
| Taxa de readmissão não planejada em 30 dias (alvo da D04) | 7,25% |
| Readmitidas com a primeira volta programada | 45.610 |
| … programada por caráter eletivo | 43.756 |
| … por procedimento sempre programado | 15.019 |
| … por diagnóstico sempre programado | 4 |
| … e com volta não planejada depois, ainda em 30 dias (continuam no alvo) | 1.967 |
| Reclassificadas: readmitidas que saem do alvo (só voltas programadas) | 43.643 |

#### Comparação das regras

| Regra | Internações | Episódios | Altas-índice | Readmitidas | Taxa 30 dias | Não planejadas (D04) | Taxa não planejada |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| transferência | 1.280.396 | 1.253.599 | 1.042.983 | 193.105 | 18,51% | 134.480 | 12,89% |
| transferência + permanência (padrão) | 1.280.396 | 1.162.040 | 963.767 | 113.511 | 11,78% | 69.868 | 7,25% |
| transferência + permanência + contíguas sem motivo no mesmo hospital (proposta D03) | 1.280.396 | 1.135.651 | 940.139 | 89.641 | 9,53% | 51.891 | 5,52% |
| transferência + permanência + todas as contíguas sem motivo | 1.280.396 | 1.131.007 | 935.991 | 85.460 | 9,13% | 48.392 | 5,17% |

Referência (D01, por internação, sem juntar): 20,32% bruta; 11,82% tirando as altas-índice seguidas de contígua após transferência ou permanência.

#### Contíguas sem motivo (D03)

| Saída anterior | Hospital | Pares | Mesmo dia | Mesmo CID (3 car.) | Mesmo procedimento | Mesmo grupo SIGTAP | Seguinte eletiva |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1x (alta) | mesmo | 10.857 | 51,14% | 51,04% | 47,98% | 77,75% | 47,95% |
| 1x (alta) | outro | 4.484 | 72,01% | 16,35% | 12,82% | 68,06% | 18,40% |
| 51 (encerramento administrativo) | mesmo | 12.328 | 78,01% | 55,15% | 58,99% | 88,40% | 14,78% |
| 51 (encerramento administrativo) | outro | 45 | 80,00% | 28,89% | 8,89% | 57,78% | 40,00% |
| 6x (alta no parto) | mesmo | 3.305 | 52,04% | 1,94% | 0,91% | 15,31% | 3,27% |
| 6x (alta no parto) | outro | 167 | 74,85% | 7,19% | 3,59% | 58,08% | 4,79% |

Total: 31.186 pares em toda a base (a primeira AIH seguinte de cada saída). O item "Contíguas sem motivo com saída anterior no período" acima restringe ao período das altas-índice, para comparar com a D01.

Pares de procedimento mais frequentes nas contíguas sem motivo:

| Procedimento anterior | Procedimento seguinte | Hospital | Pares |
| --- | ---: | ---: | ---: |
| 0413040178 | 0413040178 | mesmo | 2.530 |
| 0303010037 | 0303010037 | mesmo | 1.822 |
| 0310010039 | 0411010077 | mesmo | 1.218 |
| 0303140151 | 0303140151 | mesmo | 726 |
| 0303040203 | 0303040203 | mesmo | 680 |
| 0411010026 | 0303100036 | mesmo | 574 |
| 0303040149 | 0303040149 | mesmo | 528 |
| 0303160055 | 0303160055 | mesmo | 515 |
| 0303140135 | 0303140135 | mesmo | 425 |
| 0303160063 | 0303160063 | mesmo | 392 |
<!-- episodios:fim -->
