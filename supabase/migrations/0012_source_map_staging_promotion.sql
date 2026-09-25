-- Source Map v0.10.3: source topology, immutable staging, and transactional promotion.
-- No corpus rows are imported by this migration.

alter table public.mls_source_map_nodes
    drop constraint mls_source_map_nodes_kind_check;
alter table public.mls_source_map_nodes
    add constraint mls_source_map_nodes_kind_check check (
        kind in ('book', 'part', 'unit', 'chapter', 'section', 'subsection', 'other')
    );
alter table public.mls_source_map_nodes alter column learning_value drop not null;

alter table public.mls_logical_sources
    add column source_map_version bigint not null default 0,
    add column promoted_staging_version bigint,
    add column promoted_certificate_sha256 text;

create table public.mls_source_map_staging (
    logical_source_id text not null
        references public.mls_logical_sources(logical_source_id),
    staging_version bigint not null check (staging_version > 0),
    proposal jsonb not null check (jsonb_typeof(proposal) = 'array'),
    toc_denominator integer check (toc_denominator > 0),
    extraction_version text,
    source_manifest jsonb not null default '{}'::jsonb
        check (jsonb_typeof(source_manifest) = 'object'),
    audit_metadata jsonb not null default '{}'::jsonb
        check (jsonb_typeof(audit_metadata) = 'object'),
    payload_sha256 text not null,
    created_at timestamptz not null default now(),
    primary key (logical_source_id, staging_version)
);

create table public.mls_source_map_certificates (
    logical_source_id text not null,
    staging_version bigint not null,
    staging_sha256 text not null,
    certificate_sha256 text not null,
    toc_denominator integer not null check (toc_denominator > 0),
    audit_metadata jsonb not null,
    certified_at timestamptz not null default now(),
    primary key (logical_source_id, staging_version),
    unique (certificate_sha256),
    foreign key (logical_source_id, staging_version)
        references public.mls_source_map_staging(logical_source_id, staging_version)
);

-- Staging and certificates are append-only. Corrections create a new version.
create function public.mls_lock_source_map_artifact()
returns trigger language plpgsql security invoker
set search_path = ''
as $$
begin
    raise exception 'Source Map staging/certificates are immutable; insert a new version';
end;
$$;

create function public.mls_digest_staging_proposal()
returns trigger language plpgsql security invoker
set search_path = ''
as $$
begin
    new.payload_sha256 :=
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(new.proposal::text, 'UTF8')), 'hex');
    return new;
end;
$$;

create trigger mls_staging_digest_before_insert
before insert on public.mls_source_map_staging
for each row execute function public.mls_digest_staging_proposal();
create trigger mls_staging_immutable
before update or delete on public.mls_source_map_staging
for each row execute function public.mls_lock_source_map_artifact();
create trigger mls_certificate_immutable
before update or delete on public.mls_source_map_certificates
for each row execute function public.mls_lock_source_map_artifact();

-- The certificate is an audit attestation, not a source-discovery engine.
-- It verifies the stated denominator against the staged required identities
-- and requires a recorded, human-reviewable TOC/body reconciliation artifact.
create function public.mls_validate_source_map_stage(
    p_logical_source_id text, p_staging_version bigint
) returns text language plpgsql security invoker
set search_path = ''
as $$
declare
    s public.mls_source_map_staging%rowtype;
    v_total integer;
    v_required integer;
