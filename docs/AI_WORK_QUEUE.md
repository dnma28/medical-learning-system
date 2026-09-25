# AI work queue for the medical learning system

GitHub Issues are the durable work queue. A bounded issue owns one deliverable; a branch and PR carry its code. Google Drive remains the original textbook store, and Supabase stores runtime learner/source state. ChatGPT or a local agent session may act as the coordinator, but a chat transcript is not the handoff record.

This protocol supplements `AGENTS.md` and the Source Map staging contract. It does not change medical truth, curriculum, or production permissions.

## Roles and concurrency

| Role | Responsibility | Write boundary |
| --- | --- | --- |
| Coordinator | Read live main, issue/PR queue and dependencies; split a milestone into bounded issues; assign owner, reviewer and acceptance criteria; track blocked work. | Issues and project board only; no medical promotion. |
| Source evidence worker | Extract TOC, headings, source identity and page locators from original Drive files; report unresolved observations. | Versioned external staging drafts; no runtime import or certificate. |
| Engineer | Make a focused branch for parser, Source Map, Supabase or HỌC90 implementation; run relevant tests. | Scoped code/schema/test paths in the assigned issue. |
| Reviewer | Independently check source evidence, contract invariants, tests and changed paths; resolve disagreements with evidence. | Review comments; a reviewer may request changes but cannot manufacture missing evidence. |
| Maintainer | Check reviews, required CI and migration/source gates; merge reviewed PRs. | Merge/release only after gates. |

Start with one coordinator, two or three independent workers, and one reviewer. Increase workers only when their inputs, file paths, and review capacity are independent. Source books may be processed in parallel; certification of a book is a separate serial gate. Agent names/models are suggestions, not authority: a lower-cost model may do deterministic extraction, while the reviewer handles uncertain identity, hierarchy and clinical implications.

## Task lifecycle

1. Coordinator reads current main, open PRs, issue dependencies and external draft versions. Create or update one issue per bounded artifact; use the issue template. A milestone issue such as #97 remains the parent, not a shared writable task.
2. Mark `Ready` only when inputs and acceptance checks are specified. Record one owner and one independent reviewer in the issue. A worker claims by posting `CLAIM: <handle/session>; scope: <paths/book/batch>; base: <main SHA>; expires: <UTC time>`. The coordinator acknowledges the claim before work begins. GitHub comments are not an atomic lock: if duplicate claims appear, stop the later claimant and reassign it. Before expiry the owner renews with a new UTC time and progress checkpoint. After expiry the coordinator checks for an active PR or write, posts a reclaim notice, and reassigns only after confirming the old worker has stopped; the new worker starts from current main and an immutable draft version rather than overwriting prior work.
3. Code workers use one branch/PR per issue, cite the issue and base commit, and stay within the declared paths. Evidence workers save versioned drafts outside Git and link a manifest without textbook text, PDF bytes or secrets. Record fingerprints, parser/version, physical Drive file identity, unresolved cases and QA result. Never equate an extracted candidate count with the printed/body TOC denominator.
4. Hand off with changed paths or draft version, exact checks and results, remaining gaps, and next action. A worker may create subissues but the coordinator approves dependencies and nonoverlapping scopes before parallel execution.
5. Reviewer compares the output with original source evidence where needed, checks affected sibling code and calls, and either approves or returns specific changes. Conflicting conclusions become `REVIEW_REQUIRED` or `SOURCE_GAP` with both claims and locators retained; no majority vote.
6. Maintainer merges only when the independent review and required CI pass, no newer main invalidates the branch, and the issue's risk-specific gates pass. Record resulting SHA and close the issue. On failure, retain the branch/draft and mark `Blocked`; never silently retry a production write.

Suggested Project columns: Backlog, Ready, Claimed, In progress, Review, Blocked, Done. The issue and PR remain the source of truth if Projects is unavailable. Labels are optional; issue fields and comments are sufficient to start. Never use a file such as `TASK_STATE.json` as a competing mutable queue.

## Gates by change

| Change | Required evidence before merge or promotion |
| --- | --- |
| Documentation or task policy | Scope review and consistency with `AGENTS.md`; no runtime change. |
| Code/parser | Focused regression test for nontrivial behavior, full CI, reviewer checks provenance and other callers. |
| SQL/runtime migration | Dry run, synthetic transactional integration and rollback, access grants/RLS review, CI; production apply is a separate recorded step. |
| Source Map draft | Original Drive identity and physical/extraction fingerprints; TOC, hierarchy, locator and binding QA. Retain unresolved nodes in staging. |
| Source Map certificate/promotion | Full printed/body TOC denominator, zero unresolved required cases, independent source audit, exact immutable staging digest, expected runtime version, atomic RPC and readback. See `SOURCE_MAP_STAGING_PROMOTION.md`. |
| Canonical medical claim/current clinical protocol | Passage/figure/table provenance plus validation; check current clinical evidence separately. No automated promotion from parser or LLM output. |
| Curriculum or learner state | User approval for major curriculum changes; append-only learner events and observed performance for mastery changes. |

## Parser routing and cost

Use native PDF extraction and Docling for textbook PDFs where page/layout provenance matters. MarkItDown 0.1.8 is already installed as an optional Office/HTML/EPUB/text fallback through `markitdown_adapter.py`; it turns content into `ParsedDocument`. Its Markdown does not establish PDF page coordinates, printed page labels, verified ranges or a full-book denominator. If it is explicitly used on a PDF, preserve the fallback flag and independently verify every anchor before certification. Avoid a second orchestrator or parser platform until measured failures justify it.

Prefer batch deterministic extraction and small review queues. Run models on ambiguous cases with source snippets and locators rather than sending whole copyrighted books into GitHub issues, logs or PRs. CI should be deterministic and avoid model/API calls. One coordinator can operate from ChatGPT sessions using GitHub as durable state; continuous unattended execution would need separate credentials, runner, budgets and access controls. This protocol does not imply that a ChatGPT session continues after it ends.

## Current priority

For milestone #97, the architecture/staging RPC exists, but the corpus still needs source identity, complete TOC denominators, verified hierarchy and locators, and independent QA for 16 logical books. Split extraction by book or nonoverlapping batch; keep reviews serial per book. Complete a single pilot before any full-corpus promotion. Do not use MarkItDown to turn uncertain PDF locators into `verified`.
