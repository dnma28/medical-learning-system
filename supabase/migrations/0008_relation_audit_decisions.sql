-- Medical Learning System v0.8.6
-- Append-only relation↔claim-audit review decisions.

create table if not exists public.mls_relation_audit_decisions (
    decision_id text primary key,
    mapping_id text not null,
    relation_candidate_id text not null,
    audit_id text not null
        references public.mls_claim_audits(audit_id)
        on delete restrict,
    state text not null check (state in ('CONFIRMED', 'REJECTED')),
    reviewer text not null,
    reviewed_at timestamptz not null,
    note text,
    supersedes_decision_id text
        references public.mls_relation_audit_decisions(decision_id)
        on delete restrict
);

create index if not exists idx_mls_relation_audit_mapping_history
    on public.mls_relation_audit_decisions(
        mapping_id,
        reviewed_at,
        decision_id
    );

create index if not exists idx_mls_relation_audit_relation
    on public.mls_relation_audit_decisions(relation_candidate_id);

create index if not exists idx_mls_relation_audit_claim
    on public.mls_relation_audit_decisions(audit_id);

alter table public.mls_relation_audit_decisions enable row level security;

revoke all on table public.mls_relation_audit_decisions
    from anon, authenticated;

grant all on table public.mls_relation_audit_decisions
    to service_role;

-- Application code is append-only. No UPDATE/UPSERT review API is exposed.
