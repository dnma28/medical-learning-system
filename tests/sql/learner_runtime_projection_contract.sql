-- Isolated runtime-integrity contract. Everything rolls back.
begin;
set local role service_role;

insert into public.mls_learning_sessions(
    session_id,topic,target_outcome,status,checkpoint
) values (
    '__runtime_session__','Synthetic runtime','No learner data','paused',
    pg_catalog.jsonb_build_object(
        'pending_deeptutor_interaction',
        pg_catalog.jsonb_build_object('interaction_id','interaction-1')
    )
);

insert into public.mls_learning_events(
    event_id,session_id,event_type,concept_id,outcome,metadata
) values
(
    '__projection_event__','__runtime_session__','socratic_response',
    'concept-a','correct',
    pg_catalog.jsonb_build_object('mastery_projection_reviewed',true)
),
(
    '__error_event__','__runtime_session__','error_observed',
    'concept-a','incorrect','{}'::jsonb
),
(
    '__skill_event__','__runtime_session__','clinical_transfer',
    'concept-a','correct',
    pg_catalog.jsonb_build_object('skill_node_id','skill-a')
);

insert into public.mls_concept_mastery(
    concept_id,coarse_state,mastery_level,historical_peak_mastery,
    current_strength,retrieval_successes,retrieval_failures,
    mechanism_explained_independently,feynman_pass,counterfactual_pass,
    transfer_pass,clinical_transfer_pass,integration_pass,
    open_error_ids,evidence_for_mastery,source_contexts_seen,
    last_learning_event_id
) values (
    'concept-a','developing','M2','M2',
    0.4,1,0,
    false,false,false,false,false,false,
    '[]'::jsonb,pg_catalog.jsonb_build_array('__projection_event__'),
    '[]'::jsonb,'__projection_event__'
);

insert into public.mls_learner_errors(
    error_id,concept_id,observed_statement,error_type,status,
    contexts,times_seen,last_learning_event_id
) values (
    'error-a','concept-a','Synthetic error','concept_error','open',
    '[]'::jsonb,1,'__error_event__'
);

insert into public.mls_skill_nodes(
    skill_node_id,vi_name,domain,parent_ids,required_prerequisites,
    supporting_prerequisites,unlock_rule
) values (
    'skill-a','Synthetic skill','test',
    '[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'{}'::jsonb
);

insert into public.mls_skill_state(
    skill_node_id,mastery_level,current_strength,forgetting_risk,
    open_error_ids,evidence_summary,last_learning_event_id
) values (
    'skill-a','M1',0.2,0.1,'[]'::jsonb,
    pg_catalog.jsonb_build_object('event_ids',
        pg_catalog.jsonb_build_array('__skill_event__')),
    '__skill_event__'
);

-- Exercise both tables through INSERT and UPDATE, including peak-only grants.
-- Match the gate diagnostic: an unrelated FK/unique error must not count as PASS.
do $$
declare
    v_case record;
    v_operation text;
    v_table text;
    v_concept text;
    v_skill text;
    v_event text;
    v_payload jsonb;
    v_base jsonb;
    v_message text;
    v_failed boolean;
