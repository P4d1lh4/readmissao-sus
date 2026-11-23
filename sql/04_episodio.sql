-- Episódios (S07): internações contíguas da mesma chave juntadas num episódio único.
--
-- Entrada: internacao (02_internacao.sql), dic_cobranca e as variáveis
--   juntar_permanencia    BOOLEAN  junta também a saída por permanência (COBRANCA 21–28);
--   contiguas_sem_motivo  VARCHAR  'nenhuma' | 'mesmo_hospital' | 'todas' (D03 em docs/decisoes.md);
--   dias_contiguidade     INTEGER  1: a nova AIH começa no dia da saída ou no seguinte;
--   janela_dias           INTEGER  30: janela da readmissão;
--   inicio_indice, corte_indice DATE: as mesmas da coorte (03_coorte.sql);
--   eletiva_programada    BOOLEAN  volta eletiva é programada (D04);
--   car_int_eletivo       VARCHAR  '01';
-- e dic_sempre_programado (programadas.py): prefixos de procedimento e de CID sempre programados.
--
-- Candidata A → B: mesma chave, A sem óbito, B começa entre a saída de A e dias_contiguidade
-- dias depois e vem depois de A na ordem (dt_inter, dt_saida, n_aih), a mesma da D01. B que
-- começa antes da saída de A (sobreposta) nunca liga: é colisão (D01, tratamento 5).
-- O tipo vem da COBRANCA de A: transferência (29, 31, 32) liga sempre; permanência liga se
-- juntar_permanencia; o resto ("sem motivo") liga conforme contiguas_sem_motivo.
-- Ligação: entre as candidatas aceitas, cada A fica com a primeira B e cada B com a A de saída
-- mais tardia. Assim cada internação tem no máximo uma anterior e uma seguinte, e as ligações
-- formam cadeias A → B → C; cada cadeia é um episódio.

create or replace table episodio_candidato as
with i as (
    select n_aih, chave, cnes, diag_princ, proc_rea, car_int, dt_inter, dt_saida, cobranca, obito
    from internacao
),
par as (
    select
        a.n_aih as anterior, b.n_aih as seguinte,
        case
            when a.cobranca in (select codigo from dic_cobranca where transferencia) then 'transferencia'
            when a.cobranca in (select codigo from dic_cobranca where permanencia) then 'permanencia'
            else 'sem_motivo'
        end as tipo,
        a.cobranca,
        a.dt_inter as inter_anterior, a.dt_saida as saida_anterior,
        b.dt_inter as inter_seguinte, b.dt_saida as saida_seguinte,
        b.dt_inter - a.dt_saida as dias,
        coalesce(a.cnes = b.cnes, false) as mesmo_hospital,
        coalesce(left(a.diag_princ, 3) = left(b.diag_princ, 3), false) as mesmo_cid,
        coalesce(a.proc_rea = b.proc_rea, false) as mesmo_procedimento,
        coalesce(left(a.proc_rea, 2) = left(b.proc_rea, 2), false) as mesmo_grupo_procedimento,
        coalesce(b.car_int = '01', false) as seguinte_eletiva,
        row_number() over (
            partition by a.n_aih order by b.dt_inter, b.dt_saida, b.n_aih) = 1 as primeira
    from i a join i b
      on b.chave = a.chave and b.n_aih <> a.n_aih
     and b.dt_inter >= a.dt_saida
     and b.dt_inter <= a.dt_saida + getvariable('dias_contiguidade')
     and (b.dt_inter, b.dt_saida, b.n_aih) > (a.dt_inter, a.dt_saida, a.n_aih)
    where not a.obito
)
select
    *,
    case tipo
        when 'transferencia' then true
        when 'permanencia' then getvariable('juntar_permanencia')
        else getvariable('contiguas_sem_motivo') = 'todas'
             or (getvariable('contiguas_sem_motivo') = 'mesmo_hospital' and mesmo_hospital)
    end as pela_regra
from par;

create or replace table episodio_ligacao as
with por_anterior as (
    select * from episodio_candidato
    where pela_regra
    qualify row_number() over (
        partition by anterior order by inter_seguinte, saida_seguinte, seguinte) = 1
)
select anterior, seguinte, tipo, mesmo_hospital, dias
from por_anterior
qualify row_number() over (
    partition by seguinte order by saida_anterior desc, inter_anterior desc, anterior desc) = 1;

-- Cada internação recebe o episódio (n_aih da primeira) e a posição na cadeia.
create or replace table episodio_membro as
with recursive cadeia(n_aih, episodio_id, posicao, ligacao) as (
    select i.n_aih, i.n_aih, 1, null::varchar
    from internacao i
    where not exists (select 1 from episodio_ligacao l where l.seguinte = i.n_aih)
    union all
    select l.seguinte, c.episodio_id, c.posicao + 1, l.tipo
    from cadeia c join episodio_ligacao l on l.anterior = c.n_aih
)
select * from cadeia;

