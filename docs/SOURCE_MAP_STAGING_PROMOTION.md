# Source Map staging and promotion contract

Migration `0012_source_map_staging_promotion.sql` adds explicit `part` and
`unit` kinds. Existing `book/chapter/section/subsection/other` remain valid.
Part and Unit are sibling source labels directly under Book; Chapter may sit
under either or directly under Book. The strict runtime hierarchy is
Book → (Part or Unit) → Chapter → Section → Subsection; a source-backed
Subsection can contain deeper Subsections without losing its parent. Drafts may leave a
parent, kind, locator, source, or confidence unresolved. Do not infer Part or
Unit from bookmark depth.

## Boundaries

- **Staging**: `mls_source_map_staging` stores one complete JSONB proposal per
  logical book and staging version. A proposal node carries its source label,
  parent, kind, order/depth, optional physical source, locator kind
  (`unresolved`, `point`, `verified_range`), page/anchor, physical SHA-256,
  extraction SHA-256/version, status (`candidate`, `review_required`,
  `source_gap`, `verified`), confidence, evidence, issues and nullable
  `learning_value`. Unresolved topology belongs here. Insert is atomic; a
  trigger computes the proposal digest. UPDATE and DELETE are refused. A
  correction must use a higher staging version. Source text and PDF bytes do
  not belong in this table.
- **Certificate**: `mls_certify_source_map` is the only supported certificate
  path. It requires a full-book printed/body TOC denominator with source
  evidence, a reviewer and QA run, TOC reconciliation digest, all six QA flags,
  matching count of required node identities, valid tree, source bindings,
  current physical SHA-256, extraction fingerprints/versions and verified
  heading points or verified ranges. The audit metadata must attest zero
  required REVIEW_REQUIRED/SOURCE_GAP cases and zero unclassified outline
  observations; staged node issue lists must be empty. Every staged node must
  be required and verified for this full-book certificate. The certificate records the exact
  immutable staging digest and audit metadata. These QA fields are an
  **attestation based on source review**, not a way to manufacture missing
  textbook evidence. Evidence and denominator must be independently audited.
  No learner mastery or curriculum value participates in certification.
- **Runtime**: `mls_promote_source_map` accepts book, staging version,
  certificate SHA-256 and expected runtime version. It locks the book row,
  rejects concurrent/stale versions, revalidates the latest staging snapshot
  and certificate, replaces nodes and increments the version inside one
  Postgres transaction. An error rolls back the old map and version. A
  certificate alone does not promote. `learning_value` stays NULL unless
  separately assigned by curriculum decisions.
- **Readiness**: `mls_source_map_readiness` returns computed
  `structural_state`, `audited_state`, version fields and
  `historical_source_map_state`. READY requires a valid certificate for
  the currently promoted staging version, matching runtime tree and physical
  fingerprints. An older `section_anchored`, `deep_anchored` or
  `ready_for_hoc90` catalog label is reported only as historical metadata.
  `LogicalSourceMap.completeness()` remains fail-closed because it has no
  database certificate. A heading point does not claim full section range.

## Verification and rollout

1. Run the existing migration dry-run gate. The SQL integration script at
   `tests/sql/source_map_promotion_contract.sql` uses synthetic rows and must
   run inside `BEGIN; ... ROLLBACK;` after migration 0012. It tests successful
   promotion/readback, stale versions/certificates, QA and hierarchy failure,
   fingerprint drift, mid-transaction insertion failure, old-map rollback,
   staging immutability and historical labels. No test rows may be committed.
2. Apply migration only after PR review and CI. Verify constraints, function
   privileges, RLS, indexes/advisors, and that existing 16 books/55 sources
   remain with zero runtime Source Map nodes.
3. Pilot only a separately audited small staging version with certified
   source evidence; inspect readback before permitting corpus imports.
   The 16 Astra draft maps currently lack certified TOC denominators and must
   remain in staging.

The former `replace_source_map` API remains disabled. Use
`stage_source_map` → `certify_source_map` →
`promote_source_map(expected_version)` → `get_readiness` after migration
and pilot validation. Service-role-only grants and invoker functions do not
authorize broad user-facing writes.
