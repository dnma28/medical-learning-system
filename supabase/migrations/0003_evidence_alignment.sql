-- Medical Learning System v0.6.6
-- Persist derived evidence-to-structure alignment and expose all links in retrieval.

create unique index if not exists idx_mls_evidence_id_source
    on public.mls_evidence_blocks(evidence_id, source_id);

create table if not exists public.mls_evidence_structure_links (
    evidence_id text not null,
    source_id text not null,
    node_id text not null,
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
    primary key (evidence_id, node_id),
    foreign key (evidence_id, source_id)
        references public.mls_evidence_blocks(evidence_id, source_id)
        on delete cascade,
    foreign key (source_id, node_id)
        references public.mls_structure_nodes(source_id, node_id)
        on delete cascade
);

create index if not exists idx_mls_evidence_structure_links_source_node
    on public.mls_evidence_structure_links(source_id, node_id);

create index if not exists idx_mls_evidence_structure_links_evidence_confidence
    on public.mls_evidence_structure_links(evidence_id, confidence desc);

alter table public.mls_evidence_structure_links enable row level security;
revoke all on table public.mls_evidence_structure_links from anon, authenticated;
grant all on table public.mls_evidence_structure_links to service_role;

-- Return all structure links for one evidence hit. Ambiguous page-range
-- candidates remain a set rather than being collapsed to an arbitrary node.
drop function if exists public.mls_match_evidence(
    extensions.vector, text, integer, text[]
);

create function public.mls_match_evidence(
    query_embedding extensions.vector,
    embedding_model_filter text,
    match_count integer default 8,
    source_ids text[] default null
)
returns table (
    evidence_id text,
    source_id text,
    structure_node_ids text[],
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
        coalesce(
            (
                select array_agg(
                    l.node_id
                    order by l.confidence desc, n.depth desc, l.node_id
                )
                from public.mls_evidence_structure_links l
                join public.mls_structure_nodes n
                  on n.source_id = l.source_id
                 and n.node_id = l.node_id
                where l.evidence_id = e.evidence_id
            ),
            array[]::text[]
        ) as structure_node_ids,
        e.page_index,
        e.content_type,
        e.text,
        1 - (emb.embedding <=> query_embedding) as similarity
    from public.mls_evidence_embeddings emb
    join public.mls_evidence_blocks e
      on e.evidence_id = emb.evidence_id
    where emb.embedding_model = embedding_model_filter
      and emb.embedding_dim = extensions.vector_dims(query_embedding)
      and (source_ids is null or e.source_id = any(source_ids))
    order by emb.embedding <=> query_embedding
    limit greatest(match_count, 1);
$$;

drop function if exists public.mls_keyword_evidence(
    text, integer, text[]
);

create function public.mls_keyword_evidence(
    query_text text,
    match_count integer default 8,
    source_ids text[] default null
)
returns table (
    evidence_id text,
    source_id text,
    structure_node_ids text[],
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
        coalesce(
            (
                select array_agg(
                    l.node_id
                    order by l.confidence desc, n.depth desc, l.node_id
                )
                from public.mls_evidence_structure_links l
                join public.mls_structure_nodes n
                  on n.source_id = l.source_id
                 and n.node_id = l.node_id
                where l.evidence_id = e.evidence_id
            ),
            array[]::text[]
        ) as structure_node_ids,
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
