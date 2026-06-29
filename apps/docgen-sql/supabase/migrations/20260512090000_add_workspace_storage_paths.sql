alter table if exists public.run_workspace_files
  add column if not exists storage_path text;
