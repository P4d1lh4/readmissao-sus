-- Atributos por episódio elegível (S09): uma linha por episódio de coorte_episodio com
-- readmissao_30d não nulo. Só leva informação conhecida até a alta do episódio.
--
-- Entrada: episodio e coorte_episodio (04_episodio.sql), dic_sexo, dic_cid10_capitulo e
-- dic_sigtap_grupo (carregadas de dicionario_sih.py) e as variáveis
--   inicio_dados    DATE     primeiro dia coberto pelos dados (a mesma inicio_indice da coorte);
--   dias_historico  INTEGER  365: janela do histórico, contada para trás a partir da entrada.
--
-- Histórico da chave: um episódio H (da tabela episodio inteira: elegível, censurado, com
-- saída antes do início ou terminado em óbito) é anterior ao episódio atual E quando
--   H.dt_saida <= E.dt_inter  e  (H.dt_inter, H.dt_saida, H.episodio_id) < (E.dt_inter, E.dt_saida, E.episodio_id).
-- É o espelho da readmissão (04_episodio.sql): H tem E como candidato a readmissão exatamente
-- quando H é anterior a E. As datas não têm hora; saída no mesmo dia da entrada conta como
-- anterior, como na D01. O próprio E e os episódios sobrepostos a ele (colisões da D01) nunca
-- entram. Janela: H entra nas contagens de 365 dias se a saída cai em
-- [E.dt_inter − dias_historico, E.dt_inter]; os dias internados são os da estadia de H dentro
-- dessa janela (saída − max(entrada, início da janela), como a permanência).
-- historico_completo: a janela inteira está dentro dos dados (E.dt_inter − dias_historico >= inicio_dados).

-- Pares de episódios da mesma chave sobrepostos no tempo (o seguinte começa antes da saída
-- do anterior, na ordem da D01). Uma pessoa não pode estar em duas internações ao mesmo tempo.
create or replace table episodio_sobreposicao as
with e as (select episodio_id, chave, dt_inter, dt_saida from episodio)
select a.chave, a.episodio_id as anterior, b.episodio_id as seguinte
from e a join e b
  on b.chave = a.chave and b.episodio_id <> a.episodio_id
 and (b.dt_inter, b.dt_saida, b.episodio_id) > (a.dt_inter, a.dt_saida, a.episodio_id)
 and b.dt_inter < a.dt_saida;

create or replace table atributo_episodio as
with alvo as (
    select * from coorte_episodio where readmissao_30d is not null
),
anterior as (
    select
        a.episodio_id,
        h.obito,
        h.dt_saida,
        h.dt_saida >= a.dt_inter - getvariable('dias_historico') as na_janela,
        h.dt_saida - greatest(h.dt_inter, a.dt_inter - getvariable('dias_historico')) as dias_na_janela,
        a.dt_inter - h.dt_saida as dias_desde_alta
    from alvo a join episodio h
      on h.chave = a.chave and h.episodio_id <> a.episodio_id
     and h.dt_saida <= a.dt_inter
     and (h.dt_inter, h.dt_saida, h.episodio_id) < (a.dt_inter, a.dt_saida, a.episodio_id)
),
historico as (
    select
        episodio_id,
        (count(*) filter (where na_janela))::integer as episodios_365d,
        coalesce(sum(dias_na_janela) filter (where na_janela), 0)::integer as dias_internado_365d,
        min(dias_desde_alta)::integer as dias_desde_ultima_alta,
        bool_or(obito) as historico_com_obito
    from anterior
    group by episodio_id
),
sobreposto as (
    select anterior as episodio_id from episodio_sobreposicao
    union
    select seguinte from episodio_sobreposicao
)
select
    a.episodio_id,
    a.chave,
    a.readmissao_30d,
    -- Paciente e entrada (da primeira internação do episódio).
    case a.cod_idade
        when '2' then 0
        when '3' then 0
        when '4' then a.idade
        when '5' then 100 + a.idade
    end::smallint as idade,
    sx.sexo,
    cap.romano as capitulo_cid,
    sg.codigo as grupo_sigtap,
    a.car_int,
    -- Episódio.
    (a.dt_saida - a.dt_inter)::integer as dias_permanencia,
    a.uti_mes_to as dias_uti,
    coalesce(a.uti_mes_to > 0, false) as usou_uti,
    a.n_internacoes as n_aihs,
    a.n_hospitais,
    a.ligacoes_transferencia > 0 as houve_transferencia,
    a.ligacoes_permanencia > 0 as houve_permanencia,
    a.ligacoes_sem_motivo > 0 as houve_contigua_sem_motivo,
    a.cep_generico,
    a.cnes_saida as cnes_alta,
    year(a.dt_saida)::smallint as ano_alta,
    a.dt_inter,
    a.dt_saida,
    -- Histórico da mesma chave.
    a.dt_inter - getvariable('dias_historico') >= getvariable('inicio_dados') as historico_completo,
    coalesce(h.episodios_365d, 0) as episodios_365d,
    coalesce(h.dias_internado_365d, 0) as dias_internado_365d,
    h.dias_desde_ultima_alta,
    coalesce(h.historico_com_obito, false) as historico_com_obito,
    -- Colisões da D01.
    a.chave in (select chave from episodio_sobreposicao) as chave_colidente,
    a.episodio_id in (select episodio_id from sobreposto) as episodio_sobreposto
from alvo a
left join historico h using (episodio_id)
left join dic_sexo sx on sx.codigo = a.sexo
left join dic_cid10_capitulo cap on left(a.diag_princ, 3) between cap.inicio and cap.fim
left join dic_sigtap_grupo sg on sg.codigo = left(a.proc_rea, 2);
