-- Medical Learning System v0.7.2
-- Bounded compilation queue for cloud workers.

create table if not exists public.mls_compilation_jobs (
    job_id text primary key,
    source_id text not null
        references public.mls_sources(source_id)
        on delete cascade,
    tier text not null check (tier in ('core', 'curriculum', 'archive')),
    status text not null check (
        status in ('pending', 'running', 'succeeded', 'failed', 'cancelled')
    ),
    priority integer not null,
    attempts integer not null default 0 check (attempts >= 0),
    max_attempts integer not null default 3 check (max_attempts >= 1),
    requested_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists idx_mls_one_active_compilation_job
    on public.mls_compilation_jobs(source_id)
    where status in ('pending', 'running');

create index if not exists idx_mls_compilation_jobs_ready
    on public.mls_compilation_jobs(status, priority desc, requested_at);

alter table public.mls_compilation_jobs enable row level security;
revoke all on table public.mls_compilation_jobs from anon, authenticated;
grant all on table public.mls_compilation_jobs to service_role;
