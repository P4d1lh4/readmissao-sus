-- Contagens dos episódios (S07) para docs/coorte.md e a D03 de docs/decisoes.md. Só agregados.
--
-- Entrada: internacao, coorte, dic_cobranca e as tabelas de 04_episodio.sql.

create or replace table episodio_motivos as
with saidas as (
    select
        case
            when cobranca in (select codigo from dic_cobranca where transferencia) then 'transferencia'
            when cobranca in (select codigo from dic_cobranca where permanencia) then 'permanencia'
            else 'sem_motivo'
        end as tipo,
        count(*) as saidas
    from internacao
    where not obito
    group by 1
),
candidatas as (
    select tipo, count(distinct anterior) as com_candidata from episodio_candidato group by 1
),
juntadas as (
    select tipo, count(*) as juntadas from episodio_ligacao group by 1
)
select tipo, saidas, coalesce(com_candidata, 0) as com_candidata, coalesce(juntadas, 0) as juntadas
from saidas left join candidatas using (tipo) left join juntadas using (tipo)
order by case tipo when 'transferencia' then 1 when 'permanencia' then 2 else 3 end;

-- Contíguas sem motivo: a primeira AIH seguinte (0–1 dia) depois de uma saída que não é
-- transferência, permanência nem óbito. Mede o que a regra D03 decide, qualquer que seja ela.
create or replace table contiguas_sem_motivo as
select
    case
        when cobranca = '51' then '51 (encerramento administrativo)'
        when cobranca like '1%' then '1x (alta)'
        else '6x (alta no parto)'
    end as grupo,
    mesmo_hospital,
    count(*) as pares,
    count(*) filter (where dias = 0) as mesmo_dia,
    count(*) filter (where mesmo_cid) as mesmo_cid,
    count(*) filter (where mesmo_procedimento) as mesmo_procedimento,
    count(*) filter (where mesmo_grupo_procedimento) as mesmo_grupo_procedimento,
    count(*) filter (where seguinte_eletiva) as seguinte_eletiva
from episodio_candidato
where tipo = 'sem_motivo' and primeira
group by all
order by grupo, mesmo_hospital desc;

create or replace table contiguas_procedimentos as
select a.proc_rea as procedimento_anterior, b.proc_rea as procedimento_seguinte,
       c.mesmo_hospital, count(*) as pares
from episodio_candidato c
join internacao a on a.n_aih = c.anterior
join internacao b on b.n_aih = c.seguinte
where c.tipo = 'sem_motivo' and c.primeira
group by all
order by pares desc, procedimento_anterior, procedimento_seguinte
limit 10;

