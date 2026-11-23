-- Coorte de altas: internações sem óbito, com marcas em vez de exclusões silenciosas.
--
-- Entrada: stg_aih, internacao e as variáveis inicio_indice e corte_indice (DATE), calculadas
-- por readmissao_sus.cobertura (D01, tratamento 3).
--
-- Filtros (a linha sai da coorte; contados em coorte_filtros):
--   1. só AIH normal (IDENT = 1); 2. uma linha por N_AIH; 3. datas válidas; 4. sem óbito.
-- Marcas (a linha fica; quem usa a coorte decide):
--   censurada            saída depois de corte_indice: os 30 dias seguintes não estão cobertos;
--   alta_antes_do_inicio saída antes de inicio_indice (saídas de 2022 vêm só com atraso);
--   elegivel_indice      nenhuma das duas: pode ser alta-índice com rótulo de readmissão;
--   cep_generico         CEP terminado em 000 (D01, condição 2).

create or replace table coorte as
select
    * exclude (obito),
    dt_saida < getvariable('inicio_indice') as alta_antes_do_inicio,
    dt_saida > getvariable('corte_indice') as censurada,
    dt_saida between getvariable('inicio_indice') and getvariable('corte_indice') as elegivel_indice
from internacao
where not obito;

create or replace table coorte_filtros as
with n as (
    select
        (select count(*) from stg_aih) as linhas,
        (select count(*) from stg_aih where ident = '1') as ident1_linhas,
        (select count(distinct n_aih) from stg_aih where ident = '1') as ident1_aih,
        (select count(*) from internacao) as internacoes,
        (select count(*) from coorte) as altas
)
select ordem, etapa, antes, antes - depois as removidas, depois
from (
    select 1 as ordem, 'Só AIH normal (IDENT = 1)' as etapa, linhas as antes, ident1_linhas as depois from n
    union all
    select 2, 'Uma linha por N_AIH (fica a competência mais recente)', ident1_linhas, ident1_aih from n
    union all
    select 3, 'Datas de internação e saída válidas, saída ≥ internação', ident1_aih, internacoes from n
    union all
    select 4, 'Sem óbito na saída final (MORTE = 1 ou COBRANCA de óbito)', internacoes, altas from n
)
order by ordem;

create or replace table coorte_detalhes as
select * from (
    -- Filtro 1: o que são as linhas removidas.
    select 'ident' as secao, 1 as ordem, 'Linhas IDENT = 5 (continuação de longa permanência)' as item,
           count(*) filter (where ident = '5') as linhas from stg_aih
    union all
    select 'ident', 2, 'Linhas com outro IDENT', count(*) filter (where ident is distinct from '1' and ident is distinct from '5') from stg_aih
    union all
    select 'ident', 3, 'AIHs distintas com IDENT = 5', count(distinct n_aih) filter (where ident = '5') from stg_aih
    union all
    select 'ident', 4, 'AIHs IDENT = 5 sem a AIH 1 correspondente (descartadas)',
           count(distinct n_aih) from stg_aih
           where ident = '5' and n_aih not in (select n_aih from stg_aih where ident = '1' and n_aih is not null)
    union all
    select 'ident', 5, 'Internações com AIH 5 (saída e motivo finais vindos da continuação, quando posterior)',
           count(*) filter (where longa_permanencia) from internacao
    -- Filtro 3: datas nas linhas IDENT = 1 (antes da deduplicação).
    union all
    select 'datas', 1, 'DT_INTER ausente ou inválida', count(*) filter (where dt_inter_invalida) from stg_aih where ident = '1'
    union all
    select 'datas', 2, 'DT_SAIDA ausente ou inválida', count(*) filter (where dt_saida_invalida) from stg_aih where ident = '1'
    union all
    select 'datas', 3, 'Saída antes da internação', count(*) filter (where dt_saida < dt_inter) from stg_aih where ident = '1'
    union all
    select 'datas', 4, 'Saída depois do fim da competência', count(*) filter (where dt_saida > last_day(competencia)) from stg_aih where ident = '1'
    union all
    select 'datas', 5, 'NASC inválida (não é data)', count(*) filter (where nasc_invalida) from stg_aih where ident = '1'
    union all
    select 'datas', 6, 'NASC antes de 1900 (inclui 30/12/1899, data zero de sistemas)', count(*) filter (where nasc_antes_1900) from stg_aih where ident = '1'
    union all
    select 'datas', 7, 'NASC em 01/01 (data estimada)', count(*) filter (where nasc_0101) from stg_aih where ident = '1'
    union all
    select 'datas', 8, 'NASC depois da internação', count(*) filter (where nasc_depois_da_internacao) from stg_aih where ident = '1'
    union all
    select 'datas', 9, 'MORTE ausente ou fora de 0/1', count(*) filter (where morte_invalida) from stg_aih where ident = '1'
    -- Filtro 4: como o óbito foi identificado.
    union all
    select 'obito', 1, 'Óbitos removidos', count(*) filter (where obito) from internacao
    union all
    select 'obito', 2, '… com MORTE = 1', count(*) filter (where obito and morte) from internacao
    union all
    select 'obito', 3, '… com COBRANCA de óbito', count(*) filter (where obito and cobranca in (select codigo from dic_cobranca where obito)) from internacao
    union all
    select 'obito', 4, 'COBRANCA 63/64 (alta da mãe com óbito do recém-nascido/fetal), mantidas', count(*) filter (where cobranca in ('63', '64')) from coorte
    -- Marcas na coorte.
    union all
    select 'marcas', 1, 'Elegíveis a alta-índice (elegivel_indice)', count(*) filter (where elegivel_indice) from coorte
    union all
    select 'marcas', 2, 'Censuradas: saída depois da data de corte (censurada)', count(*) filter (where censurada) from coorte
    union all
    select 'marcas', 3, 'Saída antes do início do período (alta_antes_do_inicio)', count(*) filter (where alta_antes_do_inicio) from coorte
    union all
    select 'marcas', 4, 'CEP genérico (cep_generico), toda a coorte', count(*) filter (where cep_generico) from coorte
    union all
    select 'marcas', 5, 'CEP genérico entre as elegíveis', count(*) filter (where cep_generico and elegivel_indice) from coorte
)
order by secao, ordem;
