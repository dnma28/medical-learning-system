-- Run inside BEGIN ... ROLLBACK after all Source Map migrations.
-- Synthetic rows only; this contract test never targets a real textbook.
do $test$
declare
    book text := '__toc_identity_point_contract__';
    physical text := '__toc_identity_point_physical__';
    source_hash text := repeat('a',64);
    extraction_hash text := repeat('b',64);
    qa jsonb := '{"scope":"full_book","reviewer_id":"contract-reviewer",
        "qa_run_id":"toc-identity-point-contract",
        "required_review_required":0,"required_source_gap":0,
        "unclassified_observations":0,
        "toc_reconciliation_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "toc_evidence":{"source_id":"__toc_identity_point_physical__",
            "locator":"publisher Contents physical PDF page 5",
            "source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        "qa":{"toc_coverage_valid":true,"hierarchy_valid":true,
            "locator_qa_passed":true,"fingerprint_valid":true,
            "extraction_valid":true,"staging_qa_passed":true}}'::jsonb;
    manifest jsonb;
    proposal jsonb;
    digest text;
    failed boolean;
begin
    insert into public.mls_logical_sources(
        logical_source_id,title,kind,identity_status,source_map_state
    ) values (
        book,'Synthetic TOC point fixture','textbook','verify_from_source','unmapped'
    );
    insert into public.mls_sources(
        source_id,logical_source_id,provider,provider_file_id,title,mime_type,
        modified_time,kind,status,content_sha256,metadata_fingerprint
    ) values (
        physical,book,'google_drive','synthetic-only','Synthetic source',
        'application/pdf',now(),'textbook','new',source_hash,repeat('d',64)
    );
    manifest := pg_catalog.jsonb_build_object(
        physical, pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash
        )
    );

    -- Positive: exact publisher Contents identity point.
    proposal := pg_catalog.jsonb_build_array(
        pg_catalog.jsonb_build_object(
            'node_id','book','title','Synthetic book','kind','book',
            'depth',0,'order_index',0,'required',true,'status','verified'
        ),
        pg_catalog.jsonb_build_object(
            'node_id','part-i','title','PART I - SYNTHETIC STRUCTURE',
            'parent_id','book','kind','part','depth',1,'order_index',1,
            'required',true,'status','verified','source_id',physical,
            'source_sha256',source_hash,'extraction_sha256',extraction_hash,
            'extraction_version','test-parser-1','locator_kind','point',
            'page_start',5,
            'source_anchor',pg_catalog.jsonb_build_object(
                'scope','toc_identity_point_not_section_range',
                'publisher_surface','contents',
                'identity_text','PART I - SYNTHETIC STRUCTURE',
                'body_heading_absent',true,
                'pdf_page',5
            )
        )
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,1,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    select payload_sha256 into digest from public.mls_source_map_staging
    where logical_source_id=book and staging_version=1;
    if public.mls_validate_source_map_stage(book,1) <> digest then
        raise exception 'exact publisher TOC identity point did not validate';
    end if;

    -- Regression: the existing exact body-heading point remains valid unchanged.
    proposal := pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
            proposal,'{1,source_anchor}',
            '{"scope":"heading_point_not_section_range","pdf_page":5}'::jsonb
        ),
        '{1,title}','"Exact body heading"'
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,2,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    perform public.mls_validate_source_map_stage(book,2);

    -- Negative: arbitrary/fuzzy point scope is not accepted.
    proposal := pg_catalog.jsonb_set(
        proposal,'{1,source_anchor,scope}','"fuzzy_toc_point"'::jsonb
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,3,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    failed := false;
    begin perform public.mls_validate_source_map_stage(book,3);
    exception when others then failed := true; end;
    if not failed then raise exception 'arbitrary/fuzzy point scope was accepted'; end if;

    -- Negative: the TOC semantic remains point-only and cannot claim page_end.
    proposal := pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
            pg_catalog.jsonb_set(
                proposal,'{1,source_anchor,scope}',
                '"toc_identity_point_not_section_range"'::jsonb
            ),
            '{1,title}','"PART I - SYNTHETIC STRUCTURE"'
        ),
        '{1,page_end}','6'::jsonb
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,4,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    failed := false;
    begin perform public.mls_validate_source_map_stage(book,4);
    exception when others then failed := true; end;
    if not failed then raise exception 'TOC point with page_end was accepted'; end if;

    -- Negative: exact identity text is mandatory; semantic/fuzzy substitution fails.
    proposal := proposal #- '{1,page_end}';
    proposal := pg_catalog.jsonb_set(
        proposal,'{1,source_anchor,identity_text}','"Similar Part I label"'::jsonb
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,5,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    failed := false;
    begin perform public.mls_validate_source_map_stage(book,5);
    exception when others then failed := true; end;
    if not failed then raise exception 'non-exact TOC identity text was accepted'; end if;

    -- Negative: exact physical source fingerprint remains mandatory.
    proposal := pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
            proposal,'{1,source_anchor,identity_text}',
            '"PART I - SYNTHETIC STRUCTURE"'::jsonb
        ),
        '{1,source_sha256}',to_jsonb(repeat('e',64))
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,6,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    failed := false;
    begin perform public.mls_validate_source_map_stage(book,6);
    exception when others then failed := true; end;
    if not failed then raise exception 'TOC point with mismatched source fingerprint was accepted'; end if;

    -- Negative: the TOC semantic is only legal when no standalone body heading exists.
    proposal := pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
            proposal,'{1,source_sha256}',to_jsonb(source_hash)
        ),
        '{1,source_anchor,body_heading_absent}','false'::jsonb
    );
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (book,7,proposal,1,'test-parser-1',manifest,qa,'recomputed');
    failed := false;
    begin perform public.mls_validate_source_map_stage(book,7);
    exception when others then failed := true; end;
    if not failed then raise exception 'TOC point with a body heading was accepted'; end if;
end;
$test$;