create or replace table episodio_resumo as
with tamanho as (
    select n_internacoes, count(*) as n from episodio group by 1
),
s06 as (
    select c.n_aih, c.elegivel_indice, m.episodio_id
    from coorte c join episodio_membro m using (n_aih)
)
select * from (
    select 'juncao' as secao, 1 as ordem, 'Internações (tabela internacao)' as item,
           (select count(*) from internacao) as valor
    union all
    select 'juncao', 2, 'Episódios (tabela episodio)', (select count(*) from episodio)
    union all
    select 'juncao', 3, 'Episódios com 2 ou mais internações',
           (select count(*) from episodio where n_internacoes > 1)
    union all
    select 'juncao', 4, 'Internações juntadas a uma anterior (internações − episódios)',
           (select count(*) from episodio_ligacao)
    union all
    select 'juncao', 5, '… depois de transferência', (select count(*) from episodio_ligacao where tipo = 'transferencia')
    union all
    select 'juncao', 6, '… depois de permanência', (select count(*) from episodio_ligacao where tipo = 'permanencia')
    union all
    select 'juncao', 7, '… contíguas sem motivo (regra D03)', (select count(*) from episodio_ligacao where tipo = 'sem_motivo')
    union all
    select 'juncao', 8, 'Episódios com mais de um hospital', (select count(*) from episodio where n_hospitais > 1)
    union all
    select 'juncao', 9, 'Maior episódio (internações)', (select max(n_internacoes) from episodio)
    union all
    select 'juncao', 10, 'Candidatas aceitas pela regra que ficaram sem par (disputa entre AIHs)',
           (select count(distinct anterior) from episodio_candidato where pela_regra)
             - (select count(*) from episodio_ligacao)
    -- Tamanho dos episódios.
    union all
    select 'tamanho', 1, '1 internação', coalesce((select sum(n) from tamanho where n_internacoes = 1), 0)
    union all
    select 'tamanho', 2, '2 internações', coalesce((select sum(n) from tamanho where n_internacoes = 2), 0)
    union all
    select 'tamanho', 3, '3 internações', coalesce((select sum(n) from tamanho where n_internacoes = 3), 0)
    union all
    select 'tamanho', 4, '4 ou mais internações', coalesce((select sum(n) from tamanho where n_internacoes >= 4), 0)
    -- Desfecho, censura e marcas.
    union all
    select 'desfecho', 1, 'Episódios com óbito na última internação (fora da coorte)',
           (select count(*) from episodio where obito)
    union all
    select 'desfecho', 2, '… com 2 ou mais internações', (select count(*) from episodio where obito and n_internacoes > 1)
    union all
    select 'desfecho', 3, 'Altas sem óbito da S06 dentro de episódio terminado em óbito',
           (select count(*) from s06 join episodio e using (episodio_id) where e.obito)
    union all
    select 'desfecho', 4, 'Episódios na coorte (tabela coorte_episodio)', (select count(*) from coorte_episodio)
    union all
    select 'desfecho', 5, 'Elegíveis a alta-índice (elegivel_indice)',
           (select count(*) from coorte_episodio where elegivel_indice)
    union all
    select 'desfecho', 6, 'Censurados: saída final depois da data de corte (censurada)',
           (select count(*) from coorte_episodio where censurada)
    union all
    select 'desfecho', 7, '… com internação elegível na S06 (a cadeia passou do corte)',
           (select count(distinct s06.episodio_id) from s06 join coorte_episodio e using (episodio_id)
            where e.censurada and s06.elegivel_indice)
    union all
    select 'desfecho', 8, 'Saída final antes do início do período (alta_antes_do_inicio)',
           (select count(*) from coorte_episodio where alta_antes_do_inicio)
    union all
    select 'desfecho', 9, 'Elegíveis que terminam em transferência ou permanência sem continuação (fim_sem_continuacao)',
           (select count(*) from coorte_episodio where elegivel_indice and fim_sem_continuacao)
    union all
    select 'desfecho', 10, 'CEP genérico entre as elegíveis', (select count(*) from coorte_episodio where elegivel_indice and cep_generico)
    -- Readmissão em 30 dias por episódio (só elegíveis).
    union all
    select 'readmissao', 1, 'Altas-índice (episódios elegíveis)', (select count(*) from coorte_episodio where elegivel_indice)
    union all
    select 'readmissao', 2, 'Readmitidas em 30 dias', (select count(*) from coorte_episodio where readmissao_30d)
    union all
    select 'readmissao', 3, '… início em 0–1 dia', (select count(*) from coorte_episodio where readmissao_30d and dias_ate_readmissao <= 1)
    union all
    select 'readmissao', 4, '… em 2–7 dias', (select count(*) from coorte_episodio where readmissao_30d and dias_ate_readmissao between 2 and 7)
    union all
    select 'readmissao', 5, '… em 8–30 dias', (select count(*) from coorte_episodio where readmissao_30d and dias_ate_readmissao >= 8)
    union all
    select 'readmissao', 6, 'Readmitidas em 30 dias sem as voltas programadas (D04)', (select count(*) from coorte_episodio where readmissao_nao_planejada_30d)
    union all
    select 'readmissao', 7, 'Readmitidas com a primeira volta programada', (select count(*) from coorte_episodio where readmissao_30d and primeira_volta_programada)
    union all
    select 'readmissao', 8, '… programada por caráter eletivo', (select count(*) from coorte_episodio where readmissao_30d and primeira_volta_eletiva)
    union all
    select 'readmissao', 9, '… por procedimento sempre programado', (select count(*) from coorte_episodio where readmissao_30d and primeira_volta_procedimento_programado)
    union all
    select 'readmissao', 10, '… por diagnóstico sempre programado', (select count(*) from coorte_episodio where readmissao_30d and primeira_volta_cid_programado)
    union all
    select 'readmissao', 11, '… e com volta não planejada depois, ainda em 30 dias (continuam no alvo)', (select count(*) from coorte_episodio where readmissao_30d and primeira_volta_programada and readmissao_nao_planejada_30d)
    union all
    select 'readmissao', 12, 'Reclassificadas: readmitidas que saem do alvo (só voltas programadas)', (select count(*) from coorte_episodio where readmissao_30d and not readmissao_nao_planejada_30d)
    union all
    select 'juncao', 11, 'Contíguas sem motivo com saída anterior no período das altas-índice (D01: 27.916)',
           (select count(*) from episodio_candidato
            where tipo = 'sem_motivo' and primeira
              and saida_anterior between getvariable('inicio_indice') and getvariable('corte_indice'))
)
order by secao, ordem;