begin
    select * into s from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id
      and staging_version = p_staging_version;
    if not found then raise exception 'staging version not found'; end if;
    if s.toc_denominator is null
       or nullif(s.extraction_version, '') is null
       or s.audit_metadata->>'scope' is distinct from 'full_book'
       or nullif(s.audit_metadata->>'reviewer_id', '') is null
       or nullif(s.audit_metadata->>'qa_run_id', '') is null
       or nullif(s.audit_metadata->>'toc_reconciliation_sha256', '') is null
       or pg_catalog.jsonb_typeof(s.audit_metadata->'toc_evidence') <> 'object'
       or nullif(s.audit_metadata->'toc_evidence'->>'source_id','') is null
       or nullif(s.audit_metadata->'toc_evidence'->>'locator','') is null
       or nullif(s.audit_metadata->'toc_evidence'->>'source_sha256','') is null
       or s.audit_metadata->>'required_review_required' is distinct from '0'
       or s.audit_metadata->>'required_source_gap' is distinct from '0'
       or s.audit_metadata->>'unclassified_observations' is distinct from '0'
       or s.audit_metadata->'qa' is distinct from
          '{"toc_coverage_valid":true,"hierarchy_valid":true,"locator_qa_passed":true,"fingerprint_valid":true,"extraction_valid":true,"staging_qa_passed":true}'::jsonb
    then raise exception 'missing full-book TOC or QA attestation'; end if;
    if not exists (
        select 1 from public.mls_sources p
        where p.source_id = s.audit_metadata->'toc_evidence'->>'source_id'
          and p.logical_source_id = p_logical_source_id
          and p.content_sha256 is not null
          and p.content_sha256 =
              s.audit_metadata->'toc_evidence'->>'source_sha256'
    ) then raise exception 'TOC evidence source fingerprint mismatch'; end if;
    if pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(s.proposal::text, 'UTF8')), 'hex')
       <> s.payload_sha256
    then raise exception 'staging digest mismatch'; end if;

    select count(*), count(*) filter (
        where n.value->>'kind' <> 'book'
          and n.value->>'required' = 'true'
    ) into v_total, v_required
    from pg_catalog.jsonb_array_elements(s.proposal) n;
    if v_total < 2 or v_required <> s.toc_denominator
       or (select count(distinct n.value->>'node_id')
           from pg_catalog.jsonb_array_elements(s.proposal) n) <> v_total
       or (select count(distinct (n.value->>'order_index')::integer)
           from pg_catalog.jsonb_array_elements(s.proposal) n) <> v_total
    then raise exception 'staged node identities do not match TOC denominator'; end if;

    if (select count(*) from pg_catalog.jsonb_array_elements(s.proposal) n
        where n.value->>'kind' = 'book'
          and n.value->>'parent_id' is null
          and n.value->>'depth' = '0') <> 1
       or (select count(*) from pg_catalog.jsonb_array_elements(s.proposal) n
           where n.value->>'kind' = 'book') <> 1
       or exists (
        select 1 from pg_catalog.jsonb_array_elements(s.proposal) n
        where pg_catalog.jsonb_typeof(n.value) <> 'object'
           or nullif(n.value->>'node_id','') is null
           or nullif(n.value->>'title','') is null
           or n.value->>'kind' is null
           or n.value->>'kind' not in
               ('book','part','unit','chapter','section','subsection','other')
           or n.value->>'status' is distinct from 'verified'
           or n.value->>'required' is distinct from 'true'
           or n.value->>'depth' is null
           or n.value->>'depth' !~ '^[0-9]+$'
           or n.value->>'order_index' is null
           or n.value->>'order_index' !~ '^[0-9]+$'
           or pg_catalog.jsonb_typeof(n.value->'issues') not in ('array')
               and n.value->'issues' is not null
           or (pg_catalog.jsonb_typeof(n.value->'issues') = 'array'
               and pg_catalog.jsonb_array_length(n.value->'issues') > 0)
           or (n.value->>'learning_value' is not null
               and n.value->>'learning_value' not in
                   ('core_mastery','supporting','reference_only',
                    'current_clinical_check'))
           or (n.value->>'learning_value' = 'current_clinical_check'
               and n.value->>'freshness_required' is distinct from 'true')
           or (n.value->>'kind' <> 'book'
               and nullif(n.value->>'parent_id','') is null)
       )
    then raise exception 'unresolved or invalid staged hierarchy'; end if;

    if exists (
        select 1 from pg_catalog.jsonb_array_elements(s.proposal) n
        left join pg_catalog.jsonb_array_elements(s.proposal) parent
          on parent.value->>'node_id' = n.value->>'parent_id'
        where n.value->>'kind' <> 'book'
          and (parent.value is null
            or (n.value->>'depth')::int <> (parent.value->>'depth')::int + 1
            or (n.value->>'order_index')::int <= (parent.value->>'order_index')::int
            or case n.value->>'kind'
                when 'part' then parent.value->>'kind' <> 'book'
                when 'unit' then parent.value->>'kind' <> 'book'
                when 'chapter' then parent.value->>'kind' not in ('book','part','unit')
                when 'section' then parent.value->>'kind' <> 'chapter'
                when 'subsection' then parent.value->>'kind' <> 'section'
                else false end)
    ) then raise exception 'invalid staged parent/depth/order topology'; end if;

    if exists (
        select 1 from pg_catalog.jsonb_array_elements(s.proposal) n
        left join public.mls_sources p on p.source_id = n.value->>'source_id'
        where n.value->>'kind' <> 'book'
          and (p.source_id is null or p.logical_source_id <> p_logical_source_id
            or p.content_sha256 is null
            or p.content_sha256 is distinct from n.value->>'source_sha256'
            or s.source_manifest->(n.value->>'source_id')->>'source_sha256'
                is distinct from p.content_sha256
            or nullif(n.value->>'extraction_sha256','') is null
            or n.value->>'extraction_version' is distinct from s.extraction_version
            or s.source_manifest->(n.value->>'source_id')->>'extraction_sha256'
                is distinct from n.value->>'extraction_sha256'
            or n.value->>'locator_kind' is null
            or n.value->>'locator_kind' not in ('point','verified_range')
            or pg_catalog.jsonb_typeof(n.value->'source_anchor') <> 'object'
            or n.value->'source_anchor' = '{}'::jsonb
            or (n.value->>'locator_kind' = 'point'
                and (n.value->>'page_end' is not null
                    or (n.value->>'page_start' is not null
                        and (n.value->>'page_start' !~ '^[1-9][0-9]*$'))
                    or n.value->'source_anchor'->>'scope'
                        is distinct from 'heading_point_not_section_range'))
            or (n.value->>'locator_kind' = 'verified_range'
                and (n.value->>'page_start' is null
                  or n.value->>'page_end' is null
                  or n.value->>'page_start' !~ '^[1-9][0-9]*$'
                  or n.value->>'page_end' !~ '^[1-9][0-9]*$'
                  or (n.value->>'page_end')::int < (n.value->>'page_start')::int
                  or n.value->'source_anchor'->>'scope'
                     is distinct from 'verified_section_range'))
            or (n.value->>'locator_kind' = 'point'
                and n.value->>'page_start' is null
                and n.value->'source_anchor'->>'char_start' is null))
    ) then raise exception 'physical binding, fingerprint or locator QA invalid'; end if;
    return s.payload_sha256;
end;
$$;

create function public.mls_certify_source_map(
    p_logical_source_id text, p_staging_version bigint,
    p_expected_staging_sha256 text
) returns text language plpgsql security invoker
set search_path = ''
as $$
declare
    s public.mls_source_map_staging%rowtype;
    v_sha text;
    v_certificate text;
begin
    if p_staging_version is distinct from (
        select max(staging_version) from public.mls_source_map_staging
        where logical_source_id = p_logical_source_id
    ) then raise exception 'stale staging version'; end if;
    v_sha := public.mls_validate_source_map_stage(p_logical_source_id, p_staging_version);
    if v_sha <> p_expected_staging_sha256 then
        raise exception 'stale staging digest';
    end if;
    select * into s from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id and staging_version = p_staging_version;
    v_certificate := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
        p_logical_source_id || ':' || p_staging_version::text || ':' ||
        v_sha || ':' || s.audit_metadata::text, 'UTF8')), 'hex');
    insert into public.mls_source_map_certificates(
        logical_source_id, staging_version, staging_sha256, certificate_sha256,
        toc_denominator, audit_metadata
    ) values (
        p_logical_source_id, p_staging_version, v_sha, v_certificate,
        s.toc_denominator, s.audit_metadata
    );
    return v_certificate;
end;
$$;

create function public.mls_promote_source_map(
    p_logical_source_id text, p_staging_version bigint,
    p_certificate_sha256 text, p_expected_version bigint
) returns bigint language plpgsql security invoker
set search_path = ''
as $$
declare
    current_book public.mls_logical_sources%rowtype;
    s public.mls_source_map_staging%rowtype;
    cert public.mls_source_map_certificates%rowtype;
    v_count integer;
