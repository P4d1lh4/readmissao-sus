# Modelo com validação temporal (S10, alvo da S13)

**Alvo (S13):** `readmissao_nao_planejada_30d`, a readmissão em 30 dias sem as voltas programadas (eletivas ou com procedimento ou CID sempre programado; regra na D04 em `docs/decisoes.md`). O protocolo abaixo é o da S10, que usava `readmissao_30d`. Os resultados da S10 ficam em `reports/metrics_s10.json` e `reports/importancia_atributos_s10.csv`.

Modelo de readmissão em 30 dias treinado sobre `atributo_episodio` (S09, `docs/atributos.md`). Adapta `src/modeling.py`, `src/artifacts.py` e `src/explain.py` do Health-Project. O código fica em `src/readmissao_sus/modelagem.py` (atributos, pipeline, divisão, folds, limiar), `avaliacao.py` (métricas agregadas), `investigacao.py` (checagens de vazamento), `treino.py` (fluxo e gravação), `artefatos.py` (leitura do modelo salvo) e `explicacao.py` (contribuições SHAP do XGBoost). Os números estão no README, na seção "Resultados do modelo (S13)", com os da S10 ao lado,, e em `reports/metrics.json`.

```powershell
.venv\Scripts\python scripts\treinar.py
```

## Divisão e validação

- **Treino:** altas de 2023. **Teste:** altas de 2024 até 01/10/2024, o corte de censura da D01 (condição 3). A tabela de atributos já só tem altas com rótulo; `dividir_por_tempo` repete o corte para não depender disso.
- A mesma chave pode estar no treino e no teste, como aconteceria em uso: o modelo aprende com o passado e pontua as altas seguintes de qualquer pessoa. O que não pode acontecer é a mesma chave em dois folds da validação cruzada, porque aí o modelo veria a pessoa ao ser avaliado nela.
- **Validação cruzada:** 5 folds agrupados pela chave, dentro do treino. As chaves são embaralhadas (semente fixa) e distribuídas em rodízio entre os folds. Não é o `StratifiedGroupKFold` do Health-Project: com ~400 mil chaves, ele e o `GroupKFold` levaram minutos só para montar os folds. Com tantas chaves, a prevalência já fica parecida entre os folds.
- **Amostra:** a validação cruzada usa 50% das chaves do treino (chaves inteiras, `--fracao-cv`), para o treino completo caber em menos de 30 minutos de CPU. O vencedor é reajustado no treino inteiro.
- **Seleção:** maior ROC-AUC média. **Limiar:** máximo F1 nas probabilidades out-of-fold do vencedor (vai para `models/metadata.json` e para `reports/metrics.json`).
- **Candidatos**, sem pesos de classe: Logistic Regression; Random Forest (100 árvores, profundidade 14, folha mínima 50); XGBoost (`tree_method="hist"`, 400 árvores, profundidade 6). `random_state = 42` em tudo.
- **Calibração:** medida, não corrigida. O teste é dividido em dez faixas de igual tamanho da probabilidade prevista e cada faixa compara o previsto médio com a taxa observada (`calibracao_teste`). Os candidatos não usam pesos de classe, então a probabilidade sai na escala da prevalência; um calibrador (isotônico, Platt) só entraria se a diferença fosse grande.
- **Importância:** por permutação, queda de ROC-AUC ao embaralhar cada atributo, em 50 mil episódios sorteados do teste, 3 repetições (`reports/importancia_atributos.csv`).

## Atributos

| Entra | Colunas | Tratamento |
| --- | --- | --- |
| Numéricos | `idade`, `dias_permanencia`, `dias_uti`, `n_aihs`, `n_hospitais`, `episodios_365d`, `dias_internado_365d`, `dias_desde_ultima_alta` | mediana no lugar do nulo, com coluna indicadora de nulo; padronização |
| Sim/não | `usou_uti`, `houve_transferencia`, `houve_permanencia`, `houve_contigua_sem_motivo`, `cep_generico`, `historico_com_obito` | 0/1 |
| Categóricos | `sexo`, `capitulo_cid`, `grupo_sigtap`, `car_int`, `cnes_alta` | one-hot; categorias com menos de 0,1% do treino viram um grupo "infrequente", que também recebe as categorias novas do teste |

