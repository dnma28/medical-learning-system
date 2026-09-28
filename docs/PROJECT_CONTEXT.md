# Medical Learning System — live-first project context

> Dated checkpoint: 2026-09-27. This document is orientation only, **not runtime
> authority**. Before acting, refresh GitHub `main`, the retained work item, live
> Supabase state, and exact Drive evidence for the assigned source. Newer live state
> overrides every count/status below.

## System boundary

The project is an adaptive medical-learning system, not a standalone knowledge graph.

```text
Google Drive
  textbooks + human-readable source evidence/curriculum
        ↓
GitHub
  parser/RAG contracts + Source Map validation + Router + HỌC90 runtime + CI/migrations
        ↓
Supabase
  promoted Source Maps + source/evidence runtime + learner/session runtime
        ↓
ChatGPT / HỌC90
  source-grounded tutoring interface
```

Keep these authorities separate:

- original textbook bytes are the source-material authority;
- certified/promoted Source Maps are the source-structure authority;
- Canonical Medical KG is not learner state and must not be auto-written by extraction;
- Student Model, Error Graph, Skill Tree, HỌC90 sessions, and append-only LearningEvents
  are learner/runtime state;
- source coverage and M0–M7 concept mastery are separate dimensions;
- current clinical validity is a separate gate from textbook fidelity.

## Live checkpoint

Verified from live Supabase on 2026-09-28:

- 16 logical books;
- **6/16 promoted books** are `ready_for_hoc90=true`: Costanzo, Kandel, Magee,
  Stryer, Bates, and Ganong;
- Guyton/Hall remains unpromoted with zero staging/certificate/runtime rows while
  bounded deeper-hierarchy reconciliation continues;
- one active HỌC90 blueprint and one paused pilot session exist;
- one system `source_retrieval` LearningEvent exists;
- ConceptMastery rows = 0, learner-error rows = 0, SkillState rows = 0.

The zero learner-state counts are intentional: deployment must not fabricate learner
performance.

### Source Map routing checkpoint

Current serial routing, subject to fresh issue/live readback:

- **Guyton/Hall #171 / #174** — current serial closure target. B1 Ch1–30 and
  B2 Ch31–60 are closed; strict B3-A Ch61–65 has independent PASS. Continue only
  in small machine-scoped batches with worker → independent reviewer gating.
- **O'Sullivan #176, Moore #178, Yanoff/Duker #180** — review-ready queues waiting
  behind the current serial target.
- **Medical Biochemistry #181** — evidence/reconciliation incomplete; denominator NULL.
- **Katzung #124** — blocked by required Appendix 1–3 physical-source coverage.
- **Kisner** — registered source has an explicit corruption/integrity blocker; do not
  infer missing structure.
- **Robbins** — parked at registered-source corruption.
- **Neumann** — canonical Part 3/full-book source binding remains unresolved.
- **Junqueira** — registered source/page-object corruption remains unresolved.

Durable Source Map mutable work requires an exact work key and, after the workflow
stability migration is deployed, an atomic Supabase work lease. GitHub comments are
audit records, not locks.

Do not infer that an expired CLAIM makes a work item available. Search exact `Work key:`,
read active PRs/comments, and reconcile the latest checkpoint first.

## HỌC90 runtime checkpoint

The first source-grounded Costanzo pilot is live:

- blueprint: `hoc90-pilot-costanzo-ch1-body-fluids-v1`;
- paused session: `hoc90-pilot-costanzo-ch1-body-fluids-session-001`;
- exact pilot evidence remains source-grounded;
- no learner answer/mastery/error/skill evidence has been fabricated.

The promoted Source Map evidence bridge was hardened in #165:

- evidence links bind to immutable Source Map `staging_version`;
- database validation enforces evidence → physical source → logical book → staged node
  affinity;
- page/content-hash/parser provenance is retained;
- evidence + links can commit atomically under an advisory transaction lock;
- once a book enters the promoted evidence bridge, HỌC90 does not silently fall back to
  legacy structure evidence;
- partial migration is allowed, but uncovered nodes fail closed with `SOURCE_GAP`.

FSRS is a review-timing engine only. It never grants M0–M7. Clinical-reasoning framework
events are evidence only and carry no automatic mastery credit.

## Mandatory session bootstrap

Before source work:

1. read `AGENTS.md`;
2. read milestone #97 and the retained per-book issue;
3. search the exact work key and inspect active PRs/claims;
4. read live `mls_source_map_readiness(logical_source_id)`;
5. verify exact Drive file ID/size/SHA-256 or retain an explicit access/source gap;
6. read the latest immutable/durable evidence packet;
7. resume only unfinished/invalidated units.

Before runtime/code work:

1. read the retained issue and affected code/contracts on current `main`;
2. inspect live schema/state when the change depends on production;
3. branch from current main;
4. add focused tests;
5. PR → required CI/review → merge;
6. deploy only through the reviewed migration/workflow path;
7. read back production state after deployment.

## High-value contracts

- `docs/SOURCE_MAP_EXECUTION_PLAN.md` — serial Source Map closure and blocker vocabulary.
- `docs/source_map_scope_policy.md` — structural denominator/supplement policy.
- `docs/HOC90_SOURCE_MAP_EVIDENCE.md` — immutable-stage evidence bridge and
  no-silent-fallback resolver rules.
- `docs/HOC90_DEEPTUTOR_DEPLOYMENT.md` — DeepTutor runtime boundary.
- `docs/HOC90_SPACED_RETRIEVAL.md` — FSRS timing boundary.
- `docs/HOC90_CLINICAL_REASONING_SKILLS.md` — clinical-reasoning evidence boundary.
- `docs/AI_WORK_QUEUE.md` — bounded claims, handoffs, and independent review.

## Never infer from this checkpoint

Do not use the counts or book states above to:

- certify/promote a Source Map;
- choose a TOC denominator;
- fill a source gap;
- change curriculum;
- award learner mastery;
- close an observed learner error;
- declare a current clinical recommendation valid.

Those require their own live evidence and gates.
