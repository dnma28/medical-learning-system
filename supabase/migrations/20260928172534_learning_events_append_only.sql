-- Protect original learner evidence independently of the application INSERT API.
-- No existing rows are changed. Session ON DELETE CASCADE is blocked by the
-- row trigger when a session has events; use soft session abandonment instead.
create or replace function public.mls_reject_learning_event_mutation()
returns trigger language plpgsql security invoker
set search_path = ''
as $$
begin
    raise exception 'mls_learning_events is append-only; append a correction event'
        using errcode = '55000';
end;
$$;

drop trigger if exists mls_learning_events_append_only on public.mls_learning_events;
create trigger mls_learning_events_append_only
before update or delete on public.mls_learning_events
for each row execute function public.mls_reject_learning_event_mutation();

drop trigger if exists mls_learning_events_no_truncate on public.mls_learning_events;
create trigger mls_learning_events_no_truncate
before truncate on public.mls_learning_events
for each statement execute function public.mls_reject_learning_event_mutation();

revoke update, delete, truncate on public.mls_learning_events
    from public, anon, authenticated, service_role;
grant select, insert on public.mls_learning_events to service_role;
revoke all on function public.mls_reject_learning_event_mutation()
    from public, anon, authenticated;
grant execute on function public.mls_reject_learning_event_mutation() to service_role;
