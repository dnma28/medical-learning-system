# Supabase migration gate

This repository keeps database migrations under `supabase/migrations/` as the schema source of truth.

## Behavior

- On **pull requests** that touch migrations, the workflow connects through the project's Supavisor Session pooler and runs `supabase db push --dry-run`.
- On **pushes to `main`** that touch migrations, the same workflow first inspects migration history and then runs the reviewed `supabase db push` for real.
- `workflow_dispatch` remains dry-run only.

This keeps production migration history aligned with the committed migration files instead of applying ad-hoc SQL through another path.

## Required GitHub secrets

```text
MLS_SUPABASE_URL
SUPABASE_DB_PASSWORD
```

The Session pooler hostname is non-secret and is pinned in the workflow for the current Supabase project region (`ap-south-1`). If the project is recreated in another region, update that hostname as part of the reviewed infrastructure change.

## Why Session pooler

Supabase documents direct database connections as preferable for migrations when IPv6 is available. GitHub-hosted runners in this repository could resolve the direct IPv6 endpoint but could not establish the connection, so the workflow uses the IPv4-capable shared Session pooler on port 5432.

The generated database URL:

- derives the project ref from `MLS_SUPABASE_URL`;
- percent-encodes the database password;
- uses username `postgres.<project-ref>` for Supavisor;
- requires SSL;
- is masked before use;
- is never printed to logs.

## Safety boundary

Pull requests cannot apply schema changes. They only preview pending migrations.

Actual schema deployment happens only after the reviewed commit lands on `main`.

After DDL changes, verify the live project through the Supabase connector and run security/performance advisors.
