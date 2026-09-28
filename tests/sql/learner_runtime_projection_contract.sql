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
    'concept-a','partial',
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
        pg_catalog.jsonb_build_object(
            'event_id','deeptutor-stable-1',
            'session_id','__runtime_session__',
            'event_type','socratic_response',
            'metadata',pg_catalog.jsonb_build_object(
                'deeptutor_interaction_id','interaction-1'
            )
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
