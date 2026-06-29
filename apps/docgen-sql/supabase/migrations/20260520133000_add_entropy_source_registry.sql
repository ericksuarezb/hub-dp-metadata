create table if not exists public.entropy_schema_catalog (
  schema_name text primary key,
  description text,
  business_purpose text,
  schema_type text not null default 'NO CLASIFICADO',
  is_temporary boolean not null default false,
  include_in_entropy boolean not null default true,
  source_file_name text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (schema_type in ('RAW', 'CURADO', 'CRYSTAL', 'TEMPORAL', 'NO CLASIFICADO', 'OTRO'))
);

create table if not exists public.entropy_source_registry (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  target_table text not null,
  source_table text not null,
  target_schema text,
  target_object_name text,
  source_schema text,
  source_object_name text,
  source_schema_type text,
  source_kind text,
  is_temporary boolean not null default false,
  include_in_entropy boolean not null default true,
  review_status text not null default 'candidate',
  loaded_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  decision_source text not null default 'auto',
  rationale text,
  check (review_status in ('candidate', 'approved', 'excluded')),
  unique (run_id, target_table, source_table)
);

create index if not exists idx_entropy_schema_catalog_type
  on public.entropy_schema_catalog(schema_type);

create index if not exists idx_entropy_schema_catalog_temporary
  on public.entropy_schema_catalog(is_temporary);

create index if not exists idx_entropy_source_registry_run_id
  on public.entropy_source_registry(run_id);

create index if not exists idx_entropy_source_registry_target_table
  on public.entropy_source_registry(target_table);

create index if not exists idx_entropy_source_registry_source_table
  on public.entropy_source_registry(source_table);

create index if not exists idx_entropy_source_registry_include
  on public.entropy_source_registry(include_in_entropy);

create index if not exists idx_entropy_source_registry_review_status
  on public.entropy_source_registry(review_status);

create or replace view public.entropy_source_registry_ready as
select
  id,
  run_id,
  target_table,
  source_table,
  target_schema,
  target_object_name,
  source_schema,
  source_object_name,
  source_schema_type,
  source_kind,
  is_temporary,
  include_in_entropy,
  review_status,
  loaded_at,
  updated_at,
  decision_source,
  rationale
from public.entropy_source_registry
where include_in_entropy = true
  and review_status in ('candidate', 'approved');
