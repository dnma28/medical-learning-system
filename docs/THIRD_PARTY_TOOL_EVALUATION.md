# Third-party repository evaluation — 2026-09-24

This review evaluates candidate repositories against the Medical Learning System architecture.
Selection follows the repository's Ponytail rule: add a tool only when it fills a real gap that the existing stack does not already cover.

| Candidate | Evaluated repository | Decision | Reason |
|---|---|---|---|
| MarkItDown | `microsoft/markitdown` | **Install** | Adds a lightweight, LLM-oriented fallback for DOCX/PPTX/XLSX/XLS/HTML/EPUB/text. It complements Docling/native PDF rather than replacing them. |
| Humanizer | `blader/humanizer` | Do not install | Rewriting prose is not a project bottleneck and can conflict with source fidelity/medical terminology. Humanization belongs at final presentation time, not source ingestion or canonical knowledge. |
| agent-skills | `addyosmani/agent-skills` | Do not install as a pack | Strong engineering workflows, but substantial overlap with Spec Kit + Superpowers + Ponytail. Full installation would increase instruction/context competition. Individual skills may be reconsidered only for a demonstrated gap. |
| agent-search | `brcrusoe72/agent-search` | Defer | Useful self-hosted SearXNG layer with PubMed/Scholar/OpenAlex/Crossref and injection scrubbing, but it adds Docker/search infrastructure. The current ChatGPT research path already covers current-validity checks; revisit when the backend itself must research autonomously. |
| WeKnora | `Tencent/WeKnora` | Do not install | It is a full RAG/knowledge-base platform with parsing, vector stores, GraphRAG, agents, MCP and UI. This duplicates the project's Drive → parser/RAG → Supabase → KG architecture and would create two sources of truth. |
| Orca | `ex-machina-co/opencode-orca` (most relevant agent-orchestration match) | Do not install | OpenCode-specific orchestrator; overlaps Codex + OpenHarness + Superpowers and adds another planner/specialist state machine. If a different `orca` repository was intended, evaluate by exact `owner/repo` before any installation. |
| ECC | `affaan-m/ECC` | Do not install as a full system | Powerful but very large agent methodology/runtime (agents, skills, hooks, memory). It overlaps the current agent stack and would materially increase context and policy collision risk. |
| Open Code Review | `alibaba/open-code-review` | **Install** | Adds a specialized deterministic + agent code-review layer that the current stack does not provide. Keep it local to agent tooling and use delegation mode when possible. |

## Installed integration

### Microsoft MarkItDown v0.1.8

Project extra:

```powershell
pip install -e ".[markitdown]"
```

The extra installs the Office-format dependencies used by the project. `markitdown_adapter.py` normalizes Markdown into the existing parser-neutral `ParsedDocument` contract.

Important boundary:

- native PDF / Docling remains the default for medical textbook PDFs because those paths preserve page/layout provenance better;
- MarkItDown PDF conversion is blocked by default and requires an explicit fallback decision;
- MarkItDown output is Evidence, never Canonical Medical Knowledge.

### Alibaba Open Code Review v1.12.9

`scripts/setup_agent_stack.ps1` installs the pinned CLI locally under:

```text
.agent-tools/open-code-review/
```

This keeps Node/binary tooling out of the Python medical runtime.

Verify:

```powershell
.agent-tools\open-code-review\node_modules\.bin\ocr.cmd --version
```

For Codex integration:

```text
codex plugin marketplace add alibaba/open-code-review
```

Then install **Open Code Review** from `/plugins`. Prefer delegation mode when the host coding agent should perform the review without a separate OCR model credential.

## Re-evaluation triggers

Reconsider deferred/rejected tools only when a concrete missing capability appears:

- install AgentSearch when autonomous backend research becomes a requirement;
- reconsider one specific agent-skill when an existing workflow repeatedly fails to cover that need;
- reconsider WeKnora only if the project decides to replace, rather than complement, its custom RAG/backend architecture;
- reconsider ECC/Orca only if the primary coding-agent architecture itself is intentionally replaced.


## Codex extras requested on 2026-09-25

These additions are agent-side tooling only. They do not enter the Python
medical runtime and do not become medical knowledge sources.

| Candidate | Upstream | Decision | Boundary |
|---|---|---|---|
| Matt Pocock skills | `mattpocock/skills` @ `c55ee46073ed923f86ce59a5eb3b6d895095d1b7` | **Install for Codex** | Install the pinned bundle through the Agent Skills installer. It already includes `grill-me` and `to-prd`; avoid duplicate installations from similarly named repositories. |
| Caveman | `JuliusBrussee/caveman` @ `2fd153c67988e980fb0b2455c90832159a6a5a25` | **Install, explicit-only** | Useful for terse agent communication and compact review output. It must not remove evidence, paths, errors, commands, or medical provenance detail. |
| Graphify | `Graphify-Labs/graphify` @ `8e09034743280ecc5ff2201b27c0ccae31f61966` / PyPI `graphifyy==0.9.67` | **Install as optional graph tooling** | Use for local code/document graph exploration. It must remain separate from Source Maps and the Canonical Medical KG. |
| GitNexus | `abhigyanpatwari/GitNexus` @ `v1.6.12` | **Install as Codex plugin** | Use for local code intelligence and impact analysis. Plugin hooks require explicit Codex trust. Re-evaluate licensing before any commercial deployment. |
| grill-me | Included in `mattpocock/skills` | **No separate repo install** | Prevents duplicate skill names and instruction collisions. |
| to-prd | Included in `mattpocock/skills` | **No separate repo install** | Prevents duplicate skill names and keeps issue-tracker setup in one bundle. |

The installation entry point is `scripts/setup_codex_extras.ps1`. Graphify
and GitNexus are deliberately not wired as simultaneous always-on graph
engines: GitNexus is the default for code dependency/impact questions;
Graphify is reserved for broader heterogeneous graph exploration.
