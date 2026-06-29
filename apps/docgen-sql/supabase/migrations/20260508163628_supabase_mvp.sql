create table if not exists public.app_runs (
  run_id text primary key,
  created_at timestamptz not null default now(),
  mode text not null,
  status text not null,
  product_name text,
  sql_file_name text,
  final_table_name text,
  target_table text,
  audit_passed boolean not null default false,
  generated_files jsonb not null default '{}'::jsonb,
  storage_objects jsonb not null default '{}'::jsonb,
  stats jsonb not null default '{}'::jsonb,
  config_snapshot jsonb not null default '{}'::jsonb
);

create table if not exists public.run_analysis (
  run_id text primary key references public.app_runs(run_id) on delete cascade,
  analysis_json jsonb not null,
  odcs_yaml text,
  pipeline_mermaid text
);

create table if not exists public.run_sources (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  source_alias text,
  source_table text not null,
  source_kind text,
  layer text,
  used_in_steps jsonb not null default '[]'::jsonb
);

create table if not exists public.run_transformations (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  field_name text not null,
  expression_name text,
  field_type text,
  origin text,
  source_fields jsonb not null default '[]'::jsonb,
  physical_source_fields jsonb not null default '[]'::jsonb,
  step_name text,
  rule_id text
);

create table if not exists public.run_modules (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  module_key text not null,
  sql_file_name text not null,
  module_name text,
  is_step boolean not null default false,
  is_principal boolean not null default false,
  target_table text,
  analysis_json jsonb not null default '{}'::jsonb,
  unique (run_id, module_key)
);

create table if not exists public.run_module_sources (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  module_key text not null,
  source_alias text,
  source_table text not null,
  source_kind text,
  layer text,
  used_in_steps jsonb not null default '[]'::jsonb
);

create table if not exists public.run_module_transformations (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  module_key text not null,
  field_name text not null,
  expression_name text,
  field_type text,
  origin text,
  source_fields jsonb not null default '[]'::jsonb,
  physical_source_fields jsonb not null default '[]'::jsonb,
  step_name text,
  rule_id text
);

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

create table if not exists public.run_workspace_files (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  relative_path text not null,
  file_category text not null,
  size_bytes bigint not null default 0,
  storage_path text
);

create table if not exists public.run_audit_summary (
  run_id text primary key references public.app_runs(run_id) on delete cascade,
  passed boolean not null,
  error_count integer not null default 0,
  warning_count integer not null default 0,
  audit_json jsonb not null default '{}'::jsonb
);

create table if not exists public.run_audit_findings (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  finding_type text not null,
  severity text not null,
  message text not null
);

create index if not exists idx_run_sources_run_id on public.run_sources(run_id);
create index if not exists idx_run_sources_source_table on public.run_sources(source_table);
create index if not exists idx_run_transformations_run_id on public.run_transformations(run_id);
create index if not exists idx_run_transformations_field_name on public.run_transformations(field_name);
create index if not exists idx_run_audit_findings_run_id on public.run_audit_findings(run_id);
create index if not exists idx_run_modules_run_id on public.run_modules(run_id);
create index if not exists idx_run_modules_target_table on public.run_modules(target_table);
create index if not exists idx_run_module_sources_run_id on public.run_module_sources(run_id);
create index if not exists idx_run_module_sources_source_table on public.run_module_sources(source_table);
create index if not exists idx_run_module_transformations_run_id on public.run_module_transformations(run_id);
create index if not exists idx_run_module_transformations_field_name on public.run_module_transformations(field_name);
create index if not exists idx_run_pipeline_relations_run_id on public.run_pipeline_relations(run_id);
create index if not exists idx_run_pipeline_relations_source_node on public.run_pipeline_relations(source_node);
create index if not exists idx_run_pipeline_relations_target_node on public.run_pipeline_relations(target_node);
create index if not exists idx_run_workspace_files_run_id on public.run_workspace_files(run_id);
create index if not exists idx_run_workspace_files_category on public.run_workspace_files(file_category);

insert into storage.buckets (id, name, public)
values ('docgen-artifacts', 'docgen-artifacts', false)
on conflict (id) do nothing;
