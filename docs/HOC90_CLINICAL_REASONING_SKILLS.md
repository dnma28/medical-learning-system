# HỌC90 clinical reasoning Skill Tree contracts

The clinical-reasoning layer records advanced learner performance without turning
pedagogical frameworks into medical truth, diagnosis engines, or automatic mastery rules.

## Frameworks

The runtime currently supports three task contracts:

- **Illness Script** — mechanism-to-clinical organization practice.
- **HOAC II** — rehabilitation / physical-therapy hypothesis-oriented reasoning practice.
- **SCT-style** — reasoning under uncertainty using the interaction shape of a Script
  Concordance task.

These are framework identifiers and evidence containers. They do not contain canonical
medical answers.

## Runtime boundary

```text
verified source-bounded case / prompt
        ↓
current-validity gate when required
        ↓
ClinicalReasoningTask
        ↓
learner response
        ↓
review / assessment
        ↓
ClinicalReasoningEvidence
        ↓
CLINICAL_TRANSFER LearningEvent
        ↓
separate Skill Tree evidence policy
```

The event builder always emits `automatic_mastery_credit=false`. It does not mutate
`ConceptMastery`, `SkillState`, Error Graph, curriculum, Source Maps, or KG.

## SCT-style safety boundary

A response may be stored without a standardized score. If a standardized SCT-style score
is recorded, the evidence must name an explicit expert-panel reference. The runtime does
not manufacture a panel distribution or infer expert concordance from the language model.

This keeps ordinary HỌC90 uncertainty exercises separate from formally panel-scored SCT.

## Skill Tree persistence

The existing Supabase tables are used unchanged:

- `mls_skill_nodes` — skill identity, hierarchy, prerequisites, and unlock rule;
- `mls_skill_state` — evidence-derived learner state.

Python runtime models now mirror those tables. No schema migration is required.

A framework task can reference a Skill Tree node, but merely displaying or completing the
task does not raise M0–M7. Any future skill-state evaluator must consume append-only
learner evidence and preserve the same evidence rules used elsewhere in MLS.

## Source and freshness boundaries

Clinical cases remain source-bounded. Time-sensitive content must pass the existing MLS
current-validity gate before presentation. A task with
`current_validity_required=true` cannot be constructed unless
`current_validity_verified=true`.

The framework layer does not resolve source gaps, select a different textbook, or verify a
clinical guideline by itself.
