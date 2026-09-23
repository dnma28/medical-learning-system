-- Medical Learning System v0.6
-- Retrieval primitives: zero-embedding keyword search + model-aware pgvector.

create extension if not exists vector with schema extensions;

alter table public.mls_evidence_blocks
    add column if not exists search_tsv tsvector
    generated always as (
        to_tsvector('simple', coalesce(text, ''))
    ) stored;

create index if not exists idx_mls_evidence_search_tsv
    on public.mls_evidence_blocks using gin (search_tsv);

create table if not exists public.mls_evidence_embeddings (
    evidence_id text not null
        references public.mls_evidence_blocks(evidence_id)
        on delete cascade,
    embedding_model text not null,
    embedding_dim integer not null check (embedding_dim > 0),
    embedding extensions.vector not null,
    content_sha256 text not null,
    created_at timestamptz not null default now(),
    primary key (evidence_id, embedding_model)
);

create index if not exists idx_mls_embeddings_model
    on public.mls_evidence_embeddings(embedding_model, embedding_dim);

alter table public.mls_evidence_embeddings enable row level security;
revoke all on table public.mls_evidence_embeddings from anon, authenticated;
grant all on table public.mls_evidence_embeddings to service_role;

-- PostgREST does not expose pgvector distance operators directly, so semantic
-- search is wrapped in an RPC. Different embedding models are never mixed.
create or replace function public.mls_match_evidence(
    query_embedding extensions.vector,
    embedding_model_filter text,
    match_count integer default 8,
    source_ids text[] default null
)
returns table (
    evidence_id text,
    source_id text,
    structure_node_id text,
    page_index integer,
    content_type text,
    text text,
    similarity double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
    select
        e.evidence_id,
        e.source_id,
        e.structure_node_id,
        e.page_index,
        e.content_type,
        e.text,
        1 - (emb.embedding OPERATOR(extensions.<=>) query_embedding) as similarity
    from public.mls_evidence_embeddings emb
    join public.mls_evidence_blocks e
      on e.evidence_id = emb.evidence_id
    where emb.embedding_model = embedding_model_filter
      and emb.embedding_dim = extensions.vector_dims(query_embedding)
      and (source_ids is null or e.source_id = any(source_ids))
    order by emb.embedding OPERATOR(extensions.<=>) query_embedding
    limit greatest(match_count, 1);
$$;

-- Keyword retrieval costs no embedding/API calls and remains available even
-- before a semantic embedding model is selected.
create or replace function public.mls_keyword_evidence(
    query_text text,
    match_count integer default 8,
    source_ids text[] default null
)
returns table (
    evidence_id text,
    source_id text,
    structure_node_id text,
    page_index integer,
    content_type text,
    text text,
    rank real
)
language sql
stable
security invoker
set search_path = ''
as $$
    with query as (
        select websearch_to_tsquery('simple', query_text) as q
    )
    select
        e.evidence_id,
        e.source_id,
        e.structure_node_id,
        e.page_index,
        e.content_type,
        e.text,
        ts_rank_cd(e.search_tsv, query.q) as rank
    from public.mls_evidence_blocks e
    cross join query
    where e.search_tsv @@ query.q
      and (source_ids is null or e.source_id = any(source_ids))
    order by rank desc, e.source_id, e.block_index
    limit greatest(match_count, 1);
$$;

revoke all on function public.mls_match_evidence(
    extensions.vector, text, integer, text[]
) from public, anon, authenticated;
revoke all on function public.mls_keyword_evidence(
    text, integer, text[]
) from public, anon, authenticated;

grant execute on function public.mls_match_evidence(
    extensions.vector, text, integer, text[]
) to service_role;
grant execute on function public.mls_keyword_evidence(
    text, integer, text[]
) to service_role;

-- No HNSW/IVFFlat index yet. A vector index requires a pinned embedding model
-- and dimension. v0.6 deliberately benchmarks first, then adds a partial HNSW
-- index for the selected model instead of forcing a costly full re-embedding.
