# Verified project recovery

Start with current main, milestone #97, the retained per-book or code issue for the
exact work key, and its latest verified checkpoint. The JSON snapshot is a dated, read-only projection, not another
writable queue. GitHub issues own tasks, Supabase owns runtime, Drive textbook
bytes own source evidence. Older chat/doc counts never authorize writes.

## Resume contract

Each task has id, status, owner, authority, dependency, evidence, blocking_reason,
next_action, definition_of_done, passed_gates and last_verified_at. Evidence records
its reference, subject and observation time. Use one retained issue per work key.
Record immutable commit/file hashes and database versions alongside evidence.

Run `python scripts/check_project_health.py /path/to/snapshot.json` after installing
the package. It checks schema, dependency graph, gate references and freshness
(24 hours by default). Failure means REVIEW_REQUIRED: refresh affected authorities.
It never writes runtime state or promotes tasks. Passing is NOT proof that an
evidence URL exists, that a reviewer is independent, or that a medical claim is true.
The owner must inspect referenced evidence; do not feed unchecked model assertions
into passed_gates. Immutable evidence may be reused after verifying its applicability
to the current source fingerprint, parser/configuration and promoted stage.

## Small state machine

| State | Entry | Exit / retry | Owner |
|---|---|---|---|
| UNKNOWN | Authority unavailable or not checked | Refresh only missing evidence | Milestone owner |
| NOT_STARTED | Known scope, no work | Claim exact key after dependency check | Assigned worker |
| IN_PROGRESS | Scope and inputs frozen | Validated candidate or explicit blocker | Assigned worker |
| BLOCKED_SOURCE | Missing/corrupt/uncertain source | Retry only changed bytes/access/evidence | Source owner |
| BLOCKED_CODE | Reproduced code/gate failure | Reviewed fix, tests, deployed readback | Engineering owner |
| REVIEW_REQUIRED | Bounded evidence packet ready or invalidated | Review exceptions and exact changed artifacts | Independent reviewer |
| READY_FOR_PROMOTION | All pre-promotion gates pass | Atomic guarded promotion then readback | Milestone owner |
| VERIFIED_DONE | All declared scope-specific gates and dependencies evidenced | Reopen affected scope on changed evidence | Milestone owner |

## Execute with fewer handoffs

1. Freeze one scope, source IDs/hashes, expected identities and physical coverage.
2. Reuse deterministic extraction/cache for unchanged bytes and parser settings.
3. Validate identity, source anchors, hierarchy, reverse coverage and artifact hashes.
4. Put ambiguity in one exception queue. A model resolves only those exceptions
   against actual source evidence; unresolved items stay explicit gaps.
5. Independent review checks provenance, reproducibility, safety and changed
   invariants. Reuse unchanged evidence; invalidate review when relevant bytes change.
6. Stage/certify/promote only through deployed version-guarded contracts. Read back
   digest, certificate, runtime parity, orphan/duplicate checks and retrieval.
7. Persist checkpoint at the retained issue before concluding the work unit.

No model-specific relay is required. Internal batches are not human checkpoints.
Ask the user only for source-policy/curriculum decisions, material cost, irreversible
actions, or data-loss risk. Source gaps cannot be filled with model knowledge.

## DONE is scoped

- Code: exact commit, tests/static checks, independent review, CI, merge and
  post-deploy verification. Migration dry-run preview is not SQL execution.
- Structural map: exact physical identity, required-identity denominator, anchors,
  hierarchy, reproducible evidence, certificate, promotion and full runtime parity.
- HỌC90 evidence: covered and uncovered retrieval cases, current immutable stage
  bindings, evidence provenance and fail-closed SOURCE_GAP behavior.
- Complete learning milestone: source → processing → evidence → storage → retrieval
  → real runtime consumption. No fabricated learner response or mastery writes.

`ready_for_hoc90` from the structural readiness RPC alone does not satisfy the
last two scopes. A book-level map root without a physical binding is not itself
an orphan: inspect non-root nodes and actual affinity constraints.

## Recovery and rollback

If interrupted, read back external writes before retrying. A transient workspace or
successful tool response without retained evidence is not a completed checkpoint.
Persist branch/commit, artifact hashes, exact next action and unresolved failures.
Do not reparse the entire corpus. Invalidate only changed source/configuration scope.

Code rollback uses a reviewed revert. Database changes need a forward remediation
plan and validation queries; never delete events or production evidence to reset a
pipeline. Check migration ordering against live history before merging dependent PRs.
Do not disable provenance gates to make a blocked batch pass.

The read-only projection itself has no database effect; revert its code to roll back.
Current counts and task ownership belong in the dated checkpoint, not this runbook.
