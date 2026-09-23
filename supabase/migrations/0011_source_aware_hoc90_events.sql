-- Medical Learning System v0.10.1
-- Source-aware HỌC90 event extensions.

alter table public.mls_learning_events
    drop constraint if exists mls_learning_events_event_type_check;

alter table public.mls_learning_events
    add constraint mls_learning_events_event_type_check
    check (
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
            'source_retrieval',
            'source_gap',
            'checkpoint'
        )
    );
