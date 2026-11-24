# Decisões

Registro das decisões do projeto. Cada decisão diz o que foi medido, o que se propõe e o estado ("aguardando decisão" enquanto o usuário não decidir).

## D01 — Viabilidade do linkage determinístico (S03)

**Estado: decidida pelo usuário em 23/11/2026 — seguir com o linkage.**

### Pergunta

O SIH-RD público não traz CNS nem nome. Dá para reconhecer a mesma pessoa em internações diferentes com uma chave determinística `NASC + SEXO + CEP + MUNIC_RES` bem o bastante para usar readmissão em 30 dias como alvo do modelo? Ou é melhor o plano B (óbito hospitalar ou permanência longa, que não dependem de linkage)?

### Como os números são gerados

```powershell
.venv\Scripts\python scripts\medir_linkage.py
```

O script lê `data/parquet/RDPE*.parquet`, roda `src/readmissao_sus/linkage_viabilidade.py` e reescreve só o bloco entre as marcas `linkage-viabilidade` abaixo. A chave existe apenas como hash SHA-256, em tabelas temporárias do DuckDB em memória; NASC, SEXO, CEP e MUNIC_RES são descartados logo depois do hash. Nada por internação é gravado: o documento recebe só contagens agregadas. Um SHA-256 sem sal de uma chave com tão pouca entropia pode ser revertido por força bruta; por isso o hash também nunca é gravado em disco nesta história.

### Tratamentos aplicados

1. **Competência não é data da alta.** O `aamm` do arquivo é a competência de processamento. A internação é definida por `DT_INTER` e `DT_SAIDA`. As AIHs são deduplicadas por `N_AIH`, ficando a da competência mais recente. Resultado: das 1.287.663 linhas, 7.013 têm `N_AIH` repetido, e **todas são IDENT=5**; entre as AIHs IDENT=1 havia **0 duplicatas**. A deduplicação continua no código para o caso de reapresentação em outra competência.
2. **IDENT=5 (longa permanência).** A AIH 5 é continuação de uma AIH 1 com o mesmo `N_AIH`: mantém a `DT_INTER` original e avança a `DT_SAIDA` (conferido nos dados: em todas as 6.318 junções a data de internação é a mesma e a saída é posterior). Por isso só IDENT=1 forma internação. Quando há AIH 5, a saída do episódio passa a ser a maior `DT_SAIDA` das AIHs 5, e o motivo de saída (`COBRANCA`, `MORTE`) vem dessa última AIH 5. A AIH 5 nunca é internação-índice nem readmissão. As 254 AIHs 5 sem a AIH 1 correspondente nos dados (internações que começaram antes de 2023) são descartadas.
3. **Censura.** AIHs de uma saída aparecem em competências até 5 meses depois (tabela "Cobertura e censura"). Com a última competência em 12/2024, os meses de saída só estão ao menos 98% completos até **31/10/2024**. A alta-índice precisa ter os 30 dias seguintes dentro dessa cobertura: **data de corte 01/10/2024**. As altas sem óbito depois dela (144.549) ficam fora do denominador. O início é 01/01/2023, porque saídas de 2022 só aparecem quando processadas com atraso e seriam uma amostra viciada.
4. **Óbito.** Altas com `MORTE = 1` ou `COBRANCA` de óbito (41, 42, 43, 65, 66, 67) ficam fora do denominador (48.050 no período). Os códigos 63 e 64 (alta da mãe com óbito do recém-nascido/fetal) continuam: a paciente saiu viva.
5. **Readmissão.** É a próxima internação da mesma chave com `DT_INTER` entre o dia da saída e 30 dias depois. Internações que começam antes da saída (sobrepostas) não contam como readmissão: são colisões.
6. **Transferências e permanências.** Uma nova AIH no dia da saída ou no seguinte, depois de saída por transferência (`COBRANCA` 29, 31, 32), é continuação do cuidado em outro lugar, não volta do paciente. O mesmo vale para saída por permanência (`COBRANCA` 21–28: a AIH fecha e outra abre com o paciente ainda internado). Esta história só mede: a taxa aparece com e sem essas "readmissões contíguas", e a alta-índice sai do numerador e do denominador. A junção formal de episódios fica para a S07.
7. **Placeholders na chave.** Não há `CEP 00000000`. O CEP terminado em `000` é o CEP geral da localidade (municípios de CEP único, comuns no interior de PE) e cobre 45% das chaves: é o placeholder que importa. `NASC` em 01/01 aparece um pouco acima do esperado (4.242 chaves), e há 12 chaves com nascimento antes de 1900. O efeito de cada um nas colisões está na tabela "Placeholders na chave e colisões".

### Números

<!-- linkage-viabilidade:inicio (gerado por scripts/medir_linkage.py; não editar à mão) -->
Gerado por `.venv\Scripts\python scripts\medir_linkage.py` em 23/11/2026. Só agregados.

#### Os cinco números

