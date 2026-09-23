# Ponytail for Codex / Code

This repository already includes a root `AGENTS.md` with Ponytail-style rules, so
Codex-compatible coding agents that read repository instructions can apply the policy
without adding a runtime dependency to the Python project.

## Full Ponytail plugin

The upstream Ponytail project currently documents the Codex installation as:

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

Then start Codex, open `/hooks`, review and trust the two lifecycle hooks, and begin a
new thread.

The full plugin requires Node.js on PATH for its lifecycle hooks. Without Node.js, the
instruction/skill layer can still work but the always-on hook activation will not.

## Why Ponytail is not in pyproject.toml

Ponytail is an AI coding-agent plugin/instruction set, not a runtime Python dependency of
Medical Learning System. Adding it to the application dependency graph would couple
production code to a development-agent tool unnecessarily.

## Current repository integration

- `AGENTS.md`: always-on repository coding policy for compatible agents.
- Medical provenance and graph-separation invariants are included in the same file.
- RAG-Anything remains an application dependency; Ponytail remains a development-agent tool.

Upstream: https://github.com/DietrichGebert/ponytail
License: MIT
