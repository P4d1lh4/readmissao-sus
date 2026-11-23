-- Internações (episódios): uma linha por AIH normal (IDENT = 1), com saída e motivo finais.
--
-- Entrada: stg_aih (01_staging.sql) e dic_cobranca (carregada de dicionario_sih.py).
-- Regras (D01 em docs/decisoes.md, tratamentos 1, 2 e 4):
-- - só IDENT = 1 forma internação; IDENT = 5 (longa permanência) é continuação da AIH 1 de
--   mesmo N_AIH e nunca é internação própria;
-- - N_AIH repetido entre AIHs 1: fica a da competência mais recente;
-- - com AIH 5 cuja saída passa da saída da AIH 1, a saída do episódio é a maior DT_SAIDA das
--   AIHs 5, e COBRANCA e MORTE vêm dessa última AIH 5; AIH 5 sem AIH 1 é descartada;
-- - ficam só episódios com as duas datas válidas e saída no dia da entrada ou depois;
-- - óbito = MORTE = 1 ou COBRANCA de óbito (41, 42, 43, 65, 66, 67) na saída final.

create or replace table internacao as
with ident1 as (
    select * from stg_aih
    where ident = '1'
    qualify row_number() over (
        partition by n_aih order by competencia desc, dt_saida desc) = 1
),
continuacao as (
    select n_aih,
           max(dt_saida) as dt_saida5,
           arg_max(cobranca, (dt_saida, competencia)) as cobranca5,
           arg_max(morte, (dt_saida, competencia)) as morte5
    from stg_aih
    where ident = '5'
    group by n_aih
),
episodio as (
    select i.*,
           c.n_aih is not null as longa_permanencia,
           coalesce(c.dt_saida5 > i.dt_saida, false) as estendida,
           c.dt_saida5, c.cobranca5, c.morte5
    from ident1 i left join continuacao c using (n_aih)
),
final as (
    select * exclude (dt_saida, cobranca, morte, dt_saida5, cobranca5, morte5, estendida),
           case when estendida then dt_saida5 else dt_saida end as dt_saida,
           case when estendida then cobranca5 else cobranca end as cobranca,
           case when estendida then morte5 else morte end as morte
    from episodio
)
select
    n_aih, chave, competencia, sexo, munic_res, idade, cod_idade, cnes, diag_princ, proc_rea,
    car_int, uti_mes_to, dt_inter, dt_saida, cobranca, longa_permanencia,
    coalesce(morte, false) as morte,
    coalesce(morte, false)
        or coalesce(cobranca in (select codigo from dic_cobranca where obito), false) as obito,
    cep_generico, cep_zerado, nasc_0101, nasc_antes_1900, menor_1_ano, nasc_invalida
from final
where dt_inter is not null and dt_saida is not null and dt_saida >= dt_inter;
