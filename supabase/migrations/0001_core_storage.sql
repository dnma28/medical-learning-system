-- Medical Learning System v0.5.2
-- Backend-only Supabase schema. Source binaries remain in Google Drive.

create table if not exists public.mls_sources (
    source_id text primary key,
    logical_source_id text not null,
    provider text not null,
    provider_file_id text not null,
    title text not null,
    mime_type text not null,
    size_bytes bigint check (size_bytes is null or size_bytes >= 0),
    modified_time timestamptz not null,
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
    part_index integer check (part_index is null or part_index >= 1),
    status text not null check (
        status in ('new', 'parsed', 'indexed', 'graphed', 'compiled', 'stale', 'error')
    ),
    content_sha256 text,
    metadata_fingerprint text not null,
    updated_at timestamptz not null default now(),
    unique (provider, provider_file_id)
);

create table if not exists public.mls_structure_nodes (
    source_id text not null references public.mls_sources(source_id) on delete cascade,
    node_id text not null,
    parent_id text,
    kind text not null check (kind in ('book', 'chapter', 'section', 'subsection', 'other')),
    title text not null,
    depth integer not null check (depth >= 0),
    order_index integer not null check (order_index >= 0),
    page_start integer check (page_start is null or page_start >= 1),
    page_end integer check (page_end is null or page_end >= 1),
    primary key (source_id, node_id),
    foreign key (source_id, parent_id)
        references public.mls_structure_nodes(source_id, node_id)
        on delete cascade,
    check (page_end is null or page_start is null or page_end >= page_start)
);

create index if not exists idx_mls_structure_source_order
    on public.mls_structure_nodes(source_id, order_index);

create table if not exists public.mls_coverage (
    source_id text not null,
    node_id text not null,
    state text not null check (state in ('not_learned', 'learning', 'review', 'mastered')),
    updated_at timestamptz not null default now(),
    primary key (source_id, node_id),
    foreign key (source_id, node_id)
        references public.mls_structure_nodes(source_id, node_id)
        on delete cascade
);

create table if not exists public.mls_evidence_blocks (
    evidence_id text primary key,
    source_id text not null references public.mls_sources(source_id) on delete cascade,
    structure_node_id text,
    block_index integer not null check (block_index >= 0),
    page_index integer not null check (page_index >= 0),
    page_label text,
    content_type text not null check (
        content_type in ('text', 'image', 'table', 'equation', 'code', 'other')
    ),
    text text,
    asset_ref text,
    bbox jsonb,
    parser text not null,
    parser_version text,
    content_sha256 text not null,
    unique (source_id, block_index),
    foreign key (source_id, structure_node_id)
        references public.mls_structure_nodes(source_id, node_id)
        on delete set null
);

create index if not exists idx_mls_evidence_source_page
    on public.mls_evidence_blocks(source_id, page_index, block_index);

create index if not exists idx_mls_evidence_structure
    on public.mls_evidence_blocks(source_id, structure_node_id);

-- Backend-only access for the current single-user architecture.
-- No anon/authenticated policies are intentionally created.
alter table public.mls_sources enable row level security;
alter table public.mls_structure_nodes enable row level security;
alter table public.mls_coverage enable row level security;
alter table public.mls_evidence_blocks enable row level security;

revoke all on table public.mls_sources from anon, authenticated;
revoke all on table public.mls_structure_nodes from anon, authenticated;
revoke all on table public.mls_coverage from anon, authenticated;
revoke all on table public.mls_evidence_blocks from anon, authenticated;

grant all on table public.mls_sources to service_role;
grant all on table public.mls_structure_nodes to service_role;
grant all on table public.mls_coverage to service_role;
grant all on table public.mls_evidence_blocks to service_role;
