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
  step_name text,
  rule_id text
);

create index if not exists idx_run_modules_run_id on public.run_modules(run_id);
create index if not exists idx_run_modules_target_table on public.run_modules(target_table);
create index if not exists idx_run_module_sources_run_id on public.run_module_sources(run_id);
create index if not exists idx_run_module_sources_source_table on public.run_module_sources(source_table);
create index if not exists idx_run_module_transformations_run_id on public.run_module_transformations(run_id);
create index if not exists idx_run_module_transformations_field_name on public.run_module_transformations(field_name);
