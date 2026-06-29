create table if not exists public.run_workspace_files (
  id bigint generated always as identity primary key,
  run_id text not null references public.app_runs(run_id) on delete cascade,
  relative_path text not null,
  file_category text not null,
  size_bytes bigint not null default 0
);

create index if not exists idx_run_workspace_files_run_id on public.run_workspace_files(run_id);
create index if not exists idx_run_workspace_files_category on public.run_workspace_files(file_category);
