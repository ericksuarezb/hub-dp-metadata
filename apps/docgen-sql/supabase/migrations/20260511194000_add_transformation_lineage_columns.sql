alter table if exists public.run_transformations
  add column if not exists source_fields jsonb not null default '[]'::jsonb;

alter table if exists public.run_transformations
  add column if not exists physical_source_fields jsonb not null default '[]'::jsonb;

alter table if exists public.run_module_transformations
  add column if not exists source_fields jsonb not null default '[]'::jsonb;

alter table if exists public.run_module_transformations
  add column if not exists physical_source_fields jsonb not null default '[]'::jsonb;