begin
    for v_case in select * from (values
        ('exposure','source_retrieval','correct',0,'{}'::jsonb,'event type cannot'),
        ('hint','hint','correct',0,'{}'::jsonb,'event type cannot'),
        ('gap','source_gap','correct',0,'{}'::jsonb,'event type cannot'),
        ('checkpoint','checkpoint','correct',0,'{}'::jsonb,'event type cannot'),
        ('observed_error','error_observed','correct',0,'{}'::jsonb,'event type cannot'),
        ('unassessed','socratic_response',null,0,'{}'::jsonb,'assessed correct'),
        ('incorrect','socratic_response','incorrect',0,'{}'::jsonb,'assessed correct'),
        ('partial','clinical_transfer','partial',0,'{}'::jsonb,'assessed correct'),
        ('ceiling','socratic_response','correct',0,'{"evidence_ceiling":"M1"}'::jsonb,'exceeds mastery ceiling'),
        ('recognition','socratic_response','correct',0,'{"evidence_kind":"recognition"}'::jsonb,'exceeds mastery ceiling'),
        ('hinted_response','socratic_response','correct',1,'{}'::jsonb,'exceeds mastery ceiling'),
        ('assisted','clinical_transfer','correct',0,'{"assisted":true}'::jsonb,'exceeds mastery ceiling'),
        ('invalid_ceiling','socratic_response','correct',0,'{"evidence_ceiling":"unknown"}'::jsonb,'invalid performance'),
        ('uncited','socratic_response','correct',0,'{}'::jsonb,'lacks event evidence')
    ) as cases(label,event_type,outcome,hint_level,metadata,expected)
    loop
        foreach v_operation in array array['INSERT','UPDATE','PEAK_INSERT','PEAK_UPDATE'] loop
            foreach v_table in array array['mls_concept_mastery','mls_skill_state'] loop
                if v_table = 'mls_skill_state' and v_operation like 'PEAK_%' then
                    continue; -- SkillState has no historical_peak_mastery column.
                end if;
                v_concept := case when v_operation like '%INSERT'
                    then '__gate_concept_' || v_case.label || '_' || v_operation
                    else 'concept-a' end;
                v_skill := case when v_operation = 'INSERT'
                    then '__gate_skill_' || v_case.label else 'skill-a' end;
                v_event := '__gate_' || v_table || '_' || v_operation || '_' || v_case.label;
                insert into public.mls_learning_events(
                    event_id,session_id,event_type,concept_id,outcome,hint_level,metadata
                ) values (
                    v_event,'__runtime_session__',v_case.event_type,v_concept,
                    v_case.outcome,v_case.hint_level,
                    v_case.metadata || pg_catalog.jsonb_build_object('skill_node_id',v_skill)
                );
                if v_table = 'mls_concept_mastery' then
                    select to_jsonb(m) into v_base from public.mls_concept_mastery m
                    where concept_id='concept-a';
                    v_payload := v_base || pg_catalog.jsonb_build_object(
                        'concept_id',v_concept,
                        'mastery_level',case when v_operation = 'PEAK_INSERT' then 'M0'
                            when v_operation = 'PEAK_UPDATE' then 'M2' else 'M7' end,
                        'historical_peak_mastery','M7',
                        'last_learning_event_id',v_event,
                        'evidence_for_mastery',case when v_case.label='uncited'
                            then '[]'::jsonb else pg_catalog.jsonb_build_array(v_event) end
                    );
                else
                    insert into public.mls_skill_nodes(skill_node_id,vi_name,domain)
                    values (v_skill,'Synthetic gate','test') on conflict do nothing;
                    select to_jsonb(s) into v_base from public.mls_skill_state s
                    where skill_node_id='skill-a';
                    v_payload := v_base || pg_catalog.jsonb_build_object(
                        'skill_node_id',v_skill,'mastery_level','M7',
                        'last_learning_event_id',v_event,
                        'evidence_summary',case when v_case.label='uncited'
                            then '{}'::jsonb else pg_catalog.jsonb_build_object(
                                'event_ids',pg_catalog.jsonb_build_array(v_event)) end
                    );
                end if;
                v_failed := false;
                begin
                    if v_operation like '%INSERT' then
                        execute format(
                            'insert into public.%I select * from jsonb_populate_record(null::public.%I,$1)',
                            v_table,v_table
                        ) using v_payload;
                    elsif v_table = 'mls_concept_mastery' then
                        update public.mls_concept_mastery
                        set mastery_level=v_payload->>'mastery_level',
                            historical_peak_mastery='M7',
                            evidence_for_mastery=v_payload->'evidence_for_mastery',
                            last_learning_event_id=v_event where concept_id='concept-a';
                    else
                        update public.mls_skill_state
                        set mastery_level='M7',evidence_summary=v_payload->'evidence_summary',
                            last_learning_event_id=v_event where skill_node_id='skill-a';
                    end if;
                exception when raise_exception then
                    get stacked diagnostics v_message = message_text;
                    if position(v_case.expected in v_message) = 0 then
                        raise exception 'unexpected gate diagnostic: %',v_message;
                    end if;
                    v_failed := true;
                end;
                if not v_failed then
                    raise exception '% % accepted unsafe case %',v_table,v_operation,v_case.label;
                end if;
            end loop;
        end loop;
    end loop;

    -- Correct recognition may initialize M1, for either projection.
    insert into public.mls_skill_nodes(skill_node_id,vi_name,domain)
    values ('skill-ceiling','Synthetic recognition','test');
    insert into public.mls_learning_events(event_id,session_id,event_type,concept_id,outcome,metadata)
    values ('__ceiling_insert_ok__','__runtime_session__','socratic_response','concept-ceiling',
        'correct','{"evidence_ceiling":"M1","skill_node_id":"skill-ceiling"}'::jsonb);
    insert into public.mls_concept_mastery(concept_id,mastery_level,historical_peak_mastery,
        evidence_for_mastery,last_learning_event_id)
    values ('concept-ceiling','M1','M1','["__ceiling_insert_ok__"]'::jsonb,'__ceiling_insert_ok__');
    insert into public.mls_skill_state(skill_node_id,mastery_level,evidence_summary,last_learning_event_id)
    values ('skill-ceiling','M1','{"event_ids":["__ceiling_insert_ok__"]}'::jsonb,'__ceiling_insert_ok__');

    -- Correct independent performance can raise an existing skill level.
    update public.mls_skill_state set mastery_level='M2',
        last_learning_event_id='__skill_event__' where skill_node_id='skill-a';
    update public.mls_skill_state set mastery_level='M1',
        last_learning_event_id='__skill_event__' where skill_node_id='skill-a';

    -- Scheduling-only exposure preserves existing mastery and peak.
    insert into public.mls_learning_events(event_id,session_id,event_type,concept_id,outcome,metadata)
    values ('__timing_only__','__runtime_session__','source_retrieval','concept-a',
        'resolved','{"skill_node_id":"skill-a"}'::jsonb);
    update public.mls_concept_mastery set next_review=pg_catalog.clock_timestamp(),
        last_learning_event_id='__timing_only__' where concept_id='concept-a';
    update public.mls_skill_state set next_review=pg_catalog.clock_timestamp(),
        last_learning_event_id='__timing_only__' where skill_node_id='skill-a';

    -- Ceiling applies to a newly granted peak, not an already supported old peak.
    insert into public.mls_learning_events(event_id,session_id,event_type,concept_id,outcome,metadata)
    values ('__recognition_ok__','__runtime_session__','socratic_response','concept-a',
        'correct','{"evidence_ceiling":"M1"}'::jsonb);
    update public.mls_concept_mastery set mastery_level='M1',
        evidence_for_mastery=evidence_for_mastery || '["__recognition_ok__"]'::jsonb,
        last_learning_event_id='__recognition_ok__' where concept_id='concept-a';
    -- Restore the baseline with the original assessed performance for later checks.
    update public.mls_concept_mastery set mastery_level='M2',
        last_learning_event_id='__projection_event__' where concept_id='concept-a';
