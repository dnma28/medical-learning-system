# v0.9 Adaptive HỌC90 Runtime

## Purpose

v0.9 converts the project from a primarily source/KG pipeline into an adaptive learning runtime without weakening source provenance.

The user still learns in ChatGPT. The backend exists to make that conversation resumable, source-grounded, stateful, and adaptive.

## Responsibility split

- Google Drive: original textbooks, Source Maps, approved curriculum, human-readable project artifacts.
- GitHub: machine contracts, routing logic, retrieval, validation, migrations, tests.
- Supabase: live learner/runtime state.
- ChatGPT: teaching interface and Socratic interaction.

## Runtime state added in v0.9

`mls_learning_sessions` stores resumable HỌC90 sessions.

`mls_learning_events` stores append-only evidence after meaningful learner responses.

`mls_concept_mastery` stores evidence-based M0-M7 concept state.

`mls_learner_errors` stores observed error history and retest state.

`mls_source_coverage_state` stores book/TOC coverage separately from mastery.

`mls_skill_nodes` and `mls_skill_state` support a game-like skill tree without reducing competence to XP.

`mls_hoc90_blueprints` stores the active machine blueprint used to navigate a session.

## Mastery ladder

- M0: chưa học
- M1: nhận biết
- M2: tái hiện độc lập
- M3: giải thích cơ chế
- M4: vận dụng sang tình huống khác
- M5: bền vững qua delayed retrieval
- M6: tích hợp cross-domain và giới hạn/ngoại lệ
- M7: giảng dạy, phản biện, first-principles prediction, novel transfer và delayed retest

M5+ cannot be earned from same-session performance alone.

## Event model

State is written incrementally after meaningful responses. Examples:

- retrieval attempt;
- Socratic answer;
- hint exposure;
- self-correction;
- Feynman explanation;
- counterfactual;
- transfer;
- clinical transfer;
- observed error;
- checkpoint.

The event trail is not replaced when mastery changes. Aggregate learner state is derived from evidence, not used to erase history.

### Projection integrity

Derived learner tables are not independent authorities. Every mutation of
`mls_concept_mastery`, `mls_learner_errors`, and `mls_skill_state` must bind to
an existing append-only `mls_learning_events.event_id` with matching concept/skill
provenance. Scheduling-only projections may update retrieval timing/counters without
changing M0–M7. Mastery-level changes require explicit event evidence and remain bounded
by the evidence type/ceiling.

Concept and skill INSERTs use the same gate as mastery-changing UPDATEs, including
ConceptMastery's historical peak. Both cite the driving event (concept
`evidence_for_mastery`, skill `evidence_summary.event_ids`). Only assessed learner
performance types are accepted; a grant requires `outcome=correct`. Reductions may
use assessed `partial`/`incorrect` performance. Explicit M0–M7 ceilings are enforced
on newly granted levels/peaks; recognition and assisted responses cannot grant above
M1. Existing higher historical peaks are preserved during a lower-level reassessment.
This gate validates evidence eligibility; it does not automatically award any level.

The store saves ConceptMastery and SkillState through `mls_save_learner_projection`.
The RPC locks the projection identity, locks an existing row, and executes an actual
INSERT or UPDATE in one transaction. A table upsert would run BEFORE INSERT before
ON CONFLICT and incorrectly treat retained mastery/peak as a fresh grant. True
INSERTs still enforce the full grant gate; timing-only updates preserve higher levels.

The single-user runtime permits only one resumable (ACTIVE/PAUSED) HỌC90 session.
DeepTutor response evidence plus pending-interaction clear/session resume is committed
atomically and idempotently per interaction. ACTIVE blueprint replacement is likewise
one guarded transaction.

DeepTutor retries resolve the persisted event before checking the pending checkpoint,
so a committed submission remains retryable after resume or a newer interaction.
The bridge stores the normalized submission in event metadata and rejects conflicting
replays. The atomic RPC independently compares all persisted event fields except
`created_at`, rejects material changes, and returns the canonical event on both first
commit and retry. The store returns that readback, never an uncommitted candidate.
No replay clears a newer checkpoint. Events predating submission metadata fail closed
at the bridge rather than assuming their answer matches.

`tests/test_runtime_postgres_contract.py` exercises these actual caller paths, including
failed FSRS retrieval, assessed reductions, historical peaks, lost responses, CLI
retries and racing different answers/quiz outcomes. Opt in only on a disposable local
PostgreSQL server with `MLS_RUNTIME_POSTGRES_CONTRACT=1`; each test creates and drops
its own database. CI runs PostgreSQL 17 and the transactional SQL rollback contracts.

## Session lifecycle

```text
PLANNED → ACTIVE → PAUSED → ACTIVE → COMPLETED
                    ↘
                  ABANDONED
```

A paused session stores concept, question, hint level, TOC position, prerequisite branch, return-to-source target, open errors, and working mastery delta.

## Router priority

1. due retrieval at session start;
2. weak required prerequisite;
3. observed open learner error;
4. approved source spine / current TOC item;
5. bounded supporting-source expansion when needed;
6. transfer when mechanism understanding is ready.

The Router never approves a large curriculum change by itself.

## Quality modes

- FAST: simple, well-anchored concept.
- DEEP: complex mechanism or multi-source explanation.
- CRITICAL: time-sensitive clinical claim requiring current-validity verification.

## Backward compatibility

Legacy `MasteryState` and coarse routing APIs remain available so older code/tests are not broken abruptly.

The legacy `mls_coverage` table also remains untouched. v0.9 adds an explicit source-coverage table rather than changing historical semantics in place.

## Next engineering steps

1. Apply migration 0009 through the existing Supabase dry-run gate.
2. Verify the learning-state store against the remote schema.
3. Persist one real HỌC90 session end-to-end.
4. Normalize Drive Book Registry/Source Maps into machine-readable metadata.
5. Add blueprint generation from approved curriculum + Student Model + Error Graph + Skill Tree.
6. Add the least-privilege ChatGPT/backend bridge.
7. Build the game-like dashboard only after runtime state is stable.
