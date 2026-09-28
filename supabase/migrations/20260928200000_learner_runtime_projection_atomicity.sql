-- Enforce event-derived learner projections and atomic HOC90 runtime transitions.
-- No existing learner evidence is rewritten. The migration fails closed if legacy
-- derived learner rows exist without event provenance.

alter table public.mls_concept_mastery
    add column if not exists last_learning_event_id text;
alter table public.mls_learner_errors
    add column if not exists last_learning_event_id text;
alter table public.mls_skill_state
    add column if not exists last_learning_event_id text;

do $$
begin
    if exists (
        select 1 from public.mls_concept_mastery
        where last_learning_event_id is null
    ) or exists (
        select 1 from public.mls_learner_errors
        where last_learning_event_id is null
    ) or exists (
        select 1 from public.mls_skill_state
        where last_learning_event_id is null
    ) then
        raise exception
            'legacy learner projections require explicit event provenance before migration';
    end if;
end;
$$;

alter table public.mls_concept_mastery
    alter column last_learning_event_id set not null,
    add constraint mls_concept_mastery_last_event_fkey
        foreign key (last_learning_event_id)
        references public.mls_learning_events(event_id)
        on delete restrict;

alter table public.mls_learner_errors
    alter column last_learning_event_id set not null,
    add constraint mls_learner_errors_last_event_fkey
        foreign key (last_learning_event_id)
        references public.mls_learning_events(event_id)
        on delete restrict;

alter table public.mls_skill_state
    alter column last_learning_event_id set not null,
    add constraint mls_skill_state_last_event_fkey
        foreign key (last_learning_event_id)
        references public.mls_learning_events(event_id)
        on delete restrict;

create or replace function public.mls_validate_learner_projection_event()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_event public.mls_learning_events%rowtype;
    v_evidence_id text;
begin
    select * into v_event
    from public.mls_learning_events
    where event_id = new.last_learning_event_id;

    if not found then
        raise exception 'learner projection requires an existing learning event';
    end if;

    if tg_table_name = 'mls_concept_mastery' then
        if v_event.concept_id is null
           or v_event.concept_id is distinct from new.concept_id
        then
            raise exception 'mastery projection/event concept mismatch';
        end if;

        if pg_catalog.jsonb_typeof(new.evidence_for_mastery) <> 'array' then
            raise exception 'evidence_for_mastery must be an array';
        end if;

        for v_evidence_id in
            select value #>> '{}'
            from pg_catalog.jsonb_array_elements(new.evidence_for_mastery)
        loop
            if not exists (
                select 1
                from public.mls_learning_events e
                where e.event_id = v_evidence_id
                  and e.concept_id = new.concept_id
            ) then
                raise exception
                    'mastery evidence event is missing or belongs to another concept';
            end if;
        end loop;

        -- Scheduling-only retrieval projections may update timing/counters without
        -- changing M0-M7. Any M-level change must explicitly cite the driving
        -- append-only event in evidence_for_mastery.
        if tg_op = 'INSERT' then
            if new.mastery_level <> 'M0'
               and not (new.evidence_for_mastery ? new.last_learning_event_id)
            then
                raise exception 'non-M0 mastery insert lacks event evidence';
            end if;
        elsif new.mastery_level is distinct from old.mastery_level
              or new.historical_peak_mastery is distinct from old.historical_peak_mastery
        then
            if not (new.evidence_for_mastery ? new.last_learning_event_id) then
                raise exception 'mastery-level change lacks event evidence';
            end if;
            if v_event.event_type in (
                'source_retrieval','source_gap','hint','checkpoint'
            ) then
                raise exception 'event type cannot grant mastery-level change';
            end if;
            if v_event.metadata->>'evidence_ceiling' = 'M1'
               and new.mastery_level not in ('M0','M1')
            then
                raise exception 'recognition evidence exceeds M1 ceiling';
            end if;
        end if;

    elsif tg_table_name = 'mls_learner_errors' then
        if v_event.concept_id is null
           or v_event.concept_id is distinct from new.concept_id
        then
            raise exception 'learner-error projection/event concept mismatch';
        end if;
        if v_event.event_type not in (
            'retrieval','socratic_response','self_correction','explanation',
            'feynman','counterfactual','transfer','clinical_transfer',
            'error_observed'
        ) then
            raise exception 'event type cannot project learner error state';
        end if;

    elsif tg_table_name = 'mls_skill_state' then
        if nullif(v_event.metadata->>'skill_node_id','') is null
           or v_event.metadata->>'skill_node_id'
                is distinct from new.skill_node_id
        then
            raise exception 'skill-state projection/event skill mismatch';
        end if;
    end if;

    return new;
end;
$$;

drop trigger if exists mls_concept_mastery_event_provenance
    on public.mls_concept_mastery;
create trigger mls_concept_mastery_event_provenance
before insert or update on public.mls_concept_mastery
for each row execute function public.mls_validate_learner_projection_event();

drop trigger if exists mls_learner_errors_event_provenance
    on public.mls_learner_errors;
create trigger mls_learner_errors_event_provenance
before insert or update on public.mls_learner_errors
for each row execute function public.mls_validate_learner_projection_event();

drop trigger if exists mls_skill_state_event_provenance
    on public.mls_skill_state;
create trigger mls_skill_state_event_provenance
before insert or update on public.mls_skill_state
for each row execute function public.mls_validate_learner_projection_event();

-- Current architecture is single-user and resume-first. Two simultaneous
-- ACTIVE/PAUSED sessions are ambiguous and previously depended on latest-row choice.
create unique index if not exists idx_mls_single_resumable_session
    on public.mls_learning_sessions ((1))
    where status in ('active','paused');

