-- Medical Learning System v0.8.4
-- Append-only passage-level claim audit history.

create table if not exists public.mls_claim_audits (
    audit_id text primary key,
    patch_id text not null,
    claim_text text not null,
    source_anchor_id text not null,
    source_anchor_state text not null check (
        source_anchor_state in ('PASS', 'MISMATCH', 'GAP')
    ),
    evidence_candidate_ids text[] not null default '{}',
    selected_evidence_ids text[] not null default '{}',
    content_fidelity_state text not null check (
        content_fidelity_state in (
            'UNREVIEWED', 'VERIFIED', 'PARTIAL', 'UNSUPPORTED',
            'WRONG_SOURCE', 'UNRESOLVED'
        )
    ),
    current_validity_state text not null check (
        current_validity_state in (
            'NOT_APPLICABLE', 'BOOK_CURRENT_UNCHECKED',
            'REQUIRES_EXTERNAL_CHECK', 'CURRENT_VERIFIED',
            'OUTDATED', 'CONTESTED'
        )
    ),
    requires_current_check boolean not null default false,
    reviewer text not null,
    review_method text not null,
    reviewed_at timestamptz not null,
    supersedes_audit_id text
        references public.mls_claim_audits(audit_id)
        on delete restrict,
    notes jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    check (selected_evidence_ids <@ evidence_candidate_ids),
    check (
        content_fidelity_state <> 'VERIFIED'
        or cardinality(selected_evidence_ids) > 0
    )
);

create index if not exists idx_mls_claim_audits_claim_history
    on public.mls_claim_audits(
        patch_id,
        claim_text,
        reviewed_at,
        audit_id
    );

create or replace function public.mls_reject_claim_audit_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    raise exception
        'mls_claim_audits is append-only; insert a superseding audit instead';
end;
$$;

drop trigger if exists trg_mls_claim_audits_append_only
    on public.mls_claim_audits;

create trigger trg_mls_claim_audits_append_only
before update or delete on public.mls_claim_audits
for each row
execute function public.mls_reject_claim_audit_mutation();

alter table public.mls_claim_audits enable row level security;

revoke all on table public.mls_claim_audits from anon, authenticated;
revoke all on table public.mls_claim_audits from service_role;
grant select, insert on table public.mls_claim_audits to service_role;
