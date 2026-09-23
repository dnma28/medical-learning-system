# v0.8.6 — Append-only relation audit ledger

Relation-to-claim audit mappings now have persistent review history.

The stable `mapping_id` identifies the pair:

```text
relation_candidate_id ↔ claim_audit_id
```

Every human review produces a separate `decision_id`.

## Corrections

A correction never overwrites the old decision:

```text
decision A: CONFIRMED
    ↓ superseded by
decision B: REJECTED
```

Both remain queryable. `latest(mapping_id)` is a convenience view over the
append-only history.

## Storage

- SQLite: development/test history.
- Supabase: production cloud history.
- Supabase row-level security is enabled.
- Only the backend service role has access.
- `audit_id` references the append-only claim-audit ledger.

The relation candidate ID is preserved as an opaque v5 candidate identity.
There is no fuzzy relation remapping and no canonical graph write.

## Important boundary

A persisted CONFIRMED decision means only that a reviewer explicitly accepted
the relation↔claim-audit mapping. The relation must still pass relation support,
candidate materialization and canonical-review gates.
