# Roadmap

## Phase 0 — v0.1 scaffold — COMPLETE
- Stable module boundaries.
- Canonical vs candidate graph split.
- Provenance-first schema.
- RAG-Anything adapter boundary.
- Student/Error Graph separated from medical truth.

## Phase 0.5 — v0.2 executable first-book RAG — CURRENT
- Installable RAG-Anything dependency.
- MinerU default parser.
- OpenAI-compatible provider.
- Local source manifest + SHA-256 file fingerprint.
- CLI for one-book ingest and hybrid query.
- Copyrighted source files and API secrets excluded from Git.
- Lightweight CI.

## Phase 1 — v0.3 evidence provenance + Knowledge Graph v5 import
- Export parsed blocks with page_idx into explicit Evidence records.
- Map current KG v5 node/edge/guard JSON into typed schema.
- Preserve existing IDs and source provenance.
- Create migration report; do not silently repair data.
- Add schema validation and duplicate-ID checks.

## Phase 2 — multimodal ingest hardening
- Add Docling fallback/verification path.
- Persist chapter/figure/table/equation provenance.
- Keep automatic extraction outputs in candidate storage.

## Phase 3 — Biomedical normalization
- Add terminology normalization where licensing permits.
- Alias resolution and duplicate concept detection.
- Contradiction detection and cross-book evidence aggregation.

## Phase 4 — Canonical graph backend
- Move validated graph to Neo4j.
- Add graph + vector hybrid retrieval.
- Add typed relation constraints and graph tests.

## Phase 5 — Adaptive learning
- Versioned Student Model.
- Error Graph with misconception history.
- HỌC90 router consuming canonical concepts + retrieved evidence.
- Spaced retrieval scheduling and weekly assessment.

## Phase 6 — Evaluation
- Build a medical gold set.
- Evaluate retrieval relevance, faithfulness, citation completeness, and regression.
- Add RAGAS or equivalent evaluation harness.