# v0.8.3 — Claim fidelity and current-validity review

This is the final review boundary before a future candidate claim can be
considered by the existing KG promotion gate.

Three dimensions remain independent:

1. source-anchor state: did the legacy anchor resolve to the claimed source?
2. content fidelity: does a specifically selected evidence block support the
   claim?
3. current validity: is a currentness check unnecessary, still unchecked, or
   verified against current evidence?

A PASS source anchor does not imply VERIFIED content fidelity. VERIFIED content
fidelity does not imply CURRENT_VERIFIED.

## Content review

VERIFIED requires:
- a v0.8.2 PASS claim with candidate evidence;
- source_anchor_state PASS;
- one or more explicitly selected supporting evidence IDs;
- every supporting ID must already be one of the page-resolved candidates.

This prevents a reviewer from attaching arbitrary evidence to a legacy claim.

## Current-validity review

The v5.4 states are preserved:

- NOT_APPLICABLE
- BOOK_CURRENT_UNCHECKED
- REQUIRES_EXTERNAL_CHECK
- CURRENT_VERIFIED
- OUTDATED
- CONTESTED

CURRENT_VERIFIED, OUTDATED and CONTESTED require explicit evidence references.

Claims marked as time-sensitive/high-risk require CURRENT_VERIFIED. That flag is
set explicitly; this milestone does not infer clinical risk with a model.

## Promotion blockers

promotion_blockers() only reports whether prerequisites are missing. It does not
write to GraphNode, GraphEdge or the Canonical KG.

For the conservative initial policy, BOOK_CURRENT_UNCHECKED and
REQUIRES_EXTERNAL_CHECK remain blockers. A reviewed claim clears the
current-validity gate only with NOT_APPLICABLE or CURRENT_VERIFIED.

No LLM generates review verdicts in this milestone.
