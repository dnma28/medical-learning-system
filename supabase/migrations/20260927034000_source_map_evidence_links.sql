-- HỌC90 promoted Source Map evidence bridge.
-- Immutable Source Map staging remains the version authority; runtime nodes may be replaced.

create table public.mls_source_map_evidence_status (
    logical_source_id text not null,
    staging_version bigint not null,
    state text not null check (
        state in ('compiling', 'review_required', 'ready')
    ),
    compiler_version text not null,
    source_manifest jsonb not null default '{}'::jsonb
        check (jsonb_typeof(source_manifest) = 'object'),
    evidence_blocks integer not null default 0 check (evidence_blocks >= 0),
    promoted_links integer not null default 0 check (promoted_links >= 0),
    unresolved_node_ids jsonb not null default '[]'::jsonb
        check (jsonb_typeof(unresolved_node_ids) = 'array'),
    updated_at timestamptz not null default now(),
    primary key (logical_source_id, staging_version),
    foreign key (logical_source_id, staging_version)
        references public.mls_source_map_staging(logical_source_id, staging_version)
        on delete restrict
);

create table public.mls_source_map_evidence_links (
    evidence_id text not null,
    source_id text not null,
    logical_source_id text not null,
    staging_version bigint not null,
    node_id text not null,
    method text not null check (
        method in (
            'exact_heading',
            'heading_prefix',
            'heading_sequence',
            'verified_page_range',
            'manual_certified'
        )
    ),
    confidence double precision not null
        check (confidence >= 0 and confidence <= 1),
    status text not null check (
        status in ('provisional', 'promoted', 'review_required', 'deprecated')
    ),
    anchor_context jsonb not null default '{}'::jsonb
        check (jsonb_typeof(anchor_context) = 'object'),
    compiler_version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (
        evidence_id, logical_source_id, staging_version, node_id
    ),
    foreign key (evidence_id, source_id)
        references public.mls_evidence_blocks(evidence_id, source_id)
        on delete cascade,
    foreign key (logical_source_id, staging_version)
        references public.mls_source_map_staging(logical_source_id, staging_version)
        on delete restrict
);

create index idx_mls_source_map_evidence_node
    on public.mls_source_map_evidence_links(
        logical_source_id, staging_version, node_id, status, confidence desc
    );

create index idx_mls_source_map_evidence_source
    on public.mls_source_map_evidence_links(
        source_id, logical_source_id, staging_version
    );

create function public.mls_validate_source_map_evidence_link()
returns trigger language plpgsql security invoker
set search_path = ''
as $$
declare
    v_evidence_source text;
    v_evidence_logical text;
    v_evidence_page integer;
    v_evidence_sha text;
    v_node jsonb;
    v_book public.mls_logical_sources%rowtype;
    v_certificate public.mls_source_map_certificates%rowtype;
