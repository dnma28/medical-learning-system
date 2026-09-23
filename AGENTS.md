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

These rules override code-minimization when safety or provenance requires more structure:

1. RAG/LLM extraction is evidence, not canonical medical truth.
2. Automatic extraction must never write directly into the Canonical Medical KG.
3. Candidate/Evidence Graph and Canonical Medical KG remain separate.
4. Student Model and Error Graph remain separate from medical truth.
5. Promoted medical assertions require source provenance and validation.
6. Preserve source identity, edition/year, file fingerprint, and page/chapter metadata when available.
7. Do not silently repair or reinterpret imported KG v5 data; report migrations and conflicts.
8. Raw copyrighted textbooks stay local and out of Git.

## Scope

These instructions apply to the whole repository unless a deeper AGENTS.md overrides them.

Upstream inspiration:
- https://github.com/DietrichGebert/ponytail