| # | Medida | Valor |
| --- | ---: | ---: |
| 1 | Internações (episódios IDENT=1 deduplicados) | 1.280.396 |
| 2 | Chaves distintas (hash SHA-256 de NASC+SEXO+CEP+MUNIC_RES) | 893.318 |
| 3 | Internações por chave (média; distribuição abaixo) | 1,43 |
| 4 | Colisões: chaves com internações sobrepostas no tempo | 7.214 (3,50% das 205.869 chaves com 2+ internações; 23.266 internações) |
| 5 | Taxa bruta de readmissão em 30 dias (sem altas por óbito) | 20,32% (216.742 / 1.066.521) |
| 5a | … sem as contíguas após transferência | 18,52% |
| 5b | … sem as contíguas após transferência e após permanência | 11,82% |

#### Internações por chave

| Internações na chave | Chaves | % das chaves |
| --- | ---: | ---: |
| 1 | 687.449 | 76,95% |
| 2 | 134.310 | 15,03% |
| 3 | 37.515 | 4,20% |
| 4 | 14.740 | 1,65% |
| 5–9 | 15.797 | 1,77% |
| 10+ | 3.507 | 0,39% |

#### Preparação da base

| Item | Linhas |
| --- | ---: |
| Linhas nos 24 arquivos | 1.287.663 |
| Linhas com N_AIH repetido (todas IDENT=5) | 7.013 |
| Duplicatas de N_AIH entre AIHs IDENT=1 (removidas) | 0 |
| Linhas IDENT=5 (continuação) | 7.267 |
| AIHs distintas com IDENT=5 | 3.662 |
| AIHs IDENT=5 sem a IDENT=1 correspondente nos dados (descartadas) | 254 |
| Internações com data ausente ou saída antes da entrada (descartadas) | 0 |
| Internações na base final | 1.280.396 |

#### Cobertura e censura

| Meses entre saída e competência (até) | AIHs IDENT=1 já processadas |
| --- | ---: |
| 0 | 77,00% |
| 1 | 94,00% |
| 2 | 98,15% |
| 3 | 99,79% |
| 4 | 99,91% |
| 5 | 100,00% |

Última competência: 202412. Limiar de completude: 98,00%. Fim da cobertura completa: **31/10/2024**. Altas-índice: saída de 01/01/2023 a **01/10/2024** (data de corte = fim da cobertura − 30 dias).

#### Readmissão em 30 dias: decomposição

| Grupo | Altas-índice | Óbitos excluídos | Censuradas | Readmitidas | Início em 0–1 dia | 2–7 dias | 8–30 dias | Contíguas pós-transferência | Contíguas pós-permanência | Taxa bruta | Sem transf. | Sem transf. e perm. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Todas as chaves | 1.066.521 | 48.050 | 144.549 | 216.742 | 130.799 | 28.362 | 57.581 | 23.563 | 79.320 | 20,32% | 18,52% | 11,82% |
| Só chaves com CEP específico | 591.817 | 27.932 | 80.930 | 134.438 | 80.368 | 17.712 | 36.358 | 11.084 | 53.207 | 22,72% | 21,24% | 13,30% |

#### Placeholders na chave e colisões

| Grupo de chaves | Chaves | Chaves com 2+ internações | Chaves colidentes | % colidentes entre as com 2+ |
| --- | ---: | ---: | ---: | ---: |
| Todas as chaves | 893.318 | 205.869 | 7.214 | 3,50% |
| CEP terminado em 000 (genérico da localidade) | 405.090 | 93.376 | 4.098 | 4,39% |
| CEP específico (não termina em 000) | 488.228 | 112.493 | 3.116 | 2,77% |
| CEP 00000000 | 0 | 0 | 0 | — |
| NASC em 01/01 | 4.242 | 1.019 | 31 | 3,04% |
| NASC antes de 1900 | 12 | 4 | 1 | 25,00% |
| Sem nenhum placeholder | 485.649 | 111.892 | 3.099 | 2,77% |

Internações sobrepostas: 8.079; destas, 4.653 (57,59%) no mesmo hospital da internação anterior da chave e 2.451 (30,34%) em menores de 1 ano.

#### Plano B: óbito hospitalar e permanência

| Medida | Valor |
| --- | ---: |
| Saídas no período coberto | 1.169.621 |
| Óbitos hospitalares | 50.294 (4,30%) |
| Permanência média (dias) | 5,2 |
| Permanência p25 (dias) | 1 |
| Permanência p50 (dias) | 3 |
| Permanência p75 (dias) | 6 |
| Permanência p90 (dias) | 12 |
| Permanência p95 (dias) | 19 |
| Permanência p99 (dias) | 31 |
| Permanência > 7 dias | 232.063 (19,84%) |
| Permanência > 14 dias | 90.698 (7,75%) |
| Permanência > 30 dias | 14.561 (1,24%) |
<!-- linkage-viabilidade:fim -->

### Leitura dos números

