# HỌC90 integrated-on-demand mode

## Purpose

Preserve sequential chapter study as the default HỌC90 mode while allowing the learner to explicitly open a bounded cross-book integration branch.

This does not replace the curriculum, the Source Map, or the primary textbook. It adds a learner-invoked study mode for connecting a current structure or mechanism across compatible sources.

## Modes

### `chapter_sequential`

Default.

- Follow the approved curriculum position and the primary logical-book Source Map.
- Preserve Chapter -> Section -> Subsection coverage.
- Supporting books may still be used for prerequisite repair or when the primary source is insufficient.
- The router does not open an integration branch merely because several source references are present.

### `integrated_on_demand`

Only when explicitly requested by the learner.

- Requires an explicit `integration_goal`.
- Requires source targets from at least two logical books.
- Requires `return_to_source_spine`.
- Uses `CROSS_BOOK_EXPANSION` with DEEP quality mode.
- Source recovery, current-clinical verification, prerequisite repair, and observed-error remediation remain higher-priority gates.

## Intended learning path

A typical integration bundle may connect:

cell/molecule -> tissue -> gross anatomy -> physiology -> biomechanics/function -> pathology -> examination -> rehabilitation.

The exact books are selected from the resolved Source Map targets. No source may be silently substituted for missing textbook evidence.

## Learner commands

Examples:

- `HỌC 90: bắt đầu` -> normal sequential curriculum/session behavior.
- `HỌC 90 tích hợp: khớp háng` -> integrated-on-demand session.
- `Tích hợp phần này` -> open a bounded integration branch from the current Source Map position.
- `Quay lại chương` -> return to the stored primary source-spine target.

## Coverage and mastery

Integration never marks a whole supporting chapter as completed merely because one subsection was consulted.

Source coverage and concept mastery remain separate. Mastery still requires learner performance evidence; exposure or explanation does not increase mastery.

## Storage

No database migration is required for this change. HỌC90 blueprints already persist as structured JSONB payloads, so `study_mode` and `integration_goal` can be stored in the existing blueprint object.
