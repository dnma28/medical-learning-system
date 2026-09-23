# v0.10.1 — Source-aware HỌC90

## Purpose

HỌC90 now consumes the v0.10 logical Book Registry and Source Map layer directly instead of carrying only free-form source strings.

## Source spine

A new session may reference:

- `logical_source_id` — the logical book;
- `source_map_node_id` — the mapped chapter/section/subsection;
- `source_id` — the exact physical Drive file when known;
- `source_anchor` — page/locator metadata;
- `learning_value` — CORE_MASTERY / SUPPORTING / REFERENCE_ONLY / CURRENT_CLINICAL_CHECK;
- `freshness_required` — current-validity requirement.

Legacy sessions containing plain source strings remain readable.

## Runtime order

1. Resume an unfinished session when one exists.
2. Otherwise require a learner-approved curriculum position.
3. Load one active dynamic blueprint.
4. Run due retrieval before new teaching.
5. Recover missing source anchors instead of silently filling gaps.
6. Verify time-sensitive clinical evidence before presenting it as current standard.
7. Repair required prerequisites.
8. Retest observed learner errors.
9. Cover REFERENCE_ONLY material without turning it into a mastery target unless explicitly requested.
10. Continue the approved Source Map spine.
11. Open bounded cross-book branches when the source spine is insufficient.
12. Use transfer/counterfactual/Feynman to generate mastery evidence.
13. Persist meaningful learning events immediately.

## Commands

`HỌC 90: bắt đầu`:

- resumes an unfinished session first;
- otherwise uses the approved curriculum + active blueprint;
- never invents a large curriculum change.

`HỌC 90: tiếp tục`:

- resumes the stored concept/question/hint/source checkpoint;
- if no resumable session exists, reports that a new blueprint/session is required.

## Blueprint

A blueprint is a machine navigation contract, not a prewritten lecture. It contains source spine, objectives, mastery targets, retrieval targets, prerequisites, learner error state, Socratic chain, hint ladder, Feynman/counterfactual/transfer checks, freshness requirements, and an explicit completion gate.

## Coverage versus mastery

Source coverage remains independent from learner mastery. REFERENCE_ONLY content can be mapped/covered without pretending it is mastered. M5+ still requires delayed evidence rather than same-session performance.

## Database

Migration `0011_source_aware_hoc90_events.sql` extends append-only learning events with `source_retrieval` and `source_gap`. Structured source references are stored inside existing JSONB session/blueprint/event payloads, so no destructive table rewrite is needed.
