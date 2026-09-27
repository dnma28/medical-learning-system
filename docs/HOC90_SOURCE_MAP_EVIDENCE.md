# HỌC90 promoted Source Map evidence bridge

## Authority and purpose

The original evidence alignment table points to legacy `mls_structure_nodes`.
HỌC90 routes by certified/promoted Source Maps. The bridge is derived source
infrastructure only; it is not medical truth, curriculum, learner state, Error Graph,
Skill Tree, or mastery authority.

The authority chain is:

```text
Drive textbook bytes
  → exact registered SHA-256
  → immutable Source Map staging + certificate
  → promoted runtime Source Map
  → versioned exact evidence links
  → HỌC90 source context
```

## Immutable version binding

Runtime `mls_source_map_nodes` are a mutable projection: promotion replaces them.
Evidence links therefore carry `staging_version` and are validated against the
immutable `mls_source_map_staging.proposal`.

The previous direct foreign key to runtime nodes is removed. A future promotion no
longer cascades away historical evidence links merely because runtime nodes are
replaced.

A database trigger checks every promoted link against:

- evidence block → physical `source_id`;
- physical source → `logical_source_id`;
- immutable staging version → exact `node_id`;
- staged node → the same physical source;
- current promoted staging + runtime Source Map version;
- evidence page and content hash recorded in `anchor_context`.

This prevents a Guyton evidence block, for example, from being attached to a Costanzo
Source Map node even if application code sends inconsistent identifiers.

## Per-book migration gate

`mls_source_map_evidence_status` records whether a specific immutable staging version is:

- `partial` — some exact nodes are available; uncovered nodes fail closed;
- `complete` — all physically bound Source Map nodes have promoted evidence;
- `review_required` — the evidence version is withheld from runtime use;
- `stale` — a newer Source Map version has been promoted.

Once any version of a logical book enters this bridge with
`legacy_fallback_disabled=true`, HỌC90 never silently returns to legacy evidence for
that book.

This intentionally preserves the existing Costanzo pilot as a **partial** migration:
its exact linked node remains runnable, while other uncompiled nodes return
`SOURCE_GAP` instead of borrowing legacy structure.

## Atomic compiler commit

The compiler still parses outside the database, but the source-authority write is one
PostgreSQL transaction through `mls_commit_source_map_evidence`.

The RPC:

1. takes a logical-book advisory transaction lock;
2. rechecks the current promoted staging and runtime Source Map version;
3. rechecks the physical source SHA-256;
4. requires `mls_source_map_readiness(...).ready_for_hoc90=true`;
5. replaces the physical source evidence blocks;
6. inserts current-stage evidence links with page/bbox/hash/parser provenance;
7. updates the per-book migration gate;
8. returns exact write counts.

If any validation or insert fails, the transaction rolls back. No half-replaced
evidence/link state is exposed.

## Structural alignment policy

The source-map-aware compiler:

- materializes the registered Drive PDF privately;
- verifies size and SHA-256 before parsing;
- uses native PDF blocks retaining page and bounding-box provenance;
- aligns only by publisher structure: exact heading, heading prefix, and deterministic
  heading sequence;
- keeps weak page-range candidates as audit information but does **not** promote them
  automatically into HỌC90 exact-node context;
- never uses vector similarity, fuzzy title matching, or model inference for Source Map
  placement;
- never invents `page_end`.

If existing evidence for the physical source is present, replacement still requires the
explicit `--allow-replace-existing` operator flag.

## Resolver policy

For a migrated book:

```text
current staging has partial/complete migration
  → query only current-stage promoted links
  → exact node missing = SOURCE_GAP
  → review state = REVIEW_REQUIRED
  → never legacy fallback

book was migrated previously but Source Map advanced
  → SOURCE_GAP until current evidence is compiled
  → never legacy fallback
```

For a book that has **never** entered the bridge, the legacy exact-link/scalar adapter
remains available during migration. It never widens by guessed page range.

## RLS

The current project is backend-only for source authority:

- `anon`: no direct access;
- `authenticated`: no direct access;
- `service_role`: compiler/resolver backend access.

The external review's suggestion to grant direct authenticated SELECT is not adopted
because it would weaken the present architecture rather than solve a current need.

## Production migration safety

The hardening migration backfills already-live evidence links with:

- their current immutable `promoted_staging_version`;
- `status=promoted`;
- page/index/bbox/content-hash/parser provenance from the evidence block;
- a `partial` migration record.

It does not modify the Costanzo blueprint, paused session, SourceSpineRef,
LearningEvents, ConceptMastery, Error Graph, or Skill Tree.
