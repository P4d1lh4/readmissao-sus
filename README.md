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

Para baixar os pacotes FHIR do Sumário de Alta para `fhir/pacotes/` (versão e SHA-256 fixos; rodar de novo não baixa nada):

```powershell
.venv\Scripts\python scripts\baixar_pacotes_fhir.py
```

Não há perfil FHIR nacional do Sumário de Alta publicado. O projeto usa o perfil `sumario-alta` do guia CORE da SES-GO (versão 1.2.6, **rascunho**, ambiente de homologação) com os artefatos da RNDS do pacote `br.go.ses.reds-go`. Os motivos e as URLs canônicas estão na decisão D02 de `docs/decisoes.md`.

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
