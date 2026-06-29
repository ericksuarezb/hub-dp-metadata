alter table if exists public.run_analysis
  add column if not exists pipeline_mermaid text;

create table if not exists public.run_pipeline_relations (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  module_key text not null,
  module_name text,
  sql_file_name text,
  source_node text not null,
  target_node text not null,
  relation_label text not null,
  source_group text,
  target_group text,
  source_kind text,
  target_kind text,
  is_pivot boolean not null default false
);

create index if not exists idx_run_pipeline_relations_run_id on public.run_pipeline_relations(run_id);
create index if not exists idx_run_pipeline_relations_source_node on public.run_pipeline_relations(source_node);
create index if not exists idx_run_pipeline_relations_target_node on public.run_pipeline_relations(target_node);
