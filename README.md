# Readmissão SUS

Previsão de readmissão hospitalar em 30 dias com dados públicos do SIH/SUS (Pernambuco, 2023–2024) e geração do Sumário de Alta em FHIR no padrão da RNDS.

> **Aviso:** este é um projeto de estudo e portfólio feito sobre dados públicos e anonimizados do DATASUS. Não é ferramenta clínica e não deve apoiar decisões sobre pacientes reais.
>
> **Não há envio real à RNDS.** Os documentos FHIR são gerados e validados apenas localmente, com o validador oficial da HL7 e os perfis publicados. Nenhum dado é transmitido à Rede Nacional de Dados em Saúde.

## Objetivo

1. Baixar as AIHs reduzidas (RD) do SIH/SUS de Pernambuco, de 2023 e 2024, direto do FTP do DATASUS.
2. Montar a base de internações e identificar readmissões em até 30 dias após a alta.
3. Treinar e avaliar um modelo que estima o risco de readmissão.
4. Gerar, para cada alta, um Sumário de Alta em FHIR conforme os perfis da RNDS e validá-lo localmente.

É a segunda versão do projeto Health-Project, que usava um conjunto de dados de diabetes dos EUA. Esta versão troca a fonte por dados brasileiros e acrescenta a interoperabilidade com FHIR.

## Estrutura

```
readmissao-sus/
├── data/              # dados baixados e processados (fora do git)
├── docs/              # planejamento do projeto
├── fhir/pacotes/      # pacotes FHIR (.tgz) usados na validação
├── fhir/exemplos/     # Sumário de Alta de exemplo: um válido e um propositalmente inválido
├── fhir/saida/        # Sumários de Alta gerados de episódios reais (fora do git)
├── models/           # modelo treinado e metadata (fora do git)
├── reports/          # métricas agregadas do modelo (só metrics.json e importancia_atributos.csv vão para o git)
├── sql/               # SQL versionado do banco DuckDB (staging, internações, coorte, episódios)
├── src/readmissao_sus/  # código do pacote
├── tests/             # testes com pytest
├── pytest.ini
└── requirements.txt
```

Os arquivos de dados (`.dbc`, `.dbf`, `.parquet`, `.duckdb`) e as pastas `data/` e `fhir/saida/` nunca vão para o git.

## Como rodar

