# Supabase migration dry-run

This repository keeps database migrations under `supabase/migrations/` as the schema source of truth.

The `Supabase migration dry-run` workflow verifies those migrations against the configured remote database without applying them.

## Required GitHub configuration

Existing repository secrets:

```text
MLS_SUPABASE_URL
SUPABASE_DB_PASSWORD
```

One non-secret repository variable:

```text
SUPABASE_POOLER_HOST
```

Copy only the **Session pooler host** from the Supabase **Connect** dialog, for example a host shaped like:

```text
aws-1-example.pooler.supabase.com
```

Do not infer the pooler host from a region name. The workflow derives the project ref from the standard Project URL, percent-encodes the database password, constructs the Session pooler URL inside the ephemeral runner, masks the full connection string, and never prints it.

## Why direct database access

The migration workflow does not need to query project settings, API keys, Auth config, Storage config, or other Supabase Management API resources.

Therefore it deliberately avoids:

```bash
supabase link
```

and instead uses:

```bash
supabase migration list --db-url "$SUPABASE_DB_URL"
supabase db push --db-url "$SUPABASE_DB_URL" --dry-run
```

This avoids widening a scoped Supabase Personal Access Token merely so the CLI can fetch unrelated platform configuration.

## Reproducibility

The workflow pins Supabase CLI `2.117.0`.

## Safety boundary

The final migration command always includes `--dry-run`. Actual schema deployment remains a separate reviewed action after the dry-run output has been checked.