begin
    select e.source_id, s.logical_source_id, e.page_index, e.content_sha256
      into v_evidence_source, v_evidence_logical, v_evidence_page, v_evidence_sha
    from public.mls_evidence_blocks e
    join public.mls_sources s on s.source_id = e.source_id
    where e.evidence_id = new.evidence_id;

    if not found then
        raise exception 'evidence not found';
    end if;
    if v_evidence_source is distinct from new.source_id then
        raise exception 'evidence/source identity mismatch';
    end if;
    if v_evidence_logical is distinct from new.logical_source_id then
        raise exception 'cross-book evidence link rejected';
    end if;

    select n.value into v_node
    from public.mls_source_map_staging st
    cross join lateral pg_catalog.jsonb_array_elements(st.proposal) n
    where st.logical_source_id = new.logical_source_id
      and st.staging_version = new.staging_version
      and n.value->>'node_id' = new.node_id
    limit 1;

    if v_node is null then
        raise exception 'Source Map node not found in immutable staging version';
    end if;
    if v_node->>'kind' = 'book' then
        raise exception 'evidence cannot bind directly to the Source Map book root';
    end if;
    if v_node->>'source_id' is distinct from new.source_id then
        raise exception 'evidence physical source does not match staged Source Map node';
    end if;

    if new.anchor_context ? 'pdf_page'
       and (new.anchor_context->>'pdf_page')::integer <> v_evidence_page + 1
    then
        raise exception 'evidence physical page provenance mismatch';
    end if;
    if new.anchor_context ? 'content_sha256'
       and new.anchor_context->>'content_sha256' is distinct from v_evidence_sha
    then
        raise exception 'evidence content hash provenance mismatch';
    end if;

    if new.status = 'promoted' then
        if new.method = 'verified_page_range' and new.confidence < 1.0 then
            raise exception 'non-exact page-range evidence cannot be promoted';
        end if;
        select * into v_book from public.mls_logical_sources
        where logical_source_id = new.logical_source_id;
        if not found
           or v_book.promoted_staging_version is distinct from new.staging_version
        then
            raise exception 'cannot promote evidence link for a stale Source Map version';
        end if;

        select * into v_certificate
        from public.mls_source_map_certificates
        where logical_source_id = new.logical_source_id
          and staging_version = new.staging_version;

        if not found
           or v_book.promoted_certificate_sha256 is distinct from
              v_certificate.certificate_sha256
           or not public.mls_runtime_matches_staging(
                new.logical_source_id, new.staging_version
              )
        then
            raise exception 'promoted Source Map certificate/runtime gate is not satisfied';
        end if;
    end if;

    return new;
end;
$$;

create trigger mls_source_map_evidence_link_validate
before insert or update on public.mls_source_map_evidence_links
for each row execute function public.mls_validate_source_map_evidence_link();

create function public.mls_replace_source_map_evidence_links(
    p_logical_source_id text,
    p_staging_version bigint,
    p_source_id text,
    p_links jsonb
) returns integer language plpgsql security invoker
set search_path = ''
as $$
declare
    v_inserted integer := 0;
begin
    if pg_catalog.jsonb_typeof(p_links) <> 'array' then
        raise exception 'p_links must be a JSON array';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtext(p_logical_source_id)
    );

    delete from public.mls_source_map_evidence_links
    where logical_source_id = p_logical_source_id
      and staging_version = p_staging_version
      and source_id = p_source_id;

    insert into public.mls_source_map_evidence_links(
        evidence_id, source_id, logical_source_id, staging_version, node_id,
        method, confidence, status, anchor_context, compiler_version
    )
    select
        x.value->>'evidence_id',
        p_source_id,
        p_logical_source_id,
        p_staging_version,
        x.value->>'node_id',
        x.value->>'method',
        (x.value->>'confidence')::double precision,
        x.value->>'status',
        coalesce(x.value->'anchor_context', '{}'::jsonb),
        x.value->>'compiler_version'
    from pg_catalog.jsonb_array_elements(p_links) x;

    get diagnostics v_inserted = row_count;
    if v_inserted <> pg_catalog.jsonb_array_length(p_links) then
        raise exception 'partial Source Map evidence link replacement';
    end if;
    return v_inserted;
end;
$$;

alter table public.mls_source_map_evidence_status enable row level security;
alter table public.mls_source_map_evidence_links enable row level security;

revoke all on public.mls_source_map_evidence_status,
              public.mls_source_map_evidence_links
from anon, authenticated;
grant all on public.mls_source_map_evidence_status,
             public.mls_source_map_evidence_links
to service_role;

revoke all on function public.mls_validate_source_map_evidence_link()
from public, anon, authenticated;
revoke all on function public.mls_replace_source_map_evidence_links(
    text, bigint, text, jsonb
) from public, anon, authenticated;
grant execute on function public.mls_replace_source_map_evidence_links(
    text, bigint, text, jsonb
) to service_role;
