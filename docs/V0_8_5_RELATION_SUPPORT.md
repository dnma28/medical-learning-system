# v0.8.5 — Explicit relation-to-claim audit mapping

KG v5 relations and claim-verification records were created as separate
structures. Source grounding therefore cannot be inherited from the whole
patch.

This layer links a relation candidate to a reviewed ClaimAuditRecord only
through an explicit RelationAuditLink.

## No semantic guessing

The system does not:
- compare claim/relation text with fuzzy matching;
- use embeddings to infer equivalence;
- ask an LLM to attach claims to edges automatically.

Every relation_candidate_id ↔ audit_id link is explicit and reviewed as
UNREVIEWED, CONFIRMED or REJECTED.

## Readiness dimensions

A relation report keeps four questions separate:

- source_grounded_ready: at least one confirmed claim audit is source-grounded;
- current_standard_ready: at least one confirmed claim audit is current-standard
  ready;
- source_derived_ready: the relation itself may be represented as
  source-derived;
- current_standard_source_derived_ready: both current-standard and
  source-derived requirements are satisfied.

This separation matters for cross-domain bridges.

## Inferred bridges

An INFERRED bridge may connect concepts backed by strong source evidence, but
the bridge relation itself remains an inference. Claim mapping never upgrades it
to SOURCE_DERIVED.

## No canonical write

This module produces provenance/readiness reports only. It does not create or
write Canonical GraphNode/GraphEdge records.

The append-only claim_audit.py path is the only claim-review source used here.
