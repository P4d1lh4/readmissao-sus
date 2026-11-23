-- Staging do SIH-RD: uma linha por linha dos Parquet, com tipos corretos e datas convertidas.
--
-- Entrada: a relação rd_bruto (colunas do DBF, todas texto) e a variável sal_chave.
-- NASC e CEP não ficam em claro: viram a chave de linkage (hash SHA-256 com sal) e marcas de
-- qualidade. Ver docs/coorte.md.
--
-- Datas: só "aaaammdd" com 8 dígitos e data existente no calendário vira DATE; o resto vira
-- nulo e ganha a marca *_invalida (try_strptime sozinho aceitaria "2023011").

create or replace table stg_aih as
with b as (
    select
        *,
        case when regexp_full_match(NASC, '[0-9]{8}') then try_strptime(NASC, '%Y%m%d')::date end
            as nasc_d,
        case when regexp_full_match(DT_INTER, '[0-9]{8}') then try_strptime(DT_INTER, '%Y%m%d')::date end
            as dt_inter_d,
        case when regexp_full_match(DT_SAIDA, '[0-9]{8}') then try_strptime(DT_SAIDA, '%Y%m%d')::date end
            as dt_saida_d
    from rd_bruto
)
select
    N_AIH as n_aih,
    IDENT as ident,
    make_date(try_cast(ANO_CMPT as integer), try_cast(MES_CMPT as integer), 1) as competencia,
    sha256(getvariable('sal_chave') || NASC || '|' || SEXO || '|' || CEP || '|' || MUNIC_RES) as chave,
    SEXO as sexo,
    MUNIC_RES as munic_res,
    try_cast(IDADE as smallint) as idade,
    COD_IDADE as cod_idade,
    dt_inter_d as dt_inter,
    dt_saida_d as dt_saida,
    DIAG_PRINC as diag_princ,
    PROC_REA as proc_rea,
    CNES as cnes,
    CAR_INT as car_int,
    COBRANCA as cobranca,
    case MORTE when '1' then true when '0' then false end as morte,
    try_cast(UTI_MES_TO as smallint) as uti_mes_to,
    -- Marcas da chave (D01, tratamento 7).
    CEP like '%000' as cep_generico,
    CEP = '00000000' as cep_zerado,
    substr(NASC, 5, 4) = '0101' as nasc_0101,
    NASC < '19000101' as nasc_antes_1900,
    nasc_d > dt_inter_d - interval 1 year as menor_1_ano,
    -- Marcas de qualidade das datas (contadas em docs/coorte.md).
    NASC is not null and nasc_d is null as nasc_invalida,
    DT_INTER is null or dt_inter_d is null as dt_inter_invalida,
    DT_SAIDA is null or dt_saida_d is null as dt_saida_invalida,
    nasc_d > dt_inter_d as nasc_depois_da_internacao,
    MORTE is null or MORTE not in ('0', '1') as morte_invalida
from b;
