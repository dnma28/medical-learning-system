# Roadmap

## Completed foundations

### v0.1–v0.8.x — source, retrieval, evidence, and KG foundation

- Candidate/Evidence Graph separated from Canonical Medical KG.
- Provenance-first evidence and source identity.
- PDF parsing, native text, outline, and evidence alignment.
- Google Drive source materialization.
- Supabase source/evidence storage and cloud compilation path.
- Retrieval benchmarks and embedding candidate evaluation.
- Claim fidelity/current-validity review.
- Candidate Graph materialization.
- Relation-to-claim support and append-only claim/relation audit ledgers.
- Lossless KG v5 migration/audit path.

## v0.9 — Adaptive HỌC90 runtime — COMPLETED

- Evidence-based learner mastery M0–M7.
- Learner Error Graph with observed-error history.
- Resumable HỌC90 sessions with checkpoint state.
- Append-only learning events written after meaningful responses.
- Learning Router priorities: retrieval → required prerequisite → observed error → source spine → bounded expansion/transfer.
- Separate source coverage from concept mastery.
- Supabase runtime schema for sessions, mastery, errors, source coverage, skill tree, and blueprints.
- Align repository documentation with Drive v6 architecture.

### v0.9 completion gates

- Supabase migration dry-run passes.
- Unit tests cover runtime state and routing invariants.
- Runtime state store is validated against the cloud schema.
- One real HỌC90 session can be persisted, paused, and resumed without transcript dependence.
- One real concept can accumulate retrieval evidence without auto-promoting mastery from exposure.

## v0.10 — Source Map + Book Registry normalization — CURRENT

- Mirror the Drive logical-book registry into machine-readable source metadata.
- Normalize full-book vs split-file representations.
- Build/validate full TOC Source Maps for the corpus.
- Add learning-value classification: CORE_MASTERY / SUPPORTING / REFERENCE_ONLY / CURRENT_CLINICAL_CHECK.
- Preserve source identity/edition/page/chapter mappings.
- Sync the 16 logical books into Supabase runtime metadata.
- Keep physical-source file identity separate from logical-book identity.
- Close known unindexed-foreign-key performance findings.

## v0.11 — Multimodal source retrieval

- Retrieve figure + caption + surrounding passage as one evidence unit.
- Improve table/equation retrieval and semantic indexing.
- Preserve page regions/bounding boxes where parser support exists.
- Add visual evidence benchmark cases for anatomy, histology, neuroscience, and physiology graphs.

## v0.12 — Curriculum + blueprint runtime

- Store learner-approved curriculum versions.
- Generate dynamic HỌC90 blueprints from curriculum + Student Model + Error Graph + Skill Tree.
- Keep large curriculum changes human-approved.
- Add session-start bootstrap: current lesson, due retrieval, active source spine, checkpoint.

## v0.13 — Game-like learning dashboard

- Skill tree visualization.
- Mastery/retention/open-error/review queue views.
- Chapter/source coverage view separate from mastery.
- Locked/unlocked prerequisite visualization.
- Keep streak/XP secondary to evidence-based competence.

## v0.14 — ChatGPT/backend bridge

- Expose a least-privilege backend contract for ChatGPT to read/write learner runtime state.
- Support `HỌC 90: bắt đầu` and `HỌC 90: tiếp tục` with one runtime bootstrap call.
- Never expose service credentials to the model/client.
- Audit all state-changing calls.

## Continuous quality

- Unit/integration tests first.
- Retrieval regression benchmarks.
- Prompt/RAG evaluation as quality signals only.
- Manual source/provenance review for medically important failures.
- Explicit validation remains required before canonical medical promotion.
