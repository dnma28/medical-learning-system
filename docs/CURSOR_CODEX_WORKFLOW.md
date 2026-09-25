# Cursor + Codex parallel workflow

Cursor is supported as a first-class interactive implementation client alongside Codex. It does **not** replace Git, GitHub, CI, repository tests, or the medical provenance model.

## Responsibility split

| Layer | Primary role |
|---|---|
| Astra / Luna / Sol sessions | reasoning, evidence work, architecture, review, coordination according to assigned role |
| Cursor | interactive code editing, local terminal commands, tests, diff inspection |
| Codex | delegated/scoped coding-agent implementation, terminal/test work, project agents and Codex plugins |
| GitHub | durable issues, branches, pull requests, review and CI |
| Drive / Supabase | source-material boundary and runtime data according to repository architecture |

## Safe concurrency

The default rule is **one issue = one implementation owner**.

If Cursor and Codex need to work at the same time:

1. Sync from `main`.
2. Give each client a separate issue/scope.
3. Use separate branches or worktrees.
4. Do not edit the same branch concurrently.
5. Commit before handoff.
6. Exchange durable context through the GitHub issue/PR.
7. Run relevant tests and review the diff.
8. Merge only after required CI/review gates pass.

Example branch names:

```text
cursor/issue-123-source-map-ui
codex/issue-124-staging-validation
```

## Cursor setup

Open the repository root in Cursor. The project rule in `.cursor/rules/medical-learning-system.mdc` tells Cursor to read and obey `AGENTS.md` and preserves the medical/source invariants.

Use Cursor's integrated terminal for the same repository commands you would run in another local terminal. Cursor is the editor/agent host; the shell remains the execution layer.

For Python development, install the repository environment according to the existing project setup. Optional agent-side Codex tooling in `scripts/setup_codex_extras.ps1` remains Codex-specific unless its upstream tool independently supports Cursor.

## Handoff: Cursor → Codex

Before handing a task to Codex:

- commit or push the current Cursor changes;
- record unresolved questions and test results in the issue/PR;
- tell Codex the exact issue, branch/worktree, allowed paths, and acceptance criteria;
- avoid asking Codex to continue from uncommitted Cursor state.

## Handoff: Codex → Cursor

Before continuing a Codex change in Cursor:

- fetch the Codex branch/PR;
- read the PR diff and test/CI state;
- check out that branch only after the Codex agent has stopped writing to it;
- continue with the same issue acceptance criteria.

## Graph tooling

Prefer GitNexus for code dependency/impact questions and Graphify for broader heterogeneous code/document exploration, as documented in `AGENT_STACK.md`. Generated graph state remains local and must not become medical truth.

## Authority

When instructions conflict, use this order:

1. safety/security and explicit user constraints;
2. repository `AGENTS.md` and deeper scoped `AGENTS.md` files;
3. tests, migrations, executable contracts and source provenance rules;
4. issue/PR acceptance criteria;
5. Cursor/Codex/plugin suggestions.

Editor or agent convenience never overrides provenance, validation, data-loss protection, or learner-state integrity.
