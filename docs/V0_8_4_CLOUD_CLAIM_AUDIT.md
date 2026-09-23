# v0.8.4 — Cloud claim-audit ledger

Passage-level audit history now has production Supabase parity.

The table stores audit metadata and evidence IDs, not source passage text.

## Append-only rule

mls_claim_audits rejects UPDATE and DELETE at the database layer. Corrections
must be new audit rows and may point to the previous row using
supersedes_audit_id.

This protects the review trail even when the backend uses service-role access.

## Security

- RLS enabled.
- anon/authenticated receive no table privileges.
- service_role receives SELECT and INSERT only.
- no canonical KG mutation is exposed from this store.

The application API mirrors the SQLite audit store: append, get, history and
latest.
