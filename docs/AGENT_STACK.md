# Agent tooling stack

This repository keeps application/runtime dependencies separate from coding-agent tooling.

## Stack

- **Codex** — primary coding agent.
- **Ponytail policy** — repository-wide coding constraints in `AGENTS.md`.
- **Spec Kit v1.0.10** — spec-driven workflow for bounded changes.
- **OpenHarness v0.1.9** — optional agent harness for tools, skills, permissions, context, and long-running agent workflows.
- **Superpowers v6.4.1** — coding-agent methodology for planning, TDD, systematic debugging, verification, and code review.
- **Open Code Review v1.12.9** — specialized deterministic + agent review CLI, installed locally under `.agent-tools/open-code-review/`.

The medical safety and provenance invariants in `AGENTS.md` remain authoritative. Third-party agent tooling must not bypass or weaken them.

## Why this layout

Spec Kit's `codex` integration installs skills under `.agents/skills/`. OpenHarness discovers project skills from `.agents/skills/`, so both tools can share the same project-local workflow definitions without adding either tool to the medical application's runtime dependencies.

Superpowers is installed as an OpenHarness plugin from a pinned local checkout under `.agent-tools/superpowers/`. That directory is ignored by Git so third-party source is not vendored into this repository.

## Windows setup

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_agent_stack.ps1
```

The script pins:

- Spec Kit: `v1.0.10`
- OpenHarness: `v0.1.9`
- Superpowers: `v6.4.1`
- Open Code Review: `v1.12.9`

It installs Spec Kit and OpenHarness as isolated `uv` tools using Python 3.11, initializes Spec Kit in-place with the Codex integration when `.specify/` does not already exist, checks out Superpowers at the pinned tag, and installs it into OpenHarness.

### Verify

```powershell
specify version
specify integration status
oh --version
oh plugin list
oh --dry-run
```

OpenHarness still requires provider/auth configuration:

```powershell
oh setup
```

If you want OpenHarness to use your Codex subscription, choose the Codex Subscription provider during setup.

For native Codex App/CLI, Superpowers must still be installed through Codex's plugin UI (`/plugins`). The repository setup cannot modify a separate Codex client installation on your machine.

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

Superpowers complements this with TDD, systematic debugging, verification-before-completion, and review workflows. Open Code Review adds a dedicated diff/file review engine with deterministic file selection and line positioning. Prefer OCR delegation mode when the host coding agent should perform the reasoning without a separate model credential. When workflows disagree, repository-specific rules and medical safety/provenance invariants win.

For this repository, the constitution should preserve at least these existing rules:

1. Candidate/Evidence Graph never writes directly to Canonical Medical KG.
2. Promoted medical assertions require source provenance and validation.
3. Student/Error Graph remains separate from medical truth.
4. Preserve source identity, edition/year, fingerprint, and page/chapter metadata when available.
5. Raw copyrighted textbooks remain local and out of Git.
6. Keep changes minimal and reuse existing code before adding dependencies or abstractions.
7. Automated evals and LLM judges are quality signals, not medical truth authorities.

## Existing-project behavior

The setup intentionally uses:

```text
specify init --here --force --integration codex
```

This is the official existing-project initialization pattern. The script only runs that command when `.specify/` is absent so repeated setup does not overwrite an existing Spec Kit configuration.

## Privacy

Superpowers documents an opt-out for its optional visual-companion telemetry:

```powershell
$env:SUPERPOWERS_DISABLE_TELEMETRY = "true"
```

For persistent configuration, set the environment variable in your local user environment rather than committing secrets or machine-specific configuration.

## Updating later

Do not silently float versions in automation. Review upstream release notes first, then update the pinned versions in `scripts/setup_agent_stack.ps1`.


## Open Code Review in Codex

The setup script installs the pinned CLI locally, but Codex plugin registration is user-scoped and remains explicit:

```text
codex plugin marketplace add alibaba/open-code-review
```

Then open `/plugins`, install and enable **Open Code Review**, and start a new task. The plugin calls the local OCR CLI. Do not configure a second LLM provider unless standalone OCR-managed review is actually needed.

See `docs/THIRD_PARTY_TOOL_EVALUATION.md` for why the other candidate repositories were not installed.

## Multiple AI sessions

Use [AI_WORK_QUEUE.md](AI_WORK_QUEUE.md) for bounded issue claims, handoffs, independent review and change-specific gates. GitHub Issues and PRs carry durable state; a ChatGPT session ends when its turn ends.

## Optional LangGraph library

Install the existing MarkItDown adapter and the pinned LangGraph library together:

```bash
python -m pip install -e '.[markitdown,langgraph]'
python scripts/check_optional_tools.py
```

The smoke check converts a synthetic local HTML file through the existing
`ParsedDocument` adapter and runs a small LangGraph `StateGraph`. It uses
no model, external API, textbook, Supabase connection, or persistent store.
Installation does not start agents, issue polling, or unattended GitHub
workflows. GitHub Issues and PRs remain the work queue and review record
described in [AI_WORK_QUEUE.md](AI_WORK_QUEUE.md). Any later graph that
performs writes needs a scoped issue, explicit credentials, review gates,
and a separate implementation.

## Codex project agents

When you open a checkout of this repository in Codex, its project-scoped
`.codex/agents/` profiles are available when spawning subagents:

- `source_evidence_worker` — GPT-6 Luna, read-only textbook evidence review.
- `implementation_engineer` — GPT-6 Sol, scoped code work.
- `independent_reviewer` — GPT-6 Astra, read-only review.

The project caps concurrent subagents at three. A profile's `sandbox_mode` is a default; Codex reapplies the parent session's active permission and sandbox choices when spawning children. Set the parent session to read-only before relying on read-only profiles, and keep implementation sessions on the required scoped permissions. Ask the coordinator to delegate separate issue scopes, then wait for the reviewer before merging. Example:

```text
Use source_evidence_worker to inspect the assigned source batch, implementation_engineer to handle issue #N, and independent_reviewer to review the resulting diff. Keep their file scopes separate and wait for all results.
```

These profiles are instructions and model selections, not bundled model weights.
Codex uses models available to the signed-in account and client; model access
depends on rollout and plan. If a configured model is unavailable, edit that
profile to a model your Codex client offers. Subagent work uses additional
model/tool calls.

Install the optional project libraries in the checkout's Python environment with:

```bash
python -m pip install -e '.[markitdown,langgraph]'
```

MarkItDown is called through the existing adapter. LangGraph is a library for
Python workflows. Installing it does not connect it to Codex subagents or start
an autonomous runner; any such bridge needs its own scoped implementation,
credentials, and review gates.
