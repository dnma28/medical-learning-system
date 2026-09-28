-- Isolated PostgreSQL contract. All fixtures are rolled back, never cleaned by DELETE.
begin;
set local role service_role;
insert into public.mls_learning_sessions(session_id,topic,target_outcome,status)
values ('__append_only_contract__','Synthetic contract','No learner data','active');
insert into public.mls_learning_events(event_id,session_id,event_type,outcome)
values ('__append_only_event__','__append_only_contract__','retrieval','original');

do $$
begin
    if (select outcome from public.mls_learning_events
        where event_id='__append_only_event__') <> 'original' then
        raise exception 'service_role SELECT/INSERT contract failed';
    end if;
    begin
        insert into public.mls_learning_events(event_id,session_id,event_type)
        values ('__append_only_event__','__append_only_contract__','retrieval');
        raise exception 'duplicate event ID was accepted';
    exception when unique_violation then null;
    end;
    begin
        update public.mls_learning_events set outcome='changed'
        where event_id='__append_only_event__';
        raise exception 'service_role UPDATE was accepted';
    exception when insufficient_privilege then null;
    end;
    begin
        delete from public.mls_learning_events where event_id='__append_only_event__';
        raise exception 'service_role DELETE was accepted';
    exception when insufficient_privilege then null;
    end;
    begin
        truncate public.mls_learning_events;
        raise exception 'service_role TRUNCATE was accepted';
    exception when insufficient_privilege then null;
    end;
    begin
        delete from public.mls_learning_sessions where session_id='__append_only_contract__';
        raise exception 'session cascade erased learning evidence';
    exception when sqlstate '55000' then null;
    end;
    update public.mls_learning_sessions set status='abandoned'
    where session_id='__append_only_contract__';
end;
$$;
reset role;

-- Table owner bypasses table grants: triggers must still protect the evidence.
do $$
begin
    begin
        update public.mls_learning_events set outcome='changed'
        where event_id='__append_only_event__';
        raise exception 'owner UPDATE was accepted';
    exception when sqlstate '55000' then null;
    end;
    begin
        delete from public.mls_learning_events where event_id='__append_only_event__';
        raise exception 'owner DELETE was accepted';
    exception when sqlstate '55000' then null;
    end;
    begin
        truncate public.mls_learning_events;
        raise exception 'owner TRUNCATE was accepted';
    exception when sqlstate '55000' then null;
    end;
    begin
        truncate public.mls_learning_sessions cascade;
        raise exception 'TRUNCATE CASCADE was accepted';
    exception when sqlstate '55000' then null;
    end;
    if not exists (select 1 from public.mls_learning_events
                   where event_id='__append_only_event__' and outcome='original') then
        raise exception 'original event was not preserved';
    end if;
    if has_table_privilege('anon','public.mls_learning_events','SELECT')
       or has_table_privilege('authenticated','public.mls_learning_events','INSERT') then
        raise exception 'public access was introduced';
    end if;
end;
$$;
rollback;
