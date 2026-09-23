# v0.8.3 — Passage-level claim audit

KG v5.4 separates three validity dimensions. This milestone preserves that
separation in code.

## Three independent dimensions

1. source_anchor_state
   - PASS
   - MISMATCH
   - GAP

2. content_fidelity_state
   - UNREVIEWED
   - VERIFIED
   - PARTIAL
   - UNSUPPORTED
   - WRONG_SOURCE
   - UNRESOLVED

3. current_validity_state
   - NOT_APPLICABLE
   - BOOK_CURRENT_UNCHECKED
   - REQUIRES_EXTERNAL_CHECK
   - CURRENT_VERIFIED
   - OUTDATED
   - CONTESTED

A PASS source anchor only says the legacy source locator resolved. It does not
prove fidelity or current clinical validity.

## Explicit evidence selection

v0.8.2 can identify page-level evidence candidates. v0.8.3 requires a reviewer
to select the evidence block IDs that actually support the claim.

VERIFIED fidelity is invalid without at least one selected evidence ID, and a
selected evidence ID must already belong to the candidate set.

No source passage text is copied into the audit record.

## Two readiness questions

The gate reports two distinct results:

- source_grounded_ready: anchor PASS + fidelity VERIFIED + selected evidence.
- current_standard_ready: additionally satisfies the current-validity policy.

For a time-sensitive/high-risk claim, CURRENT_VERIFIED is mandatory before the
claim can be represented as a current standard.

BOOK_CURRENT_UNCHECKED is source-grounded metadata, not a current-standard
verdict.

## Versioned corrections

ClaimAuditStore is append-only. A later audit may point to the earlier record
with supersedes_audit_id, but previous review history is not overwritten.

This layer still does not write GraphNode or GraphEdge objects into the
Canonical KG.
