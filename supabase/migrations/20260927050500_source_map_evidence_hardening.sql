-- Harden the live promoted Source Map evidence bridge.
-- Existing Costanzo pilot rows are preserved and backfilled to immutable staging v4.

alter table public.mls_source_map_evidence_links
    add column staging_version bigint,
    add column status text,
    add column anchor_context jsonb not null default '{}'::jsonb,
    add column compiler_version text,
    add column updated_at timestamptz not null default now();

update public.mls_source_map_evidence_links l
set staging_version = b.promoted_staging_version,
    status = 'promoted',
    compiler_version = 'source-map-evidence-v1-backfill',
    anchor_context = pg_catalog.jsonb_strip_nulls(
        pg_catalog.jsonb_build_object(
            'pdf_page', e.page_index + 1,
            'page_index', e.page_index,
            'bbox', e.bbox,
            'content_sha256', e.content_sha256,
            'parser', e.parser,
            'parser_version', e.parser_version
        )
    ),
    updated_at = l.created_at
from public.mls_logical_sources b,
     public.mls_evidence_blocks e
where b.logical_source_id = l.logical_source_id
  and e.evidence_id = l.evidence_id
  and e.source_id = l.source_id
  and b.promoted_staging_version is not null;

do $$
begin
    if exists (
        select 1
        from public.mls_source_map_evidence_links
        where staging_version is null
           or status is null
           or compiler_version is null
    ) then
        raise exception 'cannot harden Source Map evidence: existing links lack promotion metadata';
    end if;
end;
$$;

alter table public.mls_source_map_evidence_links
    alter column staging_version set not null,
    alter column status set not null,
    alter column compiler_version set not null,
    add constraint mls_source_map_evidence_links_status_check check (
        status in ('promoted', 'review_required', 'deprecated')
    );

-- Runtime Source Map rows are mutable promotion projections. Evidence history binds
-- to immutable staging instead so a future promotion does not cascade-delete it.
alter table public.mls_source_map_evidence_links
    drop constraint mls_source_map_evidence_links_logical_source_id_node_id_fkey,
    drop constraint mls_source_map_evidence_links_pkey;

alter table public.mls_source_map_evidence_links
    add constraint mls_source_map_evidence_links_stage_fkey
        foreign key (logical_source_id, staging_version)
        references public.mls_source_map_staging(logical_source_id, staging_version)
        on delete restrict,
    add constraint mls_source_map_evidence_links_pkey
        primary key (logical_source_id, staging_version, node_id, evidence_id);

drop index if exists public.idx_mls_source_map_evidence_links_node;
create index idx_mls_source_map_evidence_links_node
    on public.mls_source_map_evidence_links(
        logical_source_id, staging_version, source_id, node_id,
        status, confidence desc
    );

create table public.mls_source_map_evidence_status (
    logical_source_id text not null,
    staging_version bigint not null,
    source_map_version bigint not null check (source_map_version > 0),
    state text not null check (
        state in ('partial', 'complete', 'review_required', 'stale')
    ),
    legacy_fallback_disabled boolean not null default true,
    source_manifest jsonb not null default '{}'::jsonb
        check (pg_catalog.jsonb_typeof(source_manifest) = 'object'),
    evidence_blocks integer not null default 0 check (evidence_blocks >= 0),
    promoted_links integer not null default 0 check (promoted_links >= 0),
    unresolved_node_ids jsonb not null default '[]'::jsonb
        check (pg_catalog.jsonb_typeof(unresolved_node_ids) = 'array'),
    compiler_version text not null,
    updated_at timestamptz not null default now(),
    primary key (logical_source_id, staging_version),
    foreign key (logical_source_id, staging_version)
        references public.mls_source_map_staging(logical_source_id, staging_version)
        on delete restrict
);

-- Existing production links represent a deliberately partial Costanzo pilot.
-- Backfill them as partial: linked nodes remain usable, uncovered nodes fail closed.
insert into public.mls_source_map_evidence_status(
    logical_source_id, staging_version, source_map_version, state,
    legacy_fallback_disabled, source_manifest, evidence_blocks,
    promoted_links, unresolved_node_ids, compiler_version
)
select
    l.logical_source_id,
    l.staging_version,
    max(l.source_map_version),
    'partial',
    true,
    pg_catalog.jsonb_build_object(
        'backfill', 'source-map-evidence-v1-production-links'
    ),
    count(distinct l.evidence_id),
    count(*),
    '[]'::jsonb,
    'source-map-evidence-v1-backfill'