- **Colisões.** 3,50% das chaves com duas ou mais internações têm estadias sobrepostas, o que é impossível para uma só pessoa. No CEP genérico são 4,39%; no CEP específico, 2,77%. O CEP genérico aumenta as colisões em cerca de 1,6 vez. `NASC` em 01/01 não muda nada (3,04%). Há duas ressalvas. Primeiro, 58% das sobreposições ocorrem no mesmo hospital da internação anterior, e parte delas pode ser AIH administrativa da mesma pessoa; 30% são de menores de 1 ano (gêmeos, recém-nascidos da mesma localidade). Segundo, a sobreposição só detecta pessoas diferentes internadas ao mesmo tempo. Fusões de pessoas diferentes em datas distantes não aparecem e também inflam a readmissão. A colisão é um sinal, não a taxa de erro do linkage.
- **Readmissão.** A taxa bruta (20,32%) é inflada por internações "contíguas": 60% das readmissões começam no dia da saída ou no seguinte. Sem as contíguas após transferência, a taxa cai para 18,52%. Sem as contíguas após permanência também, cai para **11,82%**. Sobram 27.916 readmissões contíguas sem motivo de transferência ou permanência (por exemplo, alta seguida de AIH nova no mesmo dia), que a S07 precisa examinar. Restrita às chaves com CEP específico, a taxa sem contíguas é 13,30%: sobe em vez de cair, então o CEP genérico não está criando readmissões falsas em massa. A diferença provavelmente vem do perfil (região metropolitana, com mais oferta hospitalar).
- **Plano B.** O óbito hospitalar é de 4,30% das saídas (classe rara, mas com 50 mil eventos). A permanência tem mediana de 3 dias; 19,84% passam de 7 dias e 7,75% passam de 14 dias.

### Referência da literatura

| Estudo | Base | Taxa |
| --- | --- | ---: |
| Freitas FA. *Readmissões hospitalares pelo Sistema Único de Saúde no Rio de Janeiro: um estudo exploratório*. Dissertação (Mestrado em Saúde Coletiva), UFJF, 2017. <https://repositorio.ufjf.br/jspui/handle/ufjf/7201> | AIHs do SIH/SUS do município do Rio de Janeiro, 2015 (331.067 registros), linkage determinístico pelo CNS | 11,6% (taxa ajustada) |
| Bettiol AB, Wajner A, Pivatto Júnior F. Hospital Readmission and Mortality in a Brazilian Tertiary Public Hospital. *Qual Manag Health Care*. 2020;29(2):76-80. doi:10.1097/QMH.0000000000000253 | Altas da Medicina Interna de um hospital público terciário de Porto Alegre, set–nov/2017 (1.047 altas) | 13,7% (não eletiva, 30 dias) |

Ressalvas: da dissertação da UFJF só foi possível ler o resumo no repositório (o PDF não abriu em 23/11/2026), e o resumo não confirma que a janela é de 30 dias. O estudo de Porto Alegre vem de um único serviço e conta só readmissões não eletivas. Mesmo assim, as duas fontes indicam uma faixa de 11–14%. A taxa medida aqui sem as contíguas (11,82%) cai dentro dela. A bruta (20,32%) fica bem acima, o que confirma que as contíguas precisam sair.

### Proposta de teto de colisões

Seguir com o linkage enquanto **as chaves colidentes forem no máximo 5% das chaves com duas ou mais internações** na base completa e **no máximo 3% nas chaves sem placeholder**. Hoje são 3,50% e 2,77%, dentro dos dois tetos. Se uma mudança na base ou na regra da chave passar de um dos tetos, a decisão volta para cá. Os 5% deixam margem para a parte das sobreposições que é AIH administrativa da mesma pessoa. Os 3% garantem que, fora a fraqueza conhecida do CEP genérico, a chave quase não junta pessoas diferentes internadas ao mesmo tempo.

### Recomendação (aguardando decisão)

**Recomendo seguir com o linkage**, com readmissão em 30 dias como alvo principal e estas condições:

1. a S07 junta formalmente os episódios contíguos (transferência, permanência e as 27.916 contíguas sem motivo) antes de rotular a readmissão;
2. o modelo traz uma marca de "CEP genérico", para avaliar o desempenho desse grupo em separado;
3. as altas a partir de 02/10/2024 ficam fora do rótulo (censura);
4. o óbito hospitalar (4,30%) fica pronto como alvo de reserva, porque não depende de linkage e usa a mesma base.

Justificativa: as colisões ficam abaixo do teto; o placeholder dominante (CEP genérico) aumenta as colisões, mas não infla a taxa; e a taxa sem contíguas (11,82%) bate com a literatura brasileira (11,6% no SIH/SUS do Rio com CNS; 13,7% em Porto Alegre). O plano B seria a escolha se o usuário preferir um alvo sem erro de linkage, ao custo de abandonar a pergunta central do projeto.

**Decisão do usuário (23/11/2026):** seguir com o linkage, com readmissão em 30 dias como alvo principal e as quatro condições acima. O óbito hospitalar fica como alvo de reserva.

## D02 — Perfil FHIR do Sumário de Alta (S04)

**Estado: decidida na S04, seguindo a orientação da história. Revisar quando o Ministério da Saúde publicar um perfil nacional.**

### Pergunta

Qual perfil FHIR usar para gerar e validar o Sumário de Alta "no padrão da RNDS", e quais pacotes o validador HL7 precisa carregar com `-ig`?

### O que foi pesquisado (23/11/2026)