| Fica fora | Motivo |
| --- | --- |
| `episodio_id`, `chave` | identificadores; a chave agrupa a validação cruzada |
| `dt_inter`, `dt_saida` | datas; separam treino e teste |
| `readmissao_nao_planejada_30d` | alvo (D04) |
| `readmissao_30d` | alvo da S10; inclui as voltas programadas. Fica como coluna auxiliar |
| `ano_alta` | constante dentro do treino (2023) e dentro do teste (2024): não ensina nada e, no teste, seria um valor nunca visto |
| `historico_completo` | constante (falso) em todo o treino: nenhuma alta de 2023 tem a janela de 365 dias inteira nos dados. Como atributo, o modelo não aprenderia nada com ela. Fica como marca de qualidade, e o teste é avaliado em separado por ela |
| `chave_colidente` | usa episódios da chave em qualquer data, inclusive depois da alta: é informação do futuro. Fica só para avaliar em separado |
| `episodio_sobreposto` | o episódio com que se sobrepõe pode terminar depois da alta deste. Fora por cautela |
| `dias_ate_readmissao_nao_planejada` (de `coorte_episodio`) | é o próprio rótulo em dias; lido como `dias_ate_readmissao` só para a checagem das readmissões em 0–1 dia |

Decisões da história:

- **`cnes_alta` entra.** O hospital da alta é conhecido na alta, e a taxa de readmissão varia muito entre hospitais (de 6% a 41% entre os dez maiores; `docs/atributos.md`). São 258 hospitais no treino. Com o limite de 0,1% do treino (cerca de 530 episódios), 107 ficam com coluna própria e cobrem 95% dos episódios de 2023; os demais, e os 318 episódios de 2024 em hospitais sem alta em 2023, caem no grupo "infrequente". A ablação sem o hospital mede quanto do resultado depende dele.
- **`cep_generico` entra**, como a condição 2 da D01 pede, e o teste é avaliado em separado por ela.
- **`historico_com_obito` entra.** Só olha episódios anteriores à entrada; é um sinal de colisão de chave que já se conhece na alta.
- **`houve_contigua_sem_motivo`** é constante (falso) com a regra padrão da D03 (`nenhuma`). Fica na lista para o modelo continuar o mesmo se a D03 mudar.

## Mudança de distribuição entre 2023 e 2024

Os dados começam em 01/01/2023. No treino (altas de 2023), nenhuma entrada tem a janela de 365 dias inteira nos dados; no teste (altas de 2024), 98,7% têm. Os atributos de histórico do treino saem subestimados (`historico_treino` e `historico_teste` em `metrics.json`). Não dá para treinar só com `historico_completo = true` em 2023, porque esse grupo não existe. Três medidas no lugar:

1. **Teste por `historico_completo`.** Os 5.735 episódios de 2024 com entrada em 2023 (janela incompleta) contra os demais.
2. **Variante com mais histórico.** O vencedor reajustado só com as entradas a partir de 01/07/2023 (ao menos 181 dias de dados antes da entrada), avaliado no mesmo teste com o mesmo limiar (`variante_historico`). Se o histórico incompleto prejudicasse o modelo, a variante iria melhor no teste.
3. **Calibração no teste**, que mostra se o modelo, treinado com histórico curto, erra o nível do risco em 2024.

## Suspeita de vazamento

ROC-AUC acima de 0,80 é tratado como suspeita de vazamento e investigado (`investigacao_vazamento` em `metrics.json`):

- **AUC de cada atributo sozinho** no teste: um atributo que sozinho separa quase tudo é o primeiro suspeito;
- **ablações:** o vencedor reajustado sem o histórico da chave e sem o hospital;
- **readmissões em 0–1 dia:** o teste sem os positivos cuja readmissão começou no dia da alta ou no seguinte. São as AIHs contíguas que a D03 (pendente) pode juntar ao episódio, em boa parte administrativas e fáceis de prever pelo hospital e pelo histórico de AIHs sucessivas.

Na S13, o teste por caráter da internação-índice (`car_int` em `teste_por_grupo`) mostra se a diferença entre eletivo e urgência da S10 vinha das voltas programadas. O resultado da investigação está no README.

## Saídas

| Arquivo | Conteúdo | No git? |
| --- | --- | --- |
| `models/modelo.joblib` | pipeline completo (pré-processamento + classificador); recebe as colunas de `ATRIBUTOS` | não |
| `models/metadata.json` | modelo, atributos, limiar, versões, semente, contagens e data do treino | não |
| `reports/metrics.json` | CV por candidato, teste, teste por grupo, calibração, histórico, variante e investigação: só agregados | sim |
| `reports/importancia_atributos.csv` | uma linha por atributo | sim |

Nada por episódio é gravado: não há arquivo de previsões do teste. O `.gitignore` ignora `reports/*` e libera só os dois arquivos agregados.
