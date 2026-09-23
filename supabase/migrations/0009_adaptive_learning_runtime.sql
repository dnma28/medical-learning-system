-- Medical Learning System v0.9
-- Adaptive HỌC90 runtime state.
-- This migration intentionally does not rewrite mls_coverage from 0001.
-- Source coverage and learner mastery are separate dimensions in v6.

create table if not exists public.mls_learning_sessions (
    session_id text primary key,
    topic text not null,
    target_outcome text not null,
    status text not null check (
        status in ('planned', 'active', 'paused', 'completed', 'abandoned')
    ),
    curriculum_position text,
    source_spine jsonb not null default '[]'::jsonb,
    toc_position text,
    checkpoint jsonb,
    stages jsonb not null default '[]'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);

create index if not exists idx_mls_learning_sessions_status_updated
    on public.mls_learning_sessions(status, updated_at desc);

create table if not exists public.mls_learning_events (
    event_id text primary key,
    session_id text not null references public.mls_learning_sessions(session_id)
        on delete cascade,
    event_type text not null check (
        event_type in (
            'retrieval',
            'socratic_response',
            'hint',
            'self_correction',
            'explanation',
            'feynman',
            'counterfactual',
            'transfer',
            'clinical_transfer',
            'error_observed',
            'checkpoint'
        )
    ),
    concept_id text,
    question_id text,
    outcome text,
    answer_summary text,
    hint_level integer not null default 0 check (hint_level between 0 and 3),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_mls_learning_events_session_time
    on public.mls_learning_events(session_id, created_at);
create index if not exists idx_mls_learning_events_concept_time
    on public.mls_learning_events(concept_id, created_at)
    where concept_id is not null;

create table if not exists public.mls_concept_mastery (
    concept_id text primary key,
    coarse_state text not null default 'new' check (
        coarse_state in ('new', 'fragile', 'developing', 'stable')
    ),
    mastery_level text not null default 'M0' check (
        mastery_level in ('M0','M1','M2','M3','M4','M5','M6','M7')
    ),
    historical_peak_mastery text not null default 'M0' check (
        historical_peak_mastery in ('M0','M1','M2','M3','M4','M5','M6','M7')
    ),
    current_strength double precision not null default 0
        check (current_strength between 0 and 1),
    retrieval_successes integer not null default 0 check (retrieval_successes >= 0),
    retrieval_failures integer not null default 0 check (retrieval_failures >= 0),
    last_exposure timestamptz,
    last_independent_retrieval timestamptz,
    next_review timestamptz,
    mechanism_explained_independently boolean not null default false,
    feynman_pass boolean not null default false,
    counterfactual_pass boolean not null default false,
    transfer_pass boolean not null default false,
    clinical_transfer_pass boolean not null default false,
    integration_pass boolean not null default false,
    open_error_ids jsonb not null default '[]'::jsonb,
    evidence_for_mastery jsonb not null default '[]'::jsonb,
    source_contexts_seen jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

create index if not exists idx_mls_concept_mastery_review
    on public.mls_concept_mastery(next_review)
    where next_review is not null;

create table if not exists public.mls_learner_errors (
    error_id text primary key,
    concept_id text not null,
    observed_statement text not null,
    error_type text not null check (
        error_type in (
            'concept_error',
            'causal_error',
            'level_error',
            'overgeneralization',
            'missing_condition',
            'terminology_error',
            'assumption_as_fact',
            'inference_leap',
            'source_confusion',
            'transfer_failure',
            'prerequisite_gap'
        )
    ),
    status text not null default 'open' check (
        status in (
            'open',
            'self_corrected',
            'retest_required',
            'corrected',
            'closed_durable',
            'deprecated'
        )
    ),
    correction text,
    underlying_gap text,
    contexts jsonb not null default '[]'::jsonb,
    hint_response text,
    next_probe text,
    times_seen integer not null default 1 check (times_seen >= 1),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_mls_learner_errors_open
    on public.mls_learner_errors(status, concept_id);

create table if not exists public.mls_source_coverage_state (
    source_id text not null,
    node_id text not null,
    state text not null check (
        state in (
            'unseen',
            'current',
            'seen',
            'review_due',
            'coverage_complete',
            'source_gap'
        )
    ),
    last_seen timestamptz,
    updated_at timestamptz not null default now(),
    primary key (source_id, node_id),
    foreign key (source_id, node_id)
        references public.mls_structure_nodes(source_id, node_id)
        on delete cascade
);

create table if not exists public.mls_skill_nodes (
    skill_node_id text primary key,
    vi_name text not null,
    english_alias text,
    domain text not null,
    parent_ids jsonb not null default '[]'::jsonb,
    required_prerequisites jsonb not null default '[]'::jsonb,
    supporting_prerequisites jsonb not null default '[]'::jsonb,
    unlock_rule jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.mls_skill_state (
    skill_node_id text primary key references public.mls_skill_nodes(skill_node_id)
        on delete cascade,
    mastery_level text not null default 'M0' check (
        mastery_level in ('M0','M1','M2','M3','M4','M5','M6','M7')
    ),
    current_strength double precision not null default 0
        check (current_strength between 0 and 1),
    forgetting_risk double precision not null default 0
        check (forgetting_risk between 0 and 1),
    open_error_ids jsonb not null default '[]'::jsonb,
    last_test timestamptz,
    next_review timestamptz,
    evidence_summary jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.mls_hoc90_blueprints (
    lesson_id text primary key,
    status text not null check (
        status in ('draft', 'active', 'paused', 'completed', 'superseded')
    ),
    curriculum_position text,
    source_spine jsonb not null default '[]'::jsonb,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists idx_mls_single_active_blueprint
    on public.mls_hoc90_blueprints ((status))
    where status = 'active';

-- Runtime tables are backend-only for the current single-user architecture.
alter table public.mls_learning_sessions enable row level security;
alter table public.mls_learning_events enable row level security;
alter table public.mls_concept_mastery enable row level security;
alter table public.mls_learner_errors enable row level security;
alter table public.mls_source_coverage_state enable row level security;
alter table public.mls_skill_nodes enable row level security;
alter table public.mls_skill_state enable row level security;
alter table public.mls_hoc90_blueprints enable row level security;

revoke all on table public.mls_learning_sessions from anon, authenticated;
revoke all on table public.mls_learning_events from anon, authenticated;
revoke all on table public.mls_concept_mastery from anon, authenticated;
revoke all on table public.mls_learner_errors from anon, authenticated;
revoke all on table public.mls_source_coverage_state from anon, authenticated;
revoke all on table public.mls_skill_nodes from anon, authenticated;
revoke all on table public.mls_skill_state from anon, authenticated;
revoke all on table public.mls_hoc90_blueprints from anon, authenticated;

grant all on table public.mls_learning_sessions to service_role;
grant all on table public.mls_learning_events to service_role;
grant all on table public.mls_concept_mastery to service_role;
grant all on table public.mls_learner_errors to service_role;
grant all on table public.mls_source_coverage_state to service_role;
grant all on table public.mls_skill_nodes to service_role;
grant all on table public.mls_skill_state to service_role;
grant all on table public.mls_hoc90_blueprints to service_role;