-- A DeepTutor interaction is one append-only evidence event, regardless of retry.
create unique index if not exists idx_mls_learning_events_deeptutor_interaction
    on public.mls_learning_events(
        session_id,
        ((metadata->>'deeptutor_interaction_id'))
    )
    where nullif(metadata->>'deeptutor_interaction_id','') is not null;

create or replace function public.mls_commit_deeptutor_submission(
    p_session_id text,
    p_interaction_id text,
    p_event jsonb,
    p_resumed_checkpoint jsonb,
    p_updated_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_session public.mls_learning_sessions%rowtype;
    v_existing_event_id text;
    v_event_id text;
begin
    if nullif(pg_catalog.btrim(p_interaction_id),'') is null
       or pg_catalog.jsonb_typeof(p_event) <> 'object'
    then
        raise exception 'invalid DeepTutor submission payload';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'hoc90:deeptutor:' || p_session_id || ':' || p_interaction_id, 0
        )
    );

    select event_id into v_existing_event_id
    from public.mls_learning_events
    where session_id = p_session_id
      and metadata->>'deeptutor_interaction_id' = p_interaction_id
    limit 1;

    if found then
        return pg_catalog.jsonb_build_object(
            'event_id', v_existing_event_id,
            'idempotent', true
        );
    end if;

    select * into v_session
    from public.mls_learning_sessions
    where session_id = p_session_id
    for update;

    if not found then raise exception 'HOK90 session not found'; end if;
    if v_session.status <> 'paused' then
        raise exception 'DeepTutor submission requires a paused session';
    end if;
    if v_session.checkpoint->'pending_deeptutor_interaction'->>'interaction_id'
         is distinct from p_interaction_id
    then
        raise exception 'DeepTutor interaction does not match pending checkpoint';
    end if;

    if p_event->>'session_id' is distinct from p_session_id
       or p_event->'metadata'->>'deeptutor_interaction_id'
            is distinct from p_interaction_id
    then
        raise exception 'DeepTutor event/session identity mismatch';
    end if;

    v_event_id := p_event->>'event_id';
    if nullif(v_event_id,'') is null then
        raise exception 'DeepTutor event_id is required';
    end if;

    insert into public.mls_learning_events(
        event_id, session_id, event_type, concept_id, question_id,
        outcome, answer_summary, hint_level, metadata, created_at
    ) values (
        v_event_id,
        p_session_id,
        p_event->>'event_type',
        nullif(p_event->>'concept_id',''),
        nullif(p_event->>'question_id',''),
        nullif(p_event->>'outcome',''),
        nullif(p_event->>'answer_summary',''),
        coalesce((p_event->>'hint_level')::integer,0),
        coalesce(p_event->'metadata','{}'::jsonb),
        coalesce((p_event->>'created_at')::timestamptz,
                 pg_catalog.clock_timestamp())
    );

    update public.mls_learning_sessions
    set status='active',
        checkpoint=p_resumed_checkpoint,
        updated_at=coalesce(p_updated_at,pg_catalog.clock_timestamp())
    where session_id=p_session_id;

    return pg_catalog.jsonb_build_object(
        'event_id', v_event_id,
        'idempotent', false
    );
end;
$$;

-- Blueprint activation is one transaction instead of update-active then upsert-new.
create or replace function public.mls_save_hoc90_blueprint(
    p_lesson_id text,
    p_status text,
    p_curriculum_position text,
    p_source_spine jsonb,
    p_payload jsonb,
    p_updated_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_row public.mls_hoc90_blueprints%rowtype;
begin
    if p_status not in ('draft','active','paused','completed','superseded')
       or pg_catalog.jsonb_typeof(p_source_spine) <> 'array'
       or pg_catalog.jsonb_typeof(p_payload) <> 'object'
    then
        raise exception 'invalid HOK90 blueprint payload';
    end if;

    if p_status = 'active' then
        perform pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('hoc90:active-blueprint',0)
        );
        update public.mls_hoc90_blueprints
        set status='superseded',
            updated_at=coalesce(p_updated_at,pg_catalog.clock_timestamp())
        where status='active'
          and lesson_id <> p_lesson_id;
    end if;

    insert into public.mls_hoc90_blueprints(
        lesson_id,status,curriculum_position,source_spine,payload,updated_at
    ) values (
        p_lesson_id,p_status,p_curriculum_position,p_source_spine,p_payload,
        coalesce(p_updated_at,pg_catalog.clock_timestamp())
    )
    on conflict (lesson_id) do update set
        status=excluded.status,
        curriculum_position=excluded.curriculum_position,
        source_spine=excluded.source_spine,
        payload=excluded.payload,
        updated_at=excluded.updated_at
    returning * into v_row;

    return pg_catalog.to_jsonb(v_row);
end;
$$;

revoke all on function public.mls_validate_learner_projection_event()
    from public, anon, authenticated;
revoke all on function public.mls_commit_deeptutor_submission(
    text,text,jsonb,jsonb,timestamptz
) from public, anon, authenticated;
revoke all on function public.mls_save_hoc90_blueprint(
    text,text,text,jsonb,jsonb,timestamptz
) from public, anon, authenticated;

grant execute on function public.mls_validate_learner_projection_event()
    to service_role;
grant execute on function public.mls_commit_deeptutor_submission(
    text,text,jsonb,jsonb,timestamptz
) to service_role;
grant execute on function public.mls_save_hoc90_blueprint(
    text,text,text,jsonb,jsonb,timestamptz
) to service_role;
