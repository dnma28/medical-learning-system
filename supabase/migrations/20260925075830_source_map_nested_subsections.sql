-- Preserve deeper source headings (e.g. Chapter > Section > Subsection > Subsection).
-- Forward-only validator adjustment; no Source Map rows are imported.
create or replace function public.mls_validate_source_map_stage(
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
                when 'subsection' then parent.value->>'kind' not in ('section','subsection')
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
