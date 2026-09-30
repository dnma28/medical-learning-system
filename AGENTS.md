# Coding instructions — Ponytail mode

This repository uses a Ponytail-style coding policy, adapted from
DietrichGebert/ponytail (MIT).

The goal is minimum necessary code, not code golf. Be efficient, never careless.

Before writing code, stop at the first option that solves the task safely:

1. Does this need to exist at all? If not, do not build it.
2. Does the repository already contain the needed helper, pattern, or abstraction? Reuse it.
3. Can Python's standard library solve it? Prefer that.
4. Can the native platform solve it? Prefer that.
5. Can an already-installed dependency solve it? Reuse it.
6. Can the change be expressed as a small direct change? Do that.
7. Only then add the minimum new code required.

Read the affected code path before changing it. For bug fixes, find the root cause and
check sibling callers rather than patching only one visible symptom.

## General rules

- Do not add abstractions unless the task actually needs them.
- Avoid new dependencies when existing code, stdlib, or current dependencies suffice.
- Avoid boilerplate and speculative extensibility.
- Prefer deletion and reuse over addition.
- Prefer boring, explicit code over clever code.
- Keep diffs small, but never at the cost of correctness.
- Preserve validation, security, data-loss protection, and accessibility.
- Non-trivial behavior should leave one small runnable test or check behind.
- Never merge a PR with a failed or pending required check. Review evidence must bind to the exact current HEAD; a new commit invalidates the previous review gate.
- Never commit secrets, API keys, local RAG storage, parser output, or copyrighted textbook binaries.

## Coordination invariants

These rules apply before an agent creates or starts a mutable work item:

1. Every AI work item must declare one stable `Work key:` in its issue body. Use a semantic key such as `source-map:<logical-book-id>`, `runtime:<component>`, or `code:<bounded-area>`.
2. Search open issues for the exact work key before creating a new issue. If one exists, continue or update that issue instead of creating another.
3. For Source Map work, one logical book has one active mutable key: `source-map:<logical-book-id>`. Parallel child work is allowed only when the parent issue explicitly freezes immutable, non-overlapping batches and gives each child a distinct key. After the Source Map workflow-stability migration is deployed, any mutable child batch must also hold the atomic Supabase work lease for its exact work key/scope/manifest; GitHub comments and Drive searches are not locks.
4. A claim timeout is not permission to overwrite work. Check the current issue, active PRs, external artifact/version, latest checkpoint, and live work lease before reassignment.
5. If the work-item guard reports a duplicate key or a required key is missing, do not write code, source evidence, staging, certificates, or runtime state for that item until coordination is reconciled.
6. Progress messages are not new work items. Resume from the latest valid checkpoint and process only unfinished or invalidated units.
7. When duplicate issues are discovered, preserve conflicting evidence and provenance in the retained issue before closing duplicates. Never resolve a source disagreement merely by choosing the newest issue.

## Project context bootstrap

For any MLS architecture, Source Map, HỌC90 runtime, or corpus task, read
`docs/PROJECT_CONTEXT.md` after this file. Treat its dated checkpoint as orientation
only: refresh current `main`, the exact work item/work key, live Supabase state, and
assigned Drive evidence before acting. Never use a stale checkpoint count/status as
permission to write, certify, promote, or infer missing source evidence.

## Medical Learning System invariants

These rules override code-minimization when safety, provenance, or learner-state integrity requires more structure:

1. RAG/LLM extraction is evidence, not canonical medical truth.
2. Automatic extraction must never write directly into the Canonical Medical KG.
3. Candidate/Evidence Graph and Canonical Medical KG remain separate.
4. Student Model, Error Graph, Skill Tree, HỌC90 sessions, and learning events remain separate from medical truth.
5. Promoted medical assertions require source provenance and validation.
6. Preserve source identity, edition/year, file fingerprint, chapter/section, page, and evidence locator metadata when available.
7. Raw copyrighted textbooks stay outside Git. Google Drive is the source-material boundary.
8. GitHub owns executable machine contracts, routing logic, migrations, validation, and tests. Human-readable Drive documents may mirror these rules but must not silently diverge.
9. Supabase is the primary runtime store for learner/session state. Do not use a Google Doc as the primary database for mastery, errors, checkpoints, or retrieval history.
10. Source coverage and concept mastery are separate dimensions. Never infer mastery from chapter completion or exposure.
11. Learning events are append-only evidence. Do not overwrite prior learner responses to make history look cleaner.
12. Mastery must not increase merely because content was displayed or explained. It requires learner performance evidence.
13. A learner error may be recorded only after it is observed. Predicted misconceptions belong in lesson planning, not the observed Error Graph.
14. Large curriculum changes require learner approval. The router may make bounded within-session adaptations only.
15. Required-prerequisite branches must preserve a return-to-source-spine target and return after repair.
16. Textbook fidelity and current clinical validity are separate. Time-sensitive clinical claims need an explicit current-validity gate.
17. Do not silently repair or reinterpret imported KG v5 data; report migrations, merges, superseded artifacts, and conflicts.
18. Important teaching claims should remain traceable toward source evidence and the physical Drive source.

## Scope

These instructions apply to the whole repository unless a deeper AGENTS.md overrides them.

Upstream inspiration:
- https://github.com/DietrichGebert/ponytail

## Resumable Source Map worker skill

For bounded Source Map evidence/classification/repair work that may span many tool calls,
use the repo-scoped Codex skill at
`.codex/skills/resumable-source-map-worker/SKILL.md`. It defines the live-first resume,
scope-lock, dedup, artifact readback, concurrency, and checkpoint protocol. The skill does
not override a narrower user-authorized scope or the source-integrity invariants above.
