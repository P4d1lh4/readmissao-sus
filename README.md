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
├── sql/               # SQL versionado do banco DuckDB (staging, internações, coorte)
├── src/readmissao_sus/  # código do pacote
├── tests/             # testes com pytest
├── pytest.ini
└── requirements.txt
```

Os arquivos de dados (`.dbc`, `.dbf`, `.parquet`, `.duckdb`) e a pasta `data/` nunca vão para o git.

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

Para recriar do zero o banco DuckDB `data/sih.duckdb` (staging tipado, internações e coorte de altas, com o SQL versionado em `sql/`) e atualizar as contagens de `docs/coorte.md`:

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

Leva cerca de 1 minuto. O banco guarda a chave de linkage como SHA-256 com sal; o sal vem de `READMISSAO_SAL_CHAVE` ou de `data/sal_chave.txt` (criado na primeira vez). Banco, sal e chave ficam em `data/`, fora do git. Filtros, marcas e o motivo do sal estão em `docs/coorte.md`.

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

Os testes de integração (rodam o validador de verdade; pulados se o Docker estiver ausente ou parado) ficam fora da suíte padrão:

```powershell
.venv\Scripts\python -m pytest -m integracao
```