from public.mls_source_map_evidence_links l
where l.status = 'promoted'
group by l.logical_source_id, l.staging_version
on conflict (logical_source_id, staging_version) do nothing;

create function public.mls_validate_source_map_evidence_link()
returns trigger language plpgsql security invoker
set search_path = ''
as $$
declare
    v_evidence_source text;
    v_evidence_logical text;
    v_page_index integer;
    v_content_sha256 text;
    v_node jsonb;
    v_book public.mls_logical_sources%rowtype;
begin
    select e.source_id, s.logical_source_id, e.page_index, e.content_sha256
      into v_evidence_source, v_evidence_logical, v_page_index, v_content_sha256
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
        raise exception 'cross-book Source Map evidence link rejected';
    end if;

    select n.value into v_node
    from public.mls_source_map_staging st
    cross join lateral pg_catalog.jsonb_array_elements(st.proposal) n
    where st.logical_source_id = new.logical_source_id
      and st.staging_version = new.staging_version
      and n.value->>'node_id' = new.node_id
    limit 1;

    if v_node is null then
        raise exception 'Source Map node is absent from immutable staging version';
    end if;
    if v_node->>'kind' = 'book' then
        raise exception 'evidence cannot bind directly to Source Map book root';
    end if;
    if v_node->>'source_id' is distinct from new.source_id then
        raise exception 'evidence physical source does not match staged Source Map node';
    end if;

    if not (new.anchor_context ? 'pdf_page')
       or not (new.anchor_context ? 'content_sha256')
    then
        raise exception 'promoted evidence link requires page and content-hash provenance';
    end if;
    if (new.anchor_context->>'pdf_page')::integer <> v_page_index + 1 then
        raise exception 'evidence page provenance mismatch';
    end if;
    if new.anchor_context->>'content_sha256' is distinct from v_content_sha256 then
        raise exception 'evidence content-hash provenance mismatch';
    end if;

    if new.status = 'promoted' then
        select * into v_book
        from public.mls_logical_sources
        where logical_source_id = new.logical_source_id;

        if not found
           or v_book.promoted_staging_version is distinct from new.staging_version
           or v_book.source_map_version is distinct from new.source_map_version
        then
            raise exception 'cannot promote evidence for a stale Source Map version';
        end if;
    end if;

    return new;
end;
$$;

create trigger mls_source_map_evidence_link_validate
before insert or update on public.mls_source_map_evidence_links
for each row execute function public.mls_validate_source_map_evidence_link();

create function public.mls_mark_source_map_evidence_stale()
returns trigger language plpgsql security invoker
set search_path = ''
as $$
begin
    if old.promoted_staging_version is distinct from new.promoted_staging_version then
        update public.mls_source_map_evidence_links
        set status = 'deprecated', updated_at = now()
        where logical_source_id = new.logical_source_id
          and staging_version is distinct from new.promoted_staging_version
          and status <> 'deprecated';

        update public.mls_source_map_evidence_status
        set state = 'stale', updated_at = now()
        where logical_source_id = new.logical_source_id
          and staging_version is distinct from new.promoted_staging_version
          and state <> 'stale';
    end if;
    return new;
end;
$$;

create trigger mls_source_map_evidence_stale_after_promotion
after update of promoted_staging_version on public.mls_logical_sources
for each row
when (old.promoted_staging_version is distinct from new.promoted_staging_version)
execute function public.mls_mark_source_map_evidence_stale();

create function public.mls_commit_source_map_evidence(
    p_logical_source_id text,
    p_staging_version bigint,
    p_source_map_version bigint,
    p_source_id text,
    p_expected_content_sha256 text,
    p_evidence jsonb,
    p_links jsonb,
    p_migration_state text,
    p_unresolved_node_ids jsonb,
    p_compiler_version text,
    p_source_manifest jsonb
) returns jsonb language plpgsql security invoker
set search_path = ''
as $$
declare
    v_book public.mls_logical_sources%rowtype;
    v_source public.mls_sources%rowtype;
    v_evidence_count integer;
    v_link_count integer;
    v_readiness jsonb;
