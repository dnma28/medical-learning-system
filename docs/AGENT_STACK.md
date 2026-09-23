# Agent tooling stack

This repository keeps application/runtime dependencies separate from coding-agent tooling.

## Stack

- **Codex** — primary coding agent.
- **Ponytail policy** — repository-wide coding constraints in `AGENTS.md`.
- **Spec Kit v1.0.10** — spec-driven workflow for bounded changes.
- **OpenHarness v0.1.9** — optional agent harness for tools, skills, permissions, context, and long-running agent workflows.

The medical safety and provenance invariants in `AGENTS.md` remain authoritative. Agent tooling must not bypass them.

## Why this layout

Spec Kit's `codex` integration installs skills under `.agents/skills/`. OpenHarness discovers project skills from `.agents/skills/`, so both tools can share the same project-local workflow definitions without adding either tool to the medical application's runtime dependencies.

## Windows setup

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_agent_stack.ps1
```

The script pins:

- Spec Kit: `v1.0.10`
- OpenHarness: `v0.1.9`

It installs both as isolated `uv` tools using Python 3.11, then initializes Spec Kit in-place with the Codex integration when `.specify/` does not already exist.

### Verify

```powershell
specify version
specify integration status
oh --version
oh --dry-run
```

OpenHarness still requires provider/auth configuration:

```powershell
oh setup
```

If you want OpenHarness to use your Codex subscription, choose the Codex Subscription provider during setup.

## Spec Kit workflow in Codex

After initialization, use the generated Codex skills in this order for a bounded feature:

```text
$speckit-constitution
$speckit-specify
$speckit-plan
$speckit-tasks
$speckit-implement
$speckit-converge
```

For this repository, the constitution should preserve at least these existing rules:

1. Candidate/Evidence Graph never writes directly to Canonical Medical KG.
2. Promoted medical assertions require source provenance and validation.
3. Student/Error Graph remains separate from medical truth.
4. Preserve source identity, edition/year, fingerprint, and page/chapter metadata when available.
5. Raw copyrighted textbooks remain local and out of Git.
6. Keep changes minimal and reuse existing code before adding dependencies or abstractions.

## Existing-project behavior

The setup intentionally uses:

```text
specify init --here --force --integration codex
```

This is the official existing-project initialization pattern. The script only runs that command when `.specify/` is absent so repeated setup does not overwrite an existing Spec Kit configuration.

## Updating later

Do not silently float versions in automation. Review upstream release notes first, then update the pinned versions in `scripts/setup_agent_stack.ps1`.