Requer Python 3.13. No Windows:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
```

Para baixar o SIH-RD de PE (2023–2024) para `data/raw/`, convertê-lo em Parquet (`data/parquet/`) e gerar o inventário de colunas (`docs/inventario-sih.md`):

```powershell
.venv\Scripts\python scripts\baixar_sih.py
```

O script é idempotente: rodar de novo não baixa nem converte o que já existe.

Os arquivos `.dbc` do DATASUS são lidos com `pyreaddbc`, que funciona no Windows (o PySUS não funciona bem nesse sistema).

Para medir a viabilidade do linkage (chave NASC + SEXO + CEP + MUNIC_RES, guardada só como hash) e atualizar os números em `docs/decisoes.md`:

```powershell
.venv\Scripts\python scripts\medir_linkage.py
```

O documento recebe só agregados; nenhuma chave ou registro por internação é gravado.

Para recriar do zero o banco DuckDB `data/sih.duckdb` (staging tipado, internações, coorte de altas e episódios, com o SQL versionado em `sql/`) e atualizar as contagens de `docs/coorte.md`:

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

Leva cerca de 5 minutos. O banco junta em episódios as internações contíguas após transferência ou permanência (S07); a regra para alta seguida de nova AIH no mesmo dia ou no seguinte aguarda decisão (D03 em `docs/decisoes.md`) e muda com `--contiguas-sem-motivo nenhuma|mesmo_hospital|todas` (padrão `nenhuma`). O banco guarda a chave de linkage como SHA-256 com sal; o sal vem de `READMISSAO_SAL_CHAVE` ou de `data/sal_chave.txt` (criado na primeira vez). Banco, sal e chave ficam em `data/`, fora do git. Filtros, marcas e o motivo do sal estão em `docs/coorte.md`.

O mesmo comando monta a tabela `atributo_episodio` (S09, `sql/06_atributos.sql`): uma linha por episódio elegível, com o alvo `readmissao_30d`, os atributos do paciente e do episódio e o histórico da mesma chave nos 365 dias antes da entrada, sem vazamento. As definições, as fontes dos códigos (capítulo da CID-10, grupo SIGTAP) e as contagens agregadas por atributo ficam em `docs/atributos.md`.

Para baixar os pacotes FHIR do Sumário de Alta para `fhir/pacotes/` (versão e SHA-256 fixos; rodar de novo não baixa nada):

```powershell
.venv\Scripts\python scripts\baixar_pacotes_fhir.py
```

Não há perfil FHIR nacional do Sumário de Alta publicado. O projeto usa o perfil `sumario-alta` do guia CORE da SES-GO (versão 1.2.6, **rascunho**, ambiente de homologação) com os artefatos da RNDS do pacote `br.go.ses.reds-go`. Os motivos e as URLs canônicas estão na decisão D02 de `docs/decisoes.md`.

### Treinar o modelo (S10)

Depois de `construir_banco.py`, para treinar o modelo de readmissão em 30 dias com validação temporal:

```powershell
.venv\Scripts\python scripts\treinar.py
```

Leva cerca de 10 minutos em CPU de 12 threads (`random_state = 42`). O script lê `atributo_episodio`, treina com as altas de 2023 e testa nas de 2024 até o corte de censura (01/10/2024). Grava o pipeline e o limiar em `models/` (fora do git) e só agregados em `reports/metrics.json` e `reports/importancia_atributos.csv`. Nenhuma previsão por episódio é gravada. Atributos que entram e ficam fora, a validação cruzada e as checagens estão em `docs/modelo.md`; os números estão em "Resultados do modelo (S10)", no fim deste README.

### Validar um documento FHIR (validador HL7 em Docker)

O validador oficial da HL7 (`validator_cli.jar` 7.0.3, SHA-256 conferido) roda num container `eclipse-temurin:21.0.13.1_2-jre` (tag e digest fixos). Não é preciso instalar Java no Windows; basta o Docker Desktop aberto.

```powershell
.venv\Scripts\python scripts\validar_fhir.py fhir\exemplos\sumario-alta-valido.json
.venv\Scripts\python scripts\validar_fhir.py fhir\exemplos\sumario-alta-invalido.json
```

O script valida contra `fhir/pacotes/` (`-ig`), aplica o perfil `sumario-alta` à Composition do Bundle (`-bundle Composition:0 <perfil>`), lê o OperationOutcome gerado com `-output` e imprime as mensagens e um resumo (erros, avisos, informações). Código de saída: **0** sem erros, **1** com erro de validação, **2** se o validador não rodou (Docker parado, pacote ausente etc.).

- O jar é baixado uma vez para `.cache/validador/` (fora do git). As dependências HL7 (`hl7.fhir.r4.core`, `hl7.terminology.r4`, `hl7.fhir.uv.extensions.r4` etc.) e as respostas do servidor de terminologia ficam no volume Docker `readmissao-sus-fhir`. A primeira execução baixa cerca de 200 MB e leva alguns minutos; depois, cada validação leva de 30 s a 1 min (quase tudo é a carga dos pacotes).
- Por padrão os códigos são conferidos no servidor de terminologia `tx.fhir.org`. Se ele não responder, o script valida de novo com `-tx n/a` e diz isso na linha "Modo". `--sem-terminologia` força esse modo. Sem terminologia, códigos de CodeSystems externos (LOINC, SNOMED etc.) não são checados; os CodeSystems e ValueSets que vêm completos nos pacotes (CID-10, Tabela SUS, municípios e demais tabelas da RNDS) continuam sendo checados localmente.
- Duas mensagens causadas pelo próprio perfil da SES-GO, e não pelo documento, aparecem como `[CONHECIDA]`, com a justificativa, e não contam como aviso. A lista fica em `MENSAGENS_CONHECIDAS` (`src/readmissao_sus/validador_fhir.py`) e está explicada na D02 de `docs/decisoes.md`.

Os exemplos em `fhir/exemplos/` usam só dados fictícios. O inválido tem dois erros de propósito: falta a seção obrigatória "Procedimento(s)" e o diagnóstico usa `I5099`, que não existe na CID-10.

Uma pasta também pode ser validada. Todos os `.json` dela passam numa única execução do validador (os pacotes carregam uma vez só), com uma linha de resumo por arquivo e o total:

```powershell
.venv\Scripts\python scripts\validar_fhir.py fhir\saida
```

### Sumário de Alta a partir do episódio (S08)

`src/readmissao_sus/fhir_sumario.py` transforma um episódio (S07) num Bundle do tipo `document`. O Bundle tem Composition (`sumario-alta`), Patient, Encounter, Organization, Practitioner, um Condition por CID-10 e um Procedure por AIH, com os perfis da D02. A construção (`montar_bundle`) é uma função pura, testada sem banco. A leitura dos episódios fica em `src/readmissao_sus/episodio_leitura.py`, e os mapeamentos de código ficam em `src/readmissao_sus/sih_fhir_mapa.py`.

```powershell
.venv\Scripts\python scripts\gerar_sumarios.py
```

O script escolhe 20 episódios de `coorte_episodio` e grava um Bundle por episódio em `fhir/saida/`. Essa pasta fica fora do git, porque os Bundles vêm de dados reais do SIH. Depois o script valida a pasta inteira numa só chamada do validador. `--sem-validar` só gera os arquivos.

A amostra é estratificada e determinística (ordem por `md5(episodio_id)` em cada estrato). Os estratos são: episódio simples eletivo e de urgência dos dois sexos, acidente (`CAR_INT` 05/06), menor de 1 ano, longa permanência (AIH 5), saída final por transferência, transferência entre hospitais (urgência e eletivo), permanência (urgência e eletivo) e transferência com permanência. Entram só episódios cujos códigos existem nos CodeSystems do pacote da RNDS e cujo hospital da alta tem CNPJ e município nos Parquet. Em toda a base, só 4 internações têm CID fora do BRCID10 e 902 têm procedimento fora do BRTabelaSUS.

Resultado em 23/11/2026, com terminologia (tx.fhir.org): **20 de 20 Bundles válidos, 0 erro**. Cada arquivo tem 2 avisos e 2 ou 3 mensagens conhecidas do perfil (as da D02). Os 2 avisos são a invariante `NumeroTelefoneValido` no telefone do hospital e no do profissional: o SIH não tem telefone, e o valor vai como ausente (ver abaixo). São avisos do documento, não do perfil, e por isso não entram em `MENSAGENS_CONHECIDAS`.

#### Mapeamento campo do SIH -> elemento FHIR

| Campo do SIH-RD | Origem | Elemento FHIR | Regra |
| --- | --- | --- | --- |
| `N_AIH` da primeira AIH (`episodio_id`) | banco | `Bundle.identifier`, `fullUrl` de cada entrada | UUID v5 determinístico por episódio e papel; os `N_AIH` aparecem na narrativa do Encounter |
| `DT_INTER` da primeira AIH | banco | `Encounter.period.start` | data (o SIH não tem hora) |
| `DT_SAIDA` da última AIH | banco | `Encounter.period.end`, `Condition.recordedDate` | data |
| `CAR_INT` da primeira AIH | banco | `Encounter.priority` (BRCaraterAtendimento) | 01 → 01 Eletivo; 02 → 02 Urgência; 03–06 (acidentes e lesões) → 02; outro → 99 |
| `COBRANCA` da última AIH | banco | `Encounter.hospitalization.dischargeDisposition` (BRMotivoDesfecho) | 11, 12, 13, 17, 19, 61–64 → 01 Alta clínica; 14 → 02 Alta voluntária; 16 → 04 Evasão; 15 → 08 Retorno; 21–28 → 07 Permanência; 29, 31, 32 → 09 Transferência; 41–43, 65–67 → 06 Óbito; 18 e 51 → 99 Sem registro |
| — | fixo | `Encounter.class` (BRModalidadeAssistencial) | 04 Atenção Hospitalar |
| — | ausente no SIH | `Encounter.hospitalization.admitSource` (BRProcedencia) | 99 Informação ausente no modelo de origem |
| `DIAG_PRINC` de cada AIH | banco | `Condition.code` (BRCID10), `Encounter.diagnosis` | um Condition por CID distinto. O da primeira AIH é o principal (BRCategoriaDiagnostico 01); os outros são secundários (02). O SIH grava sem ponto (`I500`), no mesmo formato do BRCID10; um ponto, se vier, é retirado |
| `PROC_REA` de cada AIH | banco | `Procedure.code` (BRTabelaSUS, ValueSet `br-tabela-sus`), `Encounter.diagnosis` | um Procedure por AIH, 10 dígitos. `performedDateTime` é a entrada da AIH (o perfil não aceita `performedPeriod`) |
| `CNES` da última AIH | banco | `Organization.identifier` (sid/cnes), `Encounter.serviceProvider`, `Composition.author` | 7 dígitos; hospital da alta |
| `CGC_HOSP` (senão `CNPJ_MANT`) da última AIH | Parquet | `Organization.identifier` (sid/cnpj) | o perfil exige CNPJ ou CPF; sem `CGC_HOSP`, vai o CNPJ da mantenedora |
| `MUNIC_MOV` da última AIH | Parquet | `Organization.address.city` e `.state` | código IBGE de 6 dígitos (BRMunicipio); a UF são os 2 primeiros dígitos |
| `SEXO` | banco | `Patient.gender` | 1 → male; 3 → female; outro → unknown |
| `IDADE`, `COD_IDADE` | banco | `Patient.birthDate` | **aproximada**: data de entrada menos a idade (COD_IDADE 2 dias, 3 meses de 30 dias, 4 anos, 5 anos + 100). Preserva só a idade na entrada |
| `MUNIC_RES` | banco | `Patient.address.city` e cidade de nascimento (`patient-birthPlace`) | código IBGE de 6 dígitos. Na cidade de nascimento é um **substituto**: ver abaixo |
| `RACA_COR` | Parquet | extensão BRRacaCorEtnia (BRRacaCor) | mesmo código (01–05, 99) |
| `NACIONAL` | Parquet | extensão BRNacionalidade | 010 → B (brasileiro); outro → E |
| chave de linkage (hash com sal) | banco | `Patient.identifier` (sid/cns), `Patient.name` | **sintéticos**: ver abaixo |

**Dado ausente.** Quando o perfil pede um elemento que o SIH não tem, o elemento leva a extensão `data-absent-reason` (`unknown`) em vez de um valor inventado. Isso vale para o CPF do paciente, as linhas do endereço do paciente, o telefone, o CEP, o bairro e o logradouro do hospital, e o CPF e o telefone do profissional. A filiação vai com tipo `03` (Informação desconhecida) e nome "Não informado", porque a invariante do perfil exige um nome com duas palavras. Três elementos não aceitam `data-absent-reason` e recebem um substituto, dito na narrativa:

- cidade de nascimento do paciente brasileiro: a invariante `MunicipioNascimentoSeNacionalidadeBrasileira` exige um código do BRMunicipio. Vai o município de residência;
- data de nascimento do paciente: aproximada pela idade (tabela acima);
- data de nascimento do profissional: a invariante `DataComPrecisaoDeDia` exige uma data com dia. Vai `1900-01-01`, num profissional que já é um marcador.

**Paciente sintético.** O SIH-RD público não tem CNS, CPF nem nome, e o perfil `individuo` exige CPF e CNS (fatiamento fechado, 2..2). O CNS é um número sintético de 15 dígitos derivado da chave de linkage (SHA-256 com sal; S06). A mesma pessoa tem o mesmo CNS em todos os episódios. O número começa com 0, que nenhum CNS real usa (os definitivos começam com 1 ou 2; os provisórios, com 7, 8 ou 9), então nunca é o cartão de alguém. O nome é "Paciente Sintético" seguido de 8 caracteres de outro hash da chave. NASC e CEP não são lidos: o banco não os guarda em claro, e a leitura dos Parquet seleciona só `CGC_HOSP`, `CNPJ_MANT`, `MUNIC_MOV`, `RACA_COR` e `NACIONAL`.

**Profissional.** O perfil exige um profissional como autor e como participante do Encounter, mas o SIH-RD não identifica o médico. Todos os Bundles usam o mesmo Practitioner "Profissional Não Identificado", com sexo `unknown`.

**Episódios com várias AIHs** (transferência, permanência) viram um único Encounter. O período vai da entrada da primeira AIH à saída da última. O caráter vem da primeira AIH, e o desfecho, da última. O hospital da alta é o `serviceProvider` e o autor. Os outros hospitais aparecem só na narrativa e na extensão obrigatória de evolução do Encounter, com o CNES e as datas de cada AIH. Essa extensão também diz que o SIH não traz a evolução clínica. Cada AIH tem seu Procedure.

Os testes de integração (rodam o validador de verdade; pulados se o Docker estiver ausente ou parado) ficam fora da suíte padrão:

```powershell
.venv\Scripts\python -m pytest -m integracao
```

## Resultados do modelo (S10)

Treino de 23/11/2026 com `.venv\Scripts\python scripts\treinar.py` (padrões: `--fracao-cv 0.5`, `--random-state 42`), 10 minutos em CPU de 12 threads. Os números completos estão em `reports/metrics.json`; as escolhas, em `docs/modelo.md`.

Divisão temporal: **treino** com as 533.083 altas de 2023 (436.823 chaves) e **teste** com as 430.684 altas de 2024 até 01/10/2024 (357.355 chaves). 39.435 chaves têm altas nos dois anos, como teriam em uso. A validação cruzada usa 50% das chaves do treino (266.536 episódios), em 5 folds agrupados pela chave.

Validação cruzada no treino (5 folds, média ± desvio):

| Modelo | ROC-AUC | PR-AUC |
| --- | --- | --- |
| Logistic Regression | 0,800 ± 0,002 | 0,447 ± 0,014 |
| Random Forest | 0,814 ± 0,003 | 0,487 ± 0,014 |
| **XGBoost (vencedor)** | **0,837 ± 0,002** | **0,533 ± 0,013** |

Teste (XGBoost, avaliado uma vez):

| Métrica | Valor |
| --- | --- |
| ROC-AUC | 0,839 |
| PR-AUC | 0,555 (prevalência 0,120) |
| Brier | 0,075 |
| Limiar (máx. F1 out-of-fold) | 0,260 |
| Precisão / recall / F1 no limiar | 0,515 / 0,513 / 0,514 |
| Matriz de confusão `[[VN, FP], [FN, VP]]` | `[[354367, 24825], [25098, 26394]]` |
| Calibração (dez faixas do previsto) | maior diferença entre previsto e observado: 0,7 ponto percentual |

Por grupo, no mesmo limiar:

| Grupo | Episódios | Prevalência | ROC-AUC | PR-AUC | Precisão | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cep_generico` = não | 237.050 | 0,136 | 0,857 | 0,618 | 0,538 | 0,594 |
| `cep_generico` = sim | 193.634 | 0,099 | 0,807 | 0,438 | 0,463 | 0,377 |
| `historico_completo` = sim | 424.949 | 0,119 | 0,839 | 0,555 | 0,516 | 0,512 |
| `historico_completo` = não (entrada em 2023) | 5.735 | 0,161 | 0,807 | 0,546 | 0,469 | 0,521 |
| `chave_colidente` = não | 422.850 | 0,118 | 0,840 | 0,554 | 0,515 | 0,513 |
| `chave_colidente` = sim | 7.834 | 0,210 | 0,796 | 0,593 | 0,534 | 0,493 |
| caráter eletivo (01) | 140.683 | 0,149 | 0,902 | 0,723 | 0,583 | 0,729 |
| caráter urgência (02) | 288.342 | 0,106 | 0,791 | 0,414 | 0,444 | 0,365 |

