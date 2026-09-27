# HỌC90 promoted Source Map evidence bridge

## Purpose

Legacy evidence alignment points to `mls_structure_nodes`. Certified HỌC90 source
routing uses `mls_source_map_nodes`, whose runtime rows are replaced when a new
Source Map version is promoted.

The evidence bridge therefore binds evidence to the **immutable promoted staging
version**, not directly to mutable runtime rows.

Authority remains:

```text
Drive textbook bytes
    ↓ exact SHA-256
immutable Source Map staging + certificate
    ↓ promotion
runtime Source Map
    ↓
versioned evidence links
    ↓
HỌC90 source context
```

The bridge is derived source infrastructure. It is not medical truth, curriculum,
learner state, Error Graph, Skill Tree, or mastery authority.

## Schema

Two backend-only tables are added:

- `mls_source_map_evidence_links` — evidence → physical source → logical book →
  immutable staging version → Source Map node.
- `mls_source_map_evidence_status` — per-book/per-staging migration gate with
  `compiling`, `review_required`, or `ready`.

The link table deliberately stores `source_id` and `logical_source_id` even though
they are derivable. In the current MLS schema these fields let PostgreSQL enforce and
audit physical-source affinity efficiently. A trigger verifies every row against:

1. the evidence block's physical source;
2. that physical source's logical book;
3. the exact immutable staging proposal;
4. the staged node's own physical-source binding;
5. page/content-hash provenance when supplied;
6. the current promoted certificate/runtime map before a link may be marked
   `promoted`.

This adapts the normalized design to the repository's actual text identifiers and
immutable staging architecture; it does not use the UUID/version tables assumed by
external design examples.

## Version safety

Evidence links are keyed by `staging_version`. They do **not** foreign-key directly to
mutable `mls_source_map_nodes`.

When a new Source Map version is promoted:

- old evidence links remain auditable against their immutable staging version;
- they no longer satisfy the current resolver version filter;
- a book that has ever completed evidence migration fails closed until the new
  promoted version has its own ready evidence migration;
- no old links are silently re-pointed.

This prevents stale context while avoiding destructive cascades during Source Map
promotion.

## Compile contract

The source-map-aware compiler:

1. requires `mls_source_map_readiness(...).ready_for_hoc90=true`;
2. records the active `promoted_staging_version` and runtime Source Map version;
3. materializes the exact registered Drive PDF privately;
4. verifies byte size and SHA-256 against `mls_sources` before source writes;
5. extracts born-digital PDF text blocks with page and bounding-box provenance;
6. aligns headings using normalized exact/prefix matching plus deterministic document
   sequence only;
7. never uses embeddings, fuzzy similarity, or model inference for structural
   placement;
8. never infers Source Map `page_end`;
9. writes reusable evidence, then atomically replaces links for the physical source
   through `mls_replace_source_map_evidence_links`;
10. marks the per-book gate `ready` only when every physically bound Source Map node
    has promoted evidence and the source manifest is complete.

If the Source Map promotion pointer changes during parsing, compilation aborts before
evidence replacement.

Existing evidence replacement requires explicit `--allow-replace-existing`.

## Resolver policy: no silent fallback

The exact-node HỌC90 resolver applies a per-book migration gate.

```text
current evidence status == ready
    → use only promoted links for current staging version
    → missing node evidence = SOURCE_GAP / REVIEW_REQUIRED
    → NEVER legacy fallback

book has a previous ready evidence version,
but current promoted version is not ready
    → SOURCE_GAP
    → NEVER legacy fallback

book has never completed evidence migration
    → legacy exact-link/scalar adapter may be used temporarily
    → no page-range widening
```

This prevents mixed-context pollution between certified Source Maps and legacy structure.

## RLS boundary

The current MLS deployment is backend-only and single-user. Consistent with the other
source-authority tables:

- `anon`: no access;
- `authenticated`: no direct access;
- `service_role`: backend read/write.

HỌC90 reads source evidence through the backend resolver. If MLS later adopts a
browser/mobile direct-read architecture, authenticated read policies can be introduced
as a separate reviewed migration rather than weakening the current boundary.

## Manual production pilot

`.github/workflows/hoc90-source-map-evidence-pilot.yml` is manual only.

It requires backend Supabase credentials and read-only Google Drive OAuth. The default
logical source is Costanzo, but the workflow still resolves the registered physical
source and verifies exact bytes before writes.

Raw textbook bytes never enter Git.

The pilot sequence is:

```text
merge + migration apply
→ compile Costanzo evidence
→ inspect unresolved_node_ids
→ evidence gate READY
→ exact resolver readback
→ create source-grounded HỌC90 blueprint/session
→ learner interacts
→ append LearningEvent
```

No learner response is fabricated during deployment.
