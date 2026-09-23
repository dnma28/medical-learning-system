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