- **CEP genérico (D01, condição 2).** O modelo vai pior nesse grupo (ROC-AUC 0,807 contra 0,857). É o esperado: com o CEP geral da cidade, a chave junta mais pessoas, o histórico da chave mistura gente e parte das readmissões reais some (a taxa é menor, 9,9% contra 13,6%).
- **Histórico incompleto em 2023.** No treino, nenhuma entrada tem os 365 dias de histórico nos dados (média de `episodios_365d` 0,44, contra 0,78 no teste). Mesmo assim, o modelo vai bem no teste, que tem histórico completo (0,839), e segue calibrado. Treinar só com as entradas a partir de 01/07/2023 (266.921 episódios, com ao menos 181 dias de histórico) não melhora o teste: ROC-AUC 0,838. Não dá para treinar só com `historico_completo = true` em 2023, porque esse grupo não existe no ano. Os 5.735 episódios de 2024 com entrada em 2023 vão um pouco pior (0,807).

Importância por permutação (queda de ROC-AUC no teste, 50 mil episódios): `grupo_sigtap` 0,062, `cnes_alta` 0,045, `capitulo_cid` 0,026, `dias_permanencia` 0,022, `idade` 0,016, `episodios_365d` 0,013; os demais ficam abaixo de 0,01 (`reports/importancia_atributos.csv`).

