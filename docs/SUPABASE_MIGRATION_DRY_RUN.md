# Supabase migration dry-run

This repository keeps database migrations under `supabase/migrations/` as the schema source of truth.

The `Supabase migration dry-run` workflow verifies those migrations against the configured remote project without applying them.

Required GitHub Actions secrets:

- `MLS_SUPABASE_URL`
- `SUPABASE_ACCESS_TOKEN`
- `SUPABASE_DB_PASSWORD`

The project reference is derived from `MLS_SUPABASE_URL`; it is not duplicated in repository configuration.

## Safety boundary

The workflow may authenticate and inspect remote migration state, but its final command is always:

```bash
supabase db push --dry-run
```

It does not run a non-dry-run `db push`, execute arbitrary SQL, ingest source documents, or promote Candidate knowledge into the Canonical Medical KG.

A production schema apply must remain a separate reviewed action after the dry-run output is known.