begin
    if pg_catalog.jsonb_typeof(p_evidence) <> 'array'
       or pg_catalog.jsonb_typeof(p_links) <> 'array'
       or pg_catalog.jsonb_typeof(p_unresolved_node_ids) <> 'array'
       or pg_catalog.jsonb_typeof(p_source_manifest) <> 'object'
    then
        raise exception 'invalid Source Map evidence JSON payload shape';
    end if;
    if p_migration_state not in ('partial', 'complete', 'review_required') then
        raise exception 'invalid Source Map evidence migration state';
    end if;
    if nullif(p_compiler_version, '') is null then
        raise exception 'compiler_version is required';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_logical_source_id, 0)
    );

    select * into v_book
    from public.mls_logical_sources
    where logical_source_id = p_logical_source_id
    for update;

    if not found
       or v_book.promoted_staging_version is distinct from p_staging_version
       or v_book.source_map_version is distinct from p_source_map_version
    then
        raise exception 'Source Map promotion changed before evidence commit';
    end if;

    v_readiness := public.mls_source_map_readiness(p_logical_source_id);
    if coalesce((v_readiness->>'ready_for_hoc90')::boolean, false) is not true then
        raise exception 'Source Map is not ready_for_hoc90';
    end if;

    select * into v_source
    from public.mls_sources
    where source_id = p_source_id;

    if not found
       or v_source.logical_source_id is distinct from p_logical_source_id
       or v_source.content_sha256 is distinct from p_expected_content_sha256
    then
        raise exception 'physical source identity or fingerprint mismatch';
    end if;

    if exists (
        select 1
        from pg_catalog.jsonb_array_elements(p_evidence) x
        where nullif(x.value->>'evidence_id', '') is null
           or (x.value->>'block_index') !~ '^[0-9]+$'
           or (x.value->>'page_index') !~ '^[0-9]+$'
           or x.value->>'content_type' not in (
                'text','image','table','equation','code','other'
              )
           or nullif(x.value->>'parser', '') is null
           or nullif(x.value->>'content_sha256', '') is null
           or (
                nullif(pg_catalog.btrim(coalesce(x.value->>'text','')), '') is null
                and nullif(x.value->>'asset_ref','') is null
              )
    ) then
        raise exception 'invalid evidence payload';
    end if;

    if (
        select count(distinct x.value->>'evidence_id')
        from pg_catalog.jsonb_array_elements(p_evidence) x
    ) <> pg_catalog.jsonb_array_length(p_evidence)
       or (
        select count(distinct (x.value->>'block_index')::integer)
        from pg_catalog.jsonb_array_elements(p_evidence) x
    ) <> pg_catalog.jsonb_array_length(p_evidence)
    then
        raise exception 'duplicate evidence identity or block index';
    end if;

    -- One transaction: deleting old evidence cascades its old links/embeddings,
    -- then exact evidence and current-version links are rebuilt together.
    delete from public.mls_evidence_blocks
    where source_id = p_source_id;

    insert into public.mls_evidence_blocks(
        evidence_id, source_id, structure_node_id, block_index, page_index,
        page_label, content_type, text, asset_ref, bbox, parser,
        parser_version, content_sha256
    )
    select
        x.evidence_id,
        p_source_id,
        x.structure_node_id,
        x.block_index,
        x.page_index,
        x.page_label,
        x.content_type,
        x.text,
        x.asset_ref,
        x.bbox,
        x.parser,
        x.parser_version,
        x.content_sha256
    from pg_catalog.jsonb_to_recordset(p_evidence) as x(
        evidence_id text,
        structure_node_id text,
        block_index integer,
        page_index integer,
        page_label text,
        content_type text,
        text text,
        asset_ref text,
        bbox jsonb,
        parser text,
        parser_version text,
        content_sha256 text
    );
    get diagnostics v_evidence_count = row_count;

    insert into public.mls_source_map_evidence_links(
        logical_source_id, staging_version, node_id, evidence_id, source_id,
        source_map_version, method, confidence, status, anchor_context,
        compiler_version
    )
    select
        p_logical_source_id,
        p_staging_version,
        x.node_id,
        x.evidence_id,
        p_source_id,
        p_source_map_version,
        x.method,
        x.confidence,
        'promoted',
        coalesce(x.anchor_context, '{}'::jsonb),
        p_compiler_version
    from pg_catalog.jsonb_to_recordset(p_links) as x(
        node_id text,
        evidence_id text,
        method text,
        confidence double precision,
        anchor_context jsonb
    );
    get diagnostics v_link_count = row_count;

    if v_evidence_count <> pg_catalog.jsonb_array_length(p_evidence)
       or v_link_count <> pg_catalog.jsonb_array_length(p_links)
    then
        raise exception 'partial evidence or link insertion';
    end if;

    if p_migration_state = 'complete' then
        if pg_catalog.jsonb_array_length(p_unresolved_node_ids) <> 0 then
            raise exception 'complete evidence migration cannot have unresolved nodes';
        end if;
        if exists (
            select 1
            from public.mls_source_map_staging st
            cross join lateral pg_catalog.jsonb_array_elements(st.proposal) n
            where st.logical_source_id = p_logical_source_id
              and st.staging_version = p_staging_version
              and n.value->>'kind' <> 'book'
              and nullif(n.value->>'source_id','') is not null
              and not exists (
                  select 1
                  from public.mls_source_map_evidence_links l
                  where l.logical_source_id = p_logical_source_id
                    and l.staging_version = p_staging_version
                    and l.node_id = n.value->>'node_id'
                    and l.source_id = n.value->>'source_id'
                    and l.status = 'promoted'
              )
        ) then
            raise exception 'complete evidence migration has uncovered Source Map nodes';
        end if;
    end if;

    insert into public.mls_source_map_evidence_status(
        logical_source_id, staging_version, source_map_version, state,
        legacy_fallback_disabled, source_manifest, evidence_blocks,
        promoted_links, unresolved_node_ids, compiler_version, updated_at
    ) values (
        p_logical_source_id, p_staging_version, p_source_map_version,
        p_migration_state, true, p_source_manifest,
        (
            select count(distinct evidence_id)
            from public.mls_source_map_evidence_links
            where logical_source_id = p_logical_source_id
              and staging_version = p_staging_version
              and status = 'promoted'
        ),
        (
            select count(*)
            from public.mls_source_map_evidence_links
            where logical_source_id = p_logical_source_id
              and staging_version = p_staging_version
              and status = 'promoted'
        ),
        p_unresolved_node_ids, p_compiler_version, now()
    )
    on conflict (logical_source_id, staging_version) do update set
        source_map_version = excluded.source_map_version,
        state = excluded.state,
        legacy_fallback_disabled = true,
        source_manifest =
            public.mls_source_map_evidence_status.source_manifest
            || excluded.source_manifest,
        evidence_blocks = excluded.evidence_blocks,
        promoted_links = excluded.promoted_links,
        unresolved_node_ids = excluded.unresolved_node_ids,
        compiler_version = excluded.compiler_version,
        updated_at = excluded.updated_at;

    update public.mls_source_map_evidence_status
    set state = 'stale', updated_at = now()
    where logical_source_id = p_logical_source_id
      and staging_version <> p_staging_version
      and state <> 'stale';

    return pg_catalog.jsonb_build_object(
        'evidence_blocks', v_evidence_count,
        'links', v_link_count,
        'state', p_migration_state,
        'staging_version', p_staging_version,
        'source_map_version', p_source_map_version
    );
end;
$$;

alter table public.mls_source_map_evidence_status enable row level security;
revoke all on table public.mls_source_map_evidence_status from anon, authenticated;
grant all on table public.mls_source_map_evidence_status to service_role;

revoke all on function public.mls_validate_source_map_evidence_link()
    from public, anon, authenticated;
revoke all on function public.mls_mark_source_map_evidence_stale()
    from public, anon, authenticated;
revoke all on function public.mls_commit_source_map_evidence(
    text,bigint,bigint,text,text,jsonb,jsonb,text,jsonb,text,jsonb
) from public, anon, authenticated;
grant execute on function public.mls_commit_source_map_evidence(
    text,bigint,bigint,text,text,jsonb,jsonb,text,jsonb,text,jsonb
) to service_role;

comment on table public.mls_source_map_evidence_status is
    'Per-book immutable-staging evidence migration gate. Once present with fallback disabled, HỌC90 never silently returns to legacy structure evidence.';
