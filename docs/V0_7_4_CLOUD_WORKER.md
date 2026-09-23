# v0.7.4 — Atomic cloud compilation worker

The cloud ingestion path now has one complete worker iteration:

    Supabase queue
        ↓ atomic claim
    Source Registry
        ↓
    Google Drive
        ↓ temporary PDF
    IncrementalSourceCompiler
        ↓
    Supabase Coverage / Evidence / Links / Manifest
        ↓
    queue succeeded / failed

## Atomic claim

mls_claim_compilation_job() selects one pending job using
FOR UPDATE SKIP LOCKED and changes it to RUNNING in the same transaction.
Concurrent workers therefore do not intentionally claim the same queue row.

The attempt counter is incremented at claim time.

## Finalization

mls_finish_compilation_job(...) changes only a RUNNING job to SUCCEEDED or
FAILED. A stale or duplicate finalization returns no row and the Python adapter
raises.

## Worker privacy

Worker output records only the exception class on failure. It does not echo
Drive file content, OAuth credentials, or temporary source paths.

The Drive source context removes the temporary PDF on both success and failure.

## One-shot execution

    mls-worker-once

is designed for a cron/serverless/container invocation. One call processes at
most one job, keeping runtime and failure boundaries explicit.

Required production secrets remain backend-only:

- MLS_SUPABASE_URL
- MLS_SUPABASE_SERVICE_ROLE_KEY
- Google ADC or MLS_GOOGLE_DRIVE_OAUTH_JSON

No LLM or embedding model is invoked by this worker.
