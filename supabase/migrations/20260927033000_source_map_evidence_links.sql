-- Source Map evidence bridge for source-grounded HỌC90.
-- Additive: legacy evidence↔legacy-structure alignment remains unchanged.

create table public.mls_source_map_evidence_links (
    logical_source_id text not null,
    node_id text not null,
    evidence_id text not null,
    source_id text not null,
    source_map_version bigint not null check (source_map_version > 0),
    method text not null check (
        method in (
            'exact_heading',
            'heading_prefix',
            'heading_sequence',
            'page_range_candidate'
        )
    ),
    confidence double precision not null
        check (confidence >= 0 and confidence <= 1),
    created_at timestamptz not null default now(),
    primary key (logical_source_id, node_id, evidence_id),
    foreign key (logical_source_id, node_id)
        references public.mls_source_map_nodes(logical_source_id, node_id)
        on delete cascade,
    foreign key (evidence_id, source_id)
        references public.mls_evidence_blocks(evidence_id, source_id)
        on delete cascade
);

create index idx_mls_source_map_evidence_links_node
    on public.mls_source_map_evidence_links(
        logical_source_id, source_id, node_id, confidence desc
    );

create index idx_mls_source_map_evidence_links_evidence
    on public.mls_source_map_evidence_links(
        evidence_id, confidence desc
    );

alter table public.mls_source_map_evidence_links enable row level security;
revoke all on table public.mls_source_map_evidence_links from anon, authenticated;
grant all on table public.mls_source_map_evidence_links to service_role;

comment on table public.mls_source_map_evidence_links is
    'Derived evidence links to the currently promoted Source Map. Links are learner-neutral and cascade away when the promoted map is replaced.';
