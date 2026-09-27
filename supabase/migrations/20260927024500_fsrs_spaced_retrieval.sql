-- HỌC90 spaced-retrieval scheduler state.
-- Additive only: M0-M7 remains evidence-driven and independent from FSRS timing.

alter table public.mls_concept_mastery
    add column if not exists spaced_repetition_state jsonb
    not null default '{}'::jsonb;

comment on column public.mls_concept_mastery.spaced_repetition_state is
    'Versioned scheduler state for delayed retrieval timing only; never mastery authority.';
