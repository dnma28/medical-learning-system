-- Medical Learning System v0.7.1
-- Content-versioned compilation history for cloud execution.

create table if not exists public.mls_compilation_manifests (
    run_id text not null unique,
    source_id text not null
        references public.mls_sources(source_id)
        on delete cascade,
    content_sha256 text not null,
    strategy text not null check (strategy in ('native_pdf')),
    status text not null check (status in ('success', 'error')),
    structure_nodes integer not null check (structure_nodes >= 0),
    evidence_blocks integer not null check (evidence_blocks >= 0),
    alignment_links integer not null check (alignment_links >= 0),
    grounded_evidence_blocks integer not null
        check (grounded_evidence_blocks >= 0),
    needs_multimodal_enrichment boolean not null,
    error text,
    created_at timestamptz not null,
    primary key (source_id, content_sha256, strategy)
);

create index if not exists idx_mls_compilation_source_created
    on public.mls_compilation_manifests(source_id, created_at desc);

alter table public.mls_compilation_manifests enable row level security;
revoke all on table public.mls_compilation_manifests from anon, authenticated;
grant all on table public.mls_compilation_manifests to service_role;
