# v0.8.5 — Explicit Candidate Graph materialization

This milestone starts producing the typed GraphNode/GraphEdge objects used by
the modern system while retaining the v5 migration safety boundary.

## Nodes

Legacy v5 nodes become validation_status=CANDIDATE. If the legacy payload does
not define a trustworthy semantic node type, the importer uses
legacy_v5_candidate rather than inventing a biomedical ontology class.

Candidate nodes may have no evidence. That is allowed in candidate storage and
does not make them canonical.

## Relations

Legacy edges, guards and bridges become GraphEdge candidates with their original
relation kind, provenance and raw payload preserved in metadata.

They receive no evidence automatically.

## Explicit claim binding

Evidence may be attached only when the caller supplies an explicit binding:

relation_candidate_id ↔ claim_audit_id

The audited claim must already be source-grounded ready. Every selected evidence
ID must exist. The resulting GraphEdge receives Evidence locators containing:

- physical source_id
- 1-based PDF page
- evidence content hash

The source passage itself is not copied into the graph export.

## Canonical-review gate

The new gate only answers whether a candidate is eligible to enter a later
human canonical review. It never promotes the item.

It combines:
- the existing structural promotion gate;
- v0.8.3 source/fidelity audit readiness;
- CURRENT_VERIFIED for claims flagged as requiring a current check;
- relation provenance rules.

BRIDGE relations and INFERRED relations remain blocked from being treated as
direct source facts. They require a separate inference-review policy.
