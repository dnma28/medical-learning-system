# Supabase migration dry-run

This repository keeps database migrations under `supabase/migrations/` as the schema source of truth.

The `Supabase migration dry-run` workflow verifies those migrations against the configured remote project without applying them.

Required GitHub Actions secrets:

- `MLS_SUPABASE_URL`
- `SUPABASE_ACCESS_TOKEN`
- `SUPABASE_DB_PASSWORD`

The project reference is resolved in least-privilege order: optional repository variable `SUPABASE_PROJECT_REF`; a standard project/dashboard URL; and only then the Management API. The ref is masked in logs. If the scoped token lacks account-wide Projects Read and the URL cannot identify the project, the workflow asks for the non-secret `SUPABASE_PROJECT_REF` variable instead of broadening token permissions.

## Reproducibility

The workflow uses Supabase CLI `2.117.0`, pinned to the current stable CLI version verified when this gate was created. The Actions runner creates `supabase/config.toml` only ephemerally when needed.

Before the dry-run it also executes `supabase migration list --linked` so local and remote migration history can be inspected.

## Safety boundary

The workflow may authenticate and inspect remote migration state, but its final command is always:

```bash
supabase db push --dry-run
```

It does not run a non-dry-run `db push`, execute arbitrary SQL, ingest source documents, or promote Candidate knowledge into the Canonical Medical KG.

A production schema apply must remain a separate reviewed action after the dry-run output is known.