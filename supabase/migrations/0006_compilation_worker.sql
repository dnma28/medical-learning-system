-- Medical Learning System v0.7.4
-- Atomic queue operations for concurrent cloud compilation workers.

create or replace function public.mls_claim_compilation_job()
returns setof public.mls_compilation_jobs
language plpgsql
volatile
security invoker
set search_path = ''
as $$
begin
    return query
    with next_job as (
        select job_id
        from public.mls_compilation_jobs
        where status = 'pending'
          and attempts < max_attempts
        order by priority desc, requested_at, job_id
        for update skip locked
        limit 1
    )
    update public.mls_compilation_jobs as job
    set status = 'running',
        attempts = job.attempts + 1,
        updated_at = now()
    from next_job
    where job.job_id = next_job.job_id
    returning job.*;
end;
$$;

create or replace function public.mls_finish_compilation_job(
    target_job_id text,
    was_successful boolean
)
returns setof public.mls_compilation_jobs
language plpgsql
volatile
security invoker
set search_path = ''
as $$
begin
    return query
    update public.mls_compilation_jobs as job
    set status = case
            when was_successful then 'succeeded'
            else 'failed'
        end,
        updated_at = now()
    where job.job_id = target_job_id
      and job.status = 'running'
    returning job.*;
end;
$$;

revoke all on function public.mls_claim_compilation_job()
    from public, anon, authenticated;
revoke all on function public.mls_finish_compilation_job(text, boolean)
    from public, anon, authenticated;

grant execute on function public.mls_claim_compilation_job()
    to service_role;
grant execute on function public.mls_finish_compilation_job(text, boolean)
    to service_role;
