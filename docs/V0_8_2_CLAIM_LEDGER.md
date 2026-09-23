# v0.8.2 — KG v5 claim-evidence migration ledger

This layer resolves legacy claim_verification records without promoting them.

Each claim is matched only through its explicit source_anchor_id. No fuzzy
matching is performed between claim text and legacy graph edges.

Possible states include:
- PASS with page-level evidence candidates.
- PASS but no stored evidence candidates.
- PASS with unresolved source identity.
- GAP.
- MISMATCH.
- verification conflict between claim and anchor.
- missing, unknown or ambiguous anchor references.
- unreviewed/invalid legacy records.

A PASS claim with evidence candidates still has passage_review_required=true.
The candidate blocks identify where to inspect; they do not prove that every
block on the page entails the claim.

This ledger is therefore an audit/migration artifact. It has no canonical KG
write path.