- **Base normativa.** O Modelo de Informação de Sumário de Alta (SA) foi instituído pela Portaria SAES/MS nº 701, de 29/09/2022. Essa portaria foi **revogada** pela Portaria GM/MS nº 8.026, de 27/08/2025, que institui o SA no âmbito da RNDS ([Conass Informa nº 151/2025](https://www.conass.org.br/?p=50759)). O art. 3º diz que as especificações técnicas serão publicadas no Portal de Serviços do DATASUS. A portaria não traz perfil FHIR nem URL.
- **Portal de Serviços do DATASUS** (<https://servicos-datasus.saude.gov.br>). A página é uma aplicação JavaScript; o conteúdo não pôde ser lido sem login nem navegação. Não foi encontrado, por busca, nenhum guia ou perfil do SA publicado ali.
- **gov.br/RNDS.** A página de [atualizações técnicas](https://www.gov.br/saude/pt-br/composicao/seidigi/rnds/atualizacoes-tecnicas) não menciona o SA. Ela aponta para o Simplifier e para o guia de integração (<https://rnds-guia.prod.saude.gov.br/>).
- **Simplifier da RNDS** (<https://simplifier.net/redenacionaldedadosemsaude>). O projeto avisa que "não é o repositório oficial da RNDS" e que parte dos artefatos está em homologação (draft). Não há perfil de Sumário de Alta. Há o `br-core-composition`, mas:
  - não existe pacote NPM do projeto (nem no registro do Simplifier, nem em packages.fhir.org; a busca pela URL canônica não retorna nada);
  - o perfil não tem `version` e não restringe nada além de trocar referências para perfis `br-core-*`;
  - os `binding.valueSet` apontam para páginas HTML (por exemplo `http://hl7.org/fhir/R4/valueset-doc-typecodes.html`), não para URLs canônicas de ValueSet, e o validador não consegue resolvê-los (não testado no validador nesta história).
- **Guia CORE da SES-GO.** Tem o perfil `sumario-alta`, modelado sobre o SA da portaria, com seções obrigatórias (contato assistencial, diagnósticos, procedimentos) e perfis próprios para cada entrada. Ele usa os ValueSets da RNDS (`BRCID10-1.0`, `BRMotivoDesfecho-1.0`, `BRCaraterAtendimento-1.0`, `BRModalidadeAssistencial-1.0`, `BRProcedencia-1.0` etc.). O perfil só existe na versão 1.2.6, publicada no ambiente de **homologação** (<https://fhir-homolog.saude.go.gov.br/r4/core/>). A versão de produção (<https://fhir.saude.go.gov.br/r4/core/>) e a mais recente no registro do Simplifier são a 1.1.0, que não tem o perfil.
- **IPS Brasil** (<https://ips-brasil.web.app/>). É o Sumário Internacional do Paciente, outro documento (resumo geral do paciente, não da internação). Não foi usado.

Conclusão: **não há perfil FHIR nacional do Sumário de Alta publicado.**

### Decisão

O Sumário de Alta é gerado e validado contra o perfil `sumario-alta` da SES-GO, em rascunho, com os artefatos da RNDS do pacote `br.go.ses.reds-go`. O `br-core-composition` da RNDS fica como referência, sem uso na validação.

| Perfil | URL canônica | Versão | Status | Pacote |
| --- | --- | --- | --- | --- |
| Sumário de Alta (Composition) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/sumario-alta` | 1.2.6 (2026-03-07) | draft | `br.go.ses.core#1.2.6` |
| Contato Assistencial (Encounter) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/contato-assistencial-sumario-alta` | 1.2.6 | draft | `br.go.ses.core#1.2.6` |
| Diagnóstico (Condition) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/diagnostico-sumario-alta` | 1.2.6 | draft | `br.go.ses.core#1.2.6` |
| Procedimento (Procedure) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/procedimento-sumario-alta` | 1.2.6 | draft | `br.go.ses.core#1.2.6` |
| Encaminhamento (ServiceRequest) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/encaminhamento-sumario-alta` | 1.2.6 | draft | `br.go.ses.core#1.2.6` |
| Cidadão identificado (Patient) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/individuo` | 1.2.6 | active | `br.go.ses.core#1.2.6` |
| Estabelecimento de Saúde (Organization) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/estabelecimento-saude` | 1.2.6 | draft | `br.go.ses.core#1.2.6` |
| Profissional (Practitioner) | `https://fhir.saude.go.gov.br/r4/core/StructureDefinition/profissional` | 1.2.6 | active | `br.go.ses.core#1.2.6` |
| Artefatos da RNDS (ValueSets, CodeSystems, `BRIndividuo-1.0`, `BREstabelecimentoSaude-1.0` etc.) | `http://www.saude.gov.br/fhir/r4/...` | 1.0.3 (2026-02-12) | active, alguns draft | `br.go.ses.reds-go#1.0.3` |
| BR Core Composition (referência, fora da validação) | `https://br-core.saude.gov.br/fhir/StructureDefinition/br-core-composition` | sem versão | active | sem pacote |

O guia tem também perfis para alergia, restrição funcional, prescrição e plano de cuidados (todos draft, 1.2.6). As seções deles são opcionais no `sumario-alta` e o SIH não traz esses dados.

### Por que essa escolha

1. É o único perfil de Sumário de Alta encontrado, publicado por um órgão público (SES-GO), que segue o modelo de informação do SA e usa a terminologia da RNDS.
2. Vem num pacote NPM com versão e dependências declaradas, que o validador HL7 carrega com `-ig`. O `br-core-composition` não tem pacote nem versão, e seus bindings para páginas HTML gerariam mensagens causadas pelo perfil, não pelo documento.
3. O `sumario-alta` deriva direto do `Composition` do FHIR R4, não do `br-core-composition`. Validar contra os dois exigiria também os perfis `br-core-*` referenciados, sem pacote publicado.

Limites, que o README e o documento gerado precisam deixar claros:

- é um guia **estadual**, em **rascunho** e em **homologação**; não é o perfil oficial da RNDS;
- o `br.go.ses.reds-go` é a SES-GO reempacotando os artefatos da RNDS "para compatibilidade técnica com FHIR R4 sem alteração semântica" (descrição do pacote); não é publicação do DATASUS.

### Pacotes e como reproduzir

```powershell
.venv\Scripts\python scripts\baixar_pacotes_fhir.py
```

| Arquivo em `fhir/pacotes/` | Origem | SHA-256 | No git? |
| --- | --- | --- | --- |
| `br.go.ses.core-1.2.6.tgz` (480 KB) | <https://fhir-homolog.saude.go.gov.br/r4/core/package.tgz> | `c6ddb2970eb854d87e3a79999f45649814dcee83e767dc00a57d4ebbf345ba68` | sim |
| `br.go.ses.reds-go-1.0.3.tgz` (4,2 MB) | <https://packages.simplifier.net/br.go.ses.reds-go/1.0.3> | `be49b292d14b18801b4b744f1db44a86cc1031c1d84eda21a802bdb686dbfd87` | não |

O script baixa só o que falta ou está com hash errado, confere o SHA-256 e o `package.json` (nome e versão) e só então grava o arquivo. Rodar de novo não baixa nada. O pacote da SES-GO vai para o git porque a URL de homologação não tem versão: quando a SES-GO publicar outra versão, o download passa a falhar com mensagem de hash diferente, mas o arquivo versionado continua valendo. Licença dos dois pacotes: CC0-1.0.

Dependências que o validador ainda busca no registro de pacotes (packages.fhir.org): `hl7.fhir.r4.core#4.0.1`, `hl7.terminology.r4#6.5.0` e `hl7.fhir.uv.extensions.r4#5.2.0`. Na S05, o validador recebe `-version 4.0.1 -ig fhir/pacotes/br.go.ses.reds-go-1.0.3.tgz -ig fhir/pacotes/br.go.ses.core-1.2.6.tgz` e o perfil `-profile https://fhir.saude.go.gov.br/r4/core/StructureDefinition/sumario-alta`.

### Validação local (S05)

O comando acima roda por `scripts/validar_fhir.py` (uso no README), com o validador HL7 `validator_cli.jar` 7.0.3 (SHA-256 `57aa43fb40cec5de41def81c927725fd85908eeb71509b7f9313e04d9b8ec79b`, igual ao digest publicado na release do GitHub) dentro da imagem `eclipse-temurin:21.0.13.1_2-jre@sha256:b57b0a974dc5ba8b24009a97aeb9ffd178e172727736279e5de73605f40c6813`. Duas mudanças em relação à linha sugerida acima:

- num Bundle, o perfil vai para a Composition com `-bundle Composition:0 <perfil>` em vez de `-profile`. Com `-profile`, o validador checou a Composition contra o `sumario-alta`, mas não reportou os problemas das próprias entradas do Bundle: um primeiro rascunho do exemplo, ainda sem narrativa, saiu com um único "All OK", e um diagnóstico com código errado só apareceu de forma indireta ("Unable to find a profile match"). Com `-bundle`, o validador reporta também os problemas das entradas (narrativa ausente, `display` proibido, código inexistente na CID-10);
- `-txCache /root/.fhir/tx-cache`, para guardar as respostas do tx.fhir.org no mesmo volume Docker do cache de pacotes.

**Terminologia.** Em 23/11/2026, uma das execuções de teste falhou porque o tx.fhir.org não respondeu ("Connect timed out"). Por isso o script valida com terminologia e, só quando o validador não consegue conectar, repete com `-tx n/a` e escreve isso na linha "Modo" da saída. Sem terminologia, códigos de CodeSystems que não estão nos pacotes (LOINC, SNOMED etc.) não são checados; os CodeSystems da RNDS usados no Sumário de Alta vêm completos (`content: complete`) no `br.go.ses.reds-go` e continuam sendo checados localmente.

**Mensagens causadas pelo perfil.** Duas mensagens aparecem em qualquer documento correto e vêm do próprio guia, não do documento. Elas ficam em `MENSAGENS_CONHECIDAS` (`src/readmissao_sus/validador_fhir.py`), com padrão de texto restrito; aparecem na saída como `[CONHECIDA]`, com a justificativa, e não contam como aviso nem como erro:

| Mensagem | Severidade | Por que é do perfil |
| --- | --- | --- |
| `Constraint failed: BrasileiroSeSomenteSeNasceNoBrasil` | warning | A invariante do `individuo` exige `patient-birthPlace.country = '10'` para nacionalidade `B`, mas o mesmo perfil liga `country` ao ValueSet `iso3166-1-3` (required), em que o Brasil é `BRA`. Nenhum documento satisfaz as duas regras. |
| `None of the codings provided are in the value set 'Condition Category Codes'` (só com código `BRCategoriaDiagnostico`) | warning | O `diagnostico-sumario-alta` liga `Condition.category` a `BRCategoriaDiagnostico` (required), que não faz parte do ValueSet extensible do FHIR R4. O aviso vem do binding base, que o perfil não pode remover. |

Nenhum erro (severidade `error`) precisou entrar na lista.

## D03 — Contíguas sem motivo de transferência ou permanência (S07)

**Estado: decidido pelo usuário em 24/11/2026: `mesmo_hospital`.** É o padrão do banco desde então (`REGRA_PADRAO` em `src/readmissao_sus/episodios.py`). As seções abaixo mostram as medidas e a proposta como estavam antes da decisão.

### Pergunta

A S07 junta em episódios as internações seguidas de nova AIH da mesma chave no dia da saída ou no seguinte quando a saída foi por transferência (`COBRANCA` 29, 31, 32) ou por permanência (21–28). Sobram as saídas sem óbito por outro motivo (alta 1x, encerramento administrativo 51, alta no parto 6x) seguidas de nova AIH em 0–1 dia: a D01 contou 27.916 delas entre as altas-índice. Essas internações são o mesmo episódio (AIH administrativa, troca de procedimento sem o código de permanência, transferência não codificada) ou são readmissões de verdade?

### Como os números são gerados

```powershell
.venv\Scripts\python scripts\construir_banco.py
```

As tabelas "Contíguas sem motivo (D03)" e "Comparação das regras" do bloco `episodios` em `docs/coorte.md` vêm de `sql/04_episodio.sql` e `sql/05_episodio_contagens.sql`. O par medido é a primeira AIH seguinte (0–1 dia) de cada saída. Restrito às saídas no período das altas-índice, o total é **27.916**, o mesmo da D01. Em toda a base são 31.186 pares (números de 23/11/2026).

### O que foi medido

| Saída anterior | Hospital da nova AIH | Pares | Mesmo dia | Mesmo CID (3 car.) | Mesmo procedimento | Nova AIH eletiva |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1x (alta) | mesmo | 10.857 | 51% | 51% | 48% | 48% |
| 1x (alta) | outro | 4.484 | 72% | 16% | 13% | 18% |
| 51 (encerramento administrativo) | mesmo | 12.328 | 78% | 55% | 59% | 15% |
| 51 (encerramento administrativo) | outro | 45 | 80% | 29% | 9% | 40% |
| 6x (alta no parto) | mesmo | 3.305 | 52% | 2% | 1% | 3% |
| 6x (alta no parto) | outro | 167 | 75% | 7% | 4% | 5% |

- **85% são no mesmo hospital** (26.490 de 31.186). No encerramento administrativo (51), 99,6% são no mesmo hospital, 78% no mesmo dia e 59% com o mesmo procedimento: é a AIH fechada por motivo administrativo e reaberta para a mesma internação.
- Na alta comum (1x) no mesmo hospital, metade repete o CID e o procedimento, e metade da nova AIH é eletiva: parece continuação programada (por exemplo, AIHs sucessivas do mesmo procedimento; o par mais comum, `0413040178` → `0413040178`, aparece 2.530 vezes).
- Na alta no parto (6x) no mesmo hospital, o CID e o procedimento quase nunca se repetem: o par mais comum é parto normal (`0310010039`) seguido de outro procedimento obstétrico no mesmo hospital. Pode ser a AIH de um segundo procedimento da mesma estadia ou uma complicação no puerpério.
- **Em outro hospital** (4.696 pares), 72% são no mesmo dia, mas o CID só se repete em 16%. Pode ser transferência sem o código, colisão de pessoas diferentes na chave (D01) ou readmissão de verdade. Os dados não permitem separar esses casos.

Efeito na taxa de readmissão em 30 dias por episódio (bloco `episodios` de `docs/coorte.md`):

| Regra | Episódios | Altas-índice | Taxa |
| --- | ---: | ---: | ---: |
| Transferência + permanência, `nenhuma` (padrão atual) | 1.162.040 | 963.767 | 11,78% |
| … + contíguas no mesmo hospital, `mesmo_hospital` (proposta) | 1.135.651 | 940.139 | 9,53% |
| … + todas as contíguas, `todas` | 1.131.007 | 935.991 | 9,13% |

### Proposta (aguardando decisão)

**Proponho `mesmo_hospital`**: juntar a alta sem óbito seguida de nova AIH da mesma chave, no mesmo CNES, no dia da saída ou no seguinte. Fora do mesmo hospital, a nova AIH continua contando como readmissão.

Justificativa: no mesmo hospital, com 0–1 dia, o padrão é administrativo (o 51 quase sempre, procedimento e CID repetidos, AIH eletiva marcada para o dia seguinte). Nesses casos, o paciente não voltou depois de ir para casa, e um modelo treinado com esse rótulo aprenderia a prever o faturamento em várias AIHs, não a volta do paciente. Em outro hospital, o sinal é fraco (CID repetido em 16%), e juntar esconderia readmissões reais e colisões.

Ressalvas:

- com a proposta, a taxa fica em 9,53%, abaixo da faixa de 11–14% da literatura citada na D01. As referências não dizem como trataram AIHs administrativas, então a comparação é só indicativa;
- uma regra intermediária seria juntar só o encerramento administrativo (51) no mesmo hospital. Ela não está implementada; se for a escolhida, é uma opção nova em `RegraEpisodio`.

### Por que o padrão era `nenhuma` antes da decisão

Até a decisão, o banco junta só o que o motivo de saída (`COBRANCA`) justifica pelo dicionário. A alta seguida de nova AIH continua como readmissão. O erro é conhecido e medido (a taxa fica cerca de 2,2 pontos acima da proposta), e nenhum evento some do rótulo sem decisão.

### Como aplicar a decisão

Só muda o parâmetro. Para testar sem mudar o padrão:

```powershell
.venv\Scripts\python scripts\construir_banco.py --contiguas-sem-motivo mesmo_hospital
```

Para adotar de vez, troque `REGRA_PADRAO` em `src/readmissao_sus/episodios.py` para `RegraEpisodio(contiguas_sem_motivo="mesmo_hospital")` (ou `"todas"`) e recrie o banco. A comparação das quatro regras é regerada a cada construção. Os testes das três opções ficam em `tests/test_episodios.py`.

**Decisão do usuário (24/11/2026):** `mesmo_hospital`, a proposta acima.

Efeito na construção de 24/11/2026 (bloco `episodios` de `docs/coorte.md`) e no modelo:

| Item | Antes (`nenhuma`) | Com a D03 (`mesmo_hospital`) |
| --- | ---: | ---: |
| Episódios | 1.162.040 | 1.135.651 |
| Altas-índice | 963.767 | 940.139 |
| Readmissão em 30 dias (`readmissao_30d`) | 11,78% | 9,53% |
| Readmissão não planejada (`readmissao_nao_planejada_30d`, D04) | 7,25% | 5,52% |
| Readmitidas com início em 0–1 dia | 27.898 | 4.226 |
| ROC-AUC do modelo no teste 2024 | 0,811 | 0,791 |
| Voltas em 0–1 dia entre os positivos do teste | 28,6% | 6,7% |

As voltas em 0–1 dia que sobram são, em sua maioria, em outro hospital. Os resultados antes da D03 ficam em `reports/metrics_s13.json`.

## D04 — Readmissões programadas fora do alvo (S13)

**Estado: decidido pelo usuário em 23/11/2026** (tirar as programadas do alvo). A regra abaixo é a padrão da S13.

### Pergunta

Na S10, o modelo teve ROC-AUC 0,839 no teste, e o sinal se concentrou nas internações eletivas (0,902). A explicação provável era o rótulo incluir voltas programadas: ciclos de quimioterapia, procedimentos em etapas, AIHs sucessivas. Essas voltas são fáceis de prever pelo procedimento e pelo hospital, mas não respondem à pergunta clínica, que é a volta não planejada.

### Regra

O alvo novo é `readmissao_nao_planejada_30d`. A busca é a mesma de `readmissao_30d` (próximo episódio da mesma chave que começa até 30 dias depois da alta), mas só conta uma volta **não programada**. Uma volta é programada quando a primeira AIH dela:

1. é eletiva (`CAR_INT = 01`); ou
2. tem o procedimento principal (`PROC_REA`) ou o diagnóstico principal (`DIAG_PRINC`) numa lista de sempre programados.

A volta programada não conta como evento e também não censura. Se depois dela, ainda dentro dos 30 dias, vier uma volta não planejada, a alta conta como readmitida. `readmissao_30d` continua no banco como coluna auxiliar.

A lista é inspirada no Planned Readmission Algorithm v4.0 do CMS, da medida Hospital-Wide Readmission (Yale New Haven Health Services Corporation/CORE, tabelas PR1–PR4). Nesse algoritmo, transplante, quimioterapia de manutenção e reabilitação são sempre programados. A adaptação ao SIGTAP usa os nomes das tabelas `DBF/TB_FORMA.DBF` e `DBF/TB_SUBGR.DBF` do `TAB_SIH.zip` do DATASUS. O código fica em `SEMPRE_PROGRAMADOS`, em `src/readmissao_sus/dicionario_sih.py`.

| Tipo | Prefixo | Descrição (SIGTAP / CID-10) |
| --- | --- | --- |
| procedimento | 030401 | Radioterapia |
| procedimento | 030402 a 030407 | Quimioterapia paliativa, para controle temporário, prévia, adjuvante, curativa e de tumores de criança e adolescente |
| procedimento | 030408 | Quimioterapia - procedimentos especiais (internação para quimioterapia contínua ou de leucemias) |
| procedimento | 030409 | Medicina nuclear - terapêutica oncológica (iodoterapia) |
| procedimento | 0505 | Transplante de órgãos, tecidos e células |
| CID | Z50 | Cuidados envolvendo procedimentos de reabilitação |
| CID | Z510, Z511, Z512 | Sessão de radioterapia, sessão de quimioterapia, outras quimioterapias |

Ficam de fora de propósito, porque no SIGTAP são volta não planejada:

- 030410: tratamento clínico e intercorrências do paciente oncológico;
- 0305: nefrologia. Na AIH, a diálise só aparece como intercorrência; a diálise de manutenção é APAC e não entra no SIH-RD;
- 0506: intercorrências pós-transplante;
- 0501 a 0504: ações do doador.

O parto programado não tem código próprio no SIGTAP e entra pelo caráter eletivo.

### Resultado (construção de 23/11/2026)

Os números vêm do bloco `episodios` de `docs/coorte.md`, com a regra padrão dos episódios (transferência + permanência):

| Item | Valor |
| --- | ---: |
| Altas-índice | 963.767 |
| Readmitidas em 30 dias (`readmissao_30d`) | 113.511 (11,78%) |
| Readmitidas com a primeira volta programada | 45.610 |
| … por caráter eletivo | 43.756 |
| … por procedimento sempre programado | 15.019 |
| … por diagnóstico sempre programado | 4 |
| … com volta não planejada depois, ainda em 30 dias (continuam no alvo) | 1.967 |
| **Reclassificadas** (saem do alvo) | **43.643** |
| **Readmitidas não planejadas** (`readmissao_nao_planejada_30d`) | **69.868 (7,25%)** |

Os motivos se sobrepõem: uma volta eletiva de quimioterapia conta nos dois.

Variante sem o caráter eletivo, em que só a lista tira a volta do alvo (`--eletiva-nao-programada`): 99.557 readmitidas (10,33%).

As voltas eletivas parecem mesmo programadas. De 85% a 98% delas voltam ao mesmo hospital da alta, conforme o subgrupo. As mais comuns são oncologia (0304, 15.944), tratamento clínico (0303, 8.699), consultas e acompanhamentos (0301, 4.336) e cirurgias em etapas (0415 cirurgias múltiplas, 3.635; 0413 cirurgia reparadora, 3.461).

### Comparação com a literatura

A taxa nova (7,25%) fica **abaixo** da faixa de 11–14% da D01. A referência mais próxima do alvo novo é Porto Alegre: 13,7% de readmissões não eletivas. As diferenças prováveis:

- **População.** Porto Alegre mede só a Medicina Interna de um hospital terciário, que é uma população de risco alto. Aqui entram todas as altas do estado, inclusive obstetrícia e cirurgia eletiva, que voltam pouco.
- **Linkage.** No CEP genérico, a chave junta pessoas diferentes e parte das readmissões reais some: no teste da S10, a taxa foi de 9,9% nesse grupo, contra 13,6% no CEP completo.
- **Caráter eletivo.** Ele é um critério mais largo que o do CMS, que olha o procedimento e o diagnóstico, não o caráter. Uma volta eletiva por complicação sai do alvo. A variante sem o caráter (10,33%) mede o tamanho desse efeito.

A comparação é só indicativa: as referências não descrevem como trataram AIHs administrativas nem a busca por pessoa.

### Como mudar a regra

```powershell
.venv\Scripts\python scripts\construir_banco.py --eletiva-nao-programada
```

A lista fica em `SEMPRE_PROGRAMADOS` e a regra em `RegraProgramada`, em `src/readmissao_sus/programadas.py`. Os testes estão em `tests/test_programadas.py`.

Com a D03 decidida (`mesmo_hospital`, 24/11/2026), os números da D04 passam a ser: 940.139 altas-índice, 89.641 readmitidas (9,53%), 37.750 reclassificadas e **51.891 readmitidas não planejadas (5,52%)**. A variante sem o caráter eletivo fica em 75.918 (8,08%). A tabela acima é da construção de 23/11/2026, antes da D03.

**Decisão do usuário (23/11/2026):** manter a volta eletiva como programada. Ficam valendo a regra padrão e a taxa de 7,25%. A variante só com a lista do SIGTAP (10,33%) fica registrada aqui como comparação.

## D05 — Ajuste de risco para comparar hospitais (S14)

**Estado: decidido pelo usuário em 24/11/2026** (fazer o ajuste de risco dos hospitais).

### Problema

A razão O/E por hospital da S11 usava o esperado do modelo principal. Esse modelo tem o hospital da alta (`cnes_alta`) como atributo, o de maior importância. O esperado de cada hospital já carregava parte do efeito dele, e a razão media sobretudo quanto o hospital mudou em relação a 2023, não como ele se compara aos outros.

### Regra

- **Modelo de ajuste:** o mesmo pipeline e o mesmo XGBoost do modelo principal, com os mesmos atributos menos `cnes_alta` (`src/readmissao_sus/ajuste_risco.py`). Treinado com as altas de 2023 e aplicado às do teste (2024 até 01/10/2024).
- **Recalibração no total do ano:** a probabilidade de cada alta do teste é multiplicada por um fator único, observado total ÷ esperado total. Assim, a razão de cada hospital fica relativa à média do estado em 2024, e não ao nível de 2023. É o padrão da padronização indireta.
- **O resto não muda:** observado, IC 95% de Poisson exato e mínimo de 100 altas.

### Resultado (24/11/2026)

| Item | Valor |
| --- | ---: |
| ROC-AUC do ajuste no teste | 0,774 (modelo principal: 0,791) |
| Fator de recalibração | 0,946 |
| Hospitais com >= 100 altas | 193 |
| Acima / compatíveis / abaixo, com o ajuste | 28 / 126 / 39 |
| Acima / compatíveis / abaixo, com o modelo principal | 13 / 153 / 27 |

Os números estão em `reports/hospitais_ajuste.json`. O modelo principal continua o mesmo, com `cnes_alta`: ele serve para prever o risco de cada alta, e o ajuste serve só para comparar hospitais.

### Limites

O ajuste só vê o que o SIH-RD registra. Gravidade clínica, exames e condição social ficam de fora, e um hospital de referência, que recebe os casos mais graves, pode aparecer "acima" por isso. O fator de recalibração usa o desfecho do próprio ano do teste: serve para comparar hospitais dentro de 2024, não para prever 2025.
