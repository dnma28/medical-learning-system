-- Read-only, metadata-only observation. Structural readiness is not teaching readiness.
-- No textbook passages, learner answers, or credentials are returned.
select jsonb_build_object(
    'observed_at', now(),
    'migrations', (select jsonb_agg(version order by version)
                   from supabase_migrations.schema_migrations),
    'books', (select jsonb_agg(jsonb_build_object(
        'id', b.logical_source_id,
        'identity_status', b.identity_status,
        'structural_readiness', public.mls_source_map_readiness(b.logical_source_id)
    ) order by b.logical_source_id) from public.mls_logical_sources b),
    'staging_rows', (select count(*) from public.mls_source_map_staging),
    'certificates', (select count(*) from public.mls_source_map_certificates),
    'runtime_nodes', (select count(*) from public.mls_source_map_nodes),
    'evidence_blocks', (select count(*) from public.mls_evidence_blocks),
    'learning_events', (select count(*) from public.mls_learning_events),
    'event_mutation_privileges', jsonb_build_object(
        'update', has_table_privilege('service_role','public.mls_learning_events','UPDATE'),
        'delete', has_table_privilege('service_role','public.mls_learning_events','DELETE'),
        'truncate', has_table_privilege('service_role','public.mls_learning_events','TRUNCATE')
    ),
    'event_guards', (select jsonb_agg(jsonb_build_object(
        'name', tgname, 'enabled', tgenabled
    ) order by tgname) from pg_trigger
      where tgrelid = 'public.mls_learning_events'::regclass and not tgisinternal),
    'orphan_parents', (select count(*) from public.mls_source_map_nodes n
        where n.parent_id is not null and not exists (
            select 1 from public.mls_source_map_nodes p
            where p.logical_source_id = n.logical_source_id and p.node_id = n.parent_id
        )),
    'unbound_nonroot_nodes', (select count(*) from public.mls_source_map_nodes
        where kind <> 'book' and source_id is null)
) as snapshot;
