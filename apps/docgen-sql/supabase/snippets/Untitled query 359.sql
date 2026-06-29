with recursive
latest_ok_run as (
  select distinct on (ar.final_table_name)
    ar.final_table_name,
    ar.run_id,
    ar.created_at
  from public.app_runs ar
  where ar.audit_passed = true
    and ar.final_table_name is not null
    and split_part(ar.final_table_name, '.', 1) in (
      'cd_baz_bdclientes',
      'rd_baz_bdclientes',
      'rd_baz_bdsopoperlog'
    )
  order by ar.final_table_name, ar.created_at desc, ar.run_id desc
),
lineage as (
  select
    l.final_table_name,
    l.run_id,
    r.source_node,
    r.target_node,
    r.relation_label,
    1 as depth
  from latest_ok_run l
  join public.run_pipeline_relations r
    on r.run_id = l.run_id
   and r.target_node = l.final_table_name

  union all

  select
    x.final_table_name,
    x.run_id,
    r.source_node,
    r.target_node,
    r.relation_label,
    x.depth + 1
  from lineage x
  join public.run_pipeline_relations r
    on r.run_id = x.run_id
   and r.target_node = x.source_node
),
physical_inputs as (
  select distinct
    final_table_name,
    run_id,
    source_node as tabla_insumo
  from lineage
  where source_node like '%.%'
    and split_part(source_node, '.', 1) in (
      'cd_baz_bdclientes',
      'rd_baz_bdclientes',
      'rd_baz_bdsopoperlog',
      'tmp_baz_bdclientes'
    )
)
select
  final_table_name,
  run_id,
  tabla_insumo
from physical_inputs
where tabla_insumo like '%.%'
  and tabla_insumo not like '%::union_all'
  and final_table_name = 'cd_baz_bdclientes.cd_cap_relacion_cliente'
order by final_table_name, tabla_insumo;