> **ROC-AUC acima de 0,80 é tratado como suspeita de vazamento e investigado.** O teste deu 0,839, então a suspeita vale para este resultado. O que foi checado (`investigacao_vazamento` em `reports/metrics.json`):
>
> - **Nenhum atributo sozinho explica o resultado.** O melhor atributo isolado no teste é `episodios_365d`, com ROC-AUC 0,698. Um vazamento direto (um campo que carrega o rótulo) costuma aparecer aqui com AUC perto de 1.
> - **Nenhum grupo de atributos carrega o resultado sozinho.** Sem o histórico da chave, o teste vai a 0,827; sem o hospital da alta, a 0,822.
> - **Os atributos só usam o passado.** O histórico só conta episódios que terminaram até a entrada (S09); `chave_colidente` e `episodio_sobreposto`, que podem olhar o futuro, ficaram fora; o teste é de um ano posterior ao treino; e nenhuma chave aparece em dois folds.
> - **Readmissões em 0–1 dia.** São 23% dos positivos do teste (11.843): a AIH seguinte começou no dia da alta ou no seguinte, muitas vezes no mesmo hospital (D03, pendente). Sem elas, o teste fica em 0,831.
> - **O sinal se concentra nas internações eletivas** (0,902, contra 0,791 nas de urgência) e, pela permutação, no tipo de procedimento, no hospital e no capítulo da CID. A explicação provável é que o rótulo inclui readmissões **programadas** (ciclos de tratamento, procedimentos em etapas, AIHs sucessivas), que são fáceis de prever pelo procedimento e pelo hospital. Isso não é vazamento de dado futuro, mas infla a métrica em relação à pergunta clínica (volta não planejada). A S10 não separa readmissões programadas: fica como próximo passo, junto com a D03.
>
> Conclusão: não foi achado vazamento de informação posterior à alta. O número continua sob a ressalva de que boa parte do sinal vem de readmissões programadas e contíguas, e não deve ser comparado com os 0,64–0,68 do Health-Project nem com modelos de readmissão não planejada.
