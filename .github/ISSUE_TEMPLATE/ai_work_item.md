---
name: AI work item
about: Bounded task for one owner and an independent reviewer
title: ""
labels: []
assignees: []
---

## Parent and outcome

Parent milestone:
Deliverable:
Why now:
Work key: <kind:stable-id>

The work key must be unique among open mutable work items. Source Map work uses
`source-map:<logical-book-id>`. Do not create another issue for the same key; update the
existing issue. Parallel child keys are allowed only for explicitly frozen, immutable,
non-overlapping batches.

## Scope and inputs

Owner role/session:
Independent reviewer:
Affected book/batch or code paths:
Base main commit:
Original Drive file IDs / edition / fingerprints (if relevant):
Dependencies:
Out of scope:

## Acceptance and gates

- [ ] Source/evidence or affected code paths checked against current main.
- [ ] Exact `Work key` searched across open issues; no duplicate mutable owner exists.
- [ ] Uncertainty retained as REVIEW_REQUIRED or SOURCE_GAP, if applicable.
- [ ] Relevant focused checks and CI recorded.
- [ ] Independent reviewer recorded a decision.
- [ ] PR or versioned external draft linked; handoff and blockers recorded.

Additional change-specific checks:

## Claim and handoff

CLAIM: <handle/session>; scope: <paths/book/batch>; base: <SHA>; expires: <UTC>

Changed paths or draft version:
Checks and exact results:
Unresolved cases:
Next action:
