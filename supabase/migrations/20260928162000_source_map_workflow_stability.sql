-- Stabilize Source Map orchestration and publication boundaries.
-- No textbook/source content, Source Map staging rows, certificates, runtime nodes,
-- curriculum, KG, or learner state are created by this migration.

create table if not exists public.mls_source_map_work_leases (
    work_key text primary key,
    logical_source_id text not null
        references public.mls_logical_sources(logical_source_id),
    batch_id text not null,
    owner_id text not null,
    scope_sha256 text not null check (scope_sha256 ~ '^[0-9a-f]{64}$'),
    manifest_sha256 text not null check (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    lease_token uuid not null,
    status text not null check (status in ('active','released','completed')),
    claimed_at timestamptz not null,
    lease_expires_at timestamptz not null,
    updated_at timestamptz not null,
    completed_at timestamptz,
    artifact_ref text,
    artifact_sha256 text check (
        artifact_sha256 is null or artifact_sha256 ~ '^[0-9a-f]{64}$'
    )
);

alter table public.mls_source_map_work_leases enable row level security;
revoke all on public.mls_source_map_work_leases from anon, authenticated;
revoke insert, update, delete on public.mls_source_map_work_leases from service_role;
grant select on public.mls_source_map_work_leases to service_role;

create or replace function public.mls_claim_source_map_work(
    p_work_key text,
    p_logical_source_id text,
    p_batch_id text,
    p_owner_id text,
    p_scope_sha256 text,
    p_manifest_sha256 text,
    p_lease_seconds integer
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_lease public.mls_source_map_work_leases%rowtype;
    v_now timestamptz := pg_catalog.clock_timestamp();
    v_token uuid := pg_catalog.gen_random_uuid();
begin
    if nullif(pg_catalog.btrim(p_work_key), '') is null
       or nullif(pg_catalog.btrim(p_batch_id), '') is null
       or nullif(pg_catalog.btrim(p_owner_id), '') is null
       or p_scope_sha256 !~ '^[0-9a-f]{64}$'
       or p_manifest_sha256 !~ '^[0-9a-f]{64}$'
       or p_lease_seconds < 60
       or p_lease_seconds > 21600
    then
        raise exception 'invalid Source Map work claim';
    end if;

    if not exists (
        select 1 from public.mls_logical_sources
        where logical_source_id = p_logical_source_id
    ) then
        raise exception 'logical source not found';
    end if;

    -- Serialize claim attempts for the exact durable work key.
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_work_key, 0)
    );

    select * into current_lease
    from public.mls_source_map_work_leases
    where work_key = p_work_key
    for update;

    if found and current_lease.status = 'completed' then
        raise exception 'Source Map work key already completed';
    end if;
    if found
       and current_lease.status = 'active'
       and current_lease.lease_expires_at > v_now
    then
        raise exception 'Source Map work key already has an active lease';
    end if;

    insert into public.mls_source_map_work_leases (
        work_key, logical_source_id, batch_id, owner_id,
        scope_sha256, manifest_sha256, lease_token, status,
        claimed_at, lease_expires_at, updated_at,
        completed_at, artifact_ref, artifact_sha256
    ) values (
        p_work_key, p_logical_source_id, p_batch_id, p_owner_id,
        p_scope_sha256, p_manifest_sha256, v_token, 'active',
        v_now, v_now + pg_catalog.make_interval(secs => p_lease_seconds),
        v_now, null, null, null
    )
    on conflict (work_key) do update set
        logical_source_id = excluded.logical_source_id,
        batch_id = excluded.batch_id,
        owner_id = excluded.owner_id,
        scope_sha256 = excluded.scope_sha256,
        manifest_sha256 = excluded.manifest_sha256,
        lease_token = excluded.lease_token,
        status = excluded.status,
        claimed_at = excluded.claimed_at,
        lease_expires_at = excluded.lease_expires_at,
        updated_at = excluded.updated_at,
        completed_at = null,
        artifact_ref = null,
        artifact_sha256 = null;

    return pg_catalog.jsonb_build_object(
        'work_key', p_work_key,
        'lease_token', v_token,
        'status', 'active',
        'lease_expires_at',
        v_now + pg_catalog.make_interval(secs => p_lease_seconds)
    );
end;
$$;

create or replace function public.mls_heartbeat_source_map_work(
    p_work_key text,
    p_lease_token uuid,
    p_lease_seconds integer
) returns timestamptz
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_expires timestamptz;
    v_now timestamptz := pg_catalog.clock_timestamp();
begin
    if p_lease_seconds < 60 or p_lease_seconds > 21600 then
        raise exception 'invalid Source Map lease duration';
    end if;
    update public.mls_source_map_work_leases
    set lease_expires_at =
            v_now + pg_catalog.make_interval(secs => p_lease_seconds),
        updated_at = v_now
    where work_key = p_work_key
      and lease_token = p_lease_token
      and status = 'active'
      and lease_expires_at > v_now
    returning lease_expires_at into v_expires;
    if v_expires is null then
        raise exception 'Source Map work lease is missing, expired, or not owned';
    end if;
    return v_expires;
end;
$$;

create or replace function public.mls_release_source_map_work(
    p_work_key text,
    p_lease_token uuid
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_count integer;
begin
    update public.mls_source_map_work_leases
    set status = 'released',
        lease_expires_at = pg_catalog.clock_timestamp(),
        updated_at = pg_catalog.clock_timestamp()
    where work_key = p_work_key
      and lease_token = p_lease_token
      and status = 'active';
    get diagnostics v_count = row_count;
    if v_count <> 1 then
        raise exception 'Source Map work lease is missing or not owned';
    end if;
    return true;
end;
$$;

create or replace function public.mls_complete_source_map_work(
    p_work_key text,
    p_lease_token uuid,
    p_artifact_ref text,
    p_artifact_sha256 text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_count integer;
    v_now timestamptz := pg_catalog.clock_timestamp();
begin
    if nullif(pg_catalog.btrim(p_artifact_ref), '') is null
       or p_artifact_sha256 !~ '^[0-9a-f]{64}$'
    then
        raise exception 'completed Source Map work requires artifact reference and SHA-256';
    end if;
    update public.mls_source_map_work_leases
    set status = 'completed',
        completed_at = v_now,
        lease_expires_at = v_now,
        updated_at = v_now,
        artifact_ref = p_artifact_ref,
        artifact_sha256 = p_artifact_sha256
    where work_key = p_work_key
      and lease_token = p_lease_token
      and status = 'active'
      and lease_expires_at > v_now;
    get diagnostics v_count = row_count;
    if v_count <> 1 then
        raise exception 'Source Map work lease is missing, expired, or not owned';
    end if;
    return true;
end;
$$;

revoke all on function public.mls_claim_source_map_work(
    text,text,text,text,text,text,integer
) from public, anon, authenticated;
revoke all on function public.mls_heartbeat_source_map_work(
    text,uuid,integer
) from public, anon, authenticated;
revoke all on function public.mls_release_source_map_work(
    text,uuid
) from public, anon, authenticated;
revoke all on function public.mls_complete_source_map_work(
    text,uuid,text,text
) from public, anon, authenticated;
grant execute on function public.mls_claim_source_map_work(
    text,text,text,text,text,text,integer
) to service_role;
grant execute on function public.mls_heartbeat_source_map_work(
    text,uuid,integer
) to service_role;
grant execute on function public.mls_release_source_map_work(
    text,uuid
) to service_role;
grant execute on function public.mls_complete_source_map_work(
    text,uuid,text,text
) to service_role;

-- Allocate immutable staging versions under a row lock. Callers state the
-- latest version they observed; stale/concurrent writers fail closed.
create or replace function public.mls_stage_source_map(
    p_logical_source_id text,
    p_expected_latest_staging_version bigint,
    p_proposal jsonb,
    p_toc_denominator integer,
    p_extraction_version text,
    p_source_manifest jsonb,
    p_audit_metadata jsonb
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_latest bigint;
    v_next bigint;
    v_sha text;
begin
    perform 1 from public.mls_logical_sources
    where logical_source_id = p_logical_source_id
    for update;
    if not found then raise exception 'logical source not found'; end if;

    select coalesce(max(staging_version), 0) into v_latest
    from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id;

    if p_expected_latest_staging_version is distinct from v_latest then
        raise exception 'stale expected staging version: expected %, live %',
            p_expected_latest_staging_version, v_latest;
    end if;

    v_next := v_latest + 1;
    insert into public.mls_source_map_staging (
        logical_source_id, staging_version, proposal, toc_denominator,
        extraction_version, source_manifest, audit_metadata, payload_sha256
    ) values (
        p_logical_source_id, v_next, p_proposal, p_toc_denominator,
        p_extraction_version, coalesce(p_source_manifest, '{}'::jsonb),
        coalesce(p_audit_metadata, '{}'::jsonb), 'trigger-computes-digest'
    );

    select payload_sha256 into v_sha
    from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id
      and staging_version = v_next;

    return pg_catalog.jsonb_build_object(
        'staging_version', v_next,
        'payload_sha256', v_sha
    );
end;
$$;

revoke all on function public.mls_stage_source_map(
    text,bigint,jsonb,integer,text,jsonb,jsonb
) from public, anon, authenticated;
grant execute on function public.mls_stage_source_map(
    text,bigint,jsonb,integer,text,jsonb,jsonb
) to service_role;

-- Force application writers through the version-guarded staging RPC.
revoke insert on public.mls_source_map_staging from service_role;

-- Runtime parity must cover every field that promotion materializes.
create or replace function public.mls_runtime_matches_staging(
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
                 or m.learning_value is distinct from n.value->>'learning_value'
                 or m.freshness_required is distinct from
                    coalesce((n.value->>'freshness_required')::boolean, false)
          )
    );
$$;

-- Runtime readiness is about the promoted immutable stage. A newer WIP draft
-- is reported separately and cannot make an otherwise valid runtime unready.
create or replace function public.mls_source_map_readiness(p_logical_source_id text)
returns jsonb language plpgsql security invoker
set search_path = ''
as $$
declare
    b public.mls_logical_sources%rowtype;
    latest_s public.mls_source_map_staging%rowtype;
    ready_s public.mls_source_map_staging%rowtype;
    latest_c public.mls_source_map_certificates%rowtype;
    ready_c public.mls_source_map_certificates%rowtype;
    v_structural text := 'unmapped';
    v_audited text := 'uncertified';
    v_latest_audited text := 'uncertified';
    v_latest_version bigint;
    v_readiness_version bigint;
begin
    select * into b from public.mls_logical_sources
    where logical_source_id = p_logical_source_id;
    if not found then raise exception 'logical source not found'; end if;

    if exists (
        select 1 from public.mls_source_map_nodes
        where logical_source_id = p_logical_source_id
          and kind = 'subsection'
          and source_id is not null
          and source_anchor <> '{}'::jsonb
    ) then
        v_structural := 'deep_anchored';
    elsif exists (
        select 1 from public.mls_source_map_nodes
        where logical_source_id = p_logical_source_id
          and kind = 'section'
          and source_id is not null
          and source_anchor <> '{}'::jsonb
    ) then
        v_structural := 'anchored';
    elsif exists (
        select 1 from public.mls_source_map_nodes
        where logical_source_id = p_logical_source_id
          and kind <> 'book'
    ) then
        v_structural := 'mapped';
    end if;

    select * into latest_s
    from public.mls_source_map_staging
    where logical_source_id = p_logical_source_id
    order by staging_version desc
    limit 1;

    if found then
        v_latest_version := latest_s.staging_version;
        if exists (
            select 1 from pg_catalog.jsonb_array_elements(latest_s.proposal) n
            where n.value->>'required' = 'true'
              and n.value->>'status' = 'source_gap'
        ) then
            v_latest_audited := 'source_gap';
        elsif exists (
            select 1 from pg_catalog.jsonb_array_elements(latest_s.proposal) n
            where n.value->>'required' = 'true'
              and n.value->>'status' <> 'verified'
        ) then
            v_latest_audited := 'review_required';
        else
            select * into latest_c
            from public.mls_source_map_certificates
            where logical_source_id = p_logical_source_id
              and staging_version = latest_s.staging_version;
            if found and latest_c.staging_sha256 = latest_s.payload_sha256 then
                v_latest_audited := 'certified';
            end if;
        end if;
    end if;

    if b.promoted_staging_version is not null then
        v_readiness_version := b.promoted_staging_version;
        select * into ready_s
        from public.mls_source_map_staging
        where logical_source_id = p_logical_source_id
          and staging_version = b.promoted_staging_version;

        if not found then
            v_audited := 'review_required';
        elsif exists (
            select 1 from pg_catalog.jsonb_array_elements(ready_s.proposal) n
            where n.value->>'required' = 'true'
              and n.value->>'status' = 'source_gap'
        ) then
            v_audited := 'source_gap';
        elsif exists (
            select 1 from pg_catalog.jsonb_array_elements(ready_s.proposal) n
            where n.value->>'required' = 'true'
              and n.value->>'status' <> 'verified'
        ) then
            v_audited := 'review_required';
        else
            select * into ready_c
            from public.mls_source_map_certificates
            where logical_source_id = p_logical_source_id
              and staging_version = ready_s.staging_version;

            if found
               and ready_c.staging_sha256 = ready_s.payload_sha256
               and b.promoted_certificate_sha256 = ready_c.certificate_sha256
            then
                v_audited := 'certified';
                begin
                    if public.mls_validate_source_map_stage(
                           p_logical_source_id, ready_s.staging_version
                       ) = ready_s.payload_sha256
                       and public.mls_runtime_matches_staging(
                           p_logical_source_id, ready_s.staging_version
                       )
                    then
                        v_audited := 'ready_for_hoc90';
                    end if;
                exception when others then
                    v_audited := 'source_gap';
                end;
            end if;
        end if;
    else
        v_readiness_version := v_latest_version;
        v_audited := v_latest_audited;
    end if;

    return pg_catalog.jsonb_build_object(
        'logical_source_id', p_logical_source_id,
        'historical_source_map_state', b.source_map_state,
        'structural_state', v_structural,
        'audited_state', v_audited,
        'ready_for_hoc90', v_audited = 'ready_for_hoc90',
        'current_version', b.source_map_version,
        'staging_version', v_latest_version,
        'latest_staging_version', v_latest_version,
        'latest_staging_audited_state', v_latest_audited,
        'readiness_staging_version', v_readiness_version,
        'promoted_staging_version', b.promoted_staging_version,
        'has_newer_unpromoted_staging',
            b.promoted_staging_version is not null
            and v_latest_version is not null
            and v_latest_version > b.promoted_staging_version
    );
end;
$$;

revoke all on function public.mls_runtime_matches_staging(text,bigint)
    from public, anon, authenticated;
revoke all on function public.mls_source_map_readiness(text)
    from public, anon, authenticated;
grant execute on function public.mls_runtime_matches_staging(text,bigint)
    to service_role;
grant execute on function public.mls_source_map_readiness(text)
    to service_role;