end;
$$;

do $$
declare
    failed boolean;
    result jsonb;
begin
    -- Wrong-concept events cannot mutate concept state.
    insert into public.mls_learning_events(
        event_id,session_id,event_type,concept_id,outcome
    ) values (
        '__wrong_concept_event__','__runtime_session__','socratic_response',
        'concept-b','correct'
    );
    failed := false;
    begin
        update public.mls_concept_mastery
        set current_strength=0.5,
            last_learning_event_id='__wrong_concept_event__'
        where concept_id='concept-a';
    exception when others then failed := true; end;
    if not failed then
        raise exception 'wrong-concept mastery projection was accepted';
    end if;

    -- Source retrieval is exposure, not mastery evidence.
    insert into public.mls_learning_events(
        event_id,session_id,event_type,concept_id,outcome
    ) values (
        '__source_retrieval_event__','__runtime_session__','source_retrieval',
        'concept-a','resolved'
    );
    failed := false;
    begin
        update public.mls_concept_mastery
        set mastery_level='M3',
            historical_peak_mastery='M3',
            evidence_for_mastery=
                evidence_for_mastery
                || pg_catalog.jsonb_build_array('__source_retrieval_event__'),
            last_learning_event_id='__source_retrieval_event__'
        where concept_id='concept-a';
    exception when others then failed := true; end;
    if not failed then
        raise exception 'source retrieval granted mastery';
    end if;

    -- Error projection requires a compatible, same-concept event.
    failed := false;
    begin
        update public.mls_learner_errors
        set status='corrected',
            last_learning_event_id='__source_retrieval_event__'
        where error_id='error-a';
    exception when others then failed := true; end;
    if not failed then
        raise exception 'incompatible event updated learner error';
    end if;

    -- Skill state requires an event that names the same skill node.
    insert into public.mls_learning_events(
        event_id,session_id,event_type,concept_id,outcome,metadata
    ) values (
        '__wrong_skill_event__','__runtime_session__','clinical_transfer',
        'concept-a','partial',
        pg_catalog.jsonb_build_object('skill_node_id','skill-b')
    );
    failed := false;
    begin
        update public.mls_skill_state
        set current_strength=0.3,
            last_learning_event_id='__wrong_skill_event__'
        where skill_node_id='skill-a';
    exception when others then failed := true; end;
    if not failed then
        raise exception 'wrong-skill event updated skill state';
    end if;

    -- Atomic DeepTutor commit writes one event and resumes/clears one session.
    result := public.mls_commit_deeptutor_submission(
        '__runtime_session__',
        'interaction-1',
        pg_catalog.jsonb_build_object(
            'event_id','deeptutor-stable-1',
            'session_id','__runtime_session__',
            'event_type','socratic_response',
            'concept_id','concept-a',
            'outcome','correct',
            'answer_summary','synthetic',
            'hint_level',0,
            'metadata',pg_catalog.jsonb_build_object(
                'deeptutor_interaction_id','interaction-1',
                'automatic_mastery_credit',false
            )
        ),
        pg_catalog.jsonb_build_object(
            'pending_deeptutor_interaction',null
        ),
        pg_catalog.clock_timestamp()
    );
    if result->>'event_id' <> 'deeptutor-stable-1'
       or result->>'idempotent' <> 'false'
    then
        raise exception 'first DeepTutor commit readback mismatch';
    end if;
    if (select status from public.mls_learning_sessions
        where session_id='__runtime_session__') <> 'active'
       or (select checkpoint->'pending_deeptutor_interaction'
           from public.mls_learning_sessions
           where session_id='__runtime_session__') is distinct from 'null'::jsonb
    then
        raise exception 'DeepTutor commit did not resume/clear session atomically';
    end if;

    result := public.mls_commit_deeptutor_submission(
        '__runtime_session__',
        'interaction-1',
        (result->'event') || pg_catalog.jsonb_build_object(
            'created_at',pg_catalog.clock_timestamp()
        ),
        '{}'::jsonb,
        pg_catalog.clock_timestamp()
    );
    if result->>'event_id' <> 'deeptutor-stable-1'
       or result->>'idempotent' <> 'true'
       or (select count(*) from public.mls_learning_events
           where session_id='__runtime_session__'
             and metadata->>'deeptutor_interaction_id'='interaction-1') <> 1
    then
        raise exception 'DeepTutor retry was not idempotent';
    end if;

    -- Single-user runtime must not have two resumable sessions.
    failed := false;
    begin
        insert into public.mls_learning_sessions(
            session_id,topic,target_outcome,status
        ) values (
            '__second_resumable__','Synthetic 2','No learner data','paused'
        );
    exception when unique_violation then failed := true; end;
    if not failed then
        raise exception 'multiple resumable sessions were accepted';
    end if;

    -- Blueprint activation is atomic and leaves exactly one ACTIVE blueprint.
    perform public.mls_save_hoc90_blueprint(
        '__blueprint_a__','active','pos-a','[]'::jsonb,
        pg_catalog.jsonb_build_object('lesson_id','__blueprint_a__'),
        pg_catalog.clock_timestamp()
    );
    perform public.mls_save_hoc90_blueprint(
        '__blueprint_b__','active','pos-b','[]'::jsonb,
        pg_catalog.jsonb_build_object('lesson_id','__blueprint_b__'),
        pg_catalog.clock_timestamp()
    );
    if (select count(*) from public.mls_hoc90_blueprints
        where status='active') <> 1
       or (select status from public.mls_hoc90_blueprints
           where lesson_id='__blueprint_a__') <> 'superseded'
       or (select status from public.mls_hoc90_blueprints
           where lesson_id='__blueprint_b__') <> 'active'
    then
        raise exception 'blueprint activation was not atomic';
    end if;
end;
$$;

rollback;
