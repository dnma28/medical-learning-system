# v0.8 — KG v5 lossless migration foundation

The existing Knowledge Graph v5 corpus is treated as legacy candidate knowledge,
not as canonical medical truth.

Before this layer was implemented, two connected Drive patches were inspected:
foundation.homeostasis.v1 and bridge.pharmacology_rehab_dose_response.v1.

The observed corpus is heterogeneous. A single document can contain an original
patch JSON object, migration prose, then a second JSON object with source-audit
metadata. Fields observed include nodes, edges, guards, bridges, sources,
hoc90_core, error_graph, source_anchors, claim_verification, toc_mapping and
truth rules.

## Boundary

KG v5 text
→ strict balanced JSON extraction
→ lossless raw payload objects
→ normalized migration candidates
→ migration findings and corpus audit
→ Candidate Graph only

This module has no canonical-graph write path.

## No silent repair

The importer does not fix malformed JSON, rename node IDs, collapse duplicates,
invent missing endpoint nodes, or upgrade SOURCE_VERIFIED / CORPUS_DERIVED /
INFERRED labels into canonical approval.

Malformed JSON fails. Duplicate IDs and external endpoints are reported.

## Relation classes

Legacy relations remain separated as:
- ASSERTED: ordinary legacy edges.
- GUARD: safety or non-equivalence constraints.
- BRIDGE: cross-domain conceptual relations.

INFERRED bridge provenance is preserved explicitly.

## Coverage invariant

TOC/Coverage remains the authority for whether source material has been studied.
The Knowledge Graph only links concepts.

## Next step

Map source_anchors and claim_verification onto the current Source Registry and
Evidence Store. Only evidence-resolved candidates can later enter the existing
promotion gate.
