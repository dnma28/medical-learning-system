---
name: resumable-source-map-worker
description: Run bounded Source Map evidence/classification work safely across interruptions, concurrent workers, Drive artifacts, GitHub checkpoints, and Supabase safety gates.
---

# Resumable Source Map Worker

Use this skill for bounded Source Map evidence, classification, repair, audit, or readback work in the Medical Learning System when work can span multiple tool calls or be interrupted.

## Core objective

Make every run safe to stop and safe to resume.

An interrupted run must never require guessing what was completed, silently reuse stale evidence, widen scope, create duplicate canonical artifacts, or mutate runtime state outside the user's authorization.

## Deterministic batch runner

When the repository provides `mls-source-map-batch`, prefer it over chat-driven I/O for bounded review work:

- `prepare` verifies/materializes the source, keys the PDF block cache by content SHA-256, locks the full original manifest row, and emits a compact review packet.
- the model writes only decision fields; locked source fields are not part of the decision schema.
- `validate` is the hard gate before any artifact publication. It enforces exact row order/set, locked-row hashes, point-locator policy, source-binding restrictions, and allowed dispositions.
- with `ACCESS_GAP`/`SOURCE_GAP`, do not emit a canonical page or any VERIFIED state. Use candidate evidence only.

Do not rebuild these checks ad hoc in chat when the runner can perform them deterministically.
## Mandatory bootstrap

Before any source classification or artifact write:

1. Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
2. Read the retained GitHub issue and its latest relevant checkpoints.
3. Derive one exact `work_key` and one immutable authorized scope.
4. Search GitHub and Drive for the exact `work_key`, expected artifact name, and any superseded/duplicate artifacts.
5. Read live Supabase state required by the task.
6. Verify canonical source identity and fingerprint before classifying.
7. Recompute the input population from the frozen input artifact.
8. Assert the scope gate before reading source evidence.

If the scope gate fails, stop with `SCOPE_GATE_FAILED` and do not classify or upload.

## Resume contract

Treat GitHub checkpoints and verified Drive readback as durable state. Chat text is not durable authority.

At start or after interruption:

1. Re-read live GitHub/Drive/Supabase state.
2. Find the newest checkpoint for the exact work key.
3. Verify the artifact/checkpoint pair rather than trusting a prior assistant message.
4. Resume only unfinished or invalidated units.
5. If a correct canonical artifact already exists, stop under dedup guard.
6. If a concurrent artifact exists but is not yet canonical, compare scope, provenance, QA, and checkpoint status before deciding whether to continue.
7. Never use a superseded artifact as classification input unless the retained issue explicitly re-canonicalizes it.

## Scope lock

Record these before source inspection:

- work key;
- authorized chapter/unit set;
- expected per-unit row counts;
- total row count;
- minimum/maximum unit;
- canonical input IDs and hashes;
- source boundary where reading must stop.

Do not inspect or classify beyond the authorized source boundary. If source review crosses it, stop.

## Checkpoint protocol

Use at most three durable phases unless the task contract requires more:

### CHECKPOINT 1 — PREFLIGHT_LOCKED

Write only when useful for a long run and when no equivalent durable checkpoint already exists.

Include:
- work key;
- canonical input IDs/hashes;
- immutable scope;
- population counts;
- dedup result;
- pre-work Supabase safety state.

This checkpoint is not a classification result.

### CHECKPOINT 2 — ARTIFACT_VERIFIED

Write only after:
- all in-scope rows are classified or explicitly REVIEW_REQUIRED;
- hard QA passes;
- artifact upload succeeds;
- Drive readback independently reproduces scope, counts, digest, and fingerprint.

Do not label an artifact canonical before readback.

### CHECKPOINT 3 — CANONICAL_CLOSED

Use only if the workflow has a separate independent review/canonicalization gate.

Include the exact canonical Drive ID and explicitly name stale/duplicate artifacts as non-canonical.

For small bounded tasks where the requested GitHub checkpoint itself is the final gate, CHECKPOINT 2 can also be the final canonical checkpoint.

## Atomic artifact lifecycle

1. Build locally from frozen inputs.
2. Run all hard QA before upload.
3. Use a temporary local filename if necessary.
4. Upload exactly one candidate artifact only after QA passes.
5. Read back the uploaded Drive artifact.
6. Recompute scope, counts, digest, and file hash from readback bytes.
7. Only then publish the final checkpoint.
8. If a concurrent canonical artifact appeared during the run, do not overwrite it. Mark the new artifact `SUPERSEDED_DUPLICATE_DO_NOT_USE__` and stop.
9. Keep stale/conflicting artifacts for audit unless deletion is explicitly authorized; rename them clearly.

## Concurrency guard

Immediately before every irreversible write:

- re-search exact work key;
- re-search exact artifact name;
- re-read latest issue comments relevant to the work key.

If another worker has already completed the same work, stop. Do not produce a second canonical artifact or checkpoint.

## Evidence rules

- Original textbook bytes are source truth for Source Map structure.
- Frozen candidate rows are immutable.
- Do not use model knowledge to fill source gaps.
- Native outline is corroboration, not authority when incomplete.
- Publisher physical hierarchy controls topology.
- Never invent parent nodes.
- SOURCE_AUGMENTATION requires direct physical-source observation and explicit provenance.
- Uncertainty stays `REVIEW_REQUIRED`; never force closure.

## Hard QA before upload

At minimum verify:

- exact original-row count;
- exact authorized unit set;
- no out-of-scope rows;
- no missing/extra/duplicate/synthetic original IDs;
- original ledger fields unchanged;
- VERIFIED rows always have a final class;
- required child nodes have valid same-scope source-backed parents;
- merge targets are valid and non-chain;
- source IDs/hashes match;
- page_end policy matches the task;
- augmentations are inside scope and do not collide with originals.

If any hard assertion fails, do not upload.

## Supabase safety

If the task is evidence/classification-only, verify before and after that forbidden runtime state did not change. Never stage, certify, promote, mutate curriculum/KG, or mutate learner state unless separately authorized.

## Interruption behavior

If a tool fails:

1. Do not restart the whole batch automatically.
2. Identify the last durable state.
3. Retry only the failed stage using a different safe path after 2–3 failures.
4. Never report success from an unverified local artifact.
5. Never convert a tool failure into permission to relax scope or QA.
6. On the next user message, re-read live state before continuing.

## User-facing updates

Keep progress messages sparse:
- preflight/scope gate result;
- material blocker or concurrency event;
- final verified result.

Do not narrate every tool call.

## Definition of done

A bounded Source Map worker run is complete only when:

- scope gate passed;
- all authorized rows were handled exactly once;
- hard QA passed;
- Drive upload and independent readback passed;
- exact file hash and deterministic row digest are known;
- required GitHub checkpoint exists exactly once;
- post-work Supabase safety state is verified;
- stale/duplicate artifacts are clearly non-canonical;
- no forbidden mutation occurred.
