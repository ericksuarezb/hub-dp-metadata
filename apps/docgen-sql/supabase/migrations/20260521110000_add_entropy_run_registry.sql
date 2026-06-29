create table if not exists public.entropy_run_registry (
  run_id text primary key references public.app_runs(run_id) on delete cascade,
  include_in_entropy boolean not null default false,
  review_status text not null default 'pending',
  complementary_actions jsonb not null default '[]'::jsonb,
  notes text,
  last_import_status text not null default 'idle',
  last_operation_at timestamptz,
  last_imported_at timestamptz,
  last_import_result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (review_status in ('pending', 'approved', 'excluded')),
  check (last_import_status in ('idle', 'planned', 'executed', 'failed'))
);

create index if not exists idx_entropy_run_registry_include
  on public.entropy_run_registry(include_in_entropy);

create index if not exists idx_entropy_run_registry_review_status
  on public.entropy_run_registry(review_status);

create index if not exists idx_entropy_run_registry_last_import_status
  on public.entropy_run_registry(last_import_status);