-- Episódio: entrada da primeira internação, saída e desfecho (COBRANCA, MORTE, óbito) da última.
create or replace table episodio as
select
    m.episodio_id,
    count(*)::integer as n_internacoes,
    list(i.n_aih order by m.posicao) as aihs,
    list(i.cnes order by m.posicao) as hospitais,
    count(distinct i.cnes)::integer as n_hospitais,
    (count(*) filter (where m.ligacao = 'transferencia'))::integer as ligacoes_transferencia,
    (count(*) filter (where m.ligacao = 'permanencia'))::integer as ligacoes_permanencia,
    (count(*) filter (where m.ligacao = 'sem_motivo'))::integer as ligacoes_sem_motivo,
    arg_min(i.chave, m.posicao) as chave,
    arg_min(i.sexo, m.posicao) as sexo,
    arg_min(i.munic_res, m.posicao) as munic_res,
    arg_min(i.idade, m.posicao) as idade,
    arg_min(i.cod_idade, m.posicao) as cod_idade,
    arg_min(i.cnes, m.posicao) as cnes,
    arg_max(i.cnes, m.posicao) as cnes_saida,
    arg_min(i.diag_princ, m.posicao) as diag_princ,
    arg_max(i.diag_princ, m.posicao) as diag_princ_saida,
    arg_min(i.proc_rea, m.posicao) as proc_rea,
    arg_max(i.proc_rea, m.posicao) as proc_rea_saida,
    arg_min(i.car_int, m.posicao) as car_int,
    sum(i.uti_mes_to)::integer as uti_mes_to,
    arg_min(i.dt_inter, m.posicao) as dt_inter,
    arg_max(i.dt_saida, m.posicao) as dt_saida,
    arg_max(i.cobranca, m.posicao) as cobranca,
    arg_max(i.morte, m.posicao) as morte,
    arg_max(i.obito, m.posicao) as obito,
    bool_or(i.longa_permanencia) as longa_permanencia,
    arg_min(i.cep_generico, m.posicao) as cep_generico,
    arg_min(i.cep_zerado, m.posicao) as cep_zerado,
    arg_min(i.nasc_0101, m.posicao) as nasc_0101,
    arg_min(i.nasc_antes_1900, m.posicao) as nasc_antes_1900,
    arg_min(i.menor_1_ano, m.posicao) as menor_1_ano,
    arg_min(i.nasc_invalida, m.posicao) as nasc_invalida
from episodio_membro m join internacao i using (n_aih)
group by m.episodio_id;

-- Volta programada (D04): a primeira AIH do episódio é eletiva (se eletiva_programada) ou tem
-- procedimento ou diagnóstico principal com prefixo de dic_sempre_programado.
create or replace table episodio_programado as
select
    e.episodio_id,
    coalesce(getvariable('eletiva_programada') and e.car_int = getvariable('car_int_eletivo'), false)
        as eletiva,
    exists (select 1 from dic_sempre_programado d
            where d.tipo = 'procedimento' and starts_with(e.proc_rea, d.prefixo)) as procedimento,
    exists (select 1 from dic_sempre_programado d
            where d.tipo = 'cid' and starts_with(e.diag_princ, d.prefixo)) as cid
from episodio e;

-- Coorte de episódios: como a coorte da S06, mas a unidade é o episódio. Óbito na última
-- internação tira o episódio inteiro; as marcas usam a saída final. Readmissão: o próximo
-- episódio da mesma chave que começa entre a saída e janela_dias depois (pode terminar em
-- óbito). readmissao_30d só tem valor nas elegíveis; nas outras é nulo.
-- readmissao_nao_planejada_30d (D04): a mesma busca, mas só com voltas não programadas. A
-- programada não conta nem censura: uma volta não planejada depois dela, na janela, conta.
create or replace table coorte_episodio as
with base as (
    select
        * exclude (obito),
        dt_saida < getvariable('inicio_indice') as alta_antes_do_inicio,
        dt_saida > getvariable('corte_indice') as censurada,
        dt_saida between getvariable('inicio_indice') and getvariable('corte_indice') as elegivel_indice,
        coalesce(cobranca in (select codigo from dic_cobranca where transferencia or permanencia), false)
            as fim_sem_continuacao
    from episodio
    where not obito
),
volta as (
    select
        b.episodio_id,
        r.dt_inter - b.dt_saida as dias,
        p.eletiva or p.procedimento or p.cid as programada,
        p.eletiva, p.procedimento, p.cid,
        row_number() over (
            partition by b.episodio_id order by r.dt_inter, r.dt_saida, r.episodio_id) as ordem
    from base b join episodio r
      on r.chave = b.chave and r.episodio_id <> b.episodio_id
     and r.dt_inter >= b.dt_saida
     and r.dt_inter <= b.dt_saida + getvariable('janela_dias')
     and (r.dt_inter, r.dt_saida, r.episodio_id) > (b.dt_inter, b.dt_saida, b.episodio_id)
    join episodio_programado p on p.episodio_id = r.episodio_id
),
proxima as (
    select
        episodio_id,
        min(dias) as dias_ate_readmissao,
        bool_or(programada) filter (where ordem = 1) as primeira_volta_programada,
        bool_or(eletiva) filter (where ordem = 1) as primeira_volta_eletiva,
        bool_or(procedimento) filter (where ordem = 1) as primeira_volta_procedimento_programado,
        bool_or(cid) filter (where ordem = 1) as primeira_volta_cid_programado,
        min(dias) filter (where not programada) as dias_ate_readmissao_nao_planejada
    from volta
    group by episodio_id
)
select
    base.*,
    p.dias_ate_readmissao,
    case when base.elegivel_indice then p.episodio_id is not null end as readmissao_30d,
    p.primeira_volta_programada,
    p.primeira_volta_eletiva,
    p.primeira_volta_procedimento_programado,
    p.primeira_volta_cid_programado,
    p.dias_ate_readmissao_nao_planejada,
    case when base.elegivel_indice then p.dias_ate_readmissao_nao_planejada is not null end
        as readmissao_nao_planejada_30d
from base left join proxima p using (episodio_id);
