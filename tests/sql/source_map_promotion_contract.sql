-- Run only inside BEGIN ... ROLLBACK after migration 0013.
-- Synthetic source identifiers and rows are never committed.
do $test$
declare
    book text := '__source_map_contract_test__';
    physical text := '__source_map_contract_physical__';
    source_hash text := repeat('a',64);
    extraction_hash text := repeat('b',64);
    qa jsonb := '{"scope":"full_book","reviewer_id":"test-reviewer",
        "qa_run_id":"test-qa-run",
        "required_review_required":0,"required_source_gap":0,
        "unclassified_observations":0,
        "toc_reconciliation_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "toc_evidence":{"source_id":"__source_map_contract_physical__",
            "locator":"physical PDF page 1",
            "source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        "qa":{"toc_coverage_valid":true,"hierarchy_valid":true,
            "locator_qa_passed":true,"fingerprint_valid":true,
            "extraction_valid":true,"staging_qa_passed":true}}'::jsonb;
    proposal jsonb;
    digest1 text;
    digest2 text;
    certificate1 text;
    certificate2 text;
    failed boolean;
    readiness jsonb;
begin
    readiness := public.mls_source_map_readiness('kandel-principles-neural-science');
    if readiness->>'historical_source_map_state' <> 'deep_anchored'
       or readiness->>'structural_state' <> 'unmapped'
       or readiness->>'audited_state' <> 'uncertified'
       or readiness->>'ready_for_hoc90' <> 'false'
    then raise exception 'historical anchor label became audited readiness'; end if;
    insert into public.mls_logical_sources(
        logical_source_id,title,kind,identity_status,source_map_state
    ) values (book,'Synthetic integration fixture','textbook',
              'verify_from_source','unmapped');
    insert into public.mls_sources(
        source_id,logical_source_id,provider,provider_file_id,title,mime_type,
        modified_time,kind,status,content_sha256,metadata_fingerprint
    ) values (physical,book,'google_drive','synthetic-only',
              'Synthetic test pages','application/pdf',now(),'textbook',
              'new',source_hash,repeat('d',64));
    proposal := pg_catalog.jsonb_build_array(
        pg_catalog.jsonb_build_object(
            'node_id','book','title','Synthetic book','kind','book',
            'depth',0,'order_index',0,'required',true,'status','verified'),
        pg_catalog.jsonb_build_object(
            'node_id','chapter-v1','title','Synthetic chapter',
            'parent_id','book','kind','chapter','depth',1,'order_index',1,
            'required',true,'status','verified','source_id',physical,
            'source_sha256',source_hash,'extraction_sha256',extraction_hash,
            'extraction_version','test-parser-1','locator_kind','point',
            'page_start',1,
            'source_anchor',pg_catalog.jsonb_build_object(
                'scope','heading_point_not_section_range','pdf_page',1),
            'learning_value',null));
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,1,proposal,1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    select payload_sha256 into digest1 from public.mls_source_map_staging
    where logical_source_id=book and staging_version=1;
    certificate1 := public.mls_certify_source_map(book,1,digest1);
    if public.mls_promote_source_map(book,1,certificate1,0) <> 1 then
        raise exception 'successful promotion returned incorrect version';
    end if;
    readiness := public.mls_source_map_readiness(book);
    if readiness->>'audited_state' <> 'ready_for_hoc90'
       or (select count(*) from public.mls_source_map_nodes
           where logical_source_id=book) <> 2
    then raise exception 'promotion readback mismatch'; end if;
    update public.mls_source_map_nodes set title='tampered'
    where logical_source_id=book and node_id='chapter-v1';
    if public.mls_source_map_readiness(book)->>'ready_for_hoc90' <> 'false'
    then raise exception 'tampered runtime node reported READY'; end if;
    update public.mls_source_map_nodes set title='Synthetic chapter'
    where logical_source_id=book and node_id='chapter-v1';
    update public.mls_sources set content_sha256=repeat('e',64)
    where source_id=physical;
    if public.mls_source_map_readiness(book)->>'ready_for_hoc90' <> 'false'
    then raise exception 'changed physical fingerprint reported READY'; end if;
    update public.mls_sources set content_sha256=source_hash
    where source_id=physical;

    failed := false;
    begin
        update public.mls_source_map_staging set toc_denominator=2
        where logical_source_id=book and staging_version=1;
    exception when others then failed := true; end;
    if not failed then raise exception 'staging mutation was allowed'; end if;

    proposal := pg_catalog.jsonb_set(proposal,'{1,node_id}','"chapter-v2"');
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,2,proposal,1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    select payload_sha256 into digest2 from public.mls_source_map_staging
    where logical_source_id=book and staging_version=2;
    certificate2 := public.mls_certify_source_map(book,2,digest2);

    failed := false;
    begin perform public.mls_promote_source_map(book,2,certificate2,0);
    exception when others then failed := true; end;
    if not failed then raise exception 'wrong expected_version was accepted'; end if;
    failed := false;
    begin perform public.mls_promote_source_map(book,2,repeat('f',64),1);
    exception when others then failed := true; end;
    if not failed then raise exception 'invalid certificate was accepted'; end if;

    -- A trigger makes the second insert fail *after* the old rows were deleted.
    create function public.mls_test_mid_tx_failure() returns trigger
    language plpgsql as $failure$
    begin
        if new.logical_source_id='__source_map_contract_test__'
           and new.node_id='chapter-v2'
        then raise exception 'synthetic mid-transaction failure'; end if;
        return new;
    end; $failure$;
    create trigger mls_test_mid_tx_failure before insert
    on public.mls_source_map_nodes for each row
    execute function public.mls_test_mid_tx_failure();
    failed := false;
    begin perform public.mls_promote_source_map(book,2,certificate2,1);
    exception when others then failed := true; end;
    if not failed then raise exception 'mid-transaction failure was swallowed'; end if;
    if (select source_map_version from public.mls_logical_sources
        where logical_source_id=book) <> 1
       or (select count(*) from public.mls_source_map_nodes
           where logical_source_id=book and node_id='chapter-v1') <> 1
       or (select count(*) from public.mls_source_map_nodes
           where logical_source_id=book) <> 2
    then raise exception 'old map/version not restored after insertion failure'; end if;
    drop trigger mls_test_mid_tx_failure on public.mls_source_map_nodes;
    drop function public.mls_test_mid_tx_failure();

    -- A later draft makes the previously certified version stale.
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,3,proposal,1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin perform public.mls_promote_source_map(book,2,certificate2,1);
    exception when others then failed := true; end;
    if not failed then raise exception 'stale staging version was promoted'; end if;
    failed := false;
    begin perform public.mls_certify_source_map(book,2,digest2);
    exception when others then failed := true; end;
    if not failed then raise exception 'stale staging version was certified'; end if;

    -- QA failure must prevent a certificate even for complete-looking nodes.
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,4,proposal,1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        pg_catalog.jsonb_set(qa,'{qa,staging_qa_passed}','false'),
        'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,4,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=4));
    exception when others then failed := true; end;
    if not failed then raise exception 'QA failure was certified'; end if;

    -- A wrong parent or missing physical binding remains a draft, never a certificate.
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,5,pg_catalog.jsonb_set(proposal,'{1,parent_id}','"unknown-parent"'),
        1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,5,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=5));
    exception when others then failed := true; end;
    if not failed then raise exception 'invalid hierarchy was certified'; end if;
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,6,pg_catalog.jsonb_set(proposal,'{1,source_id}','null'::jsonb),
        1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,6,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=6));
    exception when others then failed := true; end;
    if not failed then raise exception 'unbound physical source was certified'; end if;

    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,7,pg_catalog.jsonb_set(proposal,'{1,order_index}','0'::jsonb),
        1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,7,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=7));
    exception when others then failed := true; end;
    if not failed then raise exception 'duplicate order was certified'; end if;

    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,8,pg_catalog.jsonb_set(proposal,'{1,status}','"source_gap"'),
        1,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,8,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=8));
    exception when others then failed := true; end;
    if not failed then raise exception 'SOURCE_GAP was certified'; end if;
    if public.mls_source_map_readiness(book)->>'audited_state' <> 'source_gap'
    then raise exception 'required SOURCE_GAP not surfaced in readiness'; end if;

    -- True printed heading depth can exceed the original five-kind chain.
    -- Keep every parent and a point locator without claiming page_end.
    proposal := pg_catalog.jsonb_build_array(
        proposal->0,
        proposal->1,
        proposal->1 || '{"node_id":"section","parent_id":"chapter-v2",
                          "kind":"section","title":"Transport","depth":2,"order_index":2}'::jsonb,
        proposal->1 || '{"node_id":"sub-a","parent_id":"section",
                          "kind":"subsection","title":"Diffusion","depth":3,"order_index":3}'::jsonb,
        proposal->1 || '{"node_id":"sub-b","parent_id":"sub-a",
                          "kind":"subsection","title":"Nonelectrolytes","depth":4,"order_index":4}'::jsonb,
        proposal->1 || '{"node_id":"sub-c","parent_id":"sub-b",
                          "kind":"subsection","title":"Concentration gradient","depth":5,"order_index":5}'::jsonb);
    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,9,proposal,5,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    certificate2 := public.mls_certify_source_map(book,9,
        (select payload_sha256 from public.mls_source_map_staging
         where logical_source_id=book and staging_version=9));
    if public.mls_promote_source_map(book,9,certificate2,1) <> 2
    then raise exception 'nested subsection promotion version mismatch'; end if;
    if (select count(*) from public.mls_source_map_nodes
           where logical_source_id=book) <> 6
       or (select parent_id from public.mls_source_map_nodes
           where logical_source_id=book and node_id='sub-c') <> 'sub-b'
       or (select page_end from public.mls_source_map_nodes
           where logical_source_id=book and node_id='sub-c') is not null
       or public.mls_source_map_readiness(book)->>'ready_for_hoc90' <> 'true'
    then raise exception 'nested subsection promotion/readback failed'; end if;

    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,10,pg_catalog.jsonb_set(proposal,'{5,parent_id}','"book"'),
        5,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,10,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=10));
    exception when others then failed := true; end;
    if not failed then raise exception 'invalid deep parent was certified'; end if;

    insert into public.mls_source_map_staging(
        logical_source_id,staging_version,proposal,toc_denominator,
        extraction_version,source_manifest,audit_metadata,payload_sha256
    ) values (
        book,11,pg_catalog.jsonb_set(proposal,'{5,page_end}','15'::jsonb),
        5,'test-parser-1',
        pg_catalog.jsonb_build_object(physical,pg_catalog.jsonb_build_object(
            'source_sha256',source_hash,'extraction_sha256',extraction_hash)),
        qa,'ignored-and-recomputed');
    failed := false;
    begin
        perform public.mls_certify_source_map(book,11,
            (select payload_sha256 from public.mls_source_map_staging
             where logical_source_id=book and staging_version=11));
    exception when others then failed := true; end;
    if not failed then raise exception 'point locator with page_end was certified'; end if;
    if (select source_map_version from public.mls_logical_sources
        where logical_source_id=book) <> 2
       or (select count(*) from public.mls_source_map_nodes
           where logical_source_id=book) <> 6
    then raise exception 'failed staging changed runtime map/version'; end if;
end;
$test$;
