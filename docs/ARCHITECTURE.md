# Architecture v0.9 — Adaptive HỌC90

## Responsibility boundaries

```text
Google Drive
  original textbooks + human-readable Source Maps/Curriculum
        |
        v
Parser / RAG / evidence alignment
        |
        +-----------------------------+
        |                             |
        v                             v
Candidate / Evidence Graph       Source coverage
        |
 claim + relation audit
        |
        v
Canonical Medical KG
        |
        +-----------------------------+
        |                             |
        v                             v
Learning Router               Supabase runtime state
        |                      - Student Model M0-M7
        |                      - Error Graph
        |                      - Skill Tree
        |                      - HỌC90 sessions/events
        |                      - active blueprint
        v
Adaptive HỌC90
        |
        v
ChatGPT teaching interface
```

## Canonical ownership

- **Google Drive** owns original textbook binaries and human-readable study artifacts.
- **GitHub** owns executable machine contracts, routing logic, migrations, tests, retrieval code, and validation.
- **Supabase** owns live learner/runtime state.
- **Canonical Medical KG** owns validated medical concepts/relations, not learner state.
- **Candidate/Evidence Graph** owns extracted/proposed evidence before promotion.

## Learning-state separation

Two dimensions must never be collapsed:

1. **Source coverage** — whether a book/chapter/section/subsection has been mapped or studied.
2. **Concept mastery** — what the learner can independently retrieve, explain, transfer, and retain.

`mls_coverage` from older migrations is preserved for compatibility. v0.9 adds explicit runtime tables rather than silently changing old semantics.

## HỌC90 execution contract

At session start:

1. load approved curriculum position;
2. load resumable checkpoint if present;
3. load Student Model, Error Graph, Skill Tree, and due reviews;
4. load one active blueprint;
5. resolve source spine and required source anchors;
6. run retrieval before new teaching when due;
7. adapt within-session path using the Router.

Within a session, bounded adaptations may occur automatically: prerequisite repair, hint depth, retrieval selection, cross-book support, and transfer difficulty. Large curriculum changes require learner approval.

Meaningful learner responses are persisted immediately as append-only learning events. Aggregate state can then be updated without losing the original evidence trail.

## Retrieval rule

Use one **source spine** by default. Add supporting sources only when they materially improve mechanism, resolve a prerequisite, expose a meaningful disagreement, or provide a needed clinical bridge.

Do not load all textbooks or all KG patches for a single lesson.

## Provenance rule

Important teaching claims should remain traceable through:

```text
answer
→ claim
→ evidence block
→ passage / figure / table / equation
→ page / chapter
→ logical book + edition
→ physical Google Drive file
```

## Current-validity gate

Textbook fidelity and present-day clinical validity are separate. Dose, threshold, regimen, guideline, contraindication, monitoring, and similar time-sensitive claims require current verification before being presented as current standard.

## Security

Supabase and Google Drive backend credentials remain server-side. Raw copyrighted textbook binaries and extracted copyrighted corpora are not committed to Git.
