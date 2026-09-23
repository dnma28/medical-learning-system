-- Medical Learning System v0.10
-- Logical Book Registry + logical-book Source Maps.
-- This layer sits above physical source files and below the Canonical Medical KG.

create table if not exists public.mls_logical_sources (
    logical_source_id text primary key,
    title text not null,
    kind text not null check (
        kind in (
            'textbook', 'guideline', 'systematic_review',
            'review', 'primary_study', 'other'
        )
    ),
    domain text,
    edition text,
    publication_year integer check (
        publication_year is null or publication_year between 1800 and 2200
    ),
    role text,
    identity_status text not null check (
        identity_status in (
            'verified',
            'verify_from_source',
            'potential_duplicate'
        )
    ),
    source_map_state text not null check (
        source_map_state in (
            'unmapped',
            'toc_mapped',
            'section_anchored',
            'deep_anchored',
            'ready_for_hoc90'
        )
    ),
    metadata jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.mls_source_map_nodes (
    logical_source_id text not null
        references public.mls_logical_sources(logical_source_id)
        on delete cascade,
    node_id text not null,
    parent_id text,
    source_id text references public.mls_sources(source_id)
        on delete set null,
    kind text not null check (
        kind in ('book', 'chapter', 'section', 'subsection', 'other')
    ),
    title text not null,
    depth integer not null check (depth >= 0),
    order_index integer not null check (order_index >= 0),
    page_start integer check (page_start is null or page_start >= 1),
    page_end integer check (page_end is null or page_end >= 1),
    source_anchor jsonb not null default '{}'::jsonb,
    learning_value text not null check (
        learning_value in (
            'core_mastery',
            'supporting',
            'reference_only',
            'current_clinical_check'
        )
    ),
    freshness_required boolean not null default false,
    updated_at timestamptz not null default now(),
    primary key (logical_source_id, node_id),
    unique (logical_source_id, order_index),
    foreign key (logical_source_id, parent_id)
        references public.mls_source_map_nodes(logical_source_id, node_id)
        on delete cascade,
    check (page_end is null or page_start is null or page_end >= page_start),
    check (
        learning_value <> 'current_clinical_check'
        or freshness_required = true
    )
);

create index if not exists idx_mls_source_map_parent
    on public.mls_source_map_nodes(logical_source_id, parent_id)
    where parent_id is not null;

create index if not exists idx_mls_source_map_physical_source
    on public.mls_source_map_nodes(source_id)
    where source_id is not null;

-- Cover foreign keys reported by the Supabase performance advisor.
create index if not exists idx_mls_claim_audits_supersedes
    on public.mls_claim_audits(supersedes_audit_id)
    where supersedes_audit_id is not null;

create index if not exists idx_mls_evidence_structure_links_evidence_source
    on public.mls_evidence_structure_links(evidence_id, source_id);

create index if not exists idx_mls_relation_audit_supersedes
    on public.mls_relation_audit_decisions(supersedes_decision_id)
    where supersedes_decision_id is not null;

create index if not exists idx_mls_structure_nodes_parent
    on public.mls_structure_nodes(source_id, parent_id)
    where parent_id is not null;

-- Backend-only access for the current single-user architecture.
alter table public.mls_logical_sources enable row level security;
alter table public.mls_source_map_nodes enable row level security;

revoke all on table public.mls_logical_sources from anon, authenticated;
revoke all on table public.mls_source_map_nodes from anon, authenticated;

grant all on table public.mls_logical_sources to service_role;
grant all on table public.mls_source_map_nodes to service_role;
