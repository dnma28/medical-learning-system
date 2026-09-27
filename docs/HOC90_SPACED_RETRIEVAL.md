# HỌC90 spaced retrieval with FSRS

This integration closes the runtime path from an append-only retrieval event to a due
review target without making the scheduler an authority over M0–M7.

## Runtime boundary

```text
independent free-retrieval LearningEvent
        ↓
explicit retrieval_rating
        ↓
FSRS 6.3.2 scheduler
        ↓
mls_concept_mastery.spaced_repetition_state
        ↓
mls_concept_mastery.next_review
        ↓
list_due_retrieval_concept_ids()
        ↓
LearningRouter.route_next_from_state()
        ↓
START_RETRIEVAL before new teaching
```

The scheduler controls **when to ask again**, not **what the learner has mastered**.

## Evidence gate

A scheduling event must:

- have `event_type=retrieval`;
- identify one `concept_id`;
- have `hint_level=0`;
- set `metadata.retrieval_independent=true`;
- set `metadata.retrieval_rating` to `again`, `hard`, `good`, or `easy`;
- not be recognition-only evidence.

Reading-quiz multiple choice remains recognition evidence and does not enter this path.

## Why learning/relearning steps are disabled

MLS already owns same-session hinting, self-correction, Error Graph repair, and immediate
retest. The FSRS card is therefore used for **delayed concept-level retrieval**, not as a
second in-session tutoring state machine. The runtime config uses:

- desired retention: 0.90;
- learning steps: none;
- relearning steps: none;
- interval fuzzing: disabled;
- maximum interval: 36,500 days.

Disabling fuzzing makes scheduling reproducible for the same evidence history.

## Persistence and replay

Migration `20260927024500_fsrs_spaced_retrieval.sql` adds one JSONB field to
`mls_concept_mastery`:

`spaced_repetition_state`

It stores the pinned engine version, scheduler configuration, serialized FSRS card, and
the last applied event ID. Reapplying the same event is idempotent. Applying a different
older event fails closed instead of silently corrupting the card history.

The append-only LearningEvent remains the behavioral evidence. The stored FSRS card is a
derived runtime projection and can be rebuilt from valid retrieval events if required.

## Mastery boundary

FSRS does not:

- promote or demote M0–M7;
- close Error Graph nodes;
- turn exposure into mastery;
- infer a correct answer from text;
- decide prerequisite sufficiency;
- change curriculum position;
- modify Source Maps, KG, or medical truth.

Successful and failed retrieval counters are updated because they describe observed
retrieval performance. Mastery-level changes still require the separate evidence rules.

## Install

```bash
pip install -e '.[supabase,fsrs]'
```

The dependency is pinned to `fsrs==6.3.2`. A future package/configuration change must be
reviewed explicitly; persisted cards using a different engine configuration fail closed
until deliberately rescheduled.
