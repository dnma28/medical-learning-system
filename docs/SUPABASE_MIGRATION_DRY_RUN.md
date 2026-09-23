# Supabase migration dry-run

This repository keeps database migrations under `supabase/migrations/` as the schema source of truth.

The `Supabase migration dry-run` workflow verifies those migrations against the configured remote database without applying them.

## Required GitHub secret

```text
SUPABASE_DB_URL
```

Use the **Session pooler** connection string copied from the Supabase **Connect** dialog. It is stored only as a GitHub Actions secret.

The pooler host must be copied from Supabase rather than inferred. The connection string includes the database password, so it must never be committed, pasted into issues, or printed in logs.

## Why direct database access

The migration workflow does not need to query project settings, API keys, Auth config, Storage config, or other Supabase Management API resources.

Therefore it deliberately avoids:

```bash
supabase link
```

and instead uses the database-specific CLI path:

```bash
supabase migration list --db-url "$SUPABASE_DB_URL"
supabase db push --db-url "$SUPABASE_DB_URL" --dry-run
```

This removes the need to broaden a scoped Supabase Personal Access Token merely so the CLI can fetch unrelated platform configuration.

## Reproducibility

The workflow pins Supabase CLI `2.117.0`.

## Safety boundary

The workflow never runs:

```bash
supabase db push --db-url "$SUPABASE_DB_URL"
supabase db reset --db-url "$SUPABASE_DB_URL"
supabase seed
```

The final migration command always includes `--dry-run`.

Actual schema deployment remains a separate reviewed action after the dry-run output has been checked.