begin
    select * into current_book from public.mls_logical_sources
    where logical_source_id = p_logical_source_id for update;
    if not found then raise exception 'logical source not found'; end if;
    if current_book.source_map_version <> p_expected_version
    then raise exception 'stale expected_version'; end if;
    if p_staging_version <> (
        select max(staging_version) from public.mls_source_map_staging
        where logical_source_id = p_logical_source_id
    ) then raise exception 'stale staging version'; end if;
    select * into s from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id and staging_version = p_staging_version;
    select * into cert from public.mls_source_map_certificates
    where logical_source_id = p_logical_source_id and staging_version = p_staging_version;
    if cert.certificate_sha256 is null
       or cert.certificate_sha256 <> p_certificate_sha256
       or cert.staging_sha256 <> s.payload_sha256
       or cert.toc_denominator <> s.toc_denominator
       or cert.audit_metadata <> s.audit_metadata
       or cert.certificate_sha256 <> pg_catalog.encode(pg_catalog.sha256(
           pg_catalog.convert_to(p_logical_source_id || ':' ||
               p_staging_version::text || ':' || s.payload_sha256 || ':' ||
               s.audit_metadata::text, 'UTF8')), 'hex')
       or public.mls_validate_source_map_stage(p_logical_source_id, p_staging_version)
           <> s.payload_sha256
    then raise exception 'invalid or stale Source Map certificate'; end if;

    delete from public.mls_source_map_nodes
    where logical_source_id = p_logical_source_id;
    insert into public.mls_source_map_nodes (
        logical_source_id, node_id, parent_id, source_id, kind, title, depth,
        order_index, page_start, page_end, source_anchor, learning_value,
        freshness_required
    )
    select p_logical_source_id, n.value->>'node_id', n.value->>'parent_id',
           n.value->>'source_id', n.value->>'kind', n.value->>'title',
           (n.value->>'depth')::integer, (n.value->>'order_index')::integer,
           (n.value->>'page_start')::integer, (n.value->>'page_end')::integer,
           coalesce(n.value->'source_anchor', '{}'::jsonb),
           n.value->>'learning_value',
           coalesce((n.value->>'freshness_required')::boolean, false)
    from pg_catalog.jsonb_array_elements(s.proposal) n
    order by (n.value->>'order_index')::integer;
    get diagnostics v_count = row_count;
    if v_count <> pg_catalog.jsonb_array_length(s.proposal)
    then raise exception 'partial Source Map insertion'; end if;
    update public.mls_logical_sources set
        source_map_version = source_map_version + 1,
        promoted_staging_version = p_staging_version,
        promoted_certificate_sha256 = p_certificate_sha256,
        updated_at = now()
    where logical_source_id = p_logical_source_id;
    return p_expected_version + 1;
end;
$$;

create function public.mls_runtime_matches_staging(
    p_logical_source_id text, p_staging_version bigint
) returns boolean language sql stable security invoker
set search_path = ''
as $$
    select exists (
        select 1 from public.mls_source_map_staging s
        where s.logical_source_id = p_logical_source_id
          and s.staging_version = p_staging_version
          and (select count(*) from public.mls_source_map_nodes m
               where m.logical_source_id = p_logical_source_id)
                = pg_catalog.jsonb_array_length(s.proposal)
          and not exists (
              select 1 from pg_catalog.jsonb_array_elements(s.proposal) n
              left join public.mls_source_map_nodes m
                on m.logical_source_id = p_logical_source_id
               and m.node_id = n.value->>'node_id'
              where m.node_id is null
                 or m.parent_id is distinct from n.value->>'parent_id'
                 or m.source_id is distinct from n.value->>'source_id'
                 or m.kind is distinct from n.value->>'kind'
                 or m.title is distinct from n.value->>'title'
                 or m.depth is distinct from (n.value->>'depth')::integer
                 or m.order_index is distinct from (n.value->>'order_index')::integer
                 or m.page_start is distinct from (n.value->>'page_start')::integer
                 or m.page_end is distinct from (n.value->>'page_end')::integer
                 or m.source_anchor is distinct from
                    coalesce(n.value->'source_anchor', '{}'::jsonb)
          )
    );
$$;

