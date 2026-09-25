# Codex project context — Học nền tảng y học

Read this with `AGENTS.md` for Source Map, HỌC90, curriculum, agent-workflow, or cross-system tasks. This document describes product intent and where to find current state; its dated snapshot is **not** permission to write to runtime or an authority for a later turn.

## Product and source boundaries

- Goal: source-grounded medical learning from foundations through physiotherapy and rehabilitation. ChatGPT is the Vietnamese teaching interface; Google Drive holds original textbooks, human-readable Source Maps and curriculum; GitHub holds executable contracts, parser/RAG/router code, validation, tests and migrations; Supabase project `ggwxpmwtvyptwbiuhhsl` holds runtime learner and Source Map state.
- One HỌC90 session follows one original book/chapter as its source spine. Cover the book's Part → Chapter → Section → Subsection sequence without skipping source sections. Cross-search another book only to repair a prerequisite, explain a mechanism, compare conflicting claims, or make a clinical bridge. Preserve disagreements with their separate citations. A Knowledge Graph relates concepts; it does not replace the textbook or the Source Map.
- The learner studies about three hours daily in two 90-minute sessions, mainly on a phone. Teach in complete Vietnamese with essential English terms in parentheses. Retrieve the original source before new teaching; let the learner answer before hints; use progressively stronger hints, Feynman explanation, counterfactuals and clinical transfer. After an observed error, record evidence, invite self-correction and retest. Do not raise M0–M7 mastery for exposure or explanation. Source coverage and concept mastery are separate.
- Keep Student Model, Error Graph, Skill Tree, HỌC90 sessions/events and blueprints separate from medical truth. Learning events are append-only. Trace important claims to passage/figure/table/equation → printed/PDF page → chapter → edition → registered physical Drive file and fingerprint where available. Validate time-sensitive clinical thresholds, protocols, contraindications and doses against current evidence separately from textbook fidelity.
- Registered file identity needs internal source evidence and byte/fingerprint verification; a matching title, filename, file size or PDF bookmark is not proof. Native PDF/Docling preserve page/layout provenance; MarkItDown remains an optional Office/HTML/EPUB/text fallback. LangGraph is an optional Python library, not the Codex agent scheduler or a promotion path. Legacy KGv5 overlays are historical migration inputs, not the current architecture.

## Current milestone and work routing

Milestone [#97](https://github.com/dnma28/medical-learning-system/issues/97): complete Source Maps for 16 logical books. The issue body contains historical checkpoints and some resolved blocker text. Before doing work, re-read current `main`, open PRs/issues, [AI_WORK_QUEUE.md](AI_WORK_QUEUE.md), [SOURCE_MAP_STAGING_PROMOTION.md](SOURCE_MAP_STAGING_PROMOTION.md), the original Drive source and the Supabase migration/readiness/staging state. Use one claimed issue and immutable draft version per bounded batch. Record unresolved source observations as `REVIEW_REQUIRED` or `SOURCE_GAP`; do not fill them from model knowledge.

Staging proposals may be incomplete and remain outside runtime. A full-book certificate requires an independently reviewed printed/body TOC denominator, every required identity and locator, current physical/extraction fingerprints, all QA gates and zero required unresolved cases. Certification binds an exact immutable staging digest. Atomic promotion additionally checks the expected runtime version and readback. `replace_source_map` remains disabled. Neither a candidate count nor a successful staging insert makes a book `READY_FOR_HOC90`. Major curriculum changes require learner approval.

For bounded work, use `source_evidence_worker` (Luna) for original-source observations, `implementation_engineer` (Sol) for issue-scoped code, and `independent_reviewer` (Astra) for an independent audit. A reviewer must inspect the **latest exact staging version and digest** and original source, not rely on another agent's PASS claim. Issue/PR history is the durable handoff. Follow branch → focused checks → PR → CI → review → merge for code. Do not commit copyrighted textbook content, raw parser output, secrets or learner data.

## Dated readback — recheck before acting

Observed **2026-09-25 12:44 UTC** from current `main` `2b2d6f9661aa0484d9bcd417487de4b270d72d8e` and Supabase project `ggwxpmwtvyptwbiuhhsl`:

- 16 logical books, 55 registered physical sources, 45 physical SHA-256 values; migration 0012 and nested-subsection migration `20260925075830` applied.
- Four immutable staging rows: Neumann v1 and Costanzo v1–v3. Costanzo v3 digest `5140f8c0aad6e75e084bcc4c24d19690b17619b5ec96c3a17f089ac7b765e2c6` proposes `toc_denominator=894` (895 nodes including Book root). Its audit metadata reports heading QA complete **pending independent review** and has no reviewer attestation.
- Zero certificates, zero runtime Source Map nodes and zero books computed `READY_FOR_HOC90`. Costanzo readiness remains `unmapped / review_required` at runtime version 0. A staged v3 with no per-node review flags is still not a certificate or reviewer PASS.

Next bounded action is independent review of Costanzo's latest version, original PDF, scope decision (front matter, appendices, answers), body-heading inventory, locators and proposed denominator. If evidence changes, create a new immutable staging version and review its new digest. This checkpoint neither authorizes certification/promotion nor bulk imports, curriculum changes, learner-state changes or Canonical Medical KG writes.
