# v0.5.2 — Supabase cloud storage

## Role in the system

```text
Google Drive        GitHub
source binaries     code / schema / tests
      │                  │
      └────────┬─────────┘
               ▼
       Medical Learning backend
               │
       ┌───────┴─────────┐
       ▼                 ▼
    SQLite            Supabase
   dev / CI        production cloud
```

SQLite remains the local test implementation. Supabase is the first persistent
cloud target for a user who does not have a dedicated computer.

## Current tables

- `mls_sources`
- `mls_structure_nodes`
- `mls_coverage`
- `mls_evidence_blocks`

Student Model, Error Graph, question bank, FSRS state and vector columns are not
added prematurely. They will receive migrations when their application models
exist.

## Security model

The current project is a single-user backend architecture.

All four tables have Row Level Security enabled, and no anon/authenticated
policies are created. The backend uses the Supabase service-role key.

**The service-role key must never appear in:**

- Git commits
- browser/mobile code
- ChatGPT prompts
- logs or screenshots
- learning packs

Use only backend environment variables:

```text
MLS_SUPABASE_URL
MLS_SUPABASE_SERVICE_ROLE_KEY
```

## Setup later

When a Supabase project is created:

1. Run `supabase/migrations/0001_core_storage.sql` in the project migration
   workflow / SQL editor.
2. Store the project URL and service-role key only in the backend secret store.
3. Install the optional dependency:
   `pip install -e ".[supabase]"`
4. Construct the client with `build_supabase_client()`.

No Supabase account is required for unit tests.

## Current API baseline

The implementation was checked against current `supabase-py` 2.x. The latest
GitHub release checked during this milestone was v2.31.0. The adapter uses the
stable `create_client`, table `select`, `upsert`, `update`, and `delete`
query interfaces.

## Deliberate limits

- PDF files remain in Google Drive.
- pgvector is deferred to v0.6.
- Evidence replacement currently uses delete + upsert and is recoverable from
  the source parser output. A database RPC transaction can be added if actual
  production concurrency makes it necessary.
- No browser-facing Supabase client is part of this milestone.