create function public.mls_source_map_readiness(p_logical_source_id text)
returns jsonb language plpgsql security invoker
set search_path = ''
as $$
declare
    b public.mls_logical_sources%rowtype;
    s public.mls_source_map_staging%rowtype;
    c public.mls_source_map_certificates%rowtype;
    v_structural text := 'unmapped';
    v_audited text := 'uncertified';
begin
    select * into b from public.mls_logical_sources
    where logical_source_id = p_logical_source_id;
    if not found then raise exception 'logical source not found'; end if;
    if exists (select 1 from public.mls_source_map_nodes
               where logical_source_id = p_logical_source_id and kind = 'subsection'
                 and source_id is not null and source_anchor <> '{}'::jsonb)
    then v_structural := 'deep_anchored';
    elsif exists (select 1 from public.mls_source_map_nodes
                  where logical_source_id = p_logical_source_id and kind = 'section'
                    and source_id is not null and source_anchor <> '{}'::jsonb)
    then v_structural := 'anchored';
    elsif exists (select 1 from public.mls_source_map_nodes
                  where logical_source_id = p_logical_source_id
                    and kind <> 'book')
    then v_structural := 'mapped'; end if;
    select * into s from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id
    order by staging_version desc limit 1;
    if found then
        if exists (select 1 from pg_catalog.jsonb_array_elements(s.proposal) n
                   where n.value->>'required' = 'true'
                     and n.value->>'status' = 'source_gap')
        then v_audited := 'source_gap';
        elsif exists (select 1 from pg_catalog.jsonb_array_elements(s.proposal) n
                      where n.value->>'required' = 'true'
                        and n.value->>'status' <> 'verified')
        then v_audited := 'review_required';
        else
            select * into c from public.mls_source_map_certificates
            where logical_source_id = p_logical_source_id
              and staging_version = s.staging_version;
            if found and c.staging_sha256 = s.payload_sha256 then
                v_audited := 'certified';
                if b.promoted_staging_version = s.staging_version
                   and b.promoted_certificate_sha256 = c.certificate_sha256
                then
                    begin
                        if public.mls_validate_source_map_stage(
                            p_logical_source_id, s.staging_version) = s.payload_sha256
                           and public.mls_runtime_matches_staging(
                               p_logical_source_id, s.staging_version)
                        then v_audited := 'ready_for_hoc90'; end if;
                    exception when others then
                        -- A source fingerprint or extraction can become stale.
                        v_audited := 'source_gap';
                    end;
                end if;
            end if;
        end if;
    end if;
    return pg_catalog.jsonb_build_object(
        'logical_source_id', p_logical_source_id,
        'historical_source_map_state', b.source_map_state,
        'structural_state', v_structural,
        'audited_state', v_audited,
        'ready_for_hoc90', v_audited = 'ready_for_hoc90',
        'current_version', b.source_map_version,
        'staging_version', s.staging_version,
        'promoted_staging_version', b.promoted_staging_version
    );
end;
$$;

alter table public.mls_source_map_staging enable row level security;
alter table public.mls_source_map_certificates enable row level security;
revoke all on public.mls_source_map_staging, public.mls_source_map_certificates
    from anon, authenticated;
grant all on public.mls_source_map_staging, public.mls_source_map_certificates
    to service_role;
revoke all on function public.mls_lock_source_map_artifact() from public, anon, authenticated;
revoke all on function public.mls_digest_staging_proposal() from public, anon, authenticated;
revoke all on function public.mls_validate_source_map_stage(text,bigint)
    from public, anon, authenticated;
revoke all on function public.mls_certify_source_map(text,bigint,text)
    from public, anon, authenticated;
revoke all on function public.mls_promote_source_map(text,bigint,text,bigint)
    from public, anon, authenticated;
revoke all on function public.mls_runtime_matches_staging(text,bigint)
    from public, anon, authenticated;
revoke all on function public.mls_source_map_readiness(text)
    from public, anon, authenticated;
grant execute on function public.mls_validate_source_map_stage(text,bigint),
    public.mls_certify_source_map(text,bigint,text),
    public.mls_promote_source_map(text,bigint,text,bigint),
    public.mls_runtime_matches_staging(text,bigint),
    public.mls_source_map_readiness(text) to service_role;
