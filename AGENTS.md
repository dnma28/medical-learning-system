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
- Never commit secrets, API keys, local RAG storage, parser output, or copyrighted textbook binaries.

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
