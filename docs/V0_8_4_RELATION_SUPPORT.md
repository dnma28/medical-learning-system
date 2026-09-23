# v0.8.4 — Explicit relation-to-claim support mapping

Legacy KG v5 relations and claim_verification entries are independent objects.
This layer prevents the migration pipeline from assuming that a nearby claim
proves a graph edge.

## Explicit mapping only

A RelationClaimLink connects exactly:
- one V5RelationCandidate.candidate_id;
- one ClaimReviewRecord.review_id.

There is no fuzzy matching, embedding match or LLM equivalence step.

Each link is UNREVIEWED, CONFIRMED or REJECTED and retains reviewer metadata.

## Support readiness

A relation is support_ready only when at least one CONFIRMED mapping points to a
claim review that clears all v0.8.3 promotion blockers.

Rejected and unreviewed mappings remain visible for audit.

## Source-derived readiness

support_ready and source_derived_ready are separate.

An INFERRED bridge can have reviewed evidence for the concepts used in the
inference, while still remaining an inferred cross-domain relation. Explicit
claim mapping therefore never relabels an INFERRED bridge as SOURCE_DERIVED.

## No promotion

The report is a gate input only. It does not create or write Canonical
GraphNode/GraphEdge records.

This preserves the v5.3/v5.4 rule that node-level or patch-level provenance does
not automatically prove edge-level provenance.